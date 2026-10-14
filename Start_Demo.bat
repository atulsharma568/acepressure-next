@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
set "DEMO_MODE=true"
set "DATA_DIR=data-demo"
set "PORT=8766"
set "PUBLIC_BASE_URL=http://localhost:8766"
set "COOKIE_SECURE=false"
set "TRUST_CLOUDFLARE=false"
echo DEMO ONLY - http://localhost:8766 - no real payments or QR codes.
".venv\Scripts\python.exe" run.py
if errorlevel 1 pause
