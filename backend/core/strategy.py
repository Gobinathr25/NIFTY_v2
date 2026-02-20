"""
GammaStrangleStrategy — core strategy engine.

Paper Trading Mode:
- Never sends real orders to broker.
- Simulates fills at LTP.

Strategies implemented:
1. Supertrend-based Short Strangle (regular session)
2. Expiry version (ATM + 100 OTM, after 09:45)
3. Gamma Defence Model (3 levels)
"""

from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple

import pandas as pd

from core.config import (
    PAPER_MODE, IST,
    CE_DELTA_TARGET, PE_DELTA_TARGET, HEDGE_DELTA_TARGET,
    GAMMA_L1_SPOT_MOVE, GAMMA_L1_PREMIUM_PCT,
    GAMMA_L2_DELTA_LIMIT, GAMMA_L3_SPOT_MOVE, GAMMA_L3_TIME_WINDOW,
    MAX_RISK_PCT_DAY, MAX_TRADES_PER_DAY,
    EXPIRY_OTM_OFFSET, EXPIRY_TARGET_PCT, EXPIRY_STOP_MULT,
    SUPERTREND_PERIOD, SUPERTREND_MULT,
)
from core.indicators import (
    compute_supertrend, compute_vwap, black_scholes_greeks,
    estimate_iv_from_price, compute_gamma_risk_score,
)
from data.fyers_client import (
    FyersClient, build_option_symbol, get_nearest_weekly_expiry, round_to_strike
)
from data.database import (
    insert_trade, update_trade, get_open_trades, get_trade_count_today,
    insert_adjustment, get_adjustments_for_trade, upsert_daily_summary,
)
from utils.logger import get_logger

log = get_logger(__name__)

# ─── CONSTANTS ────────────────────────────────────────────────────────────────
NIFTY_LOT_SIZE = 65
STRIKE_STEP = 50


class Position:
    """Represents a single leg of a paper trade."""
    def __init__(
        self,
        symbol: str,
        strike: int,
        option_type: str,
        side: str,           # BUY / SELL
        entry_price: float,
        quantity: int,
        greeks: Dict,
        is_hedge: bool = False,
    ):
        self.symbol = symbol
        self.strike = strike
        self.option_type = option_type
        self.side = side
        self.entry_price = entry_price
        self.current_price = entry_price
        self.quantity = quantity
        self.greeks = greeks
        self.is_hedge = is_hedge
        self.entry_time = datetime.now(IST)

    @property
    def pnl(self) -> float:
        sign = -1 if self.side == "SELL" else 1
        return sign * (self.entry_price - self.current_price) * self.quantity

    @property
    def delta_exposure(self) -> float:
        sign = -1 if self.side == "SELL" else 1
        return sign * self.greeks.get("delta", 0.0) * self.quantity


