"""
Unit tests for optimizer.rules.rightsizing.
Pure pandas — no @pytest.mark.django_db required.
"""
import numpy as np
import pandas as pd
import pytest

from optimizer.rules.rightsizing import (
    NON_PROD_ENVS,
    _build_raw_detail_type,
    _chron_sort,
    _clean_numeric,
    _is_monthly_col,
    _round_ram,
    compute_utilisation_metrics,
    find_cpu_rightsizing_candidates,
    find_cpu_rightsizing_optimizations,
    find_criticality_cpu_downsize_optimizations,
    find_criticality_cpu_optimizations,
    find_criticality_cpu_upsize_optimizations,
    find_criticality_ram_downsize_optimizations,
    find_criticality_ram_optimizations,
    find_criticality_ram_upsize_optimizations,
    find_lifecycle_risk_flags,
    find_physical_systems_flags,
    find_ram_rightsizing_candidates,
    find_ram_rightsizing_optimizations,
)

MONTH_COLS = ["Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec", "Jan", "Feb"]


def _avg_cpu_col(m):
    return f"Average CPU Utilisation (%) {m}"

def _max_cpu_col(m):
    return f"Maximum CPU Utilisation (%) {m}"

def _avg_mem_col(m):
    return f"Average free Memory (%) {m}"

def _min_mem_col(m):
    return f"Minimum free Memory (%) {m}"

def _ram_col(m):
    return f"Physical RAM (GiB) {m}"

def _lcpu_col(m):
    return f"Logical CPU {m}"


def _build_row(environment="Production", avg_cpu=5.0, max_cpu=50.0, avg_mem=40.0, min_mem=25.0, ram=32.0, vcpu=8):
    row = {"Environment": environment}
    for m in MONTH_COLS:
        row[_avg_cpu_col(m)] = avg_cpu
        row[_max_cpu_col(m)] = max_cpu
        row[_avg_mem_col(m)] = avg_mem
        row[_min_mem_col(m)] = min_mem
        row[_ram_col(m)] = ram
        row[_lcpu_col(m)] = vcpu
    return row


def _make_df(**kwargs):
    return pd.DataFrame([_build_row(**kwargs)])


def _compute(df):
    return compute_utilisation_metrics(df)


# ===========================================================================
# _is_monthly_col
# ===========================================================================

class TestIsMonthlyCol:
    def test_recognises_mar(self):
        assert _is_monthly_col("Average CPU Utilisation (%) Mar") is True

    def test_recognises_feb(self):
        assert _is_monthly_col("Physical RAM (GiB) Feb") is True

    def test_non_monthly_col_returns_false(self):
        assert _is_monthly_col("Server Name") is False

    def test_jan_in_substring(self):
        assert _is_monthly_col("January CPU") is True

    def test_empty_string_returns_false(self):
        assert _is_monthly_col("") is False


# ===========================================================================
# _chron_sort
# ===========================================================================

class TestChronSort:
    def test_sorts_into_fiscal_order(self):
        cols = [_avg_cpu_col("Feb"), _avg_cpu_col("Mar"), _avg_cpu_col("Jan"), _avg_cpu_col("Oct")]
        sorted_cols = _chron_sort(cols)
        months = [c.split()[-1] for c in sorted_cols]
        assert months == ["Mar", "Oct", "Jan", "Feb"]

    def test_stable_with_single_element(self):
        cols = [_avg_cpu_col("June")]
        assert _chron_sort(cols) == cols

    def test_non_month_col_sorted_last(self):
        cols = [_avg_cpu_col("Mar"), "Other Column"]
        result = _chron_sort(cols)
        assert result[-1] == "Other Column"


# ===========================================================================
# _clean_numeric
# ===========================================================================

class TestCleanNumeric:
    def test_strips_percent(self):
        s = pd.Series(["45%", "10.5%"])
        result = _clean_numeric(s)
        assert result.tolist() == pytest.approx([45.0, 10.5])

    def test_handles_na_strings(self):
        s = pd.Series(["NA", "N/A", "nan", "None", "-", ""])
        assert _clean_numeric(s).isna().all()

    def test_handles_comma_thousands(self):
        s = pd.Series(["1,024"])
        assert _clean_numeric(s)[0] == pytest.approx(1024.0)

    def test_handles_plain_float(self):
        s = pd.Series(["3.14"])
        assert _clean_numeric(s)[0] == pytest.approx(3.14)

    def test_non_numeric_becomes_nan(self):
        s = pd.Series(["abc"])
        assert pd.isna(_clean_numeric(s)[0])


