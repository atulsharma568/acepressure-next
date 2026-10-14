@echo off
setlocal
cd /d "%~dp0"
where winget >nul 2>nul
if errorlevel 1 (
 echo Windows Package Manager was not found. See docs\TTS_AND_MEDIA.md for manual installation.
 pause
 exit /b 1
)
echo This installs FFmpeg through Windows Package Manager for optional video uploads.
echo It does not change your AcePressure data or payment settings.
winget install --id Gyan.FFmpeg --exact --source winget
if errorlevel 1 (
 echo Installation did not complete. GIF and PNG uploads remain available.
) else (
 echo Close and reopen AcePressure so the new PATH is available.
)
pause
