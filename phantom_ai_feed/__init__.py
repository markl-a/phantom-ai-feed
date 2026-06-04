"""phantom-ai-feed: AI engineering daily digest + interview question generator.

Tier 1 modules:
- fetch:               RSS/Atom → list[Entry]
- summarize:           Gemini Flash REST + stdlib stub fallback
- digest:              daily orchestrator (fetch → summarize → write md + FTS5)
- weekly:              weekly digest (fetch wide → one LLM ranking pass → write md)
- interview_questions: weekend question generator from week's digests
"""

__version__ = "0.1.0-alpha"
