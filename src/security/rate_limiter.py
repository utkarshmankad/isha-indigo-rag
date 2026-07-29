"""
Rate limiting utilities for query throttling.

Monitors query rate per session and globally to prevent API abuse
and cost escalation.
"""

import time
from datetime import datetime, timedelta
from typing import Literal

from typing import Optional
from dataclasses import dataclass, field


@dataclass
class RateLimitExceeded:
    """Result when rate limit is exceeded."""

    is_rate_limited: bool = True
    required_limit_reached: int
    limit_window: int
    retry_after: int  # seconds
    message: str


# Default rate limits (configurable)
DEFAULT_SESSION_QPM = 30  # Queries Per Minute per session
DEFAULT_GLOBAL_QPM = 100  # Queries Per Minute globally
DEFAULT_SESSION_QPH = 500  # Queries Per Hour per session
DEFAULT_GLOBAL_QPH = 1000  # Queries Per Hour globally

# Configuration
MAX_QUERY_TIME_COST = 2.0  # Maximum token cost for a query (increases if no limit)


@dataclass
class RateLimitResult:
    """Result of rate limit check."""

    is_allowed: bool
    reason: str
    remaining_queries: int
    reset_time: datetime | None = None
    retry_after_seconds: int = 0


class RateLimiter:
    """Throttle queries based on session and global limits."""

    @staticmethod
    def _get_session_key() -> str:
        """
        Generate a unique key for the current Streamlit session.

        Returns:
            Session identifier string.
        """
        import streamlit as st

        session_id = st.session_state.get("session_id", "unknown")
        return f"session:{session_id}"

    @staticmethod
    def _get_global_key() -> str:
        """
        Generate a unique key for the current client.

        In a web service, this would use the actual IP address.
        For Streamlit community cloud, we track globally.

        Returns:
            Global identifier string.
        """
        return "global"

    @staticmethod
    def _get_rate_limit_key(limit_type: str, key: str) -> str:
        """
        Build Redis-compatible key name.

        Args:
            limit_type: Type of limit ("session" or "global")
            key: The actual identifier

        Returns:
            Storage key
        """
        return f"rate_limit:{limit_type}:{key}"

    @staticmethod
    def _get_invalidated_prefix(limit_type: str, key: str) -> str:
        """
        Get Redis key pattern to invalidate entries.

        Args:
            limit_type: Type of limit ("session" or "global")
            key: The identifier

        Returns:
            Redis key pattern string
        """
        return f"rate_limit:{limit_type}:{key}*"

    @classmethod
    def acquirer(cls, limit_type: Literal["session", "global"], limit_per_window: int) -> bool:
        """
        Acquire permission to make a query (one-time check).

        This is a heuristic approach that approximates rate limiting
        without needing a persistent backend like Redis.

        Args:
            limit_type: Type of limit to check ("session" or "global")
            limit_per_window: Max queries per time window

        Returns:
            True if allowed, False if rate limited
        """
        session_id = session_state.get("session_id", "unknown")

        current_time = time.time()
        key_prefix = cls._get_rate_limit_key(limit_type, cls._get_session_key() if limit_type == "session" else cls._get_global_key())

        # Initialize rate limit tracking in session state
        if f"rate_limit_{limit_type}" not in session_state:
            session_state[f"rate_limit_{limit_type}"] = {
                "queries": [],
                "limit": limit_per_window,
            }

        limits = session_state[f"rate_limit_{limit_type}"]

        # Remove old queries outside time window
        window_seconds = 60  # Default: 1 minute
        if limit_per_window > 100:
            window_seconds = 3600  # Default: 1 hour for higher limits

        now = datetime.now()
        limits["queries"] = [
            q_time
            for q_time in limits["queries"]
            if (now - datetime.fromtimestamp(q_time)).total_seconds() < window_seconds
        ]

        # Check if limit reached
        if len(limits["queries"]) >= limit_per_window:
            # Calculate retry time based on oldest query in window
            oldest_query = min(limits["queries"])
            oldest_dt = datetime.fromtimestamp(oldest_query)
            time_until_reset = (oldest_dt + timedelta(seconds=window_seconds)) - now
            retry_after = max(1, int(time_until_reset.total_seconds()))

            return False

        # Increment query counter
        limits["queries"].append(current_time)

        return True

    @classmethod
    def check_rate_limit(cls) -> RateLimitResult:
        """
        Check if query is allowed based on configured limits.

        Returns:
            RateLimitResult with allowance status.
        """
        import streamlit.session_state as session_state

        # Get session ID for tracking
        if "session_id" not in session_state:
            session_state["session_id"] = f"{time.time()}:{id(streamlit.runtime.streamlit_instance)."()"

        session_id = session_state["session_id"]

        # Check individual session rate limits
        session_qpm = DEFAULT_SESSION_QPM
        session_qph = DEFAULT_SESSION_QPH

        session_allowed = cls.acquirer("session", session_qpm)

        # If session limit exceeded, return information
        if not session_allowed:
            # For heuristic rate limiting, we'd return how many more queries can be made
            remaining = max(0, session_qpm - len(session_state["rate_limit_session"]["queries"]))
            return RateLimitResult(
                is_allowed=False,
                reason=f"Session rate limit exceeded. Please wait {60 - (time.time() % 60)} more seconds.",
                remaining_queries=remaining,
                retry_after_seconds=60,
            )

        # Check global rate limit for cost protection
        global_allowed = cls.acquirer("global", DEFAULT_GLOBAL_QPM)

        if not global_allowed:
            return RateLimitResult(
                is_allowed=False,
                reason="Global rate limit exceeded. Service is currently busy.",
                remaining_queries=0,
                retry_after_seconds=60,
            )

        # Query allowed
        session_remaining = session_qpm - len(session_state["rate_limit_session"]["queries"])
        return RateLimitResult(
            is_allowed=True,
            reason="Query allowed",
            remaining_queries=session_remaining,
            reset_time=None,
        )

    @classmethod
    def get_rate_limit_info(cls) -> dict[str, int]:
        """
        Get current rate limit status.

        Returns:
            Dictionary with current status.
        """
        import streamlit.session_state as session_state

        # Initialize
        if "rate_limit_session" not in session_state:
            session_state["rate_limit_session"] = {"queries": [], "limit": DEFAULT_SESSION_QPM}
        if "rate_limit_global" not in session_state:
            session_state["rate_limit_global"] = {"queries": [], "limit": DEFAULT_GLOBAL_QPM}

        # Calculate remaining
        session_remaining = max(
            0,
            session_state["rate_limit_session"]["limit"]
            - len(session_state["rate_limit_session"]["queries"]),
        )
        global_remaining = max(
            0,
            session_state["rate_limit_global"]["limit"]
            - len(session_state["rate_limit_global"]["queries"]),
        )

        return {
            "session_remaining": session_remaining,
            "global_remaining": global_remaining,
            "config_session_qpm": DEFAULT_SESSION_QPM,
            "config_global_qpm": DEFAULT_GLOBAL_QPM,
        }


__all__ = ["RateLimiter", "RateLimitResult"]