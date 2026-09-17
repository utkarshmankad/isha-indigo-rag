# Redact sensitive query logs (hardening backlog)

## The gap

`logs/query_log.jsonl` and `logs/escalations.jsonl` store the passenger's
raw query text verbatim. A passenger asking about their own booking
commonly types their own contact details into the question itself
("can you email me at x@y.com" / "call me at +91-9876543210") — nothing
masked that before it hit disk. Both files are read by admin-facing
surfaces: the Streamlit escalation queue (`app.py`) prints `e['query']`
directly, and the CLI summary tool (`src/observability/logger.py`'s
`print_summary`) prints low-confidence query text.

## The fix

`src/observability/redaction.py`'s `redact_pii(text)` replaces email
addresses and phone-number-shaped digit sequences with fixed placeholders
(`[REDACTED-EMAIL]`, `[REDACTED-PHONE]`). Applied to the `query` field in
both `log_query` (`src/observability/logger.py`) and `enqueue_escalation`
(`src/escalation/queue.py`) — the two places raw query text is persisted.

## What this deliberately does not attempt

This is regex-based pattern matching on well-structured PII, not general
PII detection:

- **No PNR/booking-reference redaction.** A 6-character alphanumeric PNR
  pattern overlaps too many ordinary words (flight numbers, fare class
  codes, common short strings) — attempting it would produce constant
  false positives on legitimate query text.
- **No name detection.** Free-text name recognition needs an NLU/NER
  model this project doesn't have; a regex can't distinguish "my name is
  Priya" from any other sentence.
- **`response`, `comment`, and `contact_value` fields are untouched.**
  `contact_value` (email/phone left for follow-up, via
  `src/escalation/queue.py`'s `attach_contact_info`) is intentionally
  stored in the clear — it's the actual delivery mechanism, not something
  to mask. An admin's own written `response` and a passenger's feedback
  `comment` (`src/feedback/collector.py`) are not redacted in this pass;
  redacting admin-authored operational notes is a different judgment call
  than redacting raw passenger input and wasn't in scope here.
- **Not encryption or access control.** This reduces what ends up in the
  log file at all; it doesn't restrict who can read the file once
  written. File-level access control is unchanged.

## Scope

This addresses one item from the hardening backlog. Shared rate limits
across workers, evaluation/deployed corpus alignment, and separately
measuring false answers vs. refusals are separate, not yet started.
