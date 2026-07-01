# Source Export Bundle Contract

`phantom-ai-feed-export` / `python -m phantom_ai_feed.source_export` is the P2
artifact slice for source adapter contracts and review/export ergonomics. It
derives a deterministic export package from a safe synthetic `demo-loop` bundle.

## Command

```powershell
python -m phantom_ai_feed.demo_loop --out <source-bundle> --date 2026-06-26 --query RAG
python -m phantom_ai_feed.source_export --source <source-bundle> --out <export-bundle>
```

The command prints `<export-bundle>\manifest.json`.

## Accepted Source

`source_export` accepts only a synthetic demo-loop bundle whose manifest declares:

- `mode=synthetic_knowledge_intake_loop`
- `data_policy=synthetic_only`
- `private_data_included=false`
- `external_network=false`
- `llm_provider=stub_or_disabled`

Bundles that declare private data, live network access, or live LLM output are
rejected.

Any artifact path declared by the source manifest must be bundle-relative and
must resolve inside the source bundle before it is read.

## Bundle Layout

```text
<export-bundle>/
  manifest.json
  source-adapter-contract.json
  collection-export.json
  review-export.json
  summary.md
```

## Manifest Schema

`manifest.json` is stable JSON with sorted keys and schema version `1`.

Required top-level fields:

- `mode`: `synthetic_source_export_bundle`
- `source_mode`: `synthetic_knowledge_intake_loop`
- `data_policy`: `synthetic_only`
- `private_data_included`: always `false`
- `external_network`: always `false`
- `llm_provider`: `stub_or_disabled`
- `live_sources_required`: always `false`
- `artifacts`: bundle-relative paths for `adapter_contract`,
  `collection_export`, `review_export`, and `summary`

## Adapter Contract

`source-adapter-contract.json` documents the minimum adapter interface:

- `source_id`
- `source_type`
- `fetch_policy`
- `license_note`
- `citation_policy`
- `output_schema`

Supported source-type labels include fixture, RSS, web page, newsletter export,
and paper metadata. Live fetch remains disabled by default and tests must use
fixture/offline data.

## Collection Export

`collection-export.json` contains synthetic fixture items with title, source,
category, link, summary excerpt, content hash, matched-query flag, and
`source_policy=synthetic_fixture`.

## Review Export

`review-export.json` contains generated review cards with question id, question,
source title, and review policy. It does not depend on the SQLite DB bytes.

## Safety Contract

The export bundle must not fetch live feeds, require API keys, require private
credentials, include cookies, include personal annotations, include private
reading logs, or imply that synthetic fixture entries came from live sources.

## Determinism

Two runs against the same source bundle must produce byte-stable `manifest.json`,
`source-adapter-contract.json`, `collection-export.json`, `review-export.json`,
and `summary.md`.
