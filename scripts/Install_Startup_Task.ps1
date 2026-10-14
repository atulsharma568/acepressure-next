# Optional: run from PowerShell under your normal Windows account.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run Install.bat first' }
$action = New-ScheduledTaskAction -Execute $python -Argument ('"' + (Join-Path $root 'run.py') + '"') -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'AcePressure Tipping' -Action $action -Trigger $trigger -Settings $settings -Description 'AcePressure local tipping server (starts at sign-in)' | Out-Null
Write-Host 'Installed. Starts at your next sign-in. Do not also run Start.bat simultaneously.'
