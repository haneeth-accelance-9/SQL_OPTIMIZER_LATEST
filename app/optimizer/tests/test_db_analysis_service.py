import pandas as pd

from optimizer.services.db_analysis_service import (
    RIGHTSIZING_REPORT_BASE_HEADERS,
    _prepare_db_prices_for_demand,
    build_rightsizing_sheet_export,
    compute_live_db_metrics,
    compute_rightsizing_metrics,
)
from optimizer.services.rule_engine import compute_license_metrics


def test_compute_rightsizing_metrics_builds_workload_screen_metadata(monkeypatch):
    source_df = pd.DataFrame([
        {
            "server_name": "prod-sql-01",
            "Environment": "Production",
            "Avg_CPU_12m": 8,
            "Peak_CPU_12m": 55,
            "Avg_FreeMem_12m": 45,
            "Min_FreeMem_12m": 30,
            "Current_vCPU": 8,
            "Current_RAM_GiB": 32,
        },
        {
            "server_name": "dev-sql-01",
            "Environment": "Development",
            "Avg_CPU_12m": 10,
            "Peak_CPU_12m": 40,
            "Avg_FreeMem_12m": 55,
            "Min_FreeMem_12m": 25,
            "Current_vCPU": 6,
            "Current_RAM_GiB": 16,
        },
    ])

    monkeypatch.setattr(
        "optimizer.services.db_analysis_service._build_rightsizing_df",
        lambda: source_df,
    )

    result = compute_rightsizing_metrics()

    assert result["workload_options"] == ["CPU", "RAM"]
    assert result["default_workload"] == "CPU"
    assert result["default_filter_by_workload"] == {
        "CPU": "PROD_CPU_Optimization",
        "RAM": "PROD_RAM_Optimization",
    }
    assert result["screen_filter_options"]["CPU"] == [
        "PROD_CPU_Optimization",
        "PROD_CPU_Recommendation",
        "NONPROD_CPU_Optimization",
        "NONPROD_CPU_Recommendation",
    ]
    assert result["screen_filter_options"]["RAM"] == [
        "PROD_RAM_Optimization",
        "PROD_RAM_Recommendation",
        "NONPROD_RAM_Optimization",
        "NONPROD_RAM_Recommendation",
    ]
    assert result["screen_summaries"]["CPU"]["PROD_CPU_Optimization"]["count"] == 1
    assert result["screen_summaries"]["CPU"]["NONPROD_CPU_Recommendation"]["count"] == 1
    assert result["screen_summaries"]["RAM"]["PROD_RAM_Optimization"]["reduction_total"] == 8.0
    assert result["screen_summaries"]["RAM"]["NONPROD_RAM_Recommendation"]["reduction_total"] == 8.0
    assert result["cpu_chart_data"][0]["optimization_type"] == "PROD_CPU_Optimization"
    assert result["ram_chart_data"][1]["recommendation_type"] == "NONPROD_RAM_Recommendation"


def test_compute_rightsizing_metrics_retains_hosting_zone_and_installed_status_for_api(monkeypatch):
    source_df = pd.DataFrame([
        {
            "server_name": "prod-sql-01",
            "hosting_zone": "Public Cloud",
            "installed_status_usu": "Installed",
            "Environment": "Production",
            "Avg_CPU_12m": 8,
            "Peak_CPU_12m": 55,
            "Avg_FreeMem_12m": 45,
            "Min_FreeMem_12m": 30,
            "Current_vCPU": 8,
            "Current_RAM_GiB": 32,
        },
    ])

    monkeypatch.setattr(
        "optimizer.services.db_analysis_service._build_rightsizing_df",
        lambda: source_df,
    )

    result = compute_rightsizing_metrics()

    assert result["cpu_optimizations"][0]["hosting_zone"] == "Public Cloud"
    assert result["cpu_optimizations"][0]["installed_status_usu"] == "Installed"
    assert result["ram_optimizations"][0]["hosting_zone"] == "Public Cloud"
    assert result["ram_optimizations"][0]["installed_status_usu"] == "Installed"


def test_compute_rightsizing_metrics_calculates_cpu_cost_savings_from_product_edition(monkeypatch):
    source_df = pd.DataFrame([
        {
            "server_name": "prod-sql-01",
            "product_edition": "Enterprise Edition",
            "Environment": "Production",
            "Avg_CPU_12m": 8,
            "Peak_CPU_12m": 55,
            "Avg_FreeMem_12m": 45,
            "Min_FreeMem_12m": 30,
            "Current_vCPU": 8,
            "Current_RAM_GiB": 32,
        },
        {
            "server_name": "prod-sql-02",
            "product_edition": "Standard Edition",
            "Environment": "Production",
            "Avg_CPU_12m": 9,
            "Peak_CPU_12m": 50,
            "Avg_FreeMem_12m": 40,
            "Min_FreeMem_12m": 25,
            "Current_vCPU": 8,
            "Current_RAM_GiB": 24,
        },
    ])

    monkeypatch.setattr(
        "optimizer.services.db_analysis_service._build_rightsizing_df",
        lambda: source_df,
    )

    result = compute_rightsizing_metrics()

    assert result["cpu_optimizations"][0]["Cost_Savings_EUR"] == 5275.92
    assert result["cpu_optimizations"][1]["Cost_Savings_EUR"] == 1575.92
    assert result["cpu_savings_eur"] == 6851.84


