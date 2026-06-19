# OSS Landscape & Direction — phantom-ai-feed

> ARCHIVED 2026-06-19 — 內容已併入 docs/phantom-ai-feed.md;此為歷史版本。

> **範圍：** AI 新聞聚合／個人化資訊 feed／RSS→LLM 摘要／
> 知識 feed／間隔重複（SRS）學習工具。
> **目的：** 為一個 **單人、local-first、整合 phantom-mesh** 的專案，
> 奠定其 build-vs-wrap-vs-reference 決策的依據；此專案的利基是
> **owned-memory + SRS + 在精選來源清單之上的受治理個人摘要（governed personal digest）**
> —— 而非一個通用的 reader app。
>
> **快照：** 2026-06-19。star 數／授權條款在標註處皆經由 web fetch 驗證；
> 預期會有 drift —— **採用任何相依套件前請重新驗證。** 無法直接確認的主張會以
> **`[unverified]`** 標示。
>
> *本*專案的狀態 SSOT 仍為 [`ROADMAP.md`](../ROADMAP.md)。本文件是 roadmap 所依賴的
> *外部* 全局概覽（lay-of-the-land）。

---

## 1. 現況（phantom-ai-feed 目前的位置）

依據 `master` 上已合併的 commit 及 `phantom_ai_feed/` 中的模組所整理
（見 [`ROADMAP.md`](../ROADMAP.md)；測試套件 **103 passing**）。

**已交付 —— 這不是 greenfield 專案：**

- **端到端 pipeline**（`pipeline.py`）—— 一次 `python -m phantom_ai_feed.pipeline`
  即串接每日（digest → interview-questions `--register-srs`）與每週
  （+ weekly → newsletter），stop-on-first-error。所謂「daemon-friendly 的單一排程
  呼叫」在程式碼裡已經存在。
- **RSS/Atom 抓取**（`fetch.py`）—— 14 個 feed，含中文來源，具有上限的 retry/backoff、
  HTML 去標籤、offline 模式，純 stdlib（`urllib`/`xml.etree`/`tomllib`）。
- **摘要**（`summarize.py`）—— `phantom exec` → Gemini Flash REST → stdlib 抽取式
  stub fallback（degrade-don't-crash，不需金鑰）。
- **每日 + 每週 digest**（`digest.py`、`weekly.py`）—— 跨來源去重／分群
  （`dedup.py`）、可信度加權（`credibility.py`）、「Top picks」。
- **SM-2 間隔重複**（`srs.py`）—— 真正的 `srs answer`/`srs due` CLI；**每日
  pipeline 現在會重新浮現到期卡片**（`srs-due-<date>.md`）—— SRS 迴圈是*封閉的*，
  並非 write-only。
- **面試題產生器**（`interview_questions.py`）、**newsletter 草稿**
  （`newsletter.py`，human-in-the-loop）、**FTS5 capture**（`capture.py`）、
  **eval harness**（`eval.py`，約 20 題 gold set）、gated **live mesh round-trip** 測試、CI。

**剛加入作為種子內容：** [`docs/AI-SOURCES-CURATED.md`](AI-SOURCES-CURATED.md) —— 一份
約 198 筆、精選且跨地區的來源目錄（newsletters、blogs、YouTube、X、papers、
CN/JP/zh 來源、aggregators）。**這是槓桿最高但尚未動用的資產：** pipeline 目前
抓取一份 14-feed 的 `sources/feeds.toml`，而精選目錄的廣度約為其 10 倍。
**把精選目錄 → 真實 feed 接起來，是 CP 值最高的下一步。**

**誠實的缺口判讀：** *引擎*已經成熟；薄弱的部分是 (a) **實際接進來的來源廣度**
（精選清單尚未被消費）、(b) **真正的排程**（仍是手動／cron 待辦），以及
(c) 超越 best-effort capture 的 **更深 owned-memory／recall**。利基護城河
（owned-memory + SRS + governed digest）在*架構上*已經存在，但只被*部分*發揮。

---

## 2. Landscape

### 2.1 AI 新聞聚合器／digest（最接近的「競爭者」）