# ===========================================================================
# _round_ram
# ===========================================================================

class TestRoundRam:
    def test_exact_practical_size(self):
        assert _round_ram(24.0, 8) == 24.0

    def test_never_below_min_gib(self):
        assert _round_ram(2.0, 8) == 8.0

    def test_between_sizes_rounds_down(self):
        assert _round_ram(22.0, 8) == 20.0

    def test_64_gib(self):
        assert _round_ram(64.0, 8) == 64.0

    def test_large_value(self):
        assert _round_ram(2048.0, 8) == 2048.0

    def test_min_gib_4_for_nonprod(self):
        assert _round_ram(3.0, 4) == 4.0

    def test_value_10_min_4(self):
        assert _round_ram(10.0, 4) == 10.0


# ===========================================================================
# _build_raw_detail_type
# ===========================================================================

class TestBuildRawDetailType:
    def test_prod_cpu_optimization(self):
        assert _build_raw_detail_type("PROD", "CPU", "Optimization") == "PROD_CPU_Optimization"

    def test_nonprod_ram_recommendation(self):
        result = _build_raw_detail_type("NON-PROD", "RAM", "Recommendation")
        assert result == "NONPROD_RAM_Recommendation"

    def test_strips_spaces_and_dashes(self):
        result = _build_raw_detail_type("non prod", "CPU", "Optimization")
        assert result == "NONPROD_CPU_Optimization"

    def test_none_env(self):
        result = _build_raw_detail_type(None, "CPU", "Optimization")
        assert result == "_CPU_Optimization"


# ===========================================================================
# compute_utilisation_metrics
# ===========================================================================

class TestComputeUtilisationMetrics:
    def test_avg_cpu_12m_computed(self):
        df = _compute(_make_df(avg_cpu=10.0))
        assert df["Avg_CPU_12m"].iloc[0] == pytest.approx(10.0)

    def test_peak_cpu_12m_is_max_of_monthly_max(self):
        row = _build_row(max_cpu=50.0)
        row[_max_cpu_col("Dec")] = 90.0
        df = _compute(pd.DataFrame([row]))
        assert df["Peak_CPU_12m"].iloc[0] == pytest.approx(90.0)

    def test_avg_freemem_12m_computed(self):
        df = _compute(_make_df(avg_mem=55.0))
        assert df["Avg_FreeMem_12m"].iloc[0] == pytest.approx(55.0)

    def test_min_freemem_12m_is_min_of_monthly_min(self):
        row = _build_row(min_mem=25.0)
        row[_min_mem_col("Jan")] = 5.0
        df = _compute(pd.DataFrame([row]))
        assert df["Min_FreeMem_12m"].iloc[0] == pytest.approx(5.0)

    def test_current_vcpu_last_non_null(self):
        df = _compute(_make_df(vcpu=16))
        assert df["Current_vCPU"].iloc[0] == pytest.approx(16.0)

    def test_current_ram_gib_last_non_null(self):
        df = _compute(_make_df(ram=64.0))
        assert df["Current_RAM_GiB"].iloc[0] == pytest.approx(64.0)

    def test_percent_strings_parsed_correctly(self):
        row = _build_row()
        row[_avg_cpu_col("Mar")] = "12%"
        df = _compute(pd.DataFrame([row]))
        assert not pd.isna(df["Avg_CPU_12m"].iloc[0])

    def test_environment_stripped(self):
        row = _build_row(environment="  Production  ")
        df = _compute(pd.DataFrame([row]))
        assert df["Environment"].iloc[0] == "Production"


# ===========================================================================
# UC 3.1 - CPU Right-Sizing
# ===========================================================================

