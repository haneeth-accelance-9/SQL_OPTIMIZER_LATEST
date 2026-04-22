"""
Evaluate `configs/rules.base.yaml` against normalized records.

Design goals:
- Rules are *data-first* (YAML), with versioned "engines" for complex policies.
- Adding a new rule is usually "append a new entry under `rules:`".
"""

from __future__ import annotations

import math
from typing import Any, Iterable


def _ci(s: Any) -> str:
    return str(s).strip().lower()


def _resolve_any(record: dict[str, Any], cols: list[str], column_map: dict[str, str]) -> Any:
    """
    Best-effort column resolution across multiple possible logical/physical names.
    Useful when upstream datasets use inconsistent CMDB labels (e.g. IsVirtual vs is_virtual).
    """
    for c in cols:
        v = _resolve_col(record, c, column_map)
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return v
    # fall back to raw keys (no mapping)
    for c in cols:
        v = record.get(c)
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return v
    return None


def _is_virtual_system(record: dict[str, Any], column_map: dict[str, str]) -> bool:
    """
    NOTE: per business rule, blank IsVirtual is treated as virtual.
    """
    raw = _resolve_any(record, ["is_virtual", "IsVirtual", "isVirtual", "is virtual"], column_map)
    if raw is None:
        return True
    if isinstance(raw, bool):
        return bool(raw)
    s = _ci(raw)
    if not s:
        return True
    if s in {"true", "t", "1", "yes", "y", "virtual", "vm"}:
        return True
    if s in {"false", "f", "0", "no", "n", "physical", "baremetal", "bare metal"}:
        return False
    # unknown label: default to virtual (safer than accidentally blocking a large population)
    return True


def _is_critical_system(record: dict[str, Any], column_map: dict[str, str]) -> bool:
    """
    Human intervention / conservative rightsizing when CI criticality indicates:
    - Business Critical
    - Mission Critical
    - Manufacturing Critical (often used in site contexts)
    """
    raw = _resolve_any(record, ["criticality", "Critically", "Criticality", "critical", "Critical"], column_map)
    if raw is None:
        return False
    s = _ci(raw)
    return any(
        k in s
        for k in [
            "business critical",
            "mission critical",
            "manufacturing critical",
            "manufacturing-critical",
        ]
    )


def _to_float(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, bool):
        return float(int(x))
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        s = s.replace("%", "")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _to_int(x: Any) -> int | None:
    f = _to_float(x)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None


def _get_field(record: dict[str, Any], col: str) -> Any:
    return record.get(col)


def _resolve_col(record: dict[str, Any], col: str, column_map: dict[str, str]) -> Any:
    physical = column_map.get(col, col)
    return _get_field(record, physical)


def eval_expr(
    expr: dict[str, Any] | None,
    record: dict[str, Any],
    column_map: dict[str, str],
) -> tuple[bool, list[str]]:
    """
    Evaluate a small expression DSL used in YAML.

    Supported shapes:
    - {"op": "...", ...}
    - {"all": [expr, ...]}
    - {"any": [expr, ...]}
    """
    reasons: list[str] = []
    if not expr:
        return True, reasons

    if "all" in expr:
        items = expr.get("all") or []
        ok = True
        for sub in items:
            sub_ok, sub_reasons = eval_expr(sub, record, column_map)
            reasons.extend(sub_reasons)
            ok = ok and sub_ok
        return ok, reasons

    if "any" in expr:
        items = expr.get("any") or []
        any_ok = False
        for sub in items:
            sub_ok, sub_reasons = eval_expr(sub, record, column_map)
            reasons.extend(sub_reasons)
            any_ok = any_ok or sub_ok
        return any_ok, reasons

    op = str(expr.get("op", "")).strip()
    col = str(expr.get("col", "")).strip()
    val = _resolve_col(record, col, column_map)

    if op == "eq":
        target = expr.get("value")
        ok = val == target
        if not ok:
            reasons.append(f"{col}: expected == {target!r}, got {val!r}")
        return ok, reasons

    if op == "eq_ci":
        target = expr.get("value")
        ok = _ci(val) == _ci(target)
        if not ok:
            reasons.append(f"{col}: expected == {target!r} (case-insensitive), got {val!r}")
        return ok, reasons

    if op == "ne_ci":
        target = expr.get("value")
        ok = _ci(val) != _ci(target)
        if not ok:
            reasons.append(f"{col}: expected != {target!r} (case-insensitive), got {val!r}")
        return ok, reasons

    if op == "not_eq_ci":
        target = expr.get("value")
        ok = _ci(val) != _ci(target)
        if not ok:
            reasons.append(f"{col}: expected not {target!r} (case-insensitive), got {val!r}")
        return ok, reasons

    if op == "in_ci":
        values = expr.get("values") or []
        if not isinstance(values, list):
            raise ValueError("in_ci.values must be a list")
        ok = _ci(val) in {_ci(v) for v in values}
        if not ok:
            reasons.append(f"{col}: expected one of {values!r} (case-insensitive), got {val!r}")
        return ok, reasons

    if op in {"lt", "lte", "gt", "gte"}:
        target = _to_float(expr.get("value"))
        current = _to_float(val)
        if target is None:
            raise ValueError(f"{op}: invalid target value in expr={expr!r}")
        if current is None:
            reasons.append(f"{col}: missing/invalid numeric value for {op}, got {val!r}")
            return False, reasons

        if op == "lt":
            ok = current < target
        elif op == "lte":
            ok = current <= target
        elif op == "gt":
            ok = current > target
        else:
            ok = current >= target

        if not ok:
            reasons.append(f"{col}: expected {op} {target}, got {current}")
        return ok, reasons

    raise ValueError(f"Unsupported op: {op!r} in expr={expr!r}")


