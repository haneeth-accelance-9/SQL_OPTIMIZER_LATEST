"""View tests: health, ready, auth redirect."""
from io import BytesIO

import pandas as pd
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from optimizer.models import AgentRun, AnalysisSession, Tenant, UserProfile


@pytest.mark.django_db
def test_health_returns_200(client):
    response = client.get(reverse("optimizer:health"))
    assert response.status_code == 200
    assert b"ok" in response.content


@pytest.mark.django_db
def test_ready_returns_200_when_db_ok(client):
    response = client.get(reverse("optimizer:ready"))
    assert response.status_code == 200
    assert b"ready" in response.content


@pytest.mark.django_db
def test_home_redirects_to_login_when_anonymous(client):
    response = client.get(reverse("optimizer:home"))
    assert response.status_code == 302
    assert reverse("optimizer:login") in response.url


@pytest.mark.django_db
def test_login_redirects_to_results_dashboard_by_default(client):
    user = get_user_model().objects.create_user(username="redirector", password="secret123")

    response = client.post(
        reverse("optimizer:login"),
        {"username": user.username, "password": "secret123"},
    )

    assert response.status_code == 302
    assert response.url == (
        f"{reverse('optimizer:results')}"
        "?rs3_workload=ALL&rs3_filter=PROD_CPU_Optimization&rs3_page=1#dashboard"
    )


@pytest.mark.django_db
def test_login_preserves_next_parameter(client):
    user = get_user_model().objects.create_user(username="nextuser", password="secret123")
    next_url = reverse("optimizer:alerts")

    response = client.post(
        reverse("optimizer:login"),
        {"username": user.username, "password": "secret123", "next": next_url},
    )

    assert response.status_code == 302
    assert response.url == next_url


@pytest.mark.django_db
def test_authenticated_login_page_redirects_to_results_dashboard_by_default(client):
    user = get_user_model().objects.create_user(username="alreadyin", password="secret123")
    client.force_login(user)

    response = client.get(reverse("optimizer:login"))

    assert response.status_code == 302
    assert response.url == (
        f"{reverse('optimizer:results')}"
        "?rs3_workload=ALL&rs3_filter=PROD_CPU_Optimization&rs3_page=1#dashboard"
    )


@pytest.mark.django_db
def test_results_uses_persisted_analysis_data(client):
    user = get_user_model().objects.create_user(username="analyst", password="secret123")
    analysis = AnalysisSession.objects.create(
        user=user,
        file_name="uploaded.xlsx",
        file_path="uploaded.xlsx",
        status="completed",
        result_data={
            "file_name": "customer-analysis.xlsx",
            "sheet_names_used": {"installations": "Installations"},
            "total_devices_analyzed": 42,
            "rule_results": {
                "azure_payg_count": 2,
                "azure_payg": [
                    {"device_name": "vm-01", "cpu_cores_overall_device": 8},
                    {"device_name": "vm-02", "cpu_cores_overall_device": 16},
                ],
                "retired_count": 1,
                "retired_devices": [
                    {"device_name": "old-sql-01", "inventory_status_standard": "Retired"},
                ],
            },
            "license_metrics": {
                "total_demand_quantity": 12,
                "total_license_cost": 345.6,
                "by_product": [],
                "price_distribution": [],
                "cost_reduction_tips": [],
            },
        },
    )

    client.force_login(user)
    session = client.session
    session["optimizer_analysis_id"] = analysis.id
    session.save()

    response = client.get(reverse("optimizer:results"), {"rule1_page": "bad-page", "rule2_page": "5"})

    assert response.status_code == 200
    assert response.context["analysis_id"] == analysis.id
    assert response.context["analysis_source_file_name"] == "customer-analysis.xlsx"
    assert response.context["analysis_sheet_names"] == {"installations": "Installations"}
    assert response.context["total_devices_analyzed"] == 42
    assert response.context["azure_payg_count"] == 2
    assert response.context["retired_count"] == 1
    assert response.context["total_demand_quantity"] == 12
    assert response.context["total_license_cost"] == 345.6
    assert response.context["rule1_page"] == 1
    assert response.context["rule2_page"] == 1
    assert response.context["rule1_keys"] == ["device_name", "cpu_cores_overall_device"]
    assert response.context["rule2_keys"] == ["device_name", "inventory_status_standard"]
    assert response.context["azure_payg_page"] == [["vm-01", 8], ["vm-02", 16]]
    assert response.context["retired_devices_page"] == [["old-sql-01", "Retired"]]


