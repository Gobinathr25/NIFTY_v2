"""
Telegram Command Listener — background polling thread.

Listens for commands from the bot owner (your chat_id only).
Commands:
  /start or START   — Login via TOTP + initialise + start strategy
  /stop or STOP     — Stop new entries + close all open positions
  /status or STATUS — Report current strategy status, P&L, positions
  /pause or PAUSE   — Stop new entries (keep existing positions)
  /resume or RESUME — Resume new entries
  /help or HELP     — Show available commands

Security: Only responds to messages from TELEGRAM_CHAT_ID.
All other senders receive no response (silent reject).
"""

from __future__ import annotations
import threading
import time
import requests
from typing import Optional, Callable
from utils.logger import get_logger

log = get_logger(__name__)

# Polling interval in seconds
POLL_INTERVAL = 3


class TelegramCommandListener:
    """
    Long-polls the Telegram Bot API for messages.
    Runs in a daemon thread — stops automatically when app exits.
    Exposes callback hooks that app.py wires to strategy actions.
    """

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token  = bot_token
        self.chat_id    = str(chat_id).strip()
        self._base      = f"https://api.telegram.org/bot{bot_token}"
        self._offset    = 0
        self._running   = False
        self._thread: Optional[threading.Thread] = None

        # ── Callbacks wired by the app ────────────────────────────────────────
        self.on_start:  Optional[Callable] = None   # START command
        self.on_stop:   Optional[Callable] = None   # STOP command
        self.on_status: Optional[Callable] = None   # STATUS command
        self.on_pause:  Optional[Callable] = None   # PAUSE command
        self.on_resume: Optional[Callable] = None   # RESUME command

    # ─── Public control ───────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._poll_loop, daemon=True, name="tg-cmd-listener")
        self._thread.start()
        log.info("Telegram command listener started (chat_id=%s)", self.chat_id)

    def stop(self) -> None:
        self._running = False
        log.info("Telegram command listener stopped.")

    def send(self, message: str) -> None:
        """Send a message back to the owner."""
        try:
            requests.post(
                f"{self._base}/sendMessage",
                json={
                    "chat_id":   self.chat_id,
                    "text":      message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=8,
            )
        except Exception as e:
            log.error("Telegram send error: %s", e)

    # ─── Internal polling ─────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        """Long-poll loop — runs in background thread."""
        # Drain existing messages on startup so we don't replay old commands
        self._drain_old_messages()

        while self._running:
            try:
                updates = self._get_updates()
                for upd in updates:
                    self._offset = upd["update_id"] + 1
                    self._handle_update(upd)
            except Exception as e:
                log.error("Telegram poll error: %s", e)
            time.sleep(POLL_INTERVAL)

    def _drain_old_messages(self) -> None:
        """Consume all pending messages so we start fresh."""
        try:
            resp = requests.get(
                f"{self._base}/getUpdates",
                params={"timeout": 0, "offset": -1},
                timeout=10,
            )
            data = resp.json()
            if data.get("ok") and data.get("result"):
                self._offset = data["result"][-1]["update_id"] + 1
                log.info("Telegram: drained old messages, offset=%d", self._offset)
        except Exception:
            pass

    def _get_updates(self) -> list:
        try:
            resp = requests.get(
                f"{self._base}/getUpdates",
                params={"timeout": 10, "offset": self._offset, "allowed_updates": ["message"]},
                timeout=15,
            )
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
        except Exception:
            pass
        return []

    def _handle_update(self, upd: dict) -> None:
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            return

        # ── Security: only owner ─────────────────────────────────────────────
        sender_id = str(msg.get("chat", {}).get("id", ""))
        if sender_id != self.chat_id:
            log.warning("Rejected command from unknown chat_id: %s", sender_id)
            return

        text = (msg.get("text") or "").strip().upper()
        # Strip leading slash if present
        if text.startswith("/"):
            text = text[1:]

        log.info("Telegram command received: %s", text)

        if text in ("START", "GO", "LOGIN"):
            self.send("🔄 *Received START command*\nInitiating session and starting strategy…")
            self._run_cb(self.on_start, "START")

        elif text in ("STOP", "EXIT", "CLOSE"):
            self.send("🔄 *Received STOP command*\nClosing all positions and stopping strategy…")
            self._run_cb(self.on_stop, "STOP")

        elif text in ("STATUS", "PNL", "REPORT"):
            self._run_cb(self.on_status, "STATUS")

        elif text in ("PAUSE", "HOLD"):
            self.send("⏸ *Received PAUSE command*\nStopping new entries. Existing positions kept open.")
            self._run_cb(self.on_pause, "PAUSE")

        elif text in ("RESUME", "CONTINUE"):
            self.send("▶️ *Received RESUME command*\nResuming new entries.")
            self._run_cb(self.on_resume, "RESUME")

        elif text in ("HELP", "COMMANDS", "?"):
            self.send(
                "📋 *NIFTY Terminal Commands*\n\n"
                "`START` — Login + initialise + start strategy\n"
                "`STOP` — Close all positions + stop strategy\n"
                "`PAUSE` — Stop new entries (keep positions)\n"
                "`RESUME` — Resume new entries\n"
                "`STATUS` — Current P&L and position report\n"
                "`HELP` — Show this message"
            )
        else:
            self.send(f"❓ Unknown command: `{text}`\nType `HELP` for available commands.")

    def _run_cb(self, cb: Optional[Callable], name: str) -> None:
        """Run callback in a separate thread to avoid blocking the poll loop."""
        if cb is None:
            self.send(f"⚠️ `{name}` handler not configured yet.")
            return
        def _run():
            try:
                cb()
            except Exception as e:
                log.error("Command callback %s error: %s", name, e)
                self.send(f"❌ Error executing `{name}`: {e}")
        threading.Thread(target=_run, daemon=True, name=f"tg-cmd-{name}").start()
