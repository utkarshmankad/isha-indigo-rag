# Canonical document store, versioning, approval, dedup, supersession (Weeks 3-4, items 1 and 3)

`src/documents/document_store.py` adds one durable, cross-process current
record per self-serve document, an append-only archive of its prior
versions, and the approval-status/supersession fields that gate whether a
document is searchable.

## Why

Chunking is lossy — `chunk_document` splits and overlaps text for retrieval,
and originally nothing kept the original, un-chunked document text, its
provenance, or a review step before an upload went live. If a chunk
boundary landed mid-sentence, or a tenant wanted to know exactly what was
uploaded (or what it looked like before an edit), there was no way to
recover it. Uploads also went straight into search results with no chance
for anyone to review them first, and nothing caught an accidental duplicate
upload of the same content.

## What's stored

One current record per `doc_id`, plus an archived copy of each prior
version:

| Field | Meaning |
|---|---|
| `doc_id` | Same id used for the chunks/dense points. |
| `title`, `category`, `airline` | Same tags as the chunk metadata. |
| `original_content` | The full, un-chunked text as uploaded. |
| `content_hash` | `sha256(title + original_content)`, used for dedup. |
| `source_url` | Optional authoritative URL, if the tenant provided one. |
| `effective_date` | Optional date the policy takes effect, as entered by the tenant — not independently verified. |
| `verified_date` | Optional date someone confirmed the content is still current — not automatically maintained. |
| `status` | `pending` (default on create/update), `approved`, `rejected`, or `superseded`. |
| `supersedes` / `superseded_by` | Links to the doc_id this one replaces, and vice versa. |
| `uploaded_by` | The tenant id that created/last updated it. |
| `version` | Increments by 1 on each content update via `build_record(..., previous=old_record)`. A status-only change (approve/reject/supersede) does not bump this. |
| `created_at`, `updated_at` | ISO timestamps. |

## Approval workflow

Every new upload and every content update starts `status="pending"` and is
fully indexed (dense + lexical + canonical record) — an admin can inspect
exactly what was ingested — but is excluded from retrieval (see
`docs/INDEX-CONSISTENCY.md`'s status filter) until `approve_document_for_tenant`
flips it to `approved`. `reject_document_for_tenant` sets `rejected`, which
is permanent until a fresh approval; there is no separate re-review queue
for rejected documents.

## Dedup

Before creating a new document, `ingest_document_for_tenant` computes
`content_hash` and asks `DocumentStore.find_by_content_hash` whether the
same airline already has a non-`rejected`/non-`superseded` document with
identical (title, content). If so, it raises `DuplicateDocumentError` unless
the caller passes `force=True`. This is an exact-match check — near-
duplicates with minor wording differences are not caught.

## Supersession

Passing `supersedes=<old_doc_id>` to `ingest_document_for_tenant` marks the
old document `superseded` (excluded from retrieval, same as `rejected`, but
distinguishable in the record) and links `superseded_by` to the new doc_id,
once the new document is committed. Only a tenant's own self-serve
documents can be superseded this way (ownership-checked); a bundled
document cannot be superseded through this mechanism.

## Version history

`list_versions(doc_id)` returns every archived version plus the current
record, oldest first. `DocumentStore.put` (a full content replacement)
archives whatever was current before overwriting it; `DocumentStore.patch`
(a status/supersession-only change) does not create a new archived version
— it updates the current record in place.

## Where it lives

Qdrant only — no Postgres is available in this environment (per the
reliability roadmap's stated constraint). Current records live in
`{QDRANT_COLLECTION}_documents`; archived versions live in
`{QDRANT_COLLECTION}_documents_history`. Both use one point per record with
a fixed 1-dimensional placeholder vector; neither collection is ever
searched by similarity, only fetched/filtered by `doc_id`, `airline`,
`status`, or `content_hash`.

## Scope and limits

- **Self-serve uploads only.** The bundled static corpus (`data/*.py`)
  already has a source of truth — the files themselves, in git — so this
  store does not retroactively create records for them, and bundled chunks
  have no `status` field at all (treated as always-approved). Auditing the
  bundled corpus for stale/missing authoritative URLs and dates is separate
  Weeks 3-4 scope — see `scripts/audit_bundled_corpus.py`.
- **Not replayed into search at startup.** This store is durable and
  cross-process, but the dense/BM25 indexes it feeds via `IndexManager`
  are not — a process restart does not yet re-derive dense/BM25 entries
  from these records. That replay step is separate, not-yet-authorized
  scope.
- **Dates are not verified.** `effective_date` and `verified_date` are
  free-text tenant input, not checked against anything.
- **Dedup is exact-match only.** No fuzzy/semantic near-duplicate
  detection.
- **No multi-step review workflow.** Approval is a single tenant-admin
  action, not a multi-reviewer or role-gated process.