def _branch_matches(
    branch_when: dict[str, Any] | None,
    record: dict[str, Any],
    column_map: dict[str, str],
) -> bool:
    ok, _ = eval_expr(branch_when, record, column_map)
    return ok


def _round_vcpu_down_to_min(current: int, target: float, minimum: int = 2) -> int:
    if current <= minimum:
        return current
    rounded = int(math.floor(target))
    return max(minimum, min(current, rounded))


def _allowed_ram_gib() -> list[int]:
    # Practical sizes requested by the business rules examples.
    return [4, 8, 12, 16, 24, 32, 48, 64, 96, 128]


def _round_ram_down(current_gib: int, target_gib: float, minimum_gib: int) -> int:
    if current_gib <= minimum_gib:
        return current_gib
    desired = int(math.floor(target_gib))
    desired = max(desired, minimum_gib)
    cap = min(current_gib, desired)
    # choose the largest practical size <= cap
    for size in reversed(_allowed_ram_gib()):
        if size <= cap and size >= minimum_gib:
            return size
    return max(minimum_gib, cap)


def _engine_cpu_rightsizing_prod_v1(record: dict[str, Any], column_map: dict[str, str]) -> dict[str, Any]:
    avg = _to_float(_resolve_col(record, "avg_cpu_12m", column_map))
    peak = _to_float(_resolve_col(record, "peak_cpu_12m", column_map))
    vcpu = _to_int(_resolve_col(record, "current_vcpu", column_map))
    if avg is None or peak is None or vcpu is None:
        return {
            "candidate": False,
            "reasons": ["Missing one of avg_cpu_12m / peak_cpu_12m / current_vcpu"],
            "recommendation": None,
        }

    candidate = (avg < 0.15) and (peak <= 0.70) and (vcpu > 2)
    if not candidate:
        return {
            "candidate": False,
            "reasons": ["CPU rightsizing candidate rules not met (PROD)"],
            "recommendation": None,
        }

    # Recommendations (PROD)
    if peak > 0.70:
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "no_cpu_reduction",
                "rationale": "Peak CPU > 70% — protect peak performance even if average is low.",
            },
        }

    if avg < 0.10 and (0.69 <= peak <= 0.71):  # "~70%" interpreted as a tight band
        target = vcpu * 0.50
        new_vcpu = _round_vcpu_down_to_min(vcpu, target, minimum=2)
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_vcpu",
                "from": vcpu,
                "to": new_vcpu,
                "rationale": "Avg < 10% and peak ~70% → reduce ~50% (never below 2).",
            },
        }

    if (0.10 <= avg <= 0.15) and (peak <= 0.60):
        target = vcpu * 0.75
        new_vcpu = _round_vcpu_down_to_min(vcpu, target, minimum=2)
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_vcpu",
                "from": vcpu,
                "to": new_vcpu,
                "rationale": "Avg between 10%–15% and peak <= 60% → reduce ~25% (never below 2).",
            },
        }

    return {
        "candidate": True,
        "reasons": [],
        "recommendation": {
            "action": "no_change",
            "rationale": "Candidate met optimization thresholds, but no recommendation branch matched.",
        },
    }


