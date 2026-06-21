#Requires -Version 5.1
<#
.SYNOPSIS
  Wrapper invoked by Windows Task Scheduler to run the phantom-ai-feed
  accumulation pass: conditional fetch (ETag/Last-Modified) -> capture fresh
  entries into the local phantom FTS5 store.

.DESCRIPTION
  Pure-stdlib + optional `phantom` CLI: no API key is required. When `phantom`
  is absent, capture degrades (entries are counted as capture_failed and that
  feed's validator is rolled back so the next run re-fetches it) and the run
  still exits cleanly.

  Logs every run (all streams) under
  ~/.phantom-mesh/logs/phantom-ai-feed/scheduler/accumulate-<date>.log.

.NOTES
  DRAFT — runs `python -m phantom_ai_feed.accumulate`, which lands on master
  with PR #1 (feat/fetch-concurrent-conditional-get). Register it via
  register-task.ps1 AFTER that PR merges.

.EXAMPLE
  # Smoke test without writing anything (offline + dry-run):
  $env:PHANTOM_AI_FEED_OFFLINE = '1'
  .\run-accumulate.ps1 -DryRun
#>
[CmdletBinding()]
param(
  [switch]$Strict,                 # skip feeds flagged optional=true
  [switch]$DryRun,                 # build capture commands, write nothing
  [string]$Feeds,                  # override feeds.toml path
  [string]$Cache,                  # override validator-cache path
  [int]$TopN = 3
)

$ErrorActionPreference = 'Stop'

# Repo root = parent of this script's folder (scripts/..).
$RepoRoot = Split-Path -Parent $PSScriptRoot

# Prefer the repo venv interpreter; fall back to `python` on PATH.
$VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Python = if (Test-Path $VenvPy) { $VenvPy } else { 'python' }

# Module argument list.
$ModuleArgs = @('-m', 'phantom_ai_feed.accumulate', '--top-n', $TopN)
if ($Strict) { $ModuleArgs += '--strict' }
if ($DryRun) { $ModuleArgs += '--dry-run' }
if ($Feeds)  { $ModuleArgs += @('--feeds', $Feeds) }
if ($Cache)  { $ModuleArgs += @('--cache', $Cache) }

# Log alongside the tool's other outputs.
$LogDir = Join-Path $HOME '.phantom-mesh\logs\phantom-ai-feed\scheduler'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("accumulate-{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))

"==== {0} :: {1} {2} ====" -f (Get-Date -Format o), $Python, ($ModuleArgs -join ' ') |
  Out-File -FilePath $Log -Append -Encoding utf8

# Run from the repo root so `python -m phantom_ai_feed.accumulate` resolves.
Push-Location $RepoRoot
try {
  & $Python @ModuleArgs *>> $Log
  $code = $LASTEXITCODE
} finally {
  Pop-Location
}

"==== exit {0} @ {1} ====" -f $code, (Get-Date -Format o) |
  Out-File -FilePath $Log -Append -Encoding utf8
exit $code
