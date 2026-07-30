# Sprint 2: Reliability & Observability — Completion Checklist

**Status**: ✅ **COMPLETED**
**Commits**: 6 feature commits on `main`

---

## ✅ Task Execution Summary

### S2-T1: Structured Logging (no sensitive data in logs)

**New file**: `src/observability/logging_config.py`

- Stdlib `logging` + custom `JsonFormatter` — every log line is one JSON object
  (timestamp, level, logger, message, structured fields).
- `RedactionFilter` strips OpenAI-style API keys, `Bearer` tokens, emails,
  12-digit PNRs, passport numbers, and phone numbers from both the message
  and any structured `extra_fields` before it reaches stdout or
  `logs/app.jsonl`. Dict keys named `api_key`/`password`/`token`/etc. are
  fully masked regardless of content.
- Replaced `print()` debugging in the hot paths (`src/agent/graph.py`,
  `src/retrieval/retriever.py`, `src/embedding/embedder.py`,
  `src/embedding/vector_store.py`, `src/observability/logger.py`) with
  `get_logger(__name__)` calls.
- **Bonus fix**: two pre-existing bugs in `src/security/prompt_protection.py`
  (stray indentation, un-annotated Pydantic fields) were silently breaking
  `pytest` collection for the entire retrieval test module — fixed as part
  of getting the test suite green again.

### S2-T2: Health Check Endpoint

**New files**: `src/observability/health.py`, `health_server.py`

- `run_health_checks()` checks OpenAI key presence, Qdrant reachability
  (live `get_collections()` call), and log-directory writability.
- Streamlit has no route for custom endpoints, so a small standalone
  FastAPI app (`health_server.py`) exposes `GET /health`: `200` when every
  dependency is `ok`, `503` when any is `degraded`. Run alongside
  Streamlit with `uv run uvicorn health_server:app --port 8000`.
- Manually verified: returns `503` with a per-dependency breakdown when
  Qdrant is unreachable, `200` when healthy.

### S2-T3: Error Boundaries per RAG Stage

**Modified**: `src/agent/graph.py`

Each LangGraph node now degrades instead of crashing the whole request:

| Stage | Failure mode | Fallback |
|---|---|---|
| `select_tools` | tool routing throws | fall back to full-corpus search (`search_all=True`) |
| `retrieve` (embedding) | `embed_batch` throws | return zero chunks, `confidence=0.0` |
| `retrieve` (search) | Qdrant/BM25 throws | return zero chunks, `confidence=0.0` |
| `generate` | prompt build or LLM call throws | safe fallback answer with airline support contact |

`AgentState.stage_error` records which stage (if any) degraded, feeding
into the S2-T6 metrics.

### S2-T4: Circuit Breaker for LLM Calls

**New file**: `src/reliability/circuit_breaker.py`

- Standard closed → open → half-open breaker (`CircuitBreaker` class).
- Wraps the OpenAI `chat.completions.create` call in
  `graph.generate_answer`: after 5 consecutive failures, fails fast for
  30s (`CircuitBreakerOpenError`) instead of continuing to hit a
  struggling upstream, then allows one probe call before fully closing.
- An open breaker is caught by the S2-T3 generation-stage boundary, so
  users still get a safe fallback answer, not a stack trace.
- Verified with a standalone script: 2 induced failures → breaker opens
  → immediate `CircuitBreakerOpenError` → auto half-open after cooldown
  → closes again on a successful probe call.

### S2-T5: Correlation IDs

**Modified**: `src/agent/graph.py`, `src/observability/logger.py`, `app.py`

- `run_agent()` generates (or accepts) a `uuid4` correlation ID per
  query, stored in `AgentState.correlation_id`.
- Every log line across all three RAG stages, the query-log JSONL record,
  and the Streamlit app-layer error handler now carries the same
  `correlation_id` — a single request's full trace can be grepped out of
  `logs/app.jsonl` by ID.

### S2-T6: Retrieval Quality Metrics

**Modified**: `src/observability/logger.py`, `src/agent/graph.py`

- `log_query()` now records `avg_relevance_score` (mean retrieval score
  of the chunks used), `expanded_search` (whether the low-confidence
  second retrieval pass fired), `stage_error`, and a derived
  `fallback_triggered` flag (expansion, stage failure, or zero chunks).
- `print_summary()` reports avg relevance and fallback rate alongside
  existing confidence/latency stats, plus a stage-failure breakdown —
  giving a first read on how often the pipeline degrades vs. answers
  cleanly.

---

## Testing

- Full `pytest` suite (50 tests) passes after every commit.
- `/health` manually exercised against real Qdrant credentials (verified
  both healthy and degraded responses).
- Redaction verified against realistic queries (lithium power bank /
  flight delay wording does **not** false-positive; real phone numbers
  and emails **do** get redacted).
- Circuit breaker state machine verified standalone (open → half-open →
  closed transitions).
- `log_query` / `print_summary` verified end-to-end with synthetic
  entries showing fallback rate and stage-failure counts.

## Security Review

- No new hardcoded secrets; `health_server.py` and `logging_config.py`
  both load config from environment variables only.
- Redaction filter prevents API keys, tokens, PII (email/phone/PNR/
  passport) from persisting to `logs/app.jsonl`, addressing the
  Sprint 1 "no sensitive data in logs" requirement.
- `/health` responses only ever return `status`/`detail` strings, never
  the underlying credential values.

## Carried Over from Sprint 1 (still pending)

- Rate limiting (`src/security/rate_limiter.py`) is implemented but not
  wired into `app.py` — noted in `docs/SPRINT1-CHECKLIST.md`, not part of
  this sprint's scope.

**Next Sprint**: Sprint 3 — Code Quality & Testing
