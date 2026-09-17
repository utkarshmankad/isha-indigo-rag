# Reject missing production embedding keys (hardening backlog)

## The gap

`src/embedding/embedder.py`'s `embed_batch` previously fell back to
`mock_embed` — a deterministic hash-based vector, not a real embedding —
whenever `OPENAI_API_KEY` was unset, logging one warning line and then
running silently forever after. A misconfigured production deployment
(key missing from env, secrets not wired up, etc.) would start up fine,
answer every query without error, and return semantically meaningless
retrieval results with no further signal that anything was wrong beyond
that one log line at startup.

`src/observability/health.py`'s `/health` check already flagged a missing
key as `{"status": "error"}` — but nothing stopped the actual query
pipeline from running anyway if something called `embed_batch` directly
without going through the health-gated startup path.

## The fix

`embed_batch` now raises `EmbeddingConfigurationError` when
`OPENAI_API_KEY` is unset, unless `ISHA_ALLOW_MOCK_EMBEDDINGS` is
explicitly set (`true`/`1`/`yes`, case-insensitive). This is an opt-in
escape hatch for local development only (e.g. exercising the pipeline
without incurring OpenAI cost) — never for production.

This closes the gap everywhere `embed_batch` is called, not just at one
entrypoint: the FastAPI pipeline (`src/api/main.py`), the Streamlit app
(`app.py`), self-serve document ingestion (`src/ingestion/self_serve.py`),
and the eval scripts all go through this same function.

## Why this doesn't remove `mock_embed`

`mock_embed` itself is a legitimate, tested, deterministic hash-based
vector generator — useful for local development and as a pure function in
`tests/test_embedder.py`. The gap was never `mock_embed` existing; it was
that using it required no explicit decision. Now it does.

## What already degrades gracefully vs. what's new here

`src/agent/graph.py`'s `retrieve_node` already wraps the embedding call in
a `try/except` and returns `stage_error="embedding"`, which
`src/api/main.py` turns into a `503 Service temporarily unavailable`
response — so in the query path, this change turns "silently wrong
answers" into "a clear, correct failure," not a crash. The one place this
is a behavior change without a safety net is `self_serve.py`'s
`ingest_document_for_tenant`/`update_document_for_tenant`, which call
`embed_chunks` unguarded — previously a misconfigured key would silently
create a searchable-but-garbage self-serve chunk; now it raises, and the
Streamlit UI's existing generic `except Exception` handler shows "❌
Ingestion failed" instead of silently corrupting the index.

## Scope

This is specifically about the embedding key. It does not address the
other hardening-backlog items (query log redaction, shared rate limits
across workers, evaluation/deployed corpus alignment, or separately
measuring false answers vs. refusals) — those are separate, not yet
started.
