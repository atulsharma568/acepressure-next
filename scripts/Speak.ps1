$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voices = $synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo }
    $chosen = $voices | Where-Object { $_.Name -eq $payload.voice -or $_.Culture.Name -eq $payload.voice } | Select-Object -First 1
    if (-not $chosen) { throw 'Requested SAPI voice is not installed' }
    $synth.SelectVoice($chosen.Name)
    $synth.SetOutputToWaveFile($payload.output)
    $synth.Speak([string]$payload.text)
} finally { $synth.Dispose() }
