@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run Install.bat first.
 pause
 exit /b 1
)
echo This switches the existing Tailscale Funnel front door from Flask :8765 to Next :3000.
echo Start_Next.bat must be running before you continue.
echo The same public URL remains in use; admin, bridge and OBS paths are proxied back to Flask.
pause
".venv\Scripts\python.exe" "scripts\setup_tailscale_funnel.py" --port 3000
pause
