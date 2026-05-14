"""
Responsible AI guardrails for the LiscenceOptimizer agent.

Tasks implemented here:
  - Prompt injection protection  : sanitize_prompt_input(), validate_and_sanitize_records()
  - Output filtering             : filter_llm_output()
"""

import logging
import re
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
