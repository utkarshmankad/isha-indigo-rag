# Sprint 5: Self-Serve Ingestion & Admin Basics — Completion Checklist

**Status**: ✅ **COMPLETED**

**Branch note**: stacked on `sprint-4-multi-tenancy` (not `main`) — this
sprint's UI gating and per-tenant metrics depend on the tenant registry
(`src/tenancy/registry.py`) added in Sprint 4, which isn't on `main` yet.
Merge order: Sprint 4 → Sprint 5.

---

## ✅ Task Execution Summary

### S5-T1: Self-Serve Document Upload

**New file**: `src/ingestion/self_serve.py`

- `ingest_document_for_tenant(tenant, title, content, category, vector_store)`
  reuses the existing chunk → embed → upsert pipeline
  (`chunker.chunk_document`, `embedder.embed_chunks`,
  `vector_store.upsert`), building a single ad-hoc `doc` dict.
- The `airline` tag comes from `tenant.airline`, never from a caller-supplied
  string — a tenant can't tag a document into another airline's scope
  (same defense-in-depth pattern as `run_agent_for_tenant` from Sprint 4).
- `validate_upload()` rejects empty titles, too-short content (<50 chars),
  and oversized content (>50k chars) before spending any embedding cost.
- Wired into the sidebar (`app.py`) behind the Sprint 4 tenant auth gate —
  an expander with title/category/text inputs and an "Ingest document"
  button.

### S5-T2: Admin Dashboard v1

**New file**: `src/observability/admin_metrics.py`

- `compute_tenant_metrics(airline)` reads the existing query log
  (`src/observability/logger.py:read_logs`) filtered to one airline, returns
  query volume, unanswered rate, avg confidence, and an estimated cost.
- **Cost is a flat per-query estimate** (`$0.0015`), not measured spend — the
  OpenAI call in `graph.py` doesn't capture token usage today, so a real
  number needs that instrumentation first. Documented in the module
  docstring rather than presented as precise.
- Surfaced in the sidebar as a tenant-gated expander, next to the upload UI.

### S5-T3: Query Log Tenant Tagging

**Modified**: `src/observability/logger.py`, `src/agent/graph.py`

- `log_query()` gained `airline` and `refused` fields — previously the log
  had no way to attribute a query to a tenant or distinguish "answered
  poorly" from "explicitly refused" (the Sprint 3 confidence-floor path).
  Both new params default to backward-compatible values (`"all"`, `False`)
  so old call sites don't break.
- Both `generate_node` call sites in `graph.py` (refusal short-circuit and
  normal generation) now pass these through.

---

## Testing

- Full `pytest` suite: **66 tests pass** (58 prior + 8 new: 5 in
  `tests/test_self_serve.py`, 3 in `tests/test_admin_metrics.py`).
- `test_self_serve.py` covers: upload validation (empty title, too-short
  content, valid input), and — the key isolation property — that a
  document ingested by the SpiceJet tenant is tagged `airline=spicejet`
  regardless of what's in the document text, mirroring the Sprint 4
  cross-tenant tests.
- `test_admin_metrics.py` covers: metrics scoped to one airline don't leak
  another tenant's queries, and the empty-log case doesn't divide by zero.
- Live-verified against the real Qdrant collection: uploaded a test "Pet
  Travel Policy" document as the IndiGo tenant, confirmed it was the
  top-scoring hit (0.73) for a matching query via `query_for_tenant`, then
  deleted the test points to leave the collection at its original 394
  vectors.

## Bug Found & Fixed

The upload success message originally said "Restart the app to rebuild the
search index with this document" — checked this claim against the live
test and it was wrong on both counts. Semantic (vector) search picks up a
self-serve upload immediately, no restart needed, because retrieval queries
Qdrant directly. The BM25 keyword index, meanwhile, is cached by a hash of
the *static* `data/*.py` document set (`hybrid_search.BM25Index`) and has
no path to a Qdrant-only upload at all — restarting the app doesn't add it
there either, since `app.py`'s `init_pipeline()` only ever chunks
`data/*.py`. Fixed the message to state the real behavior: available
immediately for semantic search, permanently absent from exact-keyword
matching until a maintainer re-ingests it into the static set. Documented
the same caveat in `self_serve.py`'s module docstring.

## Security Review

- Upload content length capped (50k chars) — bounds embedding cost and
  payload size per request.
- No new secrets; tenant auth reused unchanged from Sprint 4.
- Admin metrics only ever read the tenant's own airline-filtered slice of
  the query log — no endpoint exposes another tenant's log entries.

## Carried Over / Next Steps

- Per-tenant Qdrant collection provisioning (vs. today's shared collection
  with payload-filter isolation) — still deferred, per the Sprint 4 scope
  note; revisit once tenant count grows past a handful.
- Real cost tracking needs token-usage capture added to
  `graph.generate_answer()` before `admin_metrics`'s cost figure can be
  trusted for anything billing-related.
- BM25 index has no path to self-serve uploads at all (see bug note above)
  — worth a follow-up if keyword-exact matching on uploaded docs turns out
  to matter in practice.

**Next Sprint**: Sprint 6 — API & Channel Integrations
