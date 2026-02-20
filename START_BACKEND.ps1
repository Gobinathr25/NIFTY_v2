# NIFTY Terminal — Backend
Set-Location $PSScriptRoot\backend
python -m uvicorn server:app --reload --port 8000
