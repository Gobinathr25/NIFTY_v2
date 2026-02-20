"""
Technical indicators: Supertrend, VWAP, Black-Scholes Greeks.
"""

from __future__ import annotations
import math
import numpy as np
import pandas as pd
from typing import Tuple, Optional, List, Dict
from scipy.stats import norm

from core.config import SUPERTREND_PERIOD, SUPERTREND_MULT
from utils.logger import get_logger

log = get_logger(__name__)


# ─── SUPERTREND ───────────────────────────────────────────────────────────────

def compute_supertrend(
    df: pd.DataFrame,
    period: int = SUPERTREND_PERIOD,
    multiplier: float = SUPERTREND_MULT,
) -> pd.DataFrame:
    """
    Compute Supertrend indicator on OHLC dataframe.
    Input df must have columns: open, high, low, close
    Returns df with added columns: supertrend, trend_direction ('BULLISH'/'BEARISH')
    """
    df = df.copy()
    hl2 = (df["high"] + df["low"]) / 2

    # ATR via Wilder's smoothing
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)  # 1=bullish, -1=bearish

    for i in range(1, len(df)):
        prev_close = df["close"].iloc[i - 1]
        curr_close = df["close"].iloc[i]

        # Final upper band
        if i == 1:
            final_ub = upper_band.iloc[i]
            final_lb = lower_band.iloc[i]
        else:
            prev_ub = supertrend.iloc[i - 1] if direction.iloc[i - 1] == -1 else upper_band.iloc[i - 1]
            final_ub = upper_band.iloc[i] if upper_band.iloc[i] < prev_ub or prev_close > prev_ub else prev_ub

            prev_lb = supertrend.iloc[i - 1] if direction.iloc[i - 1] == 1 else lower_band.iloc[i - 1]
            final_lb = lower_band.iloc[i] if lower_band.iloc[i] > prev_lb or prev_close < prev_lb else prev_lb

        prev_dir = direction.iloc[i - 1] if i > 1 else 1
        if prev_dir == 1:
            if curr_close < final_lb:
                direction.iloc[i] = -1
                supertrend.iloc[i] = final_ub
            else:
                direction.iloc[i] = 1
                supertrend.iloc[i] = final_lb
        else:
            if curr_close > final_ub:
                direction.iloc[i] = 1
                supertrend.iloc[i] = final_lb
            else:
                direction.iloc[i] = -1
                supertrend.iloc[i] = final_ub

    df["supertrend"] = supertrend
    df["st_direction"] = direction.map({1: "BULLISH", -1: "BEARISH"})
    return df


# ─── VWAP ─────────────────────────────────────────────────────────────────────

def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Compute intraday VWAP. df must have: high, low, close, volume.
    Returns VWAP series.
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    return cum_tp_vol / cum_vol


# ─── BLACK-SCHOLES GREEKS ─────────────────────────────────────────────────────

def black_scholes_greeks(
    S: float,          # Spot
    K: float,          # Strike
    T: float,          # Time to expiry (years)
    r: float = 0.065,  # Risk-free rate (RBI repo ~6.5%)
    sigma: float = 0.15,  # IV (use 15% as default estimate)
    option_type: str = "CE",
) -> Dict[str, float]:
    """
    Compute Black-Scholes delta, gamma, theta, vega.
    Returns dict with delta, gamma, theta, vega, iv.
    """
    if T <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "iv": sigma}

    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if option_type == "CE":
            delta = norm.cdf(d1)
        else:  # PE
            delta = norm.cdf(d1) - 1.0

        gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
        vega = S * norm.pdf(d1) * math.sqrt(T) * 0.01  # per 1% IV change
        theta = (
            -(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
            - r * K * math.exp(-r * T) * (norm.cdf(d2) if option_type == "CE" else norm.cdf(-d2))
        ) / 365  # per day

        return {
            "delta": round(delta, 4),
            "gamma": round(gamma, 6),
            "theta": round(theta, 4),
            "vega": round(vega, 4),
            "iv": sigma,
        }
    except Exception as e:
        log.error("BS greeks error: %s", e)
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "iv": sigma}


def estimate_iv_from_price(
    market_price: float,
    S: float,
    K: float,
    T: float,
    option_type: str = "CE",
    r: float = 0.065,
) -> float:
    """Newton-Raphson IV solver. Returns IV as decimal."""
    if T <= 0 or market_price <= 0:
        return 0.15

    sigma = 0.20  # initial guess
    for _ in range(100):
        try:
            d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
            d2 = d1 - sigma * math.sqrt(T)
            if option_type == "CE":
                price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
            else:
                price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            vega = S * norm.pdf(d1) * math.sqrt(T)
            if abs(vega) < 1e-10:
                break
            diff = market_price - price
            sigma += diff / vega
            sigma = max(0.01, min(sigma, 5.0))
            if abs(diff) < 0.001:
                break
        except Exception:
            break
    return round(sigma, 4)


# ─── GAMMA RISK SCORE ─────────────────────────────────────────────────────────

def compute_gamma_risk_score(
    positions: List[Dict],
    spot: float,
) -> float:
    """
    Aggregate gamma exposure across all positions.
    Positive = net long gamma, Negative = net short gamma.
    Score is normalised to [0, 100] for UI display.
    """
    total_gamma_exposure = 0.0
    for pos in positions:
        gamma = pos.get("gamma", 0.0)
        qty = pos.get("quantity", 75)
        sign = -1 if pos.get("side", "SELL") == "SELL" else 1
        total_gamma_exposure += sign * gamma * qty * spot

    # Normalise: clip at ±50000 → map to 0-100
    clamped = max(-50000, min(50000, total_gamma_exposure))
    score = 50 + (clamped / 50000) * 50
    return round(score, 2)
