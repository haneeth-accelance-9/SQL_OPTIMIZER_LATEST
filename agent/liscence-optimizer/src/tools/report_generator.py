"""
Generate an executive-summary style markdown report from:
- upstream `strategy_results` JSON (from backend / prior phases)
- optional rules evaluation JSON (from `evaluate_optimization_rules`)
"""

from __future__ import annotations

import json
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


def _render_markdown(
    *,
    usecase_id: str,
    strategy_results: dict[str, Any] | None,
    rules_evaluation: dict[str, Any] | None,
    notes: str | None,
    instructions: str,
) -> str:
    lines: list[str] = []
    lines.append("## Executive summary")
    lines.append("")
    lines.append(f"- **Usecase**: `{usecase_id}`")
    lines.append("")

    lines.append("## Model instructions (internal)")
    lines.append("")
    lines.append(instructions.strip())
    lines.append("")

    lines.append("## Grounding JSON (internal)")
    lines.append("")
    lines.append("```json")
    lines.append(
        json.dumps(
            {
                "usecase_id": usecase_id,
                "strategy_results": strategy_results or {},
                "rules_evaluation": rules_evaluation or {},
                "notes": notes or "",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    lines.append("```")
    lines.append("")

    lines.append("## Draft summary (deterministic skeleton)")
    lines.append("")
    lines.append("### Overview")
    lines.append("- This section should be rewritten by the LLM using ONLY the JSON above.")
    lines.append("")

    if strategy_results:
        lines.append("### Strategy outputs (keys)")
        lines.append(", ".join(sorted(map(str, strategy_results.keys()))))
        lines.append("")

    if rules_evaluation:
        summary = rules_evaluation.get("summary") if isinstance(rules_evaluation, dict) else None
        matched = None
        if isinstance(summary, dict):
            matched = summary.get("rules")

        lines.append("### Rules evaluation")
        if isinstance(matched, list):
            for r in matched:
                rid = r.get("id")
                cnt = r.get("matched_count")
                lines.append(f"- **{rid}**: matched **{cnt}** record(s)")
        else:
            lines.append("- Rules evaluation provided, but no compact summary was found.")
        lines.append("")

    lines.append("### Risks / caveats")
    lines.append("- Confirm all percentages are consistently represented (fractions vs percents).")
    lines.append("- Confirm environment classification (`environment` field) is correct for PROD vs non-PROD.")
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
        strategy_results = _json_loads_maybe(strategy_results_json)
        if strategy_results is None:
            strategy_results = {}
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
