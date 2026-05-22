"""
Responsible AI guardrails for the LiscenceOptimizer agent.

Tasks implemented here:
  - Prompt injection protection  : sanitize_prompt_input(), validate_and_sanitize_records()
  - Output filtering             : filter_llm_output()
  - Data quality assessment      : assess_data_quality()
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Prompt injection protection
# ─────────────────────────────────────────────────────────────────────────────

_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(previous|prior|all)\s+instructions", re.IGNORECASE),
    # "System: …" / "Human: …" / "Assistant: …" are ChatML-style role markers.
    # Anchored to line-start so that mid-sentence occurrences like
    # "Operating system: Windows Server" are NOT flagged.
    re.compile(r"(?:^|\n)\s*(system|human|assistant)\s*:\s*", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"disregard\s+(previous|prior|all|your)", re.IGNORECASE),
    re.compile(r"(act|pretend|behave)\s+as\s+(if\s+you\s+(are|were)|a\s+)", re.IGNORECASE),
    # "New instructions:" only at line start — avoids matching "new installation instructions:"
    re.compile(r"(?:^|\n)\s*new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"<\s*(script|iframe|object|embed|form)[^>]*>", re.IGNORECASE),
    re.compile(r"prompt\s*injection", re.IGNORECASE),
    # Llama / Mistral / Claude control tokens that could hijack context
    re.compile(r"\[INST\]|\[\/INST\]|<<SYS>>|<</SYS>>|<\|im_start\|>|<\|im_end\|>"),
]

# Control characters except TAB (0x09) and LF (0x0a) and CR (0x0d)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_MAX_FIELD_LENGTHS: dict[str, int] = {
    "usecase_id": 120,
    "notes": 2000,
    "record_key": 80,
    "record_value": 500,
    "default": 1000,
}

MAX_RECORDS = 2000


def sanitize_prompt_input(
    text: Any,
    field_name: str = "default",
    max_length: int | None = None,
) -> str:
    """
    Sanitize a free-text value before it is embedded in an LLM prompt.

    Steps:
      1. Coerce to str.
      2. Strip non-printable control characters (TAB and LF are kept).
      3. Detect and replace prompt-injection patterns with [REMOVED].
      4. Truncate to max_length.

    Returns the cleaned string; logs a warning for every detected issue.
    """
    if text is None:
        return ""

    text = str(text)

    # 1. Strip control chars
    text = _CONTROL_CHAR_RE.sub("", text)

    # 2. Injection patterns
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            logger.warning(
                "prompt_injection_detected field=%s match=%r — replaced with [REMOVED]",
                field_name,
                match.group(0),
            )
            text = pattern.sub("[REMOVED]", text)

    # 3. Truncate
    limit = max_length or _MAX_FIELD_LENGTHS.get(field_name, _MAX_FIELD_LENGTHS["default"])
    if len(text) > limit:
        logger.warning(
            "input_truncated field=%s original_len=%d limit=%d",
            field_name,
            len(text),
            limit,
        )
        text = text[:limit] + "…"

    return text


def validate_and_sanitize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Validate and sanitize a list of record dicts before they enter an LLM prompt.

    - Non-dict entries are dropped.
    - Each key and string value is sanitized via sanitize_prompt_input().
    - Numeric / bool / None values are passed through unchanged (safe in JSON).
    - Total records capped at MAX_RECORDS to prevent prompt flooding.
    """
    if not isinstance(records, list):
        logger.warning(
            "records_not_list type=%s — coerced to empty list", type(records).__name__
        )
        return []

    if len(records) > MAX_RECORDS:
        logger.warning(
            "records_truncated original=%d limit=%d", len(records), MAX_RECORDS
        )
        records = records[:MAX_RECORDS]

    sanitized: list[dict[str, Any]] = []
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            logger.warning("records[%d] is not a dict (type=%s); dropped", i, type(record).__name__)
            continue
        clean: dict[str, Any] = {}
        for key, value in record.items():
            safe_key = sanitize_prompt_input(str(key), field_name="record_key")
            if isinstance(value, (int, float, bool)) or value is None:
                clean[safe_key] = value
            else:
                clean[safe_key] = sanitize_prompt_input(value, field_name="record_value")
        sanitized.append(clean)

    return sanitized


