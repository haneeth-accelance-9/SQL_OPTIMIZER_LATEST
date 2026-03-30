"""Unit tests for Plotly chart specs."""

from optimizer.services.plotly_charts import get_all_plotly_specs


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
