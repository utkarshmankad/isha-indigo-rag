# Sprint 6: API & Channel Integrations — Completion Checklist

**Status**: ✅ **COMPLETED** (Slack/WhatsApp channels deferred, see scope note)

**Branch note**: stacked on `sprint-5-self-serve-admin` (→ `sprint-4-multi-tenancy`
→ `main`) — the API's auth reuses the Sprint 4 tenant registry. Merge order:
Sprint 4 → Sprint 5 → Sprint 6.

**Scope note**: the original roadmap bundled Slack + WhatsApp into this
sprint alongside the FastAPI wrapper. WhatsApp needs Meta Business
verification lead time outside anyone's direct control (flagged as a risk
back in the original sprint plan); Slack is a thin wrapper once the HTTP
API exists but wasn't built this pass to keep the diff reviewable. What's
here — the FastAPI wrapper — is the prerequisite either channel needs, so
it's the right thing to land first.

---

## ✅ Task Execution Summary

### S6-T1: FastAPI Wrapper

**New files**: `src/api/__init__.py`, `src/api/main.py`

- `POST /v1/query` — the only real endpoint. Auth via `X-API-Key` header,
  resolved to a tenant with the Sprint 4 registry's new
  `authenticate_by_key()` (reverse lookup by key alone — an HTTP caller
  doesn't separately assert an airline, the key *is* the airline).
- Requests are scoped through `run_agent_for_tenant()` (Sprint 4/5's
  hard-to-bypass entry point) — same defense-in-depth as the Streamlit
  sidebar, not a parallel weaker path.
- Reuses `QueryValidator.validate_input()` for the same length/attack-
  pattern checks the Streamlit app applies, and a simple in-process
  sliding-window rate limiter (30 req/min per tenant) — separate from
  `src/security/rate_limiter.py`, which is hard-wired to
  `st.session_state` and not reusable outside Streamlit.
- `GET /health` reports whether the pipeline finished initializing.
- CORS wide open (`allow_origins=["*"]`) — the API key is the actual
  access control, not same-origin; needed since a website widget embedded
  on an airline's domain calls this from the browser.
- Run with: `uv run uvicorn src.api.main:app --port 8080`.

### S6-T2: Embeddable Widget Reference

**New file**: `static/widget.html`

- Self-contained HTML/CSS/JS chat bubble, no build step or external
  dependencies — a floating button that opens a small panel and POSTs to
  `/v1/query`.
- Deliberately a reference implementation for an airline's web team to
  adapt (swap `API_BASE`/`API_KEY`), not a polished shipped widget.

---

## Testing

- Full `pytest` suite: **72 tests pass** (66 prior + 6 new in
  `tests/test_api.py`).
- New tests cover: health check before pipeline ready, missing API key
  (422), wrong API key (401), valid key routes through
  `run_agent_for_tenant` with the correct tenant, a SpiceJet key can never
  resolve to the IndiGo tenant (mirrors Sprint 4's cross-tenant test), and
  the per-tenant rate limit trips at the configured threshold (429).
- Live-verified against the real Qdrant/OpenAI stack: started
  `uvicorn src.api.main:app`, confirmed `/health` reports ready, sent a
  real baggage-policy query and got a correct grounded answer with
  properly scored sources, confirmed a missing key returns 422 and a wrong
  key returns 401, then stopped the server.

## Bug Found & Fixed

`init_app_state()` built the graph and connected to Qdrant without ever
checking whether the collection actually had any vectors — unlike
`app.py`'s `init_pipeline()`, which raises immediately if
`store.stats()["total_vectors"] == 0`. Without that guard the API would
start cleanly against an empty collection and serve confidently-refused
(or worse, low-confidence hallucinated) answers indefinitely instead of
failing loud at startup. Added the same `RuntimeError` guard used in
`app.py`.

## Security Review

- API key resolution (`authenticate_by_key`) still uses
  `secrets.compare_digest` per candidate — unchanged from Sprint 4's
  constant-time comparison, just checked against every tenant instead of
  one.
- Rate limiting happens before the security validator and before any
  retrieval/LLM cost, same ordering as the Streamlit app.
- No secrets in `static/widget.html` beyond the placeholder string a
  deployer is expected to replace — never a real key.

## Carried Over / Next Steps

- Slack app and WhatsApp webhook integrations — deferred, see scope note.
- Rate limiter state is in-process (`dict` in `src/api/main.py`) — fine for
  a single `uvicorn` worker, but won't be shared across multiple workers or
  replicas. Needs Redis (or similar) before running with `--workers > 1`.
- No FastAPI-level auth for `/health` or CORS restriction beyond wildcard —
  acceptable for a read-only status endpoint, worth revisiting if this
  becomes internet-facing without a reverse proxy in front.

**Next Sprint**: Sprint 7 — Intelligence Upgrades (HyDE, conversation memory, Hindi)