@pytest.mark.django_db
def test_results_applies_rs3_workload_and_screen_selection(client, monkeypatch):
    user = get_user_model().objects.create_user(username="rightsizer", password="secret123")
    client.force_login(user)

    fake_context = {
        "rule_results": {
            "azure_payg_count": 0,
            "azure_payg": [],
            "retired_count": 0,
            "retired_devices": [],
        },
        "license_metrics": {
            "total_demand_quantity": 0,
            "total_license_cost": 0,
            "by_product": [],
            "price_distribution": [],
            "cost_reduction_tips": [],
        },
        "rightsizing": {
            "cpu_optimizations": [
                {
                    "server_name": "prod-sql-01",
                    "Environment": "Production",
                    "Env_Type": "PROD",
                    "Avg_CPU_12m": 8,
                    "Peak_CPU_12m": 55,
                    "Current_vCPU": 8,
                    "Recommended_vCPU": 4,
                    "Potential_vCPU_Reduction": 4,
                    "CPU_Recommendation": "Reduce vCPU by ~50% -> 4",
                    "Optimization_Type": "PROD_CPU_Optimization",
                    "Recommendation_Type": "PROD_CPU_Recommendation",
                }
            ],
            "ram_optimizations": [
                {
                    "server_name": "dev-sql-01",
                    "Environment": "Development",
                    "Env_Type": "NON-PROD",
                    "Avg_FreeMem_12m": 55,
                    "Min_FreeMem_12m": 25,
                    "Current_RAM_GiB": 16,
                    "Recommended_RAM_GiB": 8,
                    "Potential_RAM_Reduction_GiB": 8,
                    "RAM_Recommendation": "Reduce RAM by ~40-60% -> 8 GiB",
                    "Optimization_Type": "NONPROD_RAM_Optimization",
                    "Recommendation_Type": "NONPROD_RAM_Recommendation",
                }
            ],
            "cpu_candidates": [],
            "ram_candidates": [],
            "cpu_filter_options": [
                "PROD_CPU_Optimization",
                "PROD_CPU_Recommendation",
                "NONPROD_CPU_Optimization",
                "NONPROD_CPU_Recommendation",
            ],
            "ram_filter_options": [
                "PROD_RAM_Optimization",
                "PROD_RAM_Recommendation",
                "NONPROD_RAM_Optimization",
                "NONPROD_RAM_Recommendation",
            ],
            "workload_options": ["CPU", "RAM"],
            "default_workload": "CPU",
            "default_filter_by_workload": {
                "CPU": "PROD_CPU_Optimization",
                "RAM": "PROD_RAM_Optimization",
            },
            "screen_filter_options": {
                "CPU": [
                    "PROD_CPU_Optimization",
                    "PROD_CPU_Recommendation",
                    "NONPROD_CPU_Optimization",
                    "NONPROD_CPU_Recommendation",
                ],
                "RAM": [
                    "PROD_RAM_Optimization",
                    "PROD_RAM_Recommendation",
                    "NONPROD_RAM_Optimization",
                    "NONPROD_RAM_Recommendation",
                ],
            },
            "screen_summaries": {
                "CPU": {
                    "PROD_CPU_Optimization": {
                        "count": 1,
                        "prod_count": 1,
                        "nonprod_count": 0,
                        "reduction_total": 4,
                    }
                },
                "RAM": {
                    "NONPROD_RAM_Recommendation": {
                        "count": 1,
                        "prod_count": 0,
                        "nonprod_count": 1,
                        "reduction_total": 8,
                    }
                },
            },
            "cpu_chart_data": [],
            "ram_chart_data": [],
            "cpu_count": 1,
            "cpu_prod_count": 1,
            "cpu_nonprod_count": 0,
            "ram_count": 1,
            "ram_prod_count": 0,
            "ram_nonprod_count": 1,
            "total_vcpu_reduction": 4,
            "total_ram_reduction_gib": 8,
            "error": None,
        },
    }

    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.compute_live_db_metrics",
        lambda: fake_context,
    )

    response = client.get(
        reverse("optimizer:results"),
        {
            "rs3_workload": "RAM",
            "rs3_filter": "NONPROD_RAM_Recommendation",
            "rs3_page": "7",
        },
    )

    assert response.status_code == 200
    assert response.context["rs3_selected_workload"] == "RAM"
    assert response.context["rs3_selected_filter"] == "NONPROD_RAM_Recommendation"
    assert response.context["rs3_page"] == 1
    assert response.context["rs3_filter_options"] == [
        "PROD_RAM_Optimization",
        "PROD_RAM_Recommendation",
        "NONPROD_RAM_Optimization",
        "NONPROD_RAM_Recommendation",
    ]
    assert response.context["rs3_keys"] == [
        "server_name",
        "Environment",
        "Env_Type",
        "Current_RAM_GiB",
        "Recommended_RAM_GiB",
        "RAM_Recommendation",
    ]
    assert response.context["rs3_selected_summary"] == {
        "count": 1,
        "prod_count": 0,
        "nonprod_count": 1,
        "reduction_total": 8,
    }
    assert response.context["rightsizing_selected_page"] == [
        ["dev-sql-01", "Development", "NON-PROD", 16, 8, "Reduce RAM by ~40-60% -> 8 GiB"]
    ]
    assert [option["label"] for option in response.context["download_sheet_options"]] == [
        "Prod Cpu Optimization",
        "Prod Cpu Recommendation",
        "Nonprod Cpu Optimization",
        "Nonprod Cpu Recommendation",
        "Prod Ram Optimization",
        "Prod Ram Recommendation",
        "Nonprod Ram Optimization",
        "Nonprod Ram Recommendation",
    ]


