"""
Coverage tests for optimizer.clients.base, grafana_client, cosmos_client, llm_client.
All external HTTP / SDK calls are mocked so no real services are needed.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import time

from optimizer.clients.base import BaseIntegrationClient, IntegrationError


# ===========================================================================
# IntegrationError
# ===========================================================================

class TestIntegrationError:
    def test_str_basic(self):
        err = IntegrationError(service="svc", message="bad")
        assert "[svc] bad" in str(err)

    def test_str_with_status_code(self):
        err = IntegrationError(service="svc", message="bad", status_code=404)
        s = str(err)
        assert "HTTP 404" in s

    def test_str_retryable(self):
        err = IntegrationError(service="svc", message="bad", retryable=True)
        assert "[retryable]" in str(err)

    def test_is_exception(self):
        err = IntegrationError(service="svc", message="bad")
        assert isinstance(err, Exception)


# ===========================================================================
# BaseIntegrationClient._with_retry
# ===========================================================================

class _ConcreteClient(BaseIntegrationClient):
    def get_service_name(self) -> str:
        return "test-service"

    def health_check(self) -> bool:
        return True


class TestBaseClientRetry:
    def test_success_on_first_try(self):
        client = _ConcreteClient()
        result = client._with_retry(lambda: 42)
        assert result == 42

    def test_retries_on_failure_then_succeeds(self):
        client = _ConcreteClient()
        client.MAX_RETRIES = 3
        client.RETRY_BACKOFF = 0.0
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("temp")
            return "ok"

        with patch("time.sleep"):
            result = client._with_retry(fn)
        assert result == "ok"
        assert call_count[0] == 2

    def test_raises_integration_error_after_all_retries(self):
        client = _ConcreteClient()
        client.MAX_RETRIES = 2
        client.RETRY_BACKOFF = 0.0

        def always_fail():
            raise RuntimeError("always")

        with patch("time.sleep"), pytest.raises(IntegrationError) as exc_info:
            client._with_retry(always_fail)
        assert exc_info.value.retryable is True
        assert "always" in exc_info.value.message

    def test_logging_on_retry(self):
        client = _ConcreteClient()
        client.MAX_RETRIES = 2
        client.RETRY_BACKOFF = 0.0
        attempts = [0]

        def fail_once():
            attempts[0] += 1
            if attempts[0] < 2:
                raise ValueError("retry me")
            return "done"

        with patch("time.sleep"):
            result = client._with_retry(fail_once)
        assert result == "done"


# ===========================================================================
# GrafanaClient
# ===========================================================================

class TestGrafanaClientConfig:
    def test_defaults(self):
        from optimizer.clients.grafana_client import GrafanaClientConfig
        cfg = GrafanaClientConfig()
        assert "grafana" in cfg.base_url.lower()
        assert cfg.timeout == 30.0

    def test_is_configured_false_when_empty(self):
        from optimizer.clients.grafana_client import GrafanaClientConfig
        cfg = GrafanaClientConfig(token="", tenant_id="")
        assert cfg.is_configured() is False

    def test_is_configured_true(self):
        from optimizer.clients.grafana_client import GrafanaClientConfig
        cfg = GrafanaClientConfig(token="tok", tenant_id="tid")
        assert cfg.is_configured() is True

    def test_from_django_settings(self, settings):
        from optimizer.clients.grafana_client import GrafanaClientConfig
        settings.GRAFANA_BASE_URL = "https://grafana.example.com"
        settings.GRAFANA_USER = "u"
        settings.GRAFANA_TOKEN = "t"
        settings.GRAFANA_TENANT_ID = "tid"
        settings.GRAFANA_TIMEOUT = 15
        settings.GRAFANA_DASHBOARD = "dash"
        cfg = GrafanaClientConfig.from_django_settings()
        assert cfg.base_url == "https://grafana.example.com"
        assert cfg.user == "u"
        assert cfg.token == "t"
        assert cfg.tenant_id == "tid"
        assert cfg.timeout == 15.0
        assert cfg.dashboard == "dash"


class TestGrafanaClientMethods:
    def _make_client(self):
        from optimizer.clients.grafana_client import GrafanaClient, GrafanaClientConfig
        cfg = GrafanaClientConfig(token="tok", tenant_id="tid", base_url="https://g.example.com")
        return GrafanaClient(cfg)

    def test_get_service_name(self):
        client = self._make_client()
        assert client.get_service_name() == "grafana-mimir"

    def test_health_check_returns_false_when_not_configured(self):
        from optimizer.clients.grafana_client import GrafanaClient, GrafanaClientConfig
        cfg = GrafanaClientConfig(token="", tenant_id="")
        client = GrafanaClient(cfg)
        assert client.health_check() is False

    def test_health_check_returns_true_on_200(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        with patch.object(client, "_make_client", return_value=mock_client):
            assert client.health_check() is True

    def test_health_check_returns_false_on_exception(self):
        client = self._make_client()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(side_effect=Exception("fail"))
        mock_client.__exit__ = MagicMock(return_value=False)
        with patch.object(client, "_make_client", return_value=mock_client):
            assert client.health_check() is False

    def test_make_client_raises_when_httpx_missing(self):
        client = self._make_client()
        with patch.dict("sys.modules", {"httpx": None}):
            with pytest.raises(IntegrationError) as exc_info:
                client._make_client()
            assert "httpx" in exc_info.value.message

    def test_query_range_returns_results(self):
        client = self._make_client()
        expected = [{"metric": {}, "values": [[1, "2"]]}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "success", "data": {"result": expected}}
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value = mock_resp
        with patch.object(client, "_make_client", return_value=mock_http):
            result = client.query_range("mssql_connections", "now-1h", "now", "5m")
        assert result == expected

    def test_query_range_raises_on_non_success_status(self):
        client = self._make_client()
        client.MAX_RETRIES = 1
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "error", "error": "oops"}
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value = mock_resp
        with patch.object(client, "_make_client", return_value=mock_http), \
             patch("time.sleep"), \
             pytest.raises(IntegrationError):
            client.query_range("bad", "now-1h", "now", "5m")

    def test_list_metric_names_no_filter(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": ["mssql_connections", "go_gc_duration"]}
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value = mock_resp
        with patch.object(client, "_make_client", return_value=mock_http):
            names = client.list_metric_names()
        assert "mssql_connections" in names

    def test_list_metric_names_with_keyword(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": ["mssql_connections", "go_gc_duration"]}
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value = mock_resp
        with patch.object(client, "_make_client", return_value=mock_http):
            names = client.list_metric_names(keyword="mssql")
        assert names == ["mssql_connections"]

    def test_list_job_values(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": ["job_b", "job_a"]}
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value = mock_resp
        with patch.object(client, "_make_client", return_value=mock_http):
            jobs = client.list_job_values()
        assert jobs == ["job_a", "job_b"]  # sorted

    def test_test_promql(self):
        client = self._make_client()
        expected = [{"metric": {"instance": "srv1"}, "value": [1, "42"]}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"result": expected}}
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value = mock_resp
        with patch.object(client, "_make_client", return_value=mock_http):
            result = client.test_promql("mssql_connections")
        assert result == expected

    def test_grafana_metrics_dict_exists(self):
        from optimizer.clients.grafana_client import GRAFANA_METRICS
        assert "connections" in GRAFANA_METRICS
        assert "batch_requests" in GRAFANA_METRICS


# ===========================================================================
# CosmosClient
# ===========================================================================

class TestCosmosClientConfig:
    def test_defaults(self):
        from optimizer.clients.cosmos_client import CosmosClientConfig
        cfg = CosmosClientConfig()
        assert cfg.database == "mvp6"
        assert cfg.container == "workflow_state"

    def test_is_configured_false(self):
        from optimizer.clients.cosmos_client import CosmosClientConfig
        cfg = CosmosClientConfig(endpoint="", key="")
        assert cfg.is_configured() is False

    def test_is_configured_true(self):
        from optimizer.clients.cosmos_client import CosmosClientConfig
        cfg = CosmosClientConfig(endpoint="https://cosmos.example.com", key="abc123")
        assert cfg.is_configured() is True

    def test_from_django_settings(self, settings):
        from optimizer.clients.cosmos_client import CosmosClientConfig
        settings.COSMOSDB_ENDPOINT = "https://cosmos.example.com"
        settings.COSMOSDB_KEY = "mykey"
        settings.COSMOSDB_DATABASE = "mydb"
        settings.COSMOSDB_CONTAINER = "mycontainer"
        cfg = CosmosClientConfig.from_django_settings()
        assert cfg.endpoint == "https://cosmos.example.com"
        assert cfg.key == "mykey"
        assert cfg.database == "mydb"
        assert cfg.container == "mycontainer"


class TestCosmosClientMethods:
    def _make_client(self):
        from optimizer.clients.cosmos_client import CosmosClient, CosmosClientConfig
        cfg = CosmosClientConfig(endpoint="https://cosmos.example.com", key="abc123")
        return CosmosClient(cfg)

    def _make_unconfigured_client(self):
        from optimizer.clients.cosmos_client import CosmosClient, CosmosClientConfig
        cfg = CosmosClientConfig(endpoint="", key="")
        return CosmosClient(cfg)

    def test_get_service_name(self):
        client = self._make_client()
        assert client.get_service_name() == "azure-cosmos"

    def test_health_check_false_when_not_configured(self):
        client = self._make_unconfigured_client()
        assert client.health_check() is False

    def test_get_container_raises_when_not_configured(self):
        client = self._make_unconfigured_client()
        with pytest.raises(IntegrationError) as exc_info:
            client._get_container()
        assert "COSMOSDB_ENDPOINT" in exc_info.value.message

    def test_get_container_raises_when_azure_cosmos_missing(self):
        client = self._make_client()
        with patch.dict("sys.modules", {"azure.cosmos": None, "azure": MagicMock()}):
            with pytest.raises(Exception):
                client._get_container()

    def test_is_not_found_with_404(self):
        from optimizer.clients.cosmos_client import CosmosClient
        assert CosmosClient._is_not_found(Exception("404 not found"))

    def test_is_not_found_with_not_found_in_class_name(self):
        from optimizer.clients.cosmos_client import CosmosClient

        class NotFoundException(Exception):
            pass

        assert CosmosClient._is_not_found(NotFoundException("oops"))

    def test_is_not_found_false_for_other(self):
        from optimizer.clients.cosmos_client import CosmosClient
        assert not CosmosClient._is_not_found(ValueError("something else"))

    def test_health_check_true_on_success(self):
        client = self._make_client()
        mock_container = MagicMock()
        mock_container.query_items.return_value = iter([{"id": "x"}])
        with patch.object(client, "_get_container", return_value=mock_container):
            assert client.health_check() is True

    def test_health_check_false_on_exception(self):
        client = self._make_client()
        with patch.object(client, "_get_container", side_effect=Exception("fail")):
            assert client.health_check() is False

    def test_save_workflow_state(self):
        client = self._make_client()
        mock_container = MagicMock()
        mock_container.upsert_item = MagicMock()
        with patch.object(client, "_get_container", return_value=mock_container):
            client.save_workflow_state("wf-123", {"step": 1})
        mock_container.upsert_item.assert_called_once()
        doc = mock_container.upsert_item.call_args[1]["body"]
        assert doc["workflow_id"] == "wf-123"
        assert doc["state"] == {"step": 1}

    def test_load_workflow_state_returns_state(self):
        client = self._make_client()
        mock_container = MagicMock()
        mock_container.read_item.return_value = {"id": "wf-1", "state": {"x": 1}}
        with patch.object(client, "_get_container", return_value=mock_container):
            result = client.load_workflow_state("wf-1")
        assert result == {"x": 1}

    def test_load_workflow_state_returns_none_on_404(self):
        client = self._make_client()
        mock_container = MagicMock()
        mock_container.read_item.side_effect = Exception("404 not found")
        with patch.object(client, "_get_container", return_value=mock_container):
            result = client.load_workflow_state("wf-missing")
        assert result is None

    def test_delete_workflow_state(self):
        client = self._make_client()
        mock_container = MagicMock()
        mock_container.delete_item = MagicMock()
        with patch.object(client, "_get_container", return_value=mock_container):
            client.delete_workflow_state("wf-123")
        mock_container.delete_item.assert_called_once()

    def test_delete_workflow_state_ignores_404(self):
        client = self._make_client()
        mock_container = MagicMock()
        mock_container.delete_item.side_effect = Exception("404 not found")
        with patch.object(client, "_get_container", return_value=mock_container):
            client.delete_workflow_state("wf-missing")  # should not raise


# ===========================================================================
# LLMClient
# ===========================================================================

class TestLLMClientConfig:
    def test_defaults(self):
        from optimizer.clients.llm_client import LLMClientConfig
        cfg = LLMClientConfig()
        assert cfg.deployment == "gpt-4"
        assert cfg.api_version == "2024-12-01-preview"
        assert cfg.timeout == 60.0

    def test_is_configured_false_when_empty(self):
        from optimizer.clients.llm_client import LLMClientConfig
        cfg = LLMClientConfig(endpoint="", api_key="")
        assert cfg.is_configured() is False

    def test_is_configured_true(self):
        from optimizer.clients.llm_client import LLMClientConfig
        cfg = LLMClientConfig(endpoint="https://openai.example.com", api_key="k")
        assert cfg.is_configured() is True

    def test_from_django_settings_prefers_apim(self, settings):
        from optimizer.clients.llm_client import LLMClientConfig
        settings.AZURE_APIM_ENDPOINT = "https://apim.example.com"
        settings.AZURE_OPENAI_ENDPOINT = "https://openai.example.com"
        settings.AZURE_OPENAI_API_KEY = "key"
        settings.AZURE_OPENAI_DEPLOYMENT = "gpt-4o"
        settings.AZURE_OPENAI_API_VERSION = "2025-01-01"
        settings.AZURE_OPENAI_TIMEOUT = 30
        settings.AZURE_APIM_SUB_KEY = "subkey"
        cfg = LLMClientConfig.from_django_settings()
        assert cfg.endpoint == "https://apim.example.com"
        assert cfg.deployment == "gpt-4o"

    def test_from_django_settings_falls_back_to_openai_endpoint(self, settings):
        from optimizer.clients.llm_client import LLMClientConfig
        settings.AZURE_APIM_ENDPOINT = ""
        settings.AZURE_OPENAI_ENDPOINT = "https://openai.example.com"
        settings.AZURE_OPENAI_API_KEY = "key"
        settings.AZURE_OPENAI_DEPLOYMENT = "gpt-4"
        settings.AZURE_OPENAI_API_VERSION = "2024-12-01-preview"
        settings.AZURE_OPENAI_TIMEOUT = 60
        settings.AZURE_APIM_SUB_KEY = ""
        cfg = LLMClientConfig.from_django_settings()
        assert cfg.endpoint == "https://openai.example.com"


class TestLLMClientMethods:
    def _make_client(self, configured=True):
        from optimizer.clients.llm_client import LLMClient, LLMClientConfig
        if configured:
            cfg = LLMClientConfig(endpoint="https://openai.example.com", api_key="k")
        else:
            cfg = LLMClientConfig(endpoint="", api_key="")
        return LLMClient(cfg)

    def test_get_service_name(self):
        client = self._make_client()
        assert client.get_service_name() == "azure-openai"

    def test_health_check_false_when_not_configured(self):
        client = self._make_client(configured=False)
        assert client.health_check() is False

    def test_health_check_true_on_success(self):
        client = self._make_client()
        mock_openai = MagicMock()
        mock_openai.models.list.return_value = []
        with patch.object(client, "_get_client", return_value=mock_openai):
            assert client.health_check() is True

    def test_health_check_false_on_exception(self):
        client = self._make_client()
        with patch.object(client, "_get_client", side_effect=Exception("fail")):
            assert client.health_check() is False

    def test_build_client_raises_when_openai_missing(self):
        client = self._make_client()
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(IntegrationError) as exc_info:
                client._build_client()
            assert "openai" in exc_info.value.message.lower()

    def test_build_client_raises_when_not_configured(self):
        client = self._make_client(configured=False)
        with pytest.raises(IntegrationError) as exc_info:
            client._build_client()
        assert "AZURE_OPENAI_ENDPOINT" in exc_info.value.message

    def test_complete_returns_none_when_not_configured(self):
        client = self._make_client(configured=False)
        result = client.complete(system="sys", user="user")
        assert result is None

    def test_complete_returns_text(self):
        client = self._make_client()
        mock_choice = MagicMock()
        mock_choice.message.content = "  Answer text  "
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = mock_response
        with patch.object(client, "_get_client", return_value=mock_openai):
            result = client.complete(system="sys", user="user")
        assert result == "Answer text"

    def test_complete_returns_none_when_empty_content(self):
        client = self._make_client()
        mock_choice = MagicMock()
        mock_choice.message.content = "   "
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = mock_response
        with patch.object(client, "_get_client", return_value=mock_openai):
            result = client.complete(system="sys", user="user")
        assert result is None

    def test_complete_raises_integration_error_on_api_failure(self):
        client = self._make_client()
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.side_effect = RuntimeError("API down")
        with patch.object(client, "_get_client", return_value=mock_openai), \
             pytest.raises(IntegrationError) as exc_info:
            client.complete(system="sys", user="user")
        assert "API down" in exc_info.value.message

    def test_complete_with_usage_returns_none_when_not_configured(self):
        client = self._make_client(configured=False)
        content, meta = client.complete_with_usage(system="sys", user="user")
        assert content is None
        assert meta == {}

    def test_complete_with_usage_returns_content_and_meta(self):
        client = self._make_client()
        mock_choice = MagicMock()
        mock_choice.message.content = "result"
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5
        mock_usage.total_tokens = 15
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = mock_response
        with patch.object(client, "_get_client", return_value=mock_openai):
            content, meta = client.complete_with_usage(system="sys", user="user")
        assert content == "result"
        assert meta["prompt_tokens"] == 10
        assert meta["completion_tokens"] == 5

    def test_calculate_cost_eur(self):
        from optimizer.clients.llm_client import LLMClient
        cost = LLMClient.calculate_cost_eur(1000, 500)
        assert cost > 0
        assert isinstance(cost, float)

    def test_get_client_caches_instance(self):
        client = self._make_client()
        mock_openai = MagicMock()
        with patch.object(client, "_build_client", return_value=mock_openai) as mock_build:
            _ = client._get_client()
            _ = client._get_client()
        mock_build.assert_called_once()

    def test_build_client_includes_apim_header(self):
        from optimizer.clients.llm_client import LLMClient, LLMClientConfig
        cfg = LLMClientConfig(
            endpoint="https://apim.example.com",
            api_key="k",
            apim_sub_key="sub123",
        )
        client = LLMClient(cfg)
        mock_azure_openai_cls = MagicMock()
        mock_azure_openai_cls.return_value = MagicMock()
        with patch.dict("sys.modules", {"openai": MagicMock(AzureOpenAI=mock_azure_openai_cls)}):
            client._build_client()
        call_kwargs = mock_azure_openai_cls.call_args[1]
        assert "default_headers" in call_kwargs
        assert call_kwargs["default_headers"]["Ocp-Apim-Subscription-Key"] == "sub123"
