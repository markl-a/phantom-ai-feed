<!--
Sample output, regenerable. Produced by the real pipeline in stub mode:

    python -m phantom_ai_feed.interview_questions --use-stub \
        --log-dir <dir-with-sample-digest> --end 2026-06-14

The stub generator (no LLM / no API key) counts the "## <heading>" lines across
the week's digests, takes the top topics, and fills a fixed question template
bank — one template per topic. This run had 3 topics (from docs/sample-digest.md),
so 3 questions are produced; with more daily digests it emits up to 5. With a
real GEMINI_API_KEY the questions are LLM-written and grounded in the week's
stories instead. All topics below come from the synthetic sample digest.
-->

# phantom-ai-feed weekly interview questions — week ending 2026-06-14

_Stub generator: questions templated from this week's top sources._

1. Explain Sparse-MoE-routing at a level a senior ML engineer would expect; include one failure mode you have seen in production.
2. Walk through how you would build an offline benchmark for Quantization; what metric correlates best with user-perceived quality?
3. Compare two real implementations of RAG-evaluation; where do their assumptions diverge?
