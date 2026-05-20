# Integration Abstraction Layer

## Overview

All external service calls in the Django application are routed through a single
`optimizer/clients/` package. No feature code imports `requests`, `httpx`, `openai`,
`urllib.request`, or `azure-cosmos` directly — it always goes through the registry.

## Package Layout

```
app/optimizer/clients/
├── __init__.py          ← registry: get_client("llm"), clear_registry()
├── base.py              ← BaseIntegrationClient + IntegrationError
├── llm_client.py        ← Azure OpenAI (openai SDK)
├── agent_client.py      ← A2A agent server (urllib HTTP)
├── grafana_client.py    ← Grafana/Mimir Prometheus HTTP API (httpx)
├── usu_client.py        ← USU SAM API (requests + BasicAuth)
└── cosmos_client.py     ← Azure Cosmos DB (azure-cosmos SDK)
```

## BaseIntegrationClient Contract

Every client extends `BaseIntegrationClient` (`base.py`) and must implement:

| Method | Required | Description |
|--------|----------|-------------|
| `get_service_name()` | yes | Short slug used in error messages and logs |
| `health_check()` | yes | Returns `bool` — safe to call from a health endpoint |
| `_with_retry(fn)` | inherited | Runs `fn()` with linear back-off, respects `MAX_RETRIES` / `RETRY_BACKOFF` |

`IntegrationError` is raised on unrecoverable or post-retry failures:

```python
@dataclass
class IntegrationError(Exception):
    service: str
    message: str
    status_code: Optional[int] = None
    retryable: bool = False
```

## Client Registry

`optimizer/clients/__init__.py` provides a module-level singleton cache:

```python
from optimizer.clients import get_client

llm    = get_client("llm")       # LLMClient
agent  = get_client("agent")     # AgentClient
grafana = get_client("grafana")  # GrafanaClient
usu    = get_client("usu")       # USUClient
cosmos = get_client("cosmos")    # CosmosClient
```

Each client is built once (lazy, on first call) and cached for the process lifetime.
`clear_registry()` resets the cache — used in tests to inject fresh configs.

## Configuration

Each client has a typed `*Config` dataclass with a `from_django_settings()` class method.
Calling `get_client("llm")` automatically invokes `LLMClientConfig.from_django_settings()`.

| Client | Key env vars (via Django settings) |
|--------|-------------------------------------|
| `llm` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION` |
| `agent` | `AGENT_A2A_ENDPOINT`, `AGENT_A2A_TIMEOUT`, `AGENT_A2A_MAX_RETRIES` |
| `grafana` | `GRAFANA_BASE_URL`, `GRAFANA_USER`, `GRAFANA_TOKEN`, `GRAFANA_TENANT_ID` |
| `usu` | `USU_API_BASE_URL`, `USU_API_USERNAME`, `USU_API_PASSWORD` |
| `cosmos` | `COSMOSDB_ENDPOINT`, `COSMOSDB_KEY`, `COSMOSDB_DATABASE`, `COSMOSDB_CONTAINER` |

## Call-Site Files Updated

| File | Change |
|------|--------|
| `optimizer/services/ai_report_generator.py` | `generate_report_text()` and `generate_cost_reduction_recommendations()` use `get_client("llm").complete()`; `call_agent_generate_report()` uses `get_client("agent").call_generate_report()` |
| `management/commands/fetch_grafana_metrics.py` | `GRAFANA_METRICS` imported from `grafana_client`; `_query_range()` replaced by `get_client("grafana").query_range()` |
| `management/commands/explore_grafana_metrics.py` | `httpx.Client` replaced by `get_client("grafana").list_metric_names()` / `.list_job_values()` / `.test_promql()` |
| `management/commands/fetch_usu_data.py` | `_build_session()` / `_fetch_page()` removed; fetch functions accept `usu` client, call `usu.fetch_url()` |
| `management/commands/fetch_java_usu_data.py` | Same as above |
| `management/commands/fetch_demand_data.py` | `_build_session()` / `_fetch_page_with_retry()` removed; `_fetch_page(usu, skip)` helper wraps `usu.fetch_url()` |
| `agent/liscence-optimizer/src/a2a_server.py` | `_call_azure_openai_chat()` rewritten from urllib to openai SDK; API version default standardised to `2024-12-01-preview` |

## API Version Drift Bug Fixed

`ai_report_generator.py` previously defaulted to `"2024-02-15-preview"` while
`a2a_server.py` used `"2024-12-01-preview"`. Both now use `"2024-12-01-preview"` as
the single authoritative default (set in `LLMClientConfig` and `_call_azure_openai_chat`).

## Degradation and Fallback Strategy

| Service | Behaviour when unavailable |
|---------|---------------------------|
| LLM (`llm`) | `complete()` returns `None` if not configured; callers skip AI section and return deterministic result |
| A2A agent (`agent`) | `call_agent_generate_report()` falls back to `_build_local_agent_report_response()` in-process; an `AgentRun` row with `status='failed'` is written |
| Grafana (`grafana`) | Management commands log errors per-metric and `continue` the loop; partial snapshots are still saved |
| USU (`usu`) | Management commands propagate the exception up to Django management; APScheduler catches and logs it |
| Cosmos DB (`cosmos`) | Unconfigured silently (no endpoint/key); raises `IntegrationError` if configured but unreachable |

## Adding a New Integration

1. Create `optimizer/clients/my_service_client.py` — extend `BaseIntegrationClient`, implement `get_service_name()` and `health_check()`.
2. Add a `MyServiceConfig` dataclass with `from_django_settings()`.
3. Register it in `optimizer/clients/__init__.py`'s `_build_client()` dispatch.
4. Add the required env vars to `.env.example` and Django settings.
5. Call `get_client("my_service")` at the call site — never import `requests` / `httpx` / SDK directly.
