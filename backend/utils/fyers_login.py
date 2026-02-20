"""
Fyers headless login — correct 4-step flow.

VERIFIED flow:
  Step 1: POST /send_login_otp_v2   — fy_id base64 encoded, app_id="2"
  Step 2: POST /verify_otp          — TOTP or SMS otp
  Step 3: POST /verify_pin_v2       — PIN base64 encoded → returns trade access_token
  Step 4: POST /token               — trade token → returns data.auth (= final access token)
  
  data.auth IS the final access token. Do NOT call /validate-authcode after this.
  /validate-authcode is only needed for browser OAuth flow (not headless).
"""

from __future__ import annotations
import base64
import hashlib
import time
import requests
import pyotp
from typing import Tuple
from utils.logger import get_logger

log = get_logger(__name__)

# ─── HARDCODED CREDENTIALS ────────────────────────────────────────────────────
FYERS_CLIENT_ID  = "KS5VRSP9RF-100"       # App ID e.g. "AB12345-100"
FYERS_SECRET_KEY = "6NXYPEG7NB"   # Secret key from myapi.fyers.in
FYERS_REDIRECT_URI = "https://trade.fyers.in/api-login/redirect-uri/index.html"  # Must match your Fyers app setting
FYERS_USERNAME   = "XR33487"           # Your Fyers login ID e.g. "XY12345"
FYERS_TOTP_KEY   = "546FOAJ66NUNKWB6A45RJJ3J6FCEDHQT" # 32-char base32 TOTP secret from Fyers 2FA
FYERS_PIN        = "1228"              # Your 4-digit Fyers PIN
TELEGRAM_BOT_TOKEN = "8469692207:AAHQPtw3Z1K7vw1j4fCQYwVMFrk6U1sSHIA"  # Bot token from @BotFather
TELEGRAM_CHAT_ID   = "918853932"  # Your chat/channel ID
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL  = "https://api-t2.fyers.in/vagator/v2"
BASE_URL2 = "https://api-t1.fyers.in/api/v3"

URL_SEND_LOGIN_OTP = f"{BASE_URL}/send_login_otp_v2"
URL_VERIFY_OTP     = f"{BASE_URL}/verify_otp"
URL_VERIFY_PIN     = f"{BASE_URL}/verify_pin_v2"
URL_TOKEN          = f"{BASE_URL2}/token"

SUCCESS =  1
ERROR   = -1


def _b64(s: str) -> str:
    return base64.b64encode(str(s).encode("ascii")).decode("ascii")


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _post(url: str, payload: dict, headers: dict = None) -> Tuple[int, dict]:
    try:
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        resp = requests.post(url, json=payload, headers=hdrs, timeout=15)
        raw  = resp.text.strip()
        log.debug("POST %s → %d | %.300s", url, resp.status_code, raw)
        try:
            return SUCCESS, resp.json()
        except Exception:
            return ERROR, {"message": f"Non-JSON ({resp.status_code}): {raw[:200]}"}
    except Exception as e:
        return ERROR, {"message": str(e)}


def _is_error(d: dict) -> bool:
    """Return True if the response clearly indicates failure."""
    if d.get("s") == "error":
        return True
    msg = str(d.get("message", "")).lower()
    if any(w in msg for w in ["invalid", "incorrect", "wrong", "expired", "failed"]):
        return True
    return False


# ─── STEP FUNCTIONS ──────────────────────────────────────────────────────────

def _send_login_otp(username: str) -> Tuple[int, dict]:
    """Step 1 — fy_id must be base64 encoded."""
    s, d = _post(URL_SEND_LOGIN_OTP, {"fy_id": _b64(username), "app_id": "2"})
    log.info("send_login_otp → code=%s msg=%s", d.get("code"), d.get("message", ""))
    return s, d


def _verify_totp(request_key: str) -> Tuple[int, dict]:
    """Step 2a — auto-generate TOTP and verify."""
    # Wait if near 30s boundary to avoid stale code
    if int(time.time()) % 30 >= 27:
        log.info("Near TOTP boundary — waiting 4s")
        time.sleep(4)
    code = pyotp.TOTP(FYERS_TOTP_KEY.strip().replace(" ", "")).now()
    log.info("TOTP code: %s", code)
    s, d = _post(URL_VERIFY_OTP, {"request_key": request_key, "otp": code})
    log.info("verify_otp (TOTP) → code=%s msg=%s", d.get("code"), d.get("message", ""))
    return s, d


def _verify_sms_otp(request_key: str, otp: str) -> Tuple[int, dict]:
    """Step 2b — verify SMS OTP from user."""
    s, d = _post(URL_VERIFY_OTP, {"request_key": request_key, "otp": otp.strip()})
    log.info("verify_otp (SMS) → code=%s msg=%s", d.get("code"), d.get("message", ""))
    return s, d


