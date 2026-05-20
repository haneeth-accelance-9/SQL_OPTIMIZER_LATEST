"""
Integration client registry — single import point for all external services.

Usage (in views, services, management commands):
    from optimizer.clients import get_client

    llm     = get_client("llm")      # Azure OpenAI
    agent   = get_client("agent")    # A2A agent server
    grafana = get_client("grafana")  # Grafana / Mimir Prometheus API
    usu     = get_client("usu")      # USU SAM API
    cosmos  = get_client("cosmos")   # Azure Cosmos DB

Swapping to a mock in tests:
    from optimizer.clients import _registry
    _registry["grafana"] = MockGrafanaClient()
    # or use clear_registry() to force fresh construction
"""
from __future__ import annotations

from optimizer.clients.base import BaseIntegrationClient, IntegrationError  # noqa: F401

# Lazily-populated singleton cache: service_name → client instance.
# Populated on first call to get_client(); never imported directly by callers.
_registry: dict[str, BaseIntegrationClient] = {}


def get_client(service: str) -> BaseIntegrationClient:
    """
    Return the singleton client for the requested service.

    Constructs the client on first call using Django settings; caches for reuse.
    Valid service names: "llm", "agent", "grafana", "usu", "cosmos"
    """
    if service in _registry:
        return _registry[service]
    client = _build_client(service)
    _registry[service] = client
    return client


def clear_registry() -> None:
    """Clear the client cache. Call in tests to force fresh construction."""
    _registry.clear()


def _build_client(service: str) -> BaseIntegrationClient:
    if service == "llm":
        from optimizer.clients.llm_client import LLMClient, LLMClientConfig
        return LLMClient(LLMClientConfig.from_django_settings())

    if service == "agent":
        from optimizer.clients.agent_client import AgentClient, AgentClientConfig
        return AgentClient(AgentClientConfig.from_django_settings())

    if service == "grafana":
        from optimizer.clients.grafana_client import GrafanaClient, GrafanaClientConfig
        return GrafanaClient(GrafanaClientConfig.from_django_settings())

    if service == "usu":
        from optimizer.clients.usu_client import USUClient, USUClientConfig
        return USUClient(USUClientConfig.from_django_settings())

    if service == "cosmos":
        from optimizer.clients.cosmos_client import CosmosClient, CosmosClientConfig
        return CosmosClient(CosmosClientConfig.from_django_settings())

    raise ValueError(
        f"Unknown service '{service}'. Valid: llm, agent, grafana, usu, cosmos"
    )
