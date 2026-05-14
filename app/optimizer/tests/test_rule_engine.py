"""
Unit tests for optimizer.services.rule_engine.
Pure pandas — no @pytest.mark.django_db required.
"""
import pytest
import pandas as pd

from optimizer.services.rule_engine import (
    _find_column,
    _get_actual_demand_from_helpful_reports,
    _get_price_distribution_from_helpful_reports,
    _classify_license_type,
    compute_license_metrics,
    run_rules,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _demand_df(rows=None):
    if rows is None:
        rows = [
            {"product_name": "MySQL Standard", "quantity_effective": 10},
            {"product_name": "MySQL Enterprise", "quantity_effective": 5},
        ]
    return pd.DataFrame(rows)


def _prices_df(rows=None):
    if rows is None:
        rows = [
            {"product_name": "MySQL Standard", "price": 100.0},
            {"product_name": "MySQL Enterprise", "price": 200.0},
        ]
    return pd.DataFrame(rows)


# ===========================================================================
# _find_column
# ===========================================================================

class TestFindColumn:
    def test_exact_match(self):
        df = pd.DataFrame(columns=["product_name", "quantity"])
        assert _find_column(df, ["product_name"]) == "product_name"

    def test_case_insensitive_match(self):
        df = pd.DataFrame(columns=["Product_Name", "Quantity"])
        assert _find_column(df, ["product_name"]) == "Product_Name"

    def test_alias_fallback(self):
        df = pd.DataFrame(columns=["quantity_effective", "price"])
        col = _find_column(df, ["quantity_missing", "quantity_effective"])
        assert col == "quantity_effective"

    def test_partial_substring_match(self):
        df = pd.DataFrame(columns=["quantity_effective_total", "price"])
        col = _find_column(df, ["quantity_effective"])
        assert col == "quantity_effective_total"

    def test_raises_when_not_found(self):
        df = pd.DataFrame(columns=["alpha", "beta"])
        with pytest.raises(ValueError, match="Could not find column"):
            _find_column(df, ["product_name", "quantity"])

    def test_multiple_aliases_first_wins(self):
        df = pd.DataFrame(columns=["product_name", "product"])
        col = _find_column(df, ["product_name", "product"])
        assert col == "product_name"

    def test_spaces_in_alias_normalised(self):
        df = pd.DataFrame(columns=["quantity_effective"])
        col = _find_column(df, ["quantity effective"])
        assert col == "quantity_effective"


# ===========================================================================
# _classify_license_type
# ===========================================================================

class TestClassifyLicenseType:
    def test_developer_keyword(self):
        assert _classify_license_type("MySQL Developer Edition") == "Developer"

    def test_enterprise_keyword(self):
        assert _classify_license_type("MySQL Enterprise Edition") == "Enterprise"

    def test_standard_keyword(self):
        assert _classify_license_type("MySQL Standard Edition") == "Standard"

    def test_ent_abbreviation(self):
        assert _classify_license_type("Oracle MySQL Ent Edition") == "Enterprise"

    def test_std_abbreviation(self):
        assert _classify_license_type("Oracle MySQL Std Edition") == "Standard"

    def test_mysql_connector_is_developer(self):
        assert _classify_license_type("MySQL Connector/J") == "Developer"

    def test_mysql_workbench_is_developer(self):
        assert _classify_license_type("MySQL Workbench") == "Developer"

    def test_mysql_server_is_standard(self):
        assert _classify_license_type("MySQL Server") == "Standard"

    def test_mysql_cluster_is_enterprise(self):
        assert _classify_license_type("MySQL Cluster CGE") == "Enterprise"

    def test_mysql_monitor_is_enterprise(self):
        assert _classify_license_type("MySQL Enterprise Monitor") == "Enterprise"

    def test_mysql_backup_is_enterprise(self):
        assert _classify_license_type("MySQL Enterprise Backup") == "Enterprise"

    def test_unknown_product_is_other(self):
        assert _classify_license_type("Some Random Product") == "Other"

    def test_empty_string_is_other(self):
        assert _classify_license_type("") == "Other"

    def test_none_is_other(self):
        assert _classify_license_type(None) == "Other"

    def test_non_string_is_other(self):
        assert _classify_license_type(12345) == "Other"


# ===========================================================================
# _get_price_distribution_from_helpful_reports
# ===========================================================================

class TestGetPriceDistributionFromHelpfulReports:
    def test_none_returns_empty(self):
        dist, qty, cost = _get_price_distribution_from_helpful_reports(None)
        assert dist == [] and qty is None and cost is None

    def test_empty_df_returns_empty(self):
        dist, qty, cost = _get_price_distribution_from_helpful_reports(pd.DataFrame())
        assert dist == [] and qty is None and cost is None

    def test_grand_total_parsed(self):
        df = pd.DataFrame([
            {"edition": "Standard", "quantity": 10, "license_price": 1000.0},
            {"edition": "Grand Total", "quantity": 10, "license_price": 1000.0},
        ])
        dist, grand_qty, grand_cost = _get_price_distribution_from_helpful_reports(df)
        assert grand_qty == 10
        assert grand_cost == 1000.0

    def test_distribution_contains_standard(self):
        df = pd.DataFrame([{"edition": "Standard", "quantity": 10, "license_price": 1000.0}])
        dist, _, _ = _get_price_distribution_from_helpful_reports(df)
        assert any(r["type"] == "Standard" for r in dist)

    def test_distribution_contains_developer(self):
        df = pd.DataFrame([{"edition": "Developer", "quantity": 5, "license_price": 250.0}])
        dist, _, _ = _get_price_distribution_from_helpful_reports(df)
        assert dist[0]["type"] == "Developer"
        assert dist[0]["quantity"] == 5
        assert dist[0]["total_cost"] == 250.0

    def test_avg_price_computed(self):
        df = pd.DataFrame([{"edition": "Enterprise", "quantity": 4, "license_price": 800.0}])
        dist, _, _ = _get_price_distribution_from_helpful_reports(df)
        assert dist[0]["avg_price"] == 200.0

    def test_missing_required_columns_returns_empty(self):
        df = pd.DataFrame([{"foo": "bar", "baz": 1}])
        dist, qty, cost = _get_price_distribution_from_helpful_reports(df)
        assert dist == [] and qty is None and cost is None

    def test_comma_separated_price_values(self):
        df = pd.DataFrame([{"edition": "Standard", "quantity": 2, "license_price": "1,000.00"}])
        dist, _, _ = _get_price_distribution_from_helpful_reports(df)
        assert dist[0]["total_cost"] == 1000.0

    def test_unrecognised_edition_skipped(self):
        df = pd.DataFrame([{"edition": "Gold Edition", "quantity": 5, "license_price": 500.0}])
        dist, _, _ = _get_price_distribution_from_helpful_reports(df)
        assert dist == []

    def test_sorting_standard_first(self):
        df = pd.DataFrame([
            {"edition": "Enterprise", "quantity": 2, "license_price": 400.0},
            {"edition": "Developer", "quantity": 3, "license_price": 150.0},
            {"edition": "Standard", "quantity": 10, "license_price": 1000.0},
        ])
        dist, _, _ = _get_price_distribution_from_helpful_reports(df)
        assert dist[0]["type"] == "Standard"


# ===========================================================================
# _get_actual_demand_from_helpful_reports
# ===========================================================================

class TestGetActualDemandFromHelpfulReports:
    def test_none_returns_none(self):
        assert _get_actual_demand_from_helpful_reports(None) is None

    def test_empty_df_returns_none(self):
        assert _get_actual_demand_from_helpful_reports(pd.DataFrame()) is None

    def test_total_demand_column_returned(self):
        df = pd.DataFrame([{"total_demand": 42}])
        assert _get_actual_demand_from_helpful_reports(df) == 42

    def test_demand_column_returned(self):
        df = pd.DataFrame([{"demand": 15}])
        assert _get_actual_demand_from_helpful_reports(df) == 15

    def test_license_count_column_returned(self):
        df = pd.DataFrame([{"license_count": 7}])
        assert _get_actual_demand_from_helpful_reports(df) == 7

    def test_multiple_rows_summed(self):
        df = pd.DataFrame([{"total_demand": 10}, {"total_demand": 5}])
        assert _get_actual_demand_from_helpful_reports(df) == 15

    def test_non_numeric_values_return_none(self):
        df = pd.DataFrame([{"total_demand": "N/A"}, {"total_demand": "unknown"}])
        assert _get_actual_demand_from_helpful_reports(df) is None

    def test_fallback_to_first_numeric_column(self):
        df = pd.DataFrame([{"arbitrary_count": 99}])
        assert _get_actual_demand_from_helpful_reports(df) == 99


# ===========================================================================
# compute_license_metrics
# ===========================================================================

class TestComputeLicenseMetrics:
    def test_empty_demand_returns_zeros(self):
        result = compute_license_metrics(pd.DataFrame(), _prices_df())
        assert result["total_demand_quantity"] == 0
        assert result["total_license_cost"] == 0.0
        assert result["by_product"] == []

    def test_none_demand_returns_zeros(self):
        assert compute_license_metrics(None, _prices_df())["total_demand_quantity"] == 0

    def test_empty_prices_returns_row_count_as_demand(self):
        demand = _demand_df()
        result = compute_license_metrics(demand, pd.DataFrame())
        assert result["total_demand_quantity"] == len(demand)
        assert result["total_license_cost"] == 0.0

    def test_cost_formula_price_times_qty_divided_by_two(self):
        demand = pd.DataFrame([{"product_name": "MySQL Standard", "quantity_effective": 10}])
        prices = pd.DataFrame([{"product_name": "MySQL Standard", "price": 100.0}])
        result = compute_license_metrics(demand, prices)
        assert result["total_license_cost"] == 500.0

    def test_by_product_list_populated(self):
        result = compute_license_metrics(_demand_df(), _prices_df())
        products = [r["product"] for r in result["by_product"]]
        assert "MySQL Standard" in products
        assert "MySQL Enterprise" in products

    def test_demand_row_count_key_present(self):
        result = compute_license_metrics(_demand_df(), _prices_df())
        assert result["demand_row_count"] == 2

    def test_price_distribution_always_has_four_types(self):
        result = compute_license_metrics(_demand_df(), _prices_df())
        types = {r["type"] for r in result["price_distribution"]}
        assert {"Standard", "Developer", "Enterprise", "Other"}.issubset(types)

    def test_grand_total_from_helpful_reports_overrides_cost(self):
        hr = pd.DataFrame([
            {"edition": "Standard", "quantity": 10, "license_price": 1000.0},
            {"edition": "Grand Total", "quantity": 10, "license_price": 9999.0},
        ])
        result = compute_license_metrics(_demand_df(), _prices_df(), helpful_reports_df=hr)
        assert result["total_license_cost"] == 9999.0

    def test_grand_qty_from_helpful_reports_overrides_row_count(self):
        hr = pd.DataFrame([
            {"edition": "Standard", "quantity": 77, "license_price": 100.0},
            {"edition": "Grand Total", "quantity": 77, "license_price": 100.0},
        ])
        result = compute_license_metrics(_demand_df(), _prices_df(), helpful_reports_df=hr)
        assert result["total_demand_quantity"] == 77

    def test_price_distribution_from_helpful_reports_used_when_available(self):
        hr = pd.DataFrame([{"edition": "Enterprise", "quantity": 8, "license_price": 1600.0}])
        result = compute_license_metrics(_demand_df(), _prices_df(), helpful_reports_df=hr)
        ent = next(r for r in result["price_distribution"] if r["type"] == "Enterprise")
        assert ent["quantity"] == 8

    def test_cost_reduction_tips_always_present(self):
        result = compute_license_metrics(_demand_df(), _prices_df())
        assert isinstance(result["cost_reduction_tips"], list)
        assert len(result["cost_reduction_tips"]) >= 1

    def test_unmatched_products_contribute_zero_cost(self):
        demand = pd.DataFrame([{"product_name": "Unknown Product", "quantity_effective": 10}])
        prices = pd.DataFrame([{"product_name": "MySQL Standard", "price": 100.0}])
        result = compute_license_metrics(demand, prices)
        assert result["total_license_cost"] == 0.0

    def test_multiple_matching_rows_aggregate(self):
        demand = pd.DataFrame([
            {"product_name": "MySQL Standard", "quantity_effective": 4},
            {"product_name": "MySQL Standard", "quantity_effective": 6},
        ])
        prices = pd.DataFrame([{"product_name": "MySQL Standard", "price": 100.0}])
        result = compute_license_metrics(demand, prices)
        assert result["total_license_cost"] == 500.0

    def test_result_has_all_required_keys(self):
        result = compute_license_metrics(_demand_df(), _prices_df())
        for key in ("total_demand_quantity", "total_license_cost", "by_product",
                    "demand_row_count", "price_distribution", "cost_reduction_tips"):
            assert key in result


# ===========================================================================
# run_rules
# ===========================================================================

class TestRunRules:
    def _installations(self):
        return pd.DataFrame([
            {"u_hosting_zone": "Public Cloud", "inventory_status_standard": "",
             "no_license_required": 0, "install_status": "active", "server_name": "srv-01"},
            {"u_hosting_zone": "Private Cloud", "inventory_status_standard": "",
             "no_license_required": 0, "install_status": "retired", "server_name": "srv-02"},
        ])

    def test_none_returns_empty(self):
        result = run_rules(None)
        assert result["azure_payg_count"] == 0
        assert result["retired_count"] == 0

    def test_empty_df_returns_empty(self):
        result = run_rules(pd.DataFrame())
        assert result["azure_payg_count"] == 0
        assert result["retired_count"] == 0

    def test_result_has_required_keys(self):
        result = run_rules(pd.DataFrame())
        for key in ("azure_payg", "azure_payg_count", "retired_devices", "retired_count"):
            assert key in result

    def test_error_message_when_empty(self):
        result = run_rules(pd.DataFrame())
        assert result.get("azure_error") == "No installation data"
        assert result.get("retired_error") == "No installation data"

    def test_rule_errors_do_not_propagate(self, monkeypatch):
        def raise_error(df):
            raise RuntimeError("boom")
        monkeypatch.setattr("optimizer.services.rule_engine.find_azure_payg_candidates", raise_error)
        result = run_rules(self._installations())
        assert result["azure_payg_count"] == 0
        assert result["azure_error"] is not None

    def test_azure_payg_rule_invoked(self, monkeypatch):
        payg_result = pd.DataFrame([{"server_name": "srv-cloud", "u_hosting_zone": "Public Cloud"}])
        monkeypatch.setattr("optimizer.services.rule_engine.find_azure_payg_candidates", lambda df: payg_result)
        monkeypatch.setattr("optimizer.services.rule_engine.find_retired_devices_with_installations", lambda df: pd.DataFrame())
        result = run_rules(self._installations())
        assert result["azure_payg_count"] == 1
        assert result["azure_payg"][0]["server_name"] == "srv-cloud"

    def test_retired_devices_rule_invoked(self, monkeypatch):
        retired = pd.DataFrame([{"server_name": "srv-old", "install_status": "retired"}])
        monkeypatch.setattr("optimizer.services.rule_engine.find_azure_payg_candidates", lambda df: pd.DataFrame())
        monkeypatch.setattr("optimizer.services.rule_engine.find_retired_devices_with_installations", lambda df: retired)
        result = run_rules(self._installations())
        assert result["retired_count"] == 1
        assert result["retired_devices"][0]["server_name"] == "srv-old"

    def test_na_values_converted_to_none(self, monkeypatch):
        payg_result = pd.DataFrame([{"server_name": "srv-1", "note": pd.NA}])
        monkeypatch.setattr("optimizer.services.rule_engine.find_azure_payg_candidates", lambda df: payg_result)
        monkeypatch.setattr("optimizer.services.rule_engine.find_retired_devices_with_installations", lambda df: pd.DataFrame())
        result = run_rules(self._installations())
        assert result["azure_payg"][0]["note"] is None
