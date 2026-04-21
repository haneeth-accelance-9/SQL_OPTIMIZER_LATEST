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
    # Single top-level title (avoid duplication in downstream renderers)
    lines.append(f"# IT Optimization Report")
    lines.append("")
    lines.append(f"## Use case: `{usecase_id}`")
    lines.append("")
    lines.append(f"- **Report date**: {date.today().isoformat()}")
    lines.append("")

    rules_meta = _rules_doc_by_id()

    matched_counts_map = _extract_matched_counts(rules_evaluation)
    matched_counts: list[tuple[str, int]] = []
    for rid in sorted(rules_meta.keys()):
        matched_counts.append((rid, matched_counts_map.get(rid, 0)))
    matched_total = sum(cnt for _, cnt in matched_counts)

    strategy_results = _normalize_strategy_results_payload(strategy_results)
    strategy_evidence = _collect_host_evidence_from_strategy(strategy_results or {})

    lines.append("## Executive summary")
    lines.append("")
    if matched_counts:
        top = sorted(matched_counts, key=lambda x: x[1], reverse=True)[:3]
        top_text = ", ".join([f"{rid} ({cnt})" for rid, cnt in top if cnt > 0]) or "no matched rules"
        lines.append(
            f"- Findings generated for **{usecase_id}** using provided rule evaluation and strategy outputs. "
            f"Top matching rules: **{top_text}**."
        )
    else:
        lines.append(f"- Findings generated for **{usecase_id}** using provided strategy outputs.")
    lines.append("- Counts reflect rule-engine matches; recommendations reflect upstream strategy outputs when provided.")
    if matched_counts_map:
        lines.append(f"- Total rule matches observed: **{matched_total}**.")
    lines.append("")

    lines.append("## Overview")
    lines.append("")
    lines.append(f"- **Use case id**: `{usecase_id}`")
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

    lines.append("## Key findings")
    lines.append("")
    if matched_counts:
        lines.append("| Rule id | Matched count |")
        lines.append("|---|---:|")
        for rid, cnt in sorted(matched_counts, key=lambda x: x[0]):
            lines.append(f"| `{rid}` | {cnt} |")
    else:
        lines.append("- Rule evaluation summary was not available; matched counts cannot be presented.")
    lines.append("")

    lines.append("## Use case results")
    lines.append("")
    # Always render one section per known rule from rules.base.yaml
    for rid in sorted(rules_meta.keys()):
        meta = rules_meta.get(rid, {})
        desc = meta.get("description") if isinstance(meta, dict) else None
        rtype = meta.get("type") if isinstance(meta, dict) else None
        cnt = matched_counts_map.get(rid, 0)

        lines.append(f"### `{rid}`")
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

        lines.append(f"- **Results**: matched **{cnt}** record(s)")

        ex_hosts = _extract_example_hosts(rules_evaluation, rule_id=rid, limit=3)
        if ex_hosts:
            lines.append(
                f"- **Example host(s) from rule evaluation**: {', '.join([f'`{h}`' for h in ex_hosts])}"
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

    if strategy_evidence:
        lines.append("## Evidence from strategy outputs")
        lines.append("")
        for section in sorted(strategy_evidence.keys()):
            lines.append(f"### `{section}`")
            lines.append("")
            for ev in strategy_evidence[section]:
                lines.append(ev)
            lines.append("")

    lines.append("## Recommended actions")
    lines.append("")
    if strategy_evidence:
        lines.append("- Prioritize hosts with explicit rightsizing / licensing actions surfaced in strategy outputs.")
        lines.append("- Validate change windows and performance baselines before applying reductions (CPU/RAM).")
        lines.append("- For licensing actions, confirm entitlement constraints and target hosting policy (BYOL vs PAYG).")
    else:
        lines.append("- Enrich strategy outputs to surface host-level recommendations (host, action, rationale).")
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
