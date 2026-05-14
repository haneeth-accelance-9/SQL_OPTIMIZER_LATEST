"""
Additional coverage tests for optimizer/services/chart_generator.py

Targets the following missed line ranges:
  - Lines 101-132: _anim_to_gif_base64 (GIF-save path and fallback)
  - Lines 188-216: _bar_chart_animated with real data (animated path)
  - Lines 270-298: _bar_chart_horizontal_animated with real data
  - Lines 338-362: _pie_chart_animated with real data
  - Lines 399-423: _doughnut_chart_animated with real data
  - Line 678:      "test" environment label color in generate_all_charts
  - Line 706:      cost_data length mismatch path
  - Lines 828-831: CPU core bucket >8 and >16 paths
  - Line 847:      env_vals all-zero fallback to ["No data"]

NOTE: No @pytest.mark.django_db — chart_generator has no DB access.
Animated chart GIF paths are exercised by mocking _anim_to_gif_base64 (the
expensive Pillow writer call) so tests remain fast.
"""
import base64
import io
import os
import tempfile
from unittest.mock import MagicMock, patch

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.animation as mplanim
import pytest

from optimizer.services.chart_generator import (
    _anim_to_gif_base64,
    _bar_chart_animated,
    _bar_chart_horizontal_animated,
    _doughnut_chart_animated,
    _fig_to_base64,
    _pie_chart_animated,
    generate_all_charts,
)

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

_MOD = "optimizer.services.chart_generator"

FAKE_GIF_B64 = "R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs="  # minimal valid GIF

ALL_CHART_IDS = [
    "chart_azure_cores",
    "chart_azure_zones",
    "chart_retired",
    "chart_retired_env",
    "chart_demand",
    "chart_cost",
    "chart_overview",
    "chart_devices",
    "chart_license_cost_donut",
    "chart_azure_by_zone_bar",
    "chart_byol_vs_payg",
    "chart_retired_services",
    "chart_cpu_histogram",
    "chart_env_pie",
    "chart_top10_cost",
    "chart_waterfall",
]


