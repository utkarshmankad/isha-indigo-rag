# Canonical record + dense/lexical index consistency (S9-T1, Weeks 3-4 items 1 and 3)

Self-serve document add/update/delete (`src/ingestion/self_serve.py`) now goes
through `IndexManager` (`src/ingestion/index_manager.py`) instead of writing
to Qdrant directly. This closes the gap noted in `docs/SPRINT5-CHECKLIST.md`:
uploads previously reached the dense (Qdrant) index immediately but never
entered the in-process BM25 keyword index, so exact-keyword search silently
missed them. `IndexManager` now also writes a canonical record
(`src/documents/document_store.py`) — see `docs/CANONICAL-DOCUMENT-STORE.md`.

## Write ordering and compensation

Within a single running process, add/update/delete each touch three things —
the canonical record, the dense index, the lexical index — with best-effort compensation when a subsequent write fails:

- **Add**: canonical record first (durable, cheap, idempotent), then the
  dense write, then BM25. If the BM25 rebuild fails, both the dense write
  and the canonical record are rolled back and `IndexConsistencyError` is
  raised.
- **Update**: snapshot the previous dense chunks from Qdrant (including after
  a process restart), then write the record, dense chunks and BM25. Stable
  chunk IDs overwrite existing points. Cleanup deletes only obsolete IDs,
  never replacement IDs. If dense or BM25 publication fails, restore the
  dense snapshot and previous record, removing new-only points. BM25 builds
  its replacement before publishing it, so a failed build preserves its
  previous corpus. Compensating writes can themselves fail during an outage;
  this is not an atomic transaction.
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

## Approval status gates retrieval

`IndexManager.set_status(doc_id, status)` is a fourth, simpler operation:
a metadata-only transition (used for approve/reject/supersede), not a
content change. It patches the `status` field on the canonical record, on
every dense chunk (via `QdrantVectorStore.set_status_by_doc_id`, an
in-place payload patch — no vectors touched), and on the matching in-memory
BM25 chunks, all independently and idempotently (safe to retry; no
compensating rollback needed since each patch alone is harmless).

Both retrieval paths require `status=approved`. For compatibility, published
legacy corpus points (`visibility=public`) with absent/null status remain
searchable. Private uploads with absent/null status and all unknown status
values are excluded. Existing private uploads without status require explicit
admin approval before they become searchable. Invalid status transitions are
rejected before writes.

## Ownership checks

`update_document_for_tenant`, `delete_document_for_tenant`,
`approve_document_for_tenant`, and `reject_document_for_tenant` all require
the target `doc_id` to start with `SELFSERVE-{AIRLINE}-` for the calling
tenant's own airline (`OwnershipError` otherwise) — a tenant can only
modify/remove/approve/reject their own self-serve uploads, never another
tenant's uploads or a bundled policy document. The same check applies to
`supersedes` when creating a new document.
