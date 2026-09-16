# User feedback collection (Weeks 5-8, item 3c)

Before this item, there was no way for a passenger to say whether an
answer actually helped, and no aggregate signal for an admin beyond
retrieval-similarity confidence (which measures evidence match, not
answer usefulness — see `docs/CONFIDENCE.md`).

## What's new

- `src/feedback/collector.py`: `record_feedback(correlation_id, rating,
  comment=None)` — thumbs up/down plus an optional comment, keyed by the
  same `correlation_id` a query response already carries.
- `POST /v1/public/feedback/{correlation_id}` — public, unauthenticated,
  rate-limited, same trust model as the escalation contact-info endpoint
  (`docs/HUMAN-HANDOFF.md`): a `correlation_id` is a server-generated
  random UUID handed only to the client that made that exact query.
- `GET /v1/admin/feedback` — per-tenant summary (up/down counts,
  satisfaction rate) plus recent entries, scoped the same way every other
  admin endpoint is.
- The reference widget (`static/widget.html`) shows 👍/👎 under **every**
  answer, not just refusals (unlike the contact-info form, which only
  appears on a refusal).
- Streamlit admin sidebar shows the same summary and recent feedback.

## Why airline is looked up, not client-supplied

`record_feedback` never takes `airline` from the caller. It looks it up
server-side from the query log (`src/observability/logger.py`) by
`correlation_id` — the same source of truth the query itself was recorded
under. If the client could specify `airline` directly, it could attribute
feedback to any tenant it wanted, polluting another airline's satisfaction
numbers. This mirrors the same design decision already made for escalation
contact info.

## Overwrite, not append

A second feedback submission for the same `correlation_id` replaces the
first rather than adding a duplicate entry — a passenger who taps 👍 then
changes their mind to 👎 shouldn't be counted twice, once each way, in the
aggregate.

## Scope and limits

- **Per-answer, not per-conversation.** Feedback is tied to one query's
  `correlation_id`; there's no "rate this whole conversation" concept.
- **No fraud/abuse detection beyond the existing public rate limit.**
  Nothing stops repeat feedback on different correlation_ids from the same
  visitor beyond the shared `/v1/public/*` rate limiter.
- **Comments are free text, unmoderated.** They're stored and shown to the
  admin as-is (rendered as plain text, not HTML, in both the widget and
  Streamlit — no injection risk, but also no profanity/spam filtering).
- **JSONL file-backed**, same as `query_log.jsonl` and `escalations.jsonl`
  — fine for the current single-process deployment; would need a real
  store to survive across replicas.
