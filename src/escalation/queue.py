"""Human escalation queue for low-confidence / refused answers (S8-T2).

Enterprise buyers want a safety net for AI-facing customers — when ISHA
refuses (confidence below REFUSAL_FLOOR), the query lands here so a human
agent can review and follow up, instead of the passenger just hitting a
dead end. JSONL-backed, same pattern as query_log.jsonl — file-based is
the right amount of infrastructure for the current single-process
deployment; swap for a real queue (SQS, a DB table) if this needs to
survive across replicas.
"""
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.observability.logging_config import get_logger

logger = get_logger("escalation.queue")

ESCALATION_FILE = "logs/escalations.jsonl"

_lock = threading.Lock()


def enqueue_escalation(
    query: str, airline: str, confidence: float, correlation_id: str,
) -> str:
    """Add a refused/low-confidence query to the escalation queue. Returns
    the escalation ID. Never raises — a logging failure here must not
    affect the user-facing refusal response that triggered it.
    """
    escalation_id = str(uuid.uuid4())
    record = {
        "escalation_id": escalation_id,
        "correlation_id": correlation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "airline": airline,
        "confidence": round(confidence, 4),
        "status": "pending",
    }
    try:
        Path(ESCALATION_FILE).parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with open(ESCALATION_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        logger.info("query escalated", escalation_id=escalation_id, airline=airline, correlation_id=correlation_id)
    except Exception:
        logger.error("failed to write escalation record", correlation_id=correlation_id, exc_info=True)
    return escalation_id


def _read_all() -> list[dict]:
    p = Path(ESCALATION_FILE)
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


def list_pending_escalations(airline: str, limit: int = 50) -> list[dict]:
    """Pending escalations for one tenant's airline only — never another
    tenant's queries, same isolation guarantee as the rest of the system.
    """
    entries = [e for e in _read_all() if e.get("airline") == airline and e.get("status") == "pending"]
    return entries[-limit:]


def resolve_escalation(escalation_id: str, airline: str) -> bool:
    """Mark an escalation resolved. Scoped to `airline` — a tenant can only
    resolve their own escalations, verified before any write happens.
    Rewrites the whole file (JSONL has no in-place update); fine at the
    scale a file-backed queue is meant for.
    """
    entries = _read_all()
    found = False
    for e in entries:
        if e.get("escalation_id") == escalation_id and e.get("airline") == airline:
            e["status"] = "resolved"
            found = True
            break
    if not found:
        return False

    try:
        with _lock:
            with open(ESCALATION_FILE, "w", encoding="utf-8") as f:
                for e in entries:
                    f.write(json.dumps(e) + "\n")
    except Exception:
        logger.error("failed to write resolved escalation", escalation_id=escalation_id, exc_info=True)
        return False
    return True
