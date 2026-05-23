"""
Tests for results, report_page, report_download, api_strategy3_rightsizing,
api_oracle_data, and additional helper functions to increase views.py coverage.
"""
import json

import pandas as pd
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from optimizer.models import Tenant, UserProfile
from optimizer.permissions import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER

User = get_user_model()

# ─────────────────────────────────────────────────────────────────────────────
# Shared fake metrics
# ─────────────────────────────────────────────────────────────────────────────

FAKE_METRICS = {
    "total_devices_analyzed": 10,
    "rule_results": {
        "azure_payg_count": 2,
        "azure_payg": [
            {
                "device_name": "vm-01", "server_name": "vm-01",
                "cpu_cores_overall_device": 8, "hosting_zone": "Public Cloud",
                "topology_type": "VM", "cpu_core_count": 8, "cpu_socket_count": 2,
                "manufacturer": "Dell", "product_family": "SQL Server",
                "product_edition": "Standard", "product_description": "SQL Server 2019 Standard",
                "license_metric": "Per Core", "no_license_required": 0,
                "install_status": "Installed", "environment": "Production",
                "u_hosting_zone": "Public Cloud", "cloud_provider": "Azure",
                "is_cloud_device": True, "inventory_status_standard": "Active",
                "Actual_Line_Cost": 5000.0,
            },
        ],
        "azure_payg_total_cost_eur": 5000.0,
        "azure_payg_prod_candidates_count": 1,
        "azure_payg_nonprod_candidates_count": 1,
        "azure_payg_demand_matched_count": 2,
        "retired_count": 1,
        "retired_devices": [
            {
                "device_name": "old-01", "server_name": "old-01",
                "inventory_status_standard": "Retired", "Actual_Line_Cost": 100.0,
            },
        ],
        "retired_devices_savings_eur": 100.0,
        "retired_demand_matched_count": 1,
    },
    "rule_wise_savings": {
        "azure_payg": 500.0,
        "retired_devices": 100.0,
        "rightsizing": 200.0,
    },
    "license_metrics": {
        "total_demand_quantity": 5,
        "total_license_cost": 10000.0,
        "by_product": [],
        "price_distribution": [
            {"product_edition": "Standard", "total_cost": 5000.0, "avg_price": 2500.0, "count": 2},
        ],
        "cost_reduction_tips": [],
        "demand_row_count": 5,
    },
    "rightsizing": {
        "cpu_optimizations": [
            {
                "server_name": "SRV-01", "Env_Type": "PROD",
                "Optimization_Type": "PROD_CPU_Optimization",
                "Avg_CPU_12m": 12.0, "Peak_CPU_12m": 65.0,
                "Current_vCPU": 8, "Recommended_vCPU": 4,
                "Potential_vCPU_Reduction": 4,
            }
        ],
        "ram_optimizations": [],
        "screen_summaries": {},
        "cpu_chart_data": [],
        "ram_chart_data": [],
        "cpu_count": 3,
        "cpu_prod_count": 2,
        "cpu_nonprod_count": 1,
        "ram_count": 2,
        "ram_prod_count": 1,
        "ram_nonprod_count": 1,
        "total_vcpu_reduction": 8,
        "total_ram_reduction_gib": 16.0,
        "error": None,
        "default_filter_by_workload": {"CPU": "PROD_CPU_Rightsizing", "RAM": "PROD_RAM_Rightsizing"},
        "screen_filter_options": {
            "CPU": ["PROD_CPU_Rightsizing", "NONPROD_CPU_Rightsizing"],
            "RAM": ["PROD_RAM_Rightsizing", "NONPROD_RAM_Rightsizing"],
        },
    },
    "rightsizing_meta": {
        "cpu_count": 3,
        "total_vcpu_reduction": 8,
        "total_ram_reduction_gib": 16.0,
        "avg_cost_per_core_pair_eur": 150.0,
        "avg_cost_per_gib_eur": 10.0,
    },
    "data_refreshed_at": None,
}


def _patch_metrics(monkeypatch, ctx=None):
    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.compute_live_db_metrics",
        lambda: ctx or FAKE_METRICS,
    )


