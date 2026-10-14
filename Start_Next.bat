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
if not exist "web\.next\BUILD_ID" (
 echo The Next frontend has not been built yet. Building it now, this takes a minute...
 pushd web
 call npm run build
 if errorlevel 1 (
  popd
  echo The build failed. Review the error above, then run Install_Web.bat again.
  pause
  exit /b 1
 )
 popd
)
echo Starting the Next.js public front door on port 3000 first...
start "AcePressure Next frontend" /D "%~dp0web" cmd /c "npm run start -- -p 3000"
timeout /t 3 /nobreak >nul
echo Starting the AcePressure backend on the configured Flask port...
start "AcePressure Next backend" /D "%~dp0" /MIN cmd /c ""%~dp0.venv\Scripts\python.exe" "%~dp0run.py""
echo Both processes were started. Keep their windows running while streaming.
pause