def _cpu_lifecycle_flags(*, critical: bool, peak: float | None) -> list[str]:
    flags: list[str] = []
    if critical:
        flags.append("Critical System")
    if peak is not None and peak > 0.95:
        flags.append("High peak CPU (>95%)")
    return flags


def _engine_cpu_rightsizing_prod_v2(record: dict[str, Any], column_map: dict[str, str]) -> dict[str, Any]:
    avg = _to_float(_resolve_col(record, "avg_cpu_12m", column_map))
    peak = _to_float(_resolve_col(record, "peak_cpu_12m", column_map))
    vcpu = _to_int(_resolve_col(record, "current_vcpu", column_map))
    if avg is None or peak is None or vcpu is None:
        return {
            "candidate": False,
            "reasons": ["Missing one of avg_cpu_12m / peak_cpu_12m / current_vcpu"],
            "recommendation": None,
        }

    is_virtual = _is_virtual_system(record, column_map)
    critical = _is_critical_system(record, column_map)
    lifecycle_flags = _cpu_lifecycle_flags(critical=critical, peak=peak)

    if not is_virtual:
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "human_review_required",
                "rationale": "Physical system detected (IsVirtual=false) — requires human review before rightsizing.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Upsizing (flag/recommendation)
    if avg > 0.80:
        new_vcpu = max(4, int(math.ceil(vcpu * 1.25)))
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "upsize_vcpu",
                "from": vcpu,
                "to": new_vcpu,
                "rationale": "Avg CPU > 80% → upsize by ~25%.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # High peak blocks downsizing and triggers lifecycle flags
    if peak > 0.95:
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "no_cpu_reduction",
                "rationale": "High peak CPU (>95%) blocks downsizing and triggers lifecycle review.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Candidate rules (PROD): avg < 15%, peak <= 70%, current vCPU >= 4
    candidate = (avg < 0.15) and (peak <= 0.70) and (vcpu >= 4)
    if not candidate:
        return {
            "candidate": False,
            "reasons": ["CPU rightsizing candidate rules not met (PROD)"],
            "recommendation": None,
        }

    # Critical systems: extra conservatism
    if critical:
        if avg < 0.10:
            target = vcpu * 0.75  # downsize ~25%
            new_vcpu = _round_vcpu_down_to_min(vcpu, target, minimum=4)
            return {
                "candidate": True,
                "reasons": [],
                "recommendation": {
                    "action": "reduce_vcpu",
                    "from": vcpu,
                    "to": new_vcpu,
                    "rationale": "Critical System – Cautious downsizing: Avg CPU < 10% → downsize ~25% (never below 4).",
                    "lifecycle_flags": lifecycle_flags,
                },
            }
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "no_cpu_reduction",
                "rationale": "Critical System: only downsize when Avg CPU < 10%.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Non-critical PROD recommendations
    if peak > 0.70:
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "no_cpu_reduction",
                "rationale": "Peak CPU > 70% — protect peak performance even if average is low.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    if avg < 0.10 and (0.69 <= peak <= 0.71):  # "~70%" interpreted as a tight band
        target = vcpu * 0.50
        new_vcpu = _round_vcpu_down_to_min(vcpu, target, minimum=4)
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_vcpu",
                "from": vcpu,
                "to": new_vcpu,
                "rationale": "Avg < 10% and peak ~70% → reduce ~50% (never below 4).",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    if (0.10 <= avg <= 0.15) and (peak <= 0.60):
        target = vcpu * 0.75
        new_vcpu = _round_vcpu_down_to_min(vcpu, target, minimum=4)
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_vcpu",
                "from": vcpu,
                "to": new_vcpu,
                "rationale": "Avg between 10%–15% and peak <= 60% → reduce ~25% (never below 4).",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    return {
        "candidate": True,
        "reasons": [],
        "recommendation": {
            "action": "no_change",
            "rationale": "Candidate met optimization thresholds, but no recommendation branch matched.",
            "lifecycle_flags": lifecycle_flags,
        },
    }