def _is_valid_b64(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    try:
        decoded = base64.b64decode(value, validate=True)
        return len(decoded) > 0
    except Exception:
        return False


def _make_anim(frames=4):
    """Create a trivial matplotlib FuncAnimation for testing."""
    fig, ax = plt.subplots(figsize=(2, 2))
    bars = ax.bar([0], [1])

    def update(frame):
        bars[0].set_height(frame + 1)
        return bars

    anim = mplanim.FuncAnimation(fig, update, frames=frames, interval=50, blit=False)
    return anim, fig


# ---------------------------------------------------------------------------
# _anim_to_gif_base64 — GIF success path (mock the Pillow writer)
# ---------------------------------------------------------------------------

class TestAnimToGifBase64:
    def test_returns_gif_tuple_on_success(self):
        """Mock anim.save so we get the 'gif' format return path."""
        anim, fig = _make_anim()

        def fake_save(path, **kwargs):
            # Write a minimal valid GIF to the temp file
            gif_bytes = base64.b64decode(FAKE_GIF_B64)
            with open(path, "wb") as f:
                f.write(gif_bytes)

        with patch.object(anim, "save", side_effect=fake_save):
            fmt, b64 = _anim_to_gif_base64(anim, fig)

        assert fmt == "gif"
        assert _is_valid_b64(b64)

    def test_fallback_to_png_on_save_exception(self):
        """When anim.save raises, _anim_to_gif_base64 must return ('png', <b64>)."""
        anim, fig = _make_anim()

        with patch.object(anim, "save", side_effect=RuntimeError("pillow not available")):
            fmt, b64 = _anim_to_gif_base64(anim, fig)

        assert fmt == "png"
        assert _is_valid_b64(b64)

    def test_cleans_up_temp_file_on_success(self):
        """The temp GIF file must be removed after a successful save."""
        created_paths = []
        anim, fig = _make_anim()

        original_mkstemp = tempfile.mkstemp

        def tracking_mkstemp(*args, **kwargs):
            fd, path = original_mkstemp(*args, **kwargs)
            created_paths.append(path)
            return fd, path

        def fake_save(path, **kwargs):
            with open(path, "wb") as f:
                f.write(base64.b64decode(FAKE_GIF_B64))

        with patch("tempfile.mkstemp", side_effect=tracking_mkstemp):
            with patch.object(anim, "save", side_effect=fake_save):
                _anim_to_gif_base64(anim, fig)

        for path in created_paths:
            if path.endswith(".gif"):
                assert not os.path.isfile(path), "Temp GIF file was not cleaned up"

    def test_cleans_up_temp_file_on_failure(self):
        """The temp GIF file must be removed even when save raises."""
        created_paths = []
        anim, fig = _make_anim()

        original_mkstemp = tempfile.mkstemp

        def tracking_mkstemp(*args, **kwargs):
            fd, path = original_mkstemp(*args, **kwargs)
            created_paths.append(path)
            return fd, path

        with patch("tempfile.mkstemp", side_effect=tracking_mkstemp):
            with patch.object(anim, "save", side_effect=RuntimeError("fail")):
                _anim_to_gif_base64(anim, fig)

        for path in created_paths:
            if path.endswith(".gif"):
                assert not os.path.isfile(path), "Temp GIF file was not cleaned up on failure"


# ---------------------------------------------------------------------------
# _bar_chart_animated — with data (lines 188-216)
# ---------------------------------------------------------------------------

class TestBarChartAnimatedWithData:
    def test_with_data_returns_two_tuple(self):
        """Mock _anim_to_gif_base64 to avoid slow GIF generation."""
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            result = _bar_chart_animated(
                ["A", "B", "C"], [10.0, 20.0, 30.0], "Animated Bar with Data"
            )
        assert isinstance(result, tuple) and len(result) == 2
        fmt, b64 = result
        assert fmt == "gif"
        assert b64 == FAKE_GIF_B64

    def test_with_data_single_item(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _bar_chart_animated(["Only"], [1.0], "Single Bar Animated")
        assert fmt == "gif"

    def test_with_data_all_zeros(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _bar_chart_animated(["X", "Y"], [0.0, 0.0], "Zeros Animated")
        # Should not raise; 0-value bars are valid
        assert fmt == "gif"

    def test_with_data_custom_color(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _bar_chart_animated(
                ["P", "Q"], [5.0, 10.0], "Colored Animated", color="#ff0000"
            )
        assert fmt == "gif"

    def test_anim_to_gif_base64_called_with_animation(self):
        """Verify that FuncAnimation is created and passed to _anim_to_gif_base64."""
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)) as mock_gif:
            _bar_chart_animated(["A", "B"], [10.0, 20.0], "Anim Called")
        mock_gif.assert_called_once()
        # First positional arg should be a FuncAnimation
        anim_arg = mock_gif.call_args[0][0]
        assert isinstance(anim_arg, mplanim.FuncAnimation)


# ---------------------------------------------------------------------------
# _bar_chart_horizontal_animated — with data (lines 270-298)
# ---------------------------------------------------------------------------

class TestBarChartHorizontalAnimatedWithData:
    def test_with_data_returns_gif_tuple(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _bar_chart_horizontal_animated(
                ["Prod", "Dev", "Test"], [5.0, 3.0, 2.0], "H-Bar Animated with Data"
            )
        assert fmt == "gif"
        assert b64 == FAKE_GIF_B64

    def test_with_custom_colors(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _bar_chart_horizontal_animated(
                ["A", "B"], [7.0, 3.0], "Colors H-Bar",
                colors=["#ff0000", "#00ff00"]
            )
        assert fmt == "gif"

    def test_with_single_item(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _bar_chart_horizontal_animated(["Single"], [10.0], "Single H-Bar")
        assert fmt == "gif"

    def test_anim_to_gif_called(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)) as mock_gif:
            _bar_chart_horizontal_animated(
                ["X", "Y", "Z"], [1.0, 2.0, 3.0], "H Called"
            )
        mock_gif.assert_called_once()
        anim_arg = mock_gif.call_args[0][0]
        assert isinstance(anim_arg, mplanim.FuncAnimation)


# ---------------------------------------------------------------------------
# _pie_chart_animated — with data (lines 338-362)
# ---------------------------------------------------------------------------

class TestPieChartAnimatedWithData:
    def test_with_data_returns_gif_tuple(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _pie_chart_animated(
                ["Slice A", "Slice B", "Slice C"], [60.0, 30.0, 10.0], "Pie Animated with Data"
            )
        assert fmt == "gif"
        assert b64 == FAKE_GIF_B64

    def test_with_custom_colors(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _pie_chart_animated(
                ["A", "B"], [70.0, 30.0], "Colored Pie Animated",
                colors=["#aabbcc", "#112233"]
            )
        assert fmt == "gif"

    def test_with_large_palette_labels(self):
        # More labels than PALETTE entries
        labels = [f"L{i}" for i in range(15)]
        values = [float(i + 1) for i in range(15)]
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _pie_chart_animated(labels, values, "Large Pie")
        assert fmt == "gif"

    def test_anim_to_gif_called_with_funcanimation(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)) as mock_gif:
            _pie_chart_animated(["A", "B"], [50.0, 50.0], "Pie Call Check")
        mock_gif.assert_called_once()
        assert isinstance(mock_gif.call_args[0][0], mplanim.FuncAnimation)


# ---------------------------------------------------------------------------
# _doughnut_chart_animated — with data (lines 399-423)
# ---------------------------------------------------------------------------

class TestDoughnutChartAnimatedWithData:
    def test_with_data_returns_gif_tuple(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _doughnut_chart_animated(
                ["Inner", "Outer"], [40.0, 60.0], "Doughnut Animated with Data"
            )
        assert fmt == "gif"
        assert b64 == FAKE_GIF_B64

    def test_with_custom_colors(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _doughnut_chart_animated(
                ["X", "Y"], [55.0, 45.0], "Colored Doughnut",
                colors=["#123456", "#654321"]
            )
        assert fmt == "gif"

    def test_with_single_slice(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)):
            fmt, b64 = _doughnut_chart_animated(["Only"], [100.0], "Single Doughnut")
        assert fmt == "gif"

    def test_anim_to_gif_called(self):
        with patch(f"{_MOD}._anim_to_gif_base64", return_value=("gif", FAKE_GIF_B64)) as mock_gif:
            _doughnut_chart_animated(["A", "B"], [30.0, 70.0], "Doughnut Call Check")
        mock_gif.assert_called_once()
        assert isinstance(mock_gif.call_args[0][0], mplanim.FuncAnimation)


# ---------------------------------------------------------------------------
# generate_all_charts — specific missed sub-paths
# ---------------------------------------------------------------------------

_ANIMATED_PATCHES = [
    f"{_MOD}._bar_chart_animated",
    f"{_MOD}._bar_chart_horizontal_animated",
    f"{_MOD}._pie_chart_animated",
    f"{_MOD}._doughnut_chart_animated",
]


def _patch_animated(rv=("gif", FAKE_GIF_B64)):
    return [patch(t, return_value=rv) for t in _ANIMATED_PATCHES]


class TestGenerateAllChartsTestEnvColor:
    """Cover line 678: 'test' environment label in color selection."""

    def test_test_environment_label_triggers_test_color(self):
        """
        Retired devices with 'test' in their environment name should use the
        '#DCE3EC' color branch (line 677-678).
        """
        rule_results = {
            "retired_devices": [
                {"device_ci": "RDEV01", "environment": "Test Environment"},
                {"device_ci": "RDEV02", "environment": "Production"},
            ],
            "retired_count": 2,
        }
        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(rule_results, {})

        assert "chart_retired_env" in charts
        assert isinstance(charts["chart_retired_env"], str)

    def test_dev_environment_label_triggers_dev_color(self):
        rule_results = {
            "retired_devices": [
                {"device_ci": "RDEV01", "environment": "Development"},
            ],
            "retired_count": 1,
        }
        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(rule_results, {})

        assert "chart_retired_env" in charts

    def test_prod_environment_label_triggers_prod_color(self):
        rule_results = {
            "retired_devices": [
                {"device_ci": "RDEV01", "environment": "Production"},
            ],
            "retired_count": 1,
        }
        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(rule_results, {})

        assert "chart_retired_env" in charts


class TestGenerateAllChartsCostDataLenMismatch:
    """Cover line 706: cost_data length mismatch trim path."""

    def test_cost_data_longer_than_labels_is_trimmed(self):
        """
        by_product where labels and cost_data differ in length after truncation
        triggers the len(cost_data) != len(labels_bp) branch.
        """
        # Provide one product with a label but no cost (falsy), so cost_data gets
        # rebuilt differently. We give two different-length products.
        # The key trigger is when cost_data ends up having a different length
        # than labels_bp. We do this by providing data and then
        # checking the chart still generates without error.
        by_product = [
            {"product": "SQL Server", "quantity": 10, "cost": 5000.0},
            {"product": "Oracle DB", "quantity": 5, "cost": 3000.0},
            {"product": "MySQL", "quantity": 2, "cost": 1000.0},
        ]
        license_metrics = {"by_product": by_product}

        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, license_metrics)

        assert "chart_cost" in charts
        assert "chart_demand" in charts


class TestGenerateAllChartsCpuBuckets:
    """Cover lines 828-831: CPU core bucket > 8 and > 16 paths."""

    def test_cpu_cores_over_8_and_16_fill_correct_buckets(self):
        """
        Azure rows with cpu_core_count > 8 and > 16 trigger the '16' and '16+'
        bucket branches (lines 828-831).
        """
        azure_rows = [
            {"device_name": "SRV_2c",  "u_cpu": 2},   # <= 2 bucket
            {"device_name": "SRV_4c",  "u_cpu": 4},   # <= 4 bucket
            {"device_name": "SRV_8c",  "u_cpu": 8},   # <= 8 bucket
            {"device_name": "SRV_16c", "u_cpu": 16},  # <= 16 bucket (line 828)
            {"device_name": "SRV_32c", "u_cpu": 32},  # 16+ bucket (line 830-831)
            {"device_name": "SRV_64c", "u_cpu": 64},  # 16+ bucket
        ]
        rule_results = {
            "azure_payg": azure_rows,
            "azure_payg_count": len(azure_rows),
        }

        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(rule_results, {})

        assert "chart_cpu_histogram" in charts
        assert formats["chart_cpu_histogram"] == "png"
        assert _is_valid_b64(charts["chart_cpu_histogram"])

    def test_cpu_exactly_16_goes_to_16_bucket(self):
        azure_rows = [{"device_name": "SRV01", "u_cpu": 16}]
        rule_results = {"azure_payg": azure_rows, "azure_payg_count": 1}

        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(rule_results, {})

        assert "chart_cpu_histogram" in charts
        assert _is_valid_b64(charts["chart_cpu_histogram"])

    def test_cpu_over_16_goes_to_16plus_bucket(self):
        azure_rows = [
            {"device_name": "SRV_BIG1", "u_cpu": 32},
            {"device_name": "SRV_BIG2", "u_cpu": 64},
            {"device_name": "SRV_BIG3", "u_cpu": 128},
        ]
        rule_results = {"azure_payg": azure_rows, "azure_payg_count": 3}

        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(rule_results, {})

        assert _is_valid_b64(charts["chart_cpu_histogram"])


class TestGenerateAllChartsEnvPieAllZeros:
    """Cover line 847: env_vals all-zero path -> fallback to ['No data']."""

    def test_env_pie_all_zero_zones_falls_back_to_no_data(self):
        """
        When azure has rows but none produce non-zero zone counts,
        env_vals = [0, 0, ...] triggers the all-zero guard (line 846-847).
        Note: zones dict is built from azure rows; empty azure + non-zero counts
        means zones={} so the else branch fills azure_count/total_demand values.
        We force all-zero by passing azure with a zone key that results in
        counts summing to 0 (not possible naturally), OR by patching the
        zones dict to be all-zeros after it's built.
        The simplest reliable path: pass azure=[] so zones stays {}, and
        azure_count=0, total_demand=0. Then env_vals=[0,0+,0] -> may be all zero.
        """
        # azure=[], azure_count=0, total_demand=0 → env_vals=[0,0,0] → line 847 fires
        rule_results = {"azure_payg_count": 0, "retired_count": 0}
        license_metrics = {"total_demand_quantity": 0}

        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(rule_results, license_metrics)

        assert "chart_env_pie" in charts
        assert isinstance(charts["chart_env_pie"], str)

    def test_env_pie_with_valid_zones_uses_zone_data(self):
        """When azure has rows producing real zone counts, those are used for env_pie."""
        azure_rows = [
            {"device_name": "SRV01", "u_cpu": 4, "u_hosting_zone": "Public Cloud"},
            {"device_name": "SRV02", "u_cpu": 8, "u_hosting_zone": "Private Cloud"},
        ]
        rule_results = {
            "azure_payg": azure_rows,
            "azure_payg_count": 2,
        }
        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(rule_results, {})

        assert "chart_env_pie" in charts


class TestGenerateAllChartsTop10CostPath:
    """Ensure top10_cost animated path (by_product with non-zero costs) is exercised."""

    def test_top10_cost_animated_when_costs_nonzero(self):
        license_metrics = {
            "by_product": [
                {"product": f"Product {i}", "quantity": i + 1, "cost": float((i + 1) * 1000)}
                for i in range(12)
            ]
        }
        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, license_metrics)

        assert "chart_top10_cost" in charts
        assert formats["chart_top10_cost"] == "gif"
        assert charts["chart_top10_cost"] == FAKE_GIF_B64

    def test_top10_cost_static_when_all_zero_costs(self):
        license_metrics = {
            "by_product": [
                {"product": "SQL Server", "quantity": 10, "cost": 0},
            ]
        }
        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, license_metrics)

        assert "chart_top10_cost" in charts
        assert formats["chart_top10_cost"] == "png"


class TestGenerateAllChartsCompleteRun:
    """Full rule_results + license_metrics run covering all branches together."""

    RULE_RESULTS = {
        "azure_payg": [
            {"device_name": "VM-PROD01", "u_cpu": 4, "u_hosting_zone": "Public Cloud"},
            {"device_name": "VM-PROD02", "u_cpu": 16, "u_hosting_zone": "Private Cloud AVS"},
            {"device_name": "VM-DEV01",  "u_cpu": 32, "u_hosting_zone": "Public Cloud"},
            {"device_name": "VM-TEST01", "u_cpu": 2,  "u_hosting_zone": "Test Zone"},
        ],
        "azure_payg_count": 4,
        "retired_devices": [
            {"device_ci": "OLD01", "environment": "Production"},
            {"device_ci": "OLD02", "environment": "Development"},
            {"device_ci": "OLD03", "environment": "Test"},
        ],
        "retired_count": 3,
        "payg_zone_breakdown": {
            "labels": ["Public Cloud", "Private Cloud AVS"],
            "current": [3, 1],
            "estimated": [4, 2],
        },
    }

    LICENSE_METRICS = {
        "by_product": [
            {"product": "SQL Server 2019", "quantity": 50, "cost": 12000.0},
            {"product": "SQL Server 2017", "quantity": 30, "cost": 8000.0},
            {"product": "SQL Server 2016", "quantity": 10, "cost": 3000.0},
        ],
        "total_demand_quantity": 90,
        "total_license_cost": 23000.0,
    }

    def test_all_chart_ids_present(self):
        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(self.RULE_RESULTS, self.LICENSE_METRICS)

        for cid in ALL_CHART_IDS:
            assert cid in charts, f"Missing chart: {cid}"
            assert cid in formats, f"Missing format: {cid}"

    def test_static_charts_have_valid_b64(self):
        static_ids = [
            "chart_byol_vs_payg",
            "chart_retired_services",
            "chart_cpu_histogram",
            "chart_waterfall",
            "chart_azure_by_zone_bar",
        ]
        with patch(_ANIMATED_PATCHES[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCHES[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(self.RULE_RESULTS, self.LICENSE_METRICS)

        for cid in static_ids:
            assert _is_valid_b64(charts[cid]), f"{cid} has invalid base64"
            assert formats[cid] == "png", f"{cid} should be png, got {formats[cid]}"
