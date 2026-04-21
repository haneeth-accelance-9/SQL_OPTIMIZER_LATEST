"""
Rule 2: Software installations on retired devices.

Production results are driven from live database tables:
- server
- usu_installation

The core filter remains dataframe-based so it can be reused safely, and this
module also exposes a DB-backed helper for the live dashboard/results flow.

Enterprise use case (UC 1.2):
- Install_Status equals "retired"
- No License Required (Product) equals 0
"""
import logging
from typing import Optional

import pandas as pd

from optimizer.rules.column_utils import find_no_license_required_column, no_license_required_is_zero

logger = logging.getLogger(__name__)

COL_INSTALL_STATUS = "install_status"
RETIRED_STATUS = "retired"


def find_retired_devices_with_installations(
    installation_df: pd.DataFrame,
    retired_status: str = RETIRED_STATUS,
) -> pd.DataFrame:
    """
    Identify installations on devices marked as retired (UC 1.2).

    Conditions:
    - install_status equals "retired" (case-insensitive on value)
    - no_license_required (product) == 0
    """
    status_col = None
    for c in installation_df.columns:
        if c.replace(" ", "_").lower() == "install_status":
            status_col = c
            break
    if status_col is None:
        raise ValueError("Column 'install_status' not found for Rule 2")

    no_lic_col = find_no_license_required_column(installation_df)
    if no_lic_col is None:
        raise ValueError("Required column missing for Rule 2: no_license_required (or variant)")

    logger.info("Applying rule: Software installations on retired devices (UC 1.2)")

    retired_mask = (
        installation_df[status_col].astype(str).str.strip().str.lower() == retired_status.lower()
    ) & no_license_required_is_zero(installation_df[no_lic_col])

    retired = installation_df.loc[retired_mask].copy()

    logger.info("Total retired devices with software installations: %s", len(retired))
    return retired


def find_retired_devices_with_installations_from_db(
    installation_df: Optional[pd.DataFrame] = None,
    retired_status: str = RETIRED_STATUS,
) -> pd.DataFrame:
    """
    DB-backed Rule 2 entrypoint used by the live dashboard/results flow.

    When no dataframe is supplied, this pulls normalized installation data from
    the current Server and USUInstallation tables through the shared DB adapter,
    then applies the same Rule 2 filter logic.
    """
    if installation_df is None:
        from optimizer.services.db_analysis_service import _build_installations_df

        installation_df = _build_installations_df()

    return find_retired_devices_with_installations(
        installation_df,
        retired_status=retired_status,
    )