def _engine_cpu_rightsizing_nonprod_v1(record: dict[str, Any], column_map: dict[str, str]) -> dict[str, Any]:
    avg = _to_float(_resolve_col(record, "avg_cpu_12m", column_map))
    peak = _to_float(_resolve_col(record, "peak_cpu_12m", column_map))
    vcpu = _to_int(_resolve_col(record, "current_vcpu", column_map))
    if avg is None or peak is None or vcpu is None:
        return {
            "candidate": False,
            "reasons": ["Missing one of avg_cpu_12m / peak_cpu_12m / current_vcpu"],
            "recommendation": None,
        }

    candidate = (avg < 0.15) and (peak <= 0.80) and (vcpu > 2)
    if not candidate:
        return {
            "candidate": False,
            "reasons": ["CPU rightsizing candidate rules not met (non-PROD)"],
            "recommendation": None,
        }

    if peak > 0.80:
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "no_cpu_reduction",
                "rationale": "Peak CPU > 80% — no CPU reduction.",
            },
        }

    if avg < 0.15 and peak < 0.60:
        target = vcpu * 0.45  # middle of 50–60% reduction band
        new_vcpu = _round_vcpu_down_to_min(vcpu, target, minimum=2)
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_vcpu",
                "from": vcpu,
                "to": new_vcpu,
                "rationale": "Avg < 15% and peak < 60% → allow ~50–60% reduction (still >= 2).",
            },
        }

    if (0.15 <= avg <= 0.25) and (peak <= 0.70):
        target = vcpu * 0.71  # middle of 25–33% reduction band (~29%)
        new_vcpu = _round_vcpu_down_to_min(vcpu, target, minimum=2)
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_vcpu",
                "from": vcpu,
                "to": new_vcpu,
                "rationale": "Avg between 15%–25% and peak <= 70% → reduce ~25–33% (never below 2).",
            },
        }

    return {
        "candidate": True,
        "reasons": [],
        "recommendation": {
            "action": "no_change",
            "rationale": "Candidate met optimization thresholds, but no recommendation branch matched.",
        },
    }


def _engine_cpu_rightsizing_nonprod_v2(record: dict[str, Any], column_map: dict[str, str]) -> dict[str, Any]:
    avg = _to_float(_resolve_col(record, "avg_cpu_12m", column_map))
    peak = _to_float(_resolve_col(record, "peak_cpu_12m", column_map))
    vcpu = _to_int(_resolve_col(record, "current_vcpu", column_map))
    if avg is None or peak is None or vcpu is None:
        return {
            "candidate": False,
            "reasons": ["Missing one of avg_cpu_12m / peak_cpu_12m / current_vcpu"],
            "recommendation": None,
        }

    is_virtual = _is_virtual_system(record, column_map)
    critical = _is_critical_system(record, column_map)
    lifecycle_flags = _cpu_lifecycle_flags(critical=critical, peak=peak)

    if not is_virtual:
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "human_review_required",
                "rationale": "Physical system detected (IsVirtual=false) — requires human review before rightsizing.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Upsizing (flag/recommendation)
    if avg > 0.80:
        new_vcpu = max(4, int(math.ceil(vcpu * 1.25)))
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "upsize_vcpu",
                "from": vcpu,
                "to": new_vcpu,
                "rationale": "Avg CPU > 80% → upsize by ~25%.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # High peak blocks downsizing and triggers lifecycle flags
    if peak > 0.95:
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "no_cpu_reduction",
                "rationale": "High peak CPU (>95%) blocks downsizing and triggers lifecycle review.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Candidate rules (non-PROD): avg < 25% (to allow 15–25 band), peak <= 80%, vCPU >= 4
    candidate = (avg < 0.25) and (peak <= 0.80) and (vcpu >= 4)
    if not candidate:
        return {
            "candidate": False,
            "reasons": ["CPU rightsizing candidate rules not met (non-PROD)"],
            "recommendation": None,
        }

    if peak > 0.80:
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "no_cpu_reduction",
                "rationale": "Peak CPU > 80% — no CPU reduction.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Critical systems: extra conservatism
    if critical:
        if avg < 0.10:
            target = vcpu * 0.75  # downsize ~25%
            new_vcpu = _round_vcpu_down_to_min(vcpu, target, minimum=4)
            return {
                "candidate": True,
                "reasons": [],
                "recommendation": {
                    "action": "reduce_vcpu",
                    "from": vcpu,
                    "to": new_vcpu,
                    "rationale": "Critical System – Cautious downsizing: Avg CPU < 10% → downsize ~25% (never below 4).",
                    "lifecycle_flags": lifecycle_flags,
                },
            }
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "no_cpu_reduction",
                "rationale": "Critical System: only downsize when Avg CPU < 10%.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Non-PROD recommendations
    if avg < 0.15 and peak < 0.60:
        target = vcpu * 0.45  # middle of 50–60% reduction band
        new_vcpu = _round_vcpu_down_to_min(vcpu, target, minimum=4)
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_vcpu",
                "from": vcpu,
                "to": new_vcpu,
                "rationale": "Avg < 15% and peak < 60% → allow ~50–60% reduction (never below 4).",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    if (0.15 <= avg <= 0.25) and (peak <= 0.70):
        target = vcpu * 0.71  # middle of 25–33% reduction band (~29%)
        new_vcpu = _round_vcpu_down_to_min(vcpu, target, minimum=4)
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_vcpu",
                "from": vcpu,
                "to": new_vcpu,
                "rationale": "Avg between 15%–25% and peak <= 70% → reduce ~25–33% (never below 4).",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    return {
        "candidate": True,
        "reasons": [],
        "recommendation": {
            "action": "no_change",
            "rationale": "Candidate met optimization thresholds, but no recommendation branch matched.",
            "lifecycle_flags": lifecycle_flags,
        },
    }