class TestCpuRightsizing:
    def _prod(self, avg_cpu=5.0, max_cpu=50.0, vcpu=8):
        return _compute(_make_df(environment="Production", avg_cpu=avg_cpu, max_cpu=max_cpu, vcpu=vcpu))

    def _nonprod(self, avg_cpu=10.0, max_cpu=50.0, vcpu=8):
        return _compute(_make_df(environment="Development", avg_cpu=avg_cpu, max_cpu=max_cpu, vcpu=vcpu))

    def test_prod_eligible_included(self):
        assert len(find_cpu_rightsizing_optimizations(self._prod(avg_cpu=5.0, max_cpu=50.0, vcpu=8))) == 1

    def test_prod_high_avg_cpu_excluded(self):
        assert len(find_cpu_rightsizing_optimizations(self._prod(avg_cpu=20.0))) == 0

    def test_prod_high_peak_excluded(self):
        assert len(find_cpu_rightsizing_optimizations(self._prod(max_cpu=75.0))) == 0

    def test_prod_low_vcpu_excluded(self):
        assert len(find_cpu_rightsizing_optimizations(self._prod(vcpu=3))) == 0

    def test_prod_vcpu_exactly_4_included(self):
        assert len(find_cpu_rightsizing_optimizations(self._prod(vcpu=4))) == 1

    def test_prod_avg_below_10_recommends_50_percent_reduction(self):
        result = find_cpu_rightsizing_optimizations(self._prod(avg_cpu=5.0, max_cpu=50.0, vcpu=8))
        assert "50%" in result["CPU_Recommendation"].iloc[0]
        assert result["Recommended_vCPU"].iloc[0] == max(4, round(8 * 0.50))

    def test_prod_avg_10_15_peak_lte_60_recommends_25_percent(self):
        result = find_cpu_rightsizing_optimizations(self._prod(avg_cpu=12.0, max_cpu=55.0, vcpu=8))
        assert "25%" in result["CPU_Recommendation"].iloc[0]

    def test_prod_avg_10_15_peak_60_70_no_specific_band(self):
        result = find_cpu_rightsizing_optimizations(self._prod(avg_cpu=12.0, max_cpu=65.0, vcpu=8))
        assert "No specific reduction band matched" in result["CPU_Recommendation"].iloc[0]

    def test_prod_recommendation_never_below_4_vcpu(self):
        result = find_cpu_rightsizing_optimizations(self._prod(avg_cpu=5.0, max_cpu=50.0, vcpu=4))
        assert result["Recommended_vCPU"].iloc[0] >= 4

    def test_nonprod_eligible_included(self):
        assert len(find_cpu_rightsizing_optimizations(self._nonprod(avg_cpu=10.0, max_cpu=50.0))) == 1

    def test_nonprod_avg_above_25_excluded(self):
        assert len(find_cpu_rightsizing_optimizations(self._nonprod(avg_cpu=30.0))) == 0

    def test_nonprod_peak_above_80_excluded(self):
        assert len(find_cpu_rightsizing_optimizations(self._nonprod(max_cpu=85.0))) == 0

    def test_nonprod_low_vcpu_excluded(self):
        assert len(find_cpu_rightsizing_optimizations(self._nonprod(vcpu=3))) == 0

    def test_nonprod_avg_below_15_peak_below_60_recommends_50_60_percent(self):
        result = find_cpu_rightsizing_optimizations(self._nonprod(avg_cpu=8.0, max_cpu=40.0, vcpu=8))
        assert "50-60%" in result["CPU_Recommendation"].iloc[0]

    def test_nonprod_avg_15_25_peak_lte_70_recommends_25_33_percent(self):
        result = find_cpu_rightsizing_optimizations(self._nonprod(avg_cpu=18.0, max_cpu=65.0, vcpu=8))
        assert "25-33%" in result["CPU_Recommendation"].iloc[0]

    def test_nonprod_recommendation_never_below_4_vcpu(self):
        result = find_cpu_rightsizing_optimizations(self._nonprod(avg_cpu=8.0, max_cpu=40.0, vcpu=4))
        assert result["Recommended_vCPU"].iloc[0] >= 4

    def test_prod_row_labelled_prod(self):
        result = find_cpu_rightsizing_optimizations(self._prod())
        assert result["Env_Type"].iloc[0] == "PROD"

    def test_nonprod_row_labelled_nonprod(self):
        result = find_cpu_rightsizing_optimizations(self._nonprod())
        assert result["Env_Type"].iloc[0] == "NON-PROD"

    def test_candidates_alias_same_as_optimizations(self):
        df = self._prod()
        assert len(find_cpu_rightsizing_candidates(df)) == len(find_cpu_rightsizing_optimizations(df))

    def test_empty_df_returns_empty(self):
        cols = ["Environment", "Avg_CPU_12m", "Peak_CPU_12m", "Current_vCPU"]
        assert find_cpu_rightsizing_optimizations(pd.DataFrame(columns=cols)).empty


# ===========================================================================
# UC 3.2 - RAM Right-Sizing
# ===========================================================================

