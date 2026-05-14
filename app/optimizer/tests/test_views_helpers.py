"""
Unit tests for pure helper functions in optimizer.views.
No database access required — no @pytest.mark.django_db.
"""
import pytest
import pandas as pd

from optimizer.views import (
    _make_json_serializable,
    _build_rs3_download_dataframe,
    _get_rs3_api_sort_params,
    _parse_rs3_multi_value_query_param,
    _safe_content_disposition,
    _get_rs3_api_page_size,
    _format_metric_label,
    _is_rs3_recommendation_filter,
    _normalize_rs3_filter_value,
    _get_rs3_filter_field,
    _filter_rs3_records,
    _get_rs3_columns,
    _get_rs3_filter_options,
    _get_rs3_default_filter,
    _get_rs3_summary,
    _get_rs3_workload_for_filter,
    _format_rs3_sheet_label,
    _build_rs3_download_sheet_options,
    _normalize_rs3_hosting_zone_value,
    _normalize_rs3_installed_status_value,
    _canonicalize_rs3_filter_values,
    _filter_rs3_api_records,
    _coerce_float,
    _get_rs3_api_sort_field,
    _get_rs3_api_sort_field_map,
    _get_rs3_api_sort_value,
    _sort_rs3_api_records,
    _build_rs3_api_summary,
    _get_rs3_api_columns,
    _serialize_rs3_api_record,
    _format_rs3_api_screen_label,
    _build_table_rows,
    _sanitize_filename,
    RS3_CPU_RIGHTSIZING_COLUMNS,
    RS3_CPU_OPTIMIZATION_COLUMNS,
    RS3_CPU_RECOMMENDATION_COLUMNS,
    RS3_RAM_RIGHTSIZING_COLUMNS,
    RS3_RAM_OPTIMIZATION_COLUMNS,
    RS3_RAM_RECOMMENDATION_COLUMNS,
    RS3_SCREEN_FILTER_OPTIONS,
    RS3_API_HOSTING_ZONE_OPTIONS,
    RS3_API_INSTALLED_STATUS_USU_OPTIONS,
    RS3_API_NUMERIC_SORT_FIELDS,
    RS3_API_CPU_COLUMNS,
    RS3_API_RAM_COLUMNS,
    RS3_API_DEFAULT_PAGE_SIZE,
    RS3_API_MAX_PAGE_SIZE,
)


# ===========================================================================
# _format_metric_label
# ===========================================================================

class TestFormatMetricLabel:
    def test_database_size_mib_special_case(self):
        assert _format_metric_label("database_size_mib") == "Database Size Mmib"

    def test_normal_underscore_name(self):
        assert _format_metric_label("cpu_usage_pct") == "Cpu Usage Pct"

    def test_single_word(self):
        assert _format_metric_label("memory") == "Memory"

    def test_none_returns_empty(self):
        assert _format_metric_label(None) == ""

    def test_empty_string_returns_empty(self):
        assert _format_metric_label("") == ""

    def test_whitespace_only_returns_empty(self):
        assert _format_metric_label("   ") == ""

    def test_strips_leading_trailing_spaces(self):
        assert _format_metric_label("  cpu_util  ") == "Cpu Util"

    def test_consecutive_underscores_ignored(self):
        result = _format_metric_label("a__b")
        assert "A" in result and "B" in result


# ===========================================================================
# _is_rs3_recommendation_filter
# ===========================================================================

class TestIsRs3RecommendationFilter:
    def test_ends_with_recommendation(self):
        assert _is_rs3_recommendation_filter("PROD_CPU_Recommendation") is True

    def test_nonprod_recommendation(self):
        assert _is_rs3_recommendation_filter("NONPROD_RAM_Recommendation") is True

    def test_rightsizing_returns_false(self):
        assert _is_rs3_recommendation_filter("PROD_CPU_Rightsizing") is False

    def test_optimization_returns_false(self):
        assert _is_rs3_recommendation_filter("PROD_CPU_Optimization") is False

    def test_none_returns_false(self):
        assert _is_rs3_recommendation_filter(None) is False

    def test_empty_string_returns_false(self):
        assert _is_rs3_recommendation_filter("") is False


# ===========================================================================
# _normalize_rs3_filter_value
# ===========================================================================

class TestNormalizeRs3FilterValue:
    def test_cpu_optimization_aliased_to_rightsizing(self):
        result = _normalize_rs3_filter_value("CPU", "PROD_CPU_Optimization")
        assert result == "PROD_CPU_Rightsizing"

    def test_cpu_recommendation_aliased_to_rightsizing(self):
        result = _normalize_rs3_filter_value("CPU", "PROD_CPU_Recommendation")
        assert result == "PROD_CPU_Rightsizing"

    def test_nonprod_cpu_optimization_aliased(self):
        result = _normalize_rs3_filter_value("CPU", "NONPROD_CPU_Optimization")
        assert result == "NONPROD_CPU_Rightsizing"

    def test_ram_optimization_aliased(self):
        result = _normalize_rs3_filter_value("RAM", "PROD_RAM_Optimization")
        assert result == "PROD_RAM_Rightsizing"

    def test_ram_recommendation_aliased(self):
        result = _normalize_rs3_filter_value("RAM", "NONPROD_RAM_Recommendation")
        assert result == "NONPROD_RAM_Rightsizing"

    def test_unknown_workload_returns_unchanged(self):
        result = _normalize_rs3_filter_value("OTHER", "PROD_CPU_Optimization")
        assert result == "PROD_CPU_Optimization"

    def test_none_workload_treated_as_all(self):
        result = _normalize_rs3_filter_value(None, "PROD_CPU_Optimization")
        assert result == "PROD_CPU_Optimization"

    def test_none_filter_value_returns_empty(self):
        result = _normalize_rs3_filter_value("CPU", None)
        assert result == ""

    def test_already_canonical_value_unchanged(self):
        result = _normalize_rs3_filter_value("CPU", "PROD_CPU_Rightsizing")
        assert result == "PROD_CPU_Rightsizing"

    def test_case_insensitive_workload(self):
        result = _normalize_rs3_filter_value("cpu", "PROD_CPU_Optimization")
        assert result == "PROD_CPU_Rightsizing"


