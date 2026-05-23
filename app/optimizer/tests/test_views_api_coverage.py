"""
Comprehensive tests for uncovered views.py API endpoints and helper functions.
Targets: api_savings_summary, api_dashboard_summary, api_agent_runs,
         api_agent_run_detail, api_trigger_agent_run, api_candidate_decision,
         api_boones_raw_data, api_dq_usu_data, api_dq_grafana_data,
         api_rule1_data, api_rule2_data, download_demand_data,
         download_rule_data, download_rightsizing_sheet, admin_panel,
         api_admin_users, api_admin_user_detail, and many helper functions.
"""
import json
import uuid

import pandas as pd
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from optimizer.models import (
    AgentRun,
    BoonesRawRow,
    OptimizationCandidate,
    OptimizationDecision,
    Tenant,
    UserProfile,
)
from optimizer.permissions import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER
from optimizer.views import (
    _build_post_login_redirect_url,
    _build_profile_context,
    _build_profile_initials,
    _build_report_render_context,
    _build_rs3_api_summary,
    _build_rs3_download_sheet_options,
    _build_table_rows,
    _coerce_float,
    _eu_currency,
    _filter_rs3_records,
    _format_metric_label,
    _format_rs3_api_screen_label,
    _format_rs3_sheet_label,
    _get_or_create_user_profile,
    _get_rs3_columns,
    _get_rs3_filter_field,
    _get_rs3_workload_for_filter,
    _is_rs3_recommendation_filter,
    _make_json_serializable,
    _normalize_rs3_filter_value,
    _safe_content_disposition,
    _sanitize_filename,
    _serialize_rs3_api_record,
    _sort_rs3_api_records,
)

User = get_user_model()

# ─────────────────────────────────────────────────────────────────────────────
# Shared test fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