class TestRamRightsizing:
    def _prod(self, avg_mem=40.0, min_mem=25.0, ram=32.0):
        return _compute(_make_df(environment="Production", avg_mem=avg_mem, min_mem=min_mem, ram=ram))

    def _nonprod(self, avg_mem=35.0, min_mem=20.0, ram=16.0):
        return _compute(_make_df(environment="Development", avg_mem=avg_mem, min_mem=min_mem, ram=ram))

    def test_prod_eligible_included(self):
        assert len(find_ram_rightsizing_optimizations(self._prod())) == 1

    def test_prod_low_avg_freemem_excluded(self):
        assert len(find_ram_rightsizing_optimizations(self._prod(avg_mem=20.0))) == 0

    def test_prod_low_min_freemem_excluded(self):
        assert len(find_ram_rightsizing_optimizations(self._prod(min_mem=10.0))) == 0

    def test_prod_low_ram_excluded(self):
        assert len(find_ram_rightsizing_optimizations(self._prod(ram=8.0))) == 0

    def test_prod_avg_35_50_recommends_25_percent(self):
        result = find_ram_rightsizing_optimizations(self._prod(avg_mem=40.0, min_mem=25.0, ram=32.0))
        assert "25%" in result["RAM_Recommendation"].iloc[0]

    def test_prod_avg_above_50_min_above_30_recommends_40_50_percent(self):
        result = find_ram_rightsizing_optimizations(self._prod(avg_mem=60.0, min_mem=35.0, ram=32.0))
        assert "40-50%" in result["RAM_Recommendation"].iloc[0]

    def test_prod_avg_above_50_min_below_30_excluded(self):
        assert len(find_ram_rightsizing_optimizations(self._prod(avg_mem=60.0, min_mem=25.0, ram=32.0))) == 0

    def test_nonprod_eligible_included(self):
        assert len(find_ram_rightsizing_optimizations(self._nonprod())) == 1

    def test_nonprod_low_avg_freemem_excluded(self):
        assert len(find_ram_rightsizing_optimizations(self._nonprod(avg_mem=10.0))) == 0

    def test_nonprod_low_ram_excluded(self):
        assert len(find_ram_rightsizing_optimizations(self._nonprod(ram=4.0))) == 0

    def test_nonprod_avg_30_50_recommends_33_percent(self):
        result = find_ram_rightsizing_optimizations(self._nonprod(avg_mem=35.0, min_mem=20.0, ram=16.0))
        assert "33%" in result["RAM_Recommendation"].iloc[0]

    def test_nonprod_avg_above_50_min_above_25_recommends_40_60_percent(self):
        result = find_ram_rightsizing_optimizations(self._nonprod(avg_mem=60.0, min_mem=30.0, ram=16.0))
        assert "40-60%" in result["RAM_Recommendation"].iloc[0]

    def test_nonprod_avg_above_50_min_below_25_excluded(self):
        assert len(find_ram_rightsizing_optimizations(self._nonprod(avg_mem=60.0, min_mem=20.0, ram=16.0))) == 0

    def test_prod_row_labelled_prod(self):
        result = find_ram_rightsizing_optimizations(self._prod())
        assert result["Env_Type"].iloc[0] == "PROD"

    def test_nonprod_row_labelled_nonprod(self):
        result = find_ram_rightsizing_optimizations(self._nonprod())
        assert result["Env_Type"].iloc[0] == "NON-PROD"

    def test_candidates_alias_same_as_optimizations(self):
        df = self._prod()
        assert len(find_ram_rightsizing_candidates(df)) == len(find_ram_rightsizing_optimizations(df))

    def test_empty_df_returns_empty(self):
        cols = ["Environment", "Avg_FreeMem_12m", "Min_FreeMem_12m", "Current_RAM_GiB"]
        assert find_ram_rightsizing_optimizations(pd.DataFrame(columns=cols)).empty


# ===========================================================================
# UC 3.3a - Criticality CPU Downsize
# ===========================================================================