# ===========================================================================
# _get_rs3_filter_field
# ===========================================================================

class TestGetRs3FilterField:
    def test_rightsizing_returns_env_type(self):
        assert _get_rs3_filter_field("PROD_CPU_Rightsizing") == "Env_Type"

    def test_nonprod_rightsizing_returns_env_type(self):
        assert _get_rs3_filter_field("NONPROD_RAM_Rightsizing") == "Env_Type"

    def test_recommendation_returns_recommendation_type(self):
        assert _get_rs3_filter_field("PROD_CPU_Recommendation") == "Recommendation_Type"

    def test_optimization_returns_optimization_type(self):
        assert _get_rs3_filter_field("PROD_CPU_Optimization") == "Optimization_Type"

    def test_none_returns_optimization_type(self):
        assert _get_rs3_filter_field(None) == "Optimization_Type"

    def test_empty_returns_optimization_type(self):
        assert _get_rs3_filter_field("") == "Optimization_Type"


# ===========================================================================
# _filter_rs3_records
# ===========================================================================

class TestFilterRs3Records:
    def _records(self):
        return [
            {"Env_Type": "PROD", "Recommendation_Type": "PROD_CPU_Recommendation", "Optimization_Type": "Crit_CPU"},
            {"Env_Type": "NON-PROD", "Recommendation_Type": "NONPROD_CPU_Recommendation", "Optimization_Type": "Crit_CPU"},
            {"Env_Type": "PROD", "Recommendation_Type": "PROD_RAM_Recommendation", "Optimization_Type": "Crit_RAM"},
        ]

    def test_none_filter_returns_all(self):
        records = self._records()
        result = _filter_rs3_records(records, None)
        assert len(result) == 3

    def test_empty_filter_returns_all(self):
        records = self._records()
        result = _filter_rs3_records(records, "")
        assert len(result) == 3

    def test_prod_rightsizing_filters_prod_only(self):
        result = _filter_rs3_records(self._records(), "PROD_CPU_Rightsizing")
        assert all(r["Env_Type"] == "PROD" for r in result)
        assert len(result) == 2

    def test_nonprod_rightsizing_filters_nonprod_only(self):
        result = _filter_rs3_records(self._records(), "NONPROD_CPU_Rightsizing")
        assert all(r["Env_Type"] == "NON-PROD" for r in result)
        assert len(result) == 1

    def test_recommendation_type_filter(self):
        result = _filter_rs3_records(self._records(), "PROD_CPU_Recommendation")
        assert len(result) == 1
        assert result[0]["Recommendation_Type"] == "PROD_CPU_Recommendation"

    def test_optimization_type_filter(self):
        result = _filter_rs3_records(self._records(), "Crit_CPU")
        assert len(result) == 2

    def test_none_records_returns_empty_list(self):
        assert _filter_rs3_records(None, "PROD_CPU_Rightsizing") == []

    def test_empty_records_returns_empty_list(self):
        assert _filter_rs3_records([], "PROD_CPU_Rightsizing") == []


# ===========================================================================
# _get_rs3_columns
# ===========================================================================

class TestGetRs3Columns:
    def test_cpu_rightsizing_returns_rightsizing_columns(self):
        cols = _get_rs3_columns("CPU", "PROD_CPU_Rightsizing")
        assert cols is RS3_CPU_RIGHTSIZING_COLUMNS

    def test_cpu_optimization_returns_optimization_columns(self):
        cols = _get_rs3_columns("CPU", "PROD_CPU_Optimization")
        assert cols is RS3_CPU_OPTIMIZATION_COLUMNS

    def test_cpu_recommendation_returns_recommendation_columns(self):
        cols = _get_rs3_columns("CPU", "PROD_CPU_Recommendation")
        assert cols is RS3_CPU_RECOMMENDATION_COLUMNS

    def test_ram_rightsizing_returns_ram_rightsizing_columns(self):
        cols = _get_rs3_columns("RAM", "PROD_RAM_Rightsizing")
        assert cols is RS3_RAM_RIGHTSIZING_COLUMNS

    def test_ram_optimization_returns_ram_optimization_columns(self):
        cols = _get_rs3_columns("RAM", "PROD_RAM_Optimization")
        assert cols is RS3_RAM_OPTIMIZATION_COLUMNS

    def test_ram_recommendation_returns_ram_recommendation_columns(self):
        cols = _get_rs3_columns("RAM", "PROD_RAM_Recommendation")
        assert cols is RS3_RAM_RECOMMENDATION_COLUMNS

    def test_cpu_default_for_unknown_workload(self):
        cols = _get_rs3_columns(None, "PROD_CPU_Rightsizing")
        assert cols is RS3_CPU_RIGHTSIZING_COLUMNS

    def test_case_insensitive_workload(self):
        cols = _get_rs3_columns("ram", "PROD_RAM_Rightsizing")
        assert cols is RS3_RAM_RIGHTSIZING_COLUMNS


# ===========================================================================
# _get_rs3_filter_options
# ===========================================================================

