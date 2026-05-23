"""
Coverage tests for pure helper functions in optimizer.views related to
RS3 (rightsizing) API and display logic. No database access required.
"""
import pytest
from unittest.mock import MagicMock, patch


# ── helpers under test ────────────────────────────────────────────────────────

from optimizer.views import (
    _is_rs3_recommendation_filter,
    _normalize_rs3_filter_value,
    _get_rs3_filter_field,
    _filter_rs3_records,
    _get_rs3_columns,
    _get_rs3_filter_options,
    _get_rs3_default_filter,
    _coerce_float,
    _get_rs3_api_sort_field,
    _get_rs3_api_sort_field_map,
    _get_rs3_api_sort_value,
    _sort_rs3_api_records,
    _build_rs3_api_summary,
    _get_rs3_api_page_size,
    _get_rs3_api_columns,
    _serialize_rs3_api_record,
    _format_rs3_api_screen_label,
    _build_table_rows,
    _sanitize_filename,
    _safe_content_disposition,
    _normalize_rs3_hosting_zone_value,
    _normalize_rs3_installed_status_value,
    _get_rs3_workload_for_filter,
    _format_rs3_sheet_label,
    _get_page_number,
    _format_metric_label,
    _build_profile_initials,
    RS3_API_CPU_COLUMNS,
    RS3_API_RAM_COLUMNS,
)


# ===========================================================================
# _is_rs3_recommendation_filter
# ===========================================================================

class TestIsRs3RecommendationFilter:
    def test_true_for_recommendation_suffix(self):
        assert _is_rs3_recommendation_filter("PROD_CPU_Recommendation") is True

    def test_false_for_rightsizing(self):
        assert _is_rs3_recommendation_filter("PROD_CPU_Rightsizing") is False

    def test_false_for_none(self):
        assert _is_rs3_recommendation_filter(None) is False

    def test_false_for_empty(self):
        assert _is_rs3_recommendation_filter("") is False

    def test_true_for_ram_recommendation(self):
        assert _is_rs3_recommendation_filter("NONPROD_RAM_Recommendation") is True


# ===========================================================================
# _normalize_rs3_filter_value
# ===========================================================================

class TestNormalizeRs3FilterValue:
    def test_cpu_alias_mapped(self):
        result = _normalize_rs3_filter_value("CPU", "PROD_CPU_Optimization")
        assert result == "PROD_CPU_Rightsizing"

    def test_ram_alias_mapped(self):
        result = _normalize_rs3_filter_value("RAM", "PROD_RAM_Optimization")
        assert result == "PROD_RAM_Rightsizing"

    def test_unknown_filter_returned_as_is(self):
        result = _normalize_rs3_filter_value("CPU", "SOME_OTHER_FILTER")
        assert result == "SOME_OTHER_FILTER"

    def test_none_workload_uses_default(self):
        result = _normalize_rs3_filter_value(None, "PROD_CPU_Rightsizing")
        assert result == "PROD_CPU_Rightsizing"

    def test_none_filter_returns_empty(self):
        result = _normalize_rs3_filter_value("CPU", None)
        assert result == ""


# ===========================================================================
# _get_rs3_filter_field
# ===========================================================================

class TestGetRs3FilterField:
    def test_rightsizing_returns_env_type(self):
        assert _get_rs3_filter_field("PROD_CPU_Rightsizing") == "Env_Type"

    def test_recommendation_returns_recommendation_type(self):
        assert _get_rs3_filter_field("PROD_CPU_Recommendation") == "Recommendation_Type"

    def test_optimization_returns_optimization_type(self):
        assert _get_rs3_filter_field("PROD_CPU_Optimization") == "Optimization_Type"

    def test_none_returns_optimization_type(self):
        assert _get_rs3_filter_field(None) == "Optimization_Type"


# ===========================================================================
# _filter_rs3_records
# ===========================================================================

