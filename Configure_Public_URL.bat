@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\configure_public_url.py
pause
