# phantom-ai-feed

> 中文 AI 工程師日報 + 面試題自動生成器 + on-prem RAG-ready 知識庫。
> 每日抓取 AI 前沿 RSS → Gemini Flash 摘要 → phantom FTS5 → 週末 LLM 出題複習。

**一句話 niche**: 給中文 AI/ML 工程師的「每天 10 分鐘讀完 + 週末面試題自測 + 本機 RAG 可查」三合一管線。
延續並重定位 [markl-a/My-AI-Learning-Notes](https://github.com/markl-a/My-AI-Learning-Notes)（19 stars, Jupyter notebooks 系列）為 daemon-friendly 的自動化資訊流。

**Status:** alpha (2026-05-22). Tier 1 完成：RSS 抓取 + Gemini Flash 摘要（含 stub fallback）+ FTS5 寫入路徑 + 週末面試題生成 stub。Tier 2/3 待補（SM-2 spaced repetition、Substack draft 自動發布）。

## What's in Tier 1 (today)

| 模組 | 角色 | LOC | 狀態 |
|---|---|---|---|
| `phantom_ai_feed/fetch.py` | RSS/Atom → `{title,link,summary,source}` list | ~80 | done |
| `phantom_ai_feed/summarize.py` | Gemini Flash REST 客戶端 + stub fallback | ~120 | done |
| `phantom_ai_feed/digest.py` | 日報 orchestrator → Markdown + phantom FTS5 | ~100 | done |
| `phantom_ai_feed/interview_questions.py` | 週末出題 (Gemini or stub) | ~80 | done |

寫入位置（與 hailmary scaffold 共用，方便切換）：
```
~/.phantom-mesh/logs/phantom-ai-feed/YYYY-MM-DD.md
~/.phantom-mesh/logs/phantom-ai-feed/weekly-questions-YYYY-MM-DD.md
```

如果 `phantom` CLI 在 PATH 上，digest 會 best-effort 跑 `phantom event capture` 把摘要寫進 FTS5（失敗不會中斷主流程）。

## Quickstart

```bash
# 不需要 API key — 用 stub summarizer
python -m phantom_ai_feed.digest --use-stub

# 有 Gemini API key
export GEMINI_API_KEY=...
python -m phantom_ai_feed.digest

# 週末面試題（會讀本週的 digest 檔案）
python -m phantom_ai_feed.interview_questions --use-stub
```

## Tests

```bash
pytest tests/ -v
```

## Sibling scaffold (do not confuse)

`~/Documents/GitHub/hailmary/phantom-ai-feed/` 是更早的 cron-only RSS heartbeat（launchd 已綁定，請勿移動）。本 repo 是它的 LLM-enabled 後繼者，最終會接手 cron。

## Spec & plan

- 詳細設計: [`215jseeking/docs/projects/03-phantom-ai-feed.md`](../../Documents/215jseeking/docs/projects/03-phantom-ai-feed.md)
- 七專案總圖: [`215jseeking/phantom_mesh_7_projects_plan.md`](../../Documents/215jseeking/phantom_mesh_7_projects_plan.md)
- 上游 mesh: [phantom-mesh](https://github.com/markl-a/phantom-mesh)

## License

Apache-2.0. See [LICENSE](LICENSE).
