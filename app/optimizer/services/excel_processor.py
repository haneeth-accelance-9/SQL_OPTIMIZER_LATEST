"""
Excel processor: load sheets, normalize columns, build unified data for rules and cost calculation.
Sheet names are injected from settings (single source of truth); see analysis_service.get_sheet_config().
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _default_sheet(name: str, default: str) -> str:
    from django.conf import settings
    return getattr(settings, name, default)


# Default sheet name keys in settings (fallback used only if not injected by caller)
_DEFAULT_INSTALLATIONS = "MVP - Data 1 - Installation"
_DEFAULT_DEMAND = "MVP - Data 2 - Demand Results"
_DEFAULT_PRICES = "MVP - Data 3 - Prices"
_DEFAULT_OPTIMIZATION = "MVP - Data 4 - Optimization potential"
_DEFAULT_HELPFUL_REPORTS = "MVP - Data 5 - Helpful Reports"


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names: strip, lowercase, spaces to underscores."""
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace(" ", "_")
        .str.lower()
        .str.replace("(", "")
        .str.replace(")", "")
    )
    return df


def _detect_sheet(excel: pd.ExcelFile, *candidates: str) -> Optional[str]:
    """Return first sheet name that exists in the workbook."""
    sheet_names = set(excel.sheet_names)
    for name in candidates:
        if name in sheet_names:
            return name
    # Fallback: first sheet containing substring
    for name in excel.sheet_names:
        for c in candidates:
            if c.lower() in name.lower():
                return name
    return None


class ExcelProcessor:
    """
    Load and normalize Excel data from the standard workbook structure.
    Sheet names should be injected from settings (single source of truth).
    """

    def __init__(
        self,
        sheet_installations: Optional[str] = None,
        sheet_demand: Optional[str] = None,
        sheet_prices: Optional[str] = None,
        sheet_optimization: Optional[str] = None,
        sheet_helpful_reports: Optional[str] = None,
    ):
        self.sheet_installations = sheet_installations or _default_sheet("EXCEL_SHEET_INSTALLATIONS", _DEFAULT_INSTALLATIONS)
        self.sheet_demand = sheet_demand or _default_sheet("EXCEL_SHEET_DEMAND", _DEFAULT_DEMAND)
        self.sheet_prices = sheet_prices or _default_sheet("EXCEL_SHEET_PRICES", _DEFAULT_PRICES)
        self.sheet_optimization = sheet_optimization or _default_sheet("EXCEL_SHEET_OPTIMIZATION", _DEFAULT_OPTIMIZATION)
        self.sheet_helpful_reports = sheet_helpful_reports or _default_sheet("EXCEL_SHEET_HELPFUL_REPORTS", _DEFAULT_HELPFUL_REPORTS)

    def load_file(self, file_path: str) -> Dict[str, Any]:
        """
        Load Excel file and return dict with dataframes and metadata.
        Keys: installations, demand, prices, optimization, sheet_names_used, error.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}

        try:
            excel = pd.ExcelFile(file_path, engine="openpyxl")
            sheet_names = list(excel.sheet_names)
        except Exception as e:
            logger.exception("Failed to open Excel file")
            return {"error": str(e)}

        result = {
            "installations": None,
            "demand": None,
            "prices": None,
            "optimization": None,
            "helpful_reports": None,
            "sheet_names_used": {},
            "all_sheet_names": sheet_names,
        }

        # Installations (Data 1)
        inst_sheet = _detect_sheet(excel, self.sheet_installations, "Data 1", "Installation")
        if inst_sheet:
            try:
                df = pd.read_excel(excel, sheet_name=inst_sheet, engine="openpyxl")
                result["installations"] = normalize_columns(df)
                result["sheet_names_used"]["installations"] = inst_sheet
            except Exception as e:
                result["error"] = f"Sheet '{inst_sheet}': {e}"
                return result
        else:
            result["error"] = "Could not find Installations sheet (Data 1 / MVP - Data 1 - Installation)"
            return result

        # Demand (Data 2)
        demand_sheet = _detect_sheet(excel, self.sheet_demand, "Data 2", "Demand")
        if demand_sheet:
            try:
                df = pd.read_excel(excel, sheet_name=demand_sheet, engine="openpyxl")
                result["demand"] = normalize_columns(df)
                result["sheet_names_used"]["demand"] = demand_sheet
            except Exception as e:
                result["error"] = f"Sheet '{demand_sheet}': {e}"
                return result

        # Prices (Data 3)
        prices_sheet = _detect_sheet(excel, self.sheet_prices, "Data 3", "Prices")
        if prices_sheet:
            try:
                df = pd.read_excel(excel, sheet_name=prices_sheet, engine="openpyxl")
                result["prices"] = normalize_columns(df)
                result["sheet_names_used"]["prices"] = prices_sheet
            except Exception as e:
                result["error"] = f"Sheet '{prices_sheet}': {e}"
                return result

        # Optimization (Data 4) – optional
        opt_sheet = _detect_sheet(excel, self.sheet_optimization, "Data 4", "Optimization")
        if opt_sheet:
            try:
                df = pd.read_excel(excel, sheet_name=opt_sheet, engine="openpyxl")
                result["optimization"] = normalize_columns(df)
                result["sheet_names_used"]["optimization"] = opt_sheet
            except Exception as e:
                logger.warning("Optional optimization sheet failed: %s", e)

        # Helpful Reports (Data 5) – optional; used for actual demand and reporting
        reports_sheet = _detect_sheet(excel, self.sheet_helpful_reports, "Data 5", "Helpful Reports", "Reports")
        if reports_sheet:
            try:
                df = pd.read_excel(excel, sheet_name=reports_sheet, engine="openpyxl")
                result["helpful_reports"] = normalize_columns(df)
                result["sheet_names_used"]["helpful_reports"] = reports_sheet
            except Exception as e:
                logger.warning("Optional helpful reports sheet failed: %s", e)

        return result
