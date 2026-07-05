# phantom-ai-feed — Feature Audit

Honest status of what is shipped and tested versus what is roadmap. Grounded in
the modules under `phantom_ai_feed/` and the suite under `tests/` (39 test files
as of this writing). Update this file when module status changes.

Runtime is **pure Python stdlib** (`dependencies = []`). Optional LLM/source
integrations are reached through a local `phantom exec` seam or an explicitly
configured Gemini REST key — never as package dependencies. All end-to-end tests
run offline against stub/synthetic paths.

Legend: **Shipped + tested** = working code with tests in `tests/`;
**Shipped, LLM-backed** = works with a real LLM/network but has a tested stub path;
**Roadmap** = not implemented yet.

## Module status

| Module | Status | Notes |
| --- | --- | --- |
| `fetch` | Shipped + tested | Feed fetching with conditional GET, concurrency, and reliability handling. Network is opt-in; `PHANTOM_AI_FEED_OFFLINE=1` records per-feed errors instead of reaching out. Tests: `test_fetch`, `test_fetch_concurrent`, `test_fetch_conditional`, `test_fetch_reliability`, `test_fetch_itertext_e2e`. |
| `digest` / `weekly` | Shipped + tested | Daily and weekly digest rendering with top-picks / ranked-source selection. Tests: `test_digest_toppicks_e2e`, `test_weekly_ranked_sources_e2e`, `test_pipeline_e2e`. |
| `store` / `recall` | Shipped + tested | Local SQLite **FTS5** knowledge store at `~/.phantom-mesh/logs/phantom-ai-feed/aifeed.db`; full-text recall with no daemon required. Tests: `test_store`, `test_recall`, `test_capture_fts5`. |
| `srs` | Shipped + tested | Spaced-repetition review cards generated from captured knowledge. Tests: `test_srs_cli_e2e`. |
| `accumulate` / `capture` / `dedup` / `credibility` | Shipped + tested | Intake, capture-to-FTS5, entry de-duplication, and source-credibility scoring. Tests: `test_accumulate`, `test_dedup`, `test_credibility`, `test_entry_key`. |
| `newsletter` | Shipped + tested | Newsletter rendering with a provenance-leak guard (fixture entries never masquerade as live sources). Tests: `test_newsletter`, `test_newsletter_no_provenance_leak_e2e`. |
| `resolvers/` (youtube, podcast, discover, _net) | Shipped + tested | Source resolvers/discovery adapters. Tests: `test_resolve_youtube`, `test_resolve_podcast`, `test_resolve_discover`, `test_resolve_net`, `test_sources_expanded`. |
| `eval` | Shipped + tested | Evaluation harness + calibration for pipeline output. Tests: `test_eval_harness`, `test_eval_calibration`. |
| `demo_loop` / `source_export` / `knowledge_scenario` | Shipped + tested | Deterministic synthetic bundles (no network, no LLM, no credentials) with documented artifact contracts. Tests: `test_demo_loop_contract`, `test_source_export_contract`, `test_knowledge_scenario_contract`. |
| `pipeline` | Shipped + tested | Chains the daily/weekly flow behind the `phantom-ai-feed` entry point. Tests: `test_pipeline_e2e`, `test_strict_optional_e2e`. |
| `summarize` | Shipped, LLM-backed | Dispatcher: `phantom exec` (mesh provider) → Gemini REST → stub. Only the stub path is exercised in CI (`test_summarize_stub`, `test_prompt_no_double_wrap`, `test_provider_passthrough`); the real-LLM paths require `phantom` on PATH or a Gemini key. |
| `interview_questions` | Shipped, LLM-backed | Weekly ML/AI interview-question generation from the week's digests via Gemini, with a templated stub fallback for no-key/offline runs. |

## No MCP server

Despite the current working-branch name (`dev/strengthen-mcp-*`), this package
ships **no MCP server** and no `phantom-ai-feed-mcp` console script. It is a
CLI pipeline + local FTS5 store. The public entry points are listed under
`[project.scripts]` in `pyproject.toml` (see the README Usage table).

## Live / gated paths

- Real feed fetching happens only when `PHANTOM_AI_FEED_OFFLINE` is unset.
- Real summarization/questions require either a local `phantom exec` or a
  Gemini API key; otherwise the tested stub path is used.
- `tests/test_mesh_roundtrip_live.py` exercises a live mesh round-trip and is
  environment-gated (not part of the offline smoke).

## Honest limitations

- The "AI quality" of digests/questions depends on the configured LLM; the stub
  paths are for smoke/e2e correctness, not for real reading value.
- No provenance from private reading history is stored in the synthetic bundles;
  the recall/SRS value comes only after you run real intake locally.

## Roadmap (not yet shipped)

- Wire the mesh daemon capture backend (`capture.py` phantom seam) back in as a
  first-class alternative to the direct FTS5 store.
- Broaden source resolvers beyond the current youtube/podcast/discover set.
