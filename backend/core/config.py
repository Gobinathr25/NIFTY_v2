"""Central config — same as original but with FastAPI-friendly paths."""
import os
import pytz

IST        = pytz.timezone("Asia/Kolkata")
PAPER_MODE = True
DB_PATH    = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "paper_trading.db"))

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE  = os.environ.get("LOG_FILE",  os.path.join(os.path.dirname(__file__), "..", "nifty_terminal.log"))

# Strategy defaults
NIFTY_LOT_SIZE          = 65
MAX_TRADES_PER_DAY      = 2
HEDGE_DELTA_TARGET      = 0.10
GAMMA_ADJUSTMENT_LEVELS = [0.30, 0.50, 0.70]
STOP_LOSS_PCT           = 0.50
