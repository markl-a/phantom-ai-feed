# ② Entry-level dedup — design draft

> **狀態:設計草稿(untracked)。** 建在 PR #1 的 `accumulate.py` 之上,等 #1 merge
> 後實作。對應主文件 Phase 2.5 的「整併:去重」與自我審查延後項
> 「entry 層級 idempotency」。

## 問題

條件式 GET 只在**來源**層級去重:整個未變動的源(HTTP 304)會被跳過。但**有更新
的源(HTTP 200)裡**,top-N 條目會 day-to-day 重疊:

```
週一 feed top-3 = [A, B, C]            → capture A,B,C
週二 feed 變了,top-3 = [D, A, B]      → 200(changed)→ capture D,A,B
                                          ↑ A、B 已存過 → FTS5(append-only)出現重複
```

`accumulate` 目前對「有變的源」會 capture 它**全部** top-N,所以重疊條目會被重複寫進
FTS5。PR #1 加的 validator-rollback(capture 失敗 → 回滾、下次重抓)也會讓**已成功的
條目**在重抓時再被 capture 一次。

## 範圍決定(重要)

**per-feed 去重,不做 global 去重。** 只解決「同一個源內 day-to-day 重疊」這個真問題。
**刻意保留**跨來源重複(同一則新聞同時出現在 arXiv + HN):那是 credibility 的
corroboration 訊號(distinct sources),且不同 provenance 進知識庫是有價值的,不該被
殺掉。`dedup.py` 的 cross-source 聚合是「單次 run 內排名前的整併」,與這裡「跨 run 的
持久 idempotency」是兩件事,互不取代。

## Entry 身分(重用既有)

`entry_key(entry)` → 穩定字串,優先序:

1. **`dedup.normalize_url(entry["link"])`** —— 直接重用(剝 scheme/www/trailing-slash/
   追蹤參數,host 小寫、query 排序)。RSS item 的 link 是最穩定識別子。
2. link 為空時 fallback:`"t:" + " ".join(sorted(dedup._title_tokens(title)))`,再不行
   用 `source`。
3. title 也為空 → 回 `""` ⇒ **無穩定 key 就不去重**(照常 capture;極少數)。

把 `entry_key` 放進 `dedup.py`(它已經是 entry-identity 的家,正確 altitude)。

## 持久 seen-store

新檔:`~/.phantom-mesh/logs/phantom-ai-feed/seen-entries.json`(validator cache 的姊妹)。

```json
{
  "<feed-url>": ["key-newest", "...", "key-oldest-kept"]
}
```

- **per-feed**(key 用 feed 的 url;與 validator cache 同鍵,日後可考慮合併成單一
  per-feed state 檔,但先各自獨立,降低 PR 體積)。
- **有界**:每源只留最近 `MAX_SEEN_PER_FEED`(預設 200)個 key。源只會浮出最近項,
  條目滾出視窗夠久就不會再回來,所以固定上限即可,**天然防無限長大**。lookup 用
  set 成員判定,trim 保留最後 N 個。

reuse:把 `fetch.load_feed_cache`/`save_feed_cache` 抽成通用的 `_load_json(path)`/
`_save_json(path, obj)`,validator cache 與 seen-store 共用(避免第二份 JSON I/O 複製)。

## 接進 accumulate.run

對每個 **changed(200)** 的源:

```
seen = seen_store.get(feed_url) as set
new_entries = [e for e in payload if entry_key(e) not in seen]      # 過濾已見
out.skipped_duplicate += len(payload) - len(new_entries)
for e in new_entries:
    res = capture_entry(e, dry_run)
    if res.status == "ok":
        captured += 1
        seen.add(entry_key(e))          # 只有成功落地才記為已見
    elif res.status == "dry-run":
        pass
    else:
        capture_failed += 1; feed_failed += 1   # 失敗 → 不記 seen → 下次重試
trim seen to MAX_SEEN_PER_FEED; write back into seen_store[feed_url]
```

落地時:`if not dry_run: save seen-store`(與 validator cache 一致,dry-run 零副作用)。

## 與 validator-rollback 的協作(變更清)

兩者互補,合起來剛好修掉自我審查標的「重抓會重存已成功的 2 條」:

- capture 失敗 → validator-rollback 強制該源下次**重抓**(200);
- seen-store 確保重抓時**只重試失敗那條**,已成功的 2 條因在 seen 內被跳過。
- 失敗條目**不入 seen** → 保證會被重試;成功才入 seen → 保證不重複。

## 回報

`AccumulateResult` 加 `skipped_duplicate` 計數;CLI summary 印出
「captured N, skipped M duplicates」。**不靜默丟棄**(呼應審查「no silent caps」)。

## 要動的程式碼(實作時)

| 檔 | 變更 |
|---|---|
| `dedup.py` | 新增 `entry_key(entry) -> str`(重用 `normalize_url`/`_title_tokens`) |
| `fetch.py` | 抽 `_load_json`/`_save_json`;`load/save_feed_cache` 改用之(行為不變) |
| `accumulate.py` | 載入 seen-store → 過濾 new → 只 capture new → 成功才記 seen → trim → 落地(dry-run 不寫);`+skipped_duplicate` |
| `seen-store helpers` | `load_seen(path)`/`save_seen(path, store)`(或直接用通用 `_load_json`) |

## TDD 測試(實作時先寫,RED→GREEN)

1. `entry_key` — link 相同 → key 相同;link 帶 utm/www/trailing-slash 變體 → 同 key;
   無 link → title-token fallback;全空 → `""`。
2. accumulate 跳過 seen 內條目 → `captured==0, skipped_duplicate==1`。
3. accumulate capture 新條目 → 記入 seen-store 且持久化。
4. capture 失敗 → key **不**入 seen(下次重試);配合 validator-rollback 的整合測試:
   第一次 1 成功/1 失敗 → 第二次只重存失敗那條(成功那條被跳過)。
5. dry-run 不寫 seen-store。
6. seen-store 超過 `MAX_SEEN_PER_FEED` → 修剪到上限。
7. 跨來源同 URL(兩個不同 feed)→ **兩邊都 capture**(驗證 per-feed 範圍、不誤殺
   corroboration)。

## Edge cases(明列)

- 無 link 且無 title → 不去重(照常 capture)。
- 同源同一 run 內若已有重複(理論上 fetch top-N 不該)→ set 自然吸收。
- seen-store 壞檔 → 比照 validator cache 回 `{}`(best-effort,頂多重存一次,不崩)。
- 與未來「validator cache 與 seen-store 合併成單一 per-feed state」保留空間,但本階段
  不做(YAGNI / 降 PR 體積)。

## 不做

- global 跨源去重(會殺掉 corroboration 訊號)。
- 用 `phantom recall` 查 FTS5 來判重(慢、耦合 CLI、全文搜尋非精確鍵)。
- 內容雜湊比對(同 URL 內容微調算同一條;URL 識別已足夠且穩定)。
