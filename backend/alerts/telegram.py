"""
Telegram notification service.
Sends formatted alerts for trade events.
"""

from __future__ import annotations
import requests
from typing import Optional
from utils.logger import get_logger

log = get_logger(__name__)


class TelegramNotifier:
    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._enabled = bool(bot_token and chat_id)

    def send(self, message: str) -> bool:
        """Send a Markdown-formatted message. Returns True on success."""
        if not self._enabled:
            log.debug("Telegram not configured — skipping alert.")
            return False
        try:
            url = self.BASE_URL.format(token=self.bot_token)
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            resp = requests.post(url, json=payload, timeout=8)
            data = resp.json()
            if data.get("ok"):
                log.info("Telegram alert sent.")
                return True
            else:
                log.error("Telegram error: %s", data)
        except Exception as e:
            log.error("Telegram send exception: %s", e)
        return False

    def test(self) -> bool:
        return self.send("✅ *NIFTY Terminal*\nTelegram connection test successful!")

    def send_eod_report(
        self,
        total_trades: int,
        net_pnl: float,
        max_dd: float,
        win_rate: float,
    ) -> None:
        msg = (
            f"📊 *END OF DAY REPORT*\n"
            f"Total Trades: {total_trades}\n"
            f"Net P&L: ₹{net_pnl:.0f}\n"
            f"Max Drawdown: ₹{max_dd:.0f}\n"
            f"Win Rate: {win_rate:.1f}%"
        )
        self.send(msg)

    def send_entry_alert(
        self,
        ce_strike: int,
        pe_strike: int,
        premium: float,
        risk: float,
        spot: float,
    ) -> None:
        msg = (
            f"🚀 *ENTRY*\n"
            f"Strategy: Supertrend Gamma Strangle\n"
            f"Strikes: CE {ce_strike} | PE {pe_strike}\n"
            f"Premium Collected: ₹{premium:.0f}\n"
            f"Risk: ₹{risk:.0f}\n"
            f"Spot: {spot:.2f}"
        )
        self.send(msg)

    def send_adjustment_alert(self, level: int, action: str, reason: str) -> None:
        msg = (
            f"⚠️ *GAMMA ADJUSTMENT LEVEL {level}*\n"
            f"Action Taken: {action}\n"
            f"Reason: {reason}"
        )
        self.send(msg)

    def send_exit_alert(self, pnl: float, capital: float, reason: str) -> None:
        pct = pnl / capital * 100 if capital > 0 else 0
        msg = (
            f"✅ *EXIT*\n"
            f"P&L: ₹{pnl:.0f}\n"
            f"Return %: {pct:.2f}%\n"
            f"Reason: {reason}"
        )
        self.send(msg)