| 專案 | URL | 星數 | 語言 | 授權 | 成熟度 | 對我們利基的契合／落差 |
|---|---|---|---|---|---|---|
| **AI News**（smol.ai / swyx） | news.smol.ai | n/a（hosted service；`ainews-web` repo） | Py/web | proprietary-ish `[unverified]` | 生產級、builder 愛用 | **參考，別 clone。** 自動聚合 Discord/Twitter/Reddit + LLM 成為每日一期 —— 正是我們的*輸出形狀*，但屬雲端托管、英文、無 SRS、無 owned-memory。是*digest 品質*的最佳範本；在 local-first + zh + 學習迴圈上則方向相反。 |
| **Feedly AI**（AI Actions / Ask AI / Summarization） | feedly.com | proprietary SaaS | — | commercial | 成熟、付費（Pro+/Business） | **對我們而言是 anti-pattern。** 純雲端、訂閱制、資料會離開你的機器。它印證了*市場*（LLM 摘要 + 自動 newsletter 已是 table-stakes）以及*我們切入的缺口*（無 local-first、無 zh-engineer 聚焦、無 SRS）。 |
| **Kagi News** | kagi.com | proprietary | — | commercial | 新（2025–26） | **參考。** 把 RSS 拉進 LLM context 再摘要成文章 —— 與我們 digest 的核心迴圈相同。雲端、付費、面向一般受眾。印證「RSS→LLM digest」是一個真實的產品品類。 |
| AI-News-Aggregator（AKAlSS） | github.com/AKAlSS/AI-News-Aggregator | small `[unverified]` | Python | `[unverified]` | Hobby/demo | RSS→每日 digest→Notion。骨架與我們相同，但與 Notion 綁定、無 SRS、無本地儲存。沒有可採用之處；它印證這個模式很常見（所以我們的護城河必須是*學習迴圈*，而非聚合器本身）。 |

### 2.2 RSS readers + LLM summarizers（可能 wrap/reference）

| 專案 | URL | 星數 | 語言 | 授權 | 成熟度 | 契合／落差 |
|---|---|---|---|---|---|---|
| **FreshRSS** | github.com/FreshRSS/FreshRSS | **15.3k** | PHP | **AGPL-3.0** | 非常成熟、自架 | 自架聚合器的主流；具備一個「Feed Digest」LLM 擴充。**太重，無法嵌入**（PHP server、多使用者 web app）。對純 stdlib 的 Python pipeline 而言是錯誤的 substrate，但作為 **OPML/來源管理的參考** 以及供人類使用的 fallback reader 都很出色。 |
| **Precis**（leozqin） | github.com/leozqin/precis | **94** | Python | **MIT** | 活躍、利基 | 可擴充的自架 RSS reader → LLM 摘要 → 通知（Slack/Matrix）。**架構上最接近的近親**：Python、LLM 摘要、notification-first。我們已自備 fetch+summarize，因此 **參考其 notification/handler 外掛設計** 即可，不要相依它。 |
| **RLLM**（DanielZhangyc） | github.com/DanielZhangyc/RLLM | **96** | Swift | **MIT** | 活躍 | iOS 上 LLM 驅動的 RSS reader。平台不對（Swift/iOS），但若日後出現 phantom-mobile reader 介面，可作為 **UX 參考**。 |
| **FeedSummarizer**（GuizzyQC） | github.com/GuizzyQC/FeedSummarizer | small `[unverified]` | Python | `[unverified]` | Hobby CLI | CLI：RSS→OpenAI-compatible LLM 摘要。我們已做得更好（可切換 provider + stub fallback）。不採用。 |
| **rss-llm**（apiad） | github.com/apiad/rss-llm | small `[unverified]` | Python | `[unverified]` | Hobby | 極簡的 LLM RSS summarizer。同上 —— 印證此模式之普遍。 |
| **RSS-to-Telegram-Bot**（Rongronggg9） | github.com/Rongronggg9/RSS-to-Telegram-Bot | mid `[unverified]` | Python | `[unverified]`（尋找維護者中） | 偏成熟、轉手過渡中 | **遞送（delivery）參考。** 若我們想要 push 遞送（Telegram），這是經驗證的模式 —— 但 phantom-mesh 已具備 phone notify/inbox，所以 **優先用 mesh channel**，而非新增一個 bot 相依。 |
| **RSSHub** | github.com/DIYgod/RSSHub | very high `[unverified]` | TS | MIT `[unverified]` | 非常成熟 | 把～任何東西轉成 RSS。**參考／可選的上游**：若某個精選來源沒有原生 feed，RSSHub route 可以合成一個。別自己 host 它；把它當作 feed-less 來源的逃生口來引用。 |

### 2.3 知識 feed／read-it-later／PKM（「不要重造」區）

