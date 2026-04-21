"""
Generate an executive-summary style markdown report from:
- upstream `strategy_results` JSON (from backend / prior phases)
- optional rules evaluation JSON (from `evaluate_optimization_rules`)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from agenticai.tools import tool_registry


def _extract_first_balanced_json(text: str) -> str | None:
    """
    Pull the first complete top-level JSON object or array from free text (phase logs, tool dumps).

    Tracks string escapes so braces inside JSON strings do not confuse depth counting.
    """
    for i, c in enumerate(text):
        if c not in "{[":
            continue
        opener, closer = ("{", "}") if c == "{" else ("[", "]")
        depth = 0
        in_string = False
        escape = False
        for j in range(i, len(text)):
            ch = text[j]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[i : j + 1]
        return None
    return None


def _sanitize_json_text(text: str) -> str:
    """
    Best-effort cleanup for JSON emitted/copied by LLMs.

    Common failure mode: JSON strings contain raw newlines/control chars (invalid in strict JSON).
    """
    # Normalize newlines
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove BOM if present
    t = t.lstrip("\ufeff")

    # If the model wrapped JSON in markdown fences, strip them.
    fence = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)
    t = fence.sub("", t).strip()

    # Replace literal control characters inside the payload with spaces.
    # NOTE: This is a pragmatic approach for telemetry/report scaffolding, not a perfect JSON parser.
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", t)
    return t


def _json_loads_maybe(payload: str | None) -> Any:
    if payload is None:
        return None
    if isinstance(payload, (dict, list)):
        return payload
    text = _sanitize_json_text(str(payload).strip())
    if not text:
        return None

    def _loads_json_lenient(s: str) -> Any:
        try:
            return json.loads(s, strict=False)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder(strict=False)
            obj, _idx = decoder.raw_decode(s)
            return obj

    try:
        parsed = _loads_json_lenient(text)
    except json.JSONDecodeError:
        # Last-resort: some models emit JSON-like structures that are closer to YAML
        # (or otherwise not strict-json). yaml.safe_load is more permissive.
        try:
            parsed = yaml.safe_load(text)
        except Exception as e:  # pragma: no cover
            raise ValueError(f"Unable to parse JSON/YAML-ish payload: {e}") from e
    # Common LLM mistake: double-JSON-encoding (a JSON string that contains JSON)
    if isinstance(parsed, str):
        inner = _sanitize_json_text(parsed.strip())
        if inner.startswith("{") or inner.startswith("["):
            try:
                return _loads_json_lenient(inner)
            except json.JSONDecodeError:
                try:
                    return yaml.safe_load(inner)
                except Exception:
                    # If it's not JSON/YAML, return as plain string
                    return parsed
    return parsed


def _load_rules_evaluation_from_phase(phase_number: int) -> Any:
    """
    Recover `evaluate_optimization_rules` output from phased orchestration storage.

    Avoids re-stringifying large JSON in later tool calls (a common source of truncation / invalid JSON).
    """
    try:
        from agenticai.tools.orchestration import get_phase_result
    except Exception:
        return None

    pr = get_phase_result(phase_number)
    if not isinstance(pr, dict) or pr.get("error"):
        return None
    data = pr.get("data")
    if not isinstance(data, dict):
        return None

    if isinstance(data.get("evaluation"), dict) or data.get("success") is True:
        return data

    for key in ("rules_evaluation", "evaluate_output", "evaluation_json"):
        raw = data.get(key)
        if isinstance(raw, str) and raw.strip():
            try:
                return _json_loads_maybe(raw)
            except Exception:
                continue

    output = data.get("output")
    if isinstance(output, str) and output.strip():
        cleaned = _sanitize_json_text(output)
        blob = _extract_first_balanced_json(cleaned)
        if blob:
            try:
                return _json_loads_maybe(blob)
            except Exception:
                return None
    return None


def _normalize_rules_evaluation(obj: Any) -> dict[str, Any] | None:
    """
    Accept either:
    - the full output of `evaluate_optimization_rules` tool: {success, evaluation, summary}
    - or the inner `{evaluation: ...}` object only
    - or the evaluation dict directly: {rules_version, matched_counts, per_rule, ...}
    """
    if obj is None:
        return None
    if not isinstance(obj, dict):
        return None

    if "evaluation" in obj and isinstance(obj["evaluation"], dict):
        return obj["evaluation"]

    if "matched_counts" in obj and "per_rule" in obj:
        return obj

    if obj.get("success") is True and "summary" in obj:
        # If the model passed the tool wrapper but omitted evaluation for some reason,
        # still return a dict so downstream rendering can show something useful.
        return obj

    return obj


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
        "`rules_evaluation` JSON. Uses `prompts/executive_summary.base.md` as the instruction template. "
        "If `rules_evaluation_json` is omitted, empty, or invalid JSON, the tool loads analysis output "
        "from phased orchestration via `get_phase_result(1)` when available (avoids re-stringifying large JSON)."
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

        trimmed_rules = (rules_evaluation_json or "").strip()
        rules_obj: Any = None
        parse_exc: str | None = None
        if trimmed_rules:
            try:
                rules_obj = _json_loads_maybe(trimmed_rules)
            except (ValueError, json.JSONDecodeError, TypeError) as e:
                parse_exc = str(e)
                rules_obj = None

        rules_evaluation = _normalize_rules_evaluation(rules_obj)
        if rules_evaluation is None:
            phased = _load_rules_evaluation_from_phase(1)
            if phased is not None:
                rules_obj = phased
                rules_evaluation = _normalize_rules_evaluation(phased)

        if rules_evaluation is None and rules_obj is not None:
            return json.dumps(
                {
                    "success": False,
                    "error": "rules_evaluation_json must be JSON describing rules evaluation (dict)",
                },
                indent=2,
            )

        if rules_evaluation is None and trimmed_rules:
            return json.dumps(
                {
                    "success": False,
                    "error": (
                        "Could not parse rules_evaluation_json and no usable Phase 1 rule evaluation "
                        "was found in phase storage (get_phase_result(1))."
                        + (f" Parse detail: {parse_exc}" if parse_exc else "")
                    ),
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
