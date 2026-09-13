# Chat and administrator access

The browser widget calls `/v1/public/query` without a secret and only searches
published documents. Never embed staff or administrator keys in browser code.
The public endpoint fixes scope to public All Airlines; request fields cannot
select a private tenant. Its in-process global and client limits bound demo usage
(30 queries/minute per process globally). Use an edge/shared limiter before
running multiple replicas or increasing public traffic. Configure trusted proxies
at the server; do not accept arbitrary forwarded identity headers.

Staff queries use `/v1/query` with `X-API-Key` and `TENANT_APIKEY_<AIRLINE>`.
Administrator endpoints require `X-Admin-Key` and a distinct
`TENANT_ADMIN_APIKEY_<AIRLINE>`. Supported suffixes are INDIGO, AIR_INDIA, SPICEJET.
If an admin key is not configured, admin access is disabled; there is no fallback
to staff keys. Duplicate keys across roles/airlines are rejected during startup.

Streamlit has separate staff and administrator password fields. Metrics and
uploads require an administrator key. Configure both sets of secrets in the
server environment or Streamlit secrets; restart after rotation. Do not commit
real keys. Rotate any old staff keys previously placed in a published widget.

The document-visibility change must deploy before this public endpoint is enabled.
Future escalation administration must use get_admin_tenant as well. API keys are
a small-demo mechanism; per-user login and revocable sessions remain later work.