| 專案 | URL | 模型 | 授權 | 契合／落差 |
|---|---|---|---|---|
| **Readwise Reader** | readwise.io/read | proprietary SaaS | commercial | read-it-later + **highlights + SRS 重新浮現** 的黃金標準。**這正是 over-build 陷阱**：絕不要重造一個 reader。他們的 SRS-over-highlights 概念上就是我們 SRS-over-questions 在做的事 —— 我們的差異化在於 **local-first + zh + 受治理 pipeline**，而非一個 reader app。ROADMAP 已言明「完整 reader app —— Readwise 已經做了這件事。」正確。 |
| **Obsidian + Readwise plugin** | github.com/readwiseio/obsidian-readwise | plugin（MIT-ish `[unverified]`） | — | PKM 落地點。我們的 digest 是放在 `~/.phantom-mesh/logs/...` 的 markdown —— **Obsidian 已經可以索引該資料夾**。整合就是「把 Obsidian 指向輸出目錄」，而非一項開發。僅供參考。 |

### 2.4 間隔重複引擎（驗證我們的 SM-2；候選升級）

| 專案 | URL | 星數 | 語言 | 授權 | 契合／落差 |
|---|---|---|---|---|---|
| **FSRS** / fsrs4anki | github.com/open-spaced-repetition/fsrs4anki | **4k+** | Jupyter/Py | **MIT** | 現代 ML 排程器；在等同的記憶留存下 **比 SM-2 少 20–30% 的複習量**（以 500M+ 筆 Anki review 為基準測試）；現已是 Anki 的預設。**是替換我們手寫 SM-2 的強力候選**（`srs.py` 中）—— 已有純 Python 的 `free-spaced-repetition-scheduler` 套件。**稍後再採用**，現在不採：SM-2 在 alpha 階段已足夠，而 FSRS 需要一段複習歷史才能展現優勢。 |
| **free-spaced-repetition-scheduler** | github.com/open-spaced-repetition/free-spaced-repetition-scheduler | （屬該 org 一部分） | Python | **MIT** | FSRS 乾淨的函式庫形式 —— 若／當我們升級 `srs.py` 時實際會引入的相依。與我們的 Apache-2.0 在授權上相容。 |
| **Anki** | apps.ankiweb.net | — | Py/Rust | AGPL-3.0 | 既有霸主。**不要重造。** 我們的 SRS 是*針對 digest 衍生的問題*，而非通用的 flashcard app —— 利基不同。僅供演算法正確性的參考。 |

---

## 3. 建議方向

**一句話論點：** *別造 reader、別造 aggregator framework、也別造 flashcard app ——
那些都已存在且十分優秀。**要造的是那條薄的、受治理的、local-first 迴圈，把
精選 AI 來源清單 → LLM digest → owned-memory → SRS 串起來**，這是沒有人為
自己機器上的 zh-language 工程師所做的事。*

| 決策 | 內容 | 原因 |
|---|---|---|
| **BUILD（便宜、高價值）** | **把 `docs/AI-SOURCES-CURATED.md` → 真實 feed 接起來。** 把精選目錄解析成 `sources/feeds.toml` 條目（有原生 RSS 就用；沒有就走 RSSHub route 或略過）。 | 槓桿最高的單一動作。引擎已存在，只是餵食不足。把一份靜態文件變成廣度約 10× 的活躍 digest。純 stdlib + 一個 parser。 |
| **BUILD（護城河）** | **深化 owned-memory + SRS。** 讓 digest capture 寫入 FTS5 成為一等公民（而非 best-effort），並讓 recall 與 SRS-due 都讀同一個 store。 | 這是 apex-② owned-memory 的差異化，也是我們真正的利基。沒有競爭者在本地把個人 digest 與 owned-memory + SRS 配對在一起。 |
| **WRAP / REUSE** | **phantom-mesh 遞送 + 治理。** 對 digest 遞送與任何「publish」步驟，使用 mesh phone notify/inbox + governor double-gate —— 而非新增一個 Telegram bot。 | 上游已建好；reuse 勝過 rebuild。在 publish 上維持 human-in-the-loop（ROADMAP 規則）。 |
| **REFERENCE（別相依）** | smol.ai AI News（digest 品質）、Precis（handler/notification 外掛設計）、Kagi News（RSS→LLM 框架觀念）、RSSHub（feed-less 來源的逃生口）。 | 偷其*形狀*，別偷其*程式碼*。讓相依表面維持趨近於零（當前賣點：純 stdlib）。 |
| **ADOPT LATER** | **FSRS**（`free-spaced-repetition-scheduler`，MIT）以替換手寫 SM-2。 | 真實的效率提升，但只在累積出複習歷史之後才有意義；現在太早。是候選，不是承諾。 |
| **DON'T BUILD** | reader app（Readwise）、flashcard app（Anki）、多使用者 web 聚合器（FreshRSS）、hosted SaaS（Feedly/Kagi）。 | 全都已存在、資源都更充足。重造任何一個都是 over-build 陷阱，並放棄 local-first/單人聚焦。 |

