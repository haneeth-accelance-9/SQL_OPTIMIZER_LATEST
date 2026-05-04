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


def _calculate_savings(
    rule_results: Dict[str, Any],
    license_metrics: Dict[str, Any],
    rightsizing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Calculate rule-wise, scenario-wise, and total savings for all three strategies.

    Strategy 1 – BYOL to PAYG:       total_license_cost × (payg_count / demand_qty) × 0.28
    Strategy 2 – Retired But Reporting: total_license_cost × (retired_count / demand_qty) × 0.05
    Strategy 3 – Rightsizing:          (vcpu_reduction / 2) × avg_cost_per_core_pair_eur
                                       + total_ram_reduction_gib × avg_cost_per_gib_eur
    """
    azure_payg_count = int(rule_results.get("azure_payg_count", 0) or 0)
    retired_count = int(rule_results.get("retired_count", 0) or 0)
    total_demand_quantity = int(license_metrics.get("total_demand_quantity", 0) or 0)
    total_license_cost = float(license_metrics.get("total_license_cost", 0) or 0)

    # Strategy 3 inputs (zero if rightsizing data not provided)
    rs_vcpu_reduction = 0
    rs_avg_cost_per_core_pair = 0.0
    rs_avg_cost_per_gib = 0.0
    rs_cpu_count = 0
    rs_ram_count = 0
    rs_total_ram_reduction_gib = 0.0
    rs_cpu_savings_direct = None
    rs_ram_savings_direct = None
    if rightsizing:
        rs_vcpu_reduction = int(rightsizing.get("total_vcpu_reduction") or 0)
        rs_avg_cost_per_core_pair = float(rightsizing.get("avg_cost_per_core_pair_eur") or 0)
        rs_avg_cost_per_gib = float(rightsizing.get("avg_cost_per_gib_eur") or 0)
        rs_cpu_count = int(rightsizing.get("cpu_count") or 0)
        rs_ram_count = int(rightsizing.get("ram_count") or 0)
        rs_total_ram_reduction_gib = float(rightsizing.get("total_ram_reduction_gib") or 0)
        rs_cpu_savings_direct = rightsizing.get("cpu_savings_eur")
        rs_ram_savings_direct = rightsizing.get("ram_savings_eur")

    # Strategy 3 savings: CPU (core pairs saved × cost per pair) + RAM (GiB freed × cost per GiB)
    if rs_cpu_savings_direct is not None:
        cpu_rightsizing_savings = round(float(rs_cpu_savings_direct or 0), 2)
    else:
        cpu_rightsizing_savings = round((rs_vcpu_reduction / 2) * rs_avg_cost_per_core_pair, 2) if rs_avg_cost_per_core_pair > 0 else 0.0
    if rs_ram_savings_direct is not None:
        ram_rightsizing_savings = round(float(rs_ram_savings_direct or 0), 2)
    else:
        ram_rightsizing_savings = round(rs_total_ram_reduction_gib * rs_avg_cost_per_gib, 2) if rs_avg_cost_per_gib > 0 else 0.0
    rightsizing_savings = round(cpu_rightsizing_savings + ram_rightsizing_savings, 2)

    if total_demand_quantity <= 0 or total_license_cost <= 0:
        return {
            "rule_wise_savings": {
                "azure_payg": 0.0,
                "retired_devices": 0.0,
                "rightsizing": rightsizing_savings,
                "rightsizing_cpu": cpu_rightsizing_savings,
                "rightsizing_ram": ram_rightsizing_savings,
            },
            "scenario_wise_savings": {
                "cloud_licensing_optimization": 0.0,
                "inactive_asset_reclamation": 0.0,
                "workload_rightsizing": rightsizing_savings,
            },
            "rightsizing_meta": {
                "cpu_count": rs_cpu_count,
                "ram_count": rs_ram_count,
                "total_vcpu_reduction": rs_vcpu_reduction,
                "total_ram_reduction_gib": rs_total_ram_reduction_gib,
                "avg_cost_per_core_pair_eur": rs_avg_cost_per_core_pair,
                "avg_cost_per_gib_eur": rs_avg_cost_per_gib,
                "cpu_savings_eur": cpu_rightsizing_savings,
                "ram_savings_eur": ram_rightsizing_savings,
            },
            "total_savings": rightsizing_savings,
        }

    payg_share = azure_payg_count / total_demand_quantity
    retired_share = retired_count / total_demand_quantity

    azure_payg_savings = round(total_license_cost * payg_share * 0.28, 2)
    retired_devices_savings = round(total_license_cost * retired_share * 0.05, 2)

    scenario_wise_savings = {
        "cloud_licensing_optimization": azure_payg_savings,
        "inactive_asset_reclamation": retired_devices_savings,
        "workload_rightsizing": rightsizing_savings,
    }
    total_savings = round(sum(scenario_wise_savings.values()), 2)

    logger.info(f"Azure PAYG savings: {azure_payg_savings}")
    logger.info(f"Retired devices savings: {retired_devices_savings}")
    logger.info(f"Rightsizing savings: {rightsizing_savings} (cpu={cpu_rightsizing_savings}, ram={ram_rightsizing_savings})")
    logger.info(f"Scenario wise savings: {scenario_wise_savings}")
    logger.info(f"Total savings: {total_savings}")
    return {
        "rule_wise_savings": {
            "azure_payg": azure_payg_savings,
            "retired_devices": retired_devices_savings,
            "rightsizing": rightsizing_savings,
            "rightsizing_cpu": cpu_rightsizing_savings,
            "rightsizing_ram": ram_rightsizing_savings,
        },
        "scenario_wise_savings": scenario_wise_savings,
        "rightsizing_meta": {
            "cpu_count": rs_cpu_count,
            "ram_count": rs_ram_count,
            "total_vcpu_reduction": rs_vcpu_reduction,
            "total_ram_reduction_gib": rs_total_ram_reduction_gib,
            "avg_cost_per_core_pair_eur": rs_avg_cost_per_core_pair,
            "avg_cost_per_gib_eur": rs_avg_cost_per_gib,
            "cpu_savings_eur": cpu_rightsizing_savings,
            "ram_savings_eur": ram_rightsizing_savings,
        },
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
    context.update(_calculate_savings(rule_results, license_metrics))

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
    rs_ctx = context.get("rightsizing") or {}
    rightsizing_for_savings = {
        "total_vcpu_reduction": rs_ctx.get("total_vcpu_reduction") or 0,
        "total_ram_reduction_gib": rs_ctx.get("total_ram_reduction_gib") or 0,
        "cpu_count": rs_ctx.get("cpu_count") or 0,
        "ram_count": rs_ctx.get("ram_count") or 0,
        "avg_cost_per_core_pair_eur": rs_ctx.get("avg_cost_per_core_pair_eur") or 0,
        "avg_cost_per_gib_eur": rs_ctx.get("avg_cost_per_gib_eur") or 0,
        "cpu_savings_eur": rs_ctx.get("cpu_savings_eur"),
        "ram_savings_eur": rs_ctx.get("ram_savings_eur"),
    } if rs_ctx else None
    savings = _calculate_savings(rr, lm, rightsizing=rightsizing_for_savings)
    out["rule_wise_savings"] = context.get("rule_wise_savings") or savings["rule_wise_savings"]
    out["scenario_wise_savings"] = context.get("scenario_wise_savings") or savings["scenario_wise_savings"]
    out["rightsizing_meta"] = context.get("rightsizing_meta") or savings.get("rightsizing_meta") or {}
    # Prefer the per-row savings (80% of SUM Actual_Line_Cost) when available
    _payg_savings_from_cost = rr.get("azure_payg_savings_eur")
    out["azure_payg_savings"] = (
        float(_payg_savings_from_cost or 0)
        if _payg_savings_from_cost is not None
        else float(out["rule_wise_savings"].get("azure_payg", 0) or 0)
    )
    # Prefer the per-row SUM(Actual_Line_Cost) for retired devices when available
    _retired_savings_from_cost = rr.get("retired_devices_savings_eur")
    out["retired_devices_savings"] = (
        float(_retired_savings_from_cost or 0)
        if _retired_savings_from_cost is not None
        else float(out["rule_wise_savings"].get("retired_devices", 0) or 0)
    )
    out["rightsizing_savings"] = float(out["rule_wise_savings"].get("rightsizing", 0) or 0)
    out["rightsizing_cpu_savings"] = float(out["rule_wise_savings"].get("rightsizing_cpu", 0) or 0)
    out["rightsizing_ram_savings"] = float(out["rule_wise_savings"].get("rightsizing_ram", 0) or 0)
    out["total_savings"] = float(context.get("total_savings", savings["total_savings"]) or 0)
    # Potential Savings = BYOL to PAYG + Retired but reporting + CPU Estimate Savings
    out["potential_savings"] = round(
        out["azure_payg_savings"] + out["retired_devices_savings"] + out["rightsizing_cpu_savings"],
        2,
    )
    out["price_distribution"] = lm.get("price_distribution") or []
    price_distribution = out["price_distribution"]
    price_total_quantity = sum(int(item.get("quantity", 0) or 0) for item in price_distribution)
    price_total_cost = sum(float(item.get("total_cost", 0) or 0) for item in price_distribution)
    price_type_count = len(price_distribution)
    highest_avg_item = max(
        price_distribution,
        key=lambda item: float(item.get("avg_price", 0) or 0),
        default=None,
    )
    out["price_distribution_summary"] = [
        {
            "label": "License Types",
            "value": price_type_count,
            "subtext": "Active editions",
            "accent": "sky",
        },
        {
            "label": "Total Quantity",
            "value": price_total_quantity,
            "subtext": "Across visible license types",
            "accent": "emerald",
        },
        {
            "label": "Total Cost",
            "value": round(price_total_cost, 2),
            "subtext": "Combined distributed cost",
            "accent": "lime",
            "is_currency": True,
        },
        {
            "label": "Highest Avg Price",
            "value": highest_avg_item.get("avg_price", 0) if highest_avg_item else 0,
            "subtext": (highest_avg_item.get("type", "N/A") + " edition") if highest_avg_item else "No data",
            "accent": "violet",
            "is_currency": True,
        },
    ]
    out["cost_reduction_tips"] = lm.get("cost_reduction_tips") or []
    out["cost_reduction_ai_recommendations"] = context.get("cost_reduction_ai_recommendations") or ""
    out.setdefault("title", "Results & Dashboard")
    if request_id:
        out["request_id"] = request_id
    return out
