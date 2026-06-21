# scripts/ — scheduling (Phase 3 draft)

Windows Task Scheduler glue to run the daily **accumulation pass**
(`python -m phantom_ai_feed.accumulate`): conditional fetch (ETag/Last-Modified)
→ capture fresh entries into the local phantom FTS5 store, so the knowledge base
grows unattended.

> **狀態:草稿。** 這些腳本呼叫 `accumulate`,它隨 **PR #1**
> (`feat/fetch-concurrent-conditional-get`) 進入 master。**PR 合併後才啟用。**
> 排程是系統變更,建議當作獨立的 Phase 3 follow-up PR 提交,而非塞進 PR #1。

## Files

| File | What it does |
|---|---|
| `run-accumulate.ps1` | The wrapper the scheduled task runs. Picks the repo `.venv` python (falls back to PATH), runs `accumulate`, logs all output under `~/.phantom-mesh/logs/phantom-ai-feed/scheduler/`. |
| `register-task.ps1`  | Registers / replaces / removes the daily task (idempotent, S4U, catch-up). |

## No API key needed

`accumulate` is pure Python stdlib. The optional `phantom` CLI is only used to
write into FTS5 — if it is absent, capture degrades gracefully (those entries
count as `capture_failed` and the feed's validator is rolled back so the next
run re-fetches it) and the run still exits 0.

## Enable (after PR #1 merges to master)

```powershell
# 1. Smoke-test the wrapper first — writes nothing, no network:
$env:PHANTOM_AI_FEED_OFFLINE = '1'
.\scripts\run-accumulate.ps1 -DryRun
Remove-Item Env:\PHANTOM_AI_FEED_OFFLINE

# 2. Register the daily task (default 08:00, all feeds):
.\scripts\register-task.ps1

# …or core feeds only, at 07:30, and fire one run immediately to verify:
.\scripts\register-task.ps1 -Time 07:30 -Strict -RunNow
```

## Inspect / operate

```powershell
Get-ScheduledTaskInfo -TaskName 'phantom-ai-feed-accumulate'   # last result / next run
Start-ScheduledTask   -TaskName 'phantom-ai-feed-accumulate'   # run now
Get-Content "$HOME\.phantom-mesh\logs\phantom-ai-feed\scheduler\accumulate-$(Get-Date -Format yyyy-MM-dd).log"
.\scripts\register-task.ps1 -Unregister                        # remove
```

## Notes / decisions

- **S4U logon** runs the task without a stored password whether or not you are
  logged in; outbound HTTP (RSS fetch) works under S4U. It cannot reach mapped
  network shares — not needed here.
- **`StartWhenAvailable`** catches up a run missed because the machine was asleep
  at the trigger time.
- One run per day is enough: conditional GET means unchanged feeds are skipped
  cheaply, so a higher cadence mostly issues 304s.
- This replaces the old hailmary cron-only heartbeat **only when you decide to
  migrate** (see the main doc's Phase 3) — registering this task does not touch
  the existing launchd/cron heartbeat.