class TestGetRs3FilterOptions:
    def test_cpu_workload_returns_cpu_options(self):
        result = _get_rs3_filter_options({}, "CPU")
        assert result == RS3_SCREEN_FILTER_OPTIONS["CPU"]

    def test_ram_workload_returns_ram_options(self):
        result = _get_rs3_filter_options({}, "RAM")
        assert result == RS3_SCREEN_FILTER_OPTIONS["RAM"]

    def test_unknown_workload_falls_back_to_cpu(self):
        result = _get_rs3_filter_options({}, "OTHER")
        assert result == RS3_SCREEN_FILTER_OPTIONS["CPU"]

    def test_none_workload_falls_back_to_cpu(self):
        result = _get_rs3_filter_options({}, None)
        assert result == RS3_SCREEN_FILTER_OPTIONS["CPU"]

    def test_custom_options_from_rs(self):
        rs = {"screen_filter_options": {"CUSTOM": ["opt1", "opt2"]}}
        result = _get_rs3_filter_options(rs, "CUSTOM")
        assert result == ["opt1", "opt2"]

    def test_returns_copy_not_original(self):
        result = _get_rs3_filter_options({}, "CPU")
        result.append("extra")
        assert "extra" not in RS3_SCREEN_FILTER_OPTIONS["CPU"]


# ===========================================================================
# _get_rs3_default_filter
# ===========================================================================

class TestGetRs3DefaultFilter:
    def test_cpu_workload_returns_prod_cpu_rightsizing(self):
        result = _get_rs3_default_filter({}, "CPU")
        assert result == "PROD_CPU_Rightsizing"

    def test_ram_workload_returns_prod_ram_rightsizing(self):
        result = _get_rs3_default_filter({}, "RAM")
        assert result == "PROD_RAM_Rightsizing"

    def test_custom_default_from_rs(self):
        rs = {"default_filter_by_workload": {"CPU": "NONPROD_CPU_Rightsizing"}}
        result = _get_rs3_default_filter(rs, "CPU")
        assert result == "NONPROD_CPU_Rightsizing"

    def test_fallback_to_first_option_when_not_in_options(self):
        rs = {"default_filter_by_workload": {"CPU": "INVALID_FILTER"}}
        result = _get_rs3_default_filter(rs, "CPU")
        assert result == RS3_SCREEN_FILTER_OPTIONS["CPU"][0]

    def test_none_workload_treated_as_all(self):
        result = _get_rs3_default_filter({}, None)
        assert isinstance(result, str)
        assert len(result) > 0


# ===========================================================================
# _get_rs3_summary
# ===========================================================================

class TestGetRs3Summary:
    def _records(self):
        return [
            {"Env_Type": "PROD", "Potential_vCPU_Reduction": 4.0},
            {"Env_Type": "PROD", "Potential_vCPU_Reduction": 2.0},
            {"Env_Type": "NON-PROD", "Potential_vCPU_Reduction": 1.0},
        ]

    def test_count_all_records_for_rightsizing_filter(self):
        result = _get_rs3_summary({}, "CPU", "PROD_CPU_Rightsizing", self._records())
        assert result["count"] == 2
        assert result["prod_count"] == 2
        assert result["nonprod_count"] == 0

    def test_reduction_total_computed(self):
        result = _get_rs3_summary({}, "CPU", "PROD_CPU_Rightsizing", self._records())
        assert result["reduction_total"] == 6.0

    def test_nonprod_filter_counts_nonprod(self):
        result = _get_rs3_summary({}, "CPU", "NONPROD_CPU_Rightsizing", self._records())
        assert result["count"] == 1
        assert result["nonprod_count"] == 1

    def test_cached_summary_returned_if_present(self):
        cached = {"count": 99, "prod_count": 99, "nonprod_count": 0, "reduction_total": 0.0}
        rs = {"screen_summaries": {"CPU": {"PROD_CPU_Rightsizing": cached}}}
        result = _get_rs3_summary(rs, "CPU", "PROD_CPU_Rightsizing", self._records())
        assert result["count"] == 99

    def test_ram_uses_ram_reduction_key(self):
        records = [{"Env_Type": "PROD", "Potential_RAM_Reduction_GiB": 8.0}]
        result = _get_rs3_summary({}, "RAM", "PROD_RAM_Rightsizing", records)
        assert result["reduction_total"] == 8.0

    def test_empty_records_returns_zeros(self):
        result = _get_rs3_summary({}, "CPU", "PROD_CPU_Rightsizing", [])
        assert result["count"] == 0
        assert result["reduction_total"] == 0.0

    def test_non_numeric_reduction_skipped(self):
        records = [{"Env_Type": "PROD", "Potential_vCPU_Reduction": "N/A"}]
        result = _get_rs3_summary({}, "CPU", "PROD_CPU_Rightsizing", records)
        assert result["reduction_total"] == 0.0

    def test_filter_alias_normalised_before_cache_lookup(self):
        cached = {"count": 42, "prod_count": 42, "nonprod_count": 0, "reduction_total": 0.0}
        rs = {"screen_summaries": {"CPU": {"PROD_CPU_Rightsizing": cached}}}
        result = _get_rs3_summary(rs, "CPU", "PROD_CPU_Optimization", self._records())
        assert result["count"] == 42


# ===========================================================================
# _get_rs3_workload_for_filter
# ===========================================================================

class TestGetRs3WorkloadForFilter:
    def test_ram_filter_returns_ram(self):
        assert _get_rs3_workload_for_filter("PROD_RAM_Rightsizing") == "RAM"

    def test_cpu_filter_returns_cpu(self):
        assert _get_rs3_workload_for_filter("PROD_CPU_Rightsizing") == "CPU"

    def test_none_returns_cpu(self):
        assert _get_rs3_workload_for_filter(None) == "CPU"

    def test_empty_returns_cpu(self):
        assert _get_rs3_workload_for_filter("") == "CPU"

    def test_nonprod_ram_returns_ram(self):
        assert _get_rs3_workload_for_filter("NONPROD_RAM_Optimization") == "RAM"


