"""
Generate an executive-summary style markdown report from:
- upstream `strategy_results` JSON (from backend / prior phases)
- optional rules evaluation JSON (from `evaluate_optimization_rules`)
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from agenticai.tools import tool_registry


def _json_loads_maybe(payload: str | None) -> Any:
    if payload is None:
        return None
    if isinstance(payload, (dict, list)):
        return payload
    text = str(payload).strip()
    if not text:
        return None
    return json.loads(text)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _default_prompt_path() -> Path:
    return Path(__file__).resolve().parents[2] / "prompts" / "executive_summary.base.md"


def _safe_int(x: Any) -> int | None:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return int(x)
        if isinstance(x, int):
            return x
        if isinstance(x, float):
            return int(x)
        s = str(x).strip()
        if not s:
            return None
        return int(float(s))
    except Exception:
        return None


def _extract_rules_summary(rules_evaluation: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Supports both:
    - {"success": true, "summary": {...}}
    - {"summary": {...}}
    """
    if not isinstance(rules_evaluation, dict):
        return None
    summary = rules_evaluation.get("summary")
    if isinstance(summary, dict) and isinstance(summary.get("rules"), list):
        return summary
    return None


def _extract_evaluation_payload(rules_evaluation: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Normalize common shapes to the raw evaluation payload:
    - {"success": true, "evaluation": {...}, "summary": {...}}
    - {"evaluation": {...}}
    - {"rules_version": ..., "matched_counts": ..., "per_rule": ...}  (already evaluation)
    """
    if not isinstance(rules_evaluation, dict):
        return None

    if isinstance(rules_evaluation.get("evaluation"), dict):
        return rules_evaluation["evaluation"]

    # Sometimes callers pass the evaluation object directly
    if "matched_counts" in rules_evaluation and "per_rule" in rules_evaluation:
        return rules_evaluation

    return None


def _extract_matched_counts(rules_evaluation: dict[str, Any] | None) -> dict[str, int]:
    """
    Best-effort extraction of matched counts by rule id.
    Works even when `summary` is missing.
    """
    counts: dict[str, int] = {}

    # Preferred: from summary
    summary = _extract_rules_summary(rules_evaluation)
    if isinstance(summary, dict) and isinstance(summary.get("rules"), list):
        for r in summary["rules"]:
            if not isinstance(r, dict):
                continue
            rid = str(r.get("id") or "").strip()
            cnt = _safe_int(r.get("matched_count")) or 0
            if rid:
                counts[rid] = cnt
        return counts

    # Fallback: from evaluation.matched_counts
    evaluation = _extract_evaluation_payload(rules_evaluation)
    matched_counts = evaluation.get("matched_counts") if isinstance(evaluation, dict) else None
    if isinstance(matched_counts, dict):
        for rid, cnt in matched_counts.items():
            rid_s = str(rid or "").strip()
            if not rid_s:
                continue
            counts[rid_s] = _safe_int(cnt) or 0
        return counts

    return counts


def _extract_example_hosts(
    rules_evaluation: dict[str, Any] | None,
    *,
    rule_id: str,
    limit: int = 3,
) -> list[str]:
    """
    Pull example hosts for a given rule id from either summary.examples or evaluation.per_rule.
    """
    rid = str(rule_id or "").strip()
    if not rid:
        return []

    # Preferred: summary.examples
    summary = _extract_rules_summary(rules_evaluation)
    rules = (summary or {}).get("rules") if isinstance(summary, dict) else None
    if isinstance(rules, list):
        for r in rules:
            if not isinstance(r, dict):
                continue
            if str(r.get("id") or "").strip() != rid:
                continue
            examples = r.get("examples") if isinstance(r.get("examples"), list) else []
            hosts: list[str] = []
            for ex in examples:
                if not isinstance(ex, dict):
                    continue
                rec = ex.get("record") if isinstance(ex.get("record"), dict) else None
                host = (rec or {}).get("hostname") if isinstance(rec, dict) else None
                if host:
                    hosts.append(str(host))
            # dedupe keep order
            out: list[str] = []
            for h in hosts:
                if h and h not in out:
                    out.append(h)
                if len(out) >= limit:
                    break
            return out

    # Fallback: evaluation.per_rule structure
    evaluation = _extract_evaluation_payload(rules_evaluation)
    per_rule = evaluation.get("per_rule") if isinstance(evaluation, dict) else None
    if isinstance(per_rule, dict) and rid in per_rule and isinstance(per_rule[rid], list):
        out: list[str] = []
        for row in per_rule[rid]:
            if not isinstance(row, dict):
                continue
            res = row.get("result") if isinstance(row.get("result"), dict) else {}
            if not bool((res or {}).get("matched")):
                continue
            rec = row.get("record") if isinstance(row.get("record"), dict) else {}
            host = (rec or {}).get("hostname")
            if host:
                h = str(host)
                if h not in out:
                    out.append(h)
            if len(out) >= limit:
                break
        return out

    return []


def _normalize_strategy_results_payload(strategy_results: Any) -> dict[str, Any]:
    """
    Accept a few common shapes and normalize to a plain dict[str, Any].

    Expected input is already a dict, but some callers may pass:
    - {"success": true, "strategy_results": {...}}
    - {"result": {...}} or {"data": {...}}
    """
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


def _rules_doc_by_id() -> dict[str, dict[str, Any]]:
    """
    Load `configs/rules.base.yaml` and return id -> rule mapping.
    Best-effort: returns {} if rules can't be loaded.
    """
    try:
        # Local import to avoid hard-failing if YAML dependency is missing at runtime.
        from .rules_loader import load_rules_yaml  # type: ignore

        doc = load_rules_yaml()
        rules = doc.get("rules") if isinstance(doc, dict) else None
        if not isinstance(rules, list):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for r in rules:
            if not isinstance(r, dict):
                continue
            rid = str(r.get("id") or "").strip()
            if rid:
                out[rid] = r
        return out
    except Exception:
        return {}


def _friendly_usecase_name(usecase_id: str) -> str:
    """
    Translate technical usecase IDs into user-facing titles.
    This only affects the report text (no business logic).
    """
    raw = str(usecase_id or "").strip()
    if not raw:
        return "Optimization Report"

    normalized = raw.lower().replace("-", "_")
    if normalized in {"uc_1_2_3", "uc_all", "all"}:
        return "SQL License & Infrastructure Optimization (All Strategies)"

    # Fallback for "uc_1_1", "uc_3_2", etc.
    if normalized.startswith("uc_1"):
        return "Cloud Licensing Optimization (Azure BYOL → PAYG, Retired Devices)"
    if normalized.startswith("uc_2"):
        return "Retired Devices & Data Quality Remediation"
    if normalized.startswith("uc_3"):
        return "Workload Right-Sizing (CPU & RAM)"

    return raw


def _friendly_rule_heading(rule_id: str, meta: dict[str, Any] | None) -> str:
    rid = str(rule_id or "").strip()
    desc = (meta or {}).get("description") if isinstance(meta, dict) else None
    desc_s = str(desc or "").strip()
    if desc_s:
        return desc_s

    # For rules present in evaluation but not in rules.base.yaml, provide friendly labels.
    # Never show internal rule IDs in the report output.
    normalized = rid.lower().strip()
    fallback_map = {
        "uc_3_3_criticality_cpu_optimization": "Criticality-aware CPU Optimization (Human Review)",
        "uc_3_4_criticality_ram_optimization": "Criticality-aware RAM Optimization (Human Review)",
        "uc_3_5_lifecycle_risk_flags": "Lifecycle Risk Flags (Human Review)",
        "uc_3_6_physical_system_review": "Physical Systems Require Review",
    }
    if normalized in fallback_map:
        return fallback_map[normalized]

    return "Additional finding"


def _fmt_eur(value: Any) -> str:
    try:
        if value is None:
            return "€0.00"
        x = float(value)
    except Exception:
        return "€0.00"
    return f"€{x:,.2f}"


def _strategy_overview(strategy_results: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract a compact per-strategy overview from the conventional payload shape:
      strategy_1_azure_byol_payg: { candidate_count, estimated_savings_eur, ... }
      strategy_2_retired_devices: { candidate_count, estimated_savings_eur, ... }
      strategy_3_rightsizing:     { cpu_candidate_count, ram_candidate_count, estimated_savings_eur, ... }
    """
    s1 = strategy_results.get("strategy_1_azure_byol_payg") if isinstance(strategy_results, dict) else None
    s2 = strategy_results.get("strategy_2_retired_devices") if isinstance(strategy_results, dict) else None
    s3 = strategy_results.get("strategy_3_rightsizing") if isinstance(strategy_results, dict) else None

    out: list[dict[str, Any]] = []
    if isinstance(s1, dict):
        out.append({
            "name": "Strategy 1 — Azure BYOL → PAYG",
            "candidates": _safe_int(s1.get("candidate_count")) or 0,
            "savings_eur": s1.get("estimated_savings_eur"),
        })
    if isinstance(s2, dict):
        out.append({
            "name": "Strategy 2 — Retired Devices",
            "candidates": _safe_int(s2.get("candidate_count")) or 0,
            "savings_eur": s2.get("estimated_savings_eur"),
        })
    if isinstance(s3, dict):
        out.append({
            "name": "Strategy 3 — Workload Right-Sizing (CPU & RAM)",
            "cpu_candidates": _safe_int(s3.get("cpu_candidate_count")) or 0,
            "ram_candidates": _safe_int(s3.get("ram_candidate_count")) or 0,
            "vcpu_reduction": _safe_int(s3.get("total_vcpu_reduction")) or 0,
            "ram_reduction_gib": s3.get("total_ram_reduction_gib"),
            # Accept multiple possible key names from upstream payloads
            "savings_eur": (
                s3.get("estimated_savings_eur")
                if s3.get("estimated_savings_eur") is not None
                else s3.get("rightsizing_savings_eur")
            ),
        })
    return out


def _recommendations_by_strategy(
    strategy_results: dict[str, Any],
    matched_counts: dict[str, int],
) -> list[str]:
    """
    Descriptive recommendations per strategy + guardrails.
    Uses only provided counts/savings; does not invent new metrics.
    """
    lines: list[str] = []

    # Strategy 1
    s1 = strategy_results.get("strategy_1_azure_byol_payg") if isinstance(strategy_results, dict) else None
    s1_count = _safe_int((s1 or {}).get("candidate_count")) or matched_counts.get("uc_1_1_azure_byol_to_payg", 0)
    s1_savings = (s1 or {}).get("estimated_savings_eur") if isinstance(s1, dict) else None
    if s1_count:
        lines.extend([
            "### Strategy 1 — Azure BYOL → PAYG",
            "",
            f"- **What it means**: **{s1_count}** workload(s) appear eligible to move from BYOL licensing to PAYG based on hosting zone and inventory/licensing flags.",
            "- **Why it matters**: PAYG can simplify governance and reduce operational overhead; cost impact depends on workload profile and existing entitlements.",
            "- **Recommended next steps**:",
            "  - Validate the candidate list with application owners and licensing stakeholders (edition, entitlement, compliance).",
            "  - Prioritize non-PROD first; batch changes by hosting zone and application group.",
            "  - For each candidate, compare PAYG vs BYOL under current agreements (reserved capacity / hybrid benefits / enterprise discounts).",
        ])
        if s1_savings is not None:
            lines.append(f"  - Savings baseline from strategy output: **{_fmt_eur(s1_savings)}**.")
        lines.append("")

    # Strategy 2
    s2 = strategy_results.get("strategy_2_retired_devices") if isinstance(strategy_results, dict) else None
    s2_count = _safe_int((s2 or {}).get("candidate_count")) or matched_counts.get("uc_1_2_retired_device_installs", 0)
    s2_savings = (s2 or {}).get("estimated_savings_eur") if isinstance(s2, dict) else None
    if s2_count:
        lines.extend([
            "### Strategy 2 — Retired Devices (still reporting installs)",
            "",
            f"- **What it means**: **{s2_count}** device(s) are marked retired but still show installation/licensing signals.",
            "- **Why it matters**: this is often a data-quality or decommissioning gap that can inflate demand and introduce audit risk.",
            "- **Recommended next steps**:",
            "  - Reconcile CMDB retirement status vs discovery data; close the loop (decommission, update status, or correct inventory).",
            "  - Only suppress records with an auditable trail (who approved, evidence, timestamp).",
            "  - Add a recurring control: when a device is retired, verify discovery is also retired within an agreed SLA.",
        ])
        if s2_savings is not None:
            lines.append(f"  - Savings baseline from strategy output: **{_fmt_eur(s2_savings)}**.")
        lines.append("")

    # Strategy 3
    s3 = strategy_results.get("strategy_3_rightsizing") if isinstance(strategy_results, dict) else None
    cpu_count = _safe_int((s3 or {}).get("cpu_candidate_count")) or matched_counts.get("uc_3_1_cpu_rightsizing", 0)
    ram_count = _safe_int((s3 or {}).get("ram_candidate_count")) or matched_counts.get("uc_3_2_ram_rightsizing", 0)
    vcpu_red = _safe_int((s3 or {}).get("total_vcpu_reduction")) or 0
    s3_savings = (s3 or {}).get("estimated_savings_eur") if isinstance(s3, dict) else None
    if cpu_count or ram_count:
        lines.extend([
            "### Strategy 3 — Workload Right-Sizing (CPU & RAM)",
            "",
            f"- **What it means**: CPU candidates **{cpu_count}**, RAM candidates **{ram_count}**; potential vCPU reduction **{vcpu_red}**.",
            "- **Why it matters**: right-sizing reduces waste, but must be gated by peaks, business criticality, and change windows.",
            "- **Recommended next steps**:",
            "  - Apply to non-PROD first with monitoring + rollback plans; then stage PROD changes in maintenance windows.",
            "  - Validate the utilization inputs (fractions vs percents) and ensure peaks/minima are not incident-driven artifacts.",
            "  - Confirm application SLOs and owner sign-off before reducing capacity.",
        ])
        if s3_savings is not None:
            lines.append(f"  - Savings baseline from strategy output: **{_fmt_eur(s3_savings)}**.")
        lines.append("")

    # Guardrails if present
    guardrails = [
        ("uc_3_3_criticality_cpu_optimization", "Criticality-aware CPU flags"),
        ("uc_3_4_criticality_ram_optimization", "Criticality-aware RAM flags"),
        ("uc_3_5_lifecycle_risk_flags", "Lifecycle risk flags"),
        ("uc_3_6_physical_system_review", "Physical system review flags"),
    ]
    present = [(rid, label, matched_counts.get(rid, 0)) for rid, label in guardrails if matched_counts.get(rid, 0) > 0]
    if present:
        lines.extend([
            "### Guardrails (Human Review Required)",
            "",
            "- These findings are **not** direct “optimize now” actions — they are controls that require validation before change.",
        ])
        for rid, label, cnt in present:
            _ = rid
            lines.append(f"- **{label}**: **{cnt}** finding(s). Route to human review workflow.")
        lines.append("")

    return lines

_OP_LABELS: dict[str, str] = {
    "eq": "equals",
    "eq_ci": "equals (case-insensitive)",
    "ne_ci": "is not equal to (case-insensitive)",
    "not_eq_ci": "is not equal to (case-insensitive)",
    "in_ci": "is one of (case-insensitive)",
    "lt": "is less than",
    "lte": "is less than or equal to",
    "gt": "is greater than",
    "gte": "is greater than or equal to",
}


def _summarize_expr(expr: Any) -> list[str]:
    """
    Turn the YAML expression DSL into readable bullets.
    """
    if not expr or not isinstance(expr, dict):
        return []

    if "all" in expr and isinstance(expr.get("all"), list):
        items = []
        for sub in expr["all"]:
            items.extend(_summarize_expr(sub))
        return items

    if "any" in expr and isinstance(expr.get("any"), list):
        parts = []
        for sub in expr["any"]:
            parts.extend(_summarize_expr(sub))
        if parts:
            return [f"Any of: {', '.join(parts)}"]
        return []

    op = str(expr.get("op") or "").strip()
    col = str(expr.get("col") or "").strip()

    if op == "in_ci":
        values = expr.get("values") if isinstance(expr.get("values"), list) else []
        return [f"`{col}` {_OP_LABELS.get(op, op)} {values}"]

    if op in {"eq", "eq_ci", "ne_ci", "not_eq_ci", "lt", "lte", "gt", "gte"}:
        value = expr.get("value")
        return [f"`{col}` {_OP_LABELS.get(op, op)} `{value}`"]

    # Unknown op: keep minimal but visible
    return [f"`{col}` {op} ..."]


def _strategy_sections_for_rule(rule_id: str) -> list[str]:
    """
    Heuristic mapping from rule IDs to strategy sections.
    """
    rid = str(rule_id or "").strip()
    if rid.startswith("uc_1_1"):
        return ["strategy_1_azure_byol_payg"]
    if rid.startswith("uc_1_2"):
        return ["strategy_2_retired_devices"]
    if rid.startswith("uc_3_"):
        return ["strategy_3_rightsizing"]
    return []


def _collect_host_evidence_from_strategy(strategy_results: dict[str, Any]) -> dict[str, list[str]]:
    """
    Best-effort extraction of hostnames and recommendation strings from strategy outputs.
    Returns a map of section_key -> list of short evidence lines.
    """
    evidence: dict[str, list[str]] = {}

    def add(section: str, line: str) -> None:
        line = str(line).strip()
        if not line:
            return
        evidence.setdefault(section, [])
        if line not in evidence[section]:
            evidence[section].append(line)

    for k, v in (strategy_results or {}).items():
        if isinstance(v, list):
            for item in v:
                if not isinstance(item, dict):
                    continue
                host = item.get("hostname") or item.get("host") or item.get("HostName")
                comment = item.get("Comments") or item.get("comments")
                if host and comment:
                    add(str(k), f"- `{host}`: {comment}")
                elif host:
                    add(str(k), f"- `{host}`")
                elif comment:
                    add(str(k), f"- {comment}")
        elif isinstance(v, dict):
            for bucket, rows in v.items():
                if not isinstance(rows, list):
                    continue
                section = f"{k}.{bucket}"
                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    host = item.get("hostname") or item.get("host") or item.get("HostName")
                    rec = (
                        item.get("CPU_Recommendation")
                        or item.get("RAM_Recommendation")
                        or item.get("Recommendation")
                        or item.get("Recommended_vCPU")
                        or item.get("Recommended_RAM_GiB")
                    )
                    comment = item.get("Comments") or item.get("comments")
                    if host and rec:
                        add(section, f"- `{host}`: {rec}")
                    elif host and comment:
                        add(section, f"- `{host}`: {comment}")
                    elif host:
                        add(section, f"- `{host}`")
                    elif comment:
                        add(section, f"- {comment}")

    for section in list(evidence.keys()):
        evidence[section] = evidence[section][:5]

    return evidence


def _render_markdown(
    *,
    usecase_id: str,
    strategy_results: dict[str, Any] | None,
    rules_evaluation: dict[str, Any] | None,
    notes: str | None,
    instructions: str,
) -> str:
    # NOTE: `instructions` is intentionally NOT emitted. It exists only for compatibility
    # with older clients that passed a prompt template path.
    _ = instructions

    lines: list[str] = []
    report_title = "IT Optimization Report"
    usecase_title = _friendly_usecase_name(usecase_id)

    # Single top-level title (avoid duplication in downstream renderers)
    lines.append(f"# {report_title}")
    lines.append("")
    lines.append(f"## Use case: {usecase_title}")
    lines.append("")
    lines.append(f"- **Report date**: {date.today().isoformat()}")
    lines.append("")

    rules_meta = _rules_doc_by_id()

    matched_counts_map = _extract_matched_counts(rules_evaluation)

    # Render all rules that exist either in rules.base.yaml OR in the evaluation payload.
    # This ensures criticality/lifecycle/physical rules show up when the evaluator provides them.
    all_rule_ids = sorted({*rules_meta.keys(), *matched_counts_map.keys()})

    matched_counts: list[tuple[str, int]] = []
    for rid in all_rule_ids:
        matched_counts.append((rid, matched_counts_map.get(rid, 0)))
    matched_total = sum(cnt for _, cnt in matched_counts)

    strategy_results = _normalize_strategy_results_payload(strategy_results)
    strategy_evidence = _collect_host_evidence_from_strategy(strategy_results or {})
    strategy_overview = _strategy_overview(strategy_results or {})

    lines.append("## Executive summary")
    lines.append("")
    lines.append(
        "- This report summarises optimization opportunities and guardrails across licensing and right-sizing strategies."
    )
    lines.append(
        "- Counts reflect rule-engine matches; host-level recommendations/evidence reflect upstream strategy outputs when provided."
    )
    if matched_counts_map:
        lines.append(f"- Total rule matches observed: **{matched_total}** record(s) across **{len(matched_counts_map)}** rule(s).")
        top = sorted(
            [(rid, matched_counts_map.get(rid, 0)) for rid in matched_counts_map.keys()],
            key=lambda x: x[1],
            reverse=True,
        )[:3]
        top_named = []
        for rid, cnt in top:
            if cnt <= 0:
                continue
            heading = _friendly_rule_heading(rid, rules_meta.get(rid))
            top_named.append(f"{heading}: **{cnt}**")
        if top_named:
            lines.append(f"- Highest-volume findings: {', '.join(top_named)}.")
    lines.append("")

    lines.append("## Portfolio snapshot")
    lines.append("")
    if strategy_overview:
        # First: show strategy-level KPIs when provided.
        total_savings = 0.0
        for row in strategy_overview:
            try:
                total_savings += float(row.get("savings_eur") or 0)
            except Exception:
                pass
        if total_savings:
            lines.append(f"- **Estimated combined opportunity (strategies 1–3)**: **{_fmt_eur(total_savings)}**")
        for row in strategy_overview:
            name = row.get("name") or "Strategy"
            if "cpu_candidates" in row:
                lines.append(
                    f"- **{name}**: **{row.get('cpu_candidates', 0)}** CPU candidate(s), "
                    f"**{row.get('ram_candidates', 0)}** RAM candidate(s), "
                    f"**{row.get('vcpu_reduction', 0)}** vCPU reduction potential, "
                    f"estimated saving **{_fmt_eur(row.get('savings_eur'))}**."
                )
            else:
                lines.append(
                    f"- **{name}**: **{row.get('candidates', 0)}** candidate(s), "
                    f"estimated saving **{_fmt_eur(row.get('savings_eur'))}**."
                )
        lines.append("")

    rules_hit = sum(1 for _, cnt in matched_counts if cnt > 0)
    lines.append(f"- **Rules matched**: {rules_hit} rule(s); **total matches**: {matched_total} record(s)")
    if strategy_results:
        lines.append(f"- **Strategy outputs present**: {len(strategy_results)} section(s)")
    else:
        lines.append("- **Strategy outputs present**: none")
    # Best-effort footprint: unique hosts across strategy outputs
    if strategy_evidence:
        host_set: set[str] = set()
        for lines_list in strategy_evidence.values():
            for ln in lines_list:
                # simple extraction: backticked hostname
                if "`" in ln:
                    parts = ln.split("`")
                    if len(parts) >= 3:
                        host_set.add(parts[1])
        if host_set:
            lines.append(f"- **Hosts referenced in strategy outputs**: {len(host_set)}")
    if notes and str(notes).strip():
        lines.append(f"- **Notes**: {str(notes).strip()}")
    lines.append("")

    lines.append("## Rule coverage")
    lines.append("")
    if matched_counts:
        lines.append("| Rule | Matched count |")
        lines.append("|---|---:|")
        for rid, cnt in sorted(matched_counts, key=lambda x: x[0]):
            lines.append(f"| {_friendly_rule_heading(rid, rules_meta.get(rid))} | {cnt} |")
    else:
        lines.append("- Rule evaluation summary was not available; matched counts cannot be presented.")
    lines.append("")

    lines.append("## Rule results")
    lines.append("")
    # Render one section per known rule (YAML + evaluation payload ids)
    for rid in all_rule_ids:
        meta = rules_meta.get(rid, {})
        desc = meta.get("description") if isinstance(meta, dict) else None
        rtype = meta.get("type") if isinstance(meta, dict) else None
        cnt = matched_counts_map.get(rid, 0)

        lines.append(f"### {_friendly_rule_heading(rid, meta)}")
        lines.append("")
        if desc:
            lines.append(f"- **Purpose**: {desc}")
        if rtype:
            lines.append(f"- **Rule type**: `{rtype}`")

        logic_lines: list[str] = []
        if isinstance(meta, dict):
            if meta.get("type") == "filter":
                logic_lines = _summarize_expr(meta.get("when"))
            elif meta.get("type") == "recommendation":
                logic_lines = _summarize_expr(meta.get("applies_when"))
                branches = meta.get("branches") if isinstance(meta.get("branches"), list) else []
                for b in branches:
                    if not isinstance(b, dict):
                        continue
                    bid = str(b.get("id") or "").strip()
                    bw = _summarize_expr(b.get("when"))
                    bc = _summarize_expr(b.get("candidate_when"))
                    if bid and (bw or bc):
                        logic_lines.append(f"Branch `{bid}`:")
                        logic_lines.extend([f"  - {x}" for x in (bw + bc)])

        if logic_lines:
            lines.append("- **Rule logic (high level)**:")
            for ll in logic_lines[:12]:
                if ll.startswith("  - "):
                    lines.append(ll)
                elif ll.endswith(":") and ll.startswith("Branch "):
                    lines.append(f"  - {ll}")
                else:
                    lines.append(f"  - {ll}")

        lines.append(f"- **Matched records**: **{cnt}**")

        ex_hosts = _extract_example_hosts(rules_evaluation, rule_id=rid, limit=3)
        if ex_hosts:
            lines.append(
                f"- **Example host(s)**: {', '.join([f'`{h}`' for h in ex_hosts])}"
            )

        strategy_sections = _strategy_sections_for_rule(rid)
        if strategy_sections:
            relevant: list[str] = []
            for sec in strategy_sections:
                for k in sorted(strategy_evidence.keys()):
                    if k == sec or k.startswith(sec + "."):
                        relevant.extend(strategy_evidence.get(k) or [])
            relevant = relevant[:6]
            if relevant:
                lines.append("- **Evidence / recommendations (strategy outputs)**:")
                for ev in relevant:
                    lines.append(f"  {ev}")
        lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    rec_lines = _recommendations_by_strategy(strategy_results or {}, matched_counts_map)
    if rec_lines:
        lines.extend(rec_lines)
    else:
        lines.append("- Provide strategy outputs to generate tailored recommendations per use case.")
        lines.append("")

    if strategy_evidence:
        lines.append("## Evidence from strategy outputs")
        lines.append("")
        for section in sorted(strategy_evidence.keys()):
            lines.append(f"### `{section}`")
            lines.append("")
            for ev in strategy_evidence[section]:
                lines.append(ev)
            lines.append("")

    lines.append("## Risks / caveats")
    lines.append("")
    lines.append("- Metrics may be represented as **fractions vs percents** depending on upstream normalization; confirm consistency before decisions.")
    lines.append("- Environment classification (PROD vs non-PROD) changes thresholds; confirm the `environment` field is accurate.")
    if not matched_counts_map:
        lines.append("- Rule evaluation payload was missing or incomplete; matched counts may be understated.")
    lines.append("")

    return "\n".join(lines).strip() + "\n"


@tool_registry.register(
    name="report_generator",
    description=(
        "Generate an executive-summary markdown scaffold from `strategy_results` JSON and optional "
        "`rules_evaluation` JSON. Uses `prompts/executive_summary.base.md` as the instruction template."
    ),
    tags=["report", "executive-summary", "markdown"],
    requires_context=False,
)
def report_generator(
    usecase_id: str,
    strategy_results_json: str,
    rules_evaluation_json: str | None = None,
    notes: str | None = None,
    prompt_path: str | None = None,
) -> str:
    try:
        strategy_results_raw = _json_loads_maybe(strategy_results_json)
        strategy_results = _normalize_strategy_results_payload(strategy_results_raw)
        if not isinstance(strategy_results, dict):
            return json.dumps(
                {
                    "success": False,
                    "error": "strategy_results_json must be a JSON object",
                },
                indent=2,
            )

        rules_evaluation = _json_loads_maybe(rules_evaluation_json) if rules_evaluation_json else None
        if rules_evaluation is not None and not isinstance(rules_evaluation, dict):
            return json.dumps(
                {
                    "success": False,
                    "error": "rules_evaluation_json must be a JSON object (or empty)",
                },
                indent=2,
            )

        p = Path(prompt_path) if prompt_path else _default_prompt_path()
        instructions = _read_text(p)

        markdown = _render_markdown(
            usecase_id=usecase_id,
            strategy_results=strategy_results,
            rules_evaluation=rules_evaluation,
            notes=notes,
            instructions=instructions,
        )

        return json.dumps(
            {
                "success": True,
                "usecase_id": usecase_id,
                "markdown": markdown,
                "prompt_path": str(p),
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)