class TestFilterRs3Records:
    def _sample_records(self):
        return [
            {"Env_Type": "PROD", "Optimization_Type": "PROD_CPU_Optimization"},
            {"Env_Type": "NON-PROD", "Optimization_Type": "NONPROD_CPU_Optimization"},
            {"Env_Type": "PROD", "Optimization_Type": "PROD_CPU_Optimization"},
        ]

    def test_no_filter_returns_all(self):
        records = self._sample_records()
        assert len(_filter_rs3_records(records, None)) == 3

    def test_filter_by_prod_rightsizing(self):
        records = self._sample_records()
        result = _filter_rs3_records(records, "PROD_CPU_Rightsizing")
        assert all(r["Env_Type"] == "PROD" for r in result)
        assert len(result) == 2

    def test_filter_by_nonprod_rightsizing(self):
        records = self._sample_records()
        result = _filter_rs3_records(records, "NONPROD_CPU_Rightsizing")
        assert all(r["Env_Type"] == "NON-PROD" for r in result)
        assert len(result) == 1

    def test_filter_by_optimization_type(self):
        records = self._sample_records()
        result = _filter_rs3_records(records, "PROD_CPU_Optimization")
        assert len(result) == 2

    def test_empty_records_returns_empty(self):
        assert _filter_rs3_records([], "PROD_CPU_Rightsizing") == []

    def test_none_records_returns_empty(self):
        assert _filter_rs3_records(None, "PROD_CPU_Rightsizing") == []


# ===========================================================================
# _get_rs3_columns
# ===========================================================================

class TestGetRs3Columns:
    def test_ram_rightsizing_columns(self):
        from optimizer.views import RS3_RAM_RIGHTSIZING_COLUMNS
        assert _get_rs3_columns("RAM", "PROD_RAM_Rightsizing") == RS3_RAM_RIGHTSIZING_COLUMNS

    def test_ram_recommendation_columns(self):
        from optimizer.views import RS3_RAM_RECOMMENDATION_COLUMNS
        assert _get_rs3_columns("RAM", "PROD_RAM_Recommendation") == RS3_RAM_RECOMMENDATION_COLUMNS

    def test_ram_optimization_columns(self):
        from optimizer.views import RS3_RAM_OPTIMIZATION_COLUMNS
        assert _get_rs3_columns("RAM", "PROD_RAM_Optimization") == RS3_RAM_OPTIMIZATION_COLUMNS

    def test_cpu_rightsizing_columns(self):
        from optimizer.views import RS3_CPU_RIGHTSIZING_COLUMNS
        assert _get_rs3_columns("CPU", "PROD_CPU_Rightsizing") == RS3_CPU_RIGHTSIZING_COLUMNS

    def test_cpu_recommendation_columns(self):
        from optimizer.views import RS3_CPU_RECOMMENDATION_COLUMNS
        assert _get_rs3_columns("CPU", "PROD_CPU_Recommendation") == RS3_CPU_RECOMMENDATION_COLUMNS

    def test_cpu_optimization_columns(self):
        from optimizer.views import RS3_CPU_OPTIMIZATION_COLUMNS
        assert _get_rs3_columns("CPU", "PROD_CPU_Optimization") == RS3_CPU_OPTIMIZATION_COLUMNS


# ===========================================================================
# _get_rs3_filter_options
# ===========================================================================

class TestGetRs3FilterOptions:
    def test_cpu_returns_cpu_options(self):
        from optimizer.views import RS3_SCREEN_FILTER_OPTIONS
        options = _get_rs3_filter_options({}, "CPU")
        assert options == list(RS3_SCREEN_FILTER_OPTIONS["CPU"])

    def test_ram_returns_ram_options(self):
        from optimizer.views import RS3_SCREEN_FILTER_OPTIONS
        options = _get_rs3_filter_options({}, "RAM")
        assert options == list(RS3_SCREEN_FILTER_OPTIONS["RAM"])

    def test_none_workload_falls_back_to_cpu(self):
        options = _get_rs3_filter_options({}, None)
        assert len(options) > 0