class TestCriticalityCpuDownsize:
    def _make(self, criticality="Business Critical", avg_cpu=5.0, vcpu=8):
        row = _build_row(avg_cpu=avg_cpu, vcpu=vcpu)
        row["Criticality"] = criticality
        return _compute(pd.DataFrame([row]))

    def test_business_critical_low_cpu_included(self):
        assert len(find_criticality_cpu_downsize_optimizations(self._make("Business Critical", 5.0))) == 1

    def test_mission_critical_low_cpu_included(self):
        assert len(find_criticality_cpu_downsize_optimizations(self._make("Mission Critical", 5.0))) == 1

    def test_manufacturing_critical_low_cpu_included(self):
        assert len(find_criticality_cpu_downsize_optimizations(self._make("Manufacturing Critical", 5.0))) == 1

    def test_avg_cpu_above_10_excluded(self):
        assert len(find_criticality_cpu_downsize_optimizations(self._make("Business Critical", 15.0))) == 0

    def test_normal_criticality_excluded(self):
        assert len(find_criticality_cpu_downsize_optimizations(self._make("Low", 5.0))) == 0

    def test_recommendation_contains_cautious_downsizing(self):
        result = find_criticality_cpu_downsize_optimizations(self._make("Business Critical", 5.0, 8))
        assert "Cautious Downsizing" in result["CPU_Recommendation"].iloc[0]

    def test_manufacturing_critical_has_extra_conservatism(self):
        result = find_criticality_cpu_downsize_optimizations(self._make("Manufacturing Critical", 5.0, 8))
        assert "Manufacturing Critical" in result["CPU_Recommendation"].iloc[0]

    def test_recommended_vcpu_never_below_4(self):
        result = find_criticality_cpu_downsize_optimizations(self._make("Business Critical", 5.0, 4))
        assert result["Recommended_vCPU"].iloc[0] >= 4

    def test_no_criticality_column_returns_empty(self):
        assert find_criticality_cpu_downsize_optimizations(_compute(_make_df())).empty

    def test_optimization_type_label(self):
        result = find_criticality_cpu_downsize_optimizations(self._make("Business Critical", 5.0))
        assert result["Optimization_Type"].iloc[0] == "Crit_CPU_Downsize_Optimization"


# ===========================================================================
# UC 3.3b - Criticality CPU Upsize
# ===========================================================================

class TestCriticalityCpuUpsize:
    def _make(self, criticality="Business Critical", avg_cpu=85.0, vcpu=8):
        row = _build_row(avg_cpu=avg_cpu, vcpu=vcpu)
        row["Criticality"] = criticality
        return _compute(pd.DataFrame([row]))

    def test_business_critical_high_cpu_included(self):
        assert len(find_criticality_cpu_upsize_optimizations(self._make("Business Critical", 85.0))) == 1

    def test_mission_critical_high_cpu_included(self):
        assert len(find_criticality_cpu_upsize_optimizations(self._make("Mission Critical", 90.0))) == 1

    def test_manufacturing_critical_excluded(self):
        assert len(find_criticality_cpu_upsize_optimizations(self._make("Manufacturing Critical", 85.0))) == 0

    def test_avg_cpu_below_80_excluded(self):
        assert len(find_criticality_cpu_upsize_optimizations(self._make("Business Critical", 75.0))) == 0

    def test_recommendation_contains_upsize(self):
        result = find_criticality_cpu_upsize_optimizations(self._make("Business Critical", 85.0))
        assert "Upsize" in result["CPU_Recommendation"].iloc[0]

    def test_recommended_vcpu_is_25_percent_increase(self):
        result = find_criticality_cpu_upsize_optimizations(self._make("Business Critical", 85.0, 8))
        assert result["Recommended_vCPU"].iloc[0] == round(8 * 1.25)

    def test_no_criticality_column_returns_empty(self):
        assert find_criticality_cpu_upsize_optimizations(_compute(_make_df())).empty

    def test_optimization_type_label(self):
        result = find_criticality_cpu_upsize_optimizations(self._make("Business Critical", 85.0))
        assert result["Optimization_Type"].iloc[0] == "Crit_CPU_Upsize_Optimization"

    def test_lifecycle_flag_is_upsize_flag(self):
        result = find_criticality_cpu_upsize_optimizations(self._make("Business Critical", 85.0))
        assert result["Lifecycle_Flag"].iloc[0] == "Upsize Flag"


# ===========================================================================
# Combined UC 3.3
# ===========================================================================

