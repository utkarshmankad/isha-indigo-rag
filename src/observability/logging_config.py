"""
Structured JSON logging for ISHA.

All application logging should go through get_logger(__name__) instead of
print(). Log records are emitted as single-line JSON to stdout and to
logs/app.jsonl, with a redaction filter applied so secrets and PII never
land in persisted logs.
"""

import json
import logging
import re
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "app.jsonl"

# Credential/secret patterns. These are ALWAYS applied, to every field —
# no field is ever exempt from them, since no legitimate identifier
# contains an API key, bearer token, or email address.
_SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._-]+\b", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[REDACTED_EMAIL]"),
]

# Numeric PII patterns. Digit-shaped, so they can collide with opaque
# identifiers (a dash-separated hex UUID can look phone-like). Skipped
# only for _ID_KEYS fields whose value passes the strict _SAFE_ID_RE
# shape check below.
_NUMERIC_PII_PATTERNS = [
    (re.compile(r"\b\d{6}\d{6}\b"), "[REDACTED_PNR]"),
    (re.compile(r"\b[A-Z]{1,2}\d{6,8}\b"), "[REDACTED_PASSPORT]"),
    (re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,9}\b"), "[REDACTED_PHONE]"),
]

_REDACT_PATTERNS = _SECRET_PATTERNS + _NUMERIC_PII_PATTERNS

_SENSITIVE_KEYS = {
    "api_key", "openai_api_key", "qdrant_api_key", "password", "token",
    "authorization", "secret",
}

# Internally-generated trace identifiers (UUIDs, chunk IDs). These must
# survive numeric-PII redaction so requests stay greppable end-to-end.
_ID_KEYS = {"correlation_id", "chunk_id", "session_id", "request_id", "trace_id"}

# An ID-key value only skips numeric-PII redaction if it matches this
# shape: a single opaque token of alphanumerics/dash/underscore, no
# whitespace or punctuation. Anything else (free text, an email, a
# phone number someone stuffed into an ID field) falls through to the
# full pattern set rather than being trusted blindly.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _apply(patterns, text: str) -> str:
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return text


def redact_text(text: str) -> str:
    """Strip secrets/PII substrings out of a free-text log message."""
    return _apply(_REDACT_PATTERNS, text)


def _redact_value(key: str, value):
    if isinstance(value, str):
        key_lower = key.lower()
        if key_lower in _SENSITIVE_KEYS:
            return "[REDACTED]"
        if key_lower in _ID_KEYS and _SAFE_ID_RE.match(value):
            # Opaque identifier: still scrub credentials, but leave the
            # digit groups intact so the ID stays usable for tracing.
            return _apply(_SECRET_PATTERNS, value)
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, v) for v in value]
    return value


class RedactionFilter(logging.Filter):
    """Redacts secrets/PII from log message and structured 'extra' fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(str(record.getMessage()))
        record.args = ()
        extra = getattr(record, "extra_fields", None)
        if extra:
            record.extra_fields = {k: _redact_value(k, v) for k, v in extra.items()}
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _LoggerAdapter(logging.LoggerAdapter):
    """Allows logger.info("msg", correlation_id=..., latency_ms=...) style calls."""

    def process(self, msg, kwargs):
        extra_fields = {k: v for k, v in kwargs.items() if k not in ("exc_info", "stack_info", "stacklevel")}
        for k in list(kwargs.keys()):
            if k in extra_fields:
                kwargs.pop(k)
        kwargs["extra"] = {"extra_fields": extra_fields}
        return msg, kwargs


_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = JsonFormatter()
    redaction = RedactionFilter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(redaction)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction)

    root = logging.getLogger("isha")
    root.setLevel(logging.INFO)
    root.addHandler(stream_handler)
    root.addHandler(file_handler)
    root.propagate = False

    _configured = True


def get_logger(name: str) -> logging.LoggerAdapter:
    """Return a JSON-structured logger scoped under the 'isha' namespace."""
    _configure_root()
    base = logging.getLogger(f"isha.{name}")
    return _LoggerAdapter(base, {})
