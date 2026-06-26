# Open Source Readiness

Project: `phantom-ai-feed`
Current phase: P3 knowledge-intake recall/SRS scenario proof slice verified
Master plan: `../../PHANTOM-SATELLITES-OPEN-SOURCE-MASTER-PLAN.md`

## Shipped Features

- Local-first AI feed pipeline with module-level CLIs for pipeline, digest, recall, SRS, newsletter, evaluation, and source resolvers.
- Installable package metadata now exists in `pyproject.toml`.
- Console scripts now include `phantom-ai-feed`, `phantom-ai-feed-digest`, `phantom-ai-feed-weekly`, `phantom-ai-feed-recall`, `phantom-ai-feed-srs`, `phantom-ai-feed-export`, and `phantom-ai-feed-scenario`.
- Root README now includes install commands, console script table, and no-network smoke check.
- Root README points to `docs/phantom-ai-feed.md`.
- Source registry policy is documented in `docs/SOURCE_POLICY.md`.
- P2 synthetic knowledge loop contract is documented in `docs/SYNTHETIC_KNOWLEDGE_LOOP.md`.
- `python -m phantom_ai_feed.demo_loop` writes a deterministic synthetic source-items, digest, local FTS5 DB, recall result, review cards, SRS due report, summary, and `manifest.json`.
- P2 source adapter/export contract is documented in `docs/SOURCE_EXPORT_BUNDLE.md`.
- `python -m phantom_ai_feed.source_export` accepts only safe synthetic demo-loop bundles and writes deterministic source adapter, collection export, review export, summary, and `manifest.json`.
- P3 knowledge-intake recall/SRS scenario contract is documented in `docs/KNOWLEDGE_SCENARIO_BUNDLE.md`.
- `python -m phantom_ai_feed.knowledge_scenario` accepts only safe synthetic demo-loop bundles and writes deterministic `knowledge-scenario.json`, `recall-review-plan.json`, `summary.md`, and `manifest.json`.
- `source_export` and `knowledge_scenario` validate manifest artifact paths as bundle-relative and contained inside the source bundle before reading.
- Test suite baseline after P2 synthetic knowledge loop additions: `python -m pytest -q` passed with 207 tests and 1 skipped test.
- Test suite baseline after P2 source export additions: `python -m pytest -q` passed with 211 tests and 1 skipped test.
- Test suite baseline after P3 knowledge scenario additions and manifest-path hardening: `python -m pytest -q` passed with 216 tests and 1 skipped test.
- Help surface verified for:
  - `python -m phantom_ai_feed.pipeline --help`
  - `python -m phantom_ai_feed.digest --help`
  - `python -m phantom_ai_feed.recall --help`

## Planned Or Deferred Features

- Broader knowledge intake system: topic watchlists, richer collection management, annotation workflows, and knowledge graph extraction.
- Fully autonomous source maintenance, structured knowledge graph extraction, and agentic curation are out of initial release scope.

## Install And Test Commands

```powershell
python -m pytest -q
python -m pip install -e . --dry-run --no-deps
set PHANTOM_AI_FEED_OFFLINE=1
python -m phantom_ai_feed.digest --use-stub --strict --force --out <temp>
python -m phantom_ai_feed.pipeline --help
python -m phantom_ai_feed.digest --help
python -m phantom_ai_feed.recall --help
python -m phantom_ai_feed.demo_loop --out <temp>\bundle --date 2026-06-26 --query RAG
python -m phantom_ai_feed.source_export --source <temp>\bundle --out <temp>\export
python -m phantom_ai_feed.knowledge_scenario --source <temp>\bundle --out <temp>\scenario
```

Observed result on 2026-06-26:

```text
207 passed, 1 skipped
pip editable metadata OK; would install phantom-ai-feed-0.1.0a0
offline smoke wrote 2026-06-26.md with 0/9 feeds OK and isolated offline errors
```

Observed P2 source export targeted result on 2026-06-26:

```text
3 passed in 0.10s
```

Observed P2 source export full-suite result on 2026-06-26:

```text
211 passed, 1 skipped in 40.05s
212 tests collected
pip editable metadata OK; would install phantom-ai-feed-0.1.0a0
```

Observed P3 knowledge scenario targeted result on 2026-06-26:

```text
3 passed in 0.09s
```

Observed P3 contract bundle result on 2026-06-26:

```text
13 passed in 0.30s
```

Observed P3 knowledge scenario full-suite result on 2026-06-26:

```text
216 passed, 1 skipped in 54.02s
```

## Fixture And Data Policy

- Public demos must use synthetic or intentionally public feed fixtures.
- Live sources must remain optional and must not break local tests.
- No private reading logs, credentials, annotations, or personal recall database may be committed.
- Export artifacts must not imply live fetches occurred and must not include private credentials, cookies, private annotations, private reading logs, or personal recall databases.
- Scenario artifacts must not include raw source excerpts, full review questions, private reading notes, credentials, cookies, personal annotations, private recall databases, or cloud LLM output.

