"""
Load and merge rules YAML files shipped with the agent.

Rules are treated as *data* consumed by `rules_evaluator.py`.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def default_rules_path() -> Path:
    """
    Resolve `configs/rules.base.yaml` relative to this file.

    This works for local dev (repo checkout) and typical container layouts where the
    working directory is the agent root.
    """
    return Path(__file__).resolve().parents[2] / "configs" / "rules.base.yaml"


def load_rules_yaml(path: str | Path | None = None) -> dict[str, Any]:
    rules_path = Path(path) if path else default_rules_path()
    with rules_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Rules YAML must parse to a mapping/object, got: {type(data)}")
    return data


def merge_rules_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    return _deep_merge(base, override)


def load_rules_with_optional_override(
    base_path: str | Path | None = None,
    override_yaml: str | None = None,
) -> dict[str, Any]:
    base = load_rules_yaml(base_path)
    if not override_yaml:
        return base
    override = yaml.safe_load(override_yaml) or {}
    if not isinstance(override, dict):
        raise ValueError("override_yaml must parse to a mapping/object")
    return merge_rules_dict(base, override)