# ===========================================================================
# _format_rs3_sheet_label
# ===========================================================================

class TestFormatRs3SheetLabel:
    def test_prod_cpu_rightsizing(self):
        label = _format_rs3_sheet_label("PROD_CPU_Rightsizing")
        assert label == "Prod Cpu Rightsizing"

    def test_nonprod_ram_rightsizing(self):
        label = _format_rs3_sheet_label("NONPROD_RAM_Rightsizing")
        assert label == "Nonprod Ram Rightsizing"

    def test_none_returns_empty(self):
        label = _format_rs3_sheet_label(None)
        assert label == ""

    def test_alias_resolved_before_formatting(self):
        label = _format_rs3_sheet_label("PROD_CPU_Optimization")
        assert label == "Prod Cpu Rightsizing"


# ===========================================================================
# _build_rs3_download_sheet_options
# ===========================================================================

class TestBuildRs3DownloadSheetOptions:
    def test_returns_list(self):
        result = _build_rs3_download_sheet_options({})
        assert isinstance(result, list)

    def test_contains_cpu_and_ram_workloads(self):
        result = _build_rs3_download_sheet_options({})
        workloads = {opt["workload"] for opt in result}
        assert "CPU" in workloads
        assert "RAM" in workloads

    def test_each_option_has_value_label_workload(self):
        result = _build_rs3_download_sheet_options({})
        for opt in result:
            assert "value" in opt
            assert "label" in opt
            assert "workload" in opt

    def test_default_produces_four_options(self):
        result = _build_rs3_download_sheet_options({})
        assert len(result) == 4


# ===========================================================================
# _normalize_rs3_hosting_zone_value
# ===========================================================================

class TestNormalizeRs3HostingZoneValue:
    def test_normal_value_unchanged(self):
        assert _normalize_rs3_hosting_zone_value("Public Cloud") == "Public Cloud"

    def test_strips_whitespace(self):
        assert _normalize_rs3_hosting_zone_value("  Private Cloud  ") == "Private Cloud"

    def test_none_returns_none_string(self):
        assert _normalize_rs3_hosting_zone_value(None) == "none"

    def test_empty_returns_none_string(self):
        assert _normalize_rs3_hosting_zone_value("") == "none"

    def test_whitespace_only_returns_none_string(self):
        assert _normalize_rs3_hosting_zone_value("   ") == "none"


# ===========================================================================
# _normalize_rs3_installed_status_value
# ===========================================================================

class TestNormalizeRs3InstalledStatusValue:
    def test_normal_value_stripped(self):
        assert _normalize_rs3_installed_status_value("  Installed  ") == "Installed"

    def test_none_returns_empty(self):
        assert _normalize_rs3_installed_status_value(None) == ""

    def test_empty_returns_empty(self):
        assert _normalize_rs3_installed_status_value("") == ""


# ===========================================================================
# _canonicalize_rs3_filter_values
# ===========================================================================

class TestCanonicalize_Rs3FilterValues:
    def _normalizer(self, v):
        return str(v or "").strip()

    def test_valid_values_returned_canonical(self):
        canonical, invalid = _canonicalize_rs3_filter_values(
            ["public cloud", "Private Cloud"],
            RS3_API_HOSTING_ZONE_OPTIONS,
            self._normalizer,
        )
        assert "Public Cloud" in canonical
        assert "Private Cloud" in canonical

    def test_invalid_values_separated(self):
        canonical, invalid = _canonicalize_rs3_filter_values(
            ["Unknown Zone"],
            RS3_API_HOSTING_ZONE_OPTIONS,
            self._normalizer,
        )
        assert canonical == []
        assert "Unknown Zone" in invalid

    def test_deduplication(self):
        canonical, _ = _canonicalize_rs3_filter_values(
            ["Public Cloud", "public cloud"],
            RS3_API_HOSTING_ZONE_OPTIONS,
            self._normalizer,
        )
        assert len(canonical) == 1

    def test_case_insensitive_matching(self):
        canonical, _ = _canonicalize_rs3_filter_values(
            ["INSTALLED"],
            RS3_API_INSTALLED_STATUS_USU_OPTIONS,
            self._normalizer,
        )
        assert "Installed" in canonical


# ===========================================================================
# _filter_rs3_api_records
# ===========================================================================

class TestFilterRs3ApiRecords:
    def _records(self):
        return [
            {"hosting_zone": "Public Cloud", "installed_status_usu": "Installed"},
            {"hosting_zone": "Private Cloud", "installed_status_usu": "Retired"},
            {"hosting_zone": "none", "installed_status_usu": "Installed"},
        ]

    def test_no_filters_returns_all(self):
        result = _filter_rs3_api_records(self._records())
        assert len(result) == 3

    def test_hosting_zone_filter(self):
        result = _filter_rs3_api_records(self._records(), hosting_zones=["Public Cloud"])
        assert len(result) == 1
        assert result[0]["hosting_zone"] == "Public Cloud"

    def test_installed_status_filter(self):
        result = _filter_rs3_api_records(self._records(), installed_statuses=["Installed"])
        assert len(result) == 2

    def test_combined_filters(self):
        result = _filter_rs3_api_records(
            self._records(),
            hosting_zones=["Public Cloud"],
            installed_statuses=["Installed"],
        )
        assert len(result) == 1

    def test_empty_records_returns_empty(self):
        result = _filter_rs3_api_records([], hosting_zones=["Public Cloud"])
        assert result == []

    def test_none_records_returns_empty(self):
        result = _filter_rs3_api_records(None)
        assert result == []


