"""
Dependency health checks for ISHA.

Each check function returns a dict with keys: status ("ok"|"error"),
and optional detail/latency_ms. Used by the /health endpoint.
"""

import os
import time

from src.observability.logging_config import get_logger

logger = get_logger("observability.health")


def check_openai_key() -> dict:
    if os.environ.get("OPENAI_API_KEY"):
        return {"status": "ok"}
    return {"status": "error", "detail": "OPENAI_API_KEY not set"}


def check_qdrant() -> dict:
    url = os.environ.get("QDRANT_URL")
    api_key = os.environ.get("QDRANT_API_KEY")
    if not url or not api_key:
        return {"status": "error", "detail": "QDRANT_URL/QDRANT_API_KEY not set"}

    t0 = time.time()
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=url, api_key=api_key)
        client.get_collections()
        latency_ms = int((time.time() - t0) * 1000)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as e:
        logger.warning("qdrant health check failed", error=str(e))
        return {"status": "error", "detail": "could not reach Qdrant"}


def check_log_dir_writable() -> dict:
    try:
        from src.observability.logging_config import LOG_DIR

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        probe = LOG_DIR / ".health_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return {"status": "ok"}
    except Exception as e:
        logger.warning("log dir health check failed", error=str(e))
        return {"status": "error", "detail": "log directory not writable"}


def run_health_checks() -> dict:
    checks = {
        "openai": check_openai_key(),
        "qdrant": check_qdrant(),
        "log_storage": check_log_dir_writable(),
    }
    healthy = all(c["status"] == "ok" for c in checks.values())
    return {"status": "ok" if healthy else "degraded", "checks": checks}