def _engine_ram_rightsizing_prod_v1(record: dict[str, Any], column_map: dict[str, str]) -> dict[str, Any]:
    avg_free = _to_float(_resolve_col(record, "avg_free_mem_12m", column_map))
    min_free = _to_float(_resolve_col(record, "min_free_mem_12m", column_map))
    ram = _to_float(_resolve_col(record, "current_ram_gib", column_map))
    if avg_free is None or min_free is None or ram is None:
        return {
            "candidate": False,
            "reasons": ["Missing one of avg_free_mem_12m / min_free_mem_12m / current_ram_gib"],
            "recommendation": None,
        }

    ram_i = int(ram)
    candidate = (avg_free >= 0.35) and (min_free >= 0.20) and (ram_i > 8)
    if not candidate:
        return {
            "candidate": False,
            "reasons": ["RAM reduction candidate rules not met (PROD)"],
            "recommendation": None,
        }

    if (0.35 <= avg_free <= 0.50):
        new_ram = _round_ram_down(ram_i, ram_i * 0.75, minimum_gib=8)  # ~25% reduction
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_ram_gib",
                "from": ram_i,
                "to": new_ram,
                "rationale": "Avg free mem between 35%–50% → reduce ~25%, never below 8 GiB.",
            },
        }

    if avg_free > 0.50 and min_free >= 0.30:
        new_ram = _round_ram_down(ram_i, ram_i * 0.55, minimum_gib=8)  # middle of 40–50%
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_ram_gib",
                "from": ram_i,
                "to": new_ram,
                "rationale": "Avg free mem > 50% and min free mem >= 30% → reduce ~40–50%, never below 8 GiB.",
            },
        }

    return {
        "candidate": True,
        "reasons": [],
        "recommendation": {
            "action": "no_change",
            "rationale": "Candidate met optimization thresholds, but no recommendation branch matched.",
        },
    }


def _ram_lifecycle_flags(*, critical: bool, min_free: float | None) -> list[str]:
    flags: list[str] = []
    if critical:
        flags.append("Critical System")
    if min_free is not None and min_free < 0.05:
        flags.append("Low minimum memory (<5%)")
    return flags