# ===========================================================================
# _coerce_float
# ===========================================================================

class TestCoerceFloat:
    def test_integer_coerced(self):
        assert _coerce_float(5) == 5.0

    def test_string_number_coerced(self):
        assert _coerce_float("3.14") == 3.14

    def test_none_returns_zero(self):
        assert _coerce_float(None) == 0.0

    def test_invalid_string_returns_zero(self):
        assert _coerce_float("N/A") == 0.0

    def test_zero_returns_zero(self):
        assert _coerce_float(0) == 0.0


# ===========================================================================
# _get_rs3_api_sort_field
# ===========================================================================

class TestGetRs3ApiSortField:
    def test_ram_returns_ram_reduction_key(self):
        assert _get_rs3_api_sort_field("RAM") == "Potential_RAM_Reduction_GiB"

    def test_cpu_returns_vcpu_reduction_key(self):
        assert _get_rs3_api_sort_field("CPU") == "Potential_vCPU_Reduction"

    def test_none_returns_vcpu_reduction_key(self):
        assert _get_rs3_api_sort_field(None) == "Potential_vCPU_Reduction"

    def test_case_insensitive_ram(self):
        assert _get_rs3_api_sort_field("ram") == "Potential_RAM_Reduction_GiB"


# ===========================================================================
# _get_rs3_api_sort_field_map
# ===========================================================================

class TestGetRs3ApiSortFieldMap:
    def test_ram_returns_ram_map(self):
        from optimizer.views import RS3_API_RAM_SORT_FIELD_MAP
        assert _get_rs3_api_sort_field_map("RAM") is RS3_API_RAM_SORT_FIELD_MAP

    def test_cpu_returns_cpu_map(self):
        from optimizer.views import RS3_API_CPU_SORT_FIELD_MAP
        assert _get_rs3_api_sort_field_map("CPU") is RS3_API_CPU_SORT_FIELD_MAP

    def test_none_returns_cpu_map(self):
        from optimizer.views import RS3_API_CPU_SORT_FIELD_MAP
        assert _get_rs3_api_sort_field_map(None) is RS3_API_CPU_SORT_FIELD_MAP


# ===========================================================================
# _get_rs3_api_sort_value
# ===========================================================================

class TestGetRs3ApiSortValue:
    def test_numeric_sort_field_returns_numeric_tuple(self):
        record = {"Avg_CPU_12m": 45.5}
        result = _get_rs3_api_sort_value(record, "Avg_CPU_12m", "avg_cpu_12m")
        assert result == (0, 45.5)

    def test_string_sort_field_returns_string_tuple(self):
        record = {"server_name": "Server01"}
        result = _get_rs3_api_sort_value(record, "server_name", "server_name")
        assert result == (1, "server01")

    def test_missing_numeric_field_returns_zero(self):
        record = {}
        result = _get_rs3_api_sort_value(record, "Avg_CPU_12m", "avg_cpu_12m")
        assert result == (0, 0.0)

    def test_missing_string_field_returns_empty_string(self):
        record = {}
        result = _get_rs3_api_sort_value(record, "server_name", "server_name")
        assert result == (1, "")

    def test_cost_savings_is_numeric(self):
        record = {"Cost_Savings_EUR": 1000.0}
        result = _get_rs3_api_sort_value(record, "Cost_Savings_EUR", "cost_savings_eur")
        assert result[0] == 0
        assert result[1] == 1000.0


# ===========================================================================
# _make_json_serializable
# ===========================================================================

class TestMakeJsonSerializable:
    def test_plain_dict_unchanged(self):
        obj = {"a": 1, "b": "x"}
        assert _make_json_serializable(obj) == {"a": 1, "b": "x"}

    def test_list_unchanged(self):
        assert _make_json_serializable([1, 2, 3]) == [1, 2, 3]

    def test_tuple_converted_to_list(self):
        assert _make_json_serializable((1, 2)) == [1, 2]

    def test_pd_na_becomes_none(self):
        assert _make_json_serializable(pd.NA) is None

    def test_nan_becomes_none(self):
        import math
        result = _make_json_serializable(float("nan"))
        assert result is None

    def test_nested_dict_recursed(self):
        obj = {"x": {"y": pd.NA}}
        result = _make_json_serializable(obj)
        assert result == {"x": {"y": None}}

    def test_pd_timestamp_to_isoformat(self):
        ts = pd.Timestamp("2024-01-15")
        result = _make_json_serializable(ts)
        assert "2024-01-15" in result

    def test_native_types_passed_through(self):
        assert _make_json_serializable(42) == 42
        assert _make_json_serializable(3.14) == 3.14
        assert _make_json_serializable("hello") == "hello"
        assert _make_json_serializable(True) is True
        assert _make_json_serializable(None) is None

    def test_unknown_type_stringified(self):
        class Custom:
            def __str__(self):
                return "custom_str"
        result = _make_json_serializable(Custom())
        assert result == "custom_str"


# ===========================================================================
# _sort_rs3_api_records
# ===========================================================================

