# ③ phantom-ai-feed

> **每日自動爬 AI 前沿 → LLM 摘要 → 入 phantom 知識庫 → 出面試題**
> 中文 AI 學習 daily feed,改裝自 My-AI-Learning-Notes(19 star)

## 一句話定位

「phantom-mesh 上的個人 AI 持續學習引擎 — arxiv / HN / r/LocalLLaMA / 名 blog 自動抓 + 摘要 + 進 FTS5 + 每週六出 5 題回測 + 對外發 newsletter。」

## 對齊 BIG-GOAL

- **P2 多模態理解**:multimodal capture(text + audio podcast 摘要)
- **P3 進化網**:用 Hermes 把「看過的內容」變成「會用的 skill」(spaced repetition)
- 對應 BIG-GOAL audience #1「既要 workforce 又要 daily coach」

## 競品分析

| 競品 | 強項 | phantom-ai-feed 差異 |
|---|---|---|
| **Daily.dev** | dev 文章聚合 | 中英文支援 + 私人知識庫,not cloud |
| **Feedly + AI Summarizer** | RSS + AI 摘要 | 整合 phantom FTS5,跨 session 可搜尋 |
| **Anki** | spaced repetition | 自動出題(用 LLM),不用手寫 card |
| **Readwise Reader** | 文章重點 highlight | 主動推送 + 面試導向題庫 |
| **Substack newsletter** | 內容平台 | 同時為訂閱者 + 發布者 |

**niche**:**第一個中文 AI 工程師導向 + 面試題自動生成 + on-prem RAG**。

## 核心功能

```
[每日 09:00 cron]
   ↓
RSS scraper (arxiv cs.AI/cs.CL + HN + r/LocalLLaMA + 10+ 名 blog + YouTube AI 頻道)
   ↓
phantom LLM(Gemini Flash 摘要 — 便宜,500 字內)
   ↓
進 phantom FTS5(可跨 session 搜尋,跟 phantom 其他內容打通)
   ↓
每週六 09:00:
   - 從本週新摘要選 5 個 topic
   - LLM 出題(根據面試的公司類型,例如 NVIDIA → 推論優化題)
   - 推到 phantom mobile app 通知
   ↓
答題 → 紀錄 → SM-2 spaced repetition algorithm → 下次該複習時自動推
   ↓
[每週日 18:00]
   - 寫成 newsletter 草稿(LLM 整理本週重點)
   - 發 Substack(公開版)
   - 留 highlights 給 brand-hub
```

## 招聘 / 副業 / 應用評分

| 維度 | 評分 | 對應 |
|---|---|---|
| **招聘** | ⭐⭐⭐ | 展示「持續關注前沿」+ RAG + Agent 整合;**間接** 命中所有 AI 公司 |
| **副業** | ⭐⭐⭐⭐ | Substack 訂閱 + 線上課程「中文 LLM 學習路徑」 |
| **個人應用** | ⭐⭐⭐⭐⭐ | 日常學習 + 求職準備雙打 |

## 應用情境

- **日常學習**:主要 — 訂多少都不怕,每天 5 分鐘看摘要
- **求職準備**:面試題部分 — 投履歷前自動出對應風格的題
- **提問記錄**(間接):變成私人題庫

## MVP scope

### Must have(M2 W8 — MVP)
- [ ] RSS scraper(20 個 source 預設,可加)
- [ ] phantom LLM 摘要 pipeline
- [ ] 摘要寫入 phantom FTS5(無新 DB)
- [ ] 週六出題 cron(用最近投的公司 type 出題)
- [ ] 答題介面(mobile app 或 web)
- [ ] 答題結果記錄 + SM-2 spaced repetition
- [ ] Substack 草稿自動生成(週日)

### Nice to have(M3+)
- [ ] YouTube AI 頻道音檔摘要(用 Whisper)
- [ ] Twitter / X AI 帳號自動追(API limits 大坑)
- [ ] 中文 source 加強(機器之心 / iThome / 量子位)
- [ ] 跟 phantom-companion 整合(讀 vs 沒讀 ratio 分析)

### NOT doing
- 完整 reader app(Readwise 已做)
- 社交 / 評論功能(local-first 違反)
- 全自動發 Substack(必須 human-in-the-loop)

## 改裝來源

**現有**:
- `github.com/markl-a/My-AI-Learning-Notes`(19 star,Jupyter 為主)
  - 已有:中文 AI/LLM 學習路徑 + 面試準備教材 + 2024-2025 前沿
  - 改裝方向:把靜態 notebook 變成 **active 抓取 + 摘要 pipeline**

**整合**:
- phantom-mesh FTS5(寫入用)
- phantom-mesh provider trait(Gemini Flash 摘要)
- phantom Hermes Curator(篩高品質摘要)

## 風險

- **資訊污染**:LLM 摘要可能 hallucinate,要加 source 引用 + spot check
- **Substack 自動發**:過度自動可能違反 Substack TOS,維持 human-in-the-loop
- **題目品質**:LLM 出題容易太簡單,需要人工 review 樣本 calibrate
- **scope creep**:容易變成「我做一個 better Feedly」,要守住「面試導向」這個 niche

## 變現路徑

| 路徑 | 細節 |
|---|---|
| Substack 訂閱 | 中文 AI 工程師日報訂閱制 |
| 線上課程 | 「中文 AI 工程師學習路徑」一次製作 |
| Sponsor 廣告 | newsletter 內植入(廣告/工具 affiliate) |
| lead funnel | newsletter 訂戶 → blog 流量 → 接案 lead |

## 為什麼放 M2 W8(中段)

- ① phantom-mesh FTS5 + provider trait 已 ready(M1 完成)
- 立刻可以開始累積摘要 data(累積越久 ⑦ companion 越準)
- 副業變現速度第二快(週發 newsletter,3 個月可看到訂戶)

---

*Sanitized public spec. Author: Mark Lai ([@markl-a](https://github.com/markl-a)).*
