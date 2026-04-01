"""
Analysis service: run upload pipeline and return result DTO.
Single place for business logic; views handle HTTP only.
"""
import logging
from typing import Any, Dict, Optional

import pandas as pd

from django.conf import settings

from optimizer.services.excel_processor import ExcelProcessor
from optimizer.services.rule_engine import run_rules, compute_license_metrics
from optimizer.services.ai_report_generator import (
    generate_report_text,
    generate_cost_reduction_recommendations,
    get_fallback_report,
)

logger = logging.getLogger(__name__)


def get_sheet_config() -> Dict[str, str]:
    """Single source of truth for sheet names from settings."""
    return {
        "installations": getattr(settings, "EXCEL_SHEET_INSTALLATIONS", "MVP - Data 1 - Installation"),
        "demand": getattr(settings, "EXCEL_SHEET_DEMAND", "MVP - Data 2 - Demand Results"),
        "prices": getattr(settings, "EXCEL_SHEET_PRICES", "MVP - Data 3 - Prices"),
        "optimization": getattr(settings, "EXCEL_SHEET_OPTIMIZATION", "MVP - Data 4 - Optimization potential"),
        "helpful_reports": getattr(settings, "EXCEL_SHEET_HELPFUL_REPORTS", "MVP - Data 5 - Helpful Reports"),
    }


