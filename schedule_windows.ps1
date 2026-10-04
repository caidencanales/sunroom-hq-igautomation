# Registers a Windows scheduled task that runs the daily outreach every morning.
# Run once from this folder:   powershell -ExecutionPolicy Bypass -File schedule_windows.ps1
# The PC needs to be on and you need to be logged in (the bot uses a visible browser window).

param([string]$At = "8:30am")

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python).Source

$action   = New-ScheduledTaskAction -Execute $python -Argument "run.py daily" -WorkingDirectory $dir
$trigger  = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 13)

Register-ScheduledTask -TaskName "Sunroom Outreach" -Action $action -Trigger $trigger -Settings $settings -Force
Write-Host "Scheduled 'Sunroom Outreach' daily at $At (folder: $dir)"
Write-Host "Remove it with: Unregister-ScheduledTask -TaskName 'Sunroom Outreach'"
