@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
 echo Install Python 3.12 or newer from python.org with the Python Launcher, then rerun.
 pause
 exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" setup.py
if errorlevel 1 goto fail
echo Installation complete. Read README.md, then run Start_Demo.bat or Start.bat.
pause
exit /b 0
:fail
echo Installation failed. Review the error above; no OBS files were changed.
pause
exit /b 1
