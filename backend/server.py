"""
FastAPI backend — NIFTY Options Paper Trading Terminal
Replaces Streamlit. Serves REST API + WebSocket + static React frontend.

Key advantages over Streamlit:
  - Session state lives on SERVER (not browser RAM)
  - Token persisted in DB — browser reopen = auto-restore
  - WebSocket = real-time data without page refresh
  - Telegram commands hit the same state as the UI
"""
from __future__ import annotations
import asyncio, json, os, sys
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))

from core.config import PAPER_MODE, IST
from data.database import (
    init_db, session_get, session_set, session_delete,
    get_open_trades, get_all_trades, get_all_daily_summaries, get_trade_count_today
)
from utils.logger import get_logger
from utils.fyers_login import (
    login_with_totp, send_sms_otp, login_with_sms_otp,
    FYERS_CLIENT_ID, FYERS_SECRET_KEY,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
)

log = get_logger("server")

# ── Global app state (server-side, survives browser refresh) ──────────────────
class AppState:
    strategy    = None
    scheduler   = None
    tg_listener = None
    access_token: Optional[str] = None
    is_logged_in: bool = False
    capital:    float = 500_000
    risk_pct:   float = 2.0
    num_lots:   int   = 1

state = AppState()

# ── WebSocket connection manager ──────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

ws_manager = ConnectionManager()


# ── Lifespan: startup / shutdown ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _restore_session()
    _start_tg_listener()
    yield
    if state.scheduler:
        try: state.scheduler._scheduler.shutdown(wait=False)
        except: pass
    if state.tg_listener:
        state.tg_listener.stop()


def _restore_session():
    """On server start, restore access token from DB if valid."""
    token = session_get("access_token")
    if token:
        state.access_token = token
        state.is_logged_in = True
        _init_strategy(token)
        log.info("Session restored from database.")
    else:
        log.info("No saved session found — login required.")


def _init_strategy(token: str):
    """Build strategy + scheduler from token. Safe to call multiple times."""
    try:
        from data.fyers_client import FyersClient
        from alerts.telegram import TelegramNotifier
        from core.strategy import GammaStrangleStrategy
        from core.scheduler import TradingScheduler

        client   = FyersClient(FYERS_CLIENT_ID, token)
        notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

        strategy = GammaStrangleStrategy(
            fyers=client,
            capital=state.capital,
            risk_pct=state.risk_pct,
            num_lots=state.num_lots,
            telegram_fn=notifier.send,
        )
        state.strategy = strategy

        if state.scheduler is None:
            sched = TradingScheduler()
            def _eod():
                s = strategy.generate_eod_summary()
                notifier.send_eod_report(s["total_trades"], s["net_pnl"],
                                         s["max_drawdown"], s["win_rate"])
            sched.setup(
                on_market_open   = strategy.start,
                on_no_new_trades = strategy.stop,
                on_force_close   = lambda: strategy.close_all_positions("FORCE_CLOSE"),
                on_eod_report    = _eod,
                on_monitor       = strategy.monitor_positions,
            )
            sched.start()
            state.scheduler = sched

        log.info("Strategy engine initialised.")
        return True, "Strategy initialised successfully."
    except Exception as e:
        log.error("Strategy init error: %s", e, exc_info=True)
        return False, str(e)


