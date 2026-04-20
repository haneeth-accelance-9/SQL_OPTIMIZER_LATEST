"""Helpers for building the data quality page from the current analysis context."""

from __future__ import annotations

from typing import Any, Dict, List

from optimizer.services.analysis_service import build_dashboard_context


def _status_label(level: str) -> str:
    if level >= "complete":
        return "Complete"
    return level.title()


def _build_row(
    *,
    section: str,
    status: str,
    description: str,
    evidence: List[str],
    recommendation: str,
) -> Dict[str, Any]:
    return {
        "section": section,
        "status": status,
        "status_label": status.title(),
        "description": description,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def _sheet_exists(sheet_names_used: Dict[str, Any], key: str) -> bool:
    return bool((sheet_names_used or {}).get(key))


def build_data_quality_context(context: Dict[str, Any], analysis) -> Dict[str, Any]:
    """Create render context for the data quality page."""
    dashboard = build_dashboard_context(context)
    rule_results = context.get("rule_results") or {}
    license_metrics = context.get("license_metrics") or {}
    sheet_names_used = context.get("sheet_names_used") or {}

    total_devices = int(context.get("total_devices_analyzed", 0) or 0)
    total_demand = int(license_metrics.get("total_demand_quantity", 0) or 0)
    total_cost = float(license_metrics.get("total_license_cost", 0) or 0)
    price_distribution = license_metrics.get("price_distribution") or []
    azure_payg_rows = rule_results.get("azure_payg") or []
    retired_rows = rule_results.get("retired_devices") or []
    ai_recommendations = bool(context.get("cost_reduction_ai_recommendations"))

    installations_ready = _sheet_exists(sheet_names_used, "installations") and total_devices > 0
    demand_ready = _sheet_exists(sheet_names_used, "demand") and total_demand > 0
    prices_ready = _sheet_exists(sheet_names_used, "prices") and total_cost > 0
    optimization_ready = _sheet_exists(sheet_names_used, "optimization")
    helpful_ready = _sheet_exists(sheet_names_used, "helpful_reports")

    rows: List[Dict[str, Any]] = []

    rows.append(
        _build_row(
            section="Installations Dataset",
            status="complete" if installations_ready else "partial" if _sheet_exists(sheet_names_used, "installations") else "insufficient",
            description="Base inventory required for downstream PAYG and retired-device analysis.",
            evidence=[
                f"Sheet detected: {'Yes' if _sheet_exists(sheet_names_used, 'installations') else 'No'}",
                f"Devices analyzed: {total_devices}",
            ],
            recommendation=(
                "Installations sheet is healthy and ready for recommendation generation."
                if installations_ready
                else "Provide a populated Installations sheet with device inventory before relying on recommendation outputs."
            ),
        )
    )

    rows.append(
        _build_row(
            section="Demand Dataset",
            status="complete" if demand_ready else "partial" if _sheet_exists(sheet_names_used, "demand") else "insufficient",
            description="Demand is used to size total SQL license requirements and savings estimates.",
            evidence=[
                f"Sheet detected: {'Yes' if _sheet_exists(sheet_names_used, 'demand') else 'No'}",
                f"Total demand quantity: {total_demand}",
            ],
            recommendation=(
                "Demand data is complete enough for reliable capacity recommendations."
                if demand_ready
                else "Review missing or zero-demand rows. Recommendations can still be shown, but they should be interpreted with caveats."
                if _sheet_exists(sheet_names_used, "demand")
                else "Add the Demand sheet so sizing and cost recommendations can be trusted."
            ),
        )
    )

    rows.append(
        _build_row(
            section="Pricing Dataset",
            status="complete" if prices_ready else "partial" if _sheet_exists(sheet_names_used, "prices") else "insufficient",
            description="Pricing is required for trustworthy cost calculations and potential savings.",
            evidence=[
                f"Sheet detected: {'Yes' if _sheet_exists(sheet_names_used, 'prices') else 'No'}",
                f"Current cost observed: {total_cost:.2f}",
            ],
            recommendation=(
                "Pricing data is complete and cost outputs can be used confidently."
                if prices_ready
                else "Some pricing information appears missing or incomplete. Savings are directional only."
                if _sheet_exists(sheet_names_used, "prices")
                else "Provide the Prices sheet before using savings or cost outputs for decision making."
            ),
        )
    )

    rows.append(
        _build_row(
            section="Optimization Sheet",
            status="complete" if optimization_ready else "partial",
            description="Optimization workbook content supports rightsizing and downstream workbook exports.",
            evidence=[
                f"Sheet detected: {'Yes' if optimization_ready else 'No'}",
                "CPU rightsizing download remains available through the separate workbook flow.",
            ],
            recommendation=(
                "Optimization sheet is available for rightsizing workflows."
                if optimization_ready
                else "Optimization data is missing. Rightsizing outputs may still exist externally, but page-level context should be reviewed."
            ),
        )
    )

    helpful_status = "complete" if helpful_ready and price_distribution else "partial" if helpful_ready or price_distribution else "partial"
    rows.append(
        _build_row(
            section="Helpful Reports Enrichment",
            status=helpful_status,
            description="Optional enrichment that improves edition-level distribution and presentation quality.",
            evidence=[
                f"Helpful Reports sheet detected: {'Yes' if helpful_ready else 'No'}",
                f"Price distribution entries: {len(price_distribution)}",
            ],
            recommendation=(
                "Helpful Reports data is available and enrichment outputs are complete."
                if helpful_status == "complete"
                else "This section is optional, but filling the Helpful Reports sheet will improve edition distribution detail."
            ),
        )
    )

    payg_status = "complete" if installations_ready and demand_ready and prices_ready else "partial" if installations_ready else "insufficient"
    rows.append(
        _build_row(
            section="PAYG Recommendation Readiness",
            status=payg_status,
            description="Evaluates whether BYOL to PAYG recommendations can be generated with confidence.",
            evidence=[
                f"Candidate records available: {len(azure_payg_rows)}",
                f"Installations ready: {'Yes' if installations_ready else 'No'}",
                f"Demand ready: {'Yes' if demand_ready else 'No'}",
                f"Pricing ready: {'Yes' if prices_ready else 'No'}",
            ],
            recommendation=(
                "PAYG recommendations are supported by complete core data."
                if payg_status == "complete"
                else "PAYG recommendations can be shown, but missing demand or pricing reduces reliability."
                if payg_status == "partial"
                else "Critical source data is missing. Do not rely on PAYG recommendations until the installations foundation is restored."
            ),
        )
    )

    retired_status = "complete" if installations_ready and "retired_devices" in rule_results else "partial" if installations_ready else "insufficient"
    rows.append(
        _build_row(
            section="Retired Devices Readiness",
            status=retired_status,
            description="Assesses whether retired-device flags can be produced from the analyzed workbook.",
            evidence=[
                f"Retired-device records available: {len(retired_rows)}",
                f"Installations ready: {'Yes' if installations_ready else 'No'}",
            ],
            recommendation=(
                "Retired-device analysis is supported by the uploaded inventory."
                if retired_status == "complete"
                else "Retired-device signals exist, but verify CMDB completeness before taking action."
                if retired_status == "partial"
                else "Installations data is missing, so retired-device recommendations are not reliable."
            ),
        )
    )

    summary_status = (
        "complete"
        if installations_ready and demand_ready and prices_ready and dashboard.get("potential_savings", 0) >= 0
        else "partial"
        if installations_ready
        else "insufficient"
    )
    rows.append(
        _build_row(
            section="Executive Summary Readiness",
            status=summary_status,
            description="Determines whether the top-line dashboard and report metrics are decision-ready.",
            evidence=[
                f"Potential savings computed: {dashboard.get('potential_savings', 0):.2f}",
                f"AI recommendation available: {'Yes' if ai_recommendations else 'No'}",
                f"Devices / Demand / Cost available: {'Yes' if installations_ready and demand_ready and prices_ready else 'No'}",
            ],
            recommendation=(
                "Executive summary metrics are complete and decision-ready."
                if summary_status == "complete"
                else "Executive summary can be shown, but it should carry caveats because one or more supporting inputs are incomplete."
                if summary_status == "partial"
                else "Critical source data is missing, so the executive summary cannot be considered reliable."
            ),
        )
    )

    status_counts = {
        "complete": sum(1 for row in rows if row["status"] == "complete"),
        "partial": sum(1 for row in rows if row["status"] == "partial"),
        "insufficient": sum(1 for row in rows if row["status"] == "insufficient"),
    }

    render_context = {
        "title": "Data Quality",
        "analysis_source_file_name": context.get("file_name") or getattr(analysis, "file_name", ""),
        "analysis_created_at": analysis.created_at if getattr(analysis, "created_at", None) else None,
        "data_quality_rows": rows,
        "data_quality_counts": status_counts,
        "total_data_quality_sections": len(rows),
    }
    render_context.update(dashboard)
    return render_context