def test_build_rightsizing_sheet_export_matches_report_columns(monkeypatch):
    source_df = pd.DataFrame([
        {
            "Number": "123",
            "Server name": "prod-sql-01",
            "server_name": "prod-sql-01",
            "Environment": "Production",
            "Hosting Zone": "Public Cloud",
            "Comments for Allocation (GB)": "",
            "Comments for Usage (GB)": "",
            "Decom check": "",
            "Avg_CPU_12m": 8,
            "Peak_CPU_12m": 55,
            "Avg_FreeMem_12m": 48,
            "Min_FreeMem_12m": 20,
            "Current_vCPU": 8,
            "Current_RAM_GiB": 32,
            "CPU_Recommendation": "Reduce vCPU by ~50% -> 4",
            "Recommended_vCPU": 4,
        }
    ])

    monkeypatch.setattr(
        "optimizer.services.db_analysis_service._build_rightsizing_df",
        lambda: source_df,
    )

    export_df = build_rightsizing_sheet_export("PROD_CPU_Recommendation")

    assert list(export_df.columns) == list(RIGHTSIZING_REPORT_BASE_HEADERS) + [
        "CPU_Recommendation",
        "Recommended_vCPU",
    ]
    assert export_df.to_dict("records") == [
        {
            **{column: None for column in RIGHTSIZING_REPORT_BASE_HEADERS},
            "Number": "123",
            "Server name": "prod-sql-01",
            "Environment": "Production",
            "Hosting Zone": "Public Cloud",
            "Comments for Allocation (GB)": "",
            "Comments for Usage (GB)": "",
            "Decom check": "",
            "Avg_CPU_12m": 8,
            "Peak_CPU_12m": 55,
            "Avg_FreeMem_12m": 48,
            "Min_FreeMem_12m": 20,
            "Current_vCPU": 8,
            "Current_RAM_GiB": 32,
            "CPU_Recommendation": "Reduce vCPU by ~50% -> 4",
            "Recommended_vCPU": 4,
        }
    ]


def test_prepare_db_prices_for_demand_expands_family_prices_to_product_names():
    demand_df = pd.DataFrame([
        {
            "product_name": "Oracle MySQL 8.x Connector/ODBC",
            "product_family": "MySQL",
            "quantity_effective": 1.0,
        },
        {
            "product_name": "Oracle MySQL 9 Server",
            "product_family": "MySQL",
            "quantity_effective": 1.0,
        },
    ])
    prices_df = pd.DataFrame([
        {
            "product_name": "MySQL",
            "price": 2500.0,
        }
    ])

    aligned_prices = _prepare_db_prices_for_demand(demand_df, prices_df)
    metrics = compute_license_metrics(demand_df, aligned_prices)

    assert set(aligned_prices["product_name"]) == {
        "MySQL",
        "Oracle MySQL 8.x Connector/ODBC",
        "Oracle MySQL 9 Server",
    }
    assert metrics["total_demand_quantity"] == 2
    assert metrics["total_license_cost"] == 2500.0


def test_prepare_db_prices_for_demand_broadcasts_single_price_when_no_products_match():
    demand_df = pd.DataFrame([
        {
            "product_name": "Oracle MySQL 8.x Connector/ODBC",
            "product_family": "MySQL",
            "quantity_effective": 1.0,
        },
        {
            "product_name": "Oracle MySQL 9 Server",
            "product_family": "MySQL",
            "quantity_effective": 1.0,
        },
    ])
    prices_df = pd.DataFrame([
        {
            "product_name": "SQL Server",
            "price": 2500.0,
        }
    ])

    aligned_prices = _prepare_db_prices_for_demand(demand_df, prices_df)
    metrics = compute_license_metrics(demand_df, aligned_prices)

    assert "Oracle MySQL 8.x Connector/ODBC" in set(aligned_prices["product_name"])
    assert "Oracle MySQL 9 Server" in set(aligned_prices["product_name"])
    assert metrics["total_demand_quantity"] == 2
    assert metrics["total_license_cost"] == 2500.0


