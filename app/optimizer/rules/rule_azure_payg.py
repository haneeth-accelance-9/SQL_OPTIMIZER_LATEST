"""
Rule 1: Azure BYOL → PAYG Optimization.

Identifies SQL Server installations in Azure environments eligible to switch
from BYOL to PAYG. Expects normalized (snake_case) column names.

Enterprise use case (UC 1.1):
- u_hosting_zone is Public Cloud or Private Cloud AVS
- Inventory Status Standard is not equal to "License Included" (case-insensitive)
- No License Required (Product) equals 0
"""
import logging
from typing import List, Optional

import pandas as pd

from optimizer.rules.column_utils import find_no_license_required_column, no_license_required_is_zero

logger = logging.getLogger(__name__)

COL_HOSTING = "u_hosting_zone"
COL_INVENTORY_STATUS = "inventory_status_standard"

# UC 1.1: Public Cloud and Private Cloud AVS only
DEFAULT_TARGET_ZONES = ["Public Cloud", "Private Cloud AVS"]
EXCLUDED_INVENTORY_PHRASE = "license included"


def find_azure_payg_candidates(
    installation_df: pd.DataFrame,
    target_zones: Optional[List[str]] = None,
    excluded_inventory_phrase: str = EXCLUDED_INVENTORY_PHRASE,
) -> pd.DataFrame:
    """
    Identify Azure devices eligible for BYOL → PAYG migration (Installation sheet).

    Conditions (UC 1.1):
    - u_hosting_zone in (Public Cloud, Private Cloud AVS) by default
    - inventory_status_standard != "License Included" (case-insensitive)
    - no_license_required (product) == 0
    """
    if target_zones is None:
        target_zones = DEFAULT_TARGET_ZONES

    no_lic_col = find_no_license_required_column(installation_df)

    for col in (COL_HOSTING, COL_INVENTORY_STATUS):
        if col not in installation_df.columns:
            raise ValueError(f"Required column missing for Rule 1: {col}")
    if no_lic_col is None:
        raise ValueError("Required column missing for Rule 1: no_license_required (or variant)")

    logger.info("Applying Azure PAYG eligibility rule (UC 1.1)...")

    inv_norm = installation_df[COL_INVENTORY_STATUS].astype(str).str.strip().str.lower()
    excluded_lower = excluded_inventory_phrase.strip().lower()

    mask = (
        (installation_df[COL_HOSTING].astype(str).str.strip().isin(target_zones))
        & (inv_norm != excluded_lower)
        & no_license_required_is_zero(installation_df[no_lic_col])
    )
    filtered_df = installation_df.loc[mask].copy()

    logger.info("Total BYOL → PAYG candidates found: %s", len(filtered_df))
    return filtered_df