class TestCriticalityCpuOptimizations:
    def test_combined_returns_both(self):
        row_down = _build_row(avg_cpu=5.0, vcpu=8)
        row_down["Criticality"] = "Business Critical"
        row_up = _build_row(avg_cpu=85.0, vcpu=8)
        row_up["Criticality"] = "Mission Critical"
        df = _compute(pd.DataFrame([row_down, row_up]))
        result = find_criticality_cpu_optimizations(df)
        opt_types = set(result["Optimization_Type"].tolist())
        assert "Crit_CPU_Downsize_Optimization" in opt_types
        assert "Crit_CPU_Upsize_Optimization" in opt_types

    def test_no_criticality_col_returns_empty(self):
        assert find_criticality_cpu_optimizations(_compute(_make_df())).empty


# ===========================================================================
# UC 3.4a - Criticality RAM Downsize
# ===========================================================================

class TestCriticalityRamDownsize:
    def _make(self, criticality="Business Critical", avg_mem=85.0, ram=32.0):
        row = _build_row(avg_mem=avg_mem, ram=ram)
        row["Criticality"] = criticality
        return _compute(pd.DataFrame([row]))

    def test_business_critical_high_freemem_included(self):
        assert len(find_criticality_ram_downsize_optimizations(self._make("Business Critical", 85.0))) == 1

    def test_mission_critical_included(self):
        assert len(find_criticality_ram_downsize_optimizations(self._make("Mission Critical", 85.0))) == 1

    def test_manufacturing_critical_included(self):
        assert len(find_criticality_ram_downsize_optimizations(self._make("Manufacturing Critical", 85.0))) == 1

    def test_avg_freemem_below_80_excluded(self):
        assert len(find_criticality_ram_downsize_optimizations(self._make("Business Critical", 70.0))) == 0

    def test_normal_criticality_excluded(self):
        assert len(find_criticality_ram_downsize_optimizations(self._make("Low", 85.0))) == 0

    def test_recommendation_contains_downsize_ram(self):
        result = find_criticality_ram_downsize_optimizations(self._make("Business Critical", 85.0))
        assert "Downsize RAM" in result["RAM_Recommendation"].iloc[0]

    def test_recommended_ram_never_below_8(self):
        result = find_criticality_ram_downsize_optimizations(self._make("Business Critical", 85.0, 10.0))
        assert result["Recommended_RAM_GiB"].iloc[0] >= 8.0

    def test_no_criticality_column_returns_empty(self):
        assert find_criticality_ram_downsize_optimizations(_compute(_make_df())).empty

    def test_optimization_type_label(self):
        result = find_criticality_ram_downsize_optimizations(self._make("Business Critical", 85.0))
        assert result["Optimization_Type"].iloc[0] == "Crit_RAM_Downsize_Optimization"


# ===========================================================================
# UC 3.4b - Criticality RAM Upsize
# ===========================================================================

class TestCriticalityRamUpsize:
    def _make(self, criticality="Business Critical", avg_mem=10.0, ram=32.0):
        row = _build_row(avg_mem=avg_mem, ram=ram)
        row["Criticality"] = criticality
        return _compute(pd.DataFrame([row]))

    def test_business_critical_low_freemem_included(self):
        assert len(find_criticality_ram_upsize_optimizations(self._make("Business Critical", 10.0))) == 1

    def test_mission_critical_included(self):
        assert len(find_criticality_ram_upsize_optimizations(self._make("Mission Critical", 10.0))) == 1

    def test_manufacturing_critical_excluded(self):
        assert len(find_criticality_ram_upsize_optimizations(self._make("Manufacturing Critical", 10.0))) == 0

    def test_avg_freemem_above_20_excluded(self):
        assert len(find_criticality_ram_upsize_optimizations(self._make("Business Critical", 25.0))) == 0

    def test_recommendation_contains_upsize_ram(self):
        result = find_criticality_ram_upsize_optimizations(self._make("Business Critical", 10.0))
        assert "Upsize RAM" in result["RAM_Recommendation"].iloc[0]

    def test_lifecycle_flag_is_upsize_flag(self):
        result = find_criticality_ram_upsize_optimizations(self._make("Business Critical", 10.0))
        assert result["Lifecycle_Flag"].iloc[0] == "Upsize Flag"

    def test_no_criticality_column_returns_empty(self):
        assert find_criticality_ram_upsize_optimizations(_compute(_make_df())).empty

    def test_optimization_type_label(self):
        result = find_criticality_ram_upsize_optimizations(self._make("Business Critical", 10.0))
        assert result["Optimization_Type"].iloc[0] == "Crit_RAM_Upsize_Optimization"


# ===========================================================================
# Combined UC 3.4
# ===========================================================================

