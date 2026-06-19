# Roadmap

> ARCHIVED 2026-06-19 — 內容已併入 docs/phantom-ai-feed.md;此為歷史版本。

> Single source of truth for project status. Other docs (including `README.md`)
> link here instead of carrying their own status lists.
>
> Last updated: **2026-06-19** · Version: `0.2.0-alpha`

`phantom-ai-feed` is a local-first AI-news pipeline: ingest RSS/Atom → summarize
into a local FTS5 knowledge base → produce a deduped, credibility-ranked weekly
digest → generate interview questions for spaced-repetition review → assemble a
human-reviewed newsletter draft. Zero exfiltration; a satellite producer feeding
the wider `phantom-mesh` ecosystem.

Status is grounded in merged commits on `master` and the modules present in
`phantom_ai_feed/`. Test suite: **103 passing** (`pytest tests/ -v`).

---

## Shipped

The full daily/weekly pipeline runs end-to-end from a single entry point.

- **Single-invocation orchestrator** — `python -m phantom_ai_feed.pipeline`
  chains the existing stages (daily: digest → interview-questions `--register-srs`;
  weekly adds weekly → newsletter), stops on first stage error. Realizes the
  "daemon-friendly single scheduled invocation" vision. (`pipeline.py`)
- **RSS/Atom fetch** — `fetch.py`: 14 feeds (incl. Chinese `zh` sources +
  `optional`-flagged breadth feeds), bounded retry/backoff, HTML stripping that
  preserves prose after inline tags, per-feed status counts,
  `PHANTOM_AI_FEED_OFFLINE=1` honoured.
- **Summarization** — `summarize.py`: `phantom exec` → Gemini Flash REST →
  stdlib extractive stub fallback (degrade-don't-crash; no API key required).
- **Daily digest** — `digest.py`: fetch → summarize → write Markdown +
  best-effort phantom capture; surfaces dedup + credibility "Top picks".
- **Weekly digest** — `weekly.py`: fetch wide → cross-source dedup/clustering →
  credibility ranking → one LLM pass; surfaces credibility + corroboration.
- **Cross-source dedup / topic clustering** — `dedup.py`: URL + title-overlap
  merge (empty-title + distinct-URL entries no longer false-merge).
- **Source credibility weighting** — `credibility.py`: per-category trust +
  fetch history + corroboration (distinct sources, not raw dups) for ranking and
  dedup tie-breaks.
- **Interview-question generator** — `interview_questions.py`: weekend question
  generator from the week's digests; `--register-srs` seeds review cards.
- **SM-2 spaced repetition** — `srs.py` + `srs answer` / `srs due` CLI;
  the daily pipeline now **resurfaces due cards** (emits `srs-due-<date>.md`),
  closing the spaced-repetition loop (not just write-only).
- **Newsletter draft** — `newsletter.py`: human-reviewed Substack-style draft
  assembled from the weekly digest + questions; no internal provenance leaks
  into the reader-facing draft (human-in-the-loop, never autopilot).
- **FTS5 capture adapter** — `capture.py`: fold an entry into the phantom store
  (unit-tested CLI seam).
- **Eval harness** — `eval.py`: grade generated questions against a real ~20-Q
  gold set (coverage / category-mix / dup metrics + calibrated pass/fail bars).
- **`--strict` run** — optional `feed` flag honoured so a strict run requires
  only the core feed set to be reachable.
- **Mesh round-trip test** — gated LIVE `capture_entry → phantom serve → recall`
  integration test (skips on Windows / no-provider; HOME-isolated; hermetic).
- **CI** — GitHub Actions pytest workflow + badge; asciinema demo cast
  (`docs/demo.cast`).

## In progress

_Nothing actively in flight on `master` as of 2026-06-19. The pipeline is at its
"final form" for the current alpha; next work is scheduling and breadth (below)._

## Planned-next

- **Real cron / daemon scheduling** — wire the single `pipeline` entry point to
  an actual scheduler (launchd / cron), migrating off the earlier hailmary
  cron-only heartbeat. (Pipeline supports it; the schedule itself is future.)
- **Substack publish hook** — beyond file-output drafts; keep human-in-the-loop
  (auth + send still manual by design).
- **Multimodal capture** — YouTube AI-channel audio summaries (Whisper);
  podcast text.
- **More Chinese / cross-language breadth** — additional zh sources; en/ja fork
  path for non-English-native engineers.
- **phantom-companion integration** — read-vs-unread ratio analysis as a
  learning-behaviour signal.
- **Premium / paid sources** — gated breadth (e.g. arxiv-sanity-class).

## Out of scope (deliberately not doing)

- A full reader app (Readwise already does this).
- Social / commenting features (violates local-first).
- Fully automated Substack publishing (must stay human-in-the-loop).
