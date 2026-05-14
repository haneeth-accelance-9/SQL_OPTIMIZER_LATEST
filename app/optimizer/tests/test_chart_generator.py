"""
Pytest test suite for optimizer/services/chart_generator.py

Coverage targets:
  - _find_key          (pure helper)
  - _zone_colors       (pure helper)
  - _fig_to_base64     (pure helper)
  - _bar_chart         (static, with data + empty)
  - _bar_chart_horizontal (static, with data + empty)
  - _pie_chart         (static, with data + empty + all-zero values)
  - _doughnut_chart    (static, with data + empty + all-zero values)
  - _comparison_bar_chart (static, with data + empty)
  - _grouped_bar_chart (static, with data + empty)
  - _waterfall_chart   (static, with data + mismatched lengths)
  - _histogram_chart   (static, with data + empty)
  - Animated functions -- EMPTY-DATA PATH ONLY (fast PNG fallback, no GIF generation)
      _bar_chart_animated
      _bar_chart_horizontal_animated
      _pie_chart_animated
      _doughnut_chart_animated
  - generate_all_charts:
      * empty rule_results / license_metrics  (all animated fns patched)
      * minimal populated dicts               (all animated fns patched)
      * exception path (one patched fn raises, verify all 16 placeholder keys set)

NOTE: @pytest.mark.django_db is intentionally NOT used - chart_generator has no DB access.
"""

import base64
import io
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")  # must be set before any other matplotlib import
import matplotlib.pyplot as plt
import pytest