def test_compute_live_db_metrics_uses_db_backed_rule1(monkeypatch):
    installations_df = pd.DataFrame([
        {
            "u_hosting_zone": "Public Cloud",
            "inventory_status_standard": "",
            "no_license_required": 0,
            "server_name": "sql-01",
        },
        {
            "u_hosting_zone": "Private Cloud AVS",
            "inventory_status_standard": "license included",
            "no_license_required": 0,
            "server_name": "sql-02",
        },
    ])
    demand_df = pd.DataFrame([
        {
            "product_name": "MySQL",
            "quantity_effective": 2.0,
        }
    ])
    prices_df = pd.DataFrame([
        {
            "product_name": "MySQL",
            "price": 2500.0,
        }
    ])
    captured = {}

    class _DummyValuesList:
        def __init__(self, values):
            self._values = values

        def distinct(self):
            return self._values

    class _DummyManager:
        def __init__(self, values):
            self._values = values

        def exclude(self, **kwargs):
            return self

        def values_list(self, *args, **kwargs):
            return _DummyValuesList(self._values)

    class _DummyDemandDetail:
        objects = _DummyManager(list(range(1, 140)))

    class _DummyInstallation:
        objects = _DummyManager(list(range(140, 278)))

    def _fake_rule1(source_df):
        captured["rule1_source"] = source_df.copy()
        return source_df.iloc[[0]].copy()

    monkeypatch.setattr("optimizer.services.db_analysis_service._build_installations_df", lambda: installations_df)
    monkeypatch.setattr("optimizer.services.db_analysis_service._build_payg_installations_df", lambda: installations_df)
    monkeypatch.setattr("optimizer.services.db_analysis_service._build_retired_installations_df", lambda: installations_df.iloc[0:0].copy())
    monkeypatch.setattr("optimizer.services.db_analysis_service._build_demand_df", lambda: demand_df)
    monkeypatch.setattr("optimizer.services.db_analysis_service._build_prices_df", lambda: prices_df)
    monkeypatch.setattr("optimizer.services.db_analysis_service._prepare_db_prices_for_demand", lambda demand, prices: prices)
    monkeypatch.setattr("optimizer.services.db_analysis_service.find_azure_payg_candidates_from_db", _fake_rule1)
    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.find_retired_devices_with_installations_from_db",
        lambda source_df: source_df.iloc[0:0].copy(),
    )
    monkeypatch.setattr("optimizer.services.db_analysis_service.compute_rightsizing_metrics", lambda: {"error": None})
    monkeypatch.setattr("optimizer.models.USUDemandDetail", _DummyDemandDetail)
    monkeypatch.setattr("optimizer.models.USUInstallation", _DummyInstallation)

    context = compute_live_db_metrics()

    assert captured["rule1_source"].equals(installations_df)
    assert context["total_devices_analyzed"] == 277
    assert context["rule_results"]["azure_payg_count"] == 1
    assert context["rule_results"]["retired_count"] == 0
    assert context["data_source"] == "database"


def test_compute_live_db_metrics_uses_db_backed_rule2(monkeypatch):
    installations_df = pd.DataFrame([
        {
            "u_hosting_zone": "Public Cloud",
            "inventory_status_standard": "",
            "install_status": "retired",
            "no_license_required": 0,
            "server_name": "sql-01",
        },
        {
            "u_hosting_zone": "Private Cloud AVS",
            "inventory_status_standard": "",
            "install_status": "active",
            "no_license_required": 0,
            "server_name": "sql-02",
        },
    ])
    demand_df = pd.DataFrame([
        {
            "product_name": "MySQL",
            "quantity_effective": 2.0,
        }
    ])
    prices_df = pd.DataFrame([
        {
            "product_name": "MySQL",
            "price": 2500.0,
        }
    ])
    captured = {}

    class _DummyValuesList:
        def __init__(self, values):
            self._values = values

        def distinct(self):
            return self._values

    class _DummyManager:
        def __init__(self, values):
            self._values = values

        def exclude(self, **kwargs):
            return self

        def values_list(self, *args, **kwargs):
            return _DummyValuesList(self._values)

    class _DummyDemandDetail:
        objects = _DummyManager(list(range(1, 140)))

    class _DummyInstallation:
        objects = _DummyManager(list(range(140, 278)))

    def _fake_rule2(source_df):
        captured["rule2_source"] = source_df.copy()
        return source_df.iloc[[0]].copy()

    monkeypatch.setattr("optimizer.services.db_analysis_service._build_installations_df", lambda: installations_df)
    monkeypatch.setattr("optimizer.services.db_analysis_service._build_payg_installations_df", lambda: installations_df.iloc[0:0].copy())
    monkeypatch.setattr("optimizer.services.db_analysis_service._build_retired_installations_df", lambda: installations_df)
    monkeypatch.setattr("optimizer.services.db_analysis_service._build_demand_df", lambda: demand_df)
    monkeypatch.setattr("optimizer.services.db_analysis_service._build_prices_df", lambda: prices_df)
    monkeypatch.setattr("optimizer.services.db_analysis_service._prepare_db_prices_for_demand", lambda demand, prices: prices)
    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.find_azure_payg_candidates_from_db",
        lambda source_df: source_df.iloc[0:0].copy(),
    )
    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.find_retired_devices_with_installations_from_db",
        _fake_rule2,
    )
    monkeypatch.setattr("optimizer.services.db_analysis_service.compute_rightsizing_metrics", lambda: {"error": None})
    monkeypatch.setattr("optimizer.models.USUDemandDetail", _DummyDemandDetail)
    monkeypatch.setattr("optimizer.models.USUInstallation", _DummyInstallation)

    context = compute_live_db_metrics()

    assert captured["rule2_source"].equals(installations_df)
    assert context["total_devices_analyzed"] == 277
    assert context["rule_results"]["azure_payg_count"] == 0
    assert context["rule_results"]["retired_count"] == 1
    assert context["data_source"] == "database"
