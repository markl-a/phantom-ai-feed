# Synthetic Knowledge Loop Contract

The synthetic knowledge `demo-loop` command,
`python -m phantom_ai_feed.demo_loop`, is the P2 public alpha artifact loop for
`phantom-ai-feed`. It proves the local knowledge-intake path without live source
fetching, private reading history, credentials, cloud LLM calls, or a running
phantom daemon.

## Command

```powershell
python -m phantom_ai_feed.demo_loop --out <bundle> --date 2026-06-26 --query RAG
```

The command prints `<bundle>\manifest.json`.

## Bundle Layout

```text
<bundle>/
  manifest.json
  artifacts/
    source-items.jsonl
    digest.md
    aifeed.db
    recall-results.json
    review-cards.json
    srs.jsonl
    srs-due-YYYY-MM-DD.md
    summary.md
```

## Manifest Schema

`manifest.json` is stable JSON with sorted keys and schema version `1`.

Required top-level fields:

- `schema_version`: currently `1`.
- `mode`: `synthetic_knowledge_intake_loop`.
- `date`: deterministic fixture date.
- `query`: recall query used for the bundle.
- `data_policy`: `synthetic_only`.
- `private_data_included`: always `false`.
- `external_network`: always `false`.
- `llm_provider`: `stub_or_disabled`.
- `counts`: source item count, captured entry count, recall hits, review cards,
  and due cards.
- `artifacts`: bundle-relative paths for `source_items`, `digest`, `fts_db`,
  `recall_results`, `review_cards`, `srs_store`, `srs_due`, and `summary`.

## Artifact Contract

- `source-items.jsonl`: synthetic feed items before capture.
- `digest.md`: deterministic digest rendered from the synthetic feed items.
- `aifeed.db`: local SQLite FTS5 store containing captured synthetic entries.
- `recall-results.json`: deterministic recall result for the requested query.
- `review-cards.json`: generated review questions derived from source items.
- `srs.jsonl`: SM-2-style SRS card store.
- `srs-due-YYYY-MM-DD.md`: due-card review report for the fixture date.
- `summary.md`: human-readable bundle summary.

SQLite database bytes are not treated as the byte-stability artifact. The stable
public contract is the manifest, JSONL, JSON, and Markdown outputs plus the fact
that `aifeed.db` can answer the documented recall query.

Re-running the demo loop against the same bundle directory resets only the
bundle-owned artifacts listed above, including `srs.jsonl`, so the manifest and
review-card counts remain deterministic. Do not use the demo bundle directory as
a personal long-term SRS store.

`recall-results.json` is sorted by the synthetic fixture order after matching so
the JSON artifact is byte-stable across SQLite versions. The `aifeed.db` store
itself still supports normal FTS5 recall via `phantom_ai_feed.store.recall`.

## Safety Contract

The loop must remain local and synthetic. It must not:

- fetch live feeds or depend on source availability;
- call a cloud LLM or require API keys;
- include private reading logs, private annotations, credentials, or personal
  recall databases;
- imply that synthetic examples were fetched from live sources.

Live source fetching remains optional outside this bundle and is covered by
`docs/SOURCE_POLICY.md`.