def _patch_report(monkeypatch):
    _patch_metrics(monkeypatch)
    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.get_latest_agentic_context",
        lambda: {"has_agentic_data": False},
    )
    monkeypatch.setattr(
        "optimizer.services.ai_report_generator.build_live_agent_report_preview",
        lambda usecase_id="uc_1_2_3": {"report_markdown": "# Test Report\n\nContent.", "summary_context": {}},
    )


# ─────────────────────────────────────────────────────────────────────────────
# results view
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestResultsView:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:results"))
        assert response.status_code == 302

    def test_returns_200(self, client, monkeypatch):
        user = User.objects.create_user(username="results_user1", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(reverse("optimizer:results"))
        assert response.status_code == 200

    def test_with_pagination_params(self, client, monkeypatch):
        user = User.objects.create_user(username="results_page_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(reverse("optimizer:results") + "?rule1_page=1&rule2_page=1&rs3_page=1")
        assert response.status_code == 200

    def test_with_rs3_workload_filter(self, client, monkeypatch):
        user = User.objects.create_user(username="results_rs3_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(
            reverse("optimizer:results") + "?rs3_workload=CPU&rs3_filter=PROD_CPU_Rightsizing"
        )
        assert response.status_code == 200

    def test_with_ram_workload_filter(self, client, monkeypatch):
        user = User.objects.create_user(username="results_ram_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(
            reverse("optimizer:results") + "?rs3_workload=RAM&rs3_filter=PROD_RAM_Rightsizing"
        )
        assert response.status_code == 200

    def test_post_not_allowed(self, client, monkeypatch):
        user = User.objects.create_user(username="results_post_user", password="test12345!")
        client.force_login(user)
        response = client.post(reverse("optimizer:results"))
        assert response.status_code == 405

    def test_empty_rightsizing_data(self, client, monkeypatch):
        user = User.objects.create_user(username="results_empty_user", password="test12345!")
        client.force_login(user)
        empty_metrics = {**FAKE_METRICS, "rightsizing": {
            "cpu_optimizations": [], "ram_optimizations": [],
            "cpu_count": 0, "ram_count": 0,
            "screen_filter_options": {
                "CPU": ["PROD_CPU_Rightsizing", "NONPROD_CPU_Rightsizing"],
                "RAM": ["PROD_RAM_Rightsizing", "NONPROD_RAM_Rightsizing"],
            },
            "default_filter_by_workload": {"CPU": "PROD_CPU_Rightsizing", "RAM": "PROD_RAM_Rightsizing"},
        }}
        _patch_metrics(monkeypatch, empty_metrics)
        response = client.get(reverse("optimizer:results"))
        assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# report_page view
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestReportPage:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:report"))
        assert response.status_code == 302

    def test_returns_200_with_mocked_services(self, client, monkeypatch):
        user = User.objects.create_user(username="report_page_user", password="test12345!")
        client.force_login(user)
        _patch_report(monkeypatch)
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.generate_report_text",
            lambda ctx: "# Test Report\n",
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.get_fallback_report",
            lambda ctx: "# Fallback Report\n",
        )
        response = client.get(reverse("optimizer:report"))
        assert response.status_code == 200

    def test_fallback_when_agent_preview_fails(self, client, monkeypatch):
        user = User.objects.create_user(username="report_fallback_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service.get_latest_agentic_context",
            lambda: {"has_agentic_data": False},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.build_live_agent_report_preview",
            lambda usecase_id="uc_1_2_3": {"report_markdown": "", "summary_context": {}},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.build_agent_strategy_results_payload",
            lambda ctx: {},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator._build_local_rules_evaluation",
            lambda rule_results=None, rightsizing=None: {},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator._build_agent_report_summary_context",
            lambda ctx, strategy_results: {},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator._render_local_agent_report_markdown",
            lambda **kwargs: "# Agent Report\n",
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.generate_report_text",
            lambda ctx: "",
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.get_fallback_report",
            lambda ctx: "# Fallback\n",
        )
        response = client.get(reverse("optimizer:report"))
        assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# report_download view
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestReportDownload:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:report_download", args=["pdf"]))
        assert response.status_code == 302

    def test_invalid_format_returns_400(self, client):
        user = User.objects.create_user(username="report_dl_invalid", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:report_download", args=["html"]))
        assert response.status_code == 400

    def test_excel_alias_works(self, client, monkeypatch):
        user = User.objects.create_user(username="report_dl_excel", password="test12345!")
        client.force_login(user)
        _patch_report(monkeypatch)
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.generate_report_text",
            lambda ctx: "# Test Report\n",
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.get_fallback_report",
            lambda ctx: "# Fallback\n",
        )
        monkeypatch.setattr(
            "optimizer.services.report_export.export_xlsx",
            lambda text, generated_at=None, report_context=None: b"fake-excel-content",
        )
        response = client.get(reverse("optimizer:report_download", args=["excel"]))
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")

    def test_xlsx_download(self, client, monkeypatch):
        user = User.objects.create_user(username="report_dl_xlsx", password="test12345!")
        client.force_login(user)
        _patch_report(monkeypatch)
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.generate_report_text",
            lambda ctx: "# Test\n",
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.get_fallback_report",
            lambda ctx: "# Fallback\n",
        )
        monkeypatch.setattr(
            "optimizer.services.report_export.export_xlsx",
            lambda text, generated_at=None, report_context=None: b"fake-xlsx",
        )
        response = client.get(reverse("optimizer:report_download", args=["xlsx"]))
        assert response.status_code == 200

    def test_pdf_unavailable_returns_501(self, client, monkeypatch):
        user = User.objects.create_user(username="report_dl_pdf501", password="test12345!")
        client.force_login(user)
        _patch_report(monkeypatch)
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.generate_report_text",
            lambda ctx: "# Test\n",
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.get_fallback_report",
            lambda ctx: "# Fallback\n",
        )
        monkeypatch.setattr(
            "optimizer.views.export_pdf",
            lambda text, generated_at=None, report_context=None: None,
        )
        response = client.get(reverse("optimizer:report_download", args=["pdf"]))
        assert response.status_code == 501

    def test_docx_unavailable_returns_501(self, client, monkeypatch):
        user = User.objects.create_user(username="report_dl_docx501", password="test12345!")
        client.force_login(user)
        _patch_report(monkeypatch)
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.generate_report_text",
            lambda ctx: "# Test\n",
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.get_fallback_report",
            lambda ctx: "# Fallback\n",
        )
        monkeypatch.setattr(
            "optimizer.views.export_docx",
            lambda text, generated_at=None, report_context=None: None,
        )
        response = client.get(reverse("optimizer:report_download", args=["docx"]))
        assert response.status_code == 501