class TestCriticalityRamOptimizations:
    def test_combined_returns_both(self):
        row_down = _build_row(avg_mem=85.0, ram=32.0)
        row_down["Criticality"] = "Business Critical"
        row_up = _build_row(avg_mem=10.0, ram=32.0)
        row_up["Criticality"] = "Mission Critical"
        df = _compute(pd.DataFrame([row_down, row_up]))
        result = find_criticality_ram_optimizations(df)
        opt_types = set(result["Optimization_Type"].tolist())
        assert "Crit_RAM_Downsize_Optimization" in opt_types
        assert "Crit_RAM_Upsize_Optimization" in opt_types

    def test_no_criticality_col_returns_empty(self):
        assert find_criticality_ram_optimizations(_compute(_make_df())).empty


# ===========================================================================
# UC 3.5 - Lifecycle Risk Flags
# ===========================================================================

class TestLifecycleRiskFlags:
    def _make(self, criticality="Business Critical", peak_cpu=97.0, min_mem=2.0):
        row = _build_row(max_cpu=peak_cpu, min_mem=min_mem)
        row["Criticality"] = criticality
        return _compute(pd.DataFrame([row]))

    def test_all_three_conditions_met_flagged(self):
        assert len(find_lifecycle_risk_flags(self._make("Business Critical", 97.0, 2.0))) == 1

    def test_mission_critical_flagged(self):
        assert len(find_lifecycle_risk_flags(self._make("Mission Critical", 97.0, 2.0))) == 1

    def test_manufacturing_critical_excluded(self):
        assert len(find_lifecycle_risk_flags(self._make("Manufacturing Critical", 97.0, 2.0))) == 0

    def test_low_peak_cpu_not_flagged(self):
        assert len(find_lifecycle_risk_flags(self._make("Business Critical", 80.0, 2.0))) == 0

    def test_high_min_freemem_not_flagged(self):
        assert len(find_lifecycle_risk_flags(self._make("Business Critical", 97.0, 10.0))) == 0

    def test_normal_criticality_not_flagged(self):
        assert len(find_lifecycle_risk_flags(self._make("Low", 97.0, 2.0))) == 0

    def test_human_review_required_is_yes(self):
        result = find_lifecycle_risk_flags(self._make())
        assert result["Human_Review_Required"].iloc[0] == "Yes"

    def test_risk_reasons_contain_all_three_factors(self):
        result = find_lifecycle_risk_flags(self._make())
        reason = result["Lifecycle_Risk_Reasons"].iloc[0]
        assert "Critical System" in reason
        assert "High Peak CPU" in reason
        assert "Low Minimum Memory" in reason

    def test_no_criticality_column_returns_empty(self):
        assert find_lifecycle_risk_flags(_compute(_make_df())).empty

    def test_output_columns_present(self):
        result = find_lifecycle_risk_flags(self._make())
        assert "Lifecycle_Risk_Reasons" in result.columns
        assert "Human_Review_Required" in result.columns


# ===========================================================================
# Physical Systems Flags
# ===========================================================================

class TestPhysicalSystemsFlags:
    def _make(self, is_virtual="false"):
        row = _build_row()
        row["Is Virtual?"] = is_virtual
        return pd.DataFrame([row])

    def test_false_flagged_as_physical(self):
        result = find_physical_systems_flags(self._make("false"))
        assert len(result) == 1
        assert result["IsVirtual_Status"].iloc[0] == "Physical"

    def test_false_uppercase_flagged(self):
        assert len(find_physical_systems_flags(self._make("FALSE"))) == 1

    def test_true_not_flagged(self):
        assert len(find_physical_systems_flags(self._make("true"))) == 0

    def test_blank_not_flagged(self):
        assert len(find_physical_systems_flags(self._make(""))) == 0

    def test_human_review_contains_physical_system(self):
        result = find_physical_systems_flags(self._make("false"))
        assert "Physical System" in result["Human_Review_Required"].iloc[0]

    def test_review_reason_column_present(self):
        result = find_physical_systems_flags(self._make("false"))
        assert "Review_Reason" in result.columns

    def test_no_is_virtual_column_returns_empty(self):
        assert find_physical_systems_flags(_make_df()).empty

    def test_db_normalized_column_name_supported(self):
        row = _build_row()
        row["is_virtual"] = "false"
        result = find_physical_systems_flags(pd.DataFrame([row]))
        assert len(result) == 1