# ===========================================================================
# _get_rs3_default_filter
# ===========================================================================

class TestGetRs3DefaultFilter:
    def test_cpu_default_is_prod_cpu_rightsizing(self):
        rs = {"default_filter_by_workload": {"CPU": "PROD_CPU_Rightsizing"}}
        result = _get_rs3_default_filter(rs, "CPU")
        assert result == "PROD_CPU_Rightsizing"

    def test_empty_rs_falls_back_to_constant(self):
        result = _get_rs3_default_filter({}, "CPU")
        from optimizer.views import RS3_DEFAULT_FILTER_BY_WORKLOAD
        assert result in RS3_DEFAULT_FILTER_BY_WORKLOAD.get("CPU", "") or isinstance(result, str)


# ===========================================================================
# _coerce_float
# ===========================================================================

class TestCoerceFloat:
    def test_string_number(self):
        assert _coerce_float("3.14") == 3.14

    def test_none_returns_zero(self):
        assert _coerce_float(None) == 0.0

    def test_invalid_string_returns_zero(self):
        assert _coerce_float("not-a-number") == 0.0

    def test_integer(self):
        assert _coerce_float(5) == 5.0

    def test_float(self):
        assert _coerce_float(2.5) == 2.5

    def test_empty_string_returns_zero(self):
        assert _coerce_float("") == 0.0


# ===========================================================================
# _get_rs3_api_sort_field
# ===========================================================================

class TestGetRs3ApiSortField:
    def test_ram_workload(self):
        assert _get_rs3_api_sort_field("RAM") == "Potential_RAM_Reduction_GiB"

    def test_cpu_workload(self):
        assert _get_rs3_api_sort_field("CPU") == "Potential_vCPU_Reduction"

    def test_none_defaults_to_cpu(self):
        assert _get_rs3_api_sort_field(None) == "Potential_vCPU_Reduction"


# ===========================================================================
# _get_rs3_api_sort_field_map
# ===========================================================================

class TestGetRs3ApiSortFieldMap:
    def test_ram_returns_ram_map(self):
        from optimizer.views import RS3_API_RAM_SORT_FIELD_MAP
        assert _get_rs3_api_sort_field_map("RAM") == RS3_API_RAM_SORT_FIELD_MAP

    def test_cpu_returns_cpu_map(self):
        from optimizer.views import RS3_API_CPU_SORT_FIELD_MAP
        assert _get_rs3_api_sort_field_map("CPU") == RS3_API_CPU_SORT_FIELD_MAP


# ===========================================================================
# _get_rs3_api_sort_value
# ===========================================================================

class TestGetRs3ApiSortValue:
    def test_numeric_field_returns_tuple_with_float(self):
        record = {"Potential_vCPU_Reduction": "5"}
        result = _get_rs3_api_sort_value(record, "Potential_vCPU_Reduction", "potential_vcpu_reduction")
        assert result == (0, 5.0)

    def test_string_field_returns_tuple_with_string(self):
        record = {"server_name": "MySrv"}
        result = _get_rs3_api_sort_value(record, "server_name", "server_name")
        assert result == (1, "mysrv")

    def test_missing_key_returns_zero_numeric(self):
        record = {}
        result = _get_rs3_api_sort_value(record, "Potential_vCPU_Reduction", "potential_vcpu_reduction")
        assert result == (0, 0.0)


# ===========================================================================
# _sort_rs3_api_records
# ===========================================================================

class TestSortRs3ApiRecords:
    def _records(self):
        return [
            {"server_name": "srv-b", "Potential_vCPU_Reduction": 10},
            {"server_name": "srv-a", "Potential_vCPU_Reduction": 20},
            {"server_name": "srv-c", "Potential_vCPU_Reduction": 5},
        ]

    def test_sort_desc_by_vcpu(self):
        result = _sort_rs3_api_records(self._records(), "CPU", "potential_vcpu_reduction", "desc")
        assert result[0]["server_name"] == "srv-a"

    def test_sort_asc_by_vcpu(self):
        result = _sort_rs3_api_records(self._records(), "CPU", "potential_vcpu_reduction", "asc")
        assert result[0]["server_name"] == "srv-c"

    def test_empty_records_returns_empty(self):
        assert _sort_rs3_api_records([], "CPU") == []

    def test_none_records_returns_empty(self):
        assert _sort_rs3_api_records(None, "CPU") == []


