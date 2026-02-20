"""
Background scheduler using APScheduler.
Manages auto-start, stop, force-close, and EOD reporting.
All times in IST.
"""

from __future__ import annotations
import threading
from datetime import datetime
from typing import Optional, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from core.config import IST
from utils.logger import get_logger

log = get_logger(__name__)


class TradingScheduler:
    """Manages timed execution of strategy lifecycle events."""

    def __init__(self):
        self._scheduler = BackgroundScheduler(timezone=IST)
        self._started = False
        self._lock = threading.Lock()

        # Callbacks — set by the app before starting
        self.on_market_open: Optional[Callable] = None      # 09:20 — start strategy
        self.on_no_new_trades: Optional[Callable] = None    # 14:45 — stop new entries
        self.on_force_close: Optional[Callable] = None      # 15:10 — close all
        self.on_eod_report: Optional[Callable] = None       # 15:20 — send report
        self.on_monitor: Optional[Callable] = None          # every 30s — update prices

    def setup(
        self,
        on_market_open: Callable,
        on_no_new_trades: Callable,
        on_force_close: Callable,
        on_eod_report: Callable,
        on_monitor: Callable,
    ) -> None:
        self.on_market_open   = on_market_open
        self.on_no_new_trades = on_no_new_trades
        self.on_force_close   = on_force_close
        self.on_eod_report    = on_eod_report
        self.on_monitor       = on_monitor

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._register_jobs()
            self._scheduler.start()
            self._started = True
            log.info("TradingScheduler started.")

    def stop(self) -> None:
        with self._lock:
            if self._started:
                self._scheduler.shutdown(wait=False)
                self._started = False
                log.info("TradingScheduler stopped.")

    def is_running(self) -> bool:
        return self._started

    # ─── JOB REGISTRATION ────────────────────────────────────────────────────

    def _register_jobs(self) -> None:
        # Market open — Mon-Fri 09:20
        self._scheduler.add_job(
            self._safe_call(self.on_market_open),
            CronTrigger(day_of_week="mon-fri", hour=9, minute=20, timezone=IST),
            id="market_open",
            replace_existing=True,
            misfire_grace_time=60,
        )

        # No new trades — Mon-Fri 14:45
        self._scheduler.add_job(
            self._safe_call(self.on_no_new_trades),
            CronTrigger(day_of_week="mon-fri", hour=14, minute=45, timezone=IST),
            id="no_new_trades",
            replace_existing=True,
        )

        # Force close — Mon-Fri 15:10
        self._scheduler.add_job(
            self._safe_call(self.on_force_close),
            CronTrigger(day_of_week="mon-fri", hour=15, minute=10, timezone=IST),
            id="force_close",
            replace_existing=True,
        )

        # EOD report — Mon-Fri 15:20
        self._scheduler.add_job(
            self._safe_call(self.on_eod_report),
            CronTrigger(day_of_week="mon-fri", hour=15, minute=20, timezone=IST),
            id="eod_report",
            replace_existing=True,
        )

        # Position monitor — every 30 seconds
        self._scheduler.add_job(
            self._safe_call(self.on_monitor),
            "interval",
            seconds=30,
            id="monitor",
            replace_existing=True,
        )

        log.info("Scheduled jobs registered.")

    @staticmethod
    def _safe_call(fn: Optional[Callable]) -> Callable:
        """Wrap callback to catch and log exceptions."""
        def wrapper():
            if fn:
                try:
                    fn()
                except Exception as e:
                    log.error("Scheduler callback error: %s", e, exc_info=True)
        return wrapper
