"""
AI report generator using Azure OpenAI.
Produces a professional optimization report from rule results and license metrics.
"""
import json
import logging
from typing import Any, Dict, Optional

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
    by_product = context.get("by_product", [])[:20]

    prompt = f"""You are an expert IT license and cost optimization analyst. Write a professional, descriptive report in Markdown format (about 1-2 pages) with clear structure and emphasis.

Requirements:
- Use Markdown: # for main title, ## for major sections, ### for subsections. Use **bold** for key terms and important numbers. Use *italic* for emphasis where appropriate.
- Include: Executive Summary (2-3 sentences on current state and main opportunities), Current State (license demand, cost, product mix), Optimization Opportunities (Azure BYOL→PAYG: {azure_count} devices—explain benefits and risks; Retired devices: {retired_count}—explain data quality and decommissioning implications), Risks (data quality, compliance, cost), and Recommendations (3-5 prioritized, actionable steps).
- Be descriptive and professional. Use short paragraphs and bullet points. Do not invent numbers; use only: total demand {total_demand}, total cost {total_cost}, Azure PAYG candidates {azure_count}, retired devices with installations {retired_count}."""

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
        return text
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
            f"total cost {row.get('total_cost', 0):,.2f}, avg price {row.get('avg_price', 0):,.2f}"
        )
    edition_summary = "\n".join(table_lines) if table_lines else "No edition breakdown available."

    prompt = f"""You are an expert SQL Server license and cost optimization analyst. Based on the following data, provide a concise, actionable recommendation report in Markdown.

**License data:**
- Total demand (licenses): {total_demand}
- Total license cost: {total_cost:,.2f}
- Price distribution by edition:
{edition_summary}

**Optimization context:**
- Azure PAYG candidates (devices that could switch from BYOL to Pay-As-You-Go): {azure_count}
- Retired devices still reporting installations (to reconcile): {retired_count}

**Required sections (use Markdown ## and ###):**
1. **How to decrease costs** – 3–5 specific, actionable steps to reduce SQL Server license spend (e.g. move dev/test to Developer, consolidate Enterprise where not needed, leverage PAYG for cloud workloads).
2. **Which servers/workloads to convert to Developer edition** – Identify scenarios (e.g. dev, test, non-production) and estimated impact.
3. **Which servers/workloads to keep or move to Enterprise** – When Enterprise features are justified.
4. **Which servers/workloads to keep or move to Standard** – When Standard is sufficient for production.

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
        return text
    except Exception as e:
        logger.exception("Azure OpenAI cost reduction recommendations failed: %s", e)
        return None


def get_fallback_report(context: Dict[str, Any]) -> str:
    """Generate a static fallback report when AI is not available."""
    azure_count = context.get("azure_payg_count", 0)
    retired_count = context.get("retired_count", 0)
    total_demand = context.get("total_demand_quantity", 0)
    total_cost = context.get("total_license_cost", 0)

    return f"""# SQL Server License Optimization Report

## Executive Summary

This report presents a **detailed analysis** of your SQL Server license posture based on the uploaded dataset. The analysis identifies **{total_demand}** units of license demand and evaluates two critical optimization areas: *Azure BYOL to PAYG migration* and *software installations on retired devices*. Key findings include **{azure_count}** devices eligible for PAYG migration and **{retired_count}** devices with potential data quality or decommissioning issues.

## Current State

- **Total license demand (quantity):** {total_demand}
- **Total estimated license cost:** {total_cost:.2f}
- **Demand records processed:** {context.get('demand_row_count', 0)}

Understanding your *current state* is essential before making optimization decisions. The figures above reflect the aggregated demand and cost from the processed inventory.

## Optimization Opportunities

### 1. Azure BYOL → PAYG

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
4. **Consider** a tagging and approval workflow for BYOL → PAYG changes.
5. **Document** the license assignment and retirement process for audit and governance.

---
*Report generated by SQL License Optimizer. For a more tailored narrative, configure Azure OpenAI.*
"""