# ─────────────────────────────────────────────────────────────────────────────
# Output filtering
# ─────────────────────────────────────────────────────────────────────────────

_OUTPUT_BLOCKED_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Jailbreak / instruction-following artifacts
    (re.compile(r"ignore\s+(previous|prior|all)\s+instructions", re.IGNORECASE), "[REMOVED]"),
    # Script / HTML injection
    (re.compile(r"<\s*script[^>]*>.*?</\s*script\s*>", re.IGNORECASE | re.DOTALL), "[REMOVED]"),
    (re.compile(r"<\s*script[^>]*>", re.IGNORECASE), "[REMOVED]"),
    (re.compile(r"javascript\s*:", re.IGNORECASE), "[REMOVED]"),
    # Credential / connection-string leakage
    (re.compile(r"(password|pwd|secret|api[_\-]?key)\s*=\s*\S+", re.IGNORECASE), r"\1=[REDACTED]"),
    (re.compile(r"(mongodb|postgresql|mysql|mssql|redis)://\S+", re.IGNORECASE), r"\1://[REDACTED]"),
]

# Heuristic: if the output restates the system prompt verbatim it may be a leak
_SYSTEM_PROMPT_LEAK_RE = re.compile(
    r"you\s+are\s+an\s+it\s+optimization\s+reporting\s+assistant",
    re.IGNORECASE,
)

MAX_OUTPUT_CHARS = 40_000


def filter_llm_output(text: str, field_name: str = "report_markdown") -> str:
    """
    Validate and clean LLM output before it is persisted or displayed.

    Steps:
      1. Enforce a character-length ceiling.
      2. Strip control characters.
      3. Replace blocked patterns (injections, credentials, scripts).
      4. Warn (but do not strip) if the system prompt appears to have been leaked.
    """
    if not isinstance(text, str):
        text = str(text)

    # 1. Length ceiling
    if len(text) > MAX_OUTPUT_CHARS:
        logger.warning(
            "llm_output_truncated field=%s original_len=%d limit=%d",
            field_name,
            len(text),
            MAX_OUTPUT_CHARS,
        )
        text = text[:MAX_OUTPUT_CHARS] + "\n\n*[Output truncated by output filter.]*"

    # 2. Control chars
    text = _CONTROL_CHAR_RE.sub("", text)

    # 3. Blocked patterns
    for pattern, replacement in _OUTPUT_BLOCKED_PATTERNS:
        if pattern.search(text):
            logger.warning(
                "llm_output_blocked_pattern field=%s pattern=%r",
                field_name,
                pattern.pattern[:60],
            )
            text = pattern.sub(replacement, text)

    # 4. System-prompt leak heuristic (warn only)
    if _SYSTEM_PROMPT_LEAK_RE.search(text):
        logger.warning(
            "llm_output_possible_system_prompt_leak field=%s", field_name
        )

    return text


# ─────────────────────────────────────────────────────────────────────────────
# Data quality assessment
# ─────────────────────────────────────────────────────────────────────────────

# Fields expected per use-case group; absence counts as a completeness gap.
_REQUIRED_FIELDS_BY_GROUP: dict[str, list[str]] = {
    "licensing": ["install_status", "hosting_zone", "no_license_required"],
    "compute":   ["avg_cpu_12m", "peak_cpu_12m", "avg_free_mem_12m", "min_free_mem_12m", "current_vcpu"],
}

_VIOLATIONS_CAP = 50  # max violations retained in the report to keep payload bounded


@dataclass
class DataQualityReport:
    """Summary of completeness, accuracy, and consistency checks on a record batch."""

    total_records: int
    completeness_by_group: dict[str, float]
    accuracy_rate: float
    accuracy_violations: list[dict[str, Any]]
    consistency_rate: float
    consistency_violations: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "completeness_by_group": self.completeness_by_group,
            "accuracy_rate": round(self.accuracy_rate, 4),
            "accuracy_violations": self.accuracy_violations[:_VIOLATIONS_CAP],
            "consistency_rate": round(self.consistency_rate, 4),
            "consistency_violations": self.consistency_violations[:_VIOLATIONS_CAP],
        }