@pytest.mark.django_db
def test_results_keeps_live_uc2_count_visible_even_when_savings_are_zero(client, monkeypatch):
    user = get_user_model().objects.create_user(username="uc2-live", password="secret123")
    client.force_login(user)

    fake_context = {
        "rule_results": {
            "azure_payg_count": 0,
            "azure_payg": [],
            "retired_count": 6,
            "retired_devices": [
                {"server_name": f"retired-sql-0{i}", "install_status": "Retired"}
                for i in range(1, 7)
            ],
            "retired_devices_savings_eur": 0.0,
        },
        "license_metrics": {
            "total_demand_quantity": 1485,
            "total_license_cost": 5131041.24,
            "by_product": [],
            "price_distribution": [],
            "cost_reduction_tips": [],
        },
        "rightsizing": {
            "cpu_optimizations": [],
            "ram_optimizations": [],
            "screen_summaries": {},
            "default_filters": {},
            "cpu_chart_data": [],
            "ram_chart_data": [],
            "cpu_count": 0,
            "cpu_prod_count": 0,
            "cpu_nonprod_count": 0,
            "ram_count": 0,
            "ram_prod_count": 0,
            "ram_nonprod_count": 0,
            "total_vcpu_reduction": 0,
            "total_ram_reduction_gib": 0,
            "error": None,
        },
    }

    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.compute_live_db_metrics",
        lambda: fake_context,
    )

    response = client.get(reverse("optimizer:results"))

    assert response.status_code == 200
    assert response.context["retired_count"] == 6
    assert response.context["retired_devices_savings"] == 0.0
    assert response.context["rr"]["retired_count"] == 6
    assert len(response.context["rr"]["retired_devices"]) == 6


