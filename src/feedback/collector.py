"""User feedback collection (Weeks 5-8, item 3c).

Lets a passenger rate an individual answer thumbs up/down (plus an
optional comment), identified by the same `correlation_id` their query
response already carried — same trust model as the escalation contact-info
endpoint (src/escalation/queue.py): a correlation_id is a server-generated
random UUID handed only to the client that made that exact request.

JSONL-backed, same pattern as query_log.jsonl and escalations.jsonl —
file-based is the right amount of infrastructure for the current
single-process deployment.

The airline a piece of feedback belongs to is never taken from the
client — it's looked up server-side from the query log by correlation_id,
the same source of truth the query itself was recorded under. A client
could otherwise claim any airline it wanted and pollute another tenant's
feedback view.
"""
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.observability.logger import read_logs
from src.observability.logging_config import get_logger

logger = get_logger("feedback.collector")

FEEDBACK_FILE = "logs/feedback.jsonl"
VALID_RATINGS = ("up", "down")
MAX_COMMENT_CHARS = 1000

_lock = threading.RLock()


class UnknownCorrelationIdError(ValueError):
    pass


def _lookup_airline(correlation_id: str) -> str | None:
    """Airline the query under this correlation_id was logged under, or
    None if no such query was ever logged (query logging failed, or the
    correlation_id is bogus)."""
    for entry in reversed(read_logs(n=10_000)):
        if entry.get("correlation_id") == correlation_id:
            return entry.get("airline", "all")
    return None


def _read_all() -> list[dict]:
    p = Path(FEEDBACK_FILE)
    if not p.exists():
        return []
    with _lock:
        lines = p.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def _rewrite(entries: list[dict]) -> None:
    temporary = None
    try:
        destination = Path(FEEDBACK_FILE)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=".feedback-", delete=False) as stream:
            temporary = Path(stream.name)
            for entry in entries:
                stream.write(json.dumps(entry) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def record_feedback(correlation_id: str, rating: str, comment: str | None = None) -> str:
    """Record (or overwrite) feedback for one correlation_id. A second
    submission for the same correlation_id replaces the first rather than
    adding a duplicate — a passenger changing their mind (thumbs up then
    down) shouldn't distort aggregate counts. Raises UnknownCorrelationIdError
    if no query was ever logged under this correlation_id, ValueError for
    an invalid rating/comment."""
    if rating not in VALID_RATINGS:
        raise ValueError(f"rating must be one of {VALID_RATINGS}")
    if comment is not None:
        comment = comment.strip() or None
    if comment and len(comment) > MAX_COMMENT_CHARS:
        raise ValueError(f"comment too long — maximum {MAX_COMMENT_CHARS} chars")

    airline = _lookup_airline(correlation_id)
    if airline is None:
        raise UnknownCorrelationIdError(f"No logged query found for correlation_id '{correlation_id}'.")

    feedback_id = str(uuid.uuid4())
    record = {
        "feedback_id": feedback_id,
        "correlation_id": correlation_id,
        "airline": airline,
        "rating": rating,
        "comment": comment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        Path(FEEDBACK_FILE).parent.mkdir(parents=True, exist_ok=True)
        entries = [e for e in _read_all() if e.get("correlation_id") != correlation_id]
        entries.append(record)
        _rewrite(entries)
    logger.info("feedback recorded", correlation_id=correlation_id, airline=airline, rating=rating)
    return feedback_id


def list_recent_feedback(airline: str, limit: int = 50) -> list[dict]:
    """Feedback for one tenant's airline only — never another tenant's,
    same isolation guarantee as the rest of the system."""
    entries = [e for e in _read_all() if e.get("airline") == airline]
    return entries[-limit:]


def compute_feedback_summary(airline: str) -> dict:
    entries = [e for e in _read_all() if e.get("airline") == airline]
    up = sum(1 for e in entries if e["rating"] == "up")
    down = sum(1 for e in entries if e["rating"] == "down")
    total = up + down
    return {
        "up": up,
        "down": down,
        "total": total,
        "satisfaction_rate": round(up / total, 4) if total else None,
    }