def _calculate_savings(rule_results: Dict[str, Any], license_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate rule-wise, scenario-wise, and total savings.
    """
    azure_payg_count = int(rule_results.get("azure_payg_count", 0) or 0)
    retired_count = int(rule_results.get("retired_count", 0) or 0)
    total_demand_quantity = int(license_metrics.get("total_demand_quantity", 0) or 0)
    total_license_cost = float(license_metrics.get("total_license_cost", 0) or 0)

    if total_demand_quantity <= 0 or total_license_cost <= 0:
        return {
            "rule_wise_savings": {
                "azure_payg": 0.0,
                "retired_devices": 0.0,
            },
            "scenario_wise_savings": {
                "cloud_licensing_optimization": 0.0,
                "inactive_asset_reclamation": 0.0,
            },
            "total_savings": 0.0,
        }

    payg_share = azure_payg_count / total_demand_quantity
    retired_share = retired_count / total_demand_quantity

    azure_payg_savings = round(total_license_cost * payg_share * 0.28, 2)
    retired_devices_savings = round(total_license_cost * retired_share * 0.05, 2)

    scenario_wise_savings = {
        "cloud_licensing_optimization": azure_payg_savings,
        "inactive_asset_reclamation": retired_devices_savings,
    }
    total_savings = round(sum(scenario_wise_savings.values()), 2)

    logger.info(f"Azure PAYG savings: {azure_payg_savings}")
    logger.info(f"Retired devices savings: {retired_devices_savings}")
    logger.info(f"Scenario wise savings: {scenario_wise_savings}")
    logger.info(f"Total savings: {total_savings}")
    return {
        "rule_wise_savings": {
            "azure_payg": azure_payg_savings,
            "retired_devices": retired_devices_savings,
        },
        "scenario_wise_savings": scenario_wise_savings,
        "total_savings": total_savings,
    }


def _normalize_payg_zone_label(zone_value: Any) -> Optional[str]:
    """Normalize hosting zones for PAYG charts: keep only Public Cloud and Private Cloud AVS."""
    normalized = str(zone_value or "").strip().lower()
    if not normalized:
        return None
    if "public" in normalized:
        return "Public Cloud"
    if "avs" in normalized:
        return "Private Cloud AVS"
    return None


def _build_payg_zone_breakdown(
    installations_df: Optional[pd.DataFrame],
    azure_payg_rows: Any,
) -> Dict[str, Any]:
    """Build current vs estimated PAYG counts by hosting zone for the dashboard chart."""
    labels = ["Public Cloud", "Private Cloud AVS"]
    current_counts = {label: 0 for label in labels}
    estimated_counts = {label: 0 for label in labels}

    if isinstance(installations_df, pd.DataFrame) and "u_hosting_zone" in installations_df.columns:
        for zone_value in installations_df["u_hosting_zone"].tolist():
            label = _normalize_payg_zone_label(zone_value)
            if label:
                current_counts[label] += 1

    if isinstance(azure_payg_rows, list):
        zone_key = ""
        for row in azure_payg_rows:
            if not isinstance(row, dict):
                continue
            if not zone_key:
                zone_key = next(
                    (key for key in row.keys() if "hosting" in key.lower() or "zone" in key.lower()),
                    "",
                )
            label = _normalize_payg_zone_label(row.get(zone_key) if zone_key else None)
            if label:
                estimated_counts[label] += 1

    return {
        "labels": labels,
        "current": [int(current_counts[label]) for label in labels],
        "estimated": [int(estimated_counts[label]) for label in labels],
    }


def run_analysis(file_path: str, file_name: str) -> Dict[str, Any]:
    """
    Run full analysis pipeline: load Excel, run rules, compute metrics, generate report.
    Returns dict with keys: success, error, context (or None).
    context is the full render context (rule_results, license_metrics, report_text, etc.) for templates.
    """
    sheets = get_sheet_config()
    processor = ExcelProcessor(
        sheet_installations=sheets["installations"],
        sheet_demand=sheets["demand"],
        sheet_prices=sheets["prices"],
        sheet_optimization=sheets["optimization"],
        sheet_helpful_reports=sheets.get("helpful_reports"),
    )
    data = processor.load_file(file_path)
    if data.get("error"):
        return {"success": False, "error": data["error"], "context": None}

    installations_df = data["installations"]
    demand_df = data.get("demand")
    prices_df = data.get("prices")

    try:
        rule_results = run_rules(installations_df)
    except Exception as e:
        logger.exception("Rule engine failed: %s", e)
        return {"success": False, "error": "Analysis failed (rules). Please check the file format.", "context": None}
    rule_results["payg_zone_breakdown"] = _build_payg_zone_breakdown(
        installations_df,
        rule_results.get("azure_payg") or [],
    )

    try:
        license_metrics = compute_license_metrics(
            demand_df if demand_df is not None else pd.DataFrame(),
            prices_df if prices_df is not None else pd.DataFrame(),
            helpful_reports_df=data.get("helpful_reports"),
        )
    except Exception as e:
        logger.exception("License metrics failed: %s", e)
        return {"success": False, "error": "Analysis failed (metrics). Please check the file format.", "context": None}

    total_devices_analyzed = len(installations_df) if installations_df is not None else 0
    context = {
        "rule_results": rule_results,
        "license_metrics": license_metrics,
        "file_name": file_name,
        "sheet_names_used": data.get("sheet_names_used", {}),
        "total_devices_analyzed": total_devices_analyzed,
    }
    # context.update(_calculate_savings(rule_results, license_metrics))

    savings_data = _calculate_savings(rule_results, license_metrics)
    context.update(savings_data)
    report_text = None
    used_fallback = False
    if getattr(settings, "OPTIMIZER_AI_REPORT_ENABLED", True):
        report_context = {
            "azure_payg_count": rule_results.get("azure_payg_count", 0),
            "retired_count": rule_results.get("retired_count", 0),
            "total_demand_quantity": license_metrics.get("total_demand_quantity", 0),
            "total_license_cost": license_metrics.get("total_license_cost", 0),
            "by_product": license_metrics.get("by_product", []),
            "demand_row_count": license_metrics.get("demand_row_count", 0),
            "scenario_wise_savings": savings_data.get("scenario_wise_savings", {}),
            "total_savings_value": savings_data.get("total_savings", 0),
        }
        report_text = generate_report_text(report_context)
    if not report_text:
        report_text = get_fallback_report({
            "azure_payg_count": rule_results.get("azure_payg_count", 0),
            "retired_count": rule_results.get("retired_count", 0),
            "total_demand_quantity": license_metrics.get("total_demand_quantity", 0),
            "total_license_cost": license_metrics.get("total_license_cost", 0),
            "demand_row_count": license_metrics.get("demand_row_count", 0),
        })
        used_fallback = True
    context["report_text"] = report_text
    context["report_used_fallback"] = used_fallback

    # AI-generated cost reduction and server conversion recommendations (for Dashboard tab)
    if getattr(settings, "OPTIMIZER_AI_REPORT_ENABLED", True):
        ai_recommendations = generate_cost_reduction_recommendations(license_metrics, rule_results)
        context["cost_reduction_ai_recommendations"] = ai_recommendations or ""
    else:
        context["cost_reduction_ai_recommendations"] = ""

    return {"success": True, "error": None, "context": context}


def build_dashboard_context(context: Dict[str, Any], request_id: Optional[str] = None) -> Dict[str, Any]:
    """Build template context with flat integers and optional request_id for logging."""
    out = dict(context)
    rr = context.get("rule_results") or {}
    lm = context.get("license_metrics") or {}
    out["azure_payg_count"] = int(rr.get("azure_payg_count", 0) or 0)
    out["retired_count"] = int(rr.get("retired_count", 0) or 0)
    out["total_demand_quantity"] = int(lm.get("total_demand_quantity", 0) or 0)
    out["total_license_cost"] = lm.get("total_license_cost") or 0
    out["total_devices_analyzed"] = int(context.get("total_devices_analyzed", 0) or 0)
    savings = _calculate_savings(rr, lm)
    out["rule_wise_savings"] = context.get("rule_wise_savings") or savings["rule_wise_savings"]
    out["scenario_wise_savings"] = context.get("scenario_wise_savings") or savings["scenario_wise_savings"]
    out["azure_payg_savings"] = float(out["rule_wise_savings"].get("azure_payg", 0) or 0)
    out["retired_devices_savings"] = float(out["rule_wise_savings"].get("retired_devices", 0) or 0)
    out["total_savings"] = float(context.get("total_savings", savings["total_savings"]) or 0)
    out["potential_savings"] = out["total_savings"]
    out["price_distribution"] = lm.get("price_distribution") or []
    out["cost_reduction_tips"] = lm.get("cost_reduction_tips") or []
    out["cost_reduction_ai_recommendations"] = context.get("cost_reduction_ai_recommendations") or ""
    out.setdefault("title", "Results & Dashboard")
    if request_id:
        out["request_id"] = request_id
    return out