def _start_tg_listener():
    """Start Telegram command listener once."""
    if state.tg_listener or not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("X"):
        return

    from alerts.telegram_commands import TelegramCommandListener
    listener = TelegramCommandListener(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    def _tg_start():
        listener.send("Logging in via TOTP...")
        ok, result = login_with_totp()
        if not ok:
            listener.send("Login failed: " + result)
            return
        state.access_token = result
        state.is_logged_in = True
        session_set("access_token", result,
                    expires_at=datetime.now() + timedelta(hours=23))
        ok2, msg = _init_strategy(result)
        if ok2:
            state.strategy.start()
            cap  = state.capital
            lots = state.num_lots
            listener.send(
                "*Strategy Started!*\n"
                "Capital: Rs " + f"{cap:,.0f}" + "\n"
                "Lots: " + str(lots) + "\n"
                "Risk: " + f"{state.risk_pct}%" + "\n"
                "Auto entries at 09:20 IST."
            )
        else:
            listener.send("Strategy init failed: " + msg)

    def _tg_stop():
        if state.strategy is None:
            listener.send("No active strategy.")
            return
        count = len(state.strategy.active_positions)
        state.strategy.close_all_positions("TELEGRAM_STOP")
        state.strategy.stop()
        listener.send("*Stopped.* Closed " + str(count) + " position(s).")

    def _tg_status():
        s = state.strategy
        if s is None:
            listener.send("Strategy not initialised.")
            return
        running = "Running" if getattr(s, "is_running", False) else "Stopped"
        mtm     = s.calculate_mtm()
        spot    = getattr(s, "spot", 0)
        pnl     = getattr(s, "_daily_pnl", 0)
        listener.send(
            "*Status: " + running + "*\n"
            "Spot: " + f"{spot:,.2f}" + "\n"
            "Positions: " + str(len(s.active_positions)) + "\n"
            "MTM PnL: Rs " + f"{mtm:,.0f}" + "\n"
            "Daily PnL: Rs " + f"{pnl:,.0f}" + "\n"
            "Delta: " + f"{s.get_net_delta():.2f}" + "\n"
            "Gamma Risk: " + f"{s.get_gamma_risk_score():.0f}" + "/100"
        )

    def _tg_pause():
        if state.strategy:
            state.strategy.stop()
            listener.send("Paused. Positions kept open.")

    def _tg_resume():
        if state.strategy:
            state.strategy.start()
            listener.send("Resumed.")

    listener.on_start  = _tg_start
    listener.on_stop   = _tg_stop
    listener.on_status = _tg_status
    listener.on_pause  = _tg_pause
    listener.on_resume = _tg_resume
    listener.start()
    state.tg_listener = listener
    log.info("Telegram command listener started.")


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="NIFTY Terminal", lifespan=lifespan)

app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Auth routes ───────────────────────────────────────────────────────────────
class TOTPLoginRequest(BaseModel):
    pass  # credentials are hardcoded

class SMSOTPRequest(BaseModel):
    otp: str

class StrategyParamsRequest(BaseModel):
    capital:  Optional[float] = None
    risk_pct: Optional[float] = None
    num_lots: Optional[int]   = None


@app.post("/api/login/totp")
async def login_totp():
    ok, result = login_with_totp()
    if not ok:
        raise HTTPException(400, detail=result)
    state.access_token = result
    state.is_logged_in = True
    # Persist token — expires in 23h (Fyers tokens last 24h)
    session_set("access_token", result,
                expires_at=datetime.now() + timedelta(hours=23))
    ok2, msg = _init_strategy(result)
    if not ok2:
        raise HTTPException(500, detail=msg)
    return {"status": "ok", "message": "Login successful. Strategy initialised."}


@app.post("/api/login/sms/send")
async def sms_send():
    ok, msg = send_sms_otp()
    if not ok:
        raise HTTPException(400, detail=msg)
    return {"status": "ok", "message": msg}


@app.post("/api/login/sms/verify")
async def sms_verify(body: SMSOTPRequest):
    ok, result = login_with_sms_otp(body.otp)
    if not ok:
        raise HTTPException(400, detail=result)
    state.access_token = result
    state.is_logged_in = True
    session_set("access_token", result,
                expires_at=datetime.now() + timedelta(hours=23))
    ok2, msg = _init_strategy(result)
    if not ok2:
        raise HTTPException(500, detail=msg)
    return {"status": "ok", "message": "Login successful."}


@app.post("/api/logout")
async def logout():
    session_delete("access_token")
    state.access_token = None
    state.is_logged_in = False
    state.strategy     = None
    return {"status": "ok"}


# ── Status route ──────────────────────────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    s = state.strategy
    token_expiry = None
    stored = session_get("access_token")
    # Check DB for expiry info
    from data.database import engine, session_store_table
    with engine.connect() as conn:
        row = conn.execute(session_store_table.select()
            .where(session_store_table.c.key == "access_token")).fetchone()
        if row and row.expires_at:
            token_expiry = row.expires_at.isoformat()

    return {
        "logged_in":     state.is_logged_in,
        "token_saved":   bool(stored),
        "token_expiry":  token_expiry,
        "paper_mode":    PAPER_MODE,
        "strategy_ready": s is not None,
        "strategy_running": getattr(s, "is_running", False),
        "spot":           getattr(s, "spot", 0),
        "supertrend":     getattr(s, "supertrend_dir", "UNKNOWN"),
        "vwap":           getattr(s, "vwap", 0),
        "net_delta":      s.get_net_delta() if s else 0,
        "gamma_score":    s.get_gamma_risk_score() if s else 0,
        "mtm_pnl":        s.calculate_mtm() if s else 0,
        "daily_pnl":      getattr(s, "_daily_pnl", 0),
        "trades_today":   get_trade_count_today(),
        "open_positions": len(s.active_positions) if s else 0,
        "capital":        state.capital,
        "risk_pct":       state.risk_pct,
        "num_lots":       state.num_lots,
    }


