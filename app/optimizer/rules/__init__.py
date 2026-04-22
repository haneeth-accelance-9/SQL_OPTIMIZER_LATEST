"""
Optimization rules for SQL license analysis.
"""
from .rule_azure_payg import find_azure_payg_candidates, find_azure_payg_candidates_from_db
from .rule_retired_devices import (
    find_retired_devices_with_installations,
    find_retired_devices_with_installations_from_db,
)

__all__ = [
    "find_azure_payg_candidates",
    "find_azure_payg_candidates_from_db",
    "find_retired_devices_with_installations",
    "find_retired_devices_with_installations_from_db",
]
from .rule_azure_payg import find_azure_payg_candidates
from .rule_retired_devices import find_retired_devices_with_installations

__all__ = ["find_azure_payg_candidates", "find_retired_devices_with_installations"]