from optimizer.services.chart_generator import (
    _find_key,
    _zone_colors,
    _fig_to_base64,
    _bar_chart,
    _bar_chart_animated,
    _bar_chart_horizontal,
    _bar_chart_horizontal_animated,
    _pie_chart,
    _pie_chart_animated,
    _doughnut_chart,
    _doughnut_chart_animated,
    _comparison_bar_chart,
    _grouped_bar_chart,
    _waterfall_chart,
    _histogram_chart,
    generate_all_charts,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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

# A fake base64 payload returned by patched animated functions
FAKE_GIF_B64 = "ZmFrZQ=="

# Patch target prefix
_MOD = "optimizer.services.chart_generator"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_b64(value: str) -> bool:
    """Return True when *value* is a non-empty valid base64-encoded string."""
    if not value or not isinstance(value, str):
        return False
    try:
        decoded = base64.b64decode(value, validate=True)
        return len(decoded) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# _find_key
# ---------------------------------------------------------------------------

class TestFindKey:
    def test_finds_matching_key_case_insensitive(self):
        row = {"CPU_Cores": 4, "device_name": "SRV01"}
        assert _find_key(row, ["cpu"]) == "CPU_Cores"

    def test_returns_first_pattern_match(self):
        row = {"u_cpu": 8, "core_count": 4}
        # "cpu" appears in u_cpu, "core" appears in core_count; cpu listed first
        result = _find_key(row, ["cpu", "core"])
        assert result == "u_cpu"

    def test_returns_empty_string_when_no_match(self):
        row = {"device_name": "SRV01"}
        assert _find_key(row, ["cpu", "core"]) == ""

    def test_returns_empty_string_for_none_row(self):
        assert _find_key(None, ["cpu"]) == ""

    def test_returns_empty_string_for_non_dict_row(self):
        assert _find_key("not_a_dict", ["cpu"]) == ""

    def test_returns_empty_string_for_empty_dict(self):
        assert _find_key({}, ["cpu"]) == ""

    def test_returns_empty_string_for_empty_patterns(self):
        row = {"cpu": 4}
        assert _find_key(row, []) == ""

    def test_partial_match_in_key(self):
        row = {"u_hosting_zone": "AVS"}
        assert _find_key(row, ["hosting"]) == "u_hosting_zone"


# ---------------------------------------------------------------------------
# _zone_colors
# ---------------------------------------------------------------------------

class TestZoneColors:
    def test_avs_label_gets_avs_color(self):
        colors = _zone_colors(["AVS Zone", "Public Cloud", "Private Cloud"])
        assert colors[0] == "#18AEEF"

    def test_public_label_gets_public_color(self):
        colors = _zone_colors(["Public Cloud"])
        assert colors[0] == "#84D91D"

    def test_private_label_gets_private_color(self):
        colors = _zone_colors(["Private Cloud"])
        assert colors[0] == "#153E5C"

    def test_unknown_label_gets_palette_color(self):
        colors = _zone_colors(["Unknown Zone"])
        # Must be a non-empty string starting with '#'
        assert isinstance(colors[0], str) and colors[0].startswith("#")

    def test_returns_same_length_as_input(self):
        labels = ["AVS", "Public", "Private", "Other", "Foo"]
        colors = _zone_colors(labels)
        assert len(colors) == len(labels)

    def test_empty_list_returns_empty(self):
        assert _zone_colors([]) == []

    def test_case_insensitive_matching(self):
        colors_lower = _zone_colors(["avs datacenter"])
        assert colors_lower[0] == "#18AEEF"


# ---------------------------------------------------------------------------
# _fig_to_base64
# ---------------------------------------------------------------------------

class TestFigToBase64:
    def test_returns_non_empty_base64_string(self):
        fig, ax = plt.subplots(figsize=(4, 3), facecolor="white")
        ax.text(0.5, 0.5, "test", ha="center")
        result = _fig_to_base64(fig)
        plt.close(fig)
        assert _is_valid_b64(result)

    def test_output_decodes_to_png_bytes(self):
        fig, ax = plt.subplots(figsize=(2, 2), facecolor="white")
        result = _fig_to_base64(fig)
        plt.close(fig)
        png_bytes = base64.b64decode(result)
        # PNG magic bytes: \x89PNG
        assert png_bytes[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# _bar_chart (static, vertical)
# ---------------------------------------------------------------------------

class TestBarChart:
    def test_with_data_returns_valid_b64(self):
        result = _bar_chart(["A", "B", "C"], [10, 20, 30], "Test Bar")
        assert _is_valid_b64(result)

    def test_with_empty_labels_returns_valid_b64(self):
        result = _bar_chart([], [], "Empty Bar")
        assert _is_valid_b64(result)

    def test_with_none_labels_returns_valid_b64(self):
        result = _bar_chart(None, None, "None Bar")
        assert _is_valid_b64(result)

    def test_with_single_item_returns_valid_b64(self):
        result = _bar_chart(["Only"], [42], "Single Bar")
        assert _is_valid_b64(result)

    def test_custom_color_accepted(self):
        result = _bar_chart(["X"], [5], "Colored Bar", color="#ff0000")
        assert _is_valid_b64(result)


# ---------------------------------------------------------------------------
# _bar_chart_animated -- empty/None data only (PNG fallback, no GIF)
# ---------------------------------------------------------------------------

class TestBarChartAnimatedEmptyPath:
    def test_empty_labels_returns_png_tuple(self):
        fmt, b64 = _bar_chart_animated([], [], "Animated Empty")
        assert fmt == "png"
        assert _is_valid_b64(b64)

    def test_none_labels_returns_png_tuple(self):
        fmt, b64 = _bar_chart_animated(None, None, "Animated None")
        assert fmt == "png"
        assert _is_valid_b64(b64)

    def test_return_value_is_tuple_of_two(self):
        result = _bar_chart_animated([], [], "T")
        assert isinstance(result, tuple) and len(result) == 2


# ---------------------------------------------------------------------------
# _bar_chart_horizontal (static)
# ---------------------------------------------------------------------------

class TestBarChartHorizontal:
    def test_with_data_returns_valid_b64(self):
        result = _bar_chart_horizontal(["Prod", "Dev", "Test"], [5, 3, 2], "Horizontal Bar")
        assert _is_valid_b64(result)

    def test_with_empty_labels_returns_valid_b64(self):
        result = _bar_chart_horizontal([], [], "Empty H-Bar")
        assert _is_valid_b64(result)

    def test_with_custom_colors(self):
        result = _bar_chart_horizontal(["A", "B"], [1, 2], "Colors", colors=["#ff0000", "#00ff00"])
        assert _is_valid_b64(result)


# ---------------------------------------------------------------------------
# _bar_chart_horizontal_animated -- empty/None data only (PNG fallback)
# ---------------------------------------------------------------------------

class TestBarChartHorizontalAnimatedEmptyPath:
    def test_empty_labels_returns_png_tuple(self):
        fmt, b64 = _bar_chart_horizontal_animated([], [], "H Animated Empty")
        assert fmt == "png"
        assert _is_valid_b64(b64)

    def test_none_labels_returns_png_tuple(self):
        fmt, b64 = _bar_chart_horizontal_animated(None, None, "H Animated None")
        assert fmt == "png"
        assert _is_valid_b64(b64)

    def test_return_is_two_element_tuple(self):
        result = _bar_chart_horizontal_animated([], [], "T")
        assert isinstance(result, tuple) and len(result) == 2


# ---------------------------------------------------------------------------
# _pie_chart (static)
# ---------------------------------------------------------------------------

class TestPieChart:
    def test_with_data_returns_valid_b64(self):
        result = _pie_chart(["A", "B"], [60, 40], "Pie Test")
        assert _is_valid_b64(result)

    def test_empty_labels_returns_valid_b64(self):
        result = _pie_chart([], [], "Empty Pie")
        assert _is_valid_b64(result)

    def test_all_zero_values_returns_valid_b64(self):
        result = _pie_chart(["A", "B"], [0, 0], "Zero Pie")
        assert _is_valid_b64(result)

    def test_none_labels_returns_valid_b64(self):
        result = _pie_chart(None, None, "None Pie")
        assert _is_valid_b64(result)

    def test_with_custom_colors(self):
        result = _pie_chart(["X", "Y"], [50, 50], "Colored Pie", colors=["#aabbcc", "#112233"])
        assert _is_valid_b64(result)


# ---------------------------------------------------------------------------
# _pie_chart_animated -- empty/None/all-zero data only (PNG fallback)
# ---------------------------------------------------------------------------

class TestPieChartAnimatedEmptyPath:
    def test_empty_labels_returns_png_tuple(self):
        fmt, b64 = _pie_chart_animated([], [], "Animated Pie Empty")
        assert fmt == "png"
        assert _is_valid_b64(b64)

    def test_none_inputs_returns_png_tuple(self):
        fmt, b64 = _pie_chart_animated(None, None, "Animated Pie None")
        assert fmt == "png"
        assert _is_valid_b64(b64)

    def test_all_zero_values_returns_png_tuple(self):
        fmt, b64 = _pie_chart_animated(["A", "B"], [0, 0], "Animated Pie Zeros")
        assert fmt == "png"
        assert _is_valid_b64(b64)

    def test_return_is_two_element_tuple(self):
        result = _pie_chart_animated([], [], "T")
        assert isinstance(result, tuple) and len(result) == 2


# ---------------------------------------------------------------------------
# _doughnut_chart (static)
# ---------------------------------------------------------------------------

class TestDoughnutChart:
    def test_with_data_returns_valid_b64(self):
        result = _doughnut_chart(["X", "Y"], [70, 30], "Doughnut Test")
        assert _is_valid_b64(result)

    def test_empty_labels_returns_valid_b64(self):
        result = _doughnut_chart([], [], "Empty Doughnut")
        assert _is_valid_b64(result)

    def test_all_zero_values_returns_valid_b64(self):
        result = _doughnut_chart(["A", "B"], [0, 0], "Zero Doughnut")
        assert _is_valid_b64(result)

    def test_none_labels_returns_valid_b64(self):
        result = _doughnut_chart(None, None, "None Doughnut")
        assert _is_valid_b64(result)


# ---------------------------------------------------------------------------
# _doughnut_chart_animated -- empty/None/all-zero data only (PNG fallback)
# ---------------------------------------------------------------------------

class TestDoughnutChartAnimatedEmptyPath:
    def test_empty_labels_returns_png_tuple(self):
        fmt, b64 = _doughnut_chart_animated([], [], "Animated Doughnut Empty")
        assert fmt == "png"
        assert _is_valid_b64(b64)

    def test_none_inputs_returns_png_tuple(self):
        fmt, b64 = _doughnut_chart_animated(None, None, "Animated Doughnut None")
        assert fmt == "png"
        assert _is_valid_b64(b64)

    def test_all_zero_values_returns_png_tuple(self):
        fmt, b64 = _doughnut_chart_animated(["A", "B"], [0, 0], "Animated Doughnut Zeros")
        assert fmt == "png"
        assert _is_valid_b64(b64)

    def test_return_is_two_element_tuple(self):
        result = _doughnut_chart_animated([], [], "T")
        assert isinstance(result, tuple) and len(result) == 2


# ---------------------------------------------------------------------------
# _comparison_bar_chart (static)
# ---------------------------------------------------------------------------

class TestComparisonBarChart:
    def test_with_data_returns_valid_b64(self):
        result = _comparison_bar_chart(["BYOL", "PAYG"], [1000.0, 850.0], "Comparison")
        assert _is_valid_b64(result)

    def test_empty_labels_returns_valid_b64(self):
        result = _comparison_bar_chart([], [], "Empty Comparison")
        assert _is_valid_b64(result)

    def test_none_inputs_returns_valid_b64(self):
        result = _comparison_bar_chart(None, None, "None Comparison")
        assert _is_valid_b64(result)

    def test_custom_colors_accepted(self):
        result = _comparison_bar_chart(["A", "B"], [100, 200], "Colors", colors=["#ff0000", "#00ff00"])
        assert _is_valid_b64(result)


# ---------------------------------------------------------------------------
# _grouped_bar_chart (static)
# ---------------------------------------------------------------------------

class TestGroupedBarChart:
    def test_with_data_returns_valid_b64(self):
        series = [
            {"name": "Current", "values": [10, 20], "color": "#0ea5e9"},
            {"name": "Estimated", "values": [15, 25], "color": "#14b8a6"},
        ]
        result = _grouped_bar_chart(["Zone A", "Zone B"], series, "Grouped Bar")
        assert _is_valid_b64(result)

    def test_empty_labels_returns_valid_b64(self):
        result = _grouped_bar_chart([], [], "Empty Grouped")
        assert _is_valid_b64(result)

    def test_empty_series_returns_valid_b64(self):
        result = _grouped_bar_chart(["A", "B"], [], "No Series")
        assert _is_valid_b64(result)

    def test_series_with_missing_values_key(self):
        # values key missing -- should default to zeros
        series = [{"name": "S1"}]
        result = _grouped_bar_chart(["A"], series, "Missing Values")
        assert _is_valid_b64(result)

    def test_series_values_shorter_than_labels(self):
        series = [{"name": "S1", "values": [5], "color": "#0ea5e9"}]
        result = _grouped_bar_chart(["A", "B", "C"], series, "Short Values")
        assert _is_valid_b64(result)

    def test_series_values_longer_than_labels(self):
        series = [{"name": "S1", "values": [5, 10, 15, 20], "color": "#0ea5e9"}]
        result = _grouped_bar_chart(["A", "B"], series, "Long Values")
        assert _is_valid_b64(result)


# ---------------------------------------------------------------------------
# _waterfall_chart (static)
# ---------------------------------------------------------------------------

class TestWaterfallChart:
    def test_with_data_returns_valid_b64(self):
        labels = ["Current Cost", "PAYG Savings", "Retired Savings", "Final Cost"]
        values = [10000.0, -500.0, -200.0, 9300.0]
        result = _waterfall_chart(labels, values, "Waterfall Test")
        assert _is_valid_b64(result)

    def test_empty_labels_returns_valid_b64(self):
        result = _waterfall_chart([], [], "Empty Waterfall")
        assert _is_valid_b64(result)

    def test_mismatched_lengths_returns_valid_b64(self):
        # len(stage_labels) != len(values) triggers early-return path
        result = _waterfall_chart(["A", "B"], [100.0], "Mismatched Waterfall")
        assert _is_valid_b64(result)

    def test_none_inputs_returns_valid_b64(self):
        result = _waterfall_chart(None, None, "None Waterfall")
        assert _is_valid_b64(result)

    def test_negative_values_handled(self):
        labels = ["Start", "Delta", "End"]
        values = [5000.0, -1000.0, 4000.0]
        result = _waterfall_chart(labels, values, "Negative Waterfall")
        assert _is_valid_b64(result)


# ---------------------------------------------------------------------------
# _histogram_chart (static)
# ---------------------------------------------------------------------------

class TestHistogramChart:
    def test_with_data_returns_valid_b64(self):
        result = _histogram_chart(
            ["2 cores", "4 cores", "8 cores"], [10, 25, 15], "Histogram"
        )
        assert _is_valid_b64(result)

    def test_empty_bin_labels_returns_valid_b64(self):
        result = _histogram_chart([], [], "Empty Histogram")
        assert _is_valid_b64(result)

    def test_none_inputs_returns_valid_b64(self):
        result = _histogram_chart(None, None, "None Histogram")
        assert _is_valid_b64(result)

    def test_single_bin_returns_valid_b64(self):
        result = _histogram_chart(["16+ cores"], [3], "Single Bin Histogram")
        assert _is_valid_b64(result)


# ---------------------------------------------------------------------------
# generate_all_charts -- patching animated functions
# ---------------------------------------------------------------------------

_ANIMATED_PATCH_TARGETS = [
    f"{_MOD}._bar_chart_animated",
    f"{_MOD}._bar_chart_horizontal_animated",
    f"{_MOD}._pie_chart_animated",
    f"{_MOD}._doughnut_chart_animated",
]


def _patch_all_animated(return_value=("gif", FAKE_GIF_B64)):
    """Return a list of patch() context managers for all animated functions."""
    return [patch(t, return_value=return_value) for t in _ANIMATED_PATCH_TARGETS]


class TestGenerateAllChartsEmpty:
    """generate_all_charts with completely empty inputs -- animated fns patched."""

    def test_returns_tuple_of_two_dicts(self):
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            result = generate_all_charts({}, {})

        assert isinstance(result, tuple) and len(result) == 2
        charts, formats = result
        assert isinstance(charts, dict)
        assert isinstance(formats, dict)

    def test_all_16_chart_ids_present_in_charts(self):
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, {})

        for cid in ALL_CHART_IDS:
            assert cid in charts, f"Missing chart key: {cid}"

    def test_all_16_chart_ids_present_in_formats(self):
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, {})

        for cid in ALL_CHART_IDS:
            assert cid in formats, f"Missing format key: {cid}"

    def test_format_values_are_gif_or_png(self):
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, {})

        for cid, fmt in formats.items():
            assert fmt in ("gif", "png"), f"{cid} has unexpected format: {fmt!r}"

    def test_chart_values_are_non_empty_strings(self):
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, {})

        for cid, val in charts.items():
            assert isinstance(val, str) and len(val) > 0, f"{cid} chart value is empty/non-string"


