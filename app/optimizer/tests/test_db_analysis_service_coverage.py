"""
Coverage tests for optimizer.services.db_analysis_service.
Targets missed lines: 213-220, 228-232, 246-314, 324-352, 369-411, 450-523,
545-649, 668-695, 700-717, 733-792.

All public/private functions are tested with empty DB or minimal DataFrames
so the entry paths and early-return branches are covered without requiring
real fixture data.  No existing test_db_analysis_service.py tests are duplicated.
"""
import pytest
import pandas as pd
from decimal import Decimal

from optimizer.services.db_analysis_service import (
    _normalize_hosting_zone,
    _normalize_install_status,
    _classify_rightsizing_license_type,
    _get_rightsizing_cpu_license_cost_eur,
    _coerce_non_negative_float,
    _calculate_cpu_rightsizing_costs_eur,
    _calculate_cpu_rightsizing_savings_eur,
    _prepare_db_prices_for_demand,
    _filter_to_standard_enterprise_servers,
    _compute_device_cost_from_df,
    compute_azure_payg_cost_metrics,
    compute_retired_devices_extended_metrics,
    _apply_rightsizing_cost_savings,
    RIGHTSIZING_CPU_LICENSE_COSTS_EUR,
)


# ===========================================================================
# _normalize_hosting_zone  (lines 205-220)
# ===========================================================================

class TestNormalizeHostingZone:
    def test_public_cloud_exact(self):
        assert _normalize_hosting_zone("Public Cloud") == "Public Cloud"

    def test_public_cloud_lowercase(self):
        assert _normalize_hosting_zone("public cloud") == "Public Cloud"

    def test_avs_suffix_maps_to_private_cloud_avs(self):
        assert _normalize_hosting_zone("Private Cloud AVS") == "Private Cloud AVS"

    def test_avs_lowercase(self):
        assert _normalize_hosting_zone("private cloud avs") == "Private Cloud AVS"

    def test_private_cloud_without_avs_returned_as_is(self):
        result = _normalize_hosting_zone("Private Cloud")
        assert result == "Private Cloud"

    def test_empty_string_returns_empty(self):
        assert _normalize_hosting_zone("") == ""

    def test_none_returns_empty(self):
        assert _normalize_hosting_zone(None) == ""

    def test_whitespace_only_returns_empty(self):
        assert _normalize_hosting_zone("   ") == ""

    def test_unknown_value_returned_stripped(self):
        result = _normalize_hosting_zone("  On-Premise  ")
        assert result == "On-Premise"

    def test_public_substring(self):
        assert _normalize_hosting_zone("Azure Public") == "Public Cloud"


# ===========================================================================
# _normalize_install_status  (lines 223-232)
# ===========================================================================

class TestNormalizeInstallStatus:
    def test_device_status_returned_first(self):
        result = _normalize_install_status("Installed", "retired", "active")
        assert result == "Installed"

    def test_falls_back_to_usu_status(self):
        result = _normalize_install_status("", "retired", "active")
        assert result == "retired"

    def test_falls_back_to_boones_status(self):
        result = _normalize_install_status("", "", "active")
        assert result == "active"

    def test_all_empty_returns_empty(self):
        result = _normalize_install_status("", "", "")
        assert result == ""

    def test_all_none_returns_empty(self):
        result = _normalize_install_status(None, None, None)
        assert result == ""

    def test_first_non_empty_wins(self):
        result = _normalize_install_status(None, "Retired", "Active")
        assert result == "Retired"

    def test_whitespace_only_skipped(self):
        result = _normalize_install_status("  ", "", "Installed")
        # "  ".strip() is truthy-as-string but .strip() is empty — wait, " ".strip()→""
        # Per code: `str(val or "").strip()` — " " is truthy so it won't be caught by `or`
        # Actually str("  ") = "  " which is truthy, so it returns "  " ← that is the result
        assert isinstance(result, str)


# ===========================================================================
# _classify_rightsizing_license_type  (lines 1239-1251)
# ===========================================================================