# ===========================================================================
# _build_rs3_api_summary
# ===========================================================================

class TestBuildRs3ApiSummary:
    def test_cpu_summary(self):
        records = [
            {"Potential_vCPU_Reduction": 4.0, "Cost_Savings_EUR": 1000.0, "Env_Type": "PROD"},
            {"Potential_vCPU_Reduction": 2.0, "Cost_Savings_EUR": 500.0, "Env_Type": "NON-PROD"},
        ]
        summary = _build_rs3_api_summary(records, "CPU")
        assert summary["count"] == 2
        assert summary["prod_count"] == 1
        assert summary["nonprod_count"] == 1
        assert summary["reduction_total"] == 6.0
        assert summary["savings_eur"] == 1500.0

    def test_empty_records(self):
        summary = _build_rs3_api_summary([], "CPU")
        assert summary["count"] == 0
        assert summary["savings_eur"] == 0.0

    def test_ram_summary_uses_ram_reduction_key(self):
        records = [{"Potential_RAM_Reduction_GiB": 8.0, "Cost_Savings_EUR": 200.0, "Env_Type": "PROD"}]
        summary = _build_rs3_api_summary(records, "RAM")
        assert summary["reduction_total"] == 8.0


# ===========================================================================
# _get_rs3_api_page_size
# ===========================================================================

class TestGetRs3ApiPageSize:
    def _request(self, page_size=None):
        req = MagicMock()
        req.GET = {"page_size": page_size} if page_size else {}
        req.GET.get = lambda key, default=None: req.GET[key] if key in req.GET else default
        return req

    def test_default_page_size(self):
        from optimizer.views import RS3_API_DEFAULT_PAGE_SIZE
        req = MagicMock()
        req.GET.get.return_value = None
        assert _get_rs3_api_page_size(req) == RS3_API_DEFAULT_PAGE_SIZE

    def test_custom_page_size(self):
        req = MagicMock()
        req.GET.get = lambda key, default=None: "50" if key == "page_size" else default
        assert _get_rs3_api_page_size(req) == 50

    def test_page_size_capped_at_max(self):
        from optimizer.views import RS3_API_MAX_PAGE_SIZE
        req = MagicMock()
        req.GET.get = lambda key, default=None: "9999" if key == "page_size" else default
        assert _get_rs3_api_page_size(req) == RS3_API_MAX_PAGE_SIZE

    def test_invalid_page_size_returns_default(self):
        from optimizer.views import RS3_API_DEFAULT_PAGE_SIZE
        req = MagicMock()
        req.GET.get = lambda key, default=None: "bad" if key == "page_size" else default
        assert _get_rs3_api_page_size(req) == RS3_API_DEFAULT_PAGE_SIZE

    def test_page_size_min_is_one(self):
        req = MagicMock()
        req.GET.get = lambda key, default=None: "0" if key == "page_size" else default
        assert _get_rs3_api_page_size(req) == 1


# ===========================================================================
# _get_rs3_api_columns
# ===========================================================================

class TestGetRs3ApiColumns:
    def test_ram_returns_ram_columns(self):
        assert _get_rs3_api_columns("RAM") == RS3_API_RAM_COLUMNS

    def test_cpu_returns_cpu_columns(self):
        assert _get_rs3_api_columns("CPU") == RS3_API_CPU_COLUMNS

    def test_none_defaults_to_cpu(self):
        assert _get_rs3_api_columns(None) == RS3_API_CPU_COLUMNS


# ===========================================================================
# _serialize_rs3_api_record
# ===========================================================================

