# Onboarding a New Tenant (Airline)

Runbook for adding a new airline to ISHA. Assumes the multi-tenant core
(Sprint 4), self-serve ingestion (Sprint 5), and API layer (Sprint 6) are
deployed.

## 1. Add the airline to the tenant registry

`src/tenancy/registry.py`'s `KNOWN_AIRLINES` dict is currently a fixed set
(`indigo`, `air_india`, `spicejet`). Adding a new one:

```python
KNOWN_AIRLINES: dict[str, str] = {
    ...
    "new_airline": "New Airline (XX)",
}
```

## 2. Generate and set the tenant's API key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set as `TENANT_APIKEY_NEW_AIRLINE` in the deployment environment (repo
secrets for CI, your platform's env config for production). **Never commit
this value.** Without it, the registry generates an ephemeral key at
process start and logs a warning — fine for a local demo, unusable for a
real tenant (changes every restart).

## 3. Ingest the airline's policy documents

Two paths:

- **Bulk, before launch**: create `data/new_airline_documents.py` following
  the existing `DOCUMENTS = [...]` structure in `data/indigo_documents.py`,
  then `uv run python scripts/ingest.py --airline new_airline --reset`
  (or `--reset` on the shared collection if starting fresh).
- **Self-serve, after launch**: once the tenant is authenticated (Sprint 5),
  they can upload documents one at a time through the Streamlit sidebar's
  "Upload a policy document" panel, or via a script calling
  `src.ingestion.self_serve.ingest_document_for_tenant()` directly.

Self-serve uploads are searchable immediately via vector search but not
via BM25 keyword search until someone re-ingests the static document set —
see the caveat in `src/ingestion/self_serve.py`.

## 4. Verify isolation before going live

Run the isolation test suite and a manual live check:

```bash
uv run pytest tests/test_tenancy.py tests/test_pentest_isolation.py -q
```

Then confirm the new tenant's key only ever returns their own airline's
(plus DGCA) content — see `tests/test_pentest_isolation.py` for the pattern,
or query `/v1/query` directly with the new key and inspect `sources`.

## 5. Wire up the widget or API integration

- **Website widget**: copy `static/widget.html`, set `API_BASE` to the
  deployed API URL and `API_KEY` to the tenant's key, hand it to their web
  team.
- **Direct API**: `POST /v1/query` with `X-API-Key: <tenant-key>` and
  `{"query": "..."}`. See `src/api/main.py` for the full contract.
- **Admin metrics**: `GET /v1/admin/metrics` with the same key returns
  query volume, unanswered rate, avg confidence, and an estimated cost —
  same data the Streamlit sidebar shows, for API-only integrations
  (Slack, a website that never opens the Streamlit app).

## 6. Load-test before a real launch

```bash
uv run uvicorn src.api.main:app --port 8080 &
uv run python scripts/load_test.py --url http://localhost:8080 \
    --api-key <tenant-key> --requests 50 --concurrency 10
```

Confirms the 30 req/min per-tenant rate limit engages under real
concurrency and reports p50/p95 latency for the new tenant's document set.

## Known limitations (be upfront with the tenant)

- Shared Qdrant collection with payload-filter isolation, not a fully
  separate collection per tenant — fine at current scale, may need
  revisiting past a handful of tenants (see Sprint 4's scope note).
- Cost figures from `admin_metrics` are a flat per-query estimate, not
  measured OpenAI spend — real billing needs token-usage tracking added
  to `graph.generate_answer()` first.
- API rate limiter state is in-process — won't be shared across multiple
  `uvicorn` workers or replicas without adding Redis or similar.
