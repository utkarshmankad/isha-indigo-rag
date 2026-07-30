"""
Circuit breaker for outbound LLM API calls.

Standard three-state breaker (closed -> open -> half-open -> closed):
- CLOSED: calls pass through normally; failures are counted in a window.
- OPEN: calls are rejected immediately (fail fast) until recovery_timeout
  elapses, so a struggling upstream isn't hammered with more requests.
- HALF_OPEN: a single probe call is allowed through; success closes the
  breaker, failure re-opens it.
"""

import threading
import time
from enum import Enum

from src.observability.logging_config import get_logger

logger = get_logger("reliability.circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when a call is rejected because the breaker is open."""


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    def _maybe_transition_to_half_open(self) -> None:
        if (
            self._state == CircuitState.OPEN
            and self._opened_at is not None
            and time.time() - self._opened_at >= self.recovery_timeout_seconds
        ):
            self._state = CircuitState.HALF_OPEN
            logger.info("circuit breaker half-open", breaker=self.name)

    def _on_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            if self._state != CircuitState.CLOSED:
                logger.info("circuit breaker closed", breaker=self.name)
            self._state = CircuitState.CLOSED
            self._opened_at = None

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                logger.warning(
                    "circuit breaker opened", breaker=self.name, failure_count=self._failure_count,
                )

    def call(self, fn, *args, **kwargs):
        """Run fn(*args, **kwargs) through the breaker. Raises CircuitBreakerOpenError
        immediately if the breaker is open, without invoking fn."""
        current_state = self.state  # applies half-open transition if due
        if current_state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                f"circuit breaker '{self.name}' is open — failing fast"
            )

        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
