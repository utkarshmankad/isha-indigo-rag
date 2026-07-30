"""
Rate limiting utilities for query throttling.

Monitors query rate per session and globally to prevent API abuse
and cost escalation. Heuristic, in-process approach (no Redis needed):
per-session counters live in Streamlit's st.session_state, the global
counter lives in a module-level dict shared by every session in this
process.
"""

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from src.observability.logging_config import get_logger

logger = get_logger("security.rate_limiter")

# Default rate limits (configurable)
DEFAULT_SESSION_QPM = 30  # Queries Per Minute per session
DEFAULT_GLOBAL_QPM = 100  # Queries Per Minute globally
DEFAULT_SESSION_QPH = 500  # Queries Per Hour per session
DEFAULT_GLOBAL_QPH = 1000  # Queries Per Hour globally

_WINDOW_SECONDS = {"qpm": 60, "qph": 3600}

# Global (cross-session) counters, protected by a lock since Streamlit
# can serve multiple sessions concurrently in the same process.
_global_lock = threading.Lock()
_global_queries: list[float] = []


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    is_allowed: bool
    reason: str
    remaining_queries: int
    reset_time: datetime | None = None
    retry_after_seconds: int = 0


def _prune(timestamps: list[float], window_seconds: int) -> list[float]:
    cutoff = time.time() - window_seconds
    return [t for t in timestamps if t > cutoff]


class RateLimiter:
    """Throttle queries based on session and global limits."""

    @staticmethod
    def _get_session_state() -> dict:
        import streamlit as st

        if "session_id" not in st.session_state:
            st.session_state["session_id"] = str(uuid.uuid4())
        if "rate_limit_queries" not in st.session_state:
            st.session_state["rate_limit_queries"] = []
        return st.session_state

    @classmethod
    def _check_session(cls, limit_per_minute: int, limit_per_hour: int) -> RateLimitResult | None:
        """Returns a rejection RateLimitResult if the session limit is exceeded, else None."""
        state = cls._get_session_state()
        queries = state["rate_limit_queries"]

        queries_minute = _prune(queries, _WINDOW_SECONDS["qpm"])
        if len(queries_minute) >= limit_per_minute:
            retry_after = max(1, int(_WINDOW_SECONDS["qpm"] - (time.time() - min(queries_minute))))
            return RateLimitResult(
                is_allowed=False,
                reason=f"You're sending queries too quickly. Please wait {retry_after}s and try again.",
                remaining_queries=0,
                retry_after_seconds=retry_after,
            )

        queries_hour = _prune(queries, _WINDOW_SECONDS["qph"])
        if len(queries_hour) >= limit_per_hour:
            retry_after = max(1, int(_WINDOW_SECONDS["qph"] - (time.time() - min(queries_hour))))
            return RateLimitResult(
                is_allowed=False,
                reason=f"Hourly query limit reached. Please try again in {retry_after // 60} minutes.",
                remaining_queries=0,
                retry_after_seconds=retry_after,
            )

        return None

    @classmethod
    def _check_global(cls, limit_per_minute: int) -> RateLimitResult | None:
        """Returns a rejection RateLimitResult if the global limit is exceeded, else None."""
        with _global_lock:
            global _global_queries
            _global_queries = _prune(_global_queries, _WINDOW_SECONDS["qpm"])
            if len(_global_queries) >= limit_per_minute:
                return RateLimitResult(
                    is_allowed=False,
                    reason="Service is currently busy. Please try again in a moment.",
                    remaining_queries=0,
                    retry_after_seconds=60,
                )
        return None

    @classmethod
    def check_rate_limit(
        cls,
        session_qpm: int = DEFAULT_SESSION_QPM,
        session_qph: int = DEFAULT_SESSION_QPH,
        global_qpm: int = DEFAULT_GLOBAL_QPM,
    ) -> RateLimitResult:
        """
        Check whether a new query is allowed, and if so, record it.

        Returns:
            RateLimitResult with allowance status.
        """
        session_rejection = cls._check_session(session_qpm, session_qph)
        if session_rejection is not None:
            logger.warning("session rate limit exceeded", limit_qpm=session_qpm)
            return session_rejection

        global_rejection = cls._check_global(global_qpm)
        if global_rejection is not None:
            logger.warning("global rate limit exceeded", limit_qpm=global_qpm)
            return global_rejection

        # Allowed: record this query against both counters.
        now = time.time()
        state = cls._get_session_state()
        state["rate_limit_queries"].append(now)
        state["rate_limit_queries"] = _prune(state["rate_limit_queries"], _WINDOW_SECONDS["qph"])

        with _global_lock:
            global _global_queries
            _global_queries.append(now)
            _global_queries = _prune(_global_queries, _WINDOW_SECONDS["qpm"])

        remaining = max(0, session_qpm - len(_prune(state["rate_limit_queries"], _WINDOW_SECONDS["qpm"])))
        return RateLimitResult(
            is_allowed=True,
            reason="Query allowed",
            remaining_queries=remaining,
        )

    @classmethod
    def get_rate_limit_info(cls) -> dict[str, int]:
        """Get current rate limit status for display in the UI."""
        state = cls._get_session_state()
        session_used = len(_prune(state["rate_limit_queries"], _WINDOW_SECONDS["qpm"]))
        with _global_lock:
            global_used = len(_prune(_global_queries, _WINDOW_SECONDS["qpm"]))

        return {
            "session_remaining": max(0, DEFAULT_SESSION_QPM - session_used),
            "global_remaining": max(0, DEFAULT_GLOBAL_QPM - global_used),
            "config_session_qpm": DEFAULT_SESSION_QPM,
            "config_global_qpm": DEFAULT_GLOBAL_QPM,
        }


__all__ = ["RateLimiter", "RateLimitResult"]
