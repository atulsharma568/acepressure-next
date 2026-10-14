@echo off
set "PYTHONUTF8=1"
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\generate_channel_qr.py
pause
