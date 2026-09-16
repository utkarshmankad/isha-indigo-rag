# Clickable citations and widget conversation history (Weeks 5-8, item 2)

## Citations

`SourceOut` (`src/api/main.py`) now includes `source_url`, populated from
the retrieved chunk's `source_url` metadata. Two things had to be fixed for
this to actually work end to end:

- **Self-serve uploads never wrote `source_url` onto their chunks.**
  `ingest_document_for_tenant`/`update_document_for_tenant` accepted
  `source_url` (added in Weeks 3-4 item 1) and stored it on the canonical
  `DocumentStore` record, but `_build_chunks` never passed it into the `doc`
  dict handed to `chunk_document`, so the field was always `None` on the
  actual searchable/citable chunks. Fixed: `_build_chunks` now takes and
  forwards `source_url`/`effective_date`/`verified_date`.
- **Bundled corpus chunks already carry the field** (added in Weeks 3-4 item
  4's chunker change) but every bundled document is currently `None` there
  too — see `docs/BUNDLED-CORPUS-AUDIT.md`. A citation for a bundled
  document falls back to title + section until that content is reviewed and
  a real URL is entered.

`static/widget.html` renders each source as a list item under its answer:
a clickable link (`target="_blank"`, `rel="noopener noreferrer"`) when
`source_url` is present, otherwise plain text with title and section.
**ISHA does not verify that a `source_url` is correct** — it's exactly as
trustworthy as whoever entered it (a tenant admin for self-serve, nobody yet
for bundled documents).

## Widget conversation history

The API (`QueryRequest.history`) already accepted multi-turn history, but
the reference widget never sent it — every question was answered with no
memory of the conversation so far, even though the backend's HyDE/retrieval
pipeline (Sprint 7) was built to use it.

`static/widget.html` now:

- Keeps an in-memory `history` array of `{role, content}` turns, capped at
  10 turns and 2000 chars/turn to match `QueryRequest`'s own limits
  (`HistoryTurn.content` max length, `history` max length) — sending more
  than the API accepts would just 422.
- Sends `history` (everything before the current turn) on every
  `/v1/public/query` call.
- Persists history to `sessionStorage`, not `localStorage` — cleared when
  the tab closes, never shared across tabs/sessions, and never reaches
  ISHA's servers as anything other than the `history` field on the request
  the visitor is already making. A "Clear" button in the header resets it.

## Scope and limits

- This is the reference widget only (`static/widget.html`) — a real
  embedding airline would need to make the same two changes (send history,
  render `source_url`) in their own integration; this file is explicitly a
  reference implementation, not a shipped product.
- No fuzzy/broken-link checking on `source_url` — a stale or wrong URL a
  tenant entered will render as a clickable link exactly as entered.
- Widget history is per-browser-tab, not account-linked; there is no
  server-side conversation/session concept here (that would require a
  visitor identity, which doesn't exist for the anonymous public endpoint).