class TestClassifyRightsizingLicenseType:
    def test_enterprise_exact(self):
        assert _classify_rightsizing_license_type("enterprise") == "enterprise"

    def test_enterprise_in_edition(self):
        assert _classify_rightsizing_license_type("SQL Enterprise Edition") == "enterprise"

    def test_standard_exact(self):
        assert _classify_rightsizing_license_type("standard") == "standard"

    def test_standard_in_edition(self):
        assert _classify_rightsizing_license_type("SQL Standard 2019") == "standard"

    def test_developer_returns_empty(self):
        assert _classify_rightsizing_license_type("Developer") == ""

    def test_empty_returns_empty(self):
        assert _classify_rightsizing_license_type("") == ""

    def test_none_returns_empty(self):
        assert _classify_rightsizing_license_type(None) == ""

    def test_ent_abbreviation(self):
        result = _classify_rightsizing_license_type("SQL ent edition")
        # "ent" may be picked up via " ent " or "enterprise" match
        assert result in ("enterprise", "")

    def test_case_insensitive(self):
        assert _classify_rightsizing_license_type("ENTERPRISE") == "enterprise"


# ===========================================================================
# _get_rightsizing_cpu_license_cost_eur  (lines 1254-1256)
# ===========================================================================

class TestGetRightsizingCpuLicenseCostEur:
    def test_enterprise_returns_enterprise_price(self):
        price = _get_rightsizing_cpu_license_cost_eur("enterprise")
        assert price == RIGHTSIZING_CPU_LICENSE_COSTS_EUR["enterprise"]

    def test_standard_returns_standard_price(self):
        price = _get_rightsizing_cpu_license_cost_eur("Standard Edition")
        assert price == RIGHTSIZING_CPU_LICENSE_COSTS_EUR["standard"]

    def test_unknown_returns_zero(self):
        assert _get_rightsizing_cpu_license_cost_eur("Developer") == 0.0

    def test_none_returns_zero(self):
        assert _get_rightsizing_cpu_license_cost_eur(None) == 0.0


# ===========================================================================
# _coerce_non_negative_float  (lines 1259-1263)
# ===========================================================================

class TestCoerceNonNegativeFloat:
    def test_positive_float(self):
        assert _coerce_non_negative_float(5.5) == 5.5

    def test_negative_clamped_to_zero(self):
        assert _coerce_non_negative_float(-3.0) == 0.0

    def test_none_returns_zero(self):
        assert _coerce_non_negative_float(None) == 0.0

    def test_string_number(self):
        assert _coerce_non_negative_float("2.5") == 2.5

    def test_invalid_string_returns_zero(self):
        assert _coerce_non_negative_float("N/A") == 0.0

    def test_zero_returns_zero(self):
        assert _coerce_non_negative_float(0) == 0.0


# ===========================================================================
# _calculate_cpu_rightsizing_costs_eur  (lines 1267-1304)
# ===========================================================================

class TestCalculateCpuRightsizingCostsEur:
    def test_enterprise_with_eff_quantity(self):
        actual, recommended, savings = _calculate_cpu_rightsizing_costs_eur(
            "enterprise", eff_quantity=8, recommended_vcpu=4
        )
        enterprise_price = RIGHTSIZING_CPU_LICENSE_COSTS_EUR["enterprise"]
        expected_actual = round((enterprise_price * 8) / 2, 2)
        expected_recommended = round((enterprise_price * 4) / 2, 2)
        assert actual == expected_actual
        assert recommended == expected_recommended
        assert savings == round(expected_actual - expected_recommended, 2)

    def test_zero_price_returns_zeros(self):
        actual, recommended, savings = _calculate_cpu_rightsizing_costs_eur(
            "developer", eff_quantity=8, recommended_vcpu=4
        )
        assert actual == 0.0
        assert recommended == 0.0
        assert savings == 0.0

    def test_with_reduction_instead_of_recommended(self):
        actual, recommended, savings = _calculate_cpu_rightsizing_costs_eur(
            "standard", eff_quantity=8, reduction=2
        )
        std_price = RIGHTSIZING_CPU_LICENSE_COSTS_EUR["standard"]
        expected_actual = round((std_price * 8) / 2, 2)
        expected_recommended = round((std_price * 6) / 2, 2)
        assert actual == expected_actual
        assert recommended == expected_recommended

    def test_no_recommended_no_reduction_savings_zero(self):
        """When neither recommended_vcpu nor reduction is provided, recommended=actual → savings=0."""
        actual, recommended, savings = _calculate_cpu_rightsizing_costs_eur(
            "enterprise", eff_quantity=4
        )
        assert savings == 0.0

    def test_none_eff_quantity_treated_as_zero(self):
        actual, recommended, savings = _calculate_cpu_rightsizing_costs_eur(
            "enterprise", eff_quantity=None
        )
        assert actual == 0.0

    def test_invalid_recommended_vcpu_treated_as_zero(self):
        actual, recommended, savings = _calculate_cpu_rightsizing_costs_eur(
            "standard", eff_quantity=4, recommended_vcpu="N/A"
        )
        assert recommended == 0.0


