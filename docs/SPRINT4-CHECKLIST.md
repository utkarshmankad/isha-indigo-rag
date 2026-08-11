# Sprint 4: Multi-Tenancy Core — Completion Checklist

**Status**: ✅ **COMPLETED**

**Scope note**: full SSO and per-tenant Qdrant collections (as sketched in the
original roadmap) are deferred — this sprint delivers the enforceable core:
a tenant registry with per-airline API keys, and isolation enforced at the
data-access layer (not just trusted to be applied by every caller). Separate
Qdrant collections per tenant is a later hardening step once there's more
than a handful of tenants; payload-filter isolation is the right tradeoff at
this scale, made hard to bypass rather than optional.

---

## ✅ Task Execution Summary

### S4-T1: Tenant Registry

**New files**: `src/tenancy/__init__.py`, `src/tenancy/registry.py`

- `TenantConfig` dataclass: `tenant_id`, `airline`, `display_name`, `api_key`.
- One tenant per known airline (`indigo`, `air_india`, `spicejet`), loaded
  from `TENANT_APIKEY_<AIRLINE>` env vars.
- If a key isn't configured, an ephemeral key is generated at process start
  and a warning logged — demo still works, but it's loud that this isn't a
  real deployment config (keys change every restart).
- `authenticate(airline, api_key)` does a constant-time comparison
  (`secrets.compare_digest`) scoped to a single tenant — a valid Air India
  key must not authenticate against IndiGo (tested).

### S4-T2: Isolation Enforced at the Data Layer

**Modified**: `src/embedding/vector_store.py`, `src/agent/graph.py`

- `QdrantVectorStore.query_for_tenant(tenant, ...)` always injects
  `airline_filter=[tenant.airline, "dgca"]` — there is no parameter to pass
  `None` and see everything, unlike the pre-existing `query()` method whose
  `airline_filter` is optional and trusts the caller.
- `run_agent_for_tenant(query, graph, tenant, ...)` in `graph.py` derives
  `airline` from the authenticated tenant, not a caller-supplied argument —
  closes the path where an upstream bug could pass the wrong airline string.
- Verified live against the real Qdrant collection: an IndiGo-tenant query
  returns only `indigo`/`dgca`-tagged chunks, never Air India or SpiceJet
  content, even for a query that explicitly asks about another airline's
  policy (see Testing).

### S4-T3: API-Key Gate in the UI

**Modified**: `app.py`

- Selecting a specific airline in the sidebar now requires a tenant API key
  before the chat accepts queries; "All Airlines" stays open (unauthenticated
  public multi-airline demo mode, unchanged from before this sprint).
- An unauthenticated tenant-scoped query is rejected before hitting
  retrieval/LLM cost, same pattern as the existing rate-limit check.

---

## Testing

- Full `pytest` suite: **58 tests pass** (51 prior + 7 new in
  `tests/test_tenancy.py`).
- New tests cover: correct-key auth, wrong-key rejection, cross-tenant key
  rejection (Air India key against IndiGo), unknown-airline rejection,
  empty-key rejection, `query_for_tenant` always passing the tenant's
  airline filter, and `run_agent_for_tenant` ignoring any caller-supplied
  airline.
- Live-verified against the real Qdrant collection (394 points, real
  OpenAI embeddings): `query_for_tenant(indigo_tenant, ...)` returned chunks
  tagged only `indigo`/`dgca` across a real query.
- Live end-to-end: asked the SpiceJet tenant about IndiGo's 6E Prime
  baggage allowance — correctly refused ("could not find this in the
  policy documents... contact SpiceJet") rather than leaking or
  hallucinating IndiGo policy.

## Bug Found & Fixed

`app.py`'s query-submission path still called the raw `run_agent(airline=...)`
even after the auth gate was added — the tenant object was validated and
displayed in the sidebar but never actually used to scope the query. Since
`airline` was already derived from the same sidebar selection that drove
authentication, this wasn't currently exploitable, but it defeated the
whole point of building `run_agent_for_tenant` as the hard-to-bypass entry
point: any future caller/refactor could reintroduce a raw `airline` string
into that codepath with no forcing function stopping it. Fixed by routing
tenant-authenticated queries through `run_agent_for_tenant(tenant)` instead.

## Security Review

- API keys compared with `secrets.compare_digest` (constant-time), never
  `==`.
- Keys never logged; only the env var name and airline are logged when a
  dev key is generated.
- Sidebar API key input uses `type="password"`.
- No secrets committed — all keys come from env vars, generated in-memory
  otherwise.

## Carried Over / Next Steps

- Full SSO/OAuth still deferred, per original roadmap.
- Self-serve document upload and per-tenant Qdrant collection provisioning
  (S5 scope) not started.
- `context_recall` (0.52 baseline from Sprint 3) still the pipeline's
  weakest metric — worth another look once retrieval changes land.

**Next Sprint**: Sprint 5 — Self-Serve Ingestion & Admin Basics