def assess_data_quality(records: list[Any]) -> DataQualityReport:
    """
    Run completeness, accuracy, and consistency checks on a list of record dicts.

    - Completeness : per-group fraction of records that have all required fields present.
    - Accuracy     : fraction of valid records with no out-of-range numeric fields.
    - Consistency  : fraction of valid records where related fields are logically consistent.

    Non-dict items are silently skipped (they are counted in total_records but not
    included in any rate denominator so they do not penalise the rates).
    """
    total = len(records)

    if total == 0:
        return DataQualityReport(
            total_records=0,
            completeness_by_group={g: 1.0 for g in _REQUIRED_FIELDS_BY_GROUP},
            accuracy_rate=1.0,
            accuracy_violations=[],
            consistency_rate=1.0,
            consistency_violations=[],
        )

    completeness_ok: dict[str, int] = {g: 0 for g in _REQUIRED_FIELDS_BY_GROUP}
    accuracy_violated: set[int] = set()
    accuracy_violations: list[dict[str, Any]] = []
    consistency_violated: set[int] = set()
    consistency_violations: list[dict[str, Any]] = []
    valid_count = 0

    for i, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        valid_count += 1

        # ── Completeness ──────────────────────────────────────────────────────
        for group, fields in _REQUIRED_FIELDS_BY_GROUP.items():
            if all(f in record for f in fields):
                completeness_ok[group] += 1

        # ── Accuracy ──────────────────────────────────────────────────────────
        for cpu_field in ("avg_cpu_12m", "peak_cpu_12m"):
            val = record.get(cpu_field)
            if isinstance(val, (int, float)) and not isinstance(val, bool) and val > 1.0:
                accuracy_violated.add(i)
                accuracy_violations.append({
                    "record_index": i,
                    "field": cpu_field,
                    "value": val,
                    "reason": "CPU fraction exceeds 1.0 (expected 0–1 range)",
                })

        vcpu = record.get("current_vcpu")
        if isinstance(vcpu, (int, float)) and not isinstance(vcpu, bool) and vcpu < 1:
            accuracy_violated.add(i)
            accuracy_violations.append({
                "record_index": i,
                "field": "current_vcpu",
                "value": vcpu,
                "reason": "current_vcpu below minimum (must be >= 1)",
            })

        # ── Consistency ───────────────────────────────────────────────────────
        avg_cpu = record.get("avg_cpu_12m")
        peak_cpu = record.get("peak_cpu_12m")
        if (
            isinstance(avg_cpu, (int, float)) and not isinstance(avg_cpu, bool)
            and isinstance(peak_cpu, (int, float)) and not isinstance(peak_cpu, bool)
            and avg_cpu > peak_cpu
        ):
            consistency_violated.add(i)
            consistency_violations.append({
                "record_index": i,
                "check": "avg_cpu_12m <= peak_cpu_12m",
                "values": {"avg_cpu_12m": avg_cpu, "peak_cpu_12m": peak_cpu},
            })

        min_free = record.get("min_free_mem_12m")
        avg_free = record.get("avg_free_mem_12m")
        if (
            isinstance(min_free, (int, float)) and not isinstance(min_free, bool)
            and isinstance(avg_free, (int, float)) and not isinstance(avg_free, bool)
            and min_free > avg_free
        ):
            consistency_violated.add(i)
            consistency_violations.append({
                "record_index": i,
                "check": "min_free_mem_12m <= avg_free_mem_12m",
                "values": {"min_free_mem_12m": min_free, "avg_free_mem_12m": avg_free},
            })

    # ── Rates ─────────────────────────────────────────────────────────────────
    denom = valid_count if valid_count > 0 else 1
    completeness_by_group = {g: completeness_ok[g] / denom for g in _REQUIRED_FIELDS_BY_GROUP}

    if valid_count == 0:
        accuracy_rate = 1.0
        consistency_rate = 1.0
    else:
        accuracy_rate = (valid_count - len(accuracy_violated)) / valid_count
        consistency_rate = (valid_count - len(consistency_violated)) / valid_count

    logger.info(
        "data_quality total=%d valid=%d accuracy=%.4f consistency=%.4f",
        total,
        valid_count,
        accuracy_rate,
        consistency_rate,
    )

    return DataQualityReport(
        total_records=total,
        completeness_by_group=completeness_by_group,
        accuracy_rate=accuracy_rate,
        accuracy_violations=accuracy_violations,
        consistency_rate=consistency_rate,
        consistency_violations=consistency_violations,
    )
