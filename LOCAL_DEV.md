# Running Locally (Windows)

## Backend
```cmd
cd nifty_v2\backend
pip install -r ..\requirements.txt
uvicorn server:app --reload --port 8000
```

## Frontend (separate terminal)
```cmd
cd nifty_v2\frontend
npm install
npm run dev
```

Open: http://localhost:5173

---

# Running on Render

Push to GitHub. Render reads render.yaml automatically.
Build runs: pip install + npm build
Start runs: uvicorn server:app

The React frontend is built into frontend/dist/ and served
as static files by FastAPI at the root URL.

---

# Session Persistence

Access token is stored in SQLite (paper_trading.db).
- After login: token saved with 23h expiry
- Browser reopen: token auto-restored, strategy re-initialised
- Token expiry: shown in Session tab header

---

# Telegram Commands

START  → Login (TOTP) + init + start strategy
STOP   → Close all positions + stop
STATUS → P&L + position report
PAUSE  → Stop new entries (keep positions)
RESUME → Resume entries
HELP   → Show commands
