# 資料源擴充 — 設計草稿(全平台攝取)

> **狀態:設計草稿(untracked)。** 對應主文件 Phase 1「餵飽引擎」與 Phase 3「多模態」。
> 2026-06 由並行研究 agent 實際 web fetch + GitHub API 驗證;**接入前仍須逐一 re-verify
> URL/repo**(策展檔已警告會漂移)。本檔是「怎麼把更多平台接進來」的方法論與架構,不是
> feeds.toml 本身。

## 核心架構原則(一句話)

**純 stdlib 的 RSS/Atom 核心保持乾淨;每個非原生-RSS 平台都是一個「邊界 adapter」——它
產出 RSS/Atom(或正規化條目),核心照樣只吃 feed。** 依賴與脆弱性一律隔離在核心外、全標
`optional`,壞了不影響核心攝取。這延續本專案「薄、受治理、RSSHub 當逃生口、別把依賴拉進
核心」的脊椎,並讓「純 stdlib 免安裝」這個賣點對核心成立。

```
                      ┌─────────────── 純 stdlib 核心(不變) ───────────────┐
原生 feed ───────────►│ fetch_all → summarize → digest / accumulate → FTS5 │
(YouTube/Podcast/PTT/ │                                                     │
 blog/arxiv/HN/…)     └──────────────────────▲──────────────────────────────┘
                                             │ 產出 RSS/Atom 或正規化條目
        邊界 adapter(隔離依賴、可選、可替換)│
        ┌───────────────┬───────────────┬────┴────────┬─────────────────┐
        Threads API     X: RSSHub+cookie  IG: instaloader  WeChat: wewe-rss /
        (官方 OAuth)    (自架)            (拋棄帳號)        Wechat2RSS relay
```

## 平台判定總表(2026 驗證)

| 平台 | 判定 | 最佳方式 | 接法 |
|---|---|---|---|
| YouTube | 🟢 | 原生頻道 Atom `youtube.com/feeds/videos.xml?channel_id=UC...`(免金鑰,實測 200) | 直接進 feeds.toml |
| Podcast/Spotify | 🟢 | iTunes lookup API 解析 `feedUrl`(免 auth);podcast 本質即 RSS | 直接進 feeds.toml |
| PTT | 🟢 | 原生 Atom `ptt.cc/atom/<Board>.xml`(實測 200,**繞過 over18 cookie**) | 直接進 feeds.toml |
| 一般 blog/網站 | 🟢 | stdlib feed 探測(`<link rel=alternate>` + 常見路徑 + 平台慣例) | 探測後進 feeds.toml |
| Threads | 🟢 | 官方 Threads API `keyword_search`(免費 OAuth、讀公開貼文) | 薄 adapter |
| X/Twitter | 🟡 | 自架 RSSHub + 自己的 X cookie → RSS(官方 API 2026/2 改 pay-per-use) | adapter,optional |
| Instagram | 🟡 | instaloader(MIT,維護中)+ 拋棄帳號 + 限流 → 轉 Atom | adapter,optional |
| WeChat 公眾號 | 🔴→🟡 | 外部 relay:wewe-rss(archived 但可用,需 Docker+微信读书)或 Wechat2RSS(活躍) | relay 產 RSS,optional |
| Facebook | 🔴 | 公開內容無免費路徑(需商業驗證);Graph API 僅限自有粉專 | 跳過 |

---

## Tier 1 — 三個純 stdlib 解析器(現在做,零新依賴)

這三個小工具把 🟢 平台接進現有引擎。全部 `urllib` + `xml.etree` + `json` + `html.parser`,
**無新 runtime 依賴**。設計成「離線可單元測試」(網路層 patch 掉),與既有 `fetch.py` 同風格。

### 1A. YouTube @handle → channel_id 解析器

- **為何需要**:策展檔多半記 `@handle` 或頻道 URL;原生 feed 需要 `UC...` channel_id。
- **方法(實測)**:GET `https://www.youtube.com/@<handle>`,從 HTML 取
  `"externalId":"(UC[\w-]+)"`,fallback 取 `<link rel="canonical" href=".../channel/UC...">`。
- **一次性 + 快取**:handle 幾乎不變;解析結果寫進一個 `youtube-handles.json`(slug→UCID),
  之後 feeds.toml 直接用 channel feed URL,不再爬頁(爬 HTML 是唯一脆弱點,快取後只影響
  「新加頻道」)。
- **產出**:`https://www.youtube.com/feeds/videos.xml?channel_id=<UCID>` 加進 feeds.toml
  (`category="youtube"`)。引擎已支援 Atom,直接可吃。
- **小引擎強化(可選)**:YouTube Atom 用 `media:description` 而非 `atom:summary`,目前
  parser 會讓 YT 條目摘要偏空(標題+連結沒問題)。要更豐富摘要,在 `fetch._parse_entries`
  的 Atom 分支加一段 `media:` namespace 讀取。非必要、可晚做。

