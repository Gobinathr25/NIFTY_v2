"""
Fyers API v3 client wrapper.
Handles authentication, quote fetching, option chain retrieval.
PAPER_MODE guard: all order methods are disabled when PAPER_MODE=True.
"""

from __future__ import annotations
import time
import math
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from core.config import (
    PAPER_MODE, NIFTY_INDEX_SYMBOL, NIFTY_OPT_PREFIX, FYERS_BASE_URL, IST
)
from utils.logger import get_logger

log = get_logger(__name__)


class FyersClient:
    """
    Thin wrapper around Fyers API v3 REST endpoints.
    Only read-only market data methods are used in paper trading mode.
    """

    def __init__(self, client_id: str, access_token: str):
        self.client_id = client_id
        self.access_token = access_token
        self._headers = {
            "Authorization": f"{client_id}:{access_token}",
            "Content-Type": "application/json",
        }
        self._session = requests.Session()
        self._session.headers.update(self._headers)

    # ─── AUTH ────────────────────────────────────────────────────────────────

    @staticmethod
    def generate_auth_url(client_id: str, redirect_url: str, secret_key: str) -> str:
        """Returns the Fyers OAuth2 URL for the user to log in."""
        import hashlib
        app_id_hash = hashlib.sha256(f"{client_id}:{secret_key}".encode()).hexdigest()
        return (
            f"https://api-t1.fyers.in/api/v3/generate-authcode"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_url}"
            f"&response_type=code"
            f"&state=sample_state"
        )

    @staticmethod
    def exchange_auth_code(client_id: str, secret_key: str, auth_code: str) -> Optional[str]:
        """Exchange auth code for access token."""
        import hashlib, base64
        app_id_hash = hashlib.sha256(f"{client_id}:{secret_key}".encode()).hexdigest()
        payload = {
            "grant_type": "authorization_code",
            "appIdHash": app_id_hash,
            "code": auth_code,
        }
        try:
            resp = requests.post(
                f"{FYERS_BASE_URL}/validate-authcode",
                json=payload,
                timeout=10,
            )
            data = resp.json()
            if data.get("s") == "ok":
                return data.get("access_token")
            log.error("Token exchange failed: %s", data)
        except Exception as e:
            log.error("Token exchange exception: %s", e)
        return None

    def validate_token(self) -> bool:
        """Ping the profile endpoint to check if token is valid."""
        try:
            resp = self._get("/profile")
            return resp.get("s") == "ok"
        except Exception:
            return False

    # ─── MARKET DATA ─────────────────────────────────────────────────────────

    def get_spot_price(self) -> Optional[float]:
        """Fetch NIFTY spot LTP."""
        try:
            data = self._get("/quotes", params={"symbols": NIFTY_INDEX_SYMBOL})
            if data.get("s") == "ok":
                return float(data["d"][0]["v"]["lp"])
        except Exception as e:
            log.error("get_spot_price error: %s", e)
        return None

    def get_option_ltp(self, symbol: str) -> Optional[float]:
        """Fetch LTP for a specific option symbol."""
        try:
            data = self._get("/quotes", params={"symbols": symbol})
            if data.get("s") == "ok":
                return float(data["d"][0]["v"]["lp"])
        except Exception as e:
            log.error("get_option_ltp(%s) error: %s", symbol, e)
        return None

    def get_option_depth(self, symbol: str) -> Optional[Dict]:
        """Fetch full market depth for an option."""
        try:
            data = self._get("/depth", params={"symbol": symbol, "ohlcv_flag": 1})
            if data.get("s") == "ok":
                return data.get("d", {})
        except Exception as e:
            log.error("get_option_depth error: %s", e)
        return None

    def get_historical_candles(
        self,
        symbol: str,
        resolution: str = "5",
        from_ts: Optional[int] = None,
        to_ts: Optional[int] = None,
    ) -> List[Dict]:
        """
        Fetch historical OHLCV candles.
        resolution: "1","2","3","5","10","15","20","30","60","120","240","D","W","M"
        """
        if from_ts is None:
            from_ts = int((datetime.now(IST) - timedelta(days=5)).timestamp())
        if to_ts is None:
            to_ts = int(datetime.now(IST).timestamp())

        try:
            data = self._get(
                "/data/history",
                params={
                    "symbol": symbol,
                    "resolution": resolution,
                    "date_format": "1",
                    "range_from": str(from_ts),
                    "range_to": str(to_ts),
                    "cont_flag": "1",
                },
            )
            if data.get("s") == "ok":
                candles = data.get("candles", [])
                return [
                    {
                        "ts": int(c[0]),
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                    }
                    for c in candles
                ]
        except Exception as e:
            log.error("get_historical_candles error: %s", e)
        return []

    def get_option_chain(self, expiry: str) -> List[Dict]:
        """
        Fetch option chain for nearest NIFTY weekly expiry.
        expiry format: DDMMMYY e.g. 06JUN24
        Returns list of {strike, CE_ltp, PE_ltp, CE_oi, PE_oi, ...}
        """
        try:
            data = self._get(
                "/optionchain",
                params={
                    "symbol": NIFTY_INDEX_SYMBOL,
                    "strikecount": 20,
                    "timestamp": expiry,
                },
            )
            if data.get("s") == "ok":
                return data.get("data", {}).get("optionsChain", [])
        except Exception as e:
            log.error("get_option_chain error: %s", e)
        return []

    def get_funds(self) -> Optional[Dict]:
        """Fetch available funds / margin."""
        try:
            data = self._get("/funds")
            if data.get("s") == "ok":
                return data.get("fund_limit", [])
        except Exception as e:
            log.error("get_funds error: %s", e)
        return None

    # ─── ORDER METHODS (PAPER GUARD) ─────────────────────────────────────────

    def place_order(self, order: Dict) -> Dict:
        """Paper guard: always simulates, never calls real endpoint."""
        if PAPER_MODE:
            log.info("[PAPER] Simulated order: %s", order)
            return {"s": "ok", "id": f"PAPER_{int(time.time()*1000)}", "paper": True}
        # Real path (unreachable while PAPER_MODE=True)
        return self._post("/orders/sync", payload=order)

    def cancel_order(self, order_id: str) -> Dict:
        if PAPER_MODE:
            log.info("[PAPER] Simulated cancel: %s", order_id)
            return {"s": "ok", "id": order_id, "paper": True}
        return self._delete(f"/orders/{order_id}")

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        url = FYERS_BASE_URL + endpoint
        resp = self._session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, payload: Dict) -> Dict:
        url = FYERS_BASE_URL + endpoint
        resp = self._session.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, endpoint: str) -> Dict:
        url = FYERS_BASE_URL + endpoint
        resp = self._session.delete(url, timeout=10)
        resp.raise_for_status()
        return resp.json()


# ─── SYMBOL BUILDER ──────────────────────────────────────────────────────────

def build_option_symbol(strike: int, option_type: str, expiry_str: str) -> str:
    """
    Build Fyers option symbol.
    Example: NSE:NIFTY24JUN2423000CE
    expiry_str format: YYMMMDD e.g. 24JUN06
    """
    return f"NSE:NIFTY{expiry_str}{strike}{option_type}"


def get_nearest_weekly_expiry() -> str:
    """
    Return nearest Thursday (weekly expiry) as YYMMMDD string.
    """
    today = datetime.now(IST).date()
    days_until_thursday = (3 - today.weekday()) % 7
    if days_until_thursday == 0:
        # If today is Thursday but market has closed, use next Thursday
        if datetime.now(IST).hour >= 15:
            days_until_thursday = 7
    expiry = today + timedelta(days=days_until_thursday)
    return expiry.strftime("%y%b%d").upper()


def round_to_strike(price: float, step: int = 50) -> int:
    """Round spot price to nearest strike step."""
    return int(round(price / step) * step)