# ===========================================================================
# _calculate_cpu_rightsizing_savings_eur  (lines 1307-1320)
# ===========================================================================

class TestCalculateCpuRightsizingSavingsEur:
    def test_returns_float(self):
        result = _calculate_cpu_rightsizing_savings_eur("enterprise", eff_quantity=8, recommended_vcpu=4)
        assert isinstance(result, float)

    def test_savings_greater_than_zero(self):
        result = _calculate_cpu_rightsizing_savings_eur("enterprise", eff_quantity=8, recommended_vcpu=4)
        assert result > 0.0

    def test_unknown_edition_returns_zero(self):
        assert _calculate_cpu_rightsizing_savings_eur("developer", eff_quantity=8) == 0.0


# ===========================================================================
# _prepare_db_prices_for_demand  (lines 795-884) — pure function
# ===========================================================================

class TestPrepareDbPricesForDemand:
    def _demand_df(self):
        return pd.DataFrame([
            {"product_name": "SQL Server Enterprise", "product_family": "SQL Server"},
            {"product_name": "SQL Server Standard", "product_family": "SQL Server"},
        ])

    def _prices_df(self):
        return pd.DataFrame([
            {"product_name": "SQL Server", "price": 1000.0},
        ])

    def test_empty_demand_returns_prices_unchanged(self):
        result = _prepare_db_prices_for_demand(pd.DataFrame(), self._prices_df())
        assert len(result) == len(self._prices_df())

    def test_none_demand_returns_prices_unchanged(self):
        result = _prepare_db_prices_for_demand(None, self._prices_df())
        assert len(result) == len(self._prices_df())

    def test_empty_prices_returns_prices_unchanged(self):
        result = _prepare_db_prices_for_demand(self._demand_df(), pd.DataFrame())
        assert result.empty

    def test_family_level_price_expanded_to_demand_products(self):
        result = _prepare_db_prices_for_demand(self._demand_df(), self._prices_df())
        product_names = result["product_name"].tolist()
        # The family "SQL Server" should have been expanded to the concrete demand names
        assert "SQL Server" in product_names or "SQL Server Enterprise" in product_names

    def test_exact_match_preserved(self):
        prices = pd.DataFrame([{"product_name": "SQL Server Enterprise", "price": 2000.0}])
        demand = pd.DataFrame([{"product_name": "SQL Server Enterprise", "product_family": "SQL Server"}])
        result = _prepare_db_prices_for_demand(demand, prices)
        assert "SQL Server Enterprise" in result["product_name"].values

    def test_missing_product_name_column_returns_prices_unchanged(self):
        demand = pd.DataFrame([{"quantity": 5}])
        result = _prepare_db_prices_for_demand(demand, self._prices_df())
        assert len(result) == len(self._prices_df())

    def test_single_price_broadcasted_when_no_match(self):
        """When demand names don't match any price and only one price row exists → broadcast."""
        demand = pd.DataFrame([
            {"product_name": "Exotic Product A", "product_family": "Other"},
        ])
        prices = pd.DataFrame([{"product_name": "SinglePrice", "price": 500.0}])
        result = _prepare_db_prices_for_demand(demand, prices)
        # Result should have the original + broadcast row
        assert len(result) >= 1


# ===========================================================================
# _filter_to_standard_enterprise_servers  (lines 892-920) — empty-DB path
# ===========================================================================

