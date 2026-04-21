"""
Evaluate optimization/licensing rules against normalized VM/inventory records.

This tool is meant to be called by the agent (or orchestrated by phased instructions)
after the backend attaches a dataset or provides extracted rows as JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agenticai.tools import tool_registry

from .rules_evaluator import evaluate_rules_on_records, summarize_for_executive_report
from .rules_loader import load_rules_with_optional_override


def _json_loads_maybe(payload: str) -> Any:
    if payload is None:
        return None
    if isinstance(payload, (dict, list)):
        return payload
    text = str(payload).strip()
    if not text:
        return None
    return json.loads(text)


@tool_registry.register(
    name="evaluate_optimization_rules",
    description=(
        "Evaluate `configs/rules.base.yaml` against a list of normalized records (JSON). "
        "Returns matched counts per rule plus compact examples suitable for reporting."
    ),
    tags=["rules", "evaluation", "optimization", "licensing"],
    requires_context=False,
)
def evaluate_optimization_rules(
    records_json: str,
    rules_path: str | None = None,
    override_rules_yaml: str | None = None,
    max_examples_per_rule: int = 3,
) -> str:
    records = _json_loads_maybe(records_json)
    if not isinstance(records, list):
        return json.dumps(
            {
                "success": False,
                "error": "records_json must be a JSON list of objects",
            },
            indent=2,
        )

    try:
        rules_doc = load_rules_with_optional_override(
            base_path=Path(rules_path) if rules_path else None,
            override_yaml=override_rules_yaml,
        )
        evaluation = evaluate_rules_on_records(rules_doc, records)
        summary = summarize_for_executive_report(evaluation, max_examples_per_rule=max_examples_per_rule)
        return json.dumps({"success": True, "evaluation": evaluation, "summary": summary}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)
