# Measure false answers/refusals separately (hardening backlog)

## The gap

`admin_metrics.py`'s `unanswered_rate` combined two very different
outcomes into one number: a confidence-gated hard refusal (ISHA correctly
declined to answer — see `REFUSAL_FLOOR` in `src/agent/graph.py`) and a
"fallback" answer (retrieval was expanded or a stage degraded, but an
answer was still given). Those call for different responses from an
admin: a high refusal rate might mean the bundled corpus is missing
content the passengers are asking about; a high fallback rate might mean
retrieval quality needs work on answers that *are* being delivered.

Worse, neither number — nor `avg_confidence` — measures a **false
answer**: a confidently-given, non-refused answer that was simply wrong.
Confidence here is retrieval similarity, not answer-accuracy probability
(already documented honestly elsewhere in this codebase); ISHA has no
ground truth at runtime to know an answer was wrong on its own.

## The fix

`TenantMetrics` (`src/observability/admin_metrics.py`) now separates:

| Field | Meaning |
|---|---|
| `refused_count` / `refused_rate` | Confidence-gated hard refusals. |
| `fallback_only_count` / `fallback_only_rate` | Fallback-triggered but *not* refused — an answer was given. |
| `likely_false_answer_count` / `likely_false_answer_rate` | Non-refused answers that received a 👎 (thumbs-down) via `src/feedback/collector.py`, as a share of non-refused answers. |
| `unanswered_count` / `unanswered_rate` | Kept, unchanged in meaning (refused + fallback-only combined), for backward compatibility. |

`likely_false_answer_rate` is `None` (not `0.0`) when there are no
non-refused queries at all — distinct from "measured and found to be
zero."

## Why "likely," not "false"

This is a proxy signal, not a verified false-answer detector. A
thumbs-down can mean "factually wrong," "unhelpful," "not what I meant,"
or "correct but I'm frustrated for an unrelated reason" — there is no way
to distinguish these from a rating alone, and this project has no manual
answer-review pipeline to ground-truth them. The metric is honest about
that in its name and in its API/UI descriptions, the same way `confidence`
is already documented as similarity, not accuracy.

A passenger downvoting a *refusal* does not count here — there was no
answer to be false, so only non-refused queries are eligible.

## Where this shows up

- `GET /v1/admin/metrics` (`src/api/main.py`) now returns all six new
  fields alongside the existing ones.
- The Streamlit admin dashboard (`app.py`) shows Refused / Fallback-only /
  Likely-false-answers as three separate metrics with an explanatory
  caption, instead of one "Unanswered rate" number.

## Scope

This is the last item in the hardening backlog (reject missing embedding
keys, redact query logs, shared rate limits, align eval/deployed corpora,
this one). It does not add a manual review workflow for flagged answers,
does not attempt sentiment analysis on feedback comments, and does not
change refusal/confidence behavior itself — purely additive measurement.