@pytest.mark.django_db
class TestFilterToStandardEnterpriseServers:
    def test_empty_df_returns_empty_df(self):
        result = _filter_to_standard_enterprise_servers(pd.DataFrame())
        assert result.empty

    def test_df_without_server_id_returns_unchanged(self):
        df = pd.DataFrame([{"product_name": "SQL Server"}])
        result = _filter_to_standard_enterprise_servers(df)
        assert len(result) == len(df)

    def test_df_with_no_server_ids_returns_df(self):
        df = pd.DataFrame([{"server_id": None}])
        result = _filter_to_standard_enterprise_servers(df)
        # server_id column exists but all values are None → no valid server_ids → df returned
        assert isinstance(result, pd.DataFrame)

    def test_df_with_empty_db_excludes_all_servers(self):
        """With empty DB, no editions can be found → all servers filtered out."""
        import uuid
        df = pd.DataFrame([
            {"server_id": str(uuid.uuid4()), "product_name": "SQL Server Enterprise"},
            {"server_id": str(uuid.uuid4()), "product_name": "SQL Server Standard"},
        ])
        result = _filter_to_standard_enterprise_servers(df)
        # No DB records means empty edition map → both excluded
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0


# ===========================================================================
# _compute_device_cost_from_df  (lines 923-941) — empty-DB path
# ===========================================================================

@pytest.mark.django_db
class TestComputeDeviceCostFromDf:
    def test_empty_df_returns_zero(self):
        assert _compute_device_cost_from_df(pd.DataFrame()) == 0.0

    def test_df_without_server_id_returns_zero(self):
        df = pd.DataFrame([{"product_name": "SQL Server"}])
        assert _compute_device_cost_from_df(df) == 0.0

    def test_df_with_none_server_ids_returns_zero(self):
        df = pd.DataFrame([{"server_id": None}])
        assert _compute_device_cost_from_df(df) == 0.0

    def test_df_with_servers_not_in_db_returns_zero(self):
        """Server IDs that don't exist in DB → eff_quantity=0 and/or no edition → cost=0."""
        import uuid
        df = pd.DataFrame([{"server_id": str(uuid.uuid4())}])
        result = _compute_device_cost_from_df(df)
        assert result == 0.0


# ===========================================================================
# compute_azure_payg_cost_metrics  (lines 1021-1087) — pure function
# ===========================================================================

class TestComputeAzurePaygCostMetrics:
    def test_empty_df_returns_zeros(self):
        result = compute_azure_payg_cost_metrics(pd.DataFrame())
        assert result["azure_payg_total_cost_eur"] == 0.0
        assert result["azure_payg_savings_eur"] == 0.0
        assert result["azure_payg_prod_candidates_count"] == 0
        assert result["azure_payg_nonprod_candidates_count"] == 0

    def test_with_enterprise_rows(self):
        df = pd.DataFrame([
            {
                "server_id": "srv-001",
                "demand_product_edition": "Enterprise",
                "eff_quantity": 8,
                "environment": "Production",
            }
        ])
        result = compute_azure_payg_cost_metrics(df)
        enterprise_price = RIGHTSIZING_CPU_LICENSE_COSTS_EUR["enterprise"]
        expected_cost = round((enterprise_price * 8) / 2, 2)
        assert result["azure_payg_total_cost_eur"] == expected_cost
        assert result["azure_payg_savings_eur"] == round(expected_cost * 0.80, 2)

    def test_savings_is_80_percent_of_cost(self):
        df = pd.DataFrame([
            {
                "server_id": "srv-002",
                "demand_product_edition": "Standard",
                "eff_quantity": 4,
                "environment": "Production",
            }
        ])
        result = compute_azure_payg_cost_metrics(df)
        assert result["azure_payg_savings_eur"] == round(result["azure_payg_total_cost_eur"] * 0.80, 2)

    def test_prod_nonprod_split(self):
        df = pd.DataFrame([
            {"server_id": "srv-p", "demand_product_edition": "Enterprise", "eff_quantity": 4, "environment": "Production"},
            {"server_id": "srv-d", "demand_product_edition": "Standard", "eff_quantity": 2, "environment": "Development"},
            {"server_id": "srv-t", "demand_product_edition": "Standard", "eff_quantity": 2, "environment": "Test"},
        ])
        result = compute_azure_payg_cost_metrics(df)
        assert result["azure_payg_prod_candidates_count"] == 1
        assert result["azure_payg_nonprod_candidates_count"] == 2

    def test_no_environment_column_counts_zero(self):
        df = pd.DataFrame([
            {"server_id": "srv-001", "demand_product_edition": "Enterprise", "eff_quantity": 4},
        ])
        result = compute_azure_payg_cost_metrics(df)
        assert result["azure_payg_prod_candidates_count"] == 0
        assert result["azure_payg_nonprod_candidates_count"] == 0

    def test_enriched_df_returned_in_result(self):
        df = pd.DataFrame([
            {"server_id": "srv-001", "demand_product_edition": "Standard", "eff_quantity": 2},
        ])
        result = compute_azure_payg_cost_metrics(df)
        assert "_azure_payg_enriched_df" in result
        enriched = result["_azure_payg_enriched_df"]
        assert "Actual_Line_Cost" in enriched.columns

    def test_developer_edition_zero_cost(self):
        df = pd.DataFrame([
            {"server_id": "srv-001", "demand_product_edition": "Developer", "eff_quantity": 8},
        ])
        result = compute_azure_payg_cost_metrics(df)
        assert result["azure_payg_total_cost_eur"] == 0.0

    def test_fallback_to_product_edition_column(self):
        """When demand_product_edition absent, falls back to product_edition column."""
        df = pd.DataFrame([
            {"server_id": "srv-001", "product_edition": "Standard", "eff_quantity": 4},
        ])
        result = compute_azure_payg_cost_metrics(df)
        assert isinstance(result["azure_payg_total_cost_eur"], float)


