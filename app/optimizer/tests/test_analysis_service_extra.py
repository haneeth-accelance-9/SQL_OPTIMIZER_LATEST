"""
Unit tests for pure helper functions in optimizer.services.analysis_service.
No database or Django required — pure computation.
"""
import pytest
import pandas as pd

from optimizer.services.analysis_service import (
    _calculate_savings,
    _normalize_payg_zone_label,
    _build_payg_zone_breakdown,
    build_dashboard_context,
    PipelineTimer,
    PAYG_SAVINGS_MULTIPLIER,
    RETIRED_DEVICE_SAVINGS_MULTIPLIER,
)
from optimizer.services.analysis_logs import build_analysis_summary_metrics


# ===========================================================================
# _normalize_payg_zone_label
# ===========================================================================

class TestNormalizePaygZoneLabel:
    def test_public_cloud_normalized(self):
        assert _normalize_payg_zone_label("Public Cloud") == "Public Cloud"

    def test_public_cloud_case_insensitive(self):
        assert _normalize_payg_zone_label("PUBLIC CLOUD") == "Public Cloud"

    def test_avs_zone_normalized(self):
        assert _normalize_payg_zone_label("Private Cloud AVS") == "Private Cloud AVS"

    def test_avs_substring(self):
        assert _normalize_payg_zone_label("avs-zone") == "Private Cloud AVS"

    def test_private_cloud_non_avs_returns_none(self):
        assert _normalize_payg_zone_label("Private Cloud") is None

    def test_none_returns_none(self):
        assert _normalize_payg_zone_label(None) is None

    def test_empty_returns_none(self):
        assert _normalize_payg_zone_label("") is None

    def test_functional_site_returns_none(self):
        assert _normalize_payg_zone_label("Functional Site") is None

    def test_whitespace_stripped(self):
        assert _normalize_payg_zone_label("  Public Cloud  ") == "Public Cloud"


# ===========================================================================
# _build_payg_zone_breakdown
# ===========================================================================

class TestBuildPaygZoneBreakdown:
    def test_empty_inputs_returns_zeros(self):
        result = _build_payg_zone_breakdown(None, [])
        assert result["labels"] == ["Public Cloud", "Private Cloud AVS"]
        assert result["current"] == [0, 0]
        assert result["estimated"] == [0, 0]

    def test_current_counts_from_df(self):
        df = pd.DataFrame([
            {"u_hosting_zone": "Public Cloud"},
            {"u_hosting_zone": "Public Cloud"},
            {"u_hosting_zone": "Private Cloud AVS"},
        ])
        result = _build_payg_zone_breakdown(df, [])
        assert result["current"][0] == 2  # Public Cloud
        assert result["current"][1] == 1  # Private Cloud AVS

    def test_private_cloud_not_counted(self):
        df = pd.DataFrame([
            {"u_hosting_zone": "Private Cloud"},  # non-AVS
        ])
        result = _build_payg_zone_breakdown(df, [])
        assert result["current"] == [0, 0]

    def test_estimated_counts_from_payg_rows(self):
        rows = [
            {"u_hosting_zone": "Public Cloud"},
            {"u_hosting_zone": "Private Cloud AVS"},
        ]
        result = _build_payg_zone_breakdown(None, rows)
        assert result["estimated"][0] == 1
        assert result["estimated"][1] == 1

    def test_df_without_hosting_zone_column_skipped(self):
        df = pd.DataFrame([{"server_name": "srv-01"}])
        result = _build_payg_zone_breakdown(df, [])
        assert result["current"] == [0, 0]

    def test_non_list_payg_rows_ignored(self):
        result = _build_payg_zone_breakdown(None, None)
        assert result["estimated"] == [0, 0]

    def test_non_dict_rows_in_list_skipped(self):
        rows = ["not-a-dict", {"u_hosting_zone": "Public Cloud"}]
        result = _build_payg_zone_breakdown(None, rows)
        assert result["estimated"][0] == 1

    def test_returns_expected_structure(self):
        result = _build_payg_zone_breakdown(None, [])
        assert "labels" in result
        assert "current" in result
        assert "estimated" in result
        assert len(result["labels"]) == 2


# ===========================================================================
# _calculate_savings
# ===========================================================================