def _verify_pin(request_key: str) -> Tuple[int, dict]:
    """Step 3 — PIN must be base64 encoded."""
    s, d = _post(URL_VERIFY_PIN, {
        "request_key":   request_key,
        "identity_type": "pin",
        "identifier":    _b64(FYERS_PIN),
    })
    log.info("verify_pin → code=%s msg=%s", d.get("code"), d.get("message", ""))
    return s, d


def _get_final_token(trade_access_token: str) -> Tuple[int, str]:
    """
    Step 4 — POST /token with trade token.
    Response: data.auth = final access token (JWT). Use it directly.
    No further /validate-authcode call needed for headless flow.
    """
    app_id   = FYERS_CLIENT_ID.split("-")[0]
    app_type = FYERS_CLIENT_ID.split("-")[1] if "-" in FYERS_CLIENT_ID else "100"

    payload = {
        "fyers_id":       FYERS_USERNAME,
        "app_id":         app_id,
        "redirect_uri":   FYERS_REDIRECT_URI,
        "appType":        app_type,
        "code_challenge": "",
        "state":          "sample_state",
        "scope":          "",
        "nonce":          "",
        "response_type":  "code",
        "create_cookie":  True,
    }
    s, d = _post(URL_TOKEN, payload, headers={"Authorization": f"Bearer {trade_access_token}"})
    log.info("token → s=%s keys=%s", d.get("s"), list((d.get("data") or {}).keys()))

    if s == ERROR:
        return ERROR, f"Token request failed: {d.get('message', d)}"

    data = d.get("data") or {}

    # data.auth is the final access token for API calls
    token = data.get("auth", "")
    if token:
        log.info("Final access token obtained from data.auth ✅")
        return SUCCESS, token

    # Shouldn't reach here, but log full response for debugging
    return ERROR, f"data.auth missing. Full response: {d}"


# ─── PUBLIC ENTRY POINTS ─────────────────────────────────────────────────────

def login_with_totp() -> Tuple[bool, str]:
    """Full 4-step automated TOTP login. Returns (True, access_token) or (False, error)."""
    log.info("=== Fyers TOTP Login ===")

    # Step 1
    s, d = _send_login_otp(FYERS_USERNAME)
    if s == ERROR:
        return False, f"Step 1 failed: {d.get('message', d)}"
    request_key = d.get("request_key", "")
    if not request_key:
        return False, f"Step 1: no request_key. Response: {d}"
    log.info("Step 1 OK — request_key obtained")

    # Step 2
    s, d = _verify_totp(request_key)
    if s == ERROR or _is_error(d):
        return False, f"Step 2 (TOTP) failed: {d.get('message', d)}"
    request_key2 = d.get("request_key", request_key)
    log.info("Step 2 OK — TOTP verified")

    # Step 3
    s, d = _verify_pin(request_key2)
    if s == ERROR or _is_error(d):
        return False, f"Step 3 (PIN) failed: {d.get('message', d)}"
    trade_token = (d.get("data") or {}).get("access_token", "") or d.get("access_token", "")
    if not trade_token:
        return False, f"Step 3: no trade token in response: {d}"
    log.info("Step 3 OK — PIN verified, trade token obtained")

    # Step 4
    s, token = _get_final_token(trade_token)
    if s == ERROR:
        return False, f"Step 4 failed: {token}"

    log.info("=== Login SUCCESS ===")
    return True, token


# ─── SMS OTP FLOW ─────────────────────────────────────────────────────────────
_sms_state: dict = {}


def send_sms_otp() -> Tuple[bool, str]:
    """Step 1 for SMS flow — initiate login and request OTP."""
    s, d = _send_login_otp(FYERS_USERNAME)
    if s == ERROR:
        return False, d.get("message", str(d))
    rk = d.get("request_key", "")
    if not rk:
        return False, f"No request_key returned: {d}"
    _sms_state["request_key"] = rk
    return True, "OTP sent to your registered mobile/email."


def login_with_sms_otp(otp: str) -> Tuple[bool, str]:
    """Steps 2-4 for SMS flow after user enters OTP."""
    rk = _sms_state.get("request_key", "")
    if not rk:
        return False, "No session found. Click 'Send OTP' first."

    s, d = _verify_sms_otp(rk, otp)
    if s == ERROR or _is_error(d):
        return False, f"OTP failed: {d.get('message', d)}"
    rk2 = d.get("request_key", rk)

    s, d = _verify_pin(rk2)
    if s == ERROR or _is_error(d):
        return False, f"PIN failed: {d.get('message', d)}"
    trade_token = (d.get("data") or {}).get("access_token", "") or d.get("access_token", "")
    if not trade_token:
        return False, f"No trade token: {d}"

    s, token = _get_final_token(trade_token)
    if s == ERROR:
        return False, f"Final token failed: {token}"

    return True, token
