# phantom-ai-feed

[![CI](https://github.com/markl-a/phantom-ai-feed/actions/workflows/ci.yml/badge.svg)](https://github.com/markl-a/phantom-ai-feed/actions/workflows/ci.yml)
![license: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)
[![phantom-mesh ecosystem](https://img.shields.io/badge/ecosystem-phantom--mesh-purple)](https://github.com/markl-a/phantom-mesh)

> 給中文 AI/ML 工程師的「每天 10 分鐘讀完 → 週末自動出面試題複習 → 本機 RAG 可查」三合一本機資訊代謝管線(phantom-mesh 生態系)。純 Python stdlib、不外洩、owned-memory + SRS。

## Quickstart

```powershell
python -m pip install -e .[dev]
python -m pytest -q
```

After install, the public console scripts are:

| Command | Purpose |
| --- | --- |
| `phantom-ai-feed` | run the chained daily/weekly pipeline |
| `phantom-ai-feed-digest` | write a daily digest |
| `phantom-ai-feed-weekly` | write a weekly digest |
| `phantom-ai-feed-recall` | search the local FTS5 knowledge store |
| `phantom-ai-feed-srs` | review generated SRS cards |
| `phantom-ai-feed-export` | write source adapter and collection/review export artifacts |
| `phantom-ai-feed-scenario` | write a knowledge-intake recall/SRS scenario proof |

No-network smoke check:

```powershell
$env:PHANTOM_AI_FEED_OFFLINE = "1"
phantom-ai-feed-digest --use-stub --strict --force --out .\demo-out
Remove-Item Env:\PHANTOM_AI_FEED_OFFLINE
```

Offline mode deliberately records per-feed fetch errors instead of reaching the
network. Use it to verify the CLI, rendering path, and output directory on a
fresh clone. Real feed fetching is opt-in by leaving `PHANTOM_AI_FEED_OFFLINE`
unset.

Deterministic synthetic knowledge demo-loop:

```powershell
$bundle = Join-Path $env:TEMP ("phantom-ai-feed-loop-" + [guid]::NewGuid().ToString("N"))
python -m phantom_ai_feed.demo_loop --out $bundle --date 2026-06-26 --query RAG
Get-Content (Join-Path $bundle "manifest.json")
```

The bundle uses synthetic local feed items only. It writes a digest, local FTS5
store, recall result, review cards, SRS due report, and manifest with no network
fetching, no cloud LLM, no credentials, and no private reading history. The
artifact contract is documented in
[docs/SYNTHETIC_KNOWLEDGE_LOOP.md](docs/SYNTHETIC_KNOWLEDGE_LOOP.md).

Deterministic source adapter/export bundle:

```powershell
$export = Join-Path $env:TEMP ("phantom-ai-feed-export-" + [guid]::NewGuid().ToString("N"))
python -m phantom_ai_feed.source_export --source $bundle --out $export
Get-Content (Join-Path $export "source-adapter-contract.json")
```

The export bundle writes a source adapter contract, collection export, review
export, and summary from the synthetic demo-loop artifacts. It does not fetch
live feeds, require API keys, include private credentials, include cookies,
include personal annotations, include private reading logs, or imply that
fixture entries came from live sources. The contract is documented in
[docs/SOURCE_EXPORT_BUNDLE.md](docs/SOURCE_EXPORT_BUNDLE.md).

Deterministic knowledge-intake scenario proof:

```powershell
$scenario = Join-Path $env:TEMP ("phantom-ai-feed-scenario-" + [guid]::NewGuid().ToString("N"))
python -m phantom_ai_feed.knowledge_scenario --source $bundle --out $scenario
Get-Content (Join-Path $scenario "knowledge-scenario.json")
```

The scenario bundle proves the P3 path: multi-source synthetic intake, local
recall for a query, SRS review readiness, and a metadata-only recall review
plan. The contract is documented in
[docs/KNOWLEDGE_SCENARIO_BUNDLE.md](docs/KNOWLEDGE_SCENARIO_BUNDLE.md).

📄 完整文件(定位/快速上手/狀態/路線圖/開源生態):見 [docs/phantom-ai-feed.md](docs/phantom-ai-feed.md)