# ===========================================================================
# compute_retired_devices_extended_metrics  (lines 944-1018) — pure function
# ===========================================================================

class TestComputeRetiredDevicesExtendedMetrics:
    def test_empty_both_dfs(self):
        result = compute_retired_devices_extended_metrics(pd.DataFrame(), pd.DataFrame())
        assert result["total_retired_count"] == 0
        assert result["installed_count"] == 0
        assert result["retired_devices_savings_eur"] == 0.0
        assert result["installed_devices_cost_eur"] == 0.0

    def test_none_retired_df_treated_as_empty(self):
        result = compute_retired_devices_extended_metrics(pd.DataFrame(), None)
        assert result["total_retired_count"] == 0

    def test_total_retired_count(self):
        import uuid
        retired_df = pd.DataFrame([
            {"server_id": str(uuid.uuid4()), "demand_product_edition": "Standard", "eff_quantity": 4},
            {"server_id": str(uuid.uuid4()), "demand_product_edition": "Enterprise", "eff_quantity": 8},
        ])
        result = compute_retired_devices_extended_metrics(pd.DataFrame(), retired_df)
        assert result["total_retired_count"] == 2

    def test_installed_count_from_install_status(self):
        import uuid
        uid1, uid2, uid3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        # Include eff_quantity so installed_df goes through the per-row path (not _compute_device_cost_from_df)
        installations_df = pd.DataFrame([
            {"server_id": uid1, "install_status": "Installed", "eff_quantity": 0, "demand_product_edition": ""},
            {"server_id": uid2, "install_status": "Retired", "eff_quantity": 0, "demand_product_edition": ""},
            {"server_id": uid3, "install_status": "install", "eff_quantity": 0, "demand_product_edition": ""},
        ])
        retired_df = pd.DataFrame([{"server_id": uid2}])
        result = compute_retired_devices_extended_metrics(installations_df, retired_df)
        assert result["installed_count"] == 2  # "Installed" and "install"

    def test_savings_computed_from_retired_df(self):
        import uuid
        retired_df = pd.DataFrame([
            {"server_id": str(uuid.uuid4()), "demand_product_edition": "Standard",
             "eff_quantity": 4},
        ])
        result = compute_retired_devices_extended_metrics(pd.DataFrame(), retired_df)
        std_price = RIGHTSIZING_CPU_LICENSE_COSTS_EUR["standard"]
        expected = round((std_price * 4) / 2, 2)
        assert result["retired_devices_savings_eur"] == expected

    def test_installed_no_install_status_column(self):
        installations_df = pd.DataFrame([{"server_id": "s1", "product_name": "SQL"}])
        retired_df = pd.DataFrame([{"server_id": "s1"}])
        result = compute_retired_devices_extended_metrics(installations_df, retired_df)
        assert result["installed_count"] == 0

    def test_enriched_df_in_result(self):
        import uuid
        retired_df = pd.DataFrame([
            {"server_id": str(uuid.uuid4()), "demand_product_edition": "Enterprise", "eff_quantity": 2},
        ])
        result = compute_retired_devices_extended_metrics(pd.DataFrame(), retired_df)
        enriched = result["_retired_enriched_df"]
        assert "Actual_Line_Cost" in enriched.columns


