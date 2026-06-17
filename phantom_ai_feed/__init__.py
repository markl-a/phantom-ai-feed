"""phantom-ai-feed: AI engineering daily digest + interview question generator.

A local-first, privacy-preserving AI-news pipeline: ingest RSS/Atom (14 feeds,
incl. Chinese sources), summarize into a local FTS5 knowledge base, produce a
weekly deduped + credibility-ranked digest, generate interview questions for
learning validation, and assemble a human-reviewed newsletter draft. Zero
exfiltration; a satellite producer feeding phantom-companion.

Modules:
- fetch:               RSS/Atom → list[Entry] (bounded retry/backoff, HTML strip)
- summarize:           phantom exec → Gemini Flash REST → stdlib stub fallback
- capture:             fold an entry into the phantom FTS5 store (CLI seam)
- dedup:               cross-source dedup / topic clustering (URL + title overlap)
- credibility:         per-category trust + fetch history + corroboration weighting
- digest:              daily orchestrator (fetch → summarize → write md + capture)
- weekly:              weekly digest (fetch wide → dedup → rank → one LLM pass)
- interview_questions: weekend question generator from the week's digests
- eval:                grade generated questions vs a real gold set (coverage /
                       category-mix / dup metrics + calibrated pass/fail bars)
- newsletter:          assemble a human-reviewed Substack-style draft
"""

__version__ = "0.2.0-alpha"
