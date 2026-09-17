"""PII redaction for persisted query text (hardening backlog).

Query text (what a passenger typed) is stored verbatim in
`logs/query_log.jsonl` and `logs/escalations.jsonl`, and shown to admins
in the Streamlit escalation queue and the CLI summary tool
(`src/observability/logger.py`'s `print_summary`). A passenger asking
about their own booking commonly types their email or phone number into
the query itself ("can you email me at x@y.com" / "call me at
+91-9876543210") — nothing masked that before it was written to disk or
displayed.

This is a small, deterministic regex-based redaction, not PII detection
in the general sense — it only catches well-structured patterns (email
addresses, phone numbers) where the false-positive rate is low. Deliberately
does NOT attempt to redact things like PNR/booking references or names: a
6-character alphanumeric PNR pattern overlaps too many ordinary words and
would produce constant false positives, and free-text name detection needs
an NLU model this project doesn't have. Redact what can be redacted
reliably; don't pretend to catch everything.
"""
import re

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
# Matches phone numbers with an optional country code and 10+ digits,
# allowing spaces/hyphens between groups — e.g. +91 98765 43210,
# 0124-6173838, 9876543210. Deliberately requires 10+ digits so it
# doesn't catch shorter numeric sequences (fare amounts, flight numbers).
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\-\s]{8,14}\d)(?!\w)")


def redact_pii(text: str) -> str:
    """Replace email addresses and phone-number-shaped sequences in
    `text` with fixed placeholders. Safe to call on already-redacted or
    PII-free text (no-op in that case)."""
    if not text:
        return text
    text = _EMAIL_RE.sub("[REDACTED-EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED-PHONE]", text)
    return text