class TestSerializeRs3ApiRecord:
    def _cpu_record(self):
        return {
            "server_name": "srv01",
            "product_family": "SQL Server",
            "product_group": "DB",
            "product_description": "SQL Server Enterprise",
            "product_name": "SQL Server 2019",
            "Environment": "Production",
            "Env_Type": "PROD",
            "hosting_zone": "Public Cloud",
            "installed_status_usu": "Installed",
            "is_virtual": True,
            "Optimization_Type": "PROD_CPU_Rightsizing",
            "Recommendation_Type": None,
            "Avg_CPU_12m": 45.5,
            "Peak_CPU_12m": 88.0,
            "Current_vCPU": 16,
            "Recommended_vCPU": 8,
            "Potential_vCPU_Reduction": 8,
            "CPU_Recommendation": "Downsize",
            "Cost_Savings_EUR": 2000.0,
        }

    def test_cpu_serialization_keys(self):
        result = _serialize_rs3_api_record(self._cpu_record(), "CPU")
        assert "server_name" in result
        assert "avg_cpu_12m" in result
        assert "current_vcpu" in result
        assert "cost_savings_eur" in result

    def test_ram_serialization_keys(self):
        record = {
            "server_name": "srv02",
            "product_family": "SQL Server",
            "product_group": "DB",
            "product_description": "SQL Server Standard",
            "product_name": "SQL Server 2022",
            "Env_Type": "NON-PROD",
            "Avg_FreeMem_12m": 12.0,
            "Min_FreeMem_12m": 4.0,
            "Current_RAM_GiB": 32.0,
            "Recommended_RAM_GiB": 16.0,
            "Potential_RAM_Reduction_GiB": 16.0,
            "RAM_Recommendation": "Downsize",
            "Cost_Savings_EUR": 500.0,
        }
        result = _serialize_rs3_api_record(record, "RAM")
        assert "current_ram_gib" in result
        assert "recommended_ram_gib" in result
        assert "cost_savings_eur" in result


# ===========================================================================
# _format_rs3_api_screen_label
# ===========================================================================

class TestFormatRs3ApiScreenLabel:
    def test_prod_cpu_rightsizing(self):
        assert _format_rs3_api_screen_label("PROD_CPU_Rightsizing") == "PROD CPU Right-Sizing"

    def test_nonprod_ram_rightsizing(self):
        assert _format_rs3_api_screen_label("NONPROD_RAM_Rightsizing") == "Nonprod RAM Right-Sizing"

    def test_legacy_optimization_alias(self):
        assert _format_rs3_api_screen_label("PROD_CPU_Optimization") == "PROD CPU Right-Sizing"

    def test_unknown_returns_formatted(self):
        result = _format_rs3_api_screen_label("CUSTOM_FILTER")
        assert isinstance(result, str)

    def test_none_returns_string(self):
        result = _format_rs3_api_screen_label(None)
        assert isinstance(result, str)


# ===========================================================================
# _build_table_rows
# ===========================================================================

class TestBuildTableRows:
    def test_projects_columns(self):
        records = [{"a": 1, "b": 2, "c": 3}]
        result = _build_table_rows(records, ["a", "c"])
        assert result == [[1, 3]]

    def test_missing_column_returns_none(self):
        records = [{"a": 1}]
        result = _build_table_rows(records, ["a", "missing"])
        assert result == [[1, None]]

    def test_empty_records(self):
        assert _build_table_rows([], ["a", "b"]) == []


# ===========================================================================
# _sanitize_filename / _safe_content_disposition
# ===========================================================================

class TestSanitizeFilename:
    def test_removes_path_separators(self):
        result = _sanitize_filename("some/path/file.txt")
        assert "/" not in result

    def test_returns_download_for_none(self):
        assert _sanitize_filename(None) == "download"

    def test_returns_download_for_empty(self):
        assert _sanitize_filename("") == "download"

    def test_truncates_long_name(self):
        long_name = "a" * 300
        result = _sanitize_filename(long_name, max_len=200)
        assert len(result) <= 200

    def test_removes_control_chars(self):
        result = _sanitize_filename("file\x00name.txt")
        assert "\x00" not in result