### 分階段路徑（依據 ROADMAP「Planned-next」）

- **Phase 1 —— 餵食引擎（現在，無外部相依）：** 精選目錄 → `feeds.toml`
  橋接；驗證可達性；`--strict` 維持核心集合的權威性。*高價值、便宜、
  不需 operator 決策。*
- **Phase 2 —— 深化護城河（接下來）：** 一等公民的 FTS5 capture + 統一的 recall/SRS store；
  供 phantom-companion 使用的 read-vs-unread 訊號掛鉤（ROADMAP item）。*護城河工作；需要一些設計。*
- **Phase 3 —— 遞送 + 排程（需 operator／外部）：** 在單一 pipeline 進入點之上接上
  真正的 cron/launchd；mesh phone 遞送；*可選的* FSRS 替換；*可選的*
  multimodal（YouTube/Whisper）與 Substack publish hook —— **全部 human-in-the-loop、
  位於 governor 之後。** *需要外部 API／operator 決策；最後做。*

---

## 4. 誠實的 over-build 警告

- **reader 陷阱。** 想造一個漂亮閱讀 UI 的衝動很強，但是錯的。Readwise/
  FreshRSS 在這場仗會贏。我們的輸出是資料夾裡的 markdown；讓 Obsidian／任何編輯器去讀它。
- **aggregator-framework 陷阱。** 別把 `fetch.py` 一般化成外掛框架
  （Precis/RSSHub 的領域）。14→約 198 個精選 feed 透過一份扁平 TOML 已足夠；YAGNI。
- **「來源越多越好」陷阱。** 精選文件本身就警告每日的重疊
  （TLDR / Rundown / Neuron 涵蓋同一批新聞）。**去重 + 可信度排名已經存在
  —— 倚靠它們**；在沒有排名的情況下加入原始廣度只會加入雜訊。
- **FSRS-too-early 陷阱。** FSRS 需要複習歷史；在還沒有資料可擬合之前就替換掉
  一個能運作的 SM-2，是只有 churn、沒有使用者可見收益。
- **auto-publish 陷阱。** 全自動的 Substack 發佈違反 human-in-the-
  loop 規則（ROADMAP「Out of scope」）。把 auth + send 維持手動。
- **dependency-creep 陷阱。** 目前的純 stdlib 安裝（「no runtime packages」）是一個
  貨真價實的賣點。上述每一項 wrap/adopt（FSRS、RSSHub、Telegram）**都會增加表面** ——
  每一項在落地前都必須通過「這是否勝過我們已有的 mesh primitive？」這道門檻。

---

### Sources

- [smol.ai / AI News](https://news.smol.ai/) · [smol.ai org](https://github.com/smol-ai)
- [Feedly AI & Summarization](https://feedly.com/new-features/posts/feedly-ai-and-summarization) · [Feedly AI newsletters](https://feedly.com/new-features/posts/ai-powered-newsletters-faster-creation-greater-impact)
- [Kagi News (HN)](https://news.ycombinator.com/item?id=45426490)
- [FreshRSS](https://github.com/FreshRSS/FreshRSS) · [FreshRSS Extensions](https://github.com/FreshRSS/Extensions)
- [Precis (leozqin)](https://github.com/leozqin/precis) · [RLLM](https://github.com/DanielZhangyc/RLLM) · [FeedSummarizer](https://github.com/GuizzyQC/FeedSummarizer) · [rss-llm](https://github.com/apiad/rss-llm)
- [RSS-to-Telegram-Bot](https://github.com/Rongronggg9/RSS-to-Telegram-Bot) · [RSSHub guide](https://docs.rsshub.app/guide/)
- [Readwise Reader](https://readwise.io/read) · [obsidian-readwise](https://github.com/readwiseio/obsidian-readwise)
- [FSRS / fsrs4anki](https://github.com/open-spaced-repetition/fsrs4anki) · [free-spaced-repetition-scheduler](https://github.com/open-spaced-repetition/free-spaced-repetition-scheduler) · [awesome-fsrs](https://github.com/open-spaced-repetition/awesome-fsrs)
