# Canonical document store (Weeks 3-4, item 1)

`src/documents/document_store.py` adds one durable, cross-process record per
self-serve document, independent of how that document is chunked for
retrieval.

## Why

Chunking is lossy — `chunk_document` splits and overlaps text for retrieval,
and until this item nothing kept the original, un-chunked document text or
its provenance. If a chunk boundary landed mid-sentence, or a tenant wanted
to know exactly what was uploaded, there was no way to recover it. There was
also nowhere to record an authoritative source URL, an effective date, or a
verified-as-current date for an uploaded document.

## What's stored

One record per `doc_id`:

| Field | Meaning |
|---|---|
| `doc_id` | Same id used for the chunks/dense points. |
| `title`, `category`, `airline` | Same tags as the chunk metadata. |
| `original_content` | The full, un-chunked text as uploaded. |
| `source_url` | Optional authoritative URL, if the tenant provided one. |
| `effective_date` | Optional date the policy takes effect, as entered by the tenant — not independently verified. |
| `verified_date` | Optional date someone confirmed the content is still current — not automatically maintained. |
| `uploaded_by` | The tenant id that created/last updated it. |
| `version` | Increments by 1 on each update via `build_record(..., previous=old_record)`. |
| `created_at`, `updated_at` | ISO timestamps. |

## Where it lives

Qdrant only — no Postgres is available in this environment (per the
reliability roadmap's stated constraint). Records live in their own
collection (`{QDRANT_COLLECTION}_documents`, e.g. `airline_kb_documents`),
one point per doc_id with a fixed 1-dimensional placeholder vector; this
collection is never searched by similarity, only fetched by `doc_id` or
scrolled/filtered by `airline`.

## Scope and limits

- **Self-serve uploads only.** The bundled static corpus (`data/*.py`)
  already has a source of truth — the files themselves, in git — so this
  store does not retroactively create records for them. Auditing the
  bundled corpus for stale/missing authoritative URLs and dates is separate
  Weeks 3-4 scope, not started.
- **Not a version history.** An update overwrites the record in place
  (bumping `version`); prior revisions are not kept queryable. Full version
  history and supersession tracking is separate, larger, not-yet-authorized
  scope (Weeks 3-4 item 3: upload review/approval, dedup, version history,
  supersession).
- **Not replayed into search at startup.** This store is durable and
  cross-process, but the dense/BM25 indexes it feeds via `IndexManager`
  (see `docs/INDEX-CONSISTENCY.md`) are not — a process restart does not yet
  re-derive dense/BM25 entries from these records. That replay step is
  separate, not-yet-authorized scope.
- **Dates are not verified.** `effective_date` and `verified_date` are
  free-text tenant input, not checked against anything.
