"""
Additional unit tests for:
  - optimizer.rules.column_utils
  - optimizer.rules.rule_azure_payg
  - optimizer.rules.rule_retired_devices

Pure pandas — no @pytest.mark.django_db required.
"""
import pytest
import pandas as pd

from optimizer.rules.column_utils import (
    find_no_license_required_column,
    no_license_required_is_zero,
)
from optimizer.rules.rule_azure_payg import find_azure_payg_candidates
from optimizer.rules.rule_retired_devices import find_retired_devices_with_installations


# ===========================================================================
# column_utils.find_no_license_required_column
# ===========================================================================

class TestFindNoLicenseRequiredColumn:
    def test_exact_column_name(self):
        df = pd.DataFrame(columns=["no_license_required", "product_name"])
        assert find_no_license_required_column(df) == "no_license_required"

    def test_no_liscence_typo_variant(self):
        df = pd.DataFrame(columns=["no_liscence_required"])
        result = find_no_license_required_column(df)
        assert result == "no_liscence_required"

    def test_case_insensitive_match(self):
        df = pd.DataFrame(columns=["No_License_Required"])
        result = find_no_license_required_column(df)
        assert result == "No_License_Required"

    def test_parentheses_variant(self):
        df = pd.DataFrame(columns=["no_license_required_(product)"])
        result = find_no_license_required_column(df)
        assert result == "no_license_required_(product)"

    def test_product_suffix_variant(self):
        df = pd.DataFrame(columns=["no_license_required_product"])
        result = find_no_license_required_column(df)
        assert result == "no_license_required_product"

    def test_returns_none_when_not_found(self):
        df = pd.DataFrame(columns=["product_name", "quantity"])
        assert find_no_license_required_column(df) is None

    def test_empty_df_returns_none(self):
        assert find_no_license_required_column(pd.DataFrame()) is None


# ===========================================================================
# column_utils.no_license_required_is_zero
# ===========================================================================

class TestNoLicenseRequiredIsZero:
    def test_zero_integer_is_true(self):
        series = pd.Series([0, 1, 0])
        result = no_license_required_is_zero(series)
        assert list(result) == [True, False, True]

    def test_zero_float_is_true(self):
        series = pd.Series([0.0, 1.0])
        result = no_license_required_is_zero(series)
        assert list(result) == [True, False]

    def test_nan_is_false(self):
        series = pd.Series([float("nan"), 0])
        result = no_license_required_is_zero(series)
        assert result[0] is False or not result[0]
        assert result[1] is True or result[1]

    def test_non_numeric_string_is_false(self):
        series = pd.Series(["N/A", "0"])
        result = no_license_required_is_zero(series)
        assert list(result) == [False, True]

    def test_none_is_false(self):
        series = pd.Series([None, 0])
        result = no_license_required_is_zero(series)
        assert not result[0]
        assert result[1]

    def test_all_zeros(self):
        series = pd.Series([0, 0, 0])
        assert all(no_license_required_is_zero(series))

    def test_all_non_zero(self):
        series = pd.Series([1, 2, 3])
        assert not any(no_license_required_is_zero(series))


# ===========================================================================
# rule_azure_payg.find_azure_payg_candidates
# ===========================================================================

def _payg_df(rows=None):
    if rows is None:
        rows = [
            {
                "u_hosting_zone": "Public Cloud",
                "inventory_status_standard": "",
                "no_license_required": 0,
                "server_name": "srv-01",
            },
            {
                "u_hosting_zone": "Private Cloud AVS",
                "inventory_status_standard": "",
                "no_license_required": 0,
                "server_name": "srv-02",
            },
            {
                "u_hosting_zone": "Private Cloud",
                "inventory_status_standard": "",
                "no_license_required": 0,
                "server_name": "srv-03",
            },
        ]
    return pd.DataFrame(rows)