### 1B. Podcast 解析器(iTunes lookup)

- **方法(實測免 auth)**:`https://itunes.apple.com/lookup?id=<appleID>&entity=podcast` 或
  `/search?term=<name>&entity=podcast` → JSON 內 `feedUrl` 即節目真實 RSS。
- **為何不用 Spotify**:Spotify 自家 API 要 OAuth;但不需要它——幾乎每個節目都在 Apple
  目錄,iTunes lookup 直接給出真實 feed。
- **別硬編 URL**:每次以 iTunes lookup 解析,survive 主機遷移(研究實例:Practical AI 的
  changelog.com URL 已 301 到 Transistor)。
- **產出**:解析到的 `feedUrl` 進 feeds.toml(`category="podcast"`)。podcast = 標準 RSS,
  引擎直接吃。逐字稿屬 Tier 4。
- **驗證過有公開 RSS 的 AI podcast**:Latent Space、Lex Fridman、Dwarkesh、Practical AI、
  TWIML、The Gradient(主流 AI podcast 無 Spotify-exclusive 問題)。

### 1C. 一般網站 feed 自動探測器

- **探測順序**:
  1. 解析 `<head>` 的 `<link rel="alternate" type="application/rss+xml|atom+xml|feed+json">`,
     相對 href 以頁面 URL `urljoin`。WordPress/Ghost/Hugo/多數 CMS 一發命中。
  2. 無 `<link>` → 試常見路徑:`/feed` `/rss` `/rss.xml` `/atom.xml` `/feed.xml`
     `/index.xml` `/feeds/posts/default`(Blogger) `/?feed=rss2`(WP)。
  3. 平台慣例:Substack=`<name>.substack.com/feed`(全文,極穩);Ghost=`/rss/`;
     Hugo/Jekyll/Zola=`/index.xml`;Medium=`medium.com/feed/@user`(截斷);
     Reddit=任何 URL 加 `.rss`;YouTube=見 1A。
  4. **驗證候選**:GET 後確認 body 以 `<?xml`/`<rss`/`<feed` 開頭,或為 JSON Feed。
- **實作**:`urllib` + `html.parser`(`HTMLParser` 子類抓 `link` 標籤),純 stdlib。
- **產出**:命中的 feed 進 feeds.toml(原 `category`)。
- **覆蓋**:~80% 沒明示 RSS 的 blog;剩下交給 Tier 3 的 RSSHub。

### 1D. PTT(無需解析器,直接加)

- **方法(實測)**:`https://www.ptt.cc/atom/<Board>.xml` 回原生 Atom,**over18 板的 atom
  端點不需 cookie**(Gossiping 實測有/無 cookie 皆回同樣有效 XML)。板名**大小寫敏感**。
- **相關板**:`Tech_Job`、`Soft_Job`、`DataScience`(無 `MachineLearning` 板;`Gossiping`
  看趨勢)。
- **產出**:直接寫進 feeds.toml(`category="ptt"`),零基礎設施、零解析器。
- **全文**:atom 多為標題/metadata;要全文再對 entry link 做 `urllib` GET(此時 HTML 才需
  `Cookie: over18=1`)——屬可選加強。
- **工具(多半用不到)**:`PyPtt`(LGPL,維護中)若要登入/深取才用。**RSSHub 無 PTT route**。

---

## Tier 2 — Threads(免費官方 adapter)

- **唯一乾淨的 Meta 路徑**:官方 Threads API `keyword_search`(OAuth 2.0,免費)。申請
  `threads_keyword_search` 權限後可讀**他人公開貼文**;限額 ~2200 query/滾動 24h;token
  短效(1h)/長效(60d)。caveat:結果 `owner` 欄被移除;敏感詞回空。
- **adapter**:小 OAuth 客戶端 → 把貼文正規化成引擎吃的 entry dict({title,link,
  summary_excerpt,source,category="threads"})。需 `requests`/httpx?可用 stdlib `urllib`
  打 OAuth + REST,維持核心無依賴。隔離成獨立模組,核心不 import。

## Tier 3 — 自架 / 脆弱 / 全標 optional

每個都在「邊界 adapter」層,產出 RSS/正規化條目,核心照吃;全標 `optional=true`,壞了核心
不受影響。每項落地前過「這真的贏過 mesh 既有原語嗎?」閘。