class TestCalculateSavings:
    def _rule(self, payg=5, retired=3):
        return {"azure_payg_count": payg, "retired_count": retired}

    def _metrics(self, demand=100, cost=10000.0):
        return {"total_demand_quantity": demand, "total_license_cost": cost}

    def test_zero_demand_returns_zero_savings(self):
        result = _calculate_savings(self._rule(), self._metrics(demand=0))
        assert result["rule_wise_savings"]["azure_payg"] == 0.0
        assert result["rule_wise_savings"]["retired_devices"] == 0.0
        assert result["total_savings"] == 0.0

    def test_zero_cost_returns_zero_savings(self):
        result = _calculate_savings(self._rule(), self._metrics(cost=0))
        assert result["total_savings"] == 0.0

    def test_payg_savings_formula(self):
        # payg_share = 5/100 = 0.05; savings = 10000 * 0.05 * 0.28 = 140.0
        result = _calculate_savings(self._rule(payg=5), self._metrics(demand=100, cost=10000.0))
        expected = round(10000.0 * (5 / 100) * PAYG_SAVINGS_MULTIPLIER, 2)
        assert result["rule_wise_savings"]["azure_payg"] == expected

    def test_retired_savings_formula(self):
        # retired_share = 3/100 = 0.03; savings = 10000 * 0.03 * 0.05 = 15.0
        result = _calculate_savings(self._rule(retired=3), self._metrics(demand=100, cost=10000.0))
        expected = round(10000.0 * (3 / 100) * RETIRED_DEVICE_SAVINGS_MULTIPLIER, 2)
        assert result["rule_wise_savings"]["retired_devices"] == expected

    def test_total_savings_is_sum(self):
        result = _calculate_savings(self._rule(), self._metrics())
        total = (
            result["rule_wise_savings"]["azure_payg"]
            + result["rule_wise_savings"]["retired_devices"]
            + result["rule_wise_savings"]["rightsizing"]
        )
        assert result["total_savings"] == round(total, 2)

    def test_rightsizing_savings_computed_from_meta(self):
        rs = {
            "total_vcpu_reduction": 10,
            "avg_cost_per_core_pair_eur": 200.0,
            "total_ram_reduction_gib": 0,
            "avg_cost_per_gib_eur": 0,
            "cpu_count": 5,
            "ram_count": 0,
        }
        result = _calculate_savings(self._rule(payg=0, retired=0), self._metrics(), rightsizing=rs)
        # (10 / 2) * 200 = 1000
        assert result["rule_wise_savings"]["rightsizing_cpu"] == 1000.0

    def test_rightsizing_ram_savings(self):
        rs = {
            "total_vcpu_reduction": 0,
            "avg_cost_per_core_pair_eur": 0,
            "total_ram_reduction_gib": 8.0,
            "avg_cost_per_gib_eur": 50.0,
            "cpu_count": 0,
            "ram_count": 4,
        }
        result = _calculate_savings(self._rule(payg=0, retired=0), self._metrics(), rightsizing=rs)
        assert result["rule_wise_savings"]["rightsizing_ram"] == 400.0

    def test_direct_savings_override_formula(self):
        rs = {
            "total_vcpu_reduction": 10,
            "avg_cost_per_core_pair_eur": 200.0,
            "total_ram_reduction_gib": 8.0,
            "avg_cost_per_gib_eur": 50.0,
            "cpu_count": 5,
            "ram_count": 4,
            "cpu_savings_eur": 9999.0,
            "ram_savings_eur": 8888.0,
        }
        result = _calculate_savings(self._rule(payg=0, retired=0), self._metrics(), rightsizing=rs)
        assert result["rule_wise_savings"]["rightsizing_cpu"] == 9999.0
        assert result["rule_wise_savings"]["rightsizing_ram"] == 8888.0

    def test_result_has_required_keys(self):
        result = _calculate_savings(self._rule(), self._metrics())
        for key in ("rule_wise_savings", "scenario_wise_savings", "rightsizing_meta", "total_savings"):
            assert key in result

    def test_scenario_wise_savings_keys(self):
        result = _calculate_savings(self._rule(), self._metrics())
        sws = result["scenario_wise_savings"]
        assert "cloud_licensing_optimization" in sws
        assert "inactive_asset_reclamation" in sws
        assert "workload_rightsizing" in sws

    def test_none_rule_results(self):
        result = _calculate_savings({}, {})
        assert result["total_savings"] == 0.0

    def test_rightsizing_meta_in_result(self):
        rs = {
            "total_vcpu_reduction": 4,
            "avg_cost_per_core_pair_eur": 100.0,
            "total_ram_reduction_gib": 2.0,
            "avg_cost_per_gib_eur": 20.0,
            "cpu_count": 2,
            "ram_count": 1,
        }
        result = _calculate_savings(self._rule(payg=0, retired=0), self._metrics(), rightsizing=rs)
        meta = result["rightsizing_meta"]
        assert meta["total_vcpu_reduction"] == 4
        assert meta["cpu_count"] == 2
        assert meta["ram_count"] == 1


