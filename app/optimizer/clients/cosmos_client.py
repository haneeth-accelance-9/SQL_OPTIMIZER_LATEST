"""
Azure Cosmos DB client — implements the workflow-state store that was docs-only.

Previously the architecture docs described save_workflow_state / load_workflow_state
but no implementation existed anywhere in the codebase. This is that implementation.

Document shape stored in Cosmos:
  {
    "id":          "<workflow_id>",
    "workflow_id": "<workflow_id>",   ← partition key
    "state":       { ... },           ← arbitrary agent workflow state
    "updated_at":  "2026-05-20T..."
  }

Required env vars (add to .env):
  COSMOSDB_ENDPOINT   https://<account>.documents.azure.com:443/
  COSMOSDB_KEY        <primary or secondary key>
  COSMOSDB_DATABASE   mvp6                    (default)
  COSMOSDB_CONTAINER  workflow_state          (default)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from optimizer.clients.base import BaseIntegrationClient, IntegrationError

logger = logging.getLogger(__name__)


@dataclass
class CosmosClientConfig:
    endpoint: str = ""
    key: str = ""
    database: str = "mvp6"
    container: str = "workflow_state"
    partition_key_path: str = "/workflow_id"

    @classmethod
    def from_django_settings(cls) -> "CosmosClientConfig":
        from django.conf import settings as s
        return cls(
            endpoint=getattr(s, "COSMOSDB_ENDPOINT", "").strip(),
            key=getattr(s, "COSMOSDB_KEY", "").strip(),
            database=getattr(s, "COSMOSDB_DATABASE", "mvp6").strip(),
            container=getattr(s, "COSMOSDB_CONTAINER", "workflow_state").strip(),
        )

    def is_configured(self) -> bool:
        return bool(self.endpoint and self.key)


class CosmosClient(BaseIntegrationClient):
    """
    Azure Cosmos DB client for agent workflow state persistence.

    Public methods:
      save_workflow_state(workflow_id, state)  -> None
      load_workflow_state(workflow_id)         -> Optional[dict]
      delete_workflow_state(workflow_id)       -> None
    """

    def __init__(self, config: CosmosClientConfig) -> None:
        super().__init__()
        self._config = config
        self._container_client = None  # lazy

    def get_service_name(self) -> str:
        return "azure-cosmos"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_container(self):
        if self._container_client is not None:
            return self._container_client
        if not self._config.is_configured():
            raise IntegrationError(
                service=self.get_service_name(),
                message="COSMOSDB_ENDPOINT and COSMOSDB_KEY must be set in .env",
                retryable=False,
            )
        try:
            from azure.cosmos import CosmosClient as _SDK, PartitionKey
        except ImportError:
            raise IntegrationError(
                service=self.get_service_name(),
                message="azure-cosmos not installed (pip install azure-cosmos)",
                retryable=False,
            )
        cfg = self._config
        sdk = _SDK(url=cfg.endpoint, credential=cfg.key)
        db = sdk.create_database_if_not_exists(id=cfg.database)
        self._container_client = db.create_container_if_not_exists(
            id=cfg.container,
            partition_key=PartitionKey(path=cfg.partition_key_path),
        )
        return self._container_client

    @staticmethod
    def _is_not_found(exc: Exception) -> bool:
        return "404" in str(exc) or "NotFound" in type(exc).__name__

    # ── Public API ─────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        if not self._config.is_configured():
            return False
        try:
            container = self._get_container()
            list(container.query_items(
                "SELECT TOP 1 c.id FROM c",
                enable_cross_partition_query=True,
            ))
            return True
        except Exception as exc:
            self._log.warning("Cosmos DB health check failed: %s", exc)
            return False

    def save_workflow_state(self, workflow_id: str, state: Dict[str, Any]) -> None:
        """Upsert a workflow state document keyed by workflow_id."""
        from datetime import datetime, timezone

        doc: Dict[str, Any] = {
            "id": workflow_id,
            "workflow_id": workflow_id,
            "state": state,
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        def _call() -> None:
            self._get_container().upsert_item(body=doc)

        self._with_retry(_call)
        self._log.info("Saved workflow state: %s", workflow_id)

    def load_workflow_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Return the state dict for workflow_id, or None if not found."""

        def _call() -> Optional[Dict[str, Any]]:
            try:
                doc = self._get_container().read_item(
                    item=workflow_id,
                    partition_key=workflow_id,
                )
                return doc.get("state")
            except Exception as exc:
                if self._is_not_found(exc):
                    return None
                raise

        return self._with_retry(_call)

    def delete_workflow_state(self, workflow_id: str) -> None:
        """Delete the workflow state document; silently ignores 404."""

        def _call() -> None:
            try:
                self._get_container().delete_item(
                    item=workflow_id,
                    partition_key=workflow_id,
                )
            except Exception as exc:
                if self._is_not_found(exc):
                    return
                raise

        self._with_retry(_call)
        self._log.info("Deleted workflow state: %s", workflow_id)
