"""Shared, cross-process rate limiting (hardening backlog).

`_check_rate_limit` in `src/api/main.py` previously kept an in-memory
dict (`_query_times`) per process. Under multiple uvicorn/gunicorn worker
processes — the normal way to run more than one CPU core's worth of this
API on a single host — each worker had its own independent counter, so
the effective limit was `_QPM_LIMIT * worker_count`, not the configured
per-tenant/per-IP cap the code otherwise implies.

Backed by SQLite (stdlib, no new external dependency) in WAL mode, which
gives real cross-process file locking on a shared disk. This closes the
gap for multiple workers on one host. It does NOT solve multi-host/
multi-replica sharing — a real distributed store (Redis, a shared DB)
would be needed for that. Same honest limitation already documented for
this codebase's other file-backed stores (`escalations.jsonl`,
`feedback.jsonl`): fine for a single host, swap for a real store if this
needs to survive across replicas.
"""
import sqlite3
import time
from pathlib import Path

RATE_LIMIT_DB = "logs/rate_limits.sqlite"


def _connect() -> sqlite3.Connection:
    Path(RATE_LIMIT_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(RATE_LIMIT_DB, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS rate_events (tenant_id TEXT NOT NULL, ts REAL NOT NULL)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_events_tenant_ts ON rate_events(tenant_id, ts)")
    return conn


def check_and_record(tenant_id: str, limit: int, window_seconds: int = 60) -> bool:
    """Record this call for `tenant_id` and return whether it's within
    `limit` calls per `window_seconds`, counted across every process
    sharing this database file. When the limit is already reached, the
    call is NOT recorded — a client stuck over the limit doesn't keep
    pushing its own window forward just by retrying."""
    now = time.time()
    cutoff = now - window_seconds
    conn = _connect()
    try:
        conn.execute("DELETE FROM rate_events WHERE ts < ?", (cutoff,))
        count = conn.execute(
            "SELECT COUNT(*) FROM rate_events WHERE tenant_id = ? AND ts > ?", (tenant_id, cutoff),
        ).fetchone()[0]
        if count >= limit:
            return False
        conn.execute("INSERT INTO rate_events (tenant_id, ts) VALUES (?, ?)", (tenant_id, now))
        conn.commit()
        return True
    finally:
        conn.close()


def reset() -> None:
    """Test-only: wipe all recorded rate-limit events."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM rate_events")
        conn.commit()
    finally:
        conn.close()