# ===========================================================================
# build_dashboard_context
# ===========================================================================

class TestBuildDashboardContext:
    def _ctx(self, payg=5, retired=3, demand=100, cost=10000.0, devices=50):
        return {
            "rule_results": {"azure_payg_count": payg, "retired_count": retired},
            "license_metrics": {
                "total_demand_quantity": demand,
                "total_license_cost": cost,
                "price_distribution": [],
                "cost_reduction_tips": [],
            },
            "total_devices_analyzed": devices,
        }

    def test_required_keys_present(self):
        result = build_dashboard_context(self._ctx())
        for key in (
            "azure_payg_count", "retired_count", "total_demand_quantity",
            "total_license_cost", "total_savings", "azure_payg_savings",
            "retired_devices_savings", "rightsizing_savings",
            "potential_savings", "price_distribution_summary",
        ):
            assert key in result, f"Missing key: {key}"

    def test_counts_populated(self):
        result = build_dashboard_context(self._ctx(payg=5, retired=3))
        assert result["azure_payg_count"] == 5
        assert result["retired_count"] == 3

    def test_demand_and_cost_populated(self):
        result = build_dashboard_context(self._ctx(demand=150, cost=15000.0))
        assert result["total_demand_quantity"] == 150
        assert result["total_license_cost"] == 15000.0

    def test_price_distribution_summary_has_four_items(self):
        result = build_dashboard_context(self._ctx())
        assert len(result["price_distribution_summary"]) == 4

    def test_price_distribution_summary_with_data(self):
        ctx = self._ctx()
        ctx["license_metrics"]["price_distribution"] = [
            {"type": "Standard", "quantity": 10, "total_cost": 5000.0, "avg_price": 500.0},
            {"type": "Enterprise", "quantity": 5, "total_cost": 2500.0, "avg_price": 500.0},
        ]
        result = build_dashboard_context(ctx)
        summary = result["price_distribution_summary"]
        qty_item = next(s for s in summary if s["label"] == "Total Quantity")
        assert qty_item["value"] == 15

    def test_highest_avg_price_in_summary(self):
        ctx = self._ctx()
        ctx["license_metrics"]["price_distribution"] = [
            {"type": "Enterprise", "quantity": 4, "total_cost": 2000.0, "avg_price": 500.0},
        ]
        result = build_dashboard_context(ctx)
        summary = result["price_distribution_summary"]
        highest = next(s for s in summary if s["label"] == "Highest Avg Price")
        assert highest["value"] == 500.0
        assert "Enterprise" in highest["subtext"]

    def test_default_title_set(self):
        result = build_dashboard_context(self._ctx())
        assert result["title"] == "Results & Dashboard"

    def test_custom_title_preserved(self):
        ctx = self._ctx()
        ctx["title"] = "Custom Title"
        result = build_dashboard_context(ctx)
        assert result["title"] == "Custom Title"

    def test_request_id_added_when_provided(self):
        result = build_dashboard_context(self._ctx(), request_id="req-123")
        assert result["request_id"] == "req-123"

    def test_no_request_id_not_added(self):
        result = build_dashboard_context(self._ctx())
        assert "request_id" not in result

    def test_rightsizing_data_included(self):
        ctx = self._ctx()
        ctx["rightsizing"] = {
            "total_vcpu_reduction": 8,
            "avg_cost_per_core_pair_eur": 100.0,
            "total_ram_reduction_gib": 0,
            "avg_cost_per_gib_eur": 0,
            "cpu_count": 4,
            "ram_count": 0,
        }
        result = build_dashboard_context(ctx)
        assert result["rightsizing_savings"] >= 0
        meta = result["rightsizing_meta"]
        assert meta["total_vcpu_reduction"] == 8

    def test_payg_savings_from_cost_overrides(self):
        ctx = self._ctx()
        ctx["rule_results"]["azure_payg_savings_eur"] = 9999.0
        result = build_dashboard_context(ctx)
        assert result["azure_payg_savings"] == 9999.0

    def test_retired_savings_from_cost_overrides(self):
        ctx = self._ctx()
        ctx["rule_results"]["retired_devices_savings_eur"] = 8888.0
        result = build_dashboard_context(ctx)
        assert result["retired_devices_savings"] == 8888.0

    def test_empty_context_returns_zeros(self):
        result = build_dashboard_context({})
        assert result["azure_payg_count"] == 0
        assert result["total_savings"] == 0.0

    def test_precomputed_savings_preserved(self):
        ctx = self._ctx()
        ctx["rule_wise_savings"] = {"azure_payg": 99.0, "retired_devices": 1.0, "rightsizing": 0.0, "rightsizing_cpu": 0.0, "rightsizing_ram": 0.0}
        result = build_dashboard_context(ctx)
        assert result["rule_wise_savings"]["azure_payg"] == 99.0


