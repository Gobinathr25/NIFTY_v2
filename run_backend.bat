@echo off
echo Starting NIFTY Terminal Backend...
cd /d %~dp0backend
python -m uvicorn server:app --reload --port 8000
pause
