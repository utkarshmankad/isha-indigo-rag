"""Human escalation queue for low-confidence / refused answers (S8-T2,
extended Weeks 5-8 item 3 with owner claiming, a response channel, and a
recorded response — the "end-to-end human handoff" piece of the roadmap).

Enterprise buyers want a safety net for AI-facing customers — when ISHA
refuses (confidence below REFUSAL_FLOOR), the query lands here so a human
agent can review and follow up, instead of the passenger just hitting a
dead end. JSONL-backed, same pattern as query_log.jsonl — file-based is
the right amount of infrastructure for the current single-process
deployment; swap for a real queue (SQS, a DB table) if this needs to
survive across replicas.

What "end-to-end" means here, and what it doesn't: a passenger can attach
contact info (email/phone) to their own refused query via correlation_id,
an admin can claim ownership of an escalation (so two agents don't work the
same one) and record a written response against it. There is still no
outbound delivery mechanism (no email/SMS integration exists in this
environment — see docs/CANONICAL-DOCUMENT-STORE.md's sibling honesty note
in RELIABILITY-PROGRESS.md about Stripe for the same kind of gap): recording
a response here does not send it anywhere. An airline's own support
tooling has to actually reach out using the recorded contact info.
"""
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.observability.logging_config import get_logger
from src.observability.redaction import redact_pii

logger = get_logger("escalation.queue")

ESCALATION_FILE = "logs/escalations.jsonl"
VALID_CONTACT_CHANNELS = ("email", "phone")
MAX_CONTACT_VALUE_CHARS = 200
MAX_RESPONSE_CHARS = 4000

_lock = threading.RLock()


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
        "query": redact_pii(query),
        "airline": airline,
        "confidence": round(confidence, 4),
        "status": "pending",
        "contact_channel": None,
        "contact_value": None,
        "owner": None,
        "response": None,
        "responded_at": None,
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


def _rewrite(entries: list[dict]) -> bool:
    """Atomically replace the whole file with `entries`. JSONL has no
    in-place update; fine at the scale a file-backed queue is meant for."""
    temporary = None
    try:
        destination = Path(ESCALATION_FILE)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=".escalations-", delete=False) as stream:
            temporary = Path(stream.name)
            for entry in entries:
                stream.write(json.dumps(entry) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        return True
    except Exception:
        logger.error("failed to write escalation queue", exc_info=True)
        return False
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def list_pending_escalations(airline: str, limit: int = 50) -> list[dict]:
    """Pending escalations for one tenant's airline only — never another
    tenant's queries, same isolation guarantee as the rest of the system.
    """
    entries = [e for e in _read_all() if e.get("airline") == airline and e.get("status") == "pending"]
    return entries[-limit:]


def attach_contact_info(correlation_id: str, channel: str, value: str) -> bool:
    """Let the passenger who triggered a refusal leave contact info for
    follow-up, looked up by the correlation_id their own query response
    already carried — never by escalation_id, which they never see. Public,
    unauthenticated by design (matches the public query endpoint this
    correlation_id came from); a correlation_id is a server-generated
    random UUID handed only to the client that made that exact request, so
    this is the same trust model as e.g. a checkout session id.

    Only affects a still-pending escalation for that correlation_id — a
    resolved one is done, and only the most recent matching entry is
    updated (there is at most one per correlation_id in practice, since
    each query gets a fresh one)."""
    if channel not in VALID_CONTACT_CHANNELS:
        raise ValueError(f"channel must be one of {VALID_CONTACT_CHANNELS}")
    value = value.strip()
    if not value:
        raise ValueError("value is required")
    if len(value) > MAX_CONTACT_VALUE_CHARS:
        raise ValueError(f"value too long — maximum {MAX_CONTACT_VALUE_CHARS} chars")

    with _lock:
        entries = _read_all()
        found = False
        for entry in entries:
            if entry.get("correlation_id") == correlation_id and entry.get("status") == "pending":
                entry["contact_channel"] = channel
                entry["contact_value"] = value
                found = True
        if not found:
            return False
        return _rewrite(entries)


def claim_escalation(escalation_id: str, airline: str, owner: str) -> bool:
    """An admin claims an escalation as theirs to work, scoped to `airline`
    like every other escalation operation. Re-claiming (same or different
    owner) is allowed — this is a "who's on it" marker, not a lock."""
    with _lock:
        entries = _read_all()
        found = False
        for entry in entries:
            if entry.get("escalation_id") == escalation_id and entry.get("airline") == airline:
                entry["owner"] = owner
                found = True
                break
        if not found:
            return False
        return _rewrite(entries)


def resolve_escalation(escalation_id: str, airline: str, response: str | None = None) -> bool:
    """Mark an escalation resolved, scoped to `airline` — a tenant can only
    resolve their own escalations, verified before any write happens.
    Optionally records the human agent's written response and when it was
    recorded; recording it here does not send it anywhere (see module
    docstring) — that's on the airline's own follow-up process using the
    contact info attached via `attach_contact_info`."""
    if response is not None and len(response) > MAX_RESPONSE_CHARS:
        raise ValueError(f"response too long — maximum {MAX_RESPONSE_CHARS} chars")

    with _lock:
        entries = _read_all()
        found = False
        for entry in entries:
            if entry.get("escalation_id") == escalation_id and entry.get("airline") == airline:
                entry["status"] = "resolved"
                if response is not None:
                    entry["response"] = response
                    entry["responded_at"] = datetime.now(timezone.utc).isoformat()
                found = True
                break
        if not found:
            return False
        return _rewrite(entries)