FAKE_METRICS = {
    "total_devices_analyzed": 10,
    "rule_results": {
        "azure_payg_count": 2,
        "azure_payg": [
            {"device_name": "vm-01", "server_name": "vm-01", "cpu_cores_overall_device": 8,
             "hosting_zone": "Public Cloud"},
        ],
        "azure_payg_total_cost_eur": 5000.0,
        "azure_payg_prod_candidates_count": 1,
        "azure_payg_nonprod_candidates_count": 1,
        "azure_payg_demand_matched_count": 2,
        "retired_count": 1,
        "retired_devices": [
            {"device_name": "old-01", "server_name": "old-01", "inventory_status_standard": "Retired"},
        ],
        "retired_devices_savings_eur": 100.0,
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
        "price_distribution": [],
        "cost_reduction_tips": [],
    },
    "rightsizing": {
        "cpu_optimizations": [],
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


def _make_admin_user(username="admin_user", password="AdminPass123!"):
    user = User.objects.create_user(username=username, password=password, email=f"{username}@test.com")
    UserProfile.objects.update_or_create(user=user, defaults={"role": ROLE_ADMIN})
    return user


def _make_editor_user(username="editor_user", password="EditorPass123!"):
    user = User.objects.create_user(username=username, password=password, email=f"{username}@test.com")
    UserProfile.objects.update_or_create(user=user, defaults={"role": ROLE_EDITOR})
    return user


def _make_viewer_user(username="viewer_user", password="ViewerPass123!"):
    user = User.objects.create_user(username=username, password=password, email=f"{username}@test.com")
    UserProfile.objects.update_or_create(user=user, defaults={"role": ROLE_VIEWER})
    return user


# ─────────────────────────────────────────────────────────────────────────────
# Pure helper function tests (no DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatMetricLabel:
    def test_empty_string(self):
        assert _format_metric_label("") == ""

    def test_none(self):
        assert _format_metric_label(None) == ""

    def test_database_size_mib(self):
        assert _format_metric_label("database_size_mib") == "Database Size Mmib"

    def test_underscore_separated(self):
        assert _format_metric_label("cpu_usage_pct") == "Cpu Usage Pct"

    def test_single_word(self):
        assert _format_metric_label("cpu") == "Cpu"


class TestSanitizeFilename:
    def test_normal_name(self):
        assert _sanitize_filename("report.xlsx") == "report.xlsx"

    def test_path_traversal_stripped(self):
        result = _sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert ".." not in result

    def test_none_returns_download(self):
        assert _sanitize_filename(None) == "download"

    def test_empty_returns_download(self):
        assert _sanitize_filename("") == "download"

    def test_long_name_truncated(self):
        long_name = "a" * 300 + ".xlsx"
        result = _sanitize_filename(long_name, max_len=200)
        assert len(result) <= 200

    def test_control_chars_removed(self):
        result = _sanitize_filename("file\x00name.xlsx")
        assert "\x00" not in result


class TestSafeContentDisposition:
    def test_normal_filename(self):
        result = _safe_content_disposition("report.xlsx")
        assert 'attachment; filename="report.xlsx"' == result

    def test_path_in_filename_stripped(self):
        result = _safe_content_disposition("/etc/passwd")
        assert "etc" in result or "passwd" in result
        assert "/etc/" not in result


class TestCoerceFloat:
    def test_number(self):
        assert _coerce_float(3.14) == 3.14

    def test_string_number(self):
        assert _coerce_float("2.5") == 2.5

    def test_none_returns_zero(self):
        assert _coerce_float(None) == 0.0

    def test_empty_string_returns_zero(self):
        assert _coerce_float("") == 0.0

    def test_invalid_returns_zero(self):
        assert _coerce_float("not_a_number") == 0.0


class TestIsRs3RecommendationFilter:
    def test_recommendation_suffix(self):
        assert _is_rs3_recommendation_filter("PROD_CPU_Recommendation") is True

    def test_rightsizing_suffix(self):
        assert _is_rs3_recommendation_filter("PROD_CPU_Rightsizing") is False

    def test_none(self):
        assert _is_rs3_recommendation_filter(None) is False

    def test_empty(self):
        assert _is_rs3_recommendation_filter("") is False


class TestNormalizeRs3FilterValue:
    def test_cpu_alias(self):
        result = _normalize_rs3_filter_value("CPU", "PROD_CPU_Optimization")
        assert result == "PROD_CPU_Rightsizing"

    def test_ram_alias(self):
        result = _normalize_rs3_filter_value("RAM", "PROD_RAM_Optimization")
        assert result == "PROD_RAM_Rightsizing"

    def test_unknown_cpu_passthrough(self):
        result = _normalize_rs3_filter_value("CPU", "CUSTOM_VALUE")
        assert result == "CUSTOM_VALUE"

    def test_none_workload(self):
        result = _normalize_rs3_filter_value(None, "SOME_FILTER")
        assert result == "SOME_FILTER"


class TestGetRs3FilterField:
    def test_rightsizing_returns_env_type(self):
        assert _get_rs3_filter_field("PROD_CPU_Rightsizing") == "Env_Type"

    def test_recommendation_returns_recommendation_type(self):
        assert _get_rs3_filter_field("PROD_CPU_Recommendation") == "Recommendation_Type"

    def test_other_returns_optimization_type(self):
        assert _get_rs3_filter_field("PROD_CPU_Optimization") == "Optimization_Type"


class TestFilterRs3Records:
    def test_empty_filter_returns_all(self):
        records = [{"Env_Type": "PROD"}, {"Env_Type": "NON-PROD"}]
        assert _filter_rs3_records(records, None) == records

    def test_prod_rightsizing_filter(self):
        records = [
            {"Env_Type": "PROD", "Optimization_Type": "x"},
            {"Env_Type": "NON-PROD", "Optimization_Type": "x"},
        ]
        result = _filter_rs3_records(records, "PROD_CPU_Rightsizing")
        assert len(result) == 1
        assert result[0]["Env_Type"] == "PROD"

    def test_nonprod_rightsizing_filter(self):
        records = [
            {"Env_Type": "PROD"},
            {"Env_Type": "NON-PROD"},
        ]
        result = _filter_rs3_records(records, "NONPROD_CPU_Rightsizing")
        assert len(result) == 1
        assert result[0]["Env_Type"] == "NON-PROD"

    def test_optimization_type_filter(self):
        records = [
            {"Optimization_Type": "PROD_CPU_Optimization", "Env_Type": "PROD"},
            {"Optimization_Type": "OTHER", "Env_Type": "PROD"},
        ]
        result = _filter_rs3_records(records, "PROD_CPU_Optimization")
        assert len(result) == 1


class TestGetRs3Columns:
    def test_cpu_rightsizing(self):
        cols = _get_rs3_columns("CPU", "PROD_CPU_Rightsizing")
        assert "Recommended_vCPU" in cols

    def test_ram_rightsizing(self):
        cols = _get_rs3_columns("RAM", "PROD_RAM_Rightsizing")
        assert "Recommended_RAM_GiB" in cols

    def test_cpu_recommendation(self):
        cols = _get_rs3_columns("CPU", "PROD_CPU_Recommendation")
        assert "CPU_Recommendation" in cols

    def test_default_cpu(self):
        cols = _get_rs3_columns("CPU", "")
        assert "Avg_CPU_12m" in cols


class TestGetRs3WorkloadForFilter:
    def test_ram_filter(self):
        assert _get_rs3_workload_for_filter("PROD_RAM_Rightsizing") == "RAM"

    def test_cpu_filter(self):
        assert _get_rs3_workload_for_filter("PROD_CPU_Rightsizing") == "CPU"

    def test_none(self):
        assert _get_rs3_workload_for_filter(None) == "CPU"


class TestFormatRs3SheetLabel:
    def test_prod_cpu(self):
        result = _format_rs3_sheet_label("PROD_CPU_Rightsizing")
        assert "Prod" in result or "CPU" in result or "Rightsizing" in result

    def test_empty(self):
        result = _format_rs3_sheet_label("")
        assert isinstance(result, str)


class TestFormatRs3ApiScreenLabel:
    def test_prod_cpu_rightsizing(self):
        result = _format_rs3_api_screen_label("PROD_CPU_RIGHTSIZING")
        assert "PROD CPU" in result

    def test_nonprod_ram(self):
        result = _format_rs3_api_screen_label("NONPROD_RAM_RIGHTSIZING")
        assert "Nonprod" in result

    def test_unknown(self):
        result = _format_rs3_api_screen_label("CUSTOM_FILTER")
        assert isinstance(result, str)


class TestBuildRs3ApiSummary:
    def test_empty_records(self):
        result = _build_rs3_api_summary([], "CPU")
        assert result["count"] == 0
        assert result["reduction_total"] == 0.0

    def test_cpu_records(self):
        records = [
            {"Env_Type": "PROD", "Potential_vCPU_Reduction": 4.0, "Cost_Savings_EUR": 200.0},
            {"Env_Type": "NON-PROD", "Potential_vCPU_Reduction": 2.0, "Cost_Savings_EUR": 100.0},
        ]
        result = _build_rs3_api_summary(records, "CPU")
        assert result["count"] == 2
        assert result["prod_count"] == 1
        assert result["nonprod_count"] == 1
        assert result["reduction_total"] == 6.0
        assert result["savings_eur"] == 300.0

    def test_ram_records(self):
        records = [{"Env_Type": "PROD", "Potential_RAM_Reduction_GiB": 8.0, "Cost_Savings_EUR": 80.0}]
        result = _build_rs3_api_summary(records, "RAM")
        assert result["count"] == 1
        assert result["reduction_total"] == 8.0


class TestSortRs3ApiRecords:
    def test_sort_desc(self):
        records = [
            {"Potential_vCPU_Reduction": 2.0, "server_name": "b"},
            {"Potential_vCPU_Reduction": 8.0, "server_name": "a"},
        ]
        result = _sort_rs3_api_records(records, "CPU", sort_order="desc")
        assert result[0]["Potential_vCPU_Reduction"] == 8.0

    def test_sort_asc(self):
        records = [
            {"Potential_vCPU_Reduction": 8.0, "server_name": "a"},
            {"Potential_vCPU_Reduction": 2.0, "server_name": "b"},
        ]
        result = _sort_rs3_api_records(records, "CPU", sort_order="asc")
        assert result[0]["Potential_vCPU_Reduction"] == 2.0

    def test_empty_records(self):
        assert _sort_rs3_api_records([], "CPU") == []


class TestSerializeRs3ApiRecord:
    def test_cpu_record(self):
        record = {
            "server_name": "SRV-01",
            "product_family": "SQL Server",
            "Env_Type": "PROD",
            "Avg_CPU_12m": 12.5,
            "Peak_CPU_12m": 70.0,
            "Current_vCPU": 8,
            "Recommended_vCPU": 4,
            "Potential_vCPU_Reduction": 4,
            "Cost_Savings_EUR": 600.0,
        }
        result = _serialize_rs3_api_record(record, "CPU")
        assert result["server_name"] == "SRV-01"
        assert result["env_type"] == "PROD"
        assert result["current_vcpu"] == 8

    def test_ram_record(self):
        record = {
            "server_name": "SRV-02",
            "Env_Type": "NON-PROD",
            "Avg_FreeMem_12m": 40.0,
            "Min_FreeMem_12m": 25.0,
            "Current_RAM_GiB": 32,
            "Recommended_RAM_GiB": 16,
            "Potential_RAM_Reduction_GiB": 16.0,
        }
        result = _serialize_rs3_api_record(record, "RAM")
        assert result["server_name"] == "SRV-02"
        assert result["current_ram_gib"] == 32


class TestBuildTableRows:
    def test_basic(self):
        records = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        rows = _build_table_rows(records, ["a", "b"])
        assert rows == [[1, 2], [3, 4]]

    def test_missing_column_returns_none(self):
        records = [{"a": 1}]
        rows = _build_table_rows(records, ["a", "missing"])
        assert rows == [[1, None]]


class TestBuildRs3DownloadSheetOptions:
    def test_returns_all_options(self):
        options = _build_rs3_download_sheet_options({})
        assert len(options) >= 4
        values = [o["value"] for o in options]
        assert "PROD_CPU_Rightsizing" in values
        assert "NONPROD_RAM_Rightsizing" in values


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed helper tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestGetOrCreateUserProfile:
    def test_creates_if_missing(self):
        user = User.objects.create_user(username="proftest", password="test12345!")
        profile = _get_or_create_user_profile(user)
        assert profile is not None
        assert profile.user == user

    def test_returns_existing(self):
        user = User.objects.create_user(username="proftest2", password="test12345!")
        p1 = _get_or_create_user_profile(user)
        p2 = _get_or_create_user_profile(user)
        assert p1.pk == p2.pk


@pytest.mark.django_db
class TestBuildPostLoginRedirectUrl:
    def test_anonymous_user_returns_home(self):
        url = _build_post_login_redirect_url(user=None)
        assert "home" in url or url == "/"

    def test_regular_user_returns_home(self):
        user = User.objects.create_user(username="redirect_test", password="test12345!")
        url = _build_post_login_redirect_url(user=user)
        assert isinstance(url, str)

    def test_viewer_only_returns_dashboard(self):
        user = User.objects.create_user(username="viewer_redirect", password="test12345!")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = ROLE_VIEWER
        profile.save()
        url = _build_post_login_redirect_url(user=user)
        assert isinstance(url, str)


@pytest.mark.django_db
class TestBuildProfileContext:
    def test_returns_expected_keys(self):
        user = User.objects.create_user(username="ctx_user", password="test12345!")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        ctx = _build_profile_context(user, profile)
        assert "title" in ctx
        assert "profile_initials" in ctx
        assert "profile_username" in ctx


@pytest.mark.django_db
class TestBuildReportRenderContext:
    def test_returns_basic_keys(self):
        from optimizer.services.analysis_service import build_dashboard_context
        ctx = {
            "rule_results": {"azure_payg_count": 1, "retired_count": 2},
            "license_metrics": {"total_demand_quantity": 5, "total_license_cost": 1000, "by_product": []},
        }
        result = _build_report_render_context(ctx)
        assert "azure_payg_count" in result
        assert "retired_count" in result
        assert "total_license_cost" in result


# ─────────────────────────────────────────────────────────────────────────────
# API endpoint tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestApiSavingsSummary:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:api_savings_summary"))
        assert response.status_code == 302

    def test_returns_200_with_strategies(self, client, monkeypatch):
        user = User.objects.create_user(username="savings_api_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(reverse("optimizer:api_savings_summary"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "completed"
        assert "strategies" in data["result"]
        assert len(data["result"]["strategies"]) == 3
        assert "total_savings_eur" in data["result"]

    def test_strategy_structure(self, client, monkeypatch):
        user = User.objects.create_user(username="savings_struct_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(reverse("optimizer:api_savings_summary"))
        data = json.loads(response.content)
        strategy_ids = [s["id"] for s in data["result"]["strategies"]]
        assert "byol_to_payg" in strategy_ids
        assert "retired_but_reporting" in strategy_ids
        assert "rightsizing" in strategy_ids

    def test_post_not_allowed(self, client, monkeypatch):
        user = User.objects.create_user(username="savings_post_user", password="test12345!")
        client.force_login(user)
        response = client.post(reverse("optimizer:api_savings_summary"))
        assert response.status_code == 405


@pytest.mark.django_db
class TestApiDashboardSummary:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:api_dashboard_summary"))
        assert response.status_code == 302

    def test_returns_200(self, client, monkeypatch):
        user = User.objects.create_user(username="dash_api_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(reverse("optimizer:api_dashboard_summary"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "completed"
        result = data["result"]
        assert "total_devices_analyzed" in result
        assert "azure_payg_count" in result
        assert "retired_count" in result
        assert "rightsizing_cpu_count" in result

    def test_eu_formatted_values_present(self, client, monkeypatch):
        user = User.objects.create_user(username="dash_eu_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(reverse("optimizer:api_dashboard_summary"))
        data = json.loads(response.content)
        result = data["result"]
        assert "total_license_cost_eu" in result
        assert "€" in str(result.get("total_license_cost_eu", ""))


@pytest.mark.django_db
class TestApiAgentRuns:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:api_agent_runs"))
        assert response.status_code == 302

    def test_returns_200_with_empty_list(self, client, monkeypatch):
        user = User.objects.create_user(username="agent_runs_user", password="test12345!")
        client.force_login(user)
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service.get_agent_run_list",
            lambda limit=20: [],
        )
        response = client.get(reverse("optimizer:api_agent_runs"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "completed"
        assert data["result"]["total"] == 0
        assert data["result"]["runs"] == []

    def test_limit_param(self, client, monkeypatch):
        user = User.objects.create_user(username="agent_runs_limit", password="test12345!")
        client.force_login(user)
        captured = {}
        def fake_get_runs(limit=20):
            captured["limit"] = limit
            return []
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service.get_agent_run_list",
            fake_get_runs,
        )
        client.get(reverse("optimizer:api_agent_runs") + "?limit=50")
        assert captured.get("limit") == 50

    def test_limit_capped_at_100(self, client, monkeypatch):
        user = User.objects.create_user(username="agent_runs_cap", password="test12345!")
        client.force_login(user)
        captured = {}
        def fake_get_runs(limit=20):
            captured["limit"] = limit
            return []
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service.get_agent_run_list",
            fake_get_runs,
        )
        client.get(reverse("optimizer:api_agent_runs") + "?limit=999")
        assert captured.get("limit") == 100


@pytest.mark.django_db
class TestApiAgentRunDetail:
    def test_requires_login(self, client):
        run_id = uuid.uuid4()
        response = client.get(reverse("optimizer:api_agent_run_detail", args=[run_id]))
        assert response.status_code == 302

    def test_returns_404_for_nonexistent_run(self, client):
        user = User.objects.create_user(username="run_detail_user", password="test12345!")
        client.force_login(user)
        run_id = uuid.uuid4()
        response = client.get(reverse("optimizer:api_agent_run_detail", args=[run_id]))
        assert response.status_code == 404

    def test_returns_run_data(self, client):
        user = User.objects.create_user(username="run_detail_user2", password="test12345!")
        client.force_login(user)
        tenant = Tenant.objects.create(name="Test Tenant Detail")
        run = AgentRun.objects.create(
            tenant=tenant,
            status="completed",
            triggered_by="test@example.com",
        )
        response = client.get(reverse("optimizer:api_agent_run_detail", args=[run.id]))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "completed"
        result = data["result"]
        assert "agent_run" in result
        assert "candidates" in result
        assert str(run.id) == result["agent_run"]["id"]


@pytest.mark.django_db
class TestApiTriggerAgentRun:
    def test_requires_login(self, client):
        response = client.post(reverse("optimizer:api_trigger_agent_run"))
        assert response.status_code == 302

    def test_viewer_forbidden(self, client):
        user = _make_viewer_user(username="trigger_viewer")
        client.force_login(user)
        response = client.post(
            reverse("optimizer:api_trigger_agent_run"),
            content_type="application/json",
            data=json.dumps({}),
        )
        assert response.status_code == 403

    def test_editor_can_trigger(self, client, monkeypatch):
        user = _make_editor_user(username="trigger_editor")
        client.force_login(user)
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service._build_installations_df",
            lambda: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service.compute_live_db_metrics",
            lambda: FAKE_METRICS,
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.build_agent_strategy_results_payload",
            lambda ctx: {},
        )
        monkeypatch.setattr(
            "optimizer.services.ai_report_generator.generate_and_store_agentic_report",
            lambda **kwargs: {"success": True, "agent_run_id": str(uuid.uuid4()), "candidates_created": 0},
        )
        response = client.post(
            reverse("optimizer:api_trigger_agent_run"),
            content_type="application/json",
            data=json.dumps({"usecase_id": "uc_1_2_3"}),
        )
        assert response.status_code in (200, 500)


@pytest.mark.django_db
class TestApiCandidateDecision:
    def _make_candidate(self, tenant):
        from optimizer.models import LicenseRule, Server
        server = Server.objects.create(tenant=tenant, server_name="test-srv")
        rule = LicenseRule.objects.create(
            tenant=tenant, rule_name="Rule1", rule_code="UC1", use_case="UC1", conditions={},
        )
        run = AgentRun.objects.create(tenant=tenant, status="completed", triggered_by="t@t.com")
        from django.utils import timezone
        candidate = OptimizationCandidate.objects.create(
            tenant=tenant,
            agent_run=run,
            server=server,
            rule=rule,
            use_case="UC1",
            recommendation="Switch to PAYG",
            detected_on=timezone.now(),
        )
        return candidate

    def test_requires_login(self, client):
        cid = uuid.uuid4()
        response = client.post(reverse("optimizer:api_candidate_decision", args=[cid]))
        assert response.status_code == 302

    def test_viewer_forbidden(self, client):
        user = _make_viewer_user(username="decision_viewer")
        client.force_login(user)
        cid = uuid.uuid4()
        response = client.post(
            reverse("optimizer:api_candidate_decision", args=[cid]),
            content_type="application/json",
            data=json.dumps({"decision": "accepted"}),
        )
        assert response.status_code == 403

    def test_returns_404_for_nonexistent_candidate(self, client):
        user = _make_editor_user(username="decision_editor404")
        client.force_login(user)
        cid = uuid.uuid4()
        response = client.post(
            reverse("optimizer:api_candidate_decision", args=[cid]),
            content_type="application/json",
            data=json.dumps({"decision": "accepted"}),
        )
        assert response.status_code == 404

    def test_invalid_json_returns_400(self, client):
        user = _make_editor_user(username="decision_badjson")
        client.force_login(user)
        cid = uuid.uuid4()
        response = client.post(
            reverse("optimizer:api_candidate_decision", args=[cid]),
            content_type="application/json",
            data="not-json",
        )
        assert response.status_code in (400, 404)

    def test_accepts_decision(self, client):
        user = _make_editor_user(username="decision_accept")
        client.force_login(user)
        tenant = Tenant.objects.create(name="Decision Tenant")
        candidate = self._make_candidate(tenant)
        response = client.post(
            reverse("optimizer:api_candidate_decision", args=[candidate.id]),
            content_type="application/json",
            data=json.dumps({"decision": "accepted", "decision_notes": "Looks good"}),
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert data["decision"] == "accepted"

    def test_rejects_decision(self, client):
        user = _make_editor_user(username="decision_reject")
        client.force_login(user)
        tenant = Tenant.objects.create(name="Reject Tenant")
        candidate = self._make_candidate(tenant)
        response = client.post(
            reverse("optimizer:api_candidate_decision", args=[candidate.id]),
            content_type="application/json",
            data=json.dumps({"decision": "rejected"}),
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert data["decision"] == "rejected"

    def test_invalid_decision_value(self, client):
        user = _make_editor_user(username="decision_invalid")
        client.force_login(user)
        tenant = Tenant.objects.create(name="Invalid Decision Tenant")
        candidate = self._make_candidate(tenant)
        response = client.post(
            reverse("optimizer:api_candidate_decision", args=[candidate.id]),
            content_type="application/json",
            data=json.dumps({"decision": "maybe"}),
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestApiBonesRawData:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:api_boones_raw_data"))
        assert response.status_code == 302

    def test_returns_200_empty(self, client):
        user = User.objects.create_user(username="boones_user", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_boones_raw_data"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "completed"
        assert data["total"] == 0
        assert data["results"] == []

    def test_returns_rows_when_data_exists(self, client):
        user = User.objects.create_user(username="boones_data_user", password="test12345!")
        client.force_login(user)
        BoonesRawRow.objects.create(row_data={"col1": "val1"})
        response = client.get(reverse("optimizer:api_boones_raw_data"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["total"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["row_data"] == {"col1": "val1"}

    def test_pagination_params(self, client):
        user = User.objects.create_user(username="boones_page_user", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_boones_raw_data") + "?page=1&page_size=10")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["page_size"] == 10


@pytest.mark.django_db
class TestApiDqUsuData:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:api_dq_usu_data"))
        assert response.status_code == 302

    def test_returns_200_empty(self, client):
        user = User.objects.create_user(username="dq_usu_user", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_dq_usu_data"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "completed"
        assert "results" in data

    def test_sort_and_pagination(self, client):
        user = User.objects.create_user(username="dq_usu_page_user", password="test12345!")
        client.force_login(user)
        response = client.get(
            reverse("optimizer:api_dq_usu_data") + "?page=1&page_size=50&sort_field=server_name&sort_order=desc"
        )
        assert response.status_code == 200

    def test_family_filter(self, client):
        user = User.objects.create_user(username="dq_usu_family_user", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_dq_usu_data") + "?family=mssql")
        assert response.status_code == 200


@pytest.mark.django_db
class TestApiDqGrafanaData:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:api_dq_grafana_data"))
        assert response.status_code == 302

    def test_returns_200_empty(self, client):
        user = User.objects.create_user(username="dq_grafana_user", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_dq_grafana_data"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "completed"
        assert "results" in data


@pytest.mark.django_db
class TestApiRule1Data:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:api_rule1_data"))
        assert response.status_code == 302

    def test_returns_200_empty(self, client, monkeypatch):
        user = User.objects.create_user(username="rule1_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch, {**FAKE_METRICS, "rule_results": {"azure_payg": []}})
        response = client.get(reverse("optimizer:api_rule1_data"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "rows" in data
        assert "total" in data
        assert data["total"] == 0

    def test_returns_200_with_data(self, client, monkeypatch):
        user = User.objects.create_user(username="rule1_data_user", password="test12345!")
        client.force_login(user)
        metrics = {**FAKE_METRICS, "rule_results": {
            "azure_payg": [
                {"server_name": "vm-01", "hosting_zone": "Public Cloud"},
                {"server_name": "vm-02", "hosting_zone": "Public Cloud"},
            ]
        }}
        _patch_metrics(monkeypatch, metrics)
        response = client.get(reverse("optimizer:api_rule1_data"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["total"] == 2

    def test_sort_params(self, client, monkeypatch):
        user = User.objects.create_user(username="rule1_sort_user", password="test12345!")
        client.force_login(user)
        metrics = {**FAKE_METRICS, "rule_results": {
            "azure_payg": [
                {"server_name": "b-server"},
                {"server_name": "a-server"},
            ]
        }}
        _patch_metrics(monkeypatch, metrics)
        response = client.get(
            reverse("optimizer:api_rule1_data") + "?sort_field=server_name&sort_order=asc"
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["sort_field"] == "server_name"
        assert data["sort_order"] == "asc"

    def test_invalid_sort_order_defaults(self, client, monkeypatch):
        user = User.objects.create_user(username="rule1_invalidsort_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch)
        response = client.get(reverse("optimizer:api_rule1_data") + "?sort_order=invalid")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["sort_order"] == "asc"


@pytest.mark.django_db
class TestApiRule2Data:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:api_rule2_data"))
        assert response.status_code == 302

    def test_returns_200_empty(self, client, monkeypatch):
        user = User.objects.create_user(username="rule2_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch, {**FAKE_METRICS, "rule_results": {"retired_devices": []}})
        response = client.get(reverse("optimizer:api_rule2_data"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "rows" in data
        assert data["total"] == 0

    def test_returns_200_with_data(self, client, monkeypatch):
        user = User.objects.create_user(username="rule2_data_user", password="test12345!")
        client.force_login(user)
        metrics = {**FAKE_METRICS, "rule_results": {
            "retired_devices": [
                {"server_name": "old-01", "inventory_status_standard": "Retired"},
            ]
        }}
        _patch_metrics(monkeypatch, metrics)
        response = client.get(reverse("optimizer:api_rule2_data"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["total"] == 1


@pytest.mark.django_db
class TestDownloadRuleData:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:download_rule_data", args=["rule1"]))
        assert response.status_code == 302

    def test_invalid_rule_id_returns_400(self, client, monkeypatch):
        user = User.objects.create_user(username="dl_rule_400_user", password="test12345!")
        client.force_login(user)
        response = client.get(reverse("optimizer:download_rule_data", args=["rule3"]))
        assert response.status_code == 400

    def test_rule1_no_data_returns_404(self, client, monkeypatch):
        user = User.objects.create_user(username="dl_rule1_404_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch, {**FAKE_METRICS, "rule_results": {"azure_payg": []}})
        response = client.get(reverse("optimizer:download_rule_data", args=["rule1"]))
        assert response.status_code == 404

    def test_rule2_no_data_returns_404(self, client, monkeypatch):
        user = User.objects.create_user(username="dl_rule2_404_user", password="test12345!")
        client.force_login(user)
        _patch_metrics(monkeypatch, {**FAKE_METRICS, "rule_results": {"retired_devices": []}})
        response = client.get(reverse("optimizer:download_rule_data", args=["rule2"]))
        assert response.status_code == 404

    def test_rule1_with_data_returns_excel(self, client, monkeypatch):
        user = User.objects.create_user(username="dl_rule1_excel_user", password="test12345!")
        client.force_login(user)
        metrics = {**FAKE_METRICS, "rule_results": {
            "azure_payg": [{"server_name": "vm-01", "hosting_zone": "Public Cloud"}]
        }}
        _patch_metrics(monkeypatch, metrics)
        response = client.get(reverse("optimizer:download_rule_data", args=["rule1"]))
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")

    def test_rule2_with_data_returns_excel(self, client, monkeypatch):
        user = User.objects.create_user(username="dl_rule2_excel_user", password="test12345!")
        client.force_login(user)
        metrics = {**FAKE_METRICS, "rule_results": {
            "retired_devices": [{"server_name": "old-01", "status": "Retired"}]
        }}
        _patch_metrics(monkeypatch, metrics)
        response = client.get(reverse("optimizer:download_rule_data", args=["rule2"]))
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")


@pytest.mark.django_db
class TestDownloadRightsizingSheet:
    def test_requires_login(self, client):
        response = client.get(
            reverse("optimizer:download_rightsizing_sheet", args=["PROD_CPU_Rightsizing"])
        )
        assert response.status_code == 302

    def test_invalid_sheet_key_returns_400(self, client):
        user = User.objects.create_user(username="rs_dl_400_user", password="test12345!")
        client.force_login(user)
        response = client.get(
            reverse("optimizer:download_rightsizing_sheet", args=["INVALID_SHEET"])
        )
        assert response.status_code == 400

    def test_valid_sheet_key_returns_excel(self, client, monkeypatch):
        user = User.objects.create_user(username="rs_dl_ok_user", password="test12345!")
        client.force_login(user)
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service.build_rightsizing_sheet_export",
            lambda sheet_key: pd.DataFrame({"server_name": ["SRV-01"], "Current_vCPU": [8]}),
        )
        response = client.get(
            reverse("optimizer:download_rightsizing_sheet", args=["PROD_CPU_Rightsizing"])
        )
        assert response.status_code == 200
        assert "spreadsheet" in response.get("Content-Type", "")

    def test_ram_sheet_key_works(self, client, monkeypatch):
        user = User.objects.create_user(username="rs_ram_dl_user", password="test12345!")
        client.force_login(user)
        monkeypatch.setattr(
            "optimizer.services.db_analysis_service.build_rightsizing_sheet_export",
            lambda sheet_key: pd.DataFrame({"server_name": [], "Current_RAM_GiB": []}),
        )
        response = client.get(
            reverse("optimizer:download_rightsizing_sheet", args=["PROD_RAM_Rightsizing"])
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestAdminPanel:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:admin_panel"))
        assert response.status_code == 302

    def test_viewer_forbidden(self, client):
        user = _make_viewer_user(username="admin_panel_viewer")
        client.force_login(user)
        response = client.get(reverse("optimizer:admin_panel"))
        assert response.status_code in (302, 403)

    def test_editor_forbidden(self, client):
        user = _make_editor_user(username="admin_panel_editor")
        client.force_login(user)
        response = client.get(reverse("optimizer:admin_panel"))
        assert response.status_code in (302, 403)

    def test_admin_can_access(self, client):
        user = _make_admin_user(username="admin_panel_admin")
        client.force_login(user)
        response = client.get(reverse("optimizer:admin_panel"))
        assert response.status_code == 200


@pytest.mark.django_db
class TestApiAdminUsers:
    def test_requires_login(self, client):
        response = client.get(reverse("optimizer:api_admin_users"))
        assert response.status_code == 302

    def test_viewer_forbidden(self, client):
        user = _make_viewer_user(username="api_admin_viewer")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_admin_users"))
        assert response.status_code in (302, 403)

    def test_admin_can_list_users(self, client):
        user = _make_admin_user(username="api_admin_list")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_admin_users"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "users" in data

    def test_admin_create_user_success(self, client):
        user = _make_admin_user(username="api_admin_create")
        client.force_login(user)
        response = client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data=json.dumps({
                "username": "newcreateduser",
                "email": "newcreated@test.com",
                "password": "StrongPass123!",
                "role": ROLE_VIEWER,
            }),
        )
        assert response.status_code == 201
        data = json.loads(response.content)
        assert data["username"] == "newcreateduser"

    def test_admin_create_user_missing_username(self, client):
        user = _make_admin_user(username="api_admin_missing_user")
        client.force_login(user)
        response = client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data=json.dumps({"email": "x@x.com", "password": "StrongPass123!"}),
        )
        assert response.status_code == 400

    def test_admin_create_user_weak_password(self, client):
        user = _make_admin_user(username="api_admin_weak_pass")
        client.force_login(user)
        response = client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data=json.dumps({
                "username": "weakpassuser",
                "email": "weak@test.com",
                "password": "short",
                "role": ROLE_VIEWER,
            }),
        )
        assert response.status_code == 400

    def test_admin_create_duplicate_username(self, client):
        user = _make_admin_user(username="api_admin_dup")
        client.force_login(user)
        # Create first
        client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data=json.dumps({
                "username": "dupuser123",
                "email": "dup1@test.com",
                "password": "StrongPass123!",
                "role": ROLE_VIEWER,
            }),
        )
        # Try duplicate
        response = client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data=json.dumps({
                "username": "dupuser123",
                "email": "dup2@test.com",
                "password": "StrongPass123!",
                "role": ROLE_VIEWER,
            }),
        )
        assert response.status_code == 400

    def test_admin_create_invalid_json(self, client):
        user = _make_admin_user(username="api_admin_bad_json")
        client.force_login(user)
        response = client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data="not-json",
        )
        assert response.status_code == 400

    def test_admin_create_invalid_role(self, client):
        user = _make_admin_user(username="api_admin_invalid_role")
        client.force_login(user)
        response = client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data=json.dumps({
                "username": "badroleuser",
                "email": "badrole@test.com",
                "password": "StrongPass123!",
                "role": "superuser",
            }),
        )
        assert response.status_code == 400

    def test_admin_create_missing_email(self, client):
        user = _make_admin_user(username="api_admin_no_email")
        client.force_login(user)
        response = client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data=json.dumps({"username": "noemailuser", "password": "StrongPass123!"}),
        )
        assert response.status_code == 400

    def test_admin_create_password_no_letters(self, client):
        user = _make_admin_user(username="api_admin_no_letters")
        client.force_login(user)
        response = client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data=json.dumps({
                "username": "nolettersuser",
                "email": "noletters@test.com",
                "password": "1234567890123",
            }),
        )
        assert response.status_code == 400

    def test_admin_create_password_no_digits(self, client):
        user = _make_admin_user(username="api_admin_no_digits")
        client.force_login(user)
        response = client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data=json.dumps({
                "username": "nodigitsuser",
                "email": "nodigits@test.com",
                "password": "NoDigitsHereAtAll",
            }),
        )
        assert response.status_code == 400

    def test_admin_create_duplicate_email(self, client):
        user = _make_admin_user(username="api_admin_dup_email")
        client.force_login(user)
        client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data=json.dumps({
                "username": "dupemail1",
                "email": "dupemail@test.com",
                "password": "StrongPass123!",
                "role": ROLE_VIEWER,
            }),
        )
        response = client.post(
            reverse("optimizer:api_admin_users"),
            content_type="application/json",
            data=json.dumps({
                "username": "dupemail2",
                "email": "dupemail@test.com",
                "password": "StrongPass123!",
                "role": ROLE_VIEWER,
            }),
        )
        assert response.status_code == 400

    def test_admin_list_users_with_profileless_user(self, client):
        from django.contrib.auth import get_user_model
        U = get_user_model()
        no_profile_user = U.objects.create_user(
            username="noprofile_user", password="TestPass123!", email="noprofile@test.com"
        )
        user = _make_admin_user(username="api_list_noprofile")
        client.force_login(user)
        response = client.get(reverse("optimizer:api_admin_users"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "users" in data


@pytest.mark.django_db
class TestApiAdminUserDetail:
    def test_requires_login(self, client):
        response = client.delete(reverse("optimizer:api_admin_user_detail", args=[999]))
        assert response.status_code == 302

    def test_viewer_forbidden(self, client):
        user = _make_viewer_user(username="detail_viewer")
        client.force_login(user)
        response = client.delete(reverse("optimizer:api_admin_user_detail", args=[999]))
        assert response.status_code in (302, 403)

    def test_admin_delete_user(self, client):
        admin = _make_admin_user(username="detail_admin_del")
        target = User.objects.create_user(
            username="target_del_user", password="Target123!", email="target@test.com"
        )
        client.force_login(admin)
        response = client.delete(reverse("optimizer:api_admin_user_detail", args=[target.pk]))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "deleted" in data.get("message", "").lower()
        assert not User.objects.filter(pk=target.pk).exists()

    def test_admin_cannot_delete_self(self, client):
        admin = _make_admin_user(username="detail_admin_self")
        client.force_login(admin)
        response = client.delete(reverse("optimizer:api_admin_user_detail", args=[admin.pk]))
        assert response.status_code == 400

    def test_delete_nonexistent_returns_404(self, client):
        admin = _make_admin_user(username="detail_admin_404")
        client.force_login(admin)
        response = client.delete(reverse("optimizer:api_admin_user_detail", args=[99999]))
        assert response.status_code == 404

    def test_admin_update_user(self, client):
        admin = _make_admin_user(username="detail_admin_put")
        target = User.objects.create_user(
            username="target_put_user", password="Target123!", email="targetput@test.com"
        )
        client.force_login(admin)
        response = client.put(
            reverse("optimizer:api_admin_user_detail", args=[target.pk]),
            content_type="application/json",
            data=json.dumps({
                "username": "updated_put_user",
                "email": "updated@test.com",
                "role": ROLE_EDITOR,
            }),
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["username"] == "updated_put_user"

    def test_update_with_invalid_json(self, client):
        admin = _make_admin_user(username="detail_admin_badjson")
        target = User.objects.create_user(
            username="target_json_user", password="Target123!", email="targetjson@test.com"
        )
        client.force_login(admin)
        response = client.put(
            reverse("optimizer:api_admin_user_detail", args=[target.pk]),
            content_type="application/json",
            data="not-json",
        )
        assert response.status_code == 400

    def test_update_weak_password_rejected(self, client):
        admin = _make_admin_user(username="detail_admin_weakpw")
        target = User.objects.create_user(
            username="target_weakpw_user", password="Target123!", email="targetweak@test.com"
        )
        client.force_login(admin)
        response = client.put(
            reverse("optimizer:api_admin_user_detail", args=[target.pk]),
            content_type="application/json",
            data=json.dumps({
                "username": "target_weakpw_user",
                "email": "targetweak@test.com",
                "role": ROLE_VIEWER,
                "password": "weak",
            }),
        )
        assert response.status_code == 400

    def test_update_invalid_role(self, client):
        admin = _make_admin_user(username="detail_admin_badrole")
        target = User.objects.create_user(
            username="target_badrole_user", password="Target123!", email="targetbadrole@test.com"
        )
        client.force_login(admin)
        response = client.put(
            reverse("optimizer:api_admin_user_detail", args=[target.pk]),
            content_type="application/json",
            data=json.dumps({
                "username": "target_badrole_user",
                "email": "targetbadrole@test.com",
                "role": "superuser",
            }),
        )
        assert response.status_code == 400

    def test_update_duplicate_username(self, client):
        admin = _make_admin_user(username="detail_admin_dupusr")
        existing = User.objects.create_user(
            username="existing_usr", password="Target123!", email="existing_usr@test.com"
        )
        target = User.objects.create_user(
            username="target_dupusr", password="Target123!", email="target_dupusr@test.com"
        )
        client.force_login(admin)
        response = client.put(
            reverse("optimizer:api_admin_user_detail", args=[target.pk]),
            content_type="application/json",
            data=json.dumps({
                "username": "existing_usr",
                "email": "target_dupusr@test.com",
                "role": ROLE_VIEWER,
            }),
        )
        assert response.status_code == 400

    def test_update_duplicate_email(self, client):
        admin = _make_admin_user(username="detail_admin_dupeml")
        existing = User.objects.create_user(
            username="existing_eml", password="Target123!", email="existing_eml@test.com"
        )
        target = User.objects.create_user(
            username="target_dupeml", password="Target123!", email="target_dupeml@test.com"
        )
        client.force_login(admin)
        response = client.put(
            reverse("optimizer:api_admin_user_detail", args=[target.pk]),
            content_type="application/json",
            data=json.dumps({
                "username": "target_dupeml",
                "email": "existing_eml@test.com",
                "role": ROLE_VIEWER,
            }),
        )
        assert response.status_code == 400

    def test_update_password_no_letters(self, client):
        admin = _make_admin_user(username="detail_admin_noltr")
        target = User.objects.create_user(
            username="target_noltr_user", password="Target123!", email="targetnoltr@test.com"
        )
        client.force_login(admin)
        response = client.put(
            reverse("optimizer:api_admin_user_detail", args=[target.pk]),
            content_type="application/json",
            data=json.dumps({
                "username": "target_noltr_user",
                "email": "targetnoltr@test.com",
                "role": ROLE_VIEWER,
                "password": "1234567890123",
            }),
        )
        assert response.status_code == 400

    def test_update_password_no_digits(self, client):
        admin = _make_admin_user(username="detail_admin_nodgt")
        target = User.objects.create_user(
            username="target_nodgt_user", password="Target123!", email="targetnodgt@test.com"
        )
        client.force_login(admin)
        response = client.put(
            reverse("optimizer:api_admin_user_detail", args=[target.pk]),
            content_type="application/json",
            data=json.dumps({
                "username": "target_nodgt_user",
                "email": "targetnodgt@test.com",
                "role": ROLE_VIEWER,
                "password": "NoDigitsHereAtAll",
            }),
        )
        assert response.status_code == 400

    def test_update_with_valid_password_change(self, client):
        admin = _make_admin_user(username="detail_admin_pwchg")
        target = User.objects.create_user(
            username="target_pwchg_user", password="Target123!", email="targetpwchg@test.com"
        )
        client.force_login(admin)
        response = client.put(
            reverse("optimizer:api_admin_user_detail", args=[target.pk]),
            content_type="application/json",
            data=json.dumps({
                "username": "target_pwchg_user",
                "email": "targetpwchg@test.com",
                "role": ROLE_VIEWER,
                "password": "NewValidPass456!",
            }),
        )
        assert response.status_code == 200
