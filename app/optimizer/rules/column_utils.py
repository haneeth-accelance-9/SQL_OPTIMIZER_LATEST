"""
Shared column resolution for optimization rules (normalized Installation sheet).
"""
from typing import Optional

import pandas as pd


def find_no_license_required_column(installation_df: pd.DataFrame) -> Optional[str]:
    """
    Resolve the No License Required (Product) column after Excel normalization.
    Returns None if not found.
    """
    for c in installation_df.columns:
        c_lower = c.lower()
        if "no_license" in c_lower or "no_liscence" in c_lower:
            return c
    if "no_license_required_product" in installation_df.columns:
        return "no_license_required_product"
    if "no_license_required_(product)" in installation_df.columns:
        return "no_license_required_(product)"
    return None


def no_license_required_is_zero(series: pd.Series) -> pd.Series:
    """
    True where No License Required (Product) is exactly 0 (numeric).
    NaN and non-numeric values are False (do not match use case 'equals 0').
    """
    nlic = pd.to_numeric(series, errors="coerce")
    return nlic.eq(0) & nlic.notna()