class TestSortRs3ApiRecords:
    def _records(self):
        return [
            {"server_name": "srv-b", "Potential_vCPU_Reduction": 2.0, "Env_Type": "PROD"},
            {"server_name": "srv-a", "Potential_vCPU_Reduction": 8.0, "Env_Type": "PROD"},
            {"server_name": "srv-c", "Potential_vCPU_Reduction": 4.0, "Env_Type": "NON-PROD"},
        ]

    def test_default_sort_descending_by_potential_reduction(self):
        result = _sort_rs3_api_records(self._records(), "CPU")
        assert result[0]["Potential_vCPU_Reduction"] == 8.0

    def test_ascending_sort_order(self):
        result = _sort_rs3_api_records(self._records(), "CPU", sort_order="asc")
        assert result[0]["Potential_vCPU_Reduction"] == 2.0

    def test_sort_by_server_name(self):
        result = _sort_rs3_api_records(self._records(), "CPU", sort_field="server_name", sort_order="asc")
        assert result[0]["server_name"] == "srv-a"

    def test_none_records_returns_empty(self):
        result = _sort_rs3_api_records(None, "CPU")
        assert result == []

    def test_ram_sort_uses_ram_reduction_key(self):
        records = [
            {"server_name": "a", "Potential_RAM_Reduction_GiB": 10.0},
            {"server_name": "b", "Potential_RAM_Reduction_GiB": 5.0},
        ]
        result = _sort_rs3_api_records(records, "RAM", sort_field="potential_ram_reduction_gib")
        assert result[0]["Potential_RAM_Reduction_GiB"] == 10.0


# ===========================================================================
# _build_rs3_api_summary
# ===========================================================================

class TestBuildRs3ApiSummary:
    def _records(self):
        return [
            {"Env_Type": "PROD", "Potential_vCPU_Reduction": 4.0, "Cost_Savings_EUR": 200.0},
            {"Env_Type": "NON-PROD", "Potential_vCPU_Reduction": 2.0, "Cost_Savings_EUR": 100.0},
            {"Env_Type": "PROD", "Potential_vCPU_Reduction": 6.0, "Cost_Savings_EUR": 300.0},
        ]

    def test_count_all_records(self):
        result = _build_rs3_api_summary(self._records(), "CPU")
        assert result["count"] == 3

    def test_prod_count(self):
        result = _build_rs3_api_summary(self._records(), "CPU")
        assert result["prod_count"] == 2

    def test_nonprod_count(self):
        result = _build_rs3_api_summary(self._records(), "CPU")
        assert result["nonprod_count"] == 1

    def test_reduction_total(self):
        result = _build_rs3_api_summary(self._records(), "CPU")
        assert result["reduction_total"] == 12.0

    def test_savings_total(self):
        result = _build_rs3_api_summary(self._records(), "CPU")
        assert result["savings_eur"] == 600.0

    def test_empty_records(self):
        result = _build_rs3_api_summary([], "CPU")
        assert result["count"] == 0
        assert result["reduction_total"] == 0.0
        assert result["savings_eur"] == 0.0

    def test_ram_uses_ram_reduction_key(self):
        records = [{"Env_Type": "PROD", "Potential_RAM_Reduction_GiB": 8.0, "Cost_Savings_EUR": 50.0}]
        result = _build_rs3_api_summary(records, "RAM")
        assert result["reduction_total"] == 8.0

    def test_none_records_returns_zeros(self):
        result = _build_rs3_api_summary(None, "CPU")
        assert result["count"] == 0


# ===========================================================================
# _get_rs3_api_columns
# ===========================================================================

class TestGetRs3ApiColumns:
    def test_ram_returns_ram_columns(self):
        result = _get_rs3_api_columns("RAM")
        assert result is RS3_API_RAM_COLUMNS

    def test_cpu_returns_cpu_columns(self):
        result = _get_rs3_api_columns("CPU")
        assert result is RS3_API_CPU_COLUMNS

    def test_none_returns_cpu_columns(self):
        result = _get_rs3_api_columns(None)
        assert result is RS3_API_CPU_COLUMNS

    def test_case_insensitive(self):
        assert _get_rs3_api_columns("ram") is RS3_API_RAM_COLUMNS


# ===========================================================================
# _serialize_rs3_api_record
# ===========================================================================

class TestSerializeRs3ApiRecord:
    def _cpu_record(self):
        return {
            "server_name": "srv-01",
            "product_family": "MySQL",
            "product_group": "DB",
            "product_description": "Desc",
            "product_name": "MySQL Standard",
            "Environment": "Production",
            "Env_Type": "PROD",
            "hosting_zone": "Public Cloud",
            "installed_status_usu": "Installed",
            "is_virtual": True,
            "Optimization_Type": "Crit_CPU",
            "Recommendation_Type": None,
            "Avg_CPU_12m": 45.5,
            "Peak_CPU_12m": 75.0,
            "Current_vCPU": 8,
            "Recommended_vCPU": 4,
            "Potential_vCPU_Reduction": 4,
            "CPU_Recommendation": "Downsize",
            "Cost_Savings_EUR": 500.0,
        }

    def test_cpu_serialization_contains_key_fields(self):
        result = _serialize_rs3_api_record(self._cpu_record(), "CPU")
        assert result["server_name"] == "srv-01"
        assert result["avg_cpu_12m"] == 45.5
        assert result["env_type"] == "PROD"
        assert result["current_vcpu"] == 8

    def test_ram_serialization_contains_ram_fields(self):
        record = {
            "server_name": "srv-ram",
            "Env_Type": "NON-PROD",
            "hosting_zone": None,
            "installed_status_usu": "Installed",
            "Avg_FreeMem_12m": 20.0,
            "Min_FreeMem_12m": 5.0,
            "Current_RAM_GiB": 32,
            "Recommended_RAM_GiB": 16,
            "Potential_RAM_Reduction_GiB": 16,
            "RAM_Recommendation": "Downsize",
            "Cost_Savings_EUR": 100.0,
        }
        result = _serialize_rs3_api_record(record, "RAM")
        assert result["avg_free_mem_12m"] == 20.0
        assert result["current_ram_gib"] == 32

    def test_hosting_zone_normalized(self):
        record = dict(self._cpu_record(), hosting_zone=None)
        result = _serialize_rs3_api_record(record, "CPU")
        assert result["hosting_zone"] == "none"

    def test_na_values_converted_to_none(self):
        record = dict(self._cpu_record(), Avg_CPU_12m=pd.NA)
        result = _serialize_rs3_api_record(record, "CPU")
        assert result["avg_cpu_12m"] is None


