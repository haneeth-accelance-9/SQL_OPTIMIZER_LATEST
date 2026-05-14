"""Unit tests for Plotly chart specs."""
import pytest

from optimizer.services.plotly_charts import (
    get_all_plotly_specs,
    _zone_colors,
    _find_key,
    _layout,
    _layout_pie,
)


def test_zone_colors_public_cloud():
    colors = _zone_colors(["Public Cloud"])
    assert colors[0] == "#00BCFF"


def test_zone_colors_avs():
    colors = _zone_colors(["Private Cloud AVS"])
    assert colors[0] == "#89D329"


def test_zone_colors_private_cloud_non_avs():
    colors = _zone_colors(["Private Cloud"])
    assert colors[0] == "#89D329"


def test_zone_colors_other_uses_palette():
    from optimizer.services.plotly_charts import PALETTE
    colors = _zone_colors(["Unknown Zone"])
    assert colors[0] == PALETTE[0]


def test_zone_colors_empty_returns_empty():
    assert _zone_colors([]) == []


def test_find_key_returns_empty_for_empty_row():
    assert _find_key({}, ["hosting"]) == ""


def test_find_key_returns_empty_for_none():
    assert _find_key(None, ["hosting"]) == ""


def test_find_key_finds_partial_match():
    row = {"u_hosting_zone": "Public Cloud"}
    assert _find_key(row, ["hosting"]) == "u_hosting_zone"


def test_find_key_case_insensitive():
    row = {"CPU_Count": 8}
    assert _find_key(row, ["cpu"]) == "CPU_Count"


def test_find_key_returns_empty_when_no_match():
    row = {"server_name": "srv-01"}
    assert _find_key(row, ["cpu", "core"]) == ""


def test_layout_contains_title():
    out = _layout("My Chart")
    assert "title" in out


def test_layout_overrides_applied():
    out = _layout("Test", showlegend=False)
    assert out["showlegend"] is False


def test_layout_xaxis_merged():
    out = _layout("Test", xaxis={"title": {"text": "X Label"}})
    assert out["xaxis"]["title"]["text"] == "X Label"
    assert "tickfont" in out["xaxis"]


def test_layout_pie_has_pie_margin():
    from optimizer.services.plotly_charts import PIE_MARGIN
    out = _layout_pie("Pie Chart")
    assert out["margin"] == PIE_MARGIN


def test_payg_zone_bar_uses_current_and_estimated_series():
    specs = get_all_plotly_specs(
        {
            "azure_payg_count": 3,
            "retired_count": 0,
            "azure_payg": [],
            "payg_zone_breakdown": {
                "labels": ["Public Cloud", "Private Cloud AVS"],
                "current": [8, 5],
                "estimated": [3, 2],
            },
        },
        {},
    )

    chart = specs["chart_azure_by_zone_bar"]

    assert chart["layout"]["barmode"] == "group"
    assert len(chart["data"]) == 2
    assert chart["data"][0]["name"] == "Current"
    assert chart["data"][0]["x"] == ["Public Cloud", "Private Cloud AVS"]
    assert chart["data"][0]["y"] == [8, 5]
    assert chart["data"][1]["name"] == "Estimated"
    assert chart["data"][1]["y"] == [3, 2]


def _empty_rule_results():
    return {"azure_payg_count": 0, "retired_count": 0, "azure_payg": [], "retired_devices": []}


def test_all_charts_present_for_full_data():
    specs = get_all_plotly_specs(
        {
            "azure_payg_count": 5,
            "retired_count": 3,
            "azure_payg": [
                {"u_hosting_zone": "Public Cloud", "u_cpu_count": 8, "device_name": "srv-1"},
                {"u_hosting_zone": "Private Cloud AVS", "u_cpu_count": 4, "device_name": "srv-2"},
            ],
            "retired_devices": [
                {"environment": "PROD", "server_name": "old-1"},
                {"environment": "DEV", "server_name": "old-2"},
                {"environment": "TEST", "server_name": "old-3"},
            ],
        },
        {
            "total_demand_quantity": 20,
            "total_license_cost": 10000.0,
            "by_product": [
                {"product": "MySQL Standard", "quantity": 10, "cost": 5000.0},
                {"product": "MySQL Enterprise", "quantity": 10, "cost": 5000.0},
            ],
        },
    )
    for chart_id in [
        "chart_azure_cores", "chart_azure_zones", "chart_retired", "chart_retired_env",
        "chart_demand", "chart_cost", "chart_overview", "chart_devices",
        "chart_license_cost_donut", "chart_azure_by_zone_bar", "chart_byol_vs_payg",
        "chart_retired_services", "chart_cpu_histogram", "chart_env_pie",
        "chart_top10_cost", "chart_waterfall",
    ]:
        assert chart_id in specs, f"Missing chart: {chart_id}"