# ===========================================================================
# build_analysis_summary_metrics
# ===========================================================================

class TestBuildAnalysisSummaryMetrics:
    def _ctx(self):
        return {
            "rule_results": {"azure_payg_count": 3, "retired_count": 2},
            "license_metrics": {
                "total_demand_quantity": 50,
                "total_license_cost": 5000.0,
                "price_distribution": [],
                "cost_reduction_tips": [],
            },
            "total_devices_analyzed": 100,
        }

    def test_required_keys_returned(self):
        result = build_analysis_summary_metrics(self._ctx())
        for key in (
            "total_devices_analyzed", "total_demand_quantity",
            "total_license_cost", "azure_payg_count",
            "retired_count", "total_savings",
        ):
            assert key in result

    def test_values_are_correct_type(self):
        result = build_analysis_summary_metrics(self._ctx())
        assert isinstance(result["total_devices_analyzed"], int)
        assert isinstance(result["total_license_cost"], float)

    def test_counts_extracted_correctly(self):
        result = build_analysis_summary_metrics(self._ctx())
        assert result["azure_payg_count"] == 3
        assert result["retired_count"] == 2

    def test_non_dict_context_treated_as_empty(self):
        result = build_analysis_summary_metrics(None)
        assert result["azure_payg_count"] == 0

    def test_empty_context_returns_zeros(self):
        result = build_analysis_summary_metrics({})
        assert result["total_savings"] == 0.0


# ===========================================================================
# PipelineTimer
# ===========================================================================

class TestPipelineTimer:
    def test_durations_empty_initially(self):
        timer = PipelineTimer()
        # ContextVar may have leftovers from other tests; just check type
        assert isinstance(timer.durations, dict)

    def test_phase_records_duration(self):
        timer = PipelineTimer()
        with timer.phase("test_phase"):
            pass  # instant
        durations = timer.durations
        assert "test_phase_sec" in durations
        assert durations["test_phase_sec"] >= 0.0

    def test_multiple_phases_accumulated(self):
        timer = PipelineTimer()
        with timer.phase("phase_a"):
            pass
        with timer.phase("phase_b"):
            pass
        durations = timer.durations
        assert "phase_a_sec" in durations
        assert "phase_b_sec" in durations

    def test_record_sets_duration_directly(self):
        timer = PipelineTimer()
        timer.record("direct_phase", 1.234)
        durations = timer.durations
        assert "direct_phase_sec" in durations
        assert abs(durations["direct_phase_sec"] - 1.234) < 0.001

    def test_durations_returns_dict_copy(self):
        timer = PipelineTimer()
        d1 = timer.durations
        d1["extra_key"] = 999
        d2 = timer.durations
        assert "extra_key" not in d2

    def test_phase_records_even_after_exception(self):
        timer = PipelineTimer()
        try:
            with timer.phase("exception_phase"):
                raise ValueError("test error")
        except ValueError:
            pass
        assert "exception_phase_sec" in timer.durations
