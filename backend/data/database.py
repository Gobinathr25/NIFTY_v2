"""
SQLite persistence — extended with session_store for access token persistence.
Token stored AES-encrypted. Trades/positions/P&L same as before.
"""
from __future__ import annotations
import os, json
from datetime import datetime, date
from typing import List, Dict, Optional

from sqlalchemy import (
    create_engine, text, MetaData, Table, Column,
    Integer, Float, String, DateTime, Date, Text, Boolean
)
from core.config import DB_PATH
from utils.logger import get_logger

log = get_logger(__name__)
engine   = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})
metadata = MetaData()

# ── Tables ────────────────────────────────────────────────────────────────────
trades_table = Table("trades", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("trade_date",       Date,    nullable=False),
    Column("entry_time",       DateTime),
    Column("exit_time",        DateTime),
    Column("ce_strike",        Integer),
    Column("pe_strike",        Integer),
    Column("ce_entry_px",      Float),
    Column("pe_entry_px",      Float),
    Column("ce_current_px",    Float),
    Column("pe_current_px",    Float),
    Column("ce_hedge_strike",  Integer),
    Column("pe_hedge_strike",  Integer),
    Column("ce_hedge_px",      Float),
    Column("pe_hedge_px",      Float),
    Column("quantity",         Integer),
    Column("premium_collected",Float),
    Column("realized_pnl",     Float),
    Column("unrealized_pnl",   Float),
    Column("status",           String(20), default="OPEN"),
    Column("close_reason",     String(50)),
    Column("adjustment_level", Integer, default=0),
    Column("adjustment_log",   Text),
    Column("net_delta",        Float),
    Column("gamma_score",      Float),
    Column("strategy_type",    String(30), default="GAMMA_STRANGLE"),
)

adjustments_table = Table("adjustments", metadata,
    Column("id",          Integer, primary_key=True, autoincrement=True),
    Column("trade_id",    Integer, nullable=False),
    Column("adj_time",    DateTime),
    Column("level",       Integer),
    Column("action",      String(100)),
    Column("reason",      String(200)),
    Column("spot_at_adj", Float),
    Column("pnl_at_adj",  Float),
)

daily_summary_table = Table("daily_summary", metadata,
    Column("id",             Integer, primary_key=True, autoincrement=True),
    Column("trade_date",     Date,    unique=True),
    Column("total_trades",   Integer, default=0),
    Column("winning_trades", Integer, default=0),
    Column("net_pnl",        Float,   default=0.0),
    Column("max_drawdown",   Float,   default=0.0),
    Column("capital_used",   Float,   default=0.0),
    Column("win_rate",       Float,   default=0.0),
    Column("notes",          Text),
)

# ── Session store — persists access token across browser sessions ─────────────
session_store_table = Table("session_store", metadata,
    Column("id",            Integer, primary_key=True, autoincrement=True),
    Column("key",           String(64), unique=True, nullable=False),
    Column("value",         Text),
    Column("created_at",    DateTime, default=datetime.now),
    Column("updated_at",    DateTime, default=datetime.now),
    Column("expires_at",    DateTime),   # NULL = never expires
)


def init_db() -> None:
    metadata.create_all(engine)
    log.info("Database initialised at %s", DB_PATH)


# ── Session store CRUD ────────────────────────────────────────────────────────
def session_set(key: str, value: str, expires_at: Optional[datetime] = None) -> None:
    with engine.begin() as conn:
        existing = conn.execute(
            session_store_table.select().where(session_store_table.c.key == key)
        ).fetchone()
        now = datetime.now()
        if existing:
            conn.execute(session_store_table.update()
                .where(session_store_table.c.key == key)
                .values(value=value, updated_at=now, expires_at=expires_at))
        else:
            conn.execute(session_store_table.insert().values(
                key=key, value=value, created_at=now, updated_at=now, expires_at=expires_at))

def session_get(key: str) -> Optional[str]:
    with engine.connect() as conn:
        row = conn.execute(
            session_store_table.select().where(session_store_table.c.key == key)
        ).fetchone()
    if not row:
        return None
    # Check expiry
    if row.expires_at and datetime.now() > row.expires_at:
        session_delete(key)
        return None
    return row.value

def session_delete(key: str) -> None:
    with engine.begin() as conn:
        conn.execute(session_store_table.delete().where(session_store_table.c.key == key))


# ── Trade CRUD ────────────────────────────────────────────────────────────────
def insert_trade(trade: Dict) -> int:
    trade["trade_date"] = trade.get("trade_date", date.today())
    trade["entry_time"] = trade.get("entry_time", datetime.now())
    with engine.begin() as conn:
        result = conn.execute(trades_table.insert().values(**trade))
        return result.inserted_primary_key[0]

def update_trade(trade_id: int, updates: Dict) -> None:
    with engine.begin() as conn:
        conn.execute(trades_table.update()
            .where(trades_table.c.id == trade_id).values(**updates))

def get_open_trades() -> List[Dict]:
    with engine.connect() as conn:
        rows = conn.execute(trades_table.select()
            .where(trades_table.c.status == "OPEN")).fetchall()
    return [dict(r._mapping) for r in rows]

def get_trades_for_date(d: date) -> List[Dict]:
    with engine.connect() as conn:
        rows = conn.execute(trades_table.select()
            .where(trades_table.c.trade_date == d)).fetchall()
    return [dict(r._mapping) for r in rows]

def get_all_trades() -> List[Dict]:
    with engine.connect() as conn:
        rows = conn.execute(trades_table.select()
            .order_by(trades_table.c.entry_time.desc())).fetchall()
    return [dict(r._mapping) for r in rows]

def get_trade_count_today() -> int:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT COUNT(*) FROM trades WHERE trade_date = :d"),
                           {"d": date.today()}).fetchone()
    return row[0] if row else 0

def insert_adjustment(adj: Dict) -> None:
    adj["adj_time"] = adj.get("adj_time", datetime.now())
    with engine.begin() as conn:
        conn.execute(adjustments_table.insert().values(**adj))

def get_adjustments_for_trade(trade_id: int) -> List[Dict]:
    with engine.connect() as conn:
        rows = conn.execute(adjustments_table.select()
            .where(adjustments_table.c.trade_id == trade_id)).fetchall()
    return [dict(r._mapping) for r in rows]

def upsert_daily_summary(summary: Dict) -> None:
    summary["trade_date"] = summary.get("trade_date", date.today())
    with engine.begin() as conn:
        existing = conn.execute(daily_summary_table.select()
            .where(daily_summary_table.c.trade_date == summary["trade_date"])).fetchone()
        if existing:
            conn.execute(daily_summary_table.update()
                .where(daily_summary_table.c.trade_date == summary["trade_date"])
                .values(**summary))
        else:
            conn.execute(daily_summary_table.insert().values(**summary))

def get_all_daily_summaries() -> List[Dict]:
    with engine.connect() as conn:
        rows = conn.execute(daily_summary_table.select()
            .order_by(daily_summary_table.c.trade_date.desc())).fetchall()
    return [dict(r._mapping) for r in rows]
