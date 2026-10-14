@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pytest -q
pause
