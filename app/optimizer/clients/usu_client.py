"""
USU SAM API client — consolidates three duplicate HTTP session setups.

Replaces _build_session() + _fetch_page() copy-pasted across:
  fetch_usu_data.py       lines 150-183   (SQL Server installations + demand)
  fetch_java_usu_data.py  lines 132-160   (Java/Oracle installations + demand)
  fetch_demand_data.py    lines 115-164   (demand-details streaming)

All three shared the same base URL, Basic-Auth pattern, and retry logic.
The type-coercion helpers (_str, _bool, _decimal, etc.) and server-resolution
logic stay in the command files — they are domain logic, not transport logic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

from optimizer.clients.base import BaseIntegrationClient, IntegrationError

logger = logging.getLogger(__name__)

_INSTALL_PATH = "/prod/index.php/api/customization/v1.0/installations"
_DEMAND_PATH  = "/prod/index.php/api/customization/v1.0/demanddetails"


@dataclass
class USUClientConfig:
    base_url: str = "https://lima.bayer.cloud.usu.com"
    username: str = ""
    password: str = ""
    timeout: int = 120
    max_retries: int = 4
    retry_backoff: float = 5.0

    @classmethod
    def from_django_settings(cls) -> "USUClientConfig":
        from django.conf import settings as s
        return cls(
            base_url=getattr(s, "USU_API_BASE_URL", cls.base_url).rstrip("/"),
            username=getattr(s, "USU_API_USERNAME", ""),
            password=getattr(s, "USU_API_PASSWORD", ""),
        )


class USUClient(BaseIntegrationClient):
    """
    HTTP client for the USU SAM API.
    Handles Basic Auth, pagination, and retry with back-off.

    Public methods:
      fetch_url(url, params)                   -> dict   (single page, full URL)
      fetch_page(path, product_family, ...)    -> dict   (single page, path-based)
      iter_all_pages(path, product_family, ...) -> Iterator[list[dict]]
      fetch_installations(product_family, ...) -> Iterator[list[dict]]
      fetch_demand(product_family, ...)        -> Iterator[list[dict]]
    """

    def __init__(self, config: USUClientConfig) -> None:
        super().__init__()
        self._config = config
        self.MAX_RETRIES = config.max_retries
        self.RETRY_BACKOFF = config.retry_backoff

    def get_service_name(self) -> str:
        return "usu-api"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_session(self):
        try:
            import requests
            from requests.auth import HTTPBasicAuth
        except ImportError:
            raise IntegrationError(
                service=self.get_service_name(),
                message="requests package is not installed (pip install requests)",
                retryable=False,
            )
        session = requests.Session()
        session.auth = HTTPBasicAuth(self._config.username, self._config.password)
        session.headers.update({"Accept": "application/json"})
        return session

    # ── Public API ─────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            data = self.fetch_page(_INSTALL_PATH, "SQL Server", skip=0, top=1)
            return isinstance(data, dict)
        except Exception as exc:
            self._log.warning("USU API health check failed: %s", exc)
            return False

    def fetch_url(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        GET a single page by full URL with retry.
        Used when the API returns a next_page_uri that encodes params in the URL.
        """
        session = self._build_session()

        def _call() -> Dict[str, Any]:
            resp = session.get(url, params=params, timeout=self._config.timeout)
            resp.raise_for_status()
            return resp.json()

        return self._with_retry(_call)

    def fetch_page(
        self,
        path: str,
        product_family: str,
        skip: int = 0,
        top: int = 100,
    ) -> Dict[str, Any]:
        """Fetch one page by endpoint path + pagination params."""
        url = f"{self._config.base_url}{path}"
        params = {"product_family": product_family, "$top": top, "$skip": skip}
        return self.fetch_url(url, params)

    def iter_all_pages(
        self,
        path: str,
        product_family: str,
        page_size: int = 100,
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        Yield pages of records using offset-based pagination until exhausted.
        Each yield is one page (a list of raw record dicts).
        """
        skip = 0
        while True:
            data = self.fetch_page(path, product_family, skip=skip, top=page_size)
            records: List[Dict[str, Any]] = data.get("data") or []
            if not records:
                break
            yield records
            if len(records) < page_size:
                break
            skip += page_size

    def fetch_installations(
        self, product_family: str, page_size: int = 100
    ) -> Iterator[List[Dict[str, Any]]]:
        """Convenience: iterate installation pages for a given product family."""
        return self.iter_all_pages(_INSTALL_PATH, product_family, page_size)

    def fetch_demand(
        self, product_family: str, page_size: int = 30_000
    ) -> Iterator[List[Dict[str, Any]]]:
        """Convenience: iterate demand-detail pages for a given product family."""
        return self.iter_all_pages(_DEMAND_PATH, product_family, page_size)