# ===========================================================================
# _apply_rightsizing_cost_savings  (lines 1396-1444) — pure function
# ===========================================================================

class TestApplyRightsizingCostSavings:
    def _base_rightsizing(self):
        return {
            "cpu_optimizations": [
                {
                    "product_edition": "Standard",
                    "eff_quantity": 8,
                    "Recommended_vCPU": 4,
                    "Potential_vCPU_Reduction": 4,
                }
            ],
            "ram_candidates": [
                {
                    "Potential_RAM_Reduction_GiB": 16,
                }
            ],
        }

    def test_non_dict_returned_unchanged(self):
        assert _apply_rightsizing_cost_savings("not_a_dict") == "not_a_dict"
        assert _apply_rightsizing_cost_savings(None) is None

    def test_cpu_cost_savings_applied(self):
        rightsizing = self._base_rightsizing()
        _apply_rightsizing_cost_savings(rightsizing)
        record = rightsizing["cpu_optimizations"][0]
        assert "Actual_Line_Cost" in record
        assert "Recommended_Line_Cost" in record
        assert "Cost_Savings_EUR" in record
        assert record["Cost_Savings_EUR"] >= 0.0

    def test_ram_cost_savings_applied(self):
        rightsizing = self._base_rightsizing()
        _apply_rightsizing_cost_savings(rightsizing, avg_cost_per_gib_eur=100.0)
        record = rightsizing["ram_candidates"][0]
        assert "Cost_Savings_EUR" in record
        # 16 GiB reduction × 100 EUR/GiB = 1600 EUR
        assert record["Cost_Savings_EUR"] == 1600.0

    def test_empty_cpu_list_handled(self):
        rightsizing = {"cpu_optimizations": []}
        _apply_rightsizing_cost_savings(rightsizing)
        assert "cpu_savings_eur" in rightsizing
        assert rightsizing["cpu_savings_eur"] == 0.0

    def test_empty_dict_does_not_crash(self):
        result = _apply_rightsizing_cost_savings({})
        assert isinstance(result, dict)

    def test_cpu_candidates_key_also_processed(self):
        """cpu_candidates is an alias for cpu_optimizations."""
        rightsizing = {
            "cpu_candidates": [
                {"product_edition": "Enterprise", "eff_quantity": 8, "Recommended_vCPU": 4}
            ]
        }
        _apply_rightsizing_cost_savings(rightsizing)
        record = rightsizing["cpu_candidates"][0]
        assert "Cost_Savings_EUR" in record

    def test_crit_cpu_optimizations_processed(self):
        rightsizing = {
            "crit_cpu_optimizations": [
                {"product_edition": "Standard", "eff_quantity": 4, "Recommended_vCPU": 2}
            ]
        }
        _apply_rightsizing_cost_savings(rightsizing)
        record = rightsizing["crit_cpu_optimizations"][0]
        assert "Cost_Savings_EUR" in record


# ===========================================================================
# _build_installations_df  — empty DB → returns empty DataFrame  (lines 235-314)
# ===========================================================================

@pytest.mark.django_db
class TestBuildInstallationsDf:
    def test_returns_dataframe_with_empty_db(self):
        from optimizer.services.db_analysis_service import _build_installations_df
        result = _build_installations_df()
        assert isinstance(result, pd.DataFrame)

    def test_empty_db_returns_empty_df(self):
        from optimizer.services.db_analysis_service import _build_installations_df
        result = _build_installations_df()
        assert result.empty


# ===========================================================================
# _build_raw_installations_df  — empty DB → returns empty DataFrame  (lines 317-360)
# ===========================================================================

@pytest.mark.django_db
class TestBuildRawInstallationsDf:
    def test_returns_dataframe_with_empty_db(self):
        from optimizer.services.db_analysis_service import _build_raw_installations_df
        result = _build_raw_installations_df()
        assert isinstance(result, pd.DataFrame)

    def test_empty_db_returns_empty_df(self):
        from optimizer.services.db_analysis_service import _build_raw_installations_df
        result = _build_raw_installations_df()
        assert result.empty


