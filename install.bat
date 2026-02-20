@echo off
echo Installing NIFTY Terminal dependencies...
echo.
echo [1/3] Installing Python packages...
pip install -r requirements.txt
echo.
echo [2/3] Installing Node.js packages...
cd frontend
npm install
cd ..
echo.
echo [3/3] All done!
echo.
echo To run the app:
echo   1. Double-click run_backend.bat   (keep this window open)
echo   2. Double-click run_frontend.bat  (keep this window open)
echo   3. Open http://localhost:5173 in your browser
pause
