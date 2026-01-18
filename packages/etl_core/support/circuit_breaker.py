"""Thread-safe circuit breaker utility for retryable workflows.

This class intentionally provides a stable compatibility surface used by older
code (pipeline_processing) while also exposing a modern `allow()` method used by
newer code (reporting_seeder). It accepts either `reset_seconds` or
`cooldown_seconds` as the cooldown parameter.
"""
from __future__ import annotations

import threading
import time
from typing import Optional
import logging

module_logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Thread-safe circuit breaker with backward-compatible API.

    Backwards-compatible attributes/methods (used by pipeline_processing tests):
      - consecutive_failures: int
      - last_failure_time: Optional[float]
      - cooldown_seconds: int
      - active: bool
      - record_failure(), record_success(), is_active()

    Newer method:
      - allow() -> bool
    """

    def __init__(
        self,
        max_failures: int,
        reset_seconds: Optional[int] = None,
        cooldown_seconds: Optional[int] = None,
        logger_obj: Optional[logging.Logger] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.max_failures = int(max_failures)
        # Accept either reset_seconds (new name) or cooldown_seconds (legacy)
        if reset_seconds is not None:
            self.cooldown_seconds = int(reset_seconds)
        elif cooldown_seconds is not None:
            self.cooldown_seconds = int(cooldown_seconds)
        else:
            self.cooldown_seconds = 60

        self._lock = threading.Lock()
        # Public-facing counters expected by older callers
        self.consecutive_failures = 0
        self.last_failure_time: Optional[float] = None
        self.active = False
        self._opened_at: Optional[float] = None
        # optional logger: prefer explicit logger arg, then logger_obj, then module_logger
        self._logger = logger or logger_obj or module_logger

    # Backwards-compatible methods expected by older callers/tests
    def record_failure(self) -> None:
        with self._lock:
            self.consecutive_failures += 1
            self.last_failure_time = time.time()
            self._logger.warning("CircuitBreaker: recorded failure (%d/%d)", self.consecutive_failures, self.max_failures)
            if self.consecutive_failures >= self.max_failures:
                if not self.active:
                    self.active = True
                    self._opened_at = time.time()
                    self._logger.error(
                        "Circuit breaker activated after %d consecutive failures",
                        self.max_failures,
                    )

    def record_success(self) -> None:
        with self._lock:
            if self.consecutive_failures > 0 or self.active:
                self._logger.info("CircuitBreaker: success observed, resetting state")
            self.consecutive_failures = 0
            self.last_failure_time = None
            self.active = False
            self._opened_at = None

    def is_active(self) -> bool:
        with self._lock:
            if self.active and self._opened_at is not None:
                # If cooldown has passed, reset and return False
                if (time.time() - self._opened_at) >= self.cooldown_seconds:
                    self._logger.info("CircuitBreaker: cooldown elapsed; resetting")
                    self.consecutive_failures = 0
                    self.last_failure_time = None
                    self.active = False
                    self._opened_at = None
                    return False
                return True
            return False

    # Newer compatibility surface used by reporting_seeder
    def allow(self) -> bool:
        """Return True if actions are allowed (breaker closed) else False.

        This mirrors the original implementation semantics: allow if consecutive
        failures < max_failures, or if cooldown elapsed.
        """
        with self._lock:
            if self.consecutive_failures < self.max_failures:
                return True
            if self._opened_at is None:
                return False
            if time.time() - self._opened_at >= self.cooldown_seconds:
                self._logger.info("Circuit breaker reset after cooldown")
                self.consecutive_failures = 0
                self._opened_at = None
                self.active = False
                return True
            return False

    # Backwards compatibility: provide alias for reset_seconds in some callers
    @property
    def reset_seconds(self) -> int:
        return self.cooldown_seconds
