@echo off
setlocal
cd /d "%~dp0"
title AcePressure - Fix Broken Audio
REM Path variables are only expanded outside ( ) blocks and inside quotes, so names such as
REM "bruh (1).mp3", "Tom & Jerry.mp3" or "wow!.mp3" are handled safely.

REM --- Locate ffmpeg: bundled first, then PATH ---
set "FFMPEG="
if exist "%~dp0tools\bin\ffmpeg.exe" set "FFMPEG=%~dp0tools\bin\ffmpeg.exe"
if defined FFMPEG goto have_ffmpeg
where ffmpeg >nul 2>nul
if errorlevel 1 goto no_ffmpeg
set "FFMPEG=ffmpeg"
:have_ffmpeg

if "%~1"=="" goto help

echo.
echo    Converting your audio files to browser-safe standard MP3...
echo    Clips longer than 20 seconds are cut to 20 seconds.
echo.
set /a OK=0
set /a FAIL=0

:loop
if "%~1"=="" goto done
set "SRC=%~f1"
set "OUT=%~dpn1_fixed.mp3"
set "NAME=%~nx1"
set "OUTNAME=%~n1_fixed.mp3"
if exist "%SRC%" goto convert
echo    [SKIP] "%NAME%" - file not found
set /a FAIL+=1
goto next

:convert
echo    [....] "%NAME%"
"%FFMPEG%" -v error -y -i "%SRC%" -codec:a libmp3lame -b:a 128k -ar 48000 -ac 2 -map_metadata -1 -map 0:a:0 -t 20 "%OUT%"
if errorlevel 1 goto failed
echo    [ OK ] "%NAME%" -^> "%OUTNAME%"
set /a OK+=1
goto next

:failed
echo    [FAIL] "%NAME%" - could not re-encode. The original file may be damaged.
set /a FAIL+=1

:next
shift
goto loop

:done
echo.
echo    ==============================
echo    Fixed: %OK%    Failed: %FAIL%
echo    ==============================
echo.
if %OK%==0 goto finish
echo    Upload the *_fixed.mp3 files via:
echo        Admin -^> Sound library -^> Add a sound
echo    OR to change the audio of a sound already in the library:
echo        Admin -^> Sound library -^> Replace audio (or Upload audio on a meme slot)
echo    This tool cuts clips at 20 seconds. Library sounds may run up to 30 seconds,
echo    so for a longer sound upload the original file instead: the admin
echo    page converts it without cutting it.
echo.
goto finish

:help
echo.
echo    AcePressure - Fix Broken Audio
echo    ==============================
echo.
echo    OPTIONAL: with FFmpeg installed (Install_Media_Tools.bat), the admin
echo    page fixes broken audio by itself when you upload it. Use this tool to
echo    convert many files at once, or to listen to a fixed file before uploading.
echo.
echo    Drag one or more MP3 / OGG / WAV files onto this .bat file.
echo    Each file is re-encoded to a browser-safe standard MP3:
echo        - MPEG Layer 3 (the only MP3 variant browsers decode)
echo        - 128 kbps constant bitrate
echo        - 48 kHz stereo
echo        - All metadata, cover art, ID3 extras stripped
echo        - Cut to 20 seconds at most. Library sounds may run up to 30 seconds,
echo          so upload a longer sound as the original file instead.
echo.
echo    The fixed file is saved next to the original as:
echo        ^<name^>_fixed.mp3
echo.
echo    Then: Admin -^> Sound library -^> Add a sound -^> pick ^<name^>_fixed.mp3
echo.
goto finish

:no_ffmpeg
echo.
echo    ffmpeg was not found. Run Install_Media_Tools.bat first, then try again.
echo.
pause
exit /b 1

:finish
pause
exit /b 0