# ===========================================================================
# _format_rs3_api_screen_label
# ===========================================================================

class TestFormatRs3ApiScreenLabel:
    def test_prod_cpu_rightsizing(self):
        assert _format_rs3_api_screen_label("PROD_CPU_Rightsizing") == "PROD CPU Right-Sizing"

    def test_nonprod_cpu_rightsizing(self):
        assert _format_rs3_api_screen_label("NONPROD_CPU_Rightsizing") == "Nonprod CPU Right-Sizing"

    def test_prod_ram_rightsizing(self):
        assert _format_rs3_api_screen_label("PROD_RAM_Rightsizing") == "PROD RAM Right-Sizing"

    def test_nonprod_ram_rightsizing(self):
        assert _format_rs3_api_screen_label("NONPROD_RAM_Rightsizing") == "Nonprod RAM Right-Sizing"

    def test_legacy_optimization_alias(self):
        assert _format_rs3_api_screen_label("PROD_CPU_Optimization") == "PROD CPU Right-Sizing"

    def test_none_returns_empty_or_string(self):
        result = _format_rs3_api_screen_label(None)
        assert isinstance(result, str)

    def test_unknown_value_falls_back_to_sheet_label(self):
        result = _format_rs3_api_screen_label("CUSTOM_FILTER")
        assert isinstance(result, str)
        assert len(result) > 0


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

    def test_multiple_records(self):
        records = [{"x": 10}, {"x": 20}]
        result = _build_table_rows(records, ["x"])
        assert result == [[10], [20]]

    def test_empty_records_returns_empty(self):
        assert _build_table_rows([], ["a"]) == []

    def test_empty_columns_returns_empty_rows(self):
        records = [{"a": 1}]
        result = _build_table_rows(records, [])
        assert result == [[]]


# ===========================================================================
# _sanitize_filename
# ===========================================================================

class TestSanitizeFilename:
    def test_normal_filename_unchanged(self):
        assert _sanitize_filename("report.xlsx") == "report.xlsx"

    def test_none_returns_download(self):
        assert _sanitize_filename(None) == "download"

    def test_empty_returns_download(self):
        assert _sanitize_filename("") == "download"

    def test_path_separators_stripped(self):
        result = _sanitize_filename("path/to/file.xlsx")
        assert "/" not in result
        assert result == "file.xlsx"

    def test_backslash_stripped(self):
        result = _sanitize_filename(r"dir\file.xlsx")
        assert "\\" not in result

    def test_control_chars_removed(self):
        result = _sanitize_filename("file\x00name.xlsx")
        assert "\x00" not in result

    def test_long_name_truncated(self):
        long_name = "a" * 300 + ".xlsx"
        result = _sanitize_filename(long_name)
        assert len(result) <= 200

    def test_non_string_returns_download(self):
        assert _sanitize_filename(12345) == "download"


# ===========================================================================
# _build_rs3_download_dataframe
# ===========================================================================

class TestBuildRs3DownloadDataframe:
    def _rightsizing(self):
        return {
            "cpu_optimizations": [
                {
                    "server_name": "srv-01",
                    "product_family": "MySQL",
                    "product_name": "MySQL Standard",
                    "product_description": "Desc",
                    "Env_Type": "PROD",
                    "Avg_CPU_12m": 45.0,
                    "Peak_CPU_12m": 75.0,
                    "Current_vCPU": 8,
                    "Potential_vCPU_Reduction": 4,
                },
            ],
            "ram_candidates": [
                {
                    "server_name": "srv-ram",
                    "product_family": "Oracle",
                    "product_name": "Oracle DB",
                    "product_description": "DB",
                    "Env_Type": "PROD",
                    "Avg_FreeMem_12m": 20.0,
                    "Min_FreeMem_12m": 5.0,
                    "Current_RAM_GiB": 32,
                    "Potential_RAM_Reduction_GiB": 16,
                },
            ],
        }

    def test_cpu_filter_uses_cpu_optimizations(self):
        df = _build_rs3_download_dataframe(self._rightsizing(), "PROD_CPU_Rightsizing")
        assert "server_name" in df.columns
        assert len(df) == 1

    def test_ram_filter_uses_ram_candidates(self):
        df = _build_rs3_download_dataframe(self._rightsizing(), "PROD_RAM_Rightsizing")
        assert len(df) == 1
        assert "Avg_FreeMem_12m" in df.columns

    def test_empty_rightsizing_returns_empty_df(self):
        df = _build_rs3_download_dataframe({}, "PROD_CPU_Rightsizing")
        assert len(df) == 0

    def test_filter_applied_to_records(self):
        rs = {
            "cpu_optimizations": [
                {"server_name": "p1", "Env_Type": "PROD", "product_family": "", "product_name": "", "product_description": "", "Avg_CPU_12m": 1, "Peak_CPU_12m": 1, "Current_vCPU": 4, "Potential_vCPU_Reduction": 2},
                {"server_name": "n1", "Env_Type": "NON-PROD", "product_family": "", "product_name": "", "product_description": "", "Avg_CPU_12m": 1, "Peak_CPU_12m": 1, "Current_vCPU": 4, "Potential_vCPU_Reduction": 2},
            ]
        }
        df = _build_rs3_download_dataframe(rs, "PROD_CPU_Rightsizing")
        assert len(df) == 1
        assert df.iloc[0]["server_name"] == "p1"


