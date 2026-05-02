"""
AI report generator using Azure OpenAI.
Produces a professional optimization report from rule results and license metrics.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from optimizer.services.report_export import format_currency, normalize_report_content_text

logger = logging.getLogger(__name__)


_azure_client = None

AGENT_RULES_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "agent"
    / "liscence-optimizer"
    / "configs"
    / "rules.base.yaml"
)

LOCAL_AGENT_RULE_SPECS: list[dict[str, Any]] = [
    {
        "storage_rule_code": "uc_1_1",
        "report_rule_id": "uc_1_1_azure_byol_to_payg",
        "description": "Azure BYOL to PAYG optimization eligibility",
        "rule_type": "filter",
        "source": "rule_results.azure_payg",
        "recommendation_field": None,
        "default_reasons": [
            "Hosted in an Azure-compatible zone and not marked as License Included.",
        ],
        "default_recommendation": "Review Azure BYOL to PAYG migration eligibility.",
    },
    {
        "storage_rule_code": "uc_1_2",
        "report_rule_id": "uc_1_2_retired_device_installs",
        "description": "Software on retired devices",
        "rule_type": "filter",
        "source": "rule_results.retired_devices",
        "recommendation_field": None,
        "default_reasons": [
            "Device appears retired but still reports SQL-related installation data.",
        ],
        "default_recommendation": "Validate retirement status and decommission or reconcile the installation record.",
    },
    {
        "storage_rule_code": "uc_3_1",
        "report_rule_id": "uc_3_1_cpu_rightsizing",
        "description": "CPU rightsizing (PROD vs non-PROD)",
        "rule_type": "recommendation",
        "source": "rightsizing.cpu_candidates",
        "recommendation_field": "CPU_Recommendation",
        "default_reasons": [
            "CPU utilisation is below the configured rightsizing threshold.",
        ],
        "default_recommendation": "Review CPU rightsizing recommendation.",
    },
    {
        "storage_rule_code": "uc_3_2",
        "report_rule_id": "uc_3_2_ram_rightsizing",
        "description": "RAM reduction (PROD vs non-PROD)",
        "rule_type": "recommendation",
        "source": "rightsizing.ram_candidates",
        "recommendation_field": "RAM_Recommendation",
        "default_reasons": [
            "Memory headroom is above the configured rightsizing threshold.",
        ],
        "default_recommendation": "Review RAM rightsizing recommendation.",
    },
    {
        "storage_rule_code": "uc_3_3",
        "report_rule_id": "uc_3_3_criticality_cpu_optimization",
        "description": "Criticality-aware CPU optimization",
        "rule_type": "recommendation",
        "source": "rightsizing.crit_cpu_optimizations",
        "recommendation_field": "CPU_Recommendation",
        "default_reasons": [
            "Criticality-aware CPU optimization requires human review before change.",
        ],
        "default_recommendation": "Review criticality-aware CPU recommendation.",
    },
    {
        "storage_rule_code": "uc_3_4",
        "report_rule_id": "uc_3_4_criticality_ram_optimization",
        "description": "Criticality-aware RAM optimization",
        "rule_type": "recommendation",
        "source": "rightsizing.crit_ram_optimizations",
        "recommendation_field": "RAM_Recommendation",
        "default_reasons": [
            "Criticality-aware RAM optimization requires human review before change.",
        ],
        "default_recommendation": "Review criticality-aware RAM recommendation.",
    },
    {
        "storage_rule_code": "uc_3_5",
        "report_rule_id": "uc_3_5_lifecycle_risk_flags",
        "description": "Lifecycle risk flags for high CPU peaks, low minimum memory, or critical systems",
        "rule_type": "filter",
        "source": "rightsizing.lifecycle_risk_flags",
        "recommendation_field": "Lifecycle_Risk_Reasons",
        "default_reasons": [
            "Lifecycle review is required before automated optimization is attempted.",
        ],
        "default_recommendation": "Review lifecycle risk flags before applying optimization changes.",
    },
    {
        "storage_rule_code": "uc_3_6",
        "report_rule_id": "uc_3_6_physical_system_review",
        "description": "Physical systems require human review before rightsizing",
        "rule_type": "filter",
        "source": "rightsizing.physical_system_flags",
        "recommendation_field": "Review_Reason",
        "default_reasons": [
            "Physical systems should be reviewed manually before rightsizing action is taken.",
        ],
        "default_recommendation": "Route physical systems to human review before changing CPU or RAM allocations.",
    },
]

REPORT_RULE_ID_BY_STORAGE_CODE = {
    spec["storage_rule_code"]: spec["report_rule_id"]
    for spec in LOCAL_AGENT_RULE_SPECS
}
STORAGE_RULE_CODE_BY_REPORT_ID = {
    spec["report_rule_id"]: spec["storage_rule_code"]
    for spec in LOCAL_AGENT_RULE_SPECS
}


def _get_client():
    """Reuse a single Azure OpenAI client (module-level cache)."""
    global _azure_client
    if _azure_client is not None:
        return _azure_client
    try:
        from openai import AzureOpenAI
    except ImportError:
        return None
    from django.conf import settings
    if not getattr(settings, "AZURE_OPENAI_API_KEY", None) or not getattr(settings, "AZURE_OPENAI_ENDPOINT", None):
        return None
    _azure_client = AzureOpenAI(
        api_key=settings.AZURE_OPENAI_API_KEY,
        api_version=getattr(settings, "AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
    )
    return _azure_client


def build_prompt(context: Dict[str, Any]) -> str:
    """Build the prompt for the AI report."""
    azure_count = context.get("azure_payg_count", 0)
    retired_count = context.get("retired_count", 0)
    total_demand = context.get("total_demand_quantity", 0)
    total_cost = context.get("total_license_cost", 0)
    total_cost_display = format_currency(total_cost)
    by_product = context.get("by_product", [])[:20]

    prompt = f"""You are an expert IT license and cost optimization analyst. Write a professional, descriptive report in Markdown format (about 1-2 pages) with clear structure and emphasis.

