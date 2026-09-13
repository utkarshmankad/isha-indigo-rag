# Local feature reconciliation

This merge preserves the four local commits be2132d, 97c68ae, 724672f and
7117248 in repository ancestry, integrating their billing, citations and human
escalation features with the reliability changes.

Escalation API and Streamlit administration require the separate tenant admin
credential. Staff chat credentials cannot list or resolve escalations. Queue
resolution holds a process lock across reading and writing and replaces the
file atomically; a failed replacement preserves the original pending records.
The JSONL queue still requires persistent local storage and a single writer
process. Multiple workers or replicas need shared transactional storage before
this can be treated as a durable support queue. Public refusals have no verified
customer contact or tenant owner and do not provide a promised human follow-up.

Citations retain source document IDs and expose a one-based chunk position in
the existing API `section` field. This is a passage position, not an official
policy section number. Newly ingested chunks carry this metadata for lexical
and vector retrieval alike; old records without it return no position.

Billing is optional and disabled without STRIPE_API_KEY and a per-tenant
STRIPE_CUSTOMER_ID_<TENANT_ID_UPPER> mapping to a Stripe customer ID. Only
successful, non-refused authenticated API answers schedule usage recording.
Public answers and infrastructure failures do not. Stripe failures are caught;
the current background hook is best effort, without durable retries or
reconciliation. It has unit coverage but has not been verified against live
Stripe or enabled for charging. Production billing needs a separately validated
meter/customer configuration and durable delivery before revenue reliance.