## Safety And Privacy Risks

- Feed content can contain copyrighted or private material; exported examples must avoid private content.
- Live fetching can be flaky; tests must remain hermetic.
- Summaries and digests must not imply sources were fetched live unless they were.

## Blockers To Next Phase

- None for the current P3 knowledge-intake recall/SRS scenario proof slice. Next phase should harden topic watchlists or collection workflows without making live sources mandatory.

## Evidence

- `README.md` points to `docs/phantom-ai-feed.md`.
- `README.md` includes `demo-loop` as the deterministic synthetic knowledge-intake artifact bundle.
- `README.md` includes `source_export` as the deterministic source adapter/export artifact bundle.
- `README.md` includes `knowledge_scenario` as the deterministic knowledge-intake recall/SRS scenario bundle.
- `pyproject.toml` declares package `phantom-ai-feed` and seven console scripts.
- `pyproject.toml` declares `phantom-ai-feed-scenario = phantom_ai_feed.knowledge_scenario:main`.
- `docs/SYNTHETIC_KNOWLEDGE_LOOP.md` documents `manifest.json`, `synthetic_knowledge_intake_loop`, `synthetic_only`, `private_data_included=false`, `external_network=false`, `stub_or_disabled`, and the stable text artifact set.
- `docs/SOURCE_EXPORT_BUNDLE.md` documents `manifest.json`, `source-adapter-contract.json`, `collection-export.json`, `review-export.json`, `synthetic_source_export_bundle`, `synthetic_only`, `private_data_included=false`, `external_network=false`, `stub_or_disabled`, and `live_sources_required=false`.
- `docs/KNOWLEDGE_SCENARIO_BUNDLE.md` documents `manifest.json`, `knowledge-scenario.json`, `recall-review-plan.json`, `synthetic_knowledge_scenario_bundle`, `synthetic_only`, `private_data_included=false`, `external_network=false`, `stub_or_disabled`, and metadata-only recall/SRS review boundaries.
- `python -m pytest tests/test_source_export_contract.py -q`: 3 passed.
- `python -m pytest tests/test_knowledge_scenario_contract.py -q`: 3 passed.
- `python -m pytest tests/test_open_source_contract.py tests/test_knowledge_scenario_contract.py tests/test_source_export_contract.py tests/test_packaging.py -q`: 13 passed.
- `python -m pytest tests/test_source_export_contract.py tests/test_open_source_contract.py tests/test_packaging.py tests/test_demo_loop_contract.py -q`: 11 passed.
- `python -m pytest tests/test_packaging.py -q`: 2 passed.
- `python -m pytest tests/test_source_policy_docs.py -q`: 2 passed.
- `python -m pytest tests/test_packaging.py tests/test_strict_optional_e2e.py tests/test_sources_expanded.py -q`: 9 passed.
- `python -m pytest tests/test_demo_loop_contract.py tests/test_open_source_contract.py tests/test_recall.py tests/test_store.py tests/test_srs_cli_e2e.py tests/test_packaging.py tests/test_source_policy_docs.py -q`: 24 passed.
- `python -m pytest -q`: 211 passed, 1 skipped.
- `python -m pytest --collect-only -q`: 212 tests collected.
- `python -m pip install -e . --dry-run --no-deps`: editable metadata OK.
- `PHANTOM_AI_FEED_OFFLINE=1 python -m phantom_ai_feed.digest --use-stub --strict --force --out <temp>`: no-network smoke OK.
- `python -m phantom_ai_feed.pipeline --help`: help OK.
- `python -m phantom_ai_feed.digest --help`: help OK.
- `python -m phantom_ai_feed.recall --help`: help OK.
- `python -m phantom_ai_feed.source_export --help`: help OK.
- P2 synthetic knowledge loop smoke:
  - `demo_loop --out <temp> --date 2026-06-26 --query RAG` wrote `manifest.json`.
  - Manifest recorded `mode=synthetic_knowledge_intake_loop`, 4 source items, 4 captured entries, 2 recall hits, 4 review cards, 4 due cards, `private_data_included=false`, `external_network=false`, and `llm_provider=stub_or_disabled`.
  - Same-output rerun kept `srs.jsonl` stable and `recall-results.json` first hit was `Synthetic RAG evaluation harness`.
- P2 source export smoke:
  - `source_export --source <temp>\bundle --out <temp>\export` wrote `manifest.json`.
  - Manifest recorded `mode=synthetic_source_export_bundle`, `source_mode=synthetic_knowledge_intake_loop`, `data_policy=synthetic_only`, `private_data_included=false`, `external_network=false`, `llm_provider=stub_or_disabled`, and `live_sources_required=false`.
  - Bundle contained `source-adapter-contract.json`, `collection-export.json`, `review-export.json`, and `summary.md`; contract tests verify private reading, API key, credential, cookie, personal annotation, and live source fetch wording are excluded from exported artifacts.
