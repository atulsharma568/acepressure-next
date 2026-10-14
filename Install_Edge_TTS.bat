@echo off
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [AcePressure] .venv not found. Run Install.bat first.
    pause
    exit /b 1
)
echo.
echo [AcePressure] Installing Edge TTS (FREE)
echo ----------------------------------------
echo Edge TTS gives you Microsoft Neural voices (the same voices as paid Azure)
echo for FREE - no API key, no credit card, no account. It uses the public
echo Microsoft Edge TTS endpoint, which has been stable for years.
echo.
echo After install:
echo   1. Open AcePressure admin
echo   2. Go to TTS tab
echo   3. Set Engine = "edge"
echo   4. Click "Detect voices" - pick any voice tagged HINGLISH-READY
echo      (Multilingual Neural) or Hindi (hi-IN) for Hindi/Hinglish messages.
echo.
pause
".venv\Scripts\python.exe" -m pip install --upgrade "edge-tts>=6.1.0"
if errorlevel 1 (
    echo.
    echo [AcePressure] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo.
echo [AcePressure] Edge TTS installed. Restart Start.bat to pick up the new engine.
pause