class GammaStrangleStrategy:
    """
    Full gamma strangle strategy engine with paper trading simulation.
    
    Methods:
        check_entry()
        open_position()
        monitor_positions()
        adjust_positions()
        close_position()
        calculate_mtm()
        get_net_delta()
        get_gamma_risk_score()
    """

    def __init__(
        self,
        fyers: FyersClient,
        capital: float = 10_00_000,
        risk_pct: float = 2.0,
        num_lots: int = 1,
        telegram_fn=None,
    ):
        assert PAPER_MODE, "Strategy instantiated outside PAPER_MODE — abort!"
        self.fyers = fyers
        self.capital = capital
        self.risk_pct = risk_pct
        self.num_lots = max(1, num_lots)
        self._send_alert = telegram_fn or (lambda msg: None)

        self.is_running = False
        self._lock = threading.Lock()

        # In-memory position registry {trade_id: [Position, ...]}
        self.active_positions: Dict[int, List[Position]] = {}
        self.entry_spot: Dict[int, float] = {}
        self.entry_time: Dict[int, datetime] = {}
        self.adjustment_counts: Dict[int, int] = {}
        self.trade_premium: Dict[int, float] = {}  # total premium collected

        # Live market state
        self.spot: float = 0.0
        self.supertrend_dir: str = "UNKNOWN"
        self.vwap: float = 0.0
        self.candles_df: Optional[pd.DataFrame] = None

        # Daily counters
        self._trade_date: date = date.today()
        self._trades_today: int = 0
        self._daily_pnl: float = 0.0

    # ─── PUBLIC API ───────────────────────────────────────────────────────────

    def start(self) -> None:
        self.is_running = True
        log.info("[PAPER] Strategy started.")

    def stop(self) -> None:
        self.is_running = False
        log.info("[PAPER] Strategy stopped.")

    def reset_day(self) -> None:
        """Reset all daily counters and close any open positions."""
        with self._lock:
            for trade_id in list(self.active_positions.keys()):
                self._force_close_trade(trade_id, reason="DAY_RESET")
            self.active_positions.clear()
            self.entry_spot.clear()
            self.entry_time.clear()
            self.adjustment_counts.clear()
            self.trade_premium.clear()
            self._trades_today = 0
            self._daily_pnl = 0.0
            self._trade_date = date.today()
        log.info("[PAPER] Day reset complete.")

    # ─── ENTRY CHECK ─────────────────────────────────────────────────────────

    def check_entry(self) -> bool:
        """
        Returns True if all conditions are met for a new strangle entry:
        - Strategy is running
        - Within trading hours
        - Daily trade limit not reached
        - Daily risk limit not breached
        - Supertrend confirms direction
        """
        if not self.is_running:
            return False

        now = datetime.now(IST)
        t = now.time()
        start = datetime.strptime("09:20", "%H:%M").time()
        stop  = datetime.strptime("14:45", "%H:%M").time()
        if not (start <= t <= stop):
            return False

        # Reset daily counter if new day
        if self._trade_date != date.today():
            self._trades_today = get_trade_count_today()
            self._trade_date = date.today()

        if self._trades_today >= MAX_TRADES_PER_DAY:
            log.debug("Max trades reached for today.")
            return False

        max_loss = self.capital * (self.risk_pct / 100)
        if self._daily_pnl <= -max_loss:
            log.warning("Daily risk limit breached. No new trades.")
            return False

        if self.supertrend_dir == "UNKNOWN":
            return False

        # Don't open new strangle if there's already an open one
        open_trades = get_open_trades()
        if len(open_trades) >= 1:
            return False

        return True

    # ─── OPEN POSITION ───────────────────────────────────────────────────────

    def open_position(self, strategy_type: str = "GAMMA_STRANGLE") -> Optional[int]:
        """
        Simulate opening a strangle position.
        Returns trade_id on success, None on failure.
        """
        if not self.check_entry():
            return None

        spot = self.fyers.get_spot_price()
        if not spot:
            log.error("Cannot fetch spot price — aborting entry.")
            return None
        self.spot = spot

        expiry = get_nearest_weekly_expiry()
        now = datetime.now(IST)
        expiry_dt = self._parse_expiry(expiry)
        T = max((expiry_dt - now).total_seconds() / (365 * 24 * 3600), 0.001)

        # ── Strike selection ──────────────────────────────────────────────────
        if strategy_type == "EXPIRY" and now.time() >= datetime.strptime("09:45", "%H:%M").time():
            # Expiry version: ATM + 100 OTM
            atm = round_to_strike(spot)
            ce_strike = atm + EXPIRY_OTM_OFFSET
            pe_strike = atm - EXPIRY_OTM_OFFSET
            ce_hedge_strike = ce_strike + 150
            pe_hedge_strike = pe_strike - 150
        else:
            # Regular: target 20-25 delta using BS approximation
            ce_strike = self._find_strike_by_delta(spot, T, CE_DELTA_TARGET, "CE")
            pe_strike = self._find_strike_by_delta(spot, T, abs(PE_DELTA_TARGET), "PE")
            ce_hedge_strike = self._find_strike_by_delta(spot, T, HEDGE_DELTA_TARGET, "CE")
            pe_hedge_strike = self._find_strike_by_delta(spot, T, HEDGE_DELTA_TARGET, "PE")

        # ── Fetch LTPs ────────────────────────────────────────────────────────
        ce_sym  = build_option_symbol(ce_strike, "CE", expiry)
        pe_sym  = build_option_symbol(pe_strike, "PE", expiry)
        ceh_sym = build_option_symbol(ce_hedge_strike, "CE", expiry)
        peh_sym = build_option_symbol(pe_hedge_strike, "PE", expiry)

        ce_px  = self._get_simulated_ltp(ce_sym,  spot, ce_strike,  T, "CE")
        pe_px  = self._get_simulated_ltp(pe_sym,  spot, pe_strike,  T, "PE")
        ceh_px = self._get_simulated_ltp(ceh_sym, spot, ce_hedge_strike, T, "CE")
        peh_px = self._get_simulated_ltp(peh_sym, spot, pe_hedge_strike, T, "PE")

        qty = NIFTY_LOT_SIZE * self.num_lots
        premium = (ce_px + pe_px - ceh_px - peh_px) * qty  # net credit

        # ── Greeks ────────────────────────────────────────────────────────────
        ce_greeks  = black_scholes_greeks(spot, ce_strike,  T, option_type="CE")
        pe_greeks  = black_scholes_greeks(spot, pe_strike,  T, option_type="PE")
        ceh_greeks = black_scholes_greeks(spot, ce_hedge_strike, T, option_type="CE")
        peh_greeks = black_scholes_greeks(spot, pe_hedge_strike, T, option_type="PE")

        # ── Risk check ────────────────────────────────────────────────────────
        max_loss_allowed = self.capital * (self.risk_pct / 100)
        estimated_max_loss = abs(pe_px) * qty  # rough worst-case one side
        if estimated_max_loss > max_loss_allowed:
            log.warning("Trade risk ₹%.0f exceeds daily limit ₹%.0f — skipping.", 
                        estimated_max_loss, max_loss_allowed)
            return None

        # ── Build Position objects ────────────────────────────────────────────
        positions = [
            Position(ce_sym,  ce_strike,  "CE", "SELL", ce_px,  qty, ce_greeks),
            Position(pe_sym,  pe_strike,  "PE", "SELL", pe_px,  qty, pe_greeks),
            Position(ceh_sym, ce_hedge_strike, "CE", "BUY", ceh_px, qty, ceh_greeks, is_hedge=True),
            Position(peh_sym, pe_hedge_strike, "PE", "BUY", peh_px, qty, peh_greeks, is_hedge=True),
        ]

        # ── Persist to DB ─────────────────────────────────────────────────────
        net_delta = sum(p.delta_exposure for p in positions)
        gamma_score = compute_gamma_risk_score(
            [{"gamma": p.greeks["gamma"], "quantity": qty, "side": p.side} for p in positions],
            spot,
        )

        trade_id = insert_trade({
            "trade_date":       date.today(),
            "entry_time":       datetime.now(IST),
            "ce_strike":        ce_strike,
            "pe_strike":        pe_strike,
            "ce_entry_px":      ce_px,
            "pe_entry_px":      pe_px,
            "ce_current_px":    ce_px,
            "pe_current_px":    pe_px,
            "ce_hedge_strike":  ce_hedge_strike,
            "pe_hedge_strike":  pe_hedge_strike,
            "ce_hedge_px":      ceh_px,
            "pe_hedge_px":      peh_px,
            "quantity":         qty,
            "premium_collected": premium,
            "realized_pnl":     0.0,
            "unrealized_pnl":   0.0,
            "status":           "OPEN",
            "adjustment_level": 0,
            "net_delta":        net_delta,
            "gamma_score":      gamma_score,
            "strategy_type":    strategy_type,
        })

        with self._lock:
            self.active_positions[trade_id] = positions
            self.entry_spot[trade_id] = spot
            self.entry_time[trade_id] = datetime.now(IST)
            self.adjustment_counts[trade_id] = 0
            self.trade_premium[trade_id] = premium
            self._trades_today += 1

        log.info("[PAPER] Strangle opened id=%s CE=%s PE=%s premium=%.2f", 
                 trade_id, ce_strike, pe_strike, premium)

        # Telegram alert
        self._send_alert(
            f"🚀 *ENTRY*\n"
            f"Strategy: Supertrend Gamma Strangle\n"
            f"Strikes: CE {ce_strike} | PE {pe_strike}\n"
            f"Premium Collected: ₹{premium:.0f}\n"
            f"Risk: ₹{estimated_max_loss:.0f} ({self.risk_pct}% cap)\n"
            f"Spot: {spot:.2f}"
        )

        return trade_id

    # ─── MONITOR ─────────────────────────────────────────────────────────────

    def monitor_positions(self) -> None:
        """
        Called periodically (every ~30s by scheduler).
        Updates MTM and triggers gamma defence checks.
        """
        if not self.active_positions:
            return

        spot = self.fyers.get_spot_price()
        if not spot:
            return
        self.spot = spot

        for trade_id in list(self.active_positions.keys()):
            self._update_position_prices(trade_id, spot)
            self.adjust_positions(trade_id, spot)

            # Check expiry profit target / stop loss
            self._check_expiry_targets(trade_id)

    # ─── ADJUST POSITIONS ─────────────────────────────────────────────────────

    def adjust_positions(self, trade_id: int, spot: Optional[float] = None) -> None:
        """
        Gamma defence model — 3 levels.
        """
        if trade_id not in self.active_positions:
            return

        spot = spot or self.fyers.get_spot_price() or self.spot
        if not spot:
            return

        positions = self.active_positions[trade_id]
        entry_s   = self.entry_spot[trade_id]
        entry_t   = self.entry_time[trade_id]
        adj_count = self.adjustment_counts.get(trade_id, 0)
        premium   = self.trade_premium[trade_id]

        current_pnl = self.calculate_mtm(trade_id)
        spot_move = abs(spot - entry_s) / entry_s

        # ─ Level 3: 1.2% move within 45 minutes ────────────────────────────
        elapsed_min = (datetime.now(IST) - entry_t).total_seconds() / 60
        if spot_move >= GAMMA_L3_SPOT_MOVE and elapsed_min <= GAMMA_L3_TIME_WINDOW:
            log.warning("[PAPER] GAMMA L3 triggered for trade %s — closing structure", trade_id)
            self._record_adjustment(trade_id, 3, "CLOSE_ALL", 
                                    f"{spot_move*100:.2f}% move in {elapsed_min:.0f}m", spot, current_pnl)
            self.close_position(trade_id, reason="GAMMA_L3")
            return

        # ─ Level 2: tested leg delta > 35 ────────────────────────────────────
        for pos in positions:
            if pos.side == "SELL" and not pos.is_hedge:
                abs_delta = abs(pos.greeks.get("delta", 0.0)) * 100
                if abs_delta > GAMMA_L2_DELTA_LIMIT:
                    log.warning("[PAPER] GAMMA L2 — delta=%.1f on %s", abs_delta, pos.symbol)
                    action = f"Roll {pos.option_type} {pos.strike} → new 20-delta"
                    self._record_adjustment(trade_id, 2, action,
                                            f"Delta {abs_delta:.1f} > {GAMMA_L2_DELTA_LIMIT}", spot, current_pnl)
                    self._roll_leg(trade_id, pos, spot)
                    self.adjustment_counts[trade_id] = adj_count + 1
                    self._send_alert(
                        f"⚠️ *GAMMA ADJUSTMENT LEVEL 2*\n"
                        f"Action Taken: {action}\n"
                        f"Reason: Delta breach {abs_delta:.1f}\n"
                        f"Spot: {spot:.2f}"
                    )
                    return

        # ─ Level 1: 0.6% spot move OR premium +40% ────────────────────────
        premium_change = abs(current_pnl / premium) if premium != 0 else 0
        if spot_move >= GAMMA_L1_SPOT_MOVE or premium_change >= GAMMA_L1_PREMIUM_PCT:
            trigger = "spot_move" if spot_move >= GAMMA_L1_SPOT_MOVE else "premium_+40%"
            log.info("[PAPER] GAMMA L1 triggered for trade %s — rolling untested leg", trade_id)
            action = "Roll untested leg closer"
            self._record_adjustment(trade_id, 1, action,
                                    f"{trigger}: {spot_move*100:.2f}% / {premium_change*100:.0f}%",
                                    spot, current_pnl)
            self._roll_untested_leg(trade_id, spot)
            self.adjustment_counts[trade_id] = adj_count + 1
            self._send_alert(
                f"⚠️ *GAMMA ADJUSTMENT LEVEL 1*\n"
                f"Action Taken: {action}\n"
                f"Reason: {trigger}\n"
                f"Spot: {spot:.2f}"
            )

    # ─── CLOSE POSITION ──────────────────────────────────────────────────────

    def close_position(self, trade_id: int, reason: str = "MANUAL") -> float:
        """
        Simulate closing all legs of a trade at current LTP.
        Returns realised P&L.
        """
        if trade_id not in self.active_positions:
            log.warning("close_position: trade_id %s not found in memory", trade_id)
            return 0.0

        pnl = self.calculate_mtm(trade_id)

        with self._lock:
            self.active_positions.pop(trade_id, None)
            self.entry_spot.pop(trade_id, None)
            self.entry_time.pop(trade_id, None)
            self.adjustment_counts.pop(trade_id, None)
            self.trade_premium.pop(trade_id, None)

        self._daily_pnl += pnl

        update_trade(trade_id, {
            "status":        "CLOSED",
            "exit_time":     datetime.now(IST),
            "realized_pnl":  pnl,
            "unrealized_pnl": 0.0,
            "close_reason":  reason,
        })

        log.info("[PAPER] Trade %s closed. Reason=%s PnL=%.2f", trade_id, reason, pnl)

        self._send_alert(
            f"✅ *EXIT*\n"
            f"Trade ID: {trade_id}\n"
            f"P&L: ₹{pnl:.0f}\n"
            f"Return %: {pnl/self.capital*100:.2f}%\n"
            f"Reason: {reason}"
        )

        return pnl

    def close_all_positions(self, reason: str = "FORCE_CLOSE") -> float:
        """Force close all open positions."""
        total_pnl = 0.0
        for trade_id in list(self.active_positions.keys()):
            total_pnl += self.close_position(trade_id, reason=reason)
        return total_pnl

    # ─── MTM ─────────────────────────────────────────────────────────────────

    def calculate_mtm(self, trade_id: Optional[int] = None) -> float:
        """
        Calculate mark-to-market P&L.
        If trade_id is None, returns total unrealised P&L across all positions.
        """
        if trade_id is not None:
            positions = self.active_positions.get(trade_id, [])
            return sum(p.pnl for p in positions)

        return sum(
            sum(p.pnl for p in positions)
            for positions in self.active_positions.values()
        )

    # ─── GREEKS AGGREGATION ──────────────────────────────────────────────────

    def get_net_delta(self) -> float:
        """Return net delta across all open positions."""
        total = 0.0
        for positions in self.active_positions.values():
            for pos in positions:
                total += pos.delta_exposure
        return round(total, 4)

    def get_gamma_risk_score(self) -> float:
        """Return aggregated gamma risk score (0–100)."""
        all_pos = [
            {
                "gamma": p.greeks.get("gamma", 0.0),
                "quantity": p.quantity,
                "side": p.side,
            }
            for positions in self.active_positions.values()
            for p in positions
        ]
        if not all_pos:
            return 50.0
        return compute_gamma_risk_score(all_pos, self.spot or 22000)

    # ─── INTERNAL HELPERS ─────────────────────────────────────────────────────

    def _get_simulated_ltp(
        self, symbol: str, spot: float, strike: int, T: float, opt_type: str
    ) -> float:
        """
        Try to fetch live LTP. If unavailable, fall back to BS theoretical price.
        """
        ltp = self.fyers.get_option_ltp(symbol)
        if ltp and ltp > 0:
            return ltp
        # BS fallback with assumed IV
        d1 = (math.log(spot / strike) + (0.065 + 0.5 * 0.15 ** 2) * T) / (0.15 * math.sqrt(T)) if T > 0 else 0
        from scipy.stats import norm
        if opt_type == "CE":
            price = spot * norm.cdf(d1) - strike * math.exp(-0.065 * T) * norm.cdf(d1 - 0.15 * math.sqrt(T))
        else:
            price = strike * math.exp(-0.065 * T) * norm.cdf(-(d1 - 0.15 * math.sqrt(T))) - spot * norm.cdf(-d1)
        return max(0.05, round(price, 2))

    def _find_strike_by_delta(
        self, spot: float, T: float, target_delta: float, opt_type: str
    ) -> int:
        """Binary search for strike closest to target delta."""
        best_strike = round_to_strike(spot)
        best_diff = float("inf")

        search_range = range(
            round_to_strike(spot) - 1500,
            round_to_strike(spot) + 1550,
            STRIKE_STEP,
        )
        for strike in search_range:
            greeks = black_scholes_greeks(spot, strike, T, option_type=opt_type)
            delta = abs(greeks["delta"])
            diff = abs(delta - target_delta)
            if diff < best_diff:
                best_diff = diff
                best_strike = strike

        return best_strike

    def _update_position_prices(self, trade_id: int, spot: float) -> None:
        """Refresh current prices for all legs of a trade."""
        positions = self.active_positions.get(trade_id, [])
        expiry = get_nearest_weekly_expiry()
        expiry_dt = self._parse_expiry(expiry)
        T = max((expiry_dt - datetime.now(IST)).total_seconds() / (365 * 24 * 3600), 0.001)

        total_unrealised = 0.0
        for pos in positions:
            new_px = self._get_simulated_ltp(pos.symbol, spot, pos.strike, T, pos.option_type)
            pos.current_price = new_px
            # Refresh greeks
            pos.greeks = black_scholes_greeks(spot, pos.strike, T, option_type=pos.option_type)
            total_unrealised += pos.pnl

        update_trade(trade_id, {"unrealized_pnl": total_unrealised})

    def _force_close_trade(self, trade_id: int, reason: str) -> None:
        self.close_position(trade_id, reason=reason)

    def _roll_leg(self, trade_id: int, old_pos: Position, spot: float) -> None:
        """Replace an existing short leg with a new 20-delta strike."""
        expiry = get_nearest_weekly_expiry()
        expiry_dt = self._parse_expiry(expiry)
        T = max((expiry_dt - datetime.now(IST)).total_seconds() / (365 * 24 * 3600), 0.001)

        new_strike = self._find_strike_by_delta(spot, T, 0.20, old_pos.option_type)
        new_sym = build_option_symbol(new_strike, old_pos.option_type, expiry)
        new_px = self._get_simulated_ltp(new_sym, spot, new_strike, T, old_pos.option_type)
        new_greeks = black_scholes_greeks(spot, new_strike, T, option_type=old_pos.option_type)

        positions = self.active_positions[trade_id]
        positions.remove(old_pos)
        positions.append(
            Position(new_sym, new_strike, old_pos.option_type, "SELL",
                     new_px, old_pos.quantity, new_greeks)
        )
        log.info("[PAPER] Rolled %s %s → %s", old_pos.option_type, old_pos.strike, new_strike)

    def _roll_untested_leg(self, trade_id: int, spot: float) -> None:
        """Roll the untested (farther from spot) leg closer."""
        positions = self.active_positions[trade_id]
        short_legs = [p for p in positions if p.side == "SELL" and not p.is_hedge]
        if not short_legs:
            return

        # Untested = the leg farther from current spot
        untested = max(short_legs, key=lambda p: abs(p.strike - spot))
        self._roll_leg(trade_id, untested, spot)

    def _check_expiry_targets(self, trade_id: int) -> None:
        """Check profit target / stop loss for expiry strangle."""
        premium = self.trade_premium.get(trade_id, 0)
        if premium <= 0:
            return
        pnl = self.calculate_mtm(trade_id)

        if pnl >= premium * EXPIRY_TARGET_PCT:
            log.info("[PAPER] Profit target hit for trade %s", trade_id)
            self.close_position(trade_id, reason="TARGET_HIT")
        elif pnl <= -premium * EXPIRY_STOP_MULT:
            log.info("[PAPER] Stop loss hit for trade %s", trade_id)
            self.close_position(trade_id, reason="STOP_LOSS")

    def _record_adjustment(
        self, trade_id: int, level: int, action: str, reason: str,
        spot: float, pnl: float
    ) -> None:
        insert_adjustment({
            "trade_id":    trade_id,
            "level":       level,
            "action":      action,
            "reason":      reason,
            "spot_at_adj": spot,
            "pnl_at_adj":  pnl,
        })
        update_trade(trade_id, {"adjustment_level": level})

    @staticmethod
    def _parse_expiry(expiry_str: str) -> datetime:
        """Parse YYMMMDD expiry string to timezone-aware datetime."""
        try:
            dt = datetime.strptime(expiry_str, "%y%b%d")
            # Set to 15:30 IST on expiry day
            dt = dt.replace(hour=15, minute=30)
            return IST.localize(dt)
        except Exception:
            return datetime.now(IST) + timedelta(days=7)


    def calculate_margin_required(self) -> Dict[str, float]:
        """
        Fetch real margin required from Fyers API v3 /margin endpoint.
        Sends all 4 legs (2 short + 2 long hedges) together so the broker
        calculates actual SPAN + Exposure with hedge benefit applied.
        Falls back to None values if API call fails (no dummy estimates).
        """
        from data.fyers_client import build_option_symbol, get_nearest_weekly_expiry
        from datetime import datetime

        qty = NIFTY_LOT_SIZE * self.num_lots
        spot = self.spot or 0.0
        expiry = get_nearest_weekly_expiry()
        expiry_dt = self._parse_expiry(expiry)
        T = max((expiry_dt - datetime.now(IST)).total_seconds() / (365 * 24 * 3600), 0.001)

        # Find strikes for all 4 legs
        ce_strike  = self._find_strike_by_delta(spot, T, 0.22, "CE") if spot > 0 else 0
        pe_strike  = self._find_strike_by_delta(spot, T, 0.22, "PE") if spot > 0 else 0
        ceh_strike = self._find_strike_by_delta(spot, T, 0.10, "CE") if spot > 0 else 0
        peh_strike = self._find_strike_by_delta(spot, T, 0.10, "PE") if spot > 0 else 0

        legs = []
        if ce_strike:
            legs = [
                {"symbol": build_option_symbol(ce_strike,  "CE", expiry), "qty": qty,  "side": -1},  # SELL CE
                {"symbol": build_option_symbol(pe_strike,  "PE", expiry), "qty": qty,  "side": -1},  # SELL PE
                {"symbol": build_option_symbol(ceh_strike, "CE", expiry), "qty": qty,  "side":  1},  # BUY CE hedge
                {"symbol": build_option_symbol(peh_strike, "PE", expiry), "qty": qty,  "side":  1},  # BUY PE hedge
            ]

        try:
            # Build Fyers margin API payload
            # POST /margin with list of positions
            payload = {
                "data": [
                    {
                        "symbol":      leg["symbol"],
                        "qty":         leg["qty"],
                        "side":        leg["side"],       # 1=BUY, -1=SELL
                        "type":        2,                 # Market order type
                        "productType": "INTRADAY",
                        "limitPrice":  0,
                        "stopPrice":   0,
                    }
                    for leg in legs
                ]
            }
            resp = self.fyers._post("/margin", payload=payload)

            if resp.get("s") == "ok":
                d = resp.get("data", {})
                total   = float(d.get("totalMarginRequired", 0) or 0)
                span    = float(d.get("spanMargin",         0) or 0)
                exposure= float(d.get("exposureMargin",     0) or 0)
                benefit = float(d.get("hedgeBenefit",       0) or 0)
                # Some Fyers versions nest differently
                if total == 0 and "margins" in d:
                    for m in d["margins"]:
                        total    += float(m.get("total",    0) or 0)
                        span     += float(m.get("span",     0) or 0)
                        exposure += float(m.get("exposure", 0) or 0)
                return {
                    "total_required":  round(total,    0),
                    "span_margin":     round(span,     0),
                    "exposure_margin": round(exposure, 0),
                    "hedge_benefit":   round(benefit,  0),
                    "lots":            self.num_lots,
                    "qty":             qty,
                    "spot":            spot,
                    "source":          "fyers_api",
                    "legs":            legs,
                    "error":           None,
                }
            else:
                return self._margin_unavailable(qty, spot, legs, reason=str(resp))

        except Exception as e:
            log.warning("Margin API call failed: %s", e)
            return self._margin_unavailable(qty, spot, legs if ce_strike else [], reason=str(e))

    def _margin_unavailable(self, qty: int, spot: float, legs: list, reason: str = "") -> Dict:
        """Return a clean 'unavailable' dict — never show fake numbers."""
        return {
            "total_required":  None,
            "span_margin":     None,
            "exposure_margin": None,
            "hedge_benefit":   None,
            "lots":            self.num_lots,
            "qty":             qty,
            "spot":            spot,
            "source":          "unavailable",
            "legs":            legs,
            "error":           reason or "Margin API not reachable",
        }

    def generate_eod_summary(self) -> Dict:
        """Generate end-of-day report data."""
        from data.database import get_trades_for_date
        trades = get_trades_for_date(date.today())
        closed = [t for t in trades if t["status"] == "CLOSED"]
        wins = [t for t in closed if (t["realized_pnl"] or 0) > 0]
        total_pnl = sum(t.get("realized_pnl", 0) or 0 for t in closed)
        max_dd = min((t.get("realized_pnl", 0) or 0) for t in closed) if closed else 0
        win_rate = len(wins) / len(closed) * 100 if closed else 0

        summary = {
            "trade_date":     date.today(),
            "total_trades":   len(closed),
            "winning_trades": len(wins),
            "net_pnl":        total_pnl,
            "max_drawdown":   max_dd,
            "capital_used":   self.capital,
            "win_rate":       win_rate,
        }
        upsert_daily_summary(summary)
        return summary
