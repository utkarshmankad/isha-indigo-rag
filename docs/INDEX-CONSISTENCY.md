# Canonical record + dense/lexical index consistency (S9-T1, Weeks 3-4 item 1)

Self-serve document add/update/delete (`src/ingestion/self_serve.py`) now goes
through `IndexManager` (`src/ingestion/index_manager.py`) instead of writing
to Qdrant directly. This closes the gap noted in `docs/SPRINT5-CHECKLIST.md`:
uploads previously reached the dense (Qdrant) index immediately but never
entered the in-process BM25 keyword index, so exact-keyword search silently
missed them. `IndexManager` now also writes a canonical record
(`src/documents/document_store.py`) — see `docs/CANONICAL-DOCUMENT-STORE.md`.

## What IndexManager guarantees

Within a single running process, add/update/delete each touch three things —
the canonical record, the dense index, the lexical index — landing in all of
them or none:

- **Add**: canonical record first (durable, cheap, idempotent), then the
  dense write, then BM25. If the BM25 rebuild fails, both the dense write
  and the canonical record are rolled back and `IndexConsistencyError` is
  raised.
- **Update**: canonical record overwritten first; then new content is
  written to the dense index (as additional points, alongside the old
  ones); then swapped into BM25 in a single rebuild. If that BM25 step
  fails, the new dense points are deleted and the previous canonical record
  is restored — the original document is left fully intact. Only after BM25
  commits to the new content are the superseded old dense points deleted —
  best-effort; if that cleanup step itself fails, it's logged, not raised,
  because the canonical record, BM25 and the new dense points are already
  correctly committed.
- **Delete**: BM25 removal happens first (cheap, in-memory). If the
  following dense delete fails, the BM25 entries are restored and the
  canonical record is left untouched. Only once the dense delete succeeds is
  the canonical record deleted.

## What it does not do

- **No cross-process persistence for the search indexes.** BM25 is rebuilt
  at process startup only from the static bundled `data/*.py` corpus
  (`ingest_all` → `build_graph`); the dense index only reflects whatever is
  already in Qdrant. A document added through `IndexManager` is fully
  consistent across all three stores while the process is alive, but a
  restart drops it from BM25 (and the startup ingest list doesn't re-feed
  Qdrant uploads into it either). The canonical record itself **does**
  survive a restart — it's the one durable, cross-process piece here — but
  nothing yet replays canonical records back into BM25/dense at startup.
  That replay step is separate, not-yet-authorized scope.
- **No distributed transaction.** This is single-process, best-effort
  ordering with compensating deletes/restores, not a two-phase commit. A
  process crash mid-operation can still leave these three stores
  inconsistent with each other; there is no reconciliation job to detect and
  repair that today.

## Ownership checks

`update_document_for_tenant` and `delete_document_for_tenant` both require
the target `doc_id` to start with `SELFSERVE-{AIRLINE}-` for the calling
tenant's own airline (`OwnershipError` otherwise) — a tenant can only
modify/remove their own self-serve uploads, never another tenant's uploads
or a bundled policy document.