# ── Strategy control routes ───────────────────────────────────────────────────
@app.post("/api/strategy/start")
async def strategy_start():
    if not state.strategy:
        raise HTTPException(400, detail="Strategy not initialised. Login first.")
    state.strategy.start()
    return {"status": "ok", "message": "Strategy started."}


@app.post("/api/strategy/stop")
async def strategy_stop():
    if not state.strategy:
        raise HTTPException(400, detail="No active strategy.")
    state.strategy.stop()
    return {"status": "ok", "message": "Strategy stopped."}


@app.post("/api/strategy/close-all")
async def strategy_close_all():
    if not state.strategy:
        raise HTTPException(400, detail="No active strategy.")
    state.strategy.close_all_positions("MANUAL_CLOSE")
    return {"status": "ok", "message": "All positions closed."}


@app.post("/api/strategy/params")
async def update_params(body: StrategyParamsRequest):
    if body.capital  is not None: state.capital  = body.capital
    if body.risk_pct is not None: state.risk_pct = body.risk_pct
    if body.num_lots is not None: state.num_lots = body.num_lots
    if state.strategy:
        state.strategy.capital  = state.capital
        state.strategy.risk_pct = state.risk_pct
        state.strategy.num_lots = state.num_lots
    return {"status": "ok"}


@app.post("/api/strategy/reset-day")
async def reset_day():
    if state.strategy:
        state.strategy.reset_day()
    return {"status": "ok"}


# ── Data routes ───────────────────────────────────────────────────────────────
@app.get("/api/positions")
async def get_positions():
    s = state.strategy
    if not s:
        return {"positions": [], "trades": get_open_trades()}
    result = []
    for trade_id, positions in s.active_positions.items():
        for p in positions:
            result.append({
                "trade_id":    trade_id,
                "symbol":      p.symbol,
                "strike":      p.strike,
                "option_type": p.option_type,
                "side":        p.side,
                "entry_px":    p.entry_price,
                "current_px":  p.current_price,
                "pnl":         p.unrealized_pnl,
                "delta":       p.greeks.get("delta", 0),
                "gamma":       p.greeks.get("gamma", 0),
                "theta":       p.greeks.get("theta", 0),
                "is_hedge":    p.is_hedge,
            })
    return {"positions": result, "count": len(result)}


@app.get("/api/trades")
async def get_trades():
    trades = get_all_trades()
    # Convert date/datetime to string for JSON
    for t in trades:
        for k, v in t.items():
            if hasattr(v, "isoformat"):
                t[k] = v.isoformat()
    return {"trades": trades}


@app.get("/api/pnl")
async def get_pnl():
    summaries = get_all_daily_summaries()
    for s in summaries:
        for k, v in s.items():
            if hasattr(v, "isoformat"):
                s[k] = v.isoformat()
    return {"summaries": summaries}


@app.get("/api/margin")
async def get_margin():
    if not state.strategy:
        raise HTTPException(400, detail="Strategy not initialised.")
    try:
        m = state.strategy.calculate_margin_required()
        return m
    except Exception as e:
        raise HTTPException(500, detail=str(e))


# ── WebSocket — live feed ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # Push live data every 2 seconds
            s = state.strategy
            data = {
                "type":           "tick",
                "logged_in":      state.is_logged_in,
                "strategy_ready": s is not None,
                "running":        getattr(s, "is_running", False),
                "spot":           getattr(s, "spot", 0),
                "supertrend":     getattr(s, "supertrend_dir", "UNKNOWN"),
                "vwap":           getattr(s, "vwap", 0),
                "net_delta":      s.get_net_delta() if s else 0,
                "gamma_score":    s.get_gamma_risk_score() if s else 0,
                "mtm_pnl":        s.calculate_mtm() if s else 0,
                "daily_pnl":      getattr(s, "_daily_pnl", 0),
                "open_positions": len(s.active_positions) if s else 0,
                "ts":             datetime.now(IST).isoformat(),
            }
            await ws.send_json(data)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ── Serve React frontend ──────────────────────────────────────────────────────
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        index = os.path.join(FRONTEND_DIST, "index.html")
        return FileResponse(index)
else:
    @app.get("/")
    async def root():
        return {"message": "NIFTY Terminal API running. Frontend not built yet."}
