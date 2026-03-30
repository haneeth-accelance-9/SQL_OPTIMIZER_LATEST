"""Unit tests for analysis service."""
import pytest
import pandas as pd

from optimizer.services.analysis_service import (
    _build_payg_zone_breakdown,
    get_sheet_config,
    build_dashboard_context,
)


def test_get_sheet_config_returns_five_keys():
    config = get_sheet_config()
    assert "installations" in config
    assert "demand" in config
    assert "prices" in config
    assert "optimization" in config
    assert "helpful_reports" in config
    assert all(isinstance(v, str) for v in config.values())


def test_build_dashboard_context_flat_integers():
    context = {
        "rule_results": {"azure_payg_count": 10, "retired_count": 5},
        "license_metrics": {"total_demand_quantity": 100},
    }
    out = build_dashboard_context(context)
    assert out["azure_payg_count"] == 10
    assert out["retired_count"] == 5
    assert out["total_demand_quantity"] == 100
    assert out.get("title") == "Results & Dashboard"


def test_build_dashboard_context_handles_missing():
    context = {"rule_results": {}, "license_metrics": {}}
    out = build_dashboard_context(context)
    assert out["azure_payg_count"] == 0
    assert out["retired_count"] == 0
    assert out["total_demand_quantity"] == 0


def test_build_dashboard_context_exposes_category_savings():
    context = {
        "rule_results": {"azure_payg_count": 10, "retired_count": 5},
        "license_metrics": {
            "total_demand_quantity": 100,
            "total_license_cost": 1000,
        },
    }
    out = build_dashboard_context(context)
    assert out["azure_payg_savings"] == 28.0
    assert out["retired_devices_savings"] == 2.5
    assert out["total_savings"] == 30.5
    assert out["potential_savings"] == 30.5
    assert out["rule_wise_savings"]["azure_payg"] == 28.0
    assert out["rule_wise_savings"]["retired_devices"] == 2.5


def test_build_payg_zone_breakdown_keeps_public_and_avs_only():
    installations_df = pd.DataFrame(
        {
            "u_hosting_zone": [
                "Public Cloud",
                "Private Cloud",
                "Private Cloud AVS",
                "Remote Site",
            ]
        }
    )
    azure_payg_rows = [
        {"u_hosting_zone": "Public Cloud"},
        {"u_hosting_zone": "Private Cloud AVS"},
    ]

    out = _build_payg_zone_breakdown(installations_df, azure_payg_rows)

    assert out["labels"] == ["Public Cloud", "Private Cloud AVS"]
    assert out["current"] == [1, 1]
    assert out["estimated"] == [1, 1]
