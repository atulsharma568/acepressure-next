@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo } | Select-Object Name,Culture; $s.Dispose()"
pause
