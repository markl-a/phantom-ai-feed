# phantom-ai-feed

[![CI](https://github.com/markl-a/phantom-ai-feed/actions/workflows/ci.yml/badge.svg)](https://github.com/markl-a/phantom-ai-feed/actions/workflows/ci.yml)

> 中文 AI 工程師日報 + 面試題自動生成器 + on-prem RAG-ready 知識庫 — 跨裝置一站式資訊代謝管線,招聘對齊中型 AI 新創、副業可走 Substack。

![license: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)
[![phantom-mesh ecosystem](https://img.shields.io/badge/ecosystem-phantom--mesh-purple)](https://github.com/markl-a/phantom-mesh)

> **Docs:** start at [`docs/INDEX.md`](docs/INDEX.md) · **Status:** see [`ROADMAP.md`](ROADMAP.md)

## 30-second demo

[`docs/demo.cast`](docs/demo.cast) — asciinema recording of `phantom_ai_feed.digest --use-stub --force` writing today's RSS digest.

```sh
# play in a terminal (requires asciinema)
asciinema play docs/demo.cast

# or view the captured text without any tooling:
cat docs/demo.cast | jq -r '.[] | select(.[1]=="o") | .[2]'
```

Self-hosted on purpose — no upload to asciinema.org, no third-party tracking.

## 一句話 niche

給中文 AI/ML 工程師的「每天 10 分鐘讀完 + 週末自動出面試題複習 + 本機 RAG 可
查」三合一管線。Daily.dev / Feedly+AI 是英文圈 + cloud-only;Substack
electronic newsletter 是手寫;**phantom-ai-feed 是中文 + 本機 + agentic**
— RSS 抓取走你的 phantom-mesh,摘要與面試題用可換的 LLM provider,所有資料
落在 `~/.phantom-mesh/` 不外洩。延續並重定位
[markl-a/My-AI-Learning-Notes](https://github.com/markl-a/My-AI-Learning-Notes)
(19 stars, Jupyter notebook 系列)為 daemon-friendly 的自動化資訊流。

## Status

狀態(Shipped / In progress / Planned-next)的唯一真實來源見 **[`ROADMAP.md`](ROADMAP.md)**。

## 30-second quickstart

```bash
git clone https://github.com/markl-a/phantom-ai-feed
cd phantom-ai-feed
# 無需安裝任何 runtime 套件 — 純 Python 3.11+ 標準函式庫(urllib / xml.etree / tomllib)
# 只有要跑測試時才需要:pip install pytest

# 無 API key — 用 stub summarizer 跑通
python -m phantom_ai_feed.digest --use-stub

# 有 Gemini API key
export GEMINI_API_KEY=...
python -m phantom_ai_feed.digest

# 週末面試題(讀本週的 digest)
python -m phantom_ai_feed.interview_questions --use-stub

pytest tests/ -v
```

寫入位置:

```
~/.phantom-mesh/logs/phantom-ai-feed/YYYY-MM-DD.md
~/.phantom-mesh/logs/phantom-ai-feed/weekly-questions-YYYY-MM-DD.md
```

## Architecture (within phantom-mesh ecosystem)

phantom-ai-feed 是 **P1 跨平台連線 + P3 進化網** 的入口層:每天把外部世界的
AI 新進展寫進你自己的 FTS5 memory,讓 phantom 的 agent 可以回答「上週 RAG
最新進展是什麼?」。

```
14 RSS sources (含中文來源)
   ↓ phantom_ai_feed.fetch
{title, link, summary, source}[]
   ↓ phantom_ai_feed.summarize (Gemini Flash / stub)
Markdown digest
   ↓ phantom_ai_feed.digest
~/.phantom-mesh/logs/phantom-ai-feed/<date>.md   ←→  phantom event capture → FTS5
                                                              ↓
                                  phantom-companion ⑦ 讀作學習行為訊號
                                  phantom-mesh agent 回答可引用
```

Pillars served: **P1** (跨平台 — daemon-friendly,任何裝置都能跑同一份
config)、**P3** (進化網 — RSS → FTS5 → 面試題 → 回顧)。

## Target users (recruiter / co-builder angle)

- **Recruiters**: 中型 AI 新創 (Anthropic APAC、Cohere、Modal、Together、本地
  AI 顧問公司) 看重「能 ship 一個每天有人用的 internal tool」+「中文社群
  reach」。RSS / LLM provider 切換 / FTS5 整合是 AI infra 基本盤。
- **副業 angle**: Substack 中文 AI 工程師週報 (NT$ 99-199 / 月);Hahow
  課程「用 phantom 自動建你的 AI 知識庫 + 面試題」。
- **Co-builders**: 想自架英文圈 Daily.dev 替代品的非英文母語工程師(日韓越
  泰語直接 fork 換來源)。

## Roadmap & docs

- 狀態與規劃(唯一真實來源): **[`ROADMAP.md`](ROADMAP.md)**
- 文件導覽入口: [`docs/INDEX.md`](docs/INDEX.md)
- 詳細設計 spec: [`docs/03-phantom-ai-feed.md`](docs/03-phantom-ai-feed.md)
- 七專案總圖: [phantom-mesh planning tree](https://github.com/markl-a/phantom-mesh)

## Sibling scaffold (do not confuse)

`~/Documents/GitHub/hailmary/phantom-ai-feed/` 是更早的 cron-only RSS
heartbeat(launchd 已綁定,請勿移動)。本 repo 是它的 LLM-enabled 後繼者,
最終會接手 cron。

## License

Apache-2.0. © 2026 Mark Lai ([markl-a](https://github.com/markl-a)). See
[LICENSE](LICENSE).