def test_azure_payg_zone_counts_avs_and_public():
    specs = get_all_plotly_specs(
        {
            "azure_payg_count": 2,
            "retired_count": 0,
            "azure_payg": [
                {"u_hosting_zone": "Public Cloud"},
                {"u_hosting_zone": "Private Cloud AVS"},
            ],
        },
        {},
    )
    assert "chart_azure_zones" in specs


def test_retired_count_without_devices_shows_retired_label():
    specs = get_all_plotly_specs(
        {"azure_payg_count": 0, "retired_count": 5, "azure_payg": [], "retired_devices": []},
        {},
    )
    chart = specs["chart_retired_env"]
    assert chart["data"][0]["y"] == ["Retired"]
    assert chart["data"][0]["x"] == [5]


def test_env_colors_dev_prod_test():
    specs = get_all_plotly_specs(
        {
            "azure_payg_count": 0,
            "retired_count": 0,
            "azure_payg": [],
            "retired_devices": [
                {"environment": "PROD", "server_name": "p1"},
                {"environment": "DEV", "server_name": "d1"},
                {"environment": "TEST", "server_name": "t1"},
            ],
        },
        {},
    )
    chart = specs["chart_retired_env"]
    # Three distinct environments → three bars
    assert len(chart["data"][0]["y"]) == 3


def test_cpu_histogram_bins_populated():
    azure_records = [
        {"u_hosting_zone": "Public Cloud", "u_cpu_count": 1},   # ≤2
        {"u_hosting_zone": "Public Cloud", "u_cpu_count": 3},   # ≤4
        {"u_hosting_zone": "Public Cloud", "u_cpu_count": 6},   # ≤8
        {"u_hosting_zone": "Public Cloud", "u_cpu_count": 12},  # ≤16
        {"u_hosting_zone": "Public Cloud", "u_cpu_count": 32},  # 16+
    ]
    specs = get_all_plotly_specs(
        {"azure_payg_count": 5, "retired_count": 0, "azure_payg": azure_records, "retired_devices": []},
        {},
    )
    chart = specs["chart_cpu_histogram"]
    bin_counts = chart["data"][0]["y"]
    assert bin_counts == [1, 1, 1, 1, 1]


def test_exception_in_spec_build_fills_placeholder():
    # Pass a CPU value that can't be converted to float — triggers ValueError inside the try block.
    # The except handler fills all missing chart slots with a placeholder.
    azure_records = [
        {"u_hosting_zone": "Public Cloud", "u_cpu_count": "NOT_A_NUMBER", "device_name": "srv-1"},
    ]
    specs = get_all_plotly_specs(
        {"azure_payg_count": 1, "retired_count": 0,
         "azure_payg": azure_records, "retired_devices": []},
        {},
    )
    # Placeholder fills all chart IDs
    assert "chart_azure_cores" in specs
    assert "chart_waterfall" in specs


def test_no_data_fallback_for_empty_by_product():
    specs = get_all_plotly_specs(_empty_rule_results(), {"total_demand_quantity": 0, "by_product": []})
    chart = specs["chart_demand"]
    assert chart["data"][0]["x"] == ["No data"]


def test_env_pie_no_data_when_all_zones_zero():
    specs = get_all_plotly_specs(
        {"azure_payg_count": 0, "retired_count": 0, "azure_payg": [], "retired_devices": []},
        {"total_demand_quantity": 0},
    )
    chart = specs["chart_env_pie"]
    assert chart["data"][0]["labels"] == ["No data"]
