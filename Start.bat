@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run Install.bat first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" run.py
if errorlevel 1 pause
