# NIFTY Terminal — Install all dependencies
Set-Location $PSScriptRoot
Write-Host "Installing Python packages..." -ForegroundColor Cyan
pip install -r requirements.txt
Write-Host "Installing Node packages..." -ForegroundColor Cyan
Set-Location frontend
npm install
Set-Location ..
Write-Host "Done! Run START_BACKEND.ps1 and START_FRONTEND.ps1" -ForegroundColor Green