Requirements:
- Use Markdown: # for main title, ## for major sections, ### for subsections. Use **bold** for key terms and important numbers. Use *italic* for emphasis where appropriate.
- Include: Executive Summary (2-3 sentences on current state and main opportunities), Current State (license demand, cost, product mix), Optimization Opportunities (Azure BYOLâ†’PAYG: {azure_count} devicesâ€”explain benefits and risks; Retired devices: {retired_count}â€”explain data quality and decommissioning implications), Risks (data quality, compliance, cost), and Recommendations (3-5 prioritized, actionable steps).
- Use {format_currency(1)} as the currency format example for every cost, price, savings, or money value.
- Be descriptive and professional. Use short paragraphs and bullet points. Do not invent numbers; use only: total demand {total_demand}, total cost {total_cost_display}, Azure PAYG candidates {azure_count}, retired devices with installations {retired_count}."""

    return prompt


def generate_report_text(context: Dict[str, Any]) -> Optional[str]:
    """
    Call Azure OpenAI to generate report text. Returns None if API is not configured or call fails.
    """
    client = _get_client()
    if not client:
        logger.warning("Azure OpenAI not configured; skipping AI report")
        return None

    from django.conf import settings as _s
    deployment = getattr(_s, "AZURE_OPENAI_DEPLOYMENT", "gpt-4")
    prompt = build_prompt(context)

    try:
        timeout = float(getattr(_s, "AZURE_OPENAI_TIMEOUT", 60))
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": "You write professional IT and license optimization reports. Be concise and factual."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.3,
            timeout=timeout,
        )
        text = response.choices[0].message.content if response.choices else None
        if text and "**" not in text and "##" not in text:
            text = text.replace("Executive Summary", "## Executive Summary").replace("Current State", "## Current State").replace("Recommendations", "## Recommendations")
        return normalize_report_content_text(text) if text else None
    except Exception as e:
        logger.exception("Azure OpenAI report generation failed: %s", e)
        return None


def generate_cost_reduction_recommendations(
    license_metrics: Dict[str, Any],
    rule_results: Dict[str, Any],
) -> Optional[str]:
    """
    Call Azure OpenAI to generate actionable cost-reduction recommendations and
    which servers/workloads to convert to Developer, Enterprise, or Standard.
    Returns markdown string or None if API unavailable or call fails.
    """
    client = _get_client()
    if not client:
        return None

    from django.conf import settings as _s
    deployment = getattr(_s, "AZURE_OPENAI_DEPLOYMENT", "gpt-4")
    timeout = float(getattr(_s, "AZURE_OPENAI_TIMEOUT", 60))

    dist = license_metrics.get("price_distribution") or []
    azure_count = rule_results.get("azure_payg_count", 0) or 0
    retired_count = rule_results.get("retired_count", 0) or 0
    total_demand = license_metrics.get("total_demand_quantity", 0) or 0
    total_cost = license_metrics.get("total_license_cost", 0) or 0

    table_lines = []
    for row in dist:
        table_lines.append(
            f"- **{row.get('type', '')}**: quantity {row.get('quantity', 0)}, "
            f"total cost {format_currency(row.get('total_cost', 0))}, avg price {format_currency(row.get('avg_price', 0))}"
        )
    edition_summary = "\n".join(table_lines) if table_lines else "No edition breakdown available."

    prompt = f"""You are an expert SQL Server license and cost optimization analyst. Based on the following data, provide a concise, actionable recommendation report in Markdown.

**License data:**
- Total demand (licenses): {total_demand}
- Total license cost: {format_currency(total_cost)}
- Price distribution by edition:
{edition_summary}

**Optimization context:**
- Azure PAYG candidates (devices that could switch from BYOL to Pay-As-You-Go): {azure_count}
- Retired devices still reporting installations (to reconcile): {retired_count}