@pytest.mark.django_db
def test_api_strategy3_rightsizing_filters_and_sorts_cpu_records(client, monkeypatch):
    user = get_user_model().objects.create_user(username="api-rs3-cpu", password="secret123")
    client.force_login(user)

    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.compute_rightsizing_metrics",
        lambda: {
            "cpu_optimizations": [
                {
                    "server_name": "prod-sql-02",
                    "Environment": "Production",
                    "Env_Type": "PROD",
                    "product_edition": "Enterprise Edition",
                    "hosting_zone": "Public Cloud",
                    "installed_status_usu": "Installed",
                    "Avg_CPU_12m": 4.1,
                    "Peak_CPU_12m": 35.0,
                    "Current_vCPU": 16,
                    "Recommended_vCPU": 8,
                    "Potential_vCPU_Reduction": 8,
                    "CPU_Recommendation": "Reduce vCPU by ~50% -> 8",
                    "Optimization_Type": "PROD_CPU_Optimization",
                    "Recommendation_Type": "PROD_CPU_Recommendation",
                },
                {
                    "server_name": "prod-sql-01",
                    "Environment": "Production",
                    "Env_Type": "PROD",
                    "product_edition": "Standard Edition",
                    "hosting_zone": "Public Cloud",
                    "installed_status_usu": "Installed",
                    "Avg_CPU_12m": 2.5,
                    "Peak_CPU_12m": 25.0,
                    "Current_vCPU": 8,
                    "Recommended_vCPU": 4,
                    "Potential_vCPU_Reduction": 4,
                    "CPU_Recommendation": "Reduce vCPU by ~50% -> 4",
                    "Optimization_Type": "PROD_CPU_Optimization",
                    "Recommendation_Type": "PROD_CPU_Recommendation",
                },
                {
                    "server_name": "retired-sql-01",
                    "Environment": "Production",
                    "Env_Type": "PROD",
                    "product_edition": "Standard Edition",
                    "hosting_zone": "Private Cloud",
                    "installed_status_usu": "Retired",
                    "Avg_CPU_12m": 1.0,
                    "Peak_CPU_12m": 15.0,
                    "Current_vCPU": 8,
                    "Recommended_vCPU": 4,
                    "Potential_vCPU_Reduction": 4,
                    "CPU_Recommendation": "Reduce vCPU by ~50% -> 4",
                    "Optimization_Type": "PROD_CPU_Optimization",
                    "Recommendation_Type": "PROD_CPU_Recommendation",
                },
            ],
            "ram_optimizations": [],
            "cpu_candidates": [],
            "ram_candidates": [],
            "cpu_filter_options": [
                "PROD_CPU_Optimization",
                "PROD_CPU_Recommendation",
                "NONPROD_CPU_Optimization",
                "NONPROD_CPU_Recommendation",
            ],
            "ram_filter_options": [
                "PROD_RAM_Optimization",
                "PROD_RAM_Recommendation",
                "NONPROD_RAM_Optimization",
                "NONPROD_RAM_Recommendation",
            ],
            "workload_options": ["CPU", "RAM"],
            "default_workload": "CPU",
            "default_filter_by_workload": {
                "CPU": "PROD_CPU_Optimization",
                "RAM": "PROD_RAM_Optimization",
            },
            "screen_filter_options": {
                "CPU": [
                    "PROD_CPU_Optimization",
                    "PROD_CPU_Recommendation",
                    "NONPROD_CPU_Optimization",
                    "NONPROD_CPU_Recommendation",
                ],
                "RAM": [
                    "PROD_RAM_Optimization",
                    "PROD_RAM_Recommendation",
                    "NONPROD_RAM_Optimization",
                    "NONPROD_RAM_Recommendation",
                ],
            },
            "error": None,
        },
    )

    response = client.get(
        reverse("optimizer:api_strategy3_rightsizing"),
        {
            "workload": "CPU",
            "screen_filter": "PROD_CPU_Optimization",
            "hosting_zone": "Public Cloud",
            "installed_status_usu": "Installed",
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["workload"] == "CPU"
    assert payload["screen_filter"] == "PROD_CPU_Optimization"
    assert payload["summary"] == {
        "count": 2,
        "prod_count": 2,
        "nonprod_count": 0,
        "reduction_total": 12.0,
        "savings_eur": 12127.76,
    }
    assert [item["server_name"] for item in payload["items"]] == [
        "prod-sql-02",
        "prod-sql-01",
    ]
    assert payload["items"][0]["potential_vcpu_reduction"] == 8
    assert payload["items"][0]["cost_savings_eur"] == 10551.84
    assert payload["items"][1]["cost_savings_eur"] == 1575.92
    assert payload["filters"] == {
        "hosting_zone": ["Public Cloud"],
        "installed_status_usu": ["Installed"],
    }


@pytest.mark.django_db
def test_api_strategy3_rightsizing_filters_and_sorts_ram_records(client, monkeypatch):
    user = get_user_model().objects.create_user(username="api-rs3-ram", password="secret123")
    client.force_login(user)

    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.compute_rightsizing_metrics",
        lambda: {
            "cpu_optimizations": [],
            "ram_optimizations": [
                {
                    "server_name": "ram-sql-02",
                    "Environment": "Production",
                    "Env_Type": "PROD",
                    "hosting_zone": "Private Cloud AVS",
                    "installed_status_usu": "Installed",
                    "Avg_FreeMem_12m": 78.9,
                    "Min_FreeMem_12m": 63.3,
                    "Current_RAM_GiB": 32,
                    "Recommended_RAM_GiB": 16,
                    "Potential_RAM_Reduction_GiB": 16,
                    "RAM_Recommendation": "Reduce RAM by ~40-50% -> 16 GiB",
                    "Optimization_Type": "PROD_RAM_Optimization",
                    "Recommendation_Type": "PROD_RAM_Recommendation",
                },
                {
                    "server_name": "ram-sql-01",
                    "Environment": "Production",
                    "Env_Type": "PROD",
                    "hosting_zone": "Private Cloud AVS",
                    "installed_status_usu": "Installed",
                    "Avg_FreeMem_12m": 65.8,
                    "Min_FreeMem_12m": 45.1,
                    "Current_RAM_GiB": 16,
                    "Recommended_RAM_GiB": 8,
                    "Potential_RAM_Reduction_GiB": 8,
                    "RAM_Recommendation": "Reduce RAM by ~40-50% -> 8 GiB",
                    "Optimization_Type": "PROD_RAM_Optimization",
                    "Recommendation_Type": "PROD_RAM_Recommendation",
                },
                {
                    "server_name": "remote-sql-01",
                    "Environment": "Production",
                    "Env_Type": "PROD",
                    "hosting_zone": "Remote Site",
                    "installed_status_usu": "Installed",
                    "Avg_FreeMem_12m": 82.0,
                    "Min_FreeMem_12m": 67.0,
                    "Current_RAM_GiB": 32,
                    "Recommended_RAM_GiB": 16,
                    "Potential_RAM_Reduction_GiB": 16,
                    "RAM_Recommendation": "Reduce RAM by ~40-50% -> 16 GiB",
                    "Optimization_Type": "PROD_RAM_Optimization",
                    "Recommendation_Type": "PROD_RAM_Recommendation",
                },
            ],
            "cpu_candidates": [],
            "ram_candidates": [],
            "cpu_filter_options": [
                "PROD_CPU_Optimization",
                "PROD_CPU_Recommendation",
                "NONPROD_CPU_Optimization",
                "NONPROD_CPU_Recommendation",
            ],
            "ram_filter_options": [
                "PROD_RAM_Optimization",
                "PROD_RAM_Recommendation",
                "NONPROD_RAM_Optimization",
                "NONPROD_RAM_Recommendation",
            ],
            "workload_options": ["CPU", "RAM"],
            "default_workload": "CPU",
            "default_filter_by_workload": {
                "CPU": "PROD_CPU_Optimization",
                "RAM": "PROD_RAM_Optimization",
            },
            "screen_filter_options": {
                "CPU": [
                    "PROD_CPU_Optimization",
                    "PROD_CPU_Recommendation",
                    "NONPROD_CPU_Optimization",
                    "NONPROD_CPU_Recommendation",
                ],
                "RAM": [
                    "PROD_RAM_Optimization",
                    "PROD_RAM_Recommendation",
                    "NONPROD_RAM_Optimization",
                    "NONPROD_RAM_Recommendation",
                ],
            },
            "error": None,
        },
    )

    response = client.get(
        reverse("optimizer:api_strategy3_rightsizing"),
        {
            "screen_filter": "PROD_RAM_Optimization",
            "hosting_zone": "Private Cloud AVS",
            "installed_status_usu": "Installed",
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["workload"] == "RAM"
    assert payload["screen_filter"] == "PROD_RAM_Optimization"
    assert payload["summary"] == {
        "count": 2,
        "prod_count": 2,
        "nonprod_count": 0,
        "reduction_total": 24.0,
        "savings_eur": 0.0,
    }
    assert [item["server_name"] for item in payload["items"]] == [
        "ram-sql-02",
        "ram-sql-01",
    ]
    assert payload["items"][0]["potential_ram_reduction_gib"] == 16
    assert [column["key"] for column in payload["columns"]] == [
        "server_name",
        "env_type",
        "avg_free_mem_12m",
        "min_free_mem_12m",
        "current_ram_gib",
        "recommended_ram_gib",
        "ram_recommendation",
        "cost_savings_eur",
    ]


@pytest.mark.django_db
def test_download_rightsizing_sheet_exports_selected_screen(client, monkeypatch):
    user = get_user_model().objects.create_user(username="sheetdl", password="secret123")
    client.force_login(user)

    export_df = pd.DataFrame(
        [
            {
                "Number": "123",
                "Server name": "prod-sql-01",
                "Environment": "Production",
                "Avg_CPU_12m": 8,
                "Peak_CPU_12m": 55,
                "Current_vCPU": 8,
                "Current_RAM_GiB": 32,
            }
        ]
    )

    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.build_rightsizing_sheet_export",
        lambda sheet_key: export_df,
    )

    response = client.get(
        reverse("optimizer:download_rightsizing_sheet", args=["PROD_CPU_Optimization"])
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "prod_cpu_optimization.xlsx" in response["Content-Disposition"]

    df = pd.read_excel(BytesIO(response.content))
    assert list(df.columns) == [
        "Number",
        "Server name",
        "Environment",
        "Avg_CPU_12m",
        "Peak_CPU_12m",
        "Current_vCPU",
        "Current_RAM_GiB",
    ]
    assert df.to_dict("records") == [
        {
            "Number": 123,
            "Server name": "prod-sql-01",
            "Environment": "Production",
            "Avg_CPU_12m": 8,
            "Peak_CPU_12m": 55,
            "Current_vCPU": 8,
            "Current_RAM_GiB": 32,
        }
    ]


@pytest.mark.django_db
def test_download_rightsizing_sheet_rejects_invalid_sheet(client):
    user = get_user_model().objects.create_user(username="bad-sheet", password="secret123")
    client.force_login(user)

    response = client.get(
        reverse("optimizer:download_rightsizing_sheet", args=["UNKNOWN_SHEET"])
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_report_page_normalizes_currency_symbols(client):
    euro = "\u20ac"
    user = get_user_model().objects.create_user(username="reporter", password="secret123")
    analysis = AnalysisSession.objects.create(
        user=user,
        file_name="uploaded.xlsx",
        file_path="uploaded.xlsx",
        status="completed",
        result_data={
            "report_text": """# SQL Server License Optimization Report

## Current State

- **Total estimated license cost:** 6504721.08
The organization manages 20568 licenses at a total annual cost of $6,504,721.08.
""",
            "rule_results": {
                "azure_payg_count": 626,
                "retired_count": 22,
            },
            "license_metrics": {
                "total_demand_quantity": 20568,
                "total_license_cost": 6504721.08,
            },
        },
    )

    client.force_login(user)
    session = client.session
    session["optimizer_analysis_id"] = analysis.id
    session.save()

    response = client.get(reverse("optimizer:report"))

    assert response.status_code == 200
    assert f"{euro}6504721.08" in response.context["report_text"]
    assert f"{euro}6,504,721.08" in response.context["report_text"]
    assert "### Savings" in response.context["report_text"]
    assert f"Total savings: {euro}55,780.96" in response.context["report_text"]
    assert f"BYOL to PAYG Savings: {euro}55,433.08" in response.context["report_text"]
    assert f"Retired but reporting Savings: {euro}347.88" in response.context["report_text"]
    assert "$6,504,721.08" not in response.context["report_text"]


@pytest.mark.django_db
def test_report_page_prefers_latest_agent_report_and_hides_ai_tab(client):
    user = get_user_model().objects.create_user(username="agentreport", password="secret123")
    tenant = Tenant.objects.create(name="Agent Tenant")
    agent_report = "# Agent Report\n\n## Updated Rules\n\n- Includes Strategy 1, Strategy 2, and Strategy 3 findings."
    AgentRun.objects.create(
        tenant=tenant,
        run_label="agentic-uc_1_2_3-20260423-120000",
        triggered_by=user.username,
        status=AgentRun.STATUS_COMPLETED,
        report_markdown=agent_report,
        servers_evaluated=12,
        candidates_found=0,
    )

    client.force_login(user)
    response = client.get(reverse("optimizer:report"))

    assert response.status_code == 200
    assert response.context["report_text"] == agent_report
    body = response.content.decode("utf-8")
    assert "Agent Report" in body
    assert "AI Report" not in body


@pytest.mark.django_db
def test_report_download_normalizes_currency_text_before_export(client, monkeypatch):
    euro = "\u20ac"
    user = get_user_model().objects.create_user(username="exporter", password="secret123")
    analysis = AnalysisSession.objects.create(
        user=user,
        file_name="uploaded.xlsx",
        file_path="uploaded.xlsx",
        status="completed",
        result_data={
            "report_text": """# SQL Server License Optimization Report

## Current State

- **Total estimated license cost:** 6504721.08
The organization manages 20568 licenses at a total annual cost of $6,504,721.08.
""",
            "rule_results": {
                "azure_payg_count": 2,
                "retired_count": 1,
            },
            "license_metrics": {
                "total_demand_quantity": 20568,
                "total_license_cost": 6504721.08,
                "by_product": [],
            },
        },
    )
    captured = {}

    def fake_export_pdf(report_text, generated_at=None, report_context=None):
        captured["report_text"] = report_text
        captured["report_context"] = report_context
        return b"%PDF-1.4 test"

    monkeypatch.setattr("optimizer.views.export_pdf", fake_export_pdf)

    client.force_login(user)
    session = client.session
    session["optimizer_analysis_id"] = analysis.id
    session.save()

    response = client.get(reverse("optimizer:report_download", args=["pdf"]))

    assert response.status_code == 200
    assert captured["report_context"]["total_license_cost"] == 6504721.08
    assert captured["report_context"]["total_savings"] == 30.5
    assert captured["report_context"]["azure_payg_savings"] == 28.0
    assert captured["report_context"]["retired_devices_savings"] == 2.5
    assert f"{euro}6504721.08" in captured["report_text"]
    assert f"{euro}6,504,721.08" in captured["report_text"]
    assert "$6,504,721.08" not in captured["report_text"]


@pytest.mark.django_db
def test_report_download_supports_xlsx(client, monkeypatch):
    user = get_user_model().objects.create_user(username="xlsx-exporter", password="secret123")
    analysis = AnalysisSession.objects.create(
        user=user,
        file_name="uploaded.xlsx",
        file_path="uploaded.xlsx",
        status="completed",
        result_data={
            "report_text": """# SQL Server License Optimization Report

## Current State

- **Total estimated license cost:** 6504721.08
""",
            "rule_results": {
                "azure_payg_count": 2,
                "retired_count": 1,
            },
            "license_metrics": {
                "total_demand_quantity": 20568,
                "total_license_cost": 6504721.08,
                "by_product": [],
            },
        },
    )
    captured = {}

    def fake_export_xlsx(report_text, generated_at=None, report_context=None):
        captured["report_text"] = report_text
        captured["report_context"] = report_context
        return b"PK\x03\x04test-xlsx"

    monkeypatch.setattr("optimizer.views.export_xlsx", fake_export_xlsx)

    client.force_login(user)
    session = client.session
    session["optimizer_analysis_id"] = analysis.id
    session.save()

    response = client.get(reverse("optimizer:report_download", args=["xlsx"]))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.content == b"PK\x03\x04test-xlsx"
    assert captured["report_context"]["total_license_cost"] == 6504721.08
    assert captured["report_context"]["total_savings"] == 30.5


@pytest.mark.django_db
def test_report_download_supports_excel_alias(client, monkeypatch):
    user = get_user_model().objects.create_user(username="excel-exporter", password="secret123")
    analysis = AnalysisSession.objects.create(
        user=user,
        file_name="uploaded.xlsx",
        file_path="uploaded.xlsx",
        status="completed",
        result_data={
            "report_text": """# SQL Server License Optimization Report

## Current State

- **Total estimated license cost:** 6504721.08
""",
            "rule_results": {
                "azure_payg_count": 2,
                "retired_count": 1,
            },
            "license_metrics": {
                "total_demand_quantity": 20568,
                "total_license_cost": 6504721.08,
                "by_product": [],
            },
        },
    )
    captured = {}

    def fake_export_xlsx(report_text, generated_at=None, report_context=None):
        captured["report_text"] = report_text
        captured["report_context"] = report_context
        return b"PK\x03\x04test-excel"

    monkeypatch.setattr("optimizer.views.export_xlsx", fake_export_xlsx)

    client.force_login(user)
    session = client.session
    session["optimizer_analysis_id"] = analysis.id
    session.save()

    response = client.get(reverse("optimizer:report_download", args=["excel"]))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.content == b"PK\x03\x04test-excel"
    assert "filename=" in response["Content-Disposition"]
    assert response["Content-Disposition"].endswith(".xlsx\"")
    assert captured["report_context"]["total_license_cost"] == 6504721.08


@pytest.mark.django_db
def test_analysis_logs_returns_only_current_user_logs(client):
    user_model = get_user_model()
    user = user_model.objects.create_user(username="log-view-user", password="secret123")
    other_user = user_model.objects.create_user(username="log-view-other", password="secret123")

    AnalysisSession.objects.create(
        user=user,
        file_name="mine.xlsx",
        file_path="mine.xlsx",
        status="completed",
        summary_metrics={
            "total_devices_analyzed": 42,
            "total_demand_quantity": 100,
            "total_license_cost": 1000.0,
        },
    )
    AnalysisSession.objects.create(
        user=other_user,
        file_name="other.xlsx",
        file_path="other.xlsx",
        status="completed",
        summary_metrics={"total_devices_analyzed": 1},
    )

    client.force_login(user)
    response = client.get(reverse("optimizer:analysis_logs"))

    payload = response.json()
    assert response.status_code == 200
    assert len(payload["logs"]) == 1
    assert payload["logs"][0]["username"] == "log-view-user"
    assert payload["logs"][0]["file_name"] == "mine.xlsx"
    assert payload["logs"][0]["summary_metrics"]["total_devices_analyzed"] == 42


@pytest.mark.django_db
def test_profile_page_renders_saved_profile_details(client):
    user = get_user_model().objects.create_user(
        username="profile-user",
        password="secret123",
        first_name="Asha",
        last_name="Patel",
        email="asha@example.com",
    )
    UserProfile.objects.create(
        user=user,
        team_name="FinOps",
        image_url="https://example.com/avatar.png",
    )

    client.force_login(user)
    response = client.get(reverse("optimizer:profile"))

    assert response.status_code == 200
    assert response.context["profile_display_name"] == "Asha Patel"
    assert response.context["profile_email"] == "asha@example.com"
    assert response.context["profile_team_name"] == "FinOps"
    assert response.context["profile_image_url"] == "https://example.com/avatar.png"
    assert response.context["profile_initials"] == "AP"


@pytest.mark.django_db
def test_profile_page_updates_user_and_profile_fields(client):
    user = get_user_model().objects.create_user(username="editor", password="secret123")
    UserProfile.objects.create(user=user)

    client.force_login(user)
    response = client.post(
        reverse("optimizer:profile"),
        data={
            "first_name": "Riya",
            "last_name": "Shah",
            "email": "riya@example.com",
            "team_name": "Platform Engineering",
            "image_url": "https://example.com/riya.png",
        },
    )

    user.refresh_from_db()
    profile = user.optimizer_profile

    assert response.status_code == 302
    assert response.url == reverse("optimizer:profile")
    assert user.first_name == "Riya"
    assert user.last_name == "Shah"
    assert user.email == "riya@example.com"
    assert profile.team_name == "Platform Engineering"
    assert profile.image_url == "https://example.com/riya.png"
