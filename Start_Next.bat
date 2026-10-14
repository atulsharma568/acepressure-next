@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run Install.bat first.
 pause
 exit /b 1
)
if not exist "web\node_modules\.bin\next.cmd" (
 echo Run Install_Web.bat first.
 pause
 exit /b 1
)
if not exist ".env" (
 echo Run Install.bat and complete first-run setup first.
 pause
 exit /b 1
)
echo Starting the Next.js public front door on port 3000 first...
start "AcePressure Next frontend" /D "%~dp0web" cmd /c "npm run start -- -p 3000"
timeout /t 3 /nobreak >nul
echo Starting the AcePressure backend on the configured Flask port...
start "AcePressure Next backend" /D "%~dp0" /MIN cmd /c ""%~dp0.venv\Scripts\python.exe" "%~dp0run.py""
echo Both processes were started. Keep their windows running while streaming.
pause