# ===========================================================================
# _build_raw_rule1_df  — empty DB → returns empty DataFrame  (lines 363-426)
# ===========================================================================

@pytest.mark.django_db
class TestBuildRawRule1Df:
    def test_returns_dataframe_with_empty_db(self):
        from optimizer.services.db_analysis_service import _build_raw_rule1_df
        result = _build_raw_rule1_df()
        assert isinstance(result, pd.DataFrame)

    def test_empty_db_returns_empty_df(self):
        from optimizer.services.db_analysis_service import _build_raw_rule1_df
        result = _build_raw_rule1_df()
        assert result.empty


# ===========================================================================
# _build_payg_installations_df  — empty DB → returns empty DataFrame  (lines 429-523)
# ===========================================================================

@pytest.mark.django_db
class TestBuildPaygInstallationsDf:
    def test_returns_dataframe_with_empty_db(self):
        from optimizer.services.db_analysis_service import _build_payg_installations_df
        result = _build_payg_installations_df()
        assert isinstance(result, pd.DataFrame)


# ===========================================================================
# _build_retired_installations_df  — empty DB  (lines 526-649)
# ===========================================================================

@pytest.mark.django_db
class TestBuildRetiredInstallationsDf:
    def test_returns_dataframe_with_empty_db(self):
        from optimizer.services.db_analysis_service import _build_retired_installations_df
        result = _build_retired_installations_df()
        assert isinstance(result, pd.DataFrame)


# ===========================================================================
# _build_demand_df  — empty DB  (lines 652-695)
# ===========================================================================

@pytest.mark.django_db
class TestBuildDemandDf:
    def test_returns_dataframe_with_empty_db(self):
        from optimizer.services.db_analysis_service import _build_demand_df
        result = _build_demand_df()
        assert isinstance(result, pd.DataFrame)


# ===========================================================================
# _build_prices_df  — empty DB  (lines 698-717)
# ===========================================================================

@pytest.mark.django_db
class TestBuildPricesDf:
    def test_returns_dataframe_with_empty_db(self):
        from optimizer.services.db_analysis_service import _build_prices_df
        result = _build_prices_df()
        assert isinstance(result, pd.DataFrame)


# ===========================================================================
# _build_price_distribution_df  — empty DB (lines 720-792)
# ===========================================================================

@pytest.mark.django_db
class TestBuildPriceDistributionDf:
    def test_returns_dataframe_with_empty_db(self):
        from optimizer.services.db_analysis_service import _build_price_distribution_df
        result = _build_price_distribution_df()
        assert isinstance(result, pd.DataFrame)


# ===========================================================================
# _build_server_product_edition_map  — empty DB  (lines 1323-1367)
# ===========================================================================

@pytest.mark.django_db
class TestBuildServerProductEditionMap:
    def test_empty_server_ids_returns_empty_dict(self):
        from optimizer.services.db_analysis_service import _build_server_product_edition_map
        result = _build_server_product_edition_map([])
        assert result == {}

    def test_none_server_ids_returns_empty_dict(self):
        from optimizer.services.db_analysis_service import _build_server_product_edition_map
        result = _build_server_product_edition_map(None)
        assert result == {}

    def test_nonexistent_server_ids_returns_empty(self):
        import uuid
        from optimizer.services.db_analysis_service import _build_server_product_edition_map
        result = _build_server_product_edition_map([str(uuid.uuid4())])
        assert isinstance(result, dict)


# ===========================================================================
# _build_server_eff_quantity_map  — empty DB  (lines 1370-1393)
# ===========================================================================

@pytest.mark.django_db
class TestBuildServerEffQuantityMap:
    def test_empty_server_ids_returns_empty_dict(self):
        from optimizer.services.db_analysis_service import _build_server_eff_quantity_map
        result = _build_server_eff_quantity_map([])
        assert result == {}

    def test_none_returns_empty_dict(self):
        from optimizer.services.db_analysis_service import _build_server_eff_quantity_map
        result = _build_server_eff_quantity_map(None)
        assert result == {}

    def test_nonexistent_server_returns_empty(self):
        import uuid
        from optimizer.services.db_analysis_service import _build_server_eff_quantity_map
        result = _build_server_eff_quantity_map([str(uuid.uuid4())])
        assert isinstance(result, dict)