def _engine_ram_rightsizing_prod_v2(record: dict[str, Any], column_map: dict[str, str]) -> dict[str, Any]:
    avg_free = _to_float(_resolve_col(record, "avg_free_mem_12m", column_map))
    min_free = _to_float(_resolve_col(record, "min_free_mem_12m", column_map))
    ram = _to_float(_resolve_col(record, "current_ram_gib", column_map))
    if avg_free is None or min_free is None or ram is None:
        return {
            "candidate": False,
            "reasons": ["Missing one of avg_free_mem_12m / min_free_mem_12m / current_ram_gib"],
            "recommendation": None,
        }

    ram_i = int(ram)
    is_virtual = _is_virtual_system(record, column_map)
    critical = _is_critical_system(record, column_map)
    lifecycle_flags = _ram_lifecycle_flags(critical=critical, min_free=min_free)

    if not is_virtual:
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "human_review_required",
                "rationale": "Physical system detected (IsVirtual=false) — requires human review before rightsizing.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Upsizing: flag only per spec (no need to do anything)
    if (critical and avg_free < 0.20) or ((not critical) and avg_free < 0.30) or (avg_free < 0.20):
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "flag_ram_upsize",
                "rationale": "Low Avg Free Mem suggests potential RAM pressure — flag for review (no auto action).",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Candidate (PROD): avg_free >=35%, min_free >=20%, RAM > 8 GiB
    candidate = (avg_free >= 0.35) and (min_free >= 0.20) and (ram_i > 8)
    if not candidate:
        return {
            "candidate": False,
            "reasons": ["RAM reduction candidate rules not met (PROD)"],
            "recommendation": None,
        }

    # Critical systems: only downsize when Avg_FreeMem > 80%
    if critical:
        if avg_free > 0.80:
            new_ram = _round_ram_down(ram_i, ram_i * 0.75, minimum_gib=8)  # ~25% reduction
            return {
                "candidate": True,
                "reasons": [],
                "recommendation": {
                    "action": "reduce_ram_gib",
                    "from": ram_i,
                    "to": new_ram,
                    "rationale": "Critical System: Avg free mem > 80% → downsize ~25%, never below 8 GiB.",
                    "lifecycle_flags": lifecycle_flags,
                },
            }
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "no_change",
                "rationale": "Critical System: only downsize RAM when Avg free mem > 80%.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Non-critical PROD recommendations
    if 0.35 <= avg_free <= 0.50:
        new_ram = _round_ram_down(ram_i, ram_i * 0.75, minimum_gib=8)  # ~25% reduction
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_ram_gib",
                "from": ram_i,
                "to": new_ram,
                "rationale": "Avg free mem between 35%–50% → reduce ~25%, never below 8 GiB.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    if avg_free > 0.50 and min_free >= 0.30:
        new_ram = _round_ram_down(ram_i, ram_i * 0.55, minimum_gib=8)  # middle of 40–50%
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_ram_gib",
                "from": ram_i,
                "to": new_ram,
                "rationale": "Avg free mem > 50% and min free mem >= 30% → reduce ~40–50%, never below 8 GiB.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    return {
        "candidate": True,
        "reasons": [],
        "recommendation": {
            "action": "no_change",
            "rationale": "Candidate met optimization thresholds, but no recommendation branch matched.",
            "lifecycle_flags": lifecycle_flags,
        },
    }


def _engine_ram_rightsizing_nonprod_v1(record: dict[str, Any], column_map: dict[str, str]) -> dict[str, Any]:
    avg_free = _to_float(_resolve_col(record, "avg_free_mem_12m", column_map))
    min_free = _to_float(_resolve_col(record, "min_free_mem_12m", column_map))
    ram = _to_float(_resolve_col(record, "current_ram_gib", column_map))
    if avg_free is None or min_free is None or ram is None:
        return {
            "candidate": False,
            "reasons": ["Missing one of avg_free_mem_12m / min_free_mem_12m / current_ram_gib"],
            "recommendation": None,
        }

    ram_i = int(ram)
    candidate = (avg_free >= 0.30) and (min_free >= 0.15) and (ram_i > 4)
    if not candidate:
        return {
            "candidate": False,
            "reasons": ["RAM reduction candidate rules not met (non-PROD)"],
            "recommendation": None,
        }

    if (0.30 <= avg_free <= 0.50):
        new_ram = _round_ram_down(ram_i, ram_i * 0.67, minimum_gib=4)  # ~33% reduction
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_ram_gib",
                "from": ram_i,
                "to": new_ram,
                "rationale": "Avg free mem between 30%–50% → reduce ~33%, never below 4 GiB.",
            },
        }

    if avg_free > 0.50 and min_free >= 0.25:
        new_ram = _round_ram_down(ram_i, ram_i * 0.50, minimum_gib=4)  # middle of 40–60%
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_ram_gib",
                "from": ram_i,
                "to": new_ram,
                "rationale": "Avg free mem > 50% and min free mem >= 25% → reduce ~40–60%, never below 4 GiB.",
            },
        }

    return {
        "candidate": True,
        "reasons": [],
        "recommendation": {
            "action": "no_change",
            "rationale": "Candidate met optimization thresholds, but no recommendation branch matched.",
        },
    }


