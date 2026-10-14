@echo off
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [AcePressure] .venv not found. Run Install.bat first.
    pause
    exit /b 1
)
echo.
echo [AcePressure] Tailscale Funnel setup
echo ----------------------------------------
echo This gives you a FREE, PERMANENT public HTTPS URL for your tip page.
echo No domain purchase. No ngrok warning page. Your iPhone Shortcut
echo automation will keep working forever because the URL never changes.
echo.
echo If Tailscale is not installed yet, the script will tell you where to get it.
echo The first time, Tailscale may ask you to approve HTTPS certificates and Funnel in your browser.
echo.
pause
".venv\Scripts\python.exe" "scripts\setup_tailscale_funnel.py" %*
pause
