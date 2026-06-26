# Knowledge Scenario Bundle Contract

`phantom-ai-feed-scenario` / `python -m phantom_ai_feed.knowledge_scenario`
turns a synthetic `demo-loop` bundle into a P3 knowledge-intake proof. It shows
that synthetic multi-source intake can be captured locally, recalled by query,
and converted into an SRS review queue without live feeds, private reading
history, credentials, cloud LLM output, or personal annotations.

## Command

```powershell
python -m phantom_ai_feed.demo_loop --out <source-bundle> --date 2026-06-26 --query RAG
python -m phantom_ai_feed.knowledge_scenario --source <source-bundle> --out <scenario-bundle>
```

The command prints `<scenario-bundle>\manifest.json`.

## Accepted Source

`knowledge_scenario` accepts only a synthetic demo-loop bundle whose manifest
declares:

- `mode=synthetic_knowledge_intake_loop`
- `data_policy=synthetic_only`
- `private_data_included=false`
- `external_network=false`
- `llm_provider=stub_or_disabled`

Any artifact path declared by the source manifest must be bundle-relative and
must resolve inside the source bundle before it is read.

## Bundle Layout

```text
<scenario-bundle>/
  manifest.json
  knowledge-scenario.json
  recall-review-plan.json
  summary.md
```

## Manifest Schema

`manifest.json` is stable JSON with sorted keys and schema version `1`.

Required top-level fields:

- `mode`: `synthetic_knowledge_scenario_bundle`
- `source_mode`: `synthetic_knowledge_intake_loop`
- `data_policy`: `synthetic_only`
- `private_data_included`: always `false`
- `external_network`: always `false`
- `llm_provider`: `stub_or_disabled`
- `live_sources_required`: always `false`
- `artifacts`: bundle-relative paths for scenario JSON, review-plan JSON, and
  summary

## Scenario JSON

`knowledge-scenario.json` contains:

- coverage counts for source count, item count, captured entries, recall hits,
  review cards, and due cards
- query metadata and matched titles
- top recall hit metadata: title, source, category, link, and content hash
- review readiness counts and first due-card id
- readiness booleans for multi-source intake, recall grounding, review queue,
  and shareability
- explicit boundaries for live source fetch, cloud LLM, private reading history,
  credentials, and personal annotations

It does not include raw source excerpts, full review questions, private reading
notes, credentials, cookies, personal annotations, private recall databases, or
cloud LLM output.

## Recall Review Plan

`recall-review-plan.json` contains metadata-only due-card entries:

- question id
- source title, source id, category, and content hash
- due date, ease factor, and interval days
- `full_question_included=false`
- `raw_source_excerpt_included=false`

## Determinism

Two scenario bundles from the same source bundle must produce byte-stable
`manifest.json`, `knowledge-scenario.json`, `recall-review-plan.json`, and
`summary.md`.