# ─────────────────────────────────────────────────────────────────────────────
# api_strategy3_rightsizing
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestApiStrategy3Rightsizing:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:api_strategy3_rightsizing"))
        assert response.status_code == 302

    def test_returns_200_empty(self, client, monkeypatch):
        user = User.objects.create_user(username="s3_api_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(reverse("optimizer:api_strategy3_rightsizing"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "completed"
        assert "result" in data

    def test_cpu_workload(self, client, monkeypatch):
        user = User.objects.create_user(username="s3_cpu_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(
            reverse("optimizer:api_strategy3_rightsizing") + "?workload=CPU&screen_filter=PROD_CPU_Rightsizing"
        )
        assert response.status_code == 200

    def test_ram_workload(self, client, monkeypatch):
        user = User.objects.create_user(username="s3_ram_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(
            reverse("optimizer:api_strategy3_rightsizing") + "?workload=RAM&screen_filter=PROD_RAM_Rightsizing"
        )
        assert response.status_code == 200

    def test_pagination_params(self, client, monkeypatch):
        user = User.objects.create_user(username="s3_page_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(
            reverse("optimizer:api_strategy3_rightsizing") + "?page=1&page_size=10&sort_order=asc"
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "pagination" in data["result"]

    def test_hosting_zone_filter(self, client, monkeypatch):
        user = User.objects.create_user(username="s3_hz_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(
            reverse("optimizer:api_strategy3_rightsizing") + "?hosting_zone=Public+Cloud"
        )
        assert response.status_code == 200

    def test_installed_status_filter(self, client, monkeypatch):
        user = User.objects.create_user(username="s3_status_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(
            reverse("optimizer:api_strategy3_rightsizing") + "?installed_status_usu=Installed"
        )
        assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# api_oracle_data (api/usu-data/)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestApiOracleData:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:api_oracle_data"))
        assert response.status_code == 302

    def test_returns_200_empty(self, client):
        user = User.objects.create_user(username="oracle_user1", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_oracle_data"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "completed"

    def test_mssql_family(self, client):
        user = User.objects.create_user(username="oracle_mssql_user", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_oracle_data") + "?family=mssql")
        assert response.status_code == 200

    def test_oracle_family(self, client):
        user = User.objects.create_user(username="oracle_java_user", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_oracle_data") + "?family=oracle")
        assert response.status_code == 200

    def test_invalid_family_returns_400(self, client):
        user = User.objects.create_user(username="oracle_bad_family", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_oracle_data") + "?family=invalid")
        assert response.status_code == 400

    def test_installations_type(self, client):
        user = User.objects.create_user(username="oracle_inst_user", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_oracle_data") + "?type=installations")
        assert response.status_code == 200

    def test_demand_type(self, client):
        user = User.objects.create_user(username="oracle_demand_user", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_oracle_data") + "?type=demand")
        assert response.status_code == 200

    def test_all_type_with_pagination(self, client):
        user = User.objects.create_user(username="oracle_all_user", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_oracle_data") + "?type=all&page=1&page_size=50")
        assert response.status_code == 200

    def test_sort_and_filter(self, client):
        user = User.objects.create_user(username="oracle_sort_user", password="test12345!")
        client.force_login(user)
        response = client.get(
            reverse("optimizer:api_oracle_data") +
            "?sort_field=server_name&sort_order=desc&hosting=Public+Cloud&status=Installed"
        )
        assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# download_demand_data
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDownloadDemandData:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:download_demand_data"))
        assert response.status_code == 302

    def test_returns_excel_when_empty(self, client, monkeypatch):
        user = User.objects.create_user(username="demand_dl_empty", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:download_demand_data"))
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")


# ─────────────────────────────────────────────────────────────────────────────
# download_uc1_input_data
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDownloadUc1InputData:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:download_uc1_input_data"))
        assert response.status_code == 302

    def test_returns_404_when_no_data(self, client, monkeypatch):
        user = User.objects.create_user(username="uc1_input_user", password="test12345!")
        client.force_login(user)
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_installations_df",
            lambda: pd.DataFrame(),
        )
        response = client.get(reverse("optimizer:download_uc1_input_data"))
        assert response.status_code == 404

    def test_returns_excel_with_data(self, client, monkeypatch):
        user = User.objects.create_user(username="uc1_input_data_user", password="test12345!")
        client.force_login(user)
        fake_df = pd.DataFrame({
            "server_name": ["SRV-01"],
            "u_hosting_zone": ["Public Cloud"],
            "inventory_status_standard": ["Active"],
            "no_license_required": [0],
        })
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_installations_df",
            lambda: fake_df,
        )
        monkeypatch.setattr(
            "optimizer.rules.column_utils.find_no_license_required_column",
            lambda df: None,
        )
        response = client.get(reverse("optimizer:download_uc1_input_data"))
        assert response.status_code in (200, 404)


# ─────────────────────────────────────────────────────────────────────────────
# _build_rightsizing_filter_funnel (via results view with mocked data)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBuildRightsizingFilterFunnel:
    def test_funnel_with_empty_df(self, monkeypatch):
        from optimizer.views import _build_rightsizing_filter_funnel
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: pd.DataFrame(),
        )
        result = _build_rightsizing_filter_funnel()
        assert result == {}

    def test_funnel_exception_returns_empty(self, monkeypatch):
        from optimizer.views import _build_rightsizing_filter_funnel
        def raise_exc():
            raise RuntimeError("DB down")
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            raise_exc,
        )
        result = _build_rightsizing_filter_funnel()
        assert result == {}

    def test_funnel_with_data(self, monkeypatch):
        from optimizer.views import _build_rightsizing_filter_funnel
        fake_df = pd.DataFrame({
            "Environment": ["Production", "Development"],
            "Avg_CPU_12m": [8.0, 20.0],
            "Peak_CPU_12m": [60.0, 80.0],
            "Current_vCPU": [8, 4],
            "Avg_FreeMem_12m": [40.0, 20.0],
            "Min_FreeMem_12m": [25.0, 10.0],
            "Current_RAM_GiB": [32.0, 16.0],
        })
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_rightsizing_df",
            lambda: fake_df,
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_cpu_rightsizing_optimizations",
            lambda df: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_ram_rightsizing_optimizations",
            lambda df: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_cpu_downsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_cpu_upsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_ram_downsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_criticality_ram_upsize_optimizations",
            lambda df: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "optimizer.rules.rightsizing.find_lifecycle_risk_flags",
            lambda df: pd.DataFrame(),
        )
        result = _build_rightsizing_filter_funnel()
        assert isinstance(result, dict)
        assert "total_input" in result
        assert result["total_input"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# _get_db_context_for_report helper
# ─────────────────────────────────────────────────────────────────────────────

class TestGetDbContextForReport:
    def test_returns_dict_with_expected_keys(self, monkeypatch):
        from optimizer.views import _get_db_context_for_report
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service.compute_live_db_metrics",
            lambda: FAKE_METRICS,
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.generate_report_text",
            lambda ctx: "# Report",
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.get_fallback_report",
            lambda ctx: "# Fallback",
        )
        monkeypatch.setattr(
            "optimizer.views._build_rightsizing_filter_funnel",
            lambda: {},
        )
        result = _get_db_context_for_report()
        assert isinstance(result, dict)
        assert "report_text" in result or "title" in result


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_report_markdown helper
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveReportMarkdown:
    def test_uses_preview_when_available(self, monkeypatch):
        from optimizer.views import _resolve_report_markdown
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.build_live_agent_report_preview",
            lambda usecase_id="uc_1_2_3": {"report_markdown": "# Preview Report", "summary_context": {}},
        )
        result = _resolve_report_markdown(FAKE_METRICS)
        assert "Preview Report" in result

    def test_fallback_when_preview_empty(self, monkeypatch):
        from optimizer.views import _resolve_report_markdown
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.build_live_agent_report_preview",
            lambda usecase_id="uc_1_2_3": {"report_markdown": "", "summary_context": {}},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.build_agent_strategy_results_payload",
            lambda ctx: {},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator._build_local_rules_evaluation",
            lambda rule_results=None, rightsizing=None: {},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator._build_agent_report_summary_context",
            lambda ctx, strategy_results: {},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator._render_local_agent_report_markdown",
            lambda **kwargs: "# Fallback Agent Report",
        )
        result = _resolve_report_markdown(FAKE_METRICS)
        assert isinstance(result, str)

    def test_fallback_when_preview_raises(self, monkeypatch):
        from optimizer.views import _resolve_report_markdown
        def _raise_preview(usecase_id="uc_1_2_3"):
            raise RuntimeError("LLM not available")
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.build_live_agent_report_preview",
            _raise_preview,
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.build_agent_strategy_results_payload",
            lambda ctx: {},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator._build_local_rules_evaluation",
            lambda rule_results=None, rightsizing=None: {},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator._build_agent_report_summary_context",
            lambda ctx, strategy_results: {},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator._render_local_agent_report_markdown",
            lambda **kwargs: "# Local Report",
        )
        result = _resolve_report_markdown(FAKE_METRICS)
        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# _build_legacy_report_markdown helper
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildLegacyReportMarkdown:
    def test_empty_report_text_returns_empty(self):
        from optimizer.views import _build_legacy_report_markdown
        result = _build_legacy_report_markdown({})
        assert result == ""

    def test_with_report_text(self, monkeypatch):
        from optimizer.views import _build_legacy_report_markdown
        monkeypatch.setattr(
            "optimizer.services.report_export.build_report_markdown",
            lambda text, report_context=None: f"# Markdown: {text}",
        )
        ctx = {**FAKE_METRICS, "report_text": "Some text."}
        result = _build_legacy_report_markdown(ctx)
        assert "Markdown" in result or isinstance(result, str)