def _engine_ram_rightsizing_nonprod_v2(record: dict[str, Any], column_map: dict[str, str]) -> dict[str, Any]:
    avg_free = _to_float(_resolve_col(record, "avg_free_mem_12m", column_map))
    min_free = _to_float(_resolve_col(record, "min_free_mem_12m", column_map))
    ram = _to_float(_resolve_col(record, "current_ram_gib", column_map))
    if avg_free is None or min_free is None or ram is None:
        return {
            "candidate": False,
            "reasons": ["Missing one of avg_free_mem_12m / min_free_mem_12m / current_ram_gib"],
            "recommendation": None,
        }

    ram_i = int(ram)
    is_virtual = _is_virtual_system(record, column_map)
    critical = _is_critical_system(record, column_map)
    lifecycle_flags = _ram_lifecycle_flags(critical=critical, min_free=min_free)

    if not is_virtual:
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "human_review_required",
                "rationale": "Physical system detected (IsVirtual=false) — requires human review before rightsizing.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Upsizing: flag only
    if (critical and avg_free < 0.20) or ((not critical) and avg_free < 0.30) or (avg_free < 0.20):
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "flag_ram_upsize",
                "rationale": "Low Avg Free Mem suggests potential RAM pressure — flag for review (no auto action).",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Candidate (non-PROD): avg_free >=30%, min_free >=15%, RAM > 4 GiB
    candidate = (avg_free >= 0.30) and (min_free >= 0.15) and (ram_i > 4)
    if not candidate:
        return {
            "candidate": False,
            "reasons": ["RAM reduction candidate rules not met (non-PROD)"],
            "recommendation": None,
        }

    # Critical systems: only downsize when Avg_FreeMem > 80%
    if critical:
        if avg_free > 0.80:
            new_ram = _round_ram_down(ram_i, ram_i * 0.75, minimum_gib=4)  # ~25% reduction, non-prod min 4
            return {
                "candidate": True,
                "reasons": [],
                "recommendation": {
                    "action": "reduce_ram_gib",
                    "from": ram_i,
                    "to": new_ram,
                    "rationale": "Critical System: Avg free mem > 80% → downsize ~25%, never below 4 GiB.",
                    "lifecycle_flags": lifecycle_flags,
                },
            }
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "no_change",
                "rationale": "Critical System: only downsize RAM when Avg free mem > 80%.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    # Non-critical non-PROD recommendations
    if 0.30 <= avg_free <= 0.50:
        new_ram = _round_ram_down(ram_i, ram_i * 0.67, minimum_gib=4)  # ~33% reduction
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_ram_gib",
                "from": ram_i,
                "to": new_ram,
                "rationale": "Avg free mem between 30%–50% → reduce ~33%, never below 4 GiB.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    if avg_free > 0.50 and min_free >= 0.25:
        new_ram = _round_ram_down(ram_i, ram_i * 0.50, minimum_gib=4)  # middle of 40–60%
        return {
            "candidate": True,
            "reasons": [],
            "recommendation": {
                "action": "reduce_ram_gib",
                "from": ram_i,
                "to": new_ram,
                "rationale": "Avg free mem > 50% and min free mem >= 25% → reduce ~40–60%, never below 4 GiB.",
                "lifecycle_flags": lifecycle_flags,
            },
        }

    return {
        "candidate": True,
        "reasons": [],
        "recommendation": {
            "action": "no_change",
            "rationale": "Candidate met optimization thresholds, but no recommendation branch matched.",
            "lifecycle_flags": lifecycle_flags,
        },
    }


ENGINES: dict[str, Any] = {
    "cpu_rightsizing_prod_v1": _engine_cpu_rightsizing_prod_v1,
    "cpu_rightsizing_nonprod_v1": _engine_cpu_rightsizing_nonprod_v1,
    "ram_rightsizing_prod_v1": _engine_ram_rightsizing_prod_v1,
    "ram_rightsizing_nonprod_v1": _engine_ram_rightsizing_nonprod_v1,
    "cpu_rightsizing_prod_v2": _engine_cpu_rightsizing_prod_v2,
    "cpu_rightsizing_nonprod_v2": _engine_cpu_rightsizing_nonprod_v2,
    "ram_rightsizing_prod_v2": _engine_ram_rightsizing_prod_v2,
    "ram_rightsizing_nonprod_v2": _engine_ram_rightsizing_nonprod_v2,
}


