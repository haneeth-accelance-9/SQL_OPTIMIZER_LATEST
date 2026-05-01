"""
Rule 1: Azure BYOL to PAYG Optimization.

Production results are driven from live database tables:
- server
- usu_installation

The core filter remains dataframe-based so it can be reused safely, and this
module also exposes a DB-backed helper for the live dashboard/results flow.

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

DEFAULT_TARGET_ZONES = ["Public Cloud", "Private Cloud AVS"]
EXCLUDED_INVENTORY_PHRASE = "license included"


def find_azure_payg_candidates(
    installation_df: pd.DataFrame,
    target_zones: Optional[List[str]] = None,
    excluded_inventory_phrase: str = EXCLUDED_INVENTORY_PHRASE,
) -> pd.DataFrame:
    """
    Identify Azure devices eligible for BYOL to PAYG migration from normalized
    installation data.

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

    # UC 1.1 conditions:
    # 1. u_hosting_zone IN (Public Cloud, Private Cloud AVS)
    # 2. inv_status_std_name != "License Included" (case-insensitive)
    # 3. no_license_required = FALSE (== 0)
    mask = (
        (installation_df[COL_HOSTING].astype(str).str.strip().isin(target_zones))
        & (inv_norm != excluded_lower)
        & no_license_required_is_zero(installation_df[no_lic_col])
    )
    sort_cols = [c for c in ("server_name", "product_description") if c in installation_df.columns]
    filtered_df = (
        installation_df.loc[mask]
        .sort_values(sort_cols, ignore_index=True)
        .copy()
    ) if sort_cols else installation_df.loc[mask].copy()

    logger.info("Total BYOL to PAYG candidates found: %s", len(filtered_df))
    return filtered_df


def find_azure_payg_candidates_from_db(
    installation_df: Optional[pd.DataFrame] = None,
    target_zones: Optional[List[str]] = None,
    excluded_inventory_phrase: str = EXCLUDED_INVENTORY_PHRASE,
) -> pd.DataFrame:
    """
    DB-backed Rule 1 entrypoint used by the live dashboard/results flow.

    When no dataframe is supplied, this pulls normalized installation data from
    the current Server and USUInstallation tables through the shared DB adapter,
    then applies the same Rule 1 filter logic.
    """
    if installation_df is None:
        from optimizer.services.db_analysis_service import _build_installations_df

        installation_df = _build_installations_df()

    return find_azure_payg_candidates(
        installation_df,
        target_zones=target_zones,
        excluded_inventory_phrase=excluded_inventory_phrase,
    )
