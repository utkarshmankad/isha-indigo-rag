# Shared rate limits across workers (hardening backlog)

## The gap

`_check_rate_limit` in `src/api/main.py` kept an in-memory dict
(`_query_times`) as its only state. That works within a single process,
but running more than one uvicorn/gunicorn worker on a host — the normal
way to use more than one CPU core — meant each worker had its own
independent counter. The configured `_QPM_LIMIT = 30` per tenant/IP was
actually `30 * worker_count` in practice, silently, with nothing to
indicate the limit wasn't what it looked like in code.

## The fix

`src/api/rate_limiter.py`'s `check_and_record(tenant_id, limit,
window_seconds=60)` replaces the in-memory dict with a SQLite-backed
counter (stdlib `sqlite3`, no new external dependency), in WAL mode for
real cross-process file locking on a shared disk. Every worker process on
the same host now reads and writes the same counter file, so the
configured limit is the actual limit regardless of worker count.

A rejected call is not recorded — a client already over the limit
retrying doesn't keep pushing its own window forward.

## What this does not solve

**Multi-host / multi-replica deployments.** SQLite's cross-process locking
works because the workers share a filesystem. If ISHA is ever deployed as
multiple replicas across different hosts (not the case today — this is a
single-process/single-host deployment per the reliability roadmap's
stated architecture), each host would again have its own independent
counter. A real distributed store (Redis, a shared database) would be
needed for that — same honest limitation already documented for this
codebase's other file-backed stores (`escalations.jsonl`,
`feedback.jsonl`, `query_log.jsonl`): fine for one host, swap for a real
store to survive replicas.

## Scope

This addresses one item from the hardening backlog. Evaluation/deployed
corpus alignment and separately measuring false answers vs. refusals are
separate, not yet started.