def evaluate_rule_on_record(rule: dict[str, Any], record: dict[str, Any], column_map: dict[str, str]) -> dict[str, Any]:
    rule_id = rule.get("id")
    rule_type = rule.get("type")

    if rule_type == "filter":
        ok, reasons = eval_expr(rule.get("when"), record, column_map)
        return {"id": rule_id, "type": "filter", "matched": ok, "reasons": reasons, "details": None}

    if rule_type == "recommendation":
        applies_ok, applies_reasons = eval_expr(rule.get("applies_when"), record, column_map)
        if not applies_ok:
            return {
                "id": rule_id,
                "type": "recommendation",
                "matched": False,
                "reasons": applies_reasons,
                "details": {"stage": "applies_when"},
            }

        branches = rule.get("branches") or []
        if not isinstance(branches, list) or not branches:
            raise ValueError(f"Rule {rule_id!r} must define branches: [...]")

        chosen = None
        for branch in branches:
            if _branch_matches(branch.get("when"), record, column_map):
                chosen = branch
                break

        if not chosen:
            return {
                "id": rule_id,
                "type": "recommendation",
                "matched": False,
                "reasons": ["No branch matched (env/segment rules)"],
                "details": {"stage": "branch_when"},
            }

        cand_ok, cand_reasons = eval_expr(chosen.get("candidate_when"), record, column_map)
        if not cand_ok:
            return {
                "id": rule_id,
                "type": "recommendation",
                "matched": False,
                "reasons": cand_reasons,
                "details": {"stage": "candidate_when", "branch": chosen.get("id")},
            }

        recommend = chosen.get("recommend") or {}
        engine = recommend.get("engine")
        if not engine or engine not in ENGINES:
            raise ValueError(f"Unknown recommendation engine: {engine!r} for rule {rule_id!r}")

        engine_result = ENGINES[str(engine)](record, column_map)
        return {
            "id": rule_id,
            "type": "recommendation",
            "matched": bool(engine_result.get("candidate")),
            "reasons": list(engine_result.get("reasons") or []),
            "details": {"branch": chosen.get("id"), "engine": engine, "engine_result": engine_result},
        }

    raise ValueError(f"Unsupported rule.type: {rule_type!r} for rule id={rule_id!r}")


def evaluate_rules_on_records(rules_doc: dict[str, Any], records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    column_map = (rules_doc.get("defaults") or {}).get("column_names") or {}
    if not isinstance(column_map, dict):
        raise ValueError("defaults.column_names must be a mapping")

    rules = rules_doc.get("rules") or []
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")

    per_rule: dict[str, list[dict[str, Any]]] = {str(r.get("id")): [] for r in rules if r.get("id")}
    matched_counts: dict[str, int] = {k: 0 for k in per_rule.keys()}

    for record in records:
        if not isinstance(record, dict):
            continue
        for rule in rules:
            rid = str(rule.get("id"))
            res = evaluate_rule_on_record(rule, record, column_map)
            per_rule.setdefault(rid, [])
            per_rule[rid].append({"record": record, "result": res})
            if bool(res.get("matched")):
                matched_counts[rid] = matched_counts.get(rid, 0) + 1

    return {
        "rules_version": rules_doc.get("version"),
        "matched_counts": matched_counts,
        "per_rule": per_rule,
    }


def summarize_for_executive_report(evaluation: dict[str, Any], max_examples_per_rule: int = 3) -> dict[str, Any]:
    """
    Reduce evaluation output to a compact structure suitable for prompts / JSON payloads.
    """
    summary_rules: list[dict[str, Any]] = []
    per_rule = evaluation.get("per_rule") or {}
    matched_counts = evaluation.get("matched_counts") or {}

    for rid, rows in per_rule.items():
        examples: list[dict[str, Any]] = []
        for row in rows:
            res = (row or {}).get("result") or {}
            if not res.get("matched"):
                continue
            examples.append({"record": (row or {}).get("record"), "result": res})
            if len(examples) >= max_examples_per_rule:
                break

        summary_rules.append(
            {
                "id": rid,
                "matched_count": matched_counts.get(rid, 0),
                "examples": examples,
            }
        )

    return {"rules_version": evaluation.get("rules_version"), "rules": summary_rules}