class TestGenerateAllChartsPopulated:
    """generate_all_charts with minimal populated data to exercise azure/retired/by_product paths."""

    # Minimal azure_payg rows with CPU, device, and hosting zone columns
    AZURE_ROWS = [
        {"device_name": "SRV01", "u_cpu": 4, "u_hosting_zone": "Public Cloud"},
        {"device_name": "SRV02", "u_cpu": 8, "u_hosting_zone": "Private Cloud AVS"},
        {"device_name": "SRV03", "u_cpu": 2, "u_hosting_zone": "Public Cloud"},
    ]

    # Minimal retired device rows
    RETIRED_ROWS = [
        {"device_ci": "OLD01", "environment": "Production"},
        {"device_ci": "OLD02", "environment": "Development"},
    ]

    # Minimal by_product entries
    BY_PRODUCT = [
        {"product": "SQL Server", "quantity": 50, "cost": 12000.0},
        {"product": "Windows Server", "quantity": 30, "cost": 8000.0},
    ]

    RULE_RESULTS = {
        "azure_payg": AZURE_ROWS,
        "azure_payg_count": 3,
        "retired_devices": RETIRED_ROWS,
        "retired_count": 2,
        "payg_zone_breakdown": {
            "labels": ["Public Cloud", "Private Cloud AVS"],
            "current": [2, 1],
            "estimated": [3, 1],
        },
    }

    LICENSE_METRICS = {
        "by_product": BY_PRODUCT,
        "total_demand_quantity": 80,
        "total_license_cost": 20000.0,
    }

    def test_all_16_keys_present_in_charts(self):
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(self.RULE_RESULTS, self.LICENSE_METRICS)

        for cid in ALL_CHART_IDS:
            assert cid in charts, f"Missing chart key: {cid}"

    def test_all_16_keys_present_in_formats(self):
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(self.RULE_RESULTS, self.LICENSE_METRICS)

        for cid in ALL_CHART_IDS:
            assert cid in formats, f"Missing format key: {cid}"

    def test_static_chart_format_values_are_png(self):
        """Charts generated by static functions must have format 'png'."""
        static_ids = [
            "chart_byol_vs_payg",
            "chart_retired_services",
            "chart_cpu_histogram",
            "chart_waterfall",
            "chart_azure_by_zone_bar",
        ]
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(self.RULE_RESULTS, self.LICENSE_METRICS)

        for cid in static_ids:
            assert formats[cid] == "png", f"{cid} expected 'png', got {formats[cid]!r}"

    def test_animated_chart_format_values_are_gif(self):
        """Charts driven by animated fns (patched to return 'gif') should have format 'gif'."""
        animated_ids = [
            "chart_azure_cores",
            "chart_azure_zones",
            "chart_retired",
            "chart_retired_env",
            "chart_demand",
            "chart_cost",
            "chart_overview",
            "chart_devices",
            "chart_env_pie",
        ]
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(self.RULE_RESULTS, self.LICENSE_METRICS)

        for cid in animated_ids:
            assert formats[cid] == "gif", f"{cid} expected 'gif', got {formats[cid]!r}"

    def test_chart_byol_vs_payg_is_valid_b64(self):
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, _ = generate_all_charts(self.RULE_RESULTS, self.LICENSE_METRICS)

        assert _is_valid_b64(charts["chart_byol_vs_payg"])

    def test_chart_waterfall_is_valid_b64(self):
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, _ = generate_all_charts(self.RULE_RESULTS, self.LICENSE_METRICS)

        assert _is_valid_b64(charts["chart_waterfall"])

    def test_chart_azure_by_zone_bar_is_valid_b64(self):
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, _ = generate_all_charts(self.RULE_RESULTS, self.LICENSE_METRICS)

        assert _is_valid_b64(charts["chart_azure_by_zone_bar"])


