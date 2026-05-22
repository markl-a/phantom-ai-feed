# Tier 1 initial dev — 2026-05-22

## What's in (this commit)

- `phantom_ai_feed/fetch.py` — RSS/Atom fetcher refactored from hailmary
  scaffold into a library (`load_feeds`, `fetch_feed`, `fetch_all`).
  Stdlib only; tomllib with tomli fallback for Python 3.10.
- `phantom_ai_feed/summarize.py` — `summarize_gemini()` (REST via
  `urllib.request`, no SDK), `summarize_stub()` (first-2-sentences
  extractive), and `summarize()` dispatcher with stub fallback on
  missing key OR transport error (degrade-don't-crash).
- `phantom_ai_feed/digest.py` — orchestrator. Writes Markdown to
  `~/.phantom-mesh/logs/phantom-ai-feed/<date>.md` (same path as
  hailmary scaffold, so daily file is interchangeable). Best-effort
  `phantom event capture` per entry if CLI on PATH (silent on miss).
- `phantom_ai_feed/interview_questions.py` — reads last 6 daily files,
  emits 5 questions. Stub mode uses Counter of top `## section` topics
  + 5 templated question stems.
- `tests/test_summarize_stub.py` — 4 cases: non-empty, empty input,
  forced-stub-overrides-env, no-key-fallback.
- `tests/test_fetch.py` — 2 cases: feeds.toml parses ≥8 feeds; HN live
  fetch returns ≥3 entries (skipped offline).
- `sources/feeds.toml`, `LICENSE` (Apache-2.0), `.gitignore`, `README.md`
  copied/adapted from hailmary scaffold.

## What real impl needs next

1. **Gemini API key wiring**: confirm `gemini-2.5-flash` model name vs
   `gemini-flash-latest`; add rate-limit backoff (current code is
   one-shot per call, no retry). Decide if we want streaming for the
   weekly question generator (longer output).
2. **SM-2 spaced repetition** for the question bank: persist
   `weekly-questions-*.md` answers + grades into a JSONL log,
   reschedule due dates per SM-2; export "due today" set to a daily
   review file. Probably a new module `phantom_ai_feed/srs.py`.
3. **Substack draft pipeline**: weekly aggregator that takes 7 days of
   digests + question bank, asks Gemini to produce a 1200-word
   editorial draft (Substack-flavoured intro + 3 deep-dives + CTA),
   writes to `~/.phantom-mesh/logs/phantom-ai-feed/substack/`. Auth
   pending — start with file output only, copy/paste to Substack
   manually.
4. **Interview question quality calibration**: today the LLM prompt is
   generic ("ML hiring manager"). Build a small eval set of 20
   reference questions from real interviews; score generated questions
   on (a) groundedness in the week's content, (b) difficulty mix, (c)
   non-duplicate vs prior weeks. Likely needs a `phantom_ai_feed/eval.py`
   harness.
5. **FTS5 wire confirmation**: `phantom event capture` is a stub call
   today — confirm the actual CLI signature in phantom-mesh and add a
   `--dry-run` mode so we can verify wire-up without polluting the
   index during dev.
6. **Cron migration**: once this repo is stable, switch launchd plist
   from `hailmary/.../heartbeat-daily.py` to
   `python -m phantom_ai_feed.digest` and add a separate Sat 18:00
   trigger for `interview_questions`.

## Known limitations

- No retries on transient HTTP errors (one-shot, then captured as
  ERROR section in the daily Markdown).
- Reddit `r/LocalLLaMA` RSS sometimes 429s without UA rotation — same
  behaviour as hailmary scaffold.
- arxiv RSS bodies are HTML-heavy; summarizer treats whole blob as
  plain text, so stub mode for arxiv looks scrappy. Gemini path
  handles it fine. Could add a tiny HTML→text strip in fetch.py later.
