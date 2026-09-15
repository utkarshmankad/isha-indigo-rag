# Dense/lexical index consistency (S9-T1)

Self-serve document add/update/delete (`src/ingestion/self_serve.py`) now goes
through `IndexManager` (`src/ingestion/index_manager.py`) instead of writing
to Qdrant directly. This closes the gap noted in `docs/SPRINT5-CHECKLIST.md`
and Weeks 3-4 planning: uploads previously reached the dense (Qdrant) index
immediately but never entered the in-process BM25 keyword index, so
exact-keyword search silently missed them.

## What IndexManager guarantees

Within a single running process:

- **Add**: the document lands in both the dense and lexical index, or
  neither. If the BM25 rebuild fails after the dense write succeeds, the
  dense write is deleted (rolled back) and `IndexConsistencyError` is
  raised.
- **Update**: the new content is written to the dense index first (as
  additional points, alongside the old ones), then swapped into BM25 in a
  single rebuild. If that BM25 step fails, the new dense points are deleted
  and the original document is left fully intact. Only after BM25 commits to
  the new content are the superseded old dense points deleted — best-effort;
  if that cleanup step itself fails, it's logged, not raised, because the
  document is already correctly indexed in both places.
- **Delete**: BM25 removal happens first (cheap, in-memory). If the
  following dense delete fails, the BM25 entries are restored so the
  document doesn't become keyword-invisible while still present in Qdrant.

## What it does not do

- **No cross-process persistence.** BM25 is rebuilt at process startup only
  from the static bundled `data/*.py` corpus (`ingest_all` → `build_graph`).
  A document added through `IndexManager` is fully consistent while the
  process is alive, but a restart drops it from BM25 (and, since nothing
  re-feeds Qdrant uploads into the startup ingest list either, effectively
  starts the self-serve corpus over). A canonical document store that
  persists and replays self-serve uploads at startup is separate, larger,
  not-yet-authorized scope (Weeks 3-4 planning).
- **No distributed transaction.** This is single-process, best-effort
  ordering with compensating deletes, not a two-phase commit. A process
  crash mid-operation can still leave one index ahead of the other; there is
  no reconciliation job to detect and repair that today.

## Ownership checks

`update_document_for_tenant` and `delete_document_for_tenant` both require
the target `doc_id` to start with `SELFSERVE-{AIRLINE}-` for the calling
tenant's own airline (`OwnershipError` otherwise) — a tenant can only
modify/remove their own self-serve uploads, never another tenant's uploads
or a bundled policy document.
