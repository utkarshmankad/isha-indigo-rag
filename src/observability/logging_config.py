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

# Patterns for values that must never appear in logs.
_REDACT_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._-]+\b", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{6}\d{6}\b"), "[REDACTED_PNR]"),
    (re.compile(r"\b[A-Z]{1,2}\d{6,8}\b"), "[REDACTED_PASSPORT]"),
    # Matches phone-number-shaped digit runs. Not UUID-safe on its own (a
    # dash-separated hex ID can superficially look phone-like) — the
    # _ID_KEYS whitelist below is what actually protects correlation IDs
    # and similar identifiers from being mangled by this pattern.
    (re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,9}\b"), "[REDACTED_PHONE]"),
]

_SENSITIVE_KEYS = {
    "api_key", "openai_api_key", "qdrant_api_key", "password", "token",
    "authorization", "secret",
}

# Internally-generated trace identifiers: never PII/secrets, must survive
# redaction untouched so requests stay greppable end-to-end.
_ID_KEYS = {"correlation_id", "chunk_id", "session_id", "request_id", "trace_id"}


def redact_text(text: str) -> str:
    """Strip secrets/PII substrings out of a free-text log message."""
    redacted = text
    for pattern, replacement in _REDACT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _redact_value(key: str, value):
    if isinstance(value, str):
        key_lower = key.lower()
        if key_lower in _SENSITIVE_KEYS:
            return "[REDACTED]"
        if key_lower in _ID_KEYS:
            return value
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