class TestFindAzurePaygCandidates:
    def test_public_cloud_included(self):
        df = _payg_df()
        result = find_azure_payg_candidates(df)
        assert "srv-01" in result["server_name"].tolist()

    def test_private_cloud_avs_included(self):
        df = _payg_df()
        result = find_azure_payg_candidates(df)
        assert "srv-02" in result["server_name"].tolist()

    def test_private_cloud_excluded(self):
        df = _payg_df()
        result = find_azure_payg_candidates(df)
        assert "srv-03" not in result["server_name"].tolist()

    def test_license_included_excluded(self):
        df = pd.DataFrame([{
            "u_hosting_zone": "Public Cloud",
            "inventory_status_standard": "License Included",
            "no_license_required": 0,
            "server_name": "srv-lic",
        }])
        result = find_azure_payg_candidates(df)
        assert len(result) == 0

    def test_license_included_case_insensitive(self):
        df = pd.DataFrame([{
            "u_hosting_zone": "Public Cloud",
            "inventory_status_standard": "LICENSE INCLUDED",
            "no_license_required": 0,
            "server_name": "srv-lic",
        }])
        result = find_azure_payg_candidates(df)
        assert len(result) == 0

    def test_no_license_not_zero_excluded(self):
        df = pd.DataFrame([{
            "u_hosting_zone": "Public Cloud",
            "inventory_status_standard": "",
            "no_license_required": 1,
            "server_name": "srv-nz",
        }])
        result = find_azure_payg_candidates(df)
        assert len(result) == 0

    def test_custom_target_zones(self):
        df = pd.DataFrame([{
            "u_hosting_zone": "Functional Site",
            "inventory_status_standard": "",
            "no_license_required": 0,
            "server_name": "srv-func",
        }])
        result = find_azure_payg_candidates(df, target_zones=["Functional Site"])
        assert "srv-func" in result["server_name"].tolist()

    def test_missing_hosting_column_raises(self):
        df = pd.DataFrame([{"inventory_status_standard": "", "no_license_required": 0}])
        with pytest.raises(ValueError, match="u_hosting_zone"):
            find_azure_payg_candidates(df)

    def test_missing_inventory_column_raises(self):
        df = pd.DataFrame([{"u_hosting_zone": "Public Cloud", "no_license_required": 0}])
        with pytest.raises(ValueError, match="inventory_status_standard"):
            find_azure_payg_candidates(df)

    def test_missing_no_license_column_raises(self):
        df = pd.DataFrame([{"u_hosting_zone": "Public Cloud", "inventory_status_standard": ""}])
        with pytest.raises(ValueError, match="no_license_required"):
            find_azure_payg_candidates(df)

    def test_result_sorted_by_server_name(self):
        df = pd.DataFrame([
            {"u_hosting_zone": "Public Cloud", "inventory_status_standard": "",
             "no_license_required": 0, "server_name": "zzz"},
            {"u_hosting_zone": "Public Cloud", "inventory_status_standard": "",
             "no_license_required": 0, "server_name": "aaa"},
        ])
        result = find_azure_payg_candidates(df)
        assert result["server_name"].tolist() == ["aaa", "zzz"]

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame(columns=["u_hosting_zone", "inventory_status_standard", "no_license_required"])
        result = find_azure_payg_candidates(df)
        assert len(result) == 0

    def test_all_conditions_met_returns_all(self):
        rows = [
            {"u_hosting_zone": "Public Cloud", "inventory_status_standard": "",
             "no_license_required": 0, "server_name": f"srv-{i}"}
            for i in range(5)
        ]
        df = pd.DataFrame(rows)
        result = find_azure_payg_candidates(df)
        assert len(result) == 5


# ===========================================================================
# rule_retired_devices.find_retired_devices_with_installations
# ===========================================================================

def _retired_df(rows=None):
    if rows is None:
        rows = [
            {"install_status": "retired", "no_license_required": 0, "server_name": "srv-ret-01"},
            {"install_status": "active", "no_license_required": 0, "server_name": "srv-act-01"},
            {"install_status": "retired", "no_license_required": 1, "server_name": "srv-ret-nz"},
        ]
    return pd.DataFrame(rows)


class TestFindRetiredDevicesWithInstallations:
    def test_retired_with_zero_license_included(self):
        df = _retired_df()
        result = find_retired_devices_with_installations(df)
        assert "srv-ret-01" in result["server_name"].tolist()

    def test_active_excluded(self):
        df = _retired_df()
        result = find_retired_devices_with_installations(df)
        assert "srv-act-01" not in result["server_name"].tolist()

    def test_retired_with_non_zero_license_excluded(self):
        df = _retired_df()
        result = find_retired_devices_with_installations(df)
        assert "srv-ret-nz" not in result["server_name"].tolist()

    def test_case_insensitive_status(self):
        df = pd.DataFrame([
            {"install_status": "RETIRED", "no_license_required": 0, "server_name": "srv-upper"},
        ])
        result = find_retired_devices_with_installations(df)
        assert "srv-upper" in result["server_name"].tolist()

    def test_custom_retired_status(self):
        df = pd.DataFrame([
            {"install_status": "decommissioned", "no_license_required": 0, "server_name": "srv-decom"},
        ])
        result = find_retired_devices_with_installations(df, retired_status="decommissioned")
        assert "srv-decom" in result["server_name"].tolist()

    def test_missing_install_status_column_raises(self):
        df = pd.DataFrame([{"no_license_required": 0, "server_name": "srv-no-col"}])
        with pytest.raises(ValueError, match="install_status"):
            find_retired_devices_with_installations(df)

    def test_missing_no_license_column_raises(self):
        df = pd.DataFrame([{"install_status": "retired", "server_name": "srv-no-lic"}])
        with pytest.raises(ValueError, match="no_license_required"):
            find_retired_devices_with_installations(df)

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame(columns=["install_status", "no_license_required"])
        result = find_retired_devices_with_installations(df)
        assert len(result) == 0

    def test_install_status_with_spaces_normalised(self):
        df = pd.DataFrame([
            {"install_status": "  retired  ", "no_license_required": 0, "server_name": "srv-trim"},
        ])
        result = find_retired_devices_with_installations(df)
        assert "srv-trim" in result["server_name"].tolist()

    def test_none_no_license_excluded(self):
        df = pd.DataFrame([
            {"install_status": "retired", "no_license_required": None, "server_name": "srv-null"},
        ])
        result = find_retired_devices_with_installations(df)
        assert len(result) == 0
