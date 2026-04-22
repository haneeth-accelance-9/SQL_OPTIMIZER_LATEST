"""
AI report generator using Azure OpenAI.
Produces a professional optimization report from rule results and license metrics.
"""
import json
import logging
import os
from typing import Any, Dict, Optional

from optimizer.services.report_export import format_currency, normalize_report_content_text

logger = logging.getLogger(__name__)


_azure_client = None


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
) -> Dict[str, Any]:
    """
    Build a lightweight rules-evaluation payload when the external A2A server is
    unavailable. This keeps AgentRun persistence and candidate creation working.
    """
    per_rule: dict[str, list[dict[str, Any]]] = {}
    summary_rules: list[dict[str, Any]] = []

    rule_specs = [
        {
            "rule_id": "uc_1_1",
            "source_rows": rule_results.get("azure_payg") or [],
            "default_reasons": [
                "Hosted in an Azure-compatible zone and not marked as License Included.",
            ],
            "default_recommendation": "Review Azure BYOL to PAYG migration eligibility.",
            "recommendation_field": None,
        },
        {
            "rule_id": "uc_1_2",
            "source_rows": rule_results.get("retired_devices") or [],
            "default_reasons": [
                "Device appears retired but still reports SQL-related installation data.",
            ],
            "default_recommendation": "Validate retirement status and decommission or reconcile the installation record.",
            "recommendation_field": None,
        },
        {
            "rule_id": "uc_3_1",
            "source_rows": rightsizing.get("cpu_candidates") or [],
            "default_reasons": [
                "CPU utilisation is below the configured rightsizing threshold.",
            ],
            "default_recommendation": "Review CPU rightsizing recommendation.",
            "recommendation_field": "CPU_Recommendation",
        },
        {
            "rule_id": "uc_3_2",
            "source_rows": rightsizing.get("ram_candidates") or [],
            "default_reasons": [
                "Memory headroom is above the configured rightsizing threshold.",
            ],
            "default_recommendation": "Review RAM rightsizing recommendation.",
            "recommendation_field": "RAM_Recommendation",
        },
        {
            "rule_id": "uc_3_3",
            "source_rows": rightsizing.get("crit_cpu_optimizations") or [],
            "default_reasons": [
                "Criticality-aware CPU optimization requires human review before change.",
            ],
            "default_recommendation": "Review criticality-aware CPU recommendation.",
            "recommendation_field": "CPU_Recommendation",
        },
        {
            "rule_id": "uc_3_4",
            "source_rows": rightsizing.get("crit_ram_optimizations") or [],
            "default_reasons": [
                "Criticality-aware RAM optimization requires human review before change.",
            ],
            "default_recommendation": "Review criticality-aware RAM recommendation.",
            "recommendation_field": "RAM_Recommendation",
        },
    ]

    for spec in rule_specs:
        rows, summary = _build_local_rule_rows(**spec)
        per_rule[spec["rule_id"]] = rows
        summary_rules.append(summary)

    matched_counts = {rule_id: len(rows) for rule_id, rows in per_rule.items()}

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
    from optimizer.services.db_analysis_service import compute_db_metrics

    native_context = compute_db_metrics()
    rule_results = native_context.get("rule_results") or {}
    license_metrics = native_context.get("license_metrics") or {}

    rightsizing = dict(native_context.get("rightsizing") or {})
    if isinstance(strategy_results, dict):
        rs_override = strategy_results.get("strategy_3_rightsizing")
        if isinstance(rs_override, dict):
            rightsizing.update(rs_override)

    report_context = {
        "azure_payg_count": rule_results.get("azure_payg_count", 0),
        "retired_count": rule_results.get("retired_count", 0),
        "total_demand_quantity": license_metrics.get("total_demand_quantity", 0),
        "total_license_cost": license_metrics.get("total_license_cost", 0),
        "by_product": license_metrics.get("by_product", []),
        "demand_row_count": license_metrics.get("demand_row_count", 0),
    }

    deterministic_md = get_fallback_report(report_context)
    final_md = deterministic_md
    llm_used = False
    llm_error = None

    if llm_first:
        llm_md = generate_report_text(report_context)
        if llm_md:
            final_md = llm_md
            llm_used = True
        else:
            llm_error = "Local fallback used deterministic report because Azure OpenAI report generation was unavailable."

    rules_evaluation = _build_local_rules_evaluation(
        rule_results=rule_results,
        rightsizing=rightsizing,
    )

    return {
        "success": True,
        "usecase_id": usecase_id,
        "rules_evaluation": rules_evaluation,
        "report_markdown": final_md,
        "llm_used": llm_used,
        "llm_error": llm_error,
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
        # Lazy-load the LicenseRule row (may not exist for every rule id)
        if rule_code not in rule_cache:
            rule_cache[rule_code] = LicenseRule.objects.filter(
                tenant=tenant, rule_code=rule_code
            ).first()
        rule_obj = rule_cache[rule_code]

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
                            "recommendation": recommendation_text[:255] or f"{rule_code} matched",
                            "rationale": rationale_text,
                            "estimated_saving_eur": rule_obj.cost_per_core_pair_eur,
                        },
                    )
                    candidate_rows_created += 1
                except Exception as exc_inner:
                    logger.warning("Failed to create OptimizationCandidate for %s/%s: %s", rule_code, server_name, exc_inner)

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
    azure_count = context.get("azure_payg_count", 0)
    retired_count = context.get("retired_count", 0)
    total_demand = context.get("total_demand_quantity", 0)
    total_cost = context.get("total_license_cost", 0)
    total_cost_display = format_currency(total_cost)

    return normalize_report_content_text(f"""# SQL Server License Optimization Report

## Executive Summary

This report presents a **detailed analysis** of your SQL Server license posture based on the uploaded dataset. The analysis identifies **{total_demand}** units of license demand and evaluates two critical optimization areas: *Azure BYOL to PAYG migration* and *software installations on retired devices*. Key findings include **{azure_count}** devices eligible for PAYG migration and **{retired_count}** devices with potential data quality or decommissioning issues.

## Current State

- **Total license demand (quantity):** {total_demand}
- **Total estimated license cost:** {total_cost_display}
- **Demand records processed:** {context.get('demand_row_count', 0)}

Understanding your *current state* is essential before making optimization decisions. The figures above reflect the aggregated demand and cost from the processed inventory.

## Optimization Opportunities

### 1. Azure BYOL â†’ PAYG

- **Eligible devices:** **{azure_count}**
- These devices are running SQL Server in *Azure* (Public Cloud, Private Cloud AVS, or Private Cloud) and are not on *"License included"*. They represent candidates for switching to **Pay-As-You-Go** licensing, which can simplify billing and reduce upfront commitment.
- **Recommendation:** Review each candidate for *cost* and *compliance*, then plan migration where beneficial. Consider workload patterns and reserved capacity options.

### 2. Software Installations on Retired Devices

- **Affected devices:** **{retired_count}**
- These devices are marked as **retired** in the CMDB but still report software installations through discovery tools. This indicates one or more of: *stale CMDB data*, *incomplete decommissioning*, or *outdated discovery results*. Each scenario carries different implications for accuracy and compliance.
- **Recommendation:** Reconcile CMDB status, complete decommissioning procedures where needed, or refresh discovery data to align with reality.

## Risks

- **Data quality:** Retired devices with active installations suggest possible *CMDB or discovery inaccuracies*, which can affect reporting and audit readiness.
- **Compliance:** Unclear license posture on retired or cloud devices may create **compliance risk** and should be clarified.

## Recommendations

1. **Prioritize** review of Azure PAYG candidates and model cost impact before migrating.
2. **Clean up** retired device records and discovery data to improve accuracy.
3. **Establish** periodic re-runs of this analysis to track improvement over time.
4. **Consider** a tagging and approval workflow for BYOL â†’ PAYG changes.
5. **Document** the license assignment and retirement process for audit and governance.

---
*Report generated by SQL License Optimizer. For a more tailored narrative, configure Azure OpenAI.*
""")
