"""
Grafana / Mimir Prometheus API client.

Replaces inline httpx.Client() usage in:
  fetch_grafana_metrics.py    line 379   (hourly sync command)
  explore_grafana_metrics.py  line 67    (discovery helper command)

GRAFANA_METRICS registry is moved here from fetch_grafana_metrics.py so both
commands share one canonical definition of PromQL expressions and units.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from optimizer.clients.base import BaseIntegrationClient, IntegrationError

logger = logging.getLogger(__name__)


# ── Metric registry ───────────────────────────────────────────────────────────
# Canonical source for all PromQL expressions used by the fetch command.
# Previously duplicated in fetch_grafana_metrics.py; now lives here.
#
# Format: metric_name → (PromQL expression, unit string)

GRAFANA_METRICS: Dict[str, Tuple[str, str]] = {
    "connections": (
        "mssql_connections",
        "",
    ),
    "batch_requests": (
        "rate(mssql_batch_requests_total[5m])",
        "req/s",
    ),
    "os_memory_available_gib": (
        "mssql_os_memory / 1073741824",
        "GiB",
    ),
    "memory_manager_total_gib": (
        "mssql_server_total_memory_bytes / 1073741824",
        "GiB",
    ),
    "page_life_expectancy": (
        "mssql_page_life_expectancy_seconds",
        "s",
    ),
    "running_queries": (
        "mssql_running_queries",
        "",
    ),
    "memory_utilization_pct": (
        "mssql_memory_utilization_percentage",
        "%",
    ),
    "database_size_mib": (
        "mssql_database_size_bytes / 1048576",
        "MiB",
    ),
}


@dataclass
class GrafanaClientConfig:
    base_url: str = "https://prometheus-dedicated-64-prod-eu-west-5.grafana.net"
    user: str = ""
    token: str = ""
    tenant_id: str = ""
    timeout: float = 30.0
    dashboard: str = "primary"

    @classmethod
    def from_django_settings(cls) -> "GrafanaClientConfig":
        from django.conf import settings as s
        return cls(
            base_url=getattr(s, "GRAFANA_BASE_URL", cls.base_url).rstrip("/"),
            user=str(getattr(s, "GRAFANA_USER", "")),
            token=getattr(s, "GRAFANA_TOKEN", ""),
            tenant_id=getattr(s, "GRAFANA_TENANT_ID", ""),
            timeout=float(getattr(s, "GRAFANA_TIMEOUT", 30)),
            dashboard=getattr(s, "GRAFANA_DASHBOARD", "primary"),
        )

    def is_configured(self) -> bool:
        return bool(self.token and self.tenant_id)


class GrafanaClient(BaseIntegrationClient):
    """
    Prometheus HTTP API client for Grafana Mimir.

    All HTTP calls go through _with_retry() (inherited from BaseIntegrationClient).

    Public methods:
      query_range(promql, start, end, step) -> list[dict]
      list_metric_names(keyword)            -> list[str]
      list_job_values()                     -> list[str]
      test_promql(promql)                   -> list[dict]
    """

    MAX_RETRIES = 3
    RETRY_BACKOFF = 5.0

    def __init__(self, config: GrafanaClientConfig) -> None:
        super().__init__()
        self._config = config

    def get_service_name(self) -> str:
        return "grafana-mimir"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _make_client(self):
        try:
            import httpx
        except ImportError:
            raise IntegrationError(
                service=self.get_service_name(),
                message="httpx is not installed (pip install httpx)",
                retryable=False,
            )
        cfg = self._config
        return httpx.Client(
            auth=(cfg.user, cfg.token),
            headers={
                "X-Scope-OrgID": cfg.tenant_id,
                "Accept": "application/json",
            },
            timeout=cfg.timeout,
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        if not self._config.is_configured():
            return False
        try:
            with self._make_client() as client:
                resp = client.get(f"{self._config.base_url}/api/prom/api/v1/labels")
                return resp.status_code == 200
        except Exception as exc:
            self._log.warning("Grafana health check failed: %s", exc)
            return False

    def query_range(
        self,
        promql: str,
        start: str,
        end: str,
        step: str,
    ) -> List[Dict[str, Any]]:
        """
        Call the Prometheus range-query endpoint.

        Returns a list of metric series:
          [{"metric": {"instance": "...", ...}, "values": [[ts, val], ...]}, ...]

        Raises IntegrationError after MAX_RETRIES failures.
        """
        params = {"query": promql, "start": start, "end": end, "step": step}
        url = f"{self._config.base_url}/api/prom/api/v1/query_range"

        def _call() -> List[Dict[str, Any]]:
            with self._make_client() as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                body = resp.json()
                if body.get("status") != "success":
                    raise ValueError(
                        f"Prometheus status={body.get('status')}: "
                        f"{body.get('error', 'unknown error')}"
                    )
                return body.get("data", {}).get("result", [])

        return self._with_retry(_call)

    def list_metric_names(self, keyword: Optional[str] = None) -> List[str]:
        """Return all metric names from the cluster, optionally filtered by keyword."""
        url = f"{self._config.base_url}/api/prom/api/v1/label/__name__/values"

        def _call() -> List[str]:
            with self._make_client() as client:
                resp = client.get(url)
                resp.raise_for_status()
                names: List[str] = resp.json().get("data", [])
            if keyword:
                kw = keyword.lower()
                names = [n for n in names if kw in n.lower()]
            return sorted(names)

        return self._with_retry(_call)

    def list_job_values(self) -> List[str]:
        """Return all distinct job label values (active Prometheus exporters)."""
        url = f"{self._config.base_url}/api/prom/api/v1/label/job/values"

        def _call() -> List[str]:
            with self._make_client() as client:
                resp = client.get(url)
                resp.raise_for_status()
                return sorted(resp.json().get("data", []))

        return self._with_retry(_call)

    def test_promql(self, promql: str) -> List[Dict[str, Any]]:
        """Instant query — returns matching series labels + current value."""
        url = f"{self._config.base_url}/api/prom/api/v1/query"

        def _call() -> List[Dict[str, Any]]:
            with self._make_client() as client:
                resp = client.get(url, params={"query": promql, "time": "now"})
                resp.raise_for_status()
                return resp.json().get("data", {}).get("result", [])

        return self._with_retry(_call)