# ===========================================================================
# _get_rs3_api_sort_params (uses request mock)
# ===========================================================================

class _MockGet:
    def __init__(self, params):
        self._params = params

    def get(self, key, default=None):
        return self._params.get(key, default)


class _MockRequest:
    def __init__(self, params):
        self.GET = _MockGet(params)


class TestGetRs3ApiSortParams:
    def test_default_sort_order_desc(self):
        req = _MockRequest({})
        field, order = _get_rs3_api_sort_params(req, "CPU")
        assert order == "desc"

    def test_asc_sort_order_accepted(self):
        req = _MockRequest({"sort_order": "asc"})
        _, order = _get_rs3_api_sort_params(req, "CPU")
        assert order == "asc"

    def test_invalid_sort_order_defaults_to_desc(self):
        req = _MockRequest({"sort_order": "INVALID"})
        _, order = _get_rs3_api_sort_params(req, "CPU")
        assert order == "desc"

    def test_known_sort_field_returned(self):
        req = _MockRequest({"sort_field": "server_name"})
        field, _ = _get_rs3_api_sort_params(req, "CPU")
        assert field == "server_name"

    def test_unknown_sort_field_falls_back_to_default(self):
        req = _MockRequest({"sort_field": "nonexistent_field"})
        field, _ = _get_rs3_api_sort_params(req, "CPU")
        assert field == "potential_vcpu_reduction"

    def test_ram_default_sort_field(self):
        req = _MockRequest({})
        field, _ = _get_rs3_api_sort_params(req, "RAM")
        assert field == "potential_ram_reduction_gib"


# ===========================================================================
# _parse_rs3_multi_value_query_param (uses request mock)
# ===========================================================================

class TestParseRs3MultiValueQueryParam:
    def _req(self, values):
        class MockGET:
            def __init__(self, vals):
                self._vals = vals
            def getlist(self, key):
                return self._vals

        class MockReq:
            def __init__(self, vals):
                self.GET = MockGET(vals)

        return MockReq(values)

    def test_single_value_returned(self):
        req = self._req(["Public Cloud"])
        result = _parse_rs3_multi_value_query_param(req, "hosting_zone")
        assert result == ["Public Cloud"]

    def test_comma_separated_split(self):
        req = self._req(["Public Cloud,Private Cloud"])
        result = _parse_rs3_multi_value_query_param(req, "hosting_zone")
        assert "Public Cloud" in result
        assert "Private Cloud" in result

    def test_multiple_values_extended(self):
        req = self._req(["A", "B", "C"])
        result = _parse_rs3_multi_value_query_param(req, "zones")
        assert result == ["A", "B", "C"]

    def test_empty_values_skipped(self):
        req = self._req(["A,,B"])
        result = _parse_rs3_multi_value_query_param(req, "zones")
        assert "" not in result
        assert "A" in result
        assert "B" in result

    def test_none_values_skipped(self):
        req = self._req([None])
        result = _parse_rs3_multi_value_query_param(req, "zones")
        assert result == []

    def test_empty_list_returns_empty(self):
        req = self._req([])
        result = _parse_rs3_multi_value_query_param(req, "zones")
        assert result == []


# ===========================================================================
# _safe_content_disposition
# ===========================================================================

class TestSafeContentDisposition:
    def test_simple_filename(self):
        cd = _safe_content_disposition("report.xlsx")
        assert cd == 'attachment; filename="report.xlsx"'

    def test_empty_string_uses_download(self):
        cd = _safe_content_disposition("")
        assert cd == 'attachment; filename="download"'

    def test_none_uses_download(self):
        cd = _safe_content_disposition(None)
        assert cd == 'attachment; filename="download"'

    def test_strips_path_separators(self):
        cd = _safe_content_disposition("../../etc/passwd")
        assert "/" not in cd.split('"')[1]
        assert "\\" not in cd.split('"')[1]

    def test_attachment_prefix(self):
        cd = _safe_content_disposition("file.pdf")
        assert cd.startswith("attachment; filename=")


# ===========================================================================
# _get_rs3_api_page_size
# ===========================================================================

class TestGetRs3ApiPageSize:
    def _req(self, page_size=None):
        class FakeGET:
            def __init__(self, val):
                self._val = val
            def get(self, key, default=None):
                return self._val if self._val is not None else default

        class FakeRequest:
            def __init__(self, val):
                self.GET = FakeGET(val)

        return FakeRequest(page_size)

    def test_default_page_size_returned_when_not_set(self):
        req = self._req(None)
        result = _get_rs3_api_page_size(req)
        assert result == RS3_API_DEFAULT_PAGE_SIZE

    def test_valid_page_size_returned(self):
        req = self._req("50")
        result = _get_rs3_api_page_size(req)
        assert result == 50

    def test_page_size_clamped_to_max(self):
        req = self._req(str(RS3_API_MAX_PAGE_SIZE + 9999))
        result = _get_rs3_api_page_size(req)
        assert result == RS3_API_MAX_PAGE_SIZE

    def test_page_size_minimum_is_one(self):
        req = self._req("0")
        result = _get_rs3_api_page_size(req)
        assert result == 1

    def test_invalid_string_returns_default(self):
        req = self._req("not_a_number")
        result = _get_rs3_api_page_size(req)
        assert result == RS3_API_DEFAULT_PAGE_SIZE
