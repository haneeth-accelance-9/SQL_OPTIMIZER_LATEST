"""
Abstract base class for all integration clients.

Every external-service client inherits from BaseIntegrationClient and gains:
  - Shared retry loop with linear back-off (_with_retry)
  - Structured error type (IntegrationError) with service / status_code / retryable
  - Consistent logging under optimizer.clients.<service_name>
  - Abstract contract: get_service_name() and health_check()
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

T = TypeVar("T")


@dataclass
class IntegrationError(Exception):
    """Structured error raised by any integration client."""

    service: str
    message: str
    status_code: Optional[int] = None
    retryable: bool = False

    def __str__(self) -> str:
        parts = [f"[{self.service}] {self.message}"]
        if self.status_code:
            parts.append(f"(HTTP {self.status_code})")
        if self.retryable:
            parts.append("[retryable]")
        return " ".join(parts)


class BaseIntegrationClient(ABC):
    """
    Abstract base all integration clients inherit from.

    Subclasses must implement:
      get_service_name() -> str
      health_check()     -> bool
    """

    MAX_RETRIES: int = 3
    RETRY_BACKOFF: float = 5.0  # seconds; multiplied by attempt number

    def __init__(self) -> None:
        self._log = logging.getLogger(
            f"optimizer.clients.{self.get_service_name()}"
        )

    @abstractmethod
    def get_service_name(self) -> str:
        """Short identifier used in logs and error messages."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the external service is reachable."""

    def _with_retry(self, fn: Callable[[], T]) -> T:
        """
        Call fn() with up to MAX_RETRIES attempts and linear back-off.

        On each failure the delay is: attempt_number * RETRY_BACKOFF seconds.
        After all retries are exhausted, raises IntegrationError(retryable=True).
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                if attempt == self.MAX_RETRIES:
                    break
                wait = attempt * self.RETRY_BACKOFF
                self._log.warning(
                    "Attempt %d/%d failed: %s — retrying in %.0fs",
                    attempt,
                    self.MAX_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)

        raise IntegrationError(
            service=self.get_service_name(),
            message=str(last_exc),
            retryable=True,
        ) from last_exc