**Required sections (use Markdown ## and ###):**
1. **How to decrease costs** â€“ 3â€“5 specific, actionable steps to reduce SQL Server license spend (e.g. move dev/test to Developer, consolidate Enterprise where not needed, leverage PAYG for cloud workloads).
2. **Which servers/workloads to convert to Developer edition** â€“ Identify scenarios (e.g. dev, test, non-production) and estimated impact.
3. **Which servers/workloads to keep or move to Enterprise** â€“ When Enterprise features are justified.
4. **Which servers/workloads to keep or move to Standard** â€“ When Standard is sufficient for production.

Use only the numbers provided. Be specific and practical. Keep each section to a short paragraph or bullet list."""

    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": "You write concise, actionable IT license optimization recommendations. Use Markdown headings and bullet points."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1500,
            temperature=0.3,
            timeout=timeout,
        )
        text = response.choices[0].message.content if response.choices else None
        return normalize_report_content_text(text) if text else None
    except Exception as e:
        logger.exception("Azure OpenAI cost reduction recommendations failed: %s", e)
        return None


def _normalize_agent_storage_rule_code(rule_code: Any) -> str:
    normalized = str(rule_code or "").strip()
    if not normalized:
        return ""
    if normalized in STORAGE_RULE_CODE_BY_REPORT_ID:
        return STORAGE_RULE_CODE_BY_REPORT_ID[normalized]
    for storage_code in REPORT_RULE_ID_BY_STORAGE_CODE:
        if normalized == storage_code or normalized.startswith(f"{storage_code}_"):
            return storage_code
    return normalized


def _normalize_agent_report_rule_id(rule_code: Any) -> str:
    normalized = str(rule_code or "").strip()
    if not normalized:
        return ""
    if normalized in REPORT_RULE_ID_BY_STORAGE_CODE.values():
        return normalized
    storage_code = _normalize_agent_storage_rule_code(normalized)
    return REPORT_RULE_ID_BY_STORAGE_CODE.get(storage_code, normalized)


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _load_agent_rules_docs() -> list[dict[str, Any]]:
    try:
        import yaml

        if AGENT_RULES_CONFIG_PATH.exists():
            with AGENT_RULES_CONFIG_PATH.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            rules = data.get("rules") if isinstance(data, dict) else None
            if isinstance(rules, list):
                loaded = [rule for rule in rules if isinstance(rule, dict) and rule.get("id")]
                if loaded:
                    return loaded
    except Exception:
        logger.exception("Failed to load agent rules config from %s", AGENT_RULES_CONFIG_PATH)

    return [
        {
            "id": spec["report_rule_id"],
            "type": spec["rule_type"],
            "description": spec["description"],
        }
        for spec in LOCAL_AGENT_RULE_SPECS
    ]


def _load_agent_rules_doc_by_id() -> dict[str, dict[str, Any]]:
    return {
        str(rule.get("id") or "").strip(): rule
        for rule in _load_agent_rules_docs()
        if str(rule.get("id") or "").strip()
    }


def _normalize_strategy_results_payload(strategy_results: Any) -> dict[str, Any]:
    if strategy_results is None:
        return {}
    if isinstance(strategy_results, dict):
        if isinstance(strategy_results.get("strategy_results"), dict):
            return strategy_results["strategy_results"]
        if isinstance(strategy_results.get("result"), dict):
            return strategy_results["result"]
        if isinstance(strategy_results.get("data"), dict):
            return strategy_results["data"]
        return strategy_results
    return {}


def _extract_rules_summary(rules_evaluation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(rules_evaluation, dict):
        return None
    summary = rules_evaluation.get("summary")
    if isinstance(summary, dict) and isinstance(summary.get("rules"), list):
        return summary
    return None


def _extract_evaluation_payload(rules_evaluation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(rules_evaluation, dict):
        return None
    if isinstance(rules_evaluation.get("evaluation"), dict):
        return rules_evaluation["evaluation"]
    if "matched_counts" in rules_evaluation and "per_rule" in rules_evaluation:
        return rules_evaluation
    return None


def _extract_matched_counts(rules_evaluation: dict[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    summary = _extract_rules_summary(rules_evaluation)
    if isinstance(summary, dict):
        for row in summary.get("rules") or []:
            if not isinstance(row, dict):
                continue
            report_rule_id = _normalize_agent_report_rule_id(row.get("id"))
            if report_rule_id:
                counts[report_rule_id] = _safe_int(row.get("matched_count"))
        if counts:
            return counts

    evaluation = _extract_evaluation_payload(rules_evaluation)
    matched_counts = evaluation.get("matched_counts") if isinstance(evaluation, dict) else None
    if isinstance(matched_counts, dict):
        for rule_id, value in matched_counts.items():
            report_rule_id = _normalize_agent_report_rule_id(rule_id)
            if report_rule_id:
                counts[report_rule_id] = _safe_int(value)
    return counts


def _extract_example_hosts(
    rules_evaluation: dict[str, Any] | None,
    *,
    rule_id: str,
    limit: int = 3,
) -> list[str]:
    normalized_rule_id = _normalize_agent_report_rule_id(rule_id)
    if not normalized_rule_id:
        return []

    hosts: list[str] = []
    summary = _extract_rules_summary(rules_evaluation)
    if isinstance(summary, dict):
        for row in summary.get("rules") or []:
            if not isinstance(row, dict):
                continue
            if _normalize_agent_report_rule_id(row.get("id")) != normalized_rule_id:
                continue
            for example in row.get("examples") or []:
                if not isinstance(example, dict):
                    continue
                record = example.get("record") if isinstance(example.get("record"), dict) else {}
                host = str(record.get("hostname") or record.get("server_name") or "").strip()
                if host and host not in hosts:
                    hosts.append(host)
                if len(hosts) >= limit:
                    return hosts

    evaluation = _extract_evaluation_payload(rules_evaluation)
    per_rule = evaluation.get("per_rule") if isinstance(evaluation, dict) else None
    if isinstance(per_rule, dict):
        for key, rows in per_rule.items():
            if _normalize_agent_report_rule_id(key) != normalized_rule_id or not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                result = row.get("result") if isinstance(row.get("result"), dict) else {}
                if not result.get("matched"):
                    continue
                record = row.get("record") if isinstance(row.get("record"), dict) else {}
                host = str(record.get("hostname") or record.get("server_name") or "").strip()
                if host and host not in hosts:
                    hosts.append(host)
                if len(hosts) >= limit:
                    return hosts
    return hosts


def _summarize_expr(expr: Any) -> list[str]:
    if not isinstance(expr, dict):
        return []
    if isinstance(expr.get("all"), list):
        items: list[str] = []
        for sub in expr["all"]:
            items.extend(_summarize_expr(sub))
        return items
    if isinstance(expr.get("any"), list):
        parts: list[str] = []
        for sub in expr["any"]:
            parts.extend(_summarize_expr(sub))
        return [f"Any of: {', '.join(parts)}"] if parts else []

    op = str(expr.get("op") or "").strip()
    col = str(expr.get("col") or "").strip()
    if op == "in_ci":
        values = expr.get("values") if isinstance(expr.get("values"), list) else []
        return [f"`{col}` is one of {values}"]
    if op in {"eq", "eq_ci", "ne_ci", "not_eq_ci", "lt", "lte", "gt", "gte"}:
        return [f"`{col}` {op} `{expr.get('value')}`"]
    return [f"`{col}` {op} ..."] if col else []


def _strategy_sections_for_rule(rule_id: str) -> list[str]:
    normalized = _normalize_agent_report_rule_id(rule_id)
    if normalized.startswith("uc_1_1"):
        return ["strategy_1_azure_byol_payg"]
    if normalized.startswith("uc_1_2"):
        return ["strategy_2_retired_devices"]
    if normalized.startswith("uc_3_"):
        return ["strategy_3_rightsizing"]
    return []


def _collect_host_evidence_from_strategy(strategy_results: dict[str, Any]) -> dict[str, list[str]]:
    evidence: dict[str, list[str]] = {}

    def _add(section: str, line: str) -> None:
        text = str(line or "").strip()
        if not text:
            return
        evidence.setdefault(section, [])
        if text not in evidence[section]:
            evidence[section].append(text)

    for section_key, section_value in (strategy_results or {}).items():
        if not isinstance(section_value, dict):
            continue
        for bucket, rows in section_value.items():
            if not isinstance(rows, list):
                continue
            bucket_key = f"{section_key}.{bucket}"
            for row in rows:
                if not isinstance(row, dict):
                    continue
                host = str(
                    row.get("hostname")
                    or row.get("server_name")
                    or row.get("Server name")
                    or ""
                ).strip()
                recommendation = str(
                    row.get("CPU_Recommendation")
                    or row.get("RAM_Recommendation")
                    or row.get("Lifecycle_Risk_Reasons")
                    or row.get("Review_Reason")
                    or row.get("Recommendation")
                    or row.get("recommendation")
                    or ""
                ).strip()
                if host and recommendation:
                    _add(bucket_key, f"- `{host}`: {recommendation}")
                elif host:
                    _add(bucket_key, f"- `{host}`")
                elif recommendation:
                    _add(bucket_key, f"- {recommendation}")

    for key in list(evidence.keys()):
        evidence[key] = evidence[key][:6]
    return evidence


def build_agent_strategy_results_payload(
    native_context: Dict[str, Any],
    strategy_results_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rule_results = dict(native_context.get("rule_results") or {})
    rightsizing = dict(native_context.get("rightsizing") or {})

    base = {
        "strategy_1_azure_byol_payg": {
            "candidates": rule_results.get("azure_payg") or [],
            "candidate_count": _safe_int(rule_results.get("azure_payg_count")),
            "estimated_savings_eur": _safe_float(native_context.get("azure_payg_savings")),
            "zone_breakdown": rule_results.get("payg_zone_breakdown") or {},
        },
        "strategy_2_retired_devices": {
            "candidates": rule_results.get("retired_devices") or [],
            "candidate_count": _safe_int(rule_results.get("retired_count")),
            "estimated_savings_eur": _safe_float(native_context.get("retired_devices_savings")),
        },
        "strategy_3_rightsizing": {
            "cpu_candidates": rightsizing.get("cpu_optimizations") or rightsizing.get("cpu_candidates") or [],
            "ram_candidates": rightsizing.get("ram_optimizations") or rightsizing.get("ram_candidates") or [],
            "crit_cpu_optimizations": rightsizing.get("crit_cpu_optimizations") or [],
            "crit_ram_optimizations": rightsizing.get("crit_ram_optimizations") or [],
            "lifecycle_risk_flags": rightsizing.get("lifecycle_risk_flags") or [],
            "physical_system_flags": rightsizing.get("physical_system_flags") or [],
            "total_vcpu_reduction": _safe_int(rightsizing.get("total_vcpu_reduction")),
            "total_ram_reduction_gib": round(_safe_float(rightsizing.get("total_ram_reduction_gib")), 1),
            "cpu_candidate_count": _safe_int(rightsizing.get("cpu_count")),
            "ram_candidate_count": _safe_int(rightsizing.get("ram_count")),
            "crit_cpu_count": _safe_int(rightsizing.get("crit_cpu_count")),
            "crit_ram_count": _safe_int(rightsizing.get("crit_ram_count")),
            "lifecycle_count": _safe_int(rightsizing.get("lifecycle_count")),
            "physical_count": _safe_int(rightsizing.get("physical_count")),
            "estimated_savings_eur": _safe_float(
                native_context.get("rightsizing_cpu_savings")
                or (native_context.get("rule_wise_savings") or {}).get("rightsizing_cpu")
                or 0
            ),
        },
    }

    override_payload = _normalize_strategy_results_payload(strategy_results_override)
    if isinstance(override_payload, dict):
        for key, value in override_payload.items():
            if key == "strategy_3_rightsizing" and isinstance(value, dict):
                merged = dict(base.get(key) or {})
                merged.update(value)
                base[key] = merged
            elif isinstance(value, dict):
                merged = dict(base.get(key) or {})
                merged.update(value)
                base[key] = merged
            else:
                base[key] = value
    return base


def _build_agent_report_summary_context(
    native_context: Dict[str, Any],
    strategy_results: Dict[str, Any],
) -> Dict[str, Any]:
    license_metrics = native_context.get("license_metrics") or {}
    s3 = (strategy_results.get("strategy_3_rightsizing") or {}) if isinstance(strategy_results, dict) else {}
    # Use CPU-only savings for Strategy 3 to match the dashboard "CPU Estimate Savings" card
    rightsizing_savings = _safe_float(
        s3.get("estimated_savings_eur")
        or native_context.get("rightsizing_cpu_savings")
        or (native_context.get("rule_wise_savings") or {}).get("rightsizing_cpu")
        or 0
    )
    azure_payg_savings = _safe_float(
        (strategy_results.get("strategy_1_azure_byol_payg") or {}).get("estimated_savings_eur")
        or native_context.get("azure_payg_savings")
        or 0
    )
    retired_devices_savings = _safe_float(
        (strategy_results.get("strategy_2_retired_devices") or {}).get("estimated_savings_eur")
        or native_context.get("retired_devices_savings")
        or 0
    )
    # Use the full combined total from native_context (includes RAM savings) to match the dashboard
    total_savings = _safe_float(native_context.get("total_savings"))
    return {
        "total_demand_quantity": _safe_int(license_metrics.get("total_demand_quantity")),
        "total_license_cost": _safe_float(license_metrics.get("total_license_cost")),
        "azure_payg_count": _safe_int((strategy_results.get("strategy_1_azure_byol_payg") or {}).get("candidate_count")),
        "retired_count": _safe_int((strategy_results.get("strategy_2_retired_devices") or {}).get("candidate_count")),
        "azure_payg_savings": azure_payg_savings,
        "retired_devices_savings": retired_devices_savings,
        "rightsizing_savings": rightsizing_savings,
        "cpu_count": _safe_int(s3.get("cpu_candidate_count")),
        "ram_count": _safe_int(s3.get("ram_candidate_count")),
        "crit_cpu_count": _safe_int(s3.get("crit_cpu_count")),
        "crit_ram_count": _safe_int(s3.get("crit_ram_count")),
        "lifecycle_count": _safe_int(s3.get("lifecycle_count")),
        "physical_count": _safe_int(s3.get("physical_count")),
        "total_vcpu_reduction": _safe_int(s3.get("total_vcpu_reduction")),
        "total_ram_reduction_gib": round(_safe_float(s3.get("total_ram_reduction_gib")), 1),
        "total_savings": total_savings,
    }


def _render_local_agent_report_markdown(
    *,
    usecase_id: str,
    strategy_results: Dict[str, Any],
    rules_evaluation: Dict[str, Any],
    summary_context: Dict[str, Any],
    notes: Optional[str] = None,
) -> str:
    rules_docs = _load_agent_rules_docs()
    rules_meta = {
        str(rule.get("id") or "").strip(): rule
        for rule in rules_docs
        if str(rule.get("id") or "").strip()
    }
    matched_counts = _extract_matched_counts(rules_evaluation)
    strategy_evidence = _collect_host_evidence_from_strategy(strategy_results)
    ordered_rule_ids = [
        str(rule.get("id") or "").strip()
        for rule in rules_docs
        if str(rule.get("id") or "").strip()
    ]

    lines: list[str] = ["# Agent Report", ""]
    lines.extend(["## Executive Summary", ""])
    lines.append(
        f"- Estimated combined opportunity across all three strategies: **{format_currency(summary_context.get('total_savings', 0))}**."
    )
    lines.append(
        f"- **Strategy 1 – Azure BYOL to PAYG**: **{summary_context.get('azure_payg_count', 0)}** candidates,"
        f" estimated saving **{format_currency(summary_context.get('azure_payg_savings', 0))}**."
    )
    lines.append(
        f"- **Strategy 2 – Retired Devices**: **{summary_context.get('retired_count', 0)}** retired-but-reporting devices,"
        f" estimated saving **{format_currency(summary_context.get('retired_devices_savings', 0))}**."
    )
    lines.append(
        f"- **Strategy 3 – CPU/RAM Rightsizing**: **{summary_context.get('cpu_count', 0)}** CPU candidates,"
        f" **{summary_context.get('ram_count', 0)}** RAM candidates,"
        f" **{summary_context.get('total_vcpu_reduction', 0)}** vCPU reduction potential,"
        f" estimated saving **{format_currency(summary_context.get('rightsizing_savings', 0))}**."
    )
    if summary_context.get("crit_cpu_count") or summary_context.get("crit_ram_count"):
        lines.append(
            f"- Criticality-aware flags: **{summary_context.get('crit_cpu_count', 0)}** CPU and **{summary_context.get('crit_ram_count', 0)}** RAM — require human review before change."
        )
    if summary_context.get("lifecycle_count") or summary_context.get("physical_count"):
        lines.append(
            f"- Guardrail review required for **{summary_context.get('lifecycle_count', 0)}** lifecycle-risk and **{summary_context.get('physical_count', 0)}** physical systems before automated changes."
        )
    lines.append("")

    lines.extend(["## Portfolio Snapshot", ""])
    lines.append(f"- **Use case id**: `{usecase_id}`")
    lines.append(f"- **Total demand quantity**: {summary_context.get('total_demand_quantity', 0)}")
    lines.append(f"- **Total license cost**: {format_currency(summary_context.get('total_license_cost', 0))}")
    lines.append(f"- **CPU reduction potential**: {summary_context.get('total_vcpu_reduction', 0)} vCPU")
    lines.append(f"- **RAM reduction potential**: {summary_context.get('total_ram_reduction_gib', 0):.1f} GiB")
    lines.append(f"- **Strategy 1 savings (Azure BYOL→PAYG)**: {format_currency(summary_context.get('azure_payg_savings', 0))}")
    lines.append(f"- **Strategy 2 savings (Retired Devices)**: {format_currency(summary_context.get('retired_devices_savings', 0))}")
    lines.append(f"- **Strategy 3 savings (Rightsizing)**: {format_currency(summary_context.get('rightsizing_savings', 0))}")
    if notes and str(notes).strip():
        lines.append(f"- **Notes**: {str(notes).strip()}")
    lines.append("")

    lines.extend(["## Rule Coverage", ""])
    lines.append("| Rule id | Matched count |")
    lines.append("|---|---:|")
    for rule_id in ordered_rule_ids:
        display_rule_id = rule_id.replace("_", " ").title()
        lines.append(f"| {display_rule_id} | {matched_counts.get(rule_id, 0)} |")
    lines.append("")

    lines.extend(["## Rule Results", ""])
    for rule_id in ordered_rule_ids:
        meta = rules_meta.get(rule_id) or {}
        lines.append(f"### {rule_id.replace('_', ' ').title()}")
        lines.append("")
        if meta.get("description"):
            lines.append(f"- **Purpose**: {meta['description']}")
        if meta.get("type"):
            lines.append(f"- **Rule type**: `{meta['type']}`")

        logic_lines: list[str] = []
        if meta.get("type") == "filter":
            logic_lines = _summarize_expr(meta.get("when"))
        elif meta.get("type") == "recommendation":
            logic_lines = _summarize_expr(meta.get("applies_when"))
            for branch in meta.get("branches") or []:
                if not isinstance(branch, dict):
                    continue
                branch_id = str(branch.get("id") or "").strip()
                branch_lines = _summarize_expr(branch.get("when")) + _summarize_expr(branch.get("candidate_when"))
                if branch_id and branch_lines:
                    logic_lines.append(f"Branch `{branch_id}`:")
                    logic_lines.extend([f"  - {line}" for line in branch_lines])
        if logic_lines:
            lines.append("- **Rule logic (high level)**:")
            for line in logic_lines[:12]:
                lines.append(line if line.startswith("  - ") else f"  - {line}")

        lines.append(f"- **Matched records**: {matched_counts.get(rule_id, 0)}")
        example_hosts = _extract_example_hosts(rules_evaluation, rule_id=rule_id, limit=3)
        if example_hosts:
            lines.append(f"- **Example host(s)**: {', '.join([f'`{host}`' for host in example_hosts])}")

        relevant_evidence: list[str] = []
        for strategy_section in _strategy_sections_for_rule(rule_id):
            for evidence_key, evidence_rows in strategy_evidence.items():
                if evidence_key == strategy_section or evidence_key.startswith(f"{strategy_section}."):
                    relevant_evidence.extend(evidence_rows)
        if relevant_evidence:
            lines.append("- **Evidence / recommendations**:")
            for evidence_line in relevant_evidence[:6]:
                lines.append(f"  {evidence_line}")
        lines.append("")

    lines.extend(["## Recommended Actions", ""])
    lines.append("- Prioritize licensing actions with direct savings impact first: BYOL to PAYG migration and retired-device cleanup.")
    lines.append("- Validate CPU and RAM recommendations against change windows, application owners, and current performance baselines.")
    lines.append("- Route lifecycle-risk and physical-system findings through human review before approving rightsizing changes.")
    lines.append("")

    lines.extend(["## Risks / Caveats", ""])
    lines.append("- Rightsizing recommendations depend on the 12-month utilization rollups and environment classification being accurate.")
    lines.append("- Physical and critical systems should not be changed automatically without owner validation.")
    lines.append("- Savings figures for licensing strategies are proportional estimates based on current demand and rule filters.")
    lines.append("")

    return normalize_report_content_text("\n".join(lines).strip())


def _try_agent_report_tool(
    *,
    usecase_id: str,
    strategy_results: Dict[str, Any],
    rules_evaluation: Dict[str, Any],
    notes: Optional[str] = None,
) -> Optional[str]:
    """
    Try to call the actual agent report_generator tool from agent/liscence-optimizer/src/tools/.
    Imports the tool directly (no HTTP), so it works even when the A2A server is not running.
    Returns the rendered Markdown string on success, or None on any failure.
    """
    import json as _json
    import sys
    from pathlib import Path as _Path

    agent_src = (
        _Path(__file__).resolve().parents[3]
        / "agent" / "liscence-optimizer" / "src"
    )
    str_path = str(agent_src)

    try:
        added = str_path not in sys.path
        if added:
            sys.path.insert(0, str_path)
        try:
            from tools.report_generator import report_generator as _agent_report_gen  # noqa: PLC0415
        finally:
            if added and str_path in sys.path:
                try:
                    sys.path.remove(str_path)
                except ValueError:
                    pass

        result_json = _agent_report_gen(
            usecase_id=usecase_id,
            strategy_results_json=_json.dumps(strategy_results, default=str),
            rules_evaluation_json=_json.dumps(rules_evaluation, default=str),
            notes=notes,
        )
        result = _json.loads(result_json)
        if result.get("success") and result.get("markdown"):
            logger.info(
                "Agent report_generator tool (agent/liscence-optimizer) produced %d chars of markdown.",
                len(result["markdown"]),
            )
            return normalize_report_content_text(str(result["markdown"]))
        logger.warning("Agent report_generator returned success=False or empty markdown: %s", result.get("error"))
    except Exception as exc:
        logger.warning(
            "Direct agent report_generator tool call failed (%s); will use Django-native renderer.",
            exc,
        )
    return None


def build_live_agent_report_preview(
    *,
    usecase_id: str = "uc_1_2_3",
    strategy_results_override: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    from optimizer.services.db_analysis_service import compute_live_db_metrics

    try:
        native_context = compute_live_db_metrics()
    except Exception as exc:
        logger.warning(
            "compute_live_db_metrics() failed in build_live_agent_report_preview (%s); "
            "generating report with empty context.",
            exc,
        )
        native_context = {}

    rule_results = native_context.get("rule_results") or {}
    rightsizing = dict(native_context.get("rightsizing") or {})
    strategy_results = build_agent_strategy_results_payload(
        native_context,
        strategy_results_override=strategy_results_override,
    )

    # Keep rightsizing aligned with any caller-provided overrides before building rule summaries.
    merged_rightsizing = dict(rightsizing)
    merged_rightsizing.update(strategy_results.get("strategy_3_rightsizing") or {})

    # Build authoritative count overrides so the Rule Coverage table matches the
    # filter-funnel / _count fields rather than the length of the candidate lists
    # (which may differ when lists are truncated or computed via a different path).
    _mc_overrides: Dict[str, int] = {}
    _uc1 = _safe_int(rule_results.get("azure_payg_count"))
    if _uc1:
        _mc_overrides["uc_1_1_azure_byol_to_payg"] = _uc1
    _uc2 = _safe_int(rule_results.get("retired_count"))
    if _uc2:
        _mc_overrides["uc_1_2_retired_device_installs"] = _uc2
    _cpu = _safe_int(merged_rightsizing.get("cpu_count") or merged_rightsizing.get("cpu_candidate_count"))
    if _cpu:
        _mc_overrides["uc_3_1_cpu_rightsizing"] = _cpu
    _ram = _safe_int(merged_rightsizing.get("ram_count") or merged_rightsizing.get("ram_candidate_count"))
    if _ram:
        _mc_overrides["uc_3_2_ram_rightsizing"] = _ram
    _crit_cpu = _safe_int(merged_rightsizing.get("crit_cpu_count"))
    if _crit_cpu:
        _mc_overrides["uc_3_3_criticality_cpu_optimization"] = _crit_cpu
    _crit_ram = _safe_int(merged_rightsizing.get("crit_ram_count"))
    if _crit_ram:
        _mc_overrides["uc_3_4_criticality_ram_optimization"] = _crit_ram
    _lc = _safe_int(merged_rightsizing.get("lifecycle_count"))
    if _lc:
        _mc_overrides["uc_3_5_lifecycle_risk_flags"] = _lc
    _phys = _safe_int(merged_rightsizing.get("physical_count"))
    if _phys:
        _mc_overrides["uc_3_6_physical_system_review"] = _phys

    rules_evaluation = _build_local_rules_evaluation(
        rule_results=rule_results,
        rightsizing=merged_rightsizing,
        matched_count_overrides=_mc_overrides,
    )
    summary_context = _build_agent_report_summary_context(native_context, strategy_results)

    # Prefer the actual agent tool (agent/liscence-optimizer/src/tools/report_generator.py)
    # so the report format matches exactly what the A2A server would produce.
    report_markdown = _try_agent_report_tool(
        usecase_id=usecase_id,
        strategy_results=strategy_results,
        rules_evaluation=rules_evaluation,
        notes=notes,
    )
    if not report_markdown:
        # Fall back to Django-native renderer (same content, slightly different heading style)
        logger.info("Using Django-native agent report renderer as fallback.")
        report_markdown = _render_local_agent_report_markdown(
            usecase_id=usecase_id,
            strategy_results=strategy_results,
            rules_evaluation=rules_evaluation,
            summary_context=summary_context,
            notes=notes,
        )

    return {
        "native_context": native_context,
        "strategy_results": strategy_results,
        "rules_evaluation": rules_evaluation,
        "summary_context": summary_context,
        "report_markdown": report_markdown,
    }


def _build_local_rule_rows(
    *,
    rule_id: str,
    source_rows: list,
    default_reasons: list[str],
    default_recommendation: str,
    recommendation_field: Optional[str] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a compact rules-evaluation entry compatible with AgentRun storage."""
    rows: list[dict[str, Any]] = []
    examples: list[dict[str, Any]] = []

    for item in source_rows or []:
        if not isinstance(item, dict):
            continue

        record = dict(item)
        host = str(
            record.get("hostname")
            or record.get("server_name")
            or record.get("Server name")
            or record.get("name")
            or ""
        ).strip()
        if host:
            record.setdefault("hostname", host)
            record.setdefault("server_name", host)

        recommendation_text = ""
        if recommendation_field:
            recommendation_text = str(record.get(recommendation_field) or "").strip()
        if not recommendation_text:
            recommendation_text = default_recommendation

        reasons = [reason for reason in default_reasons if reason]
        if recommendation_text and recommendation_text not in reasons:
            reasons.append(recommendation_text)

        rows.append(
            {
                "record": record,
                "result": {
                    "matched": True,
                    "reasons": reasons,
                    "details": {
                        "engine_result": {
                            "recommendation": {
                                "action": recommendation_text or f"{rule_id} matched",
                                "rationale": recommendation_text or f"{rule_id} matched",
                            }
                        }
                    },
                },
            }
        )

        if host and len(examples) < 3:
            examples.append({"record": {"hostname": host}})

    return rows, {"id": rule_id, "matched_count": len(rows), "examples": examples}


def _build_local_rules_evaluation(
    *,
    rule_results: Dict[str, Any],
    rightsizing: Dict[str, Any],
    matched_count_overrides: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Build a lightweight rules-evaluation payload when the external A2A server is
    unavailable. This keeps AgentRun persistence and candidate creation working.

    matched_count_overrides: map of report_rule_id -> authoritative count. When
    provided, these replace len(rows) so the Rule Coverage table shows the same
    counts as the filter funnel / _count fields in rule_results / rightsizing.
    """
    per_rule: dict[str, list[dict[str, Any]]] = {}
    summary_rules: list[dict[str, Any]] = []
    _overrides = matched_count_overrides or {}

    source_rows_by_path = {
        "rule_results.azure_payg": rule_results.get("azure_payg") or [],
        "rule_results.retired_devices": rule_results.get("retired_devices") or [],
        "rightsizing.cpu_candidates": rightsizing.get("cpu_candidates") or rightsizing.get("cpu_optimizations") or [],
        "rightsizing.ram_candidates": rightsizing.get("ram_candidates") or rightsizing.get("ram_optimizations") or [],
        "rightsizing.crit_cpu_optimizations": rightsizing.get("crit_cpu_optimizations") or [],
        "rightsizing.crit_ram_optimizations": rightsizing.get("crit_ram_optimizations") or [],
        "rightsizing.lifecycle_risk_flags": rightsizing.get("lifecycle_risk_flags") or [],
        "rightsizing.physical_system_flags": rightsizing.get("physical_system_flags") or [],
    }

    for spec in LOCAL_AGENT_RULE_SPECS:
        report_rule_id = spec["report_rule_id"]
        rows, summary = _build_local_rule_rows(
            rule_id=report_rule_id,
            source_rows=source_rows_by_path.get(spec["source"]) or [],
            default_reasons=spec["default_reasons"],
            default_recommendation=spec["default_recommendation"],
            recommendation_field=spec["recommendation_field"],
        )
        per_rule[report_rule_id] = rows
        # Use authoritative count override when available; fall back to list length.
        if report_rule_id in _overrides:
            summary["matched_count"] = _overrides[report_rule_id]
        summary_rules.append(summary)

    matched_counts = {
        rule_id: (_overrides.get(rule_id) if rule_id in _overrides else len(rows))
        for rule_id, rows in per_rule.items()
    }

    return {
        "success": True,
        "evaluation": {
            "matched_counts": matched_counts,
            "per_rule": per_rule,
        },
        "summary": {
            "rules": summary_rules,
        },
    }


def _build_local_agent_report_response(
    *,
    records: list,
    usecase_id: str,
    strategy_results: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
    llm_first: bool = True,
) -> Dict[str, Any]:
    """
    In-process fallback used when the external A2A server is unavailable or
    clearly points back at the local Django dev server.
    """
    preview = build_live_agent_report_preview(
        usecase_id=usecase_id,
        strategy_results_override=strategy_results,
        notes=notes,
    )
    deterministic_md = preview.get("report_markdown") or ""
    rules_evaluation = preview.get("rules_evaluation") or {}

    return {
        "success": True,
        "usecase_id": usecase_id,
        "rules_evaluation": rules_evaluation,
        "report_markdown": deterministic_md,
        "llm_used": False,
        "llm_error": (
            "Django fallback generated a deterministic agent report based on the live DB rules and strategy outputs."
            if llm_first
            else None
        ),
        "llm_meta": None,
        "deterministic_report_markdown": deterministic_md,
        "agent_endpoint_used": "django-native-fallback",
        "notes": notes,
        "records_evaluated": len(records or []),
    }


def call_agent_generate_report(
    records: list,
    usecase_id: str,
    strategy_results: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
    llm_first: bool = True,
) -> Dict[str, Any]:
    """
    Call the liscence-optimizer A2A agent's /generate-report endpoint.

    When the endpoint is left at the local Django dev default (localhost:8000)
    or the A2A server is unavailable, this falls back to an in-process Django
    implementation so `/api/agent-runs/trigger/` still succeeds.

    Returns the full JSON response dict on success, or raises on connection error.
    The response shape mirrors the agent's GenerateReportRequest/response:
      {
        "success": bool,
        "usecase_id": str,
        "rules_evaluation": {...},
        "report_markdown": str,
        "llm_used": bool,
        "llm_error": str | None,
        "llm_meta": {...} | None,
        "deterministic_report_markdown": str,
      }
    """
    import json as _json
    import urllib.request
    from django.conf import settings as _s

    endpoint = getattr(_s, "AGENT_A2A_ENDPOINT", "http://localhost:8000").rstrip("/")
    timeout = getattr(_s, "AGENT_A2A_TIMEOUT", 120)
    url = f"{endpoint}/generate-report"

    default_local_endpoints = {"http://localhost:8000", "http://127.0.0.1:8000"}
    endpoint_explicitly_configured = bool(os.environ.get("AGENT_A2A_ENDPOINT", "").strip())
    if not endpoint_explicitly_configured and endpoint in default_local_endpoints:
        logger.info(
            "AGENT_A2A_ENDPOINT is using the local Django default (%s); using in-process fallback instead of HTTP.",
            endpoint,
        )
        return _build_local_agent_report_response(
            records=records,
            usecase_id=usecase_id,
            strategy_results=strategy_results,
            notes=notes,
            llm_first=llm_first,
        )

    payload = {
        "usecase_id": usecase_id,
        "records": records,
        "strategy_results": strategy_results or {},
        "notes": notes,
        "llm_first": llm_first,
        "llm_max_retries": getattr(_s, "AGENT_A2A_MAX_RETRIES", 2),
        "llm_timeout_seconds": min(timeout, 90),
    }
    body = _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        return _json.loads(raw)
    except Exception as exc:
        logger.warning(
            "A2A agent HTTP call failed for %s (%s). Falling back to in-process report generation.",
            url,
            exc,
        )
        try:
            return _build_local_agent_report_response(
                records=records,
                usecase_id=usecase_id,
                strategy_results=strategy_results,
                notes=notes,
                llm_first=llm_first,
            )
        except Exception:
            logger.exception("In-process report fallback failed after A2A agent error.")
            raise


def generate_and_store_agentic_report(
    records: list,
    usecase_id: str,
    strategy_results: Optional[Dict[str, Any]] = None,
    triggered_by: str = "system",
    tenant=None,
) -> Dict[str, Any]:
    """
    Full pipeline:
      1. Call A2A agent /generate-report
      2. Store results in AgentRun + OptimizationCandidate tables
      3. Return a summary dict

    Falls back gracefully: if the agent is unreachable, an AgentRun row with
    status='failed' is written and the error is returned without raising.
    """
    import time
    import uuid as _uuid
    from django.utils import timezone
    from django.conf import settings as _s

    from optimizer.models import AgentRun, OptimizationCandidate, LicenseRule, Server

    endpoint = getattr(_s, "AGENT_A2A_ENDPOINT", "http://localhost:8000")

    # Resolve tenant — required for TenantAwareModel rows.
    # Callers can pass a Tenant instance; otherwise try the first active tenant.
    if tenant is None:
        from optimizer.models import Tenant
        tenant = Tenant.objects.filter(is_active=True).order_by("created_at").first()

    if tenant is None:
        return {"success": False, "error": "No active tenant found — cannot store AgentRun."}

    run = AgentRun.objects.create(
        tenant=tenant,
        run_label=f"agentic-{usecase_id}-{timezone.now().strftime('%Y%m%d-%H%M%S')}",
        triggered_by=triggered_by,
        status=AgentRun.STATUS_RUNNING,
        agent_endpoint=endpoint,
    )

    started = time.time()
    try:
        result = call_agent_generate_report(
            records=records,
            usecase_id=usecase_id,
            strategy_results=strategy_results,
        )
    except Exception as exc:
        elapsed = time.time() - started
        run.status = AgentRun.STATUS_FAILED
        run.error_detail = str(exc)
        run.run_duration_sec = round(elapsed, 2)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_detail", "run_duration_sec", "finished_at"])
        logger.exception("A2A agent call failed: %s", exc)
        return {"success": False, "error": str(exc), "agent_run_id": str(run.id)}

    elapsed = time.time() - started

    if not result.get("success"):
        run.status = AgentRun.STATUS_FAILED
        run.error_detail = result.get("error") or "Agent returned success=false"
        run.run_duration_sec = round(elapsed, 2)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_detail", "run_duration_sec", "finished_at"])
        return {"success": False, "error": run.error_detail, "agent_run_id": str(run.id)}

    # Extract report + metadata
    report_md = result.get("report_markdown") or result.get("deterministic_report_markdown") or ""
    rules_eval = result.get("rules_evaluation") or {}
    llm_meta = result.get("llm_meta") or {}
    llm_used = bool(result.get("llm_used"))
    llm_model = (llm_meta.get("model") if isinstance(llm_meta, dict) else "") or (
        getattr(_s, "AZURE_OPENAI_DEPLOYMENT", "") if llm_used else ""
    )
    llm_tokens = llm_meta.get("tokens_used")
    run.agent_endpoint = result.get("agent_endpoint_used") or endpoint

    # Build OptimizationCandidate rows from rules_evaluation.per_rule
    per_rule = (rules_eval.get("evaluation") or rules_eval).get("per_rule") or {}
    candidate_rows_created = 0
    rule_cache: Dict[str, Any] = {}

    for rule_code, row_list in per_rule.items():
        if not isinstance(row_list, list):
            continue
        storage_rule_code = _normalize_agent_storage_rule_code(rule_code)
        # Lazy-load the LicenseRule row (may not exist for every rule id)
        if storage_rule_code not in rule_cache:
            rule_cache[storage_rule_code] = LicenseRule.objects.filter(
                tenant=tenant, rule_code=storage_rule_code
            ).first()
        rule_obj = rule_cache[storage_rule_code]

        for row in row_list:
            if not isinstance(row, dict):
                continue
            res = row.get("result") or {}
            if not res.get("matched"):
                continue
            record = row.get("record") or {}
            server_name = record.get("server_name") or record.get("hostname") or ""
            server_obj = None
            if server_name:
                server_obj = Server.objects.filter(
                    tenant=tenant, server_name=server_name
                ).first()

            if rule_obj and server_obj:
                try:
                    details = res.get("details") or {}
                    engine_result = (details.get("engine_result") or {}) if isinstance(details, dict) else {}
                    recommendation_text = ""
                    rec = engine_result.get("recommendation") if isinstance(engine_result, dict) else None
                    if isinstance(rec, dict):
                        recommendation_text = rec.get("rationale") or rec.get("action") or ""
                    rationale = res.get("reasons") or []
                    rationale_text = "; ".join(str(r) for r in rationale) if rationale else recommendation_text

                    OptimizationCandidate.objects.get_or_create(
                        tenant=tenant,
                        agent_run=run,
                        server=server_obj,
                        rule=rule_obj,
                        defaults={
                            "use_case": rule_obj.use_case,
                            "recommendation": recommendation_text[:255] or f"{storage_rule_code} matched",
                            "rationale": rationale_text,
                            "estimated_saving_eur": rule_obj.cost_per_core_pair_eur,
                        },
                    )
                    candidate_rows_created += 1
                except Exception as exc_inner:
                    logger.warning(
                        "Failed to create OptimizationCandidate for %s/%s: %s",
                        storage_rule_code,
                        server_name,
                        exc_inner,
                    )

    run.status = AgentRun.STATUS_COMPLETED
    run.report_markdown = report_md
    run.llm_model = llm_model
    run.llm_used = llm_used
    run.llm_tokens_used = llm_tokens
    run.run_duration_sec = round(elapsed, 2)
    run.servers_evaluated = len(records)
    run.candidates_found = candidate_rows_created
    run.rules_evaluation = rules_eval
    run.finished_at = timezone.now()
    run.save(update_fields=[
        "status", "report_markdown", "llm_model", "llm_used", "llm_tokens_used",
        "run_duration_sec", "servers_evaluated", "candidates_found", "agent_endpoint",
        "rules_evaluation", "finished_at",
    ])

    return {
        "success": True,
        "agent_run_id": str(run.id),
        "report_markdown": report_md,
        "llm_used": llm_used,
        "candidates_created": candidate_rows_created,
        "rules_evaluation": rules_eval,
    }


def get_fallback_report(context: Dict[str, Any]) -> str:
    """Generate a static fallback report when AI is not available."""
    azure_count    = context.get("azure_payg_count", 0)
    retired_count  = context.get("retired_count", 0)
    total_demand   = context.get("total_demand_quantity", 0)
    total_cost     = context.get("total_license_cost", 0)
    total_cost_display = format_currency(total_cost)

    demand_row_count  = context.get("demand_row_count", 0)
    cpu_count         = context.get("cpu_count", 0)
    ram_count         = context.get("ram_count", 0)
    cpu_prod_count    = context.get("cpu_prod_count", 0)
    cpu_nonprod_count = context.get("cpu_nonprod_count", 0)
    ram_prod_count    = context.get("ram_prod_count", 0)
    ram_nonprod_count = context.get("ram_nonprod_count", 0)
    crit_cpu_count    = context.get("crit_cpu_count", 0)
    crit_ram_count    = context.get("crit_ram_count", 0)
    lifecycle_count   = context.get("lifecycle_count", 0)
    physical_count    = context.get("physical_count", 0)

    uc3_section = ""
    if any([cpu_count, ram_count, crit_cpu_count, crit_ram_count, lifecycle_count, physical_count]):
        uc3_section = f"""
### 3. VM Rightsizing (Strategy 3)

#### UC3.1 — CPU Rightsizing
- **Total candidates:** **{cpu_count}** ({cpu_prod_count} PROD, {cpu_nonprod_count} NON-PROD)
- PROD criteria: Avg CPU < 15%, Peak CPU ≤ 70%, vCPU ≥ 4
- NON-PROD criteria: Avg CPU < 25%, Peak CPU ≤ 80%, vCPU ≥ 4

#### UC3.2 — RAM Rightsizing
- **Total candidates:** **{ram_count}** ({ram_prod_count} PROD, {ram_nonprod_count} NON-PROD)
- PROD criteria: Avg FreeMem ≥ 35%, Min FreeMem ≥ 20%, RAM > 8 GiB
- NON-PROD criteria: Avg FreeMem ≥ 30%, Min FreeMem ≥ 15%, RAM > 4 GiB

#### UC3.3 — Critically-Aware CPU Optimisation
- **Total flags:** **{crit_cpu_count}** (human review required before any change)
- Downsize candidates: All Critical systems with Avg CPU < 10%
- Upsize candidates: Bus/Mission Critical systems with Avg CPU > 80%

#### UC3.4 — Critically-Aware RAM Optimisation
- **Total flags:** **{crit_ram_count}** (human review required before any change)
- Downsize candidates: All Critical systems with Avg FreeMem > 80%
- Upsize candidates: Bus/Mission Critical systems with Avg FreeMem < 20%

#### UC3.5 — Lifecycle Risk Flags
- **Systems flagged:** **{lifecycle_count}** — Bus/Mission Critical AND Peak CPU > 95% AND Min FreeMem < 5%
- All flagged systems require **human review** before automated changes proceed.

#### Physical Systems
- **Physical servers identified:** **{physical_count}** — rightsizing requires human approval before execution.
"""

    return normalize_report_content_text(f"""# SQL Server License Optimization Report

## Executive Summary

This report presents a **detailed analysis** of your SQL Server license posture based on live database data. The analysis identifies **{total_demand}** units of license demand and evaluates three optimization strategies: *Azure BYOL to PAYG migration*, *retired device cleanup*, and *VM rightsizing*. Key findings: **{azure_count}** PAYG candidates, **{retired_count}** retired-but-active devices, **{cpu_count}** CPU rightsizing candidates, **{ram_count}** RAM rightsizing candidates, and **{lifecycle_count + physical_count}** systems requiring human review.

## Current State

- **Total license demand (quantity):** {total_demand}
- **Total estimated license cost:** {total_cost_display}
- **Demand records processed:** {demand_row_count}

Understanding your *current state* is essential before making optimization decisions. The figures above reflect the aggregated demand and cost from the live inventory.

## Optimization Opportunities

### 1. Azure BYOL → PAYG (UC1)

- **Eligible devices:** **{azure_count}**
- These devices are running SQL Server in Azure (Public Cloud, Private Cloud AVS, or Private Cloud) and are candidates for switching to **Pay-As-You-Go** licensing.
- **Recommendation:** Review each candidate for cost and compliance, then plan migration where beneficial.

### 2. Software Installations on Retired Devices (UC2)

- **Affected devices:** **{retired_count}**
- These devices are marked as **retired** in the CMDB but still report active software installations, indicating stale CMDB data or incomplete decommissioning.
- **Recommendation:** Reconcile CMDB status and complete decommissioning procedures.
{uc3_section}
## Risks

- **Data quality:** Retired devices with active installations suggest CMDB or discovery inaccuracies.
- **Compliance:** Unclear license posture on retired or cloud devices may create compliance risk.
- **Rightsizing guardrails:** Critical and physical systems must not be changed automatically without owner validation.

## Recommendations

1. **Prioritize** review of Azure PAYG candidates ({azure_count} devices) and model cost impact before migrating.
2. **Clean up** retired device records ({retired_count} devices) and refresh discovery data.
3. **Schedule** CPU and RAM rightsizing ({cpu_count + ram_count} combined candidates) through change windows with application owners.
4. **Route** all {lifecycle_count} lifecycle-risk and {physical_count} physical system flags through human review before any automated action.
5. **Establish** periodic re-runs of this analysis to track improvement over time.

---
*Report generated by SQL License Optimizer. For a more tailored narrative, configure Azure OpenAI.*
""")