- P3 knowledge scenario smoke:
  - `knowledge_scenario --source <temp>\bundle --out <temp>\scenario` wrote `manifest.json`.
  - Manifest recorded `mode=synthetic_knowledge_scenario_bundle`, `source_mode=synthetic_knowledge_intake_loop`, `data_policy=synthetic_only`, `private_data_included=false`, `external_network=false`, `llm_provider=stub_or_disabled`, and `live_sources_required=false`.
  - `knowledge-scenario.json` recorded 4 sources, 4 items, 4 captured entries, 2 recall hits, 4 review cards, 4 due cards, top hit `Synthetic RAG evaluation harness`, and readiness flags for multi-source intake, recall grounding, review queue, and shareability.
  - `recall-review-plan.json` contained metadata-only due-card entries with `full_question_included=false` and `raw_source_excerpt_included=false`.
  - Contract tests verify raw source excerpts, full review question text, private reading notes, API key/cookie wording, personal annotation wording, live source fetch wording, and manifest path traversal are excluded or rejected.
- `agy` reviewer result: no blockers. Low-severity design notes were documented in `docs/SYNTHETIC_KNOWLEDGE_LOOP.md`: same-bundle reruns reset bundle-owned SRS artifacts for deterministic counts, and `recall-results.json` is fixture-order sorted for cross-platform byte stability while the SQLite DB still supports FTS5 recall.
- `agy` P2 source export reviewer result: initial review found README console script table drift; fixed by adding `phantom-ai-feed-export`. Re-review result: `NO BLOCKERS`.
- `agy` P3 knowledge scenario reviewer result: `NO BLOCKERS` for unsafe manifest/artifact paths, raw source excerpt/full review question/private reading data leaks, live source fetch or cloud LLM implication, credential/cookie/personal annotation leakage, nondeterminism, false recall/SRS readiness, packaging console script drift, or CLI/docs/tests mismatch.

## P4 Release-Prep Slice 1

Status: governance baseline added; this does not mark the project release-ready.

Evidence:
- `CONTRIBUTING.md` defines the contribution workflow, required test command, readiness-doc update rule, and no-private-data/no-credentials boundary.
- `SECURITY.md` defines private vulnerability reporting, supported version scope, 7-day acknowledgement target, and safe report contents.
- `python -m pytest tests/test_release_prep_contract.py -q`: 1 passed.
- `python -m pytest -q`: 217 passed, 1 skipped.

Remaining P4 work: full release gate, final docs audit, package metadata audit, release notes, tag plan, and maintainer sign-off.

## P4 Release-Prep Slice 2

Status: final release gate checklist added; this does not mark the project release-ready.

Evidence:
- `CHANGELOG.md` records the unreleased governance/release-checklist work and points back to readiness evidence.
- `docs/RELEASE_CHECKLIST.md` documents final tests, dependency/license review, secret/private-data scan, known limitations, and manual maintainer approval.
- `python -m pytest tests/test_release_prep_contract.py -q`: 2 passed.
- `python -m pytest -q`: 218 passed, 1 skipped.

Remaining P4 work: execute final scans, complete dependency/license review, finalize release notes, and record manual maintainer approval.

## P4 Release-Prep Slice 3

Status: final scan and direct dependency/license audit recorded; not release-ready.

Evidence:
- `docs/FINAL_RELEASE_AUDIT.md` records scan scope, `high_conf_secret_hits=0`, direct dependency/license review, and remaining release blockers.
- Direct release-scope dependency review: no runtime dependencies beyond Python stdlib.
- `python -m pytest tests/test_release_prep_contract.py -q`: 3 passed.
- `python -m pytest -q`: 219 passed, 1 skipped.

Remaining P4 work: release notes finalization, tag plan, final maintainer approval, and separate review for any live source/browser/cloud adapter.

## P4 Release-Prep Slice 4

Status: maintainer approval recorded, conductor sign-off complete, and release-candidate tag created.

Evidence:
- `docs/RELEASE_NOTES.md` records public release-candidate notes, known limitations, and verification pointers.
- `docs/TAG_PLAN.md` records proposed tag `v0.1.0-alpha.0`, required approval-before-tag sequence, and rollback steps.
- `docs/PUBLIC_RELEASE_APPROVAL.md` records `Status: approved` with approver, approval date, and approved tag.
- Conductor root approval packet `PHANTOM-SATELLITES-PUBLIC-RELEASE-APPROVAL.md` records all ten candidate tags as approved.
- `.github/workflows/ci.yml` runs an explicit `release-prep gate` against `tests/test_release_prep_contract.py`.
- `python -m pytest tests/test_release_prep_contract.py -q`: 5 passed.
- `python -m pytest -q`: 221 passed, 1 skipped.

Remaining P4 work: none for the approved release-candidate tag.
