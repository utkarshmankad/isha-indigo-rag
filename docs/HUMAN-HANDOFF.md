# End-to-end human handoff: owner and response channel (Weeks 5-8, item 3a)

Before this item, the escalation queue (`src/escalation/queue.py`, S8-T2)
was one-directional: a refused/low-confidence query landed in a per-airline
queue, and an admin could only mark it resolved. There was no way to know
who was working an escalation, no way for the passenger to leave contact
info, and no record of what was actually communicated back.

## What's new

Every escalation record now carries:

| Field | Set by | Meaning |
|---|---|---|
| `contact_channel`, `contact_value` | passenger, via `POST /v1/public/escalations/{correlation_id}/contact` | How to reach the passenger who was refused (`email` or `phone`), if they chose to leave it. |
| `owner` | admin, via `POST /v1/admin/escalations/{id}/claim` | Free-text agent name/id — a "who's on it" marker, not a lock; re-claiming is allowed. |
| `response`, `responded_at` | admin, via `POST /v1/admin/escalations/{id}/resolve` (optional body) | What the agent told the passenger, and when. |

## The public contact-info endpoint

`POST /v1/public/escalations/{correlation_id}/contact` is intentionally
public and unauthenticated, matching `/v1/public/query`'s own trust model:
a `correlation_id` is a server-generated random UUID handed only to the
client that made that exact query — the same trust level as e.g. a
checkout session id. It only updates a still-*pending* escalation matching
that correlation_id; a resolved one can't be touched this way. Rate-limited
identically to the public query endpoint.

The reference widget (`static/widget.html`) shows an inline "leave your
email" prompt under any refused answer, using the `correlation_id` already
in that response.

## What this does not do

**There is still no outbound delivery mechanism.** No email/SMS
integration exists in this environment. Recording a `response` on an
escalation does not send anything to the passenger — an airline's own
support process has to actually reach out, using the `contact_channel`/
`contact_value` recorded here. This mirrors the same honest gap already
documented for Stripe billing delivery in the reliability roadmap notes:
the data model and workflow exist, the wire-up to a real notification
provider does not.

**`owner` is not a verified identity.** Admin authentication here is
airline-level (one shared admin key per tenant), not per-staff-member, so
`owner` is whatever free-text name the calling admin typed in — useful for
coordination, not an audit-grade assignment record.

## Scope

This closes the "owner and response channel" half of Weeks 5-8 item 3.
Hindi/Hinglish evaluation and passenger-facing user feedback (thumbs up/
down or similar) are separate, not yet started.