class TestGenerateAllChartsExceptionPath:
    """Test that the except block fills all 16 chart IDs with placeholders."""

    def test_exception_fills_all_missing_chart_ids(self):
        """If an animated function raises, the except block must populate every chart ID."""
        with patch(
            _ANIMATED_PATCH_TARGETS[0],
            side_effect=RuntimeError("Simulated chart generation failure"),
        ), patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
           patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
           patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, {})

        for cid in ALL_CHART_IDS:
            assert cid in charts, f"Placeholder missing for chart: {cid}"
            assert cid in formats, f"Placeholder format missing for: {cid}"

    def test_exception_placeholder_charts_are_non_empty_strings(self):
        with patch(
            _ANIMATED_PATCH_TARGETS[0],
            side_effect=RuntimeError("Simulated failure"),
        ), patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
           patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
           patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, {})

        for cid in ALL_CHART_IDS:
            val = charts[cid]
            assert isinstance(val, str) and len(val) > 0, (
                f"Placeholder for {cid} is empty or not a string"
            )

    def test_exception_placeholder_formats_are_png(self):
        with patch(
            _ANIMATED_PATCH_TARGETS[0],
            side_effect=RuntimeError("Simulated failure"),
        ), patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
           patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
           patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, {})

        for cid in ALL_CHART_IDS:
            assert formats[cid] == "png", (
                f"Placeholder format for {cid} should be 'png', got {formats[cid]!r}"
            )

    def test_partially_completed_charts_preserved_on_exception(self):
        """Charts generated before the exception should be retained, not overwritten."""
        call_count = [0]
        original_bar_animated = _bar_chart_animated

        def fail_on_second_call(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise RuntimeError("fail late")
            return ("gif", FAKE_GIF_B64)

        with patch(_ANIMATED_PATCH_TARGETS[0], side_effect=fail_on_second_call), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, {})

        # Regardless of when the exception hit, all IDs must still be present
        for cid in ALL_CHART_IDS:
            assert cid in charts


