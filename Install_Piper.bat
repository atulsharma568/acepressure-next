@echo off
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [AcePressure] .venv not found. Run Install.bat first.
    pause
    exit /b 1
)
echo.
echo [AcePressure] Installing Piper TTS (FREE, OFFLINE)
echo ---------------------------------------------------
echo Piper is a local neural TTS engine. Zero network calls at synthesis time,
echo zero cost, runs entirely on your CPU.
echo.
echo This will:
echo   1. Install the piper-tts Python package (~200 MB - includes ONNX runtime)
echo   2. Download 4 starter voices to data\piper-voices\ (~200 MB total)
echo        - Hindi male   (hi_IN-pratham-medium)
echo        - Hindi female (hi_IN-priyamvada-medium)
echo        - English male (en_US-ryan-medium)
echo        - English female (en_US-amy-medium)
echo.
echo After install, close AcePressure, run Start.bat again and open the TTS tab:
echo   - Piper as your main voice: under "Find and test real voices", set Voice source
echo     to Piper, click "Detect available voices", tick voices, then "Use selected voices".
echo   - Piper only when Edge, Azure or Windows voices fail: choose a Piper voice under
echo     "If the voice service fails" and click "Save backup voice".
echo.
pause
".venv\Scripts\python.exe" -m pip install --upgrade "piper-tts==1.8.0"
if errorlevel 1 (
    echo.
    echo [AcePressure] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo.
echo [AcePressure] Package installed. Downloading starter voices...
echo (Each voice is ~50 MB. First-time download, cached forever.)
".venv\Scripts\python.exe" "scripts\download_piper_voices.py"
if errorlevel 1 (
    echo.
    echo [AcePressure] Voice download encountered errors. You can re-run this script.
    pause
    exit /b 1
)
echo.
echo [AcePressure] Piper is ready. Close AcePressure, run Start.bat again, then in the TTS tab use
echo "Use selected voices" for Piper as your main voice, or "If the voice service fails" for a backup.
pause
