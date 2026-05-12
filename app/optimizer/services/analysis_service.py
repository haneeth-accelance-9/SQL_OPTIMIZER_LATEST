"""
Analysis service: run upload pipeline and return result DTO.
Single place for business logic; views handle HTTP only.
"""
import contextlib
import contextvars
import logging
import os
import time
from typing import Any, Dict, Optional

import pandas as pd

from django.conf import settings

# Savings multipliers — configurable per environment/tier via .env
PAYG_SAVINGS_MULTIPLIER = float(os.environ.get("PAYG_SAVINGS_MULTIPLIER", "0.28"))
RETIRED_DEVICE_SAVINGS_MULTIPLIER = float(os.environ.get("RETIRED_DEVICE_SAVINGS_MULTIPLIER", "0.05"))

from optimizer.services.rule_engine import run_rules, compute_license_metrics
from optimizer.services.ai_report_generator import (
    generate_report_text,
    generate_cost_reduction_recommendations,
    get_fallback_report,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Pipeline timing
# ─────────────────────────────────────────────────────────────────────────────

# ContextVar so timings accumulate across the synchronous call stack (ingestion
# and rule-eval run inside db_analysis_service; llm-gen runs in ai_report_generator)
# without threading any extra parameters through function signatures.
_pipeline_timings_var: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "pipeline_timings", default=None
)


class PipelineTimer:
    """
    Named-phase stopwatch backed by a ContextVar.

    Phases measured in the same request/thread accumulate automatically:

        timer = PipelineTimer()
        with timer.phase("ingestion"):
            load_data_from_db()
        with timer.phase("rule_eval"):
            run_rules()
        # timer.durations → {"ingestion_sec": 1.23, "rule_eval_sec": 0.45}

    Because durations are stored in a ContextVar, a PipelineTimer created
    anywhere in the call stack sees phases recorded by other PipelineTimer
    instances in the same synchronous execution context.
    """

    def __init__(self) -> None:
        if _pipeline_timings_var.get(None) is None:
            _pipeline_timings_var.set({})

    @contextlib.contextmanager
    def phase(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = round(time.perf_counter() - start, 3)
            timings = _pipeline_timings_var.get({}) or {}
            timings[f"{name}_sec"] = elapsed
            _pipeline_timings_var.set(timings)
            logger.debug("Pipeline phase %s: %.3fs", name, elapsed)

    def record(self, name: str, duration: float) -> None:
        """Directly record a pre-measured duration (seconds) for a named phase."""
        timings = _pipeline_timings_var.get({}) or {}
        timings[f"{name}_sec"] = round(duration, 3)
        _pipeline_timings_var.set(timings)
        logger.debug("Pipeline phase %s: %.3fs", name, duration)

    @property
    def durations(self) -> dict:
        return dict(_pipeline_timings_var.get({}) or {})


def record_run_timings(agent_run_id: str, extra: Optional[dict] = None) -> None:
    """
    Merge phase durations from the ContextVar into AgentRun.input_file_versions.

    ``extra`` allows the caller to supply additional key/value pairs (e.g. a
    phase timed outside the ContextVar scope) that are merged on top.

    Stored structure inside input_file_versions::

        {
            "pipeline_timings": {
                "ingestion_sec": 1.234,
                "rule_eval_sec": 0.567,
                "llm_gen_sec":  12.345
            }
        }
    """
    try:
        from optimizer.models import AgentRun
        run = AgentRun.objects.get(pk=agent_run_id)
        timings = dict(_pipeline_timings_var.get({}) or {})
        if extra:
            timings.update(extra)
        if not timings:
            return
        existing = dict(run.input_file_versions or {})
        existing["pipeline_timings"] = timings
        run.input_file_versions = existing
        run.save(update_fields=["input_file_versions"])
        logger.info("pipeline_timings stored run=%s %s", agent_run_id, timings)
    except Exception as exc:
        logger.warning("record_run_timings failed run=%s: %s", agent_run_id, exc)


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

    azure_payg_savings = round(total_license_cost * payg_share * PAYG_SAVINGS_MULTIPLIER, 2)
    retired_devices_savings = round(total_license_cost * retired_share * RETIRED_DEVICE_SAVINGS_MULTIPLIER, 2)

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
