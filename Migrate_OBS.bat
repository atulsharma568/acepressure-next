@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if "%~1"=="" (
 echo Drag an exported OBS scene collection JSON onto this BAT.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" scripts\migrate_obs.py "%~1"
pause