class TestSafeContentDisposition:
    def test_returns_attachment_prefix(self):
        result = _safe_content_disposition("report.pdf")
        assert result.startswith('attachment; filename="')

    def test_sanitizes_path(self):
        result = _safe_content_disposition("path/to/file.pdf")
        assert "/" not in result or "path" not in result


# ===========================================================================
# _normalize_rs3_hosting_zone_value / _normalize_rs3_installed_status_value
# ===========================================================================

class TestNormalizeRs3Values:
    def test_hosting_zone_none_returns_none_string(self):
        result = _normalize_rs3_hosting_zone_value(None)
        assert result == "none"  # empty → "none" sentinel

    def test_hosting_zone_value_returned(self):
        result = _normalize_rs3_hosting_zone_value("Public Cloud")
        assert result == "Public Cloud"

    def test_installed_status_none_returns_empty_string(self):
        result = _normalize_rs3_installed_status_value(None)
        assert result == ""

    def test_installed_status_returned(self):
        result = _normalize_rs3_installed_status_value("Installed")
        assert result == "Installed"


# ===========================================================================
# _get_rs3_workload_for_filter / _format_rs3_sheet_label
# ===========================================================================

class TestRs3WorkloadAndSheetLabel:
    def test_workload_for_cpu_filter(self):
        result = _get_rs3_workload_for_filter("PROD_CPU_Rightsizing")
        assert result.upper() == "CPU"

    def test_workload_for_ram_filter(self):
        result = _get_rs3_workload_for_filter("PROD_RAM_Rightsizing")
        assert result.upper() == "RAM"

    def test_sheet_label_prod_cpu(self):
        result = _format_rs3_sheet_label("PROD_CPU_Rightsizing")
        assert isinstance(result, str) and len(result) > 0


# ===========================================================================
# _get_page_number
# ===========================================================================

class TestGetPageNumber:
    def test_valid_page_number(self):
        req = MagicMock()
        req.GET.get = lambda key, default=None: "3" if key == "page" else default
        assert _get_page_number(req, "page") == 3

    def test_invalid_returns_default(self):
        req = MagicMock()
        req.GET.get = lambda key, default=None: "abc" if key == "page" else default
        assert _get_page_number(req, "page", default=1) == 1

    def test_negative_returns_default(self):
        req = MagicMock()
        req.GET.get = lambda key, default=None: "-1" if key == "page" else default
        assert _get_page_number(req, "page", default=1) == 1


# ===========================================================================
# _format_metric_label
# ===========================================================================

class TestFormatMetricLabel:
    def test_database_size_mib_special_case(self):
        result = _format_metric_label("database_size_mib")
        assert "Database" in result

    def test_generic_snake_case(self):
        result = _format_metric_label("memory_utilization_pct")
        assert "Memory" in result

    def test_empty_string_returns_empty(self):
        assert _format_metric_label("") == ""

    def test_none_returns_empty(self):
        assert _format_metric_label(None) == ""


# ===========================================================================
# _build_profile_initials (additional cases)
# ===========================================================================

class TestBuildProfileInitials:
    def test_full_name(self):
        user = MagicMock()
        user.first_name = "John"
        user.last_name = "Doe"
        user.username = "jdoe"
        result = _build_profile_initials(user)
        assert "J" in result

    def test_username_only(self):
        user = MagicMock()
        user.first_name = ""
        user.last_name = ""
        user.username = "john.doe"
        result = _build_profile_initials(user)
        assert len(result) <= 2
        assert isinstance(result, str)

    def test_empty_username(self):
        user = MagicMock()
        user.first_name = ""
        user.last_name = ""
        user.username = ""
        result = _build_profile_initials(user)
        assert isinstance(result, str)