| 平台 | 方法 | repo / 狀態(2026-06 驗證) | 維護負擔 |
|---|---|---|---|
| X/Twitter | 自架 RSSHub + `TWITTER_COOKIE`(自己的 auth_token/ct0)→ 原生 RSS | `DIYgod/RSSHub` AGPL,44.8k★,活躍 | cookie 會被風控,需輪替 |
| Instagram | instaloader + 拋棄帳號 + 限流 → 轉 Atom | `instaloader/instaloader` MIT,12.6k★,活躍(2026-04) | 限流敏感、需 session |
| WeChat | relay:wewe-rss(自架,需微信读书帳號)或 Wechat2RSS feed | wewe-rss MIT **已 archived 2026-05**;Wechat2RSS 活躍但 self-host 付費/核心未全開源 | relay 隨 WeChat 改動會壞 |

- **snscrape 已死(2023)**,別建在它上面。Nitter 程式活但公開實例生態幾乎死、且多未開 RSS。
- **WeChat 自己刻(VM/Android + Appium)**:無維護良好的 OSS,DIY 高成本脆弱,**不值得**;
  wewe-rss/Wechat2RSS 本身就是「驅動 WeChat 客戶端」的產品化版本。真要做,當獨立、最後、
  phantom-mesh computer-use/android 能力可重用的專案,而非現在。

## Tier 4 — 逐字稿理解層(重,最後,interface 隔離)

- **YouTube 字幕**:`youtube-transcript-api`(MIT,維護中)為主 + `yt-dlp`(Unlicense)
  fallback。**最脆弱一環**:未公開端點、會封 datacenter IP(住宅 IP 較穩),預期每幾個月
  壞、要升級。
- **Podcast 轉錄**:`faster-whisper`(MIT)或 `whisper.cpp`(MIT),全本機。**唯一不可免的
  重依賴**;音檔經 RSS `<enclosure>` URL 下載(stdlib)。
- **原則**:全部藏在 interface 後,壞了**絕不**拖垮核心 feed 攝取。先接 feed(metadata 即
  有用),逐字稿後補。

## 跳過

- **Facebook 公開內容**(需商業驗證;Graph API 僅自有粉專)。
- **global 跨源去重**、**用 recall 查重**(見 entry-dedup 草稿)。

---

## 依賴隔離總則(守「核心純 stdlib」)

| 層 | 依賴 | 在哪 |
|---|---|---|
| 核心攝取/解析/探測/下載 | **純 stdlib** | `fetch.py` + 三個 Tier 1 解析器 |
| Threads adapter | stdlib(urllib OAuth)或 httpx | 獨立模組,核心不 import |
| X/IG/WeChat | RSSHub(Docker)/ instaloader / relay | **外部服務或獨立 adapter**,產 RSS |
| 逐字稿 | youtube-transcript-api / yt-dlp / whisper | 獨立模組,interface 後 |

核心永遠只看見 RSS/Atom 或正規化 entry dict;任何 adapter 可獨立壞掉、可替換。

## 要動的程式碼(實作時)

| 檔 | 變更 |
|---|---|
| `sources/youtube.py`(新) | `resolve_channel_id(handle) -> UCID`(爬頁+regex);handle 快取讀寫 |
| `sources/podcast.py`(新) | `resolve_feed(apple_id\|name) -> feedUrl`(iTunes lookup JSON) |
| `sources/discover.py`(新) | `discover_feeds(url) -> [feed_url]`(html.parser + 路徑探測 + 驗證) |
| `fetch.py`(可選) | Atom 分支加 `media:description` 讀取(豐富 YouTube 摘要) |
| `feeds.toml` | 新增 `category` = youtube/podcast/ptt 的條目(由上述工具產出後人工過目) |
| adapters(後續) | `adapters/threads.py`、`adapters/rsshub.py`、`adapters/wechat.py`(全 optional) |

## TDD 測試(實作時先寫,RED→GREEN)

1. `resolve_channel_id`:給含 `externalId` 的假 HTML → 回 UCID;只有 canonical link → 回
   UCID;都沒有 → 回 None。快取命中不再爬頁。
2. `resolve_feed`:假 iTunes JSON → 回 `feedUrl`;無結果 → None;name search 路徑。
3. `discover_feeds`:`<link rel=alternate>` 命中;無 link → 路徑探測;候選 GET 驗證
   `<?xml`/`<rss`/`<feed`/JSON Feed;全空 → []。
4. PTT:atom URL 條目解析(沿用既有 Atom 測試);over18 板 atom 不需 cookie 的整合測試。
5. 每個解析器**離線可測**(網路層 monkeypatch),不開 socket。

## 誠實 caveats

- YouTube @handle 爬頁、WeChat relay、X cookie、字幕端點皆會漂移——**接入前 re-verify、
  全標 optional、用 reachability 檢查 + `--strict` 守核心**。
- 「來源變多 ≠ 變好」:靠既有 dedup + credibility 排序壓雜訊,別硬加廣度(主文件已警告)。
- 本擴充建在 PR #1 的併發 `fetch_all`(撐得住更多源)之上;先讓 PR #1 落地再大量加源。
