#Requires -Version 5.1
<#
.SYNOPSIS
  Register (or replace / remove) the daily Windows Scheduled Task that runs the
  phantom-ai-feed accumulation pass via run-accumulate.ps1.

.DESCRIPTION
  Idempotent: -Force replaces an existing task of the same name. The task runs
  whether or not the user is logged on (S4U: no stored password) and catches up
  a missed run (StartWhenAvailable) if the machine was asleep at the trigger
  time. No elevation needed for a Limited-runlevel user task.

.NOTES
  DRAFT — do NOT run until PR #1 (feat/fetch-concurrent-conditional-get) lands on
  master, since the wrapper invokes `python -m phantom_ai_feed.accumulate`.
  Registering a task is a system change; review the parameters first.

.EXAMPLE
  .\register-task.ps1                          # daily 08:00, all feeds
.EXAMPLE
  .\register-task.ps1 -Time 07:30 -Strict -RunNow   # core feeds, fire once now
.EXAMPLE
  .\register-task.ps1 -Unregister              # remove the task
#>
[CmdletBinding()]
param(
  [string]$TaskName = 'phantom-ai-feed-accumulate',
  [string]$Time = '08:00',
  [switch]$Strict,
  [switch]$RunNow,
  [switch]$Unregister
)

$ErrorActionPreference = 'Stop'

if ($Unregister) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed scheduled task '$TaskName' (if it existed)."
  return
}

$Runner = Join-Path $PSScriptRoot 'run-accumulate.ps1'
if (-not (Test-Path $Runner)) { throw "runner not found: $Runner" }

# The task launches PowerShell to run the wrapper (no profile, bypass policy).
$psArgs = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $Runner
if ($Strict) { $psArgs += ' -Strict' }

$action    = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $psArgs
$trigger   = New-ScheduledTaskTrigger -Daily -At $Time
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
              -LogonType S4U -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
              -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Registered daily task '$TaskName' at $Time -> $Runner"
Write-Host "Inspect:  Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Host "Run now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Logs:     `$HOME\.phantom-mesh\logs\phantom-ai-feed\scheduler\"

if ($RunNow) {
  Start-ScheduledTask -TaskName $TaskName
  Write-Host "Triggered an immediate run."
}
