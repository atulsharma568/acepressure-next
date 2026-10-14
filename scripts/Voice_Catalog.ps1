$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $items = @($synth.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object {
        $v = $_.VoiceInfo
        @{ id=$v.Name; label=([string]$v.Gender + ' | ' + $v.Culture.Name + ' | ' + $v.Name); gender=[string]$v.Gender; locale=$v.Culture.Name }
    })
    ConvertTo-Json -InputObject $items -Compress
} finally { $synth.Dispose() }
