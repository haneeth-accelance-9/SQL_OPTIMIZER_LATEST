"""
A2A agent endpoint client.

Replaces the inline urllib.request.urlopen() in:
  ai_report_generator.py  lines 1283-1293

The local-dev fallback logic (_build_local_agent_report_response) intentionally
stays in ai_report_generator.py — it is business logic, not transport logic.
This client only owns the HTTP transport layer.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

from optimizer.clients.base import BaseIntegrationClient, IntegrationError

logger = logging.getLogger(__name__)


@dataclass
class AgentClientConfig:
    endpoint: str = "http://localhost:8000"
    timeout: int = 120
    max_retries: int = 2

    @classmethod
    def from_django_settings(cls) -> "AgentClientConfig":
        from django.conf import settings as s
        return cls(
            endpoint=getattr(s, "AGENT_A2A_ENDPOINT", "http://localhost:8000").rstrip("/"),
            timeout=int(getattr(s, "AGENT_A2A_TIMEOUT", 120)),
            max_retries=int(getattr(s, "AGENT_A2A_MAX_RETRIES", 2)),
        )


class AgentClient(BaseIntegrationClient):
    """HTTP client for the A2A liscence-optimizer agent server."""

    _LOCAL_ENDPOINTS = frozenset({"http://localhost:8000", "http://127.0.0.1:8000"})

    def __init__(self, config: AgentClientConfig) -> None:
        super().__init__()
        self._config = config
        self.MAX_RETRIES = config.max_retries

    def get_service_name(self) -> str:
        return "a2a-agent"

    def is_local_dev(self) -> bool:
        """True when endpoint is the default local dev placeholder (not explicitly configured)."""
        explicitly_set = bool(os.environ.get("AGENT_A2A_ENDPOINT", "").strip())
        return not explicitly_set and self._config.endpoint in self._LOCAL_ENDPOINTS

    def health_check(self) -> bool:
        try:
            req = urllib.request.Request(
                f"{self._config.endpoint}/health", method="GET"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as exc:
            self._log.warning("A2A agent health check failed: %s", exc)
            return False

    def call_generate_report(
        self,
        *,
        usecase_id: str,
        records: list,
        strategy_results: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        llm_first: bool = True,
        llm_max_retries: Optional[int] = None,
        llm_timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        POST to {endpoint}/generate-report and return the parsed JSON response.
        Raises IntegrationError on any HTTP / network failure.
        """
        url = f"{self._config.endpoint}/generate-report"
        payload: Dict[str, Any] = {
            "usecase_id": usecase_id,
            "records": records,
            "strategy_results": strategy_results or {},
            "notes": notes,
            "llm_first": llm_first,
            "llm_max_retries": (
                llm_max_retries
                if llm_max_retries is not None
                else self._config.max_retries
            ),
            "llm_timeout_seconds": llm_timeout_seconds or min(self._config.timeout, 90),
        }

        def _call() -> Dict[str, Any]:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))

        try:
            return self._with_retry(_call)
        except IntegrationError:
            raise
        except Exception as exc:
            raise IntegrationError(
                service=self.get_service_name(),
                message=f"POST {url} failed: {exc}",
                retryable=True,
            ) from exc