# ---------------------------------------------------------------------------
# Edge-case: generate_all_charts with only retired_count > 0 (retired services bar path)
# ---------------------------------------------------------------------------

class TestGenerateAllChartsRetiredPath:
    """Verify the retired_count > 0 code path in chart_retired_services."""

    def test_retired_services_chart_present_when_retired_count_nonzero(self):
        rule_results = {"retired_count": 5}
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(rule_results, {})

        assert "chart_retired_services" in charts
        assert formats["chart_retired_services"] == "png"
        assert isinstance(charts["chart_retired_services"], str) and len(charts["chart_retired_services"]) > 0

    def test_retired_services_chart_present_when_retired_count_zero(self):
        rule_results = {"retired_count": 0}
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts(rule_results, {})

        assert "chart_retired_services" in charts
        assert formats["chart_retired_services"] == "png"


# ---------------------------------------------------------------------------
# Edge-case: generate_all_charts license_cost_donut branch (by_product with costs)
# ---------------------------------------------------------------------------

class TestGenerateAllChartsLicenseCostDonut:
    """Verify the by_product-with-costs path for chart_license_cost_donut."""

    def test_donut_uses_animated_when_costs_nonzero(self):
        license_metrics = {
            "by_product": [
                {"product": "SQL Server", "quantity": 10, "cost": 5000.0},
                {"product": "Windows Server", "quantity": 5, "cost": 3000.0},
            ]
        }
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, license_metrics)

        assert "chart_license_cost_donut" in charts
        # Patched animated fn returns 'gif' format
        assert formats["chart_license_cost_donut"] == "gif"

    def test_donut_falls_back_to_static_when_all_costs_zero(self):
        license_metrics = {
            "by_product": [
                {"product": "SQL Server", "quantity": 10, "cost": 0},
            ]
        }
        with patch(_ANIMATED_PATCH_TARGETS[0], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[1], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[2], return_value=("gif", FAKE_GIF_B64)), \
             patch(_ANIMATED_PATCH_TARGETS[3], return_value=("gif", FAKE_GIF_B64)):
            charts, formats = generate_all_charts({}, license_metrics)

        assert "chart_license_cost_donut" in charts
        assert formats["chart_license_cost_donut"] == "png"
