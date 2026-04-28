"""
Rule engine: run optimization rules and compute license demand/cost from Excel data.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from optimizer.rules import find_azure_payg_candidates, find_retired_devices_with_installations

logger = logging.getLogger(__name__)

# Column name variants after normalization
DEVICE_KEY_ALIASES = ["device_key_center_device", "device_key", "center_device", "device_ci"]
PRODUCT_NAME_ALIASES = ["product_name_product", "product_name", "product"]
QUANTITY_ALIASES = ["quantity_effective", "quantityeffective", "quantity"]
PRICE_ALIASES = ["price", "yearly_price", "byol_price", "license_price", "price_per_year", "yearly_byol", "byol"]

# License type keywords (product name contains these, case-insensitive)
LICENSE_TYPE_STANDARD = "standard"
LICENSE_TYPE_DEVELOPER = "developer"
LICENSE_TYPE_ENTERPRISE = "enterprise"


def _find_column(df: pd.DataFrame, aliases: List[str]) -> str:
    """Return first column name that exists (case-insensitive match on normalized names)."""
    cols_lower = {c.lower(): c for c in df.columns}
    for a in aliases:
        al = a.lower().replace(" ", "_")
        if al in cols_lower:
            return cols_lower[al]
        for k in cols_lower:
            if al in k or k in al:
                return cols_lower[k]
    raise ValueError(f"Could not find column from {aliases} in {list(df.columns)}")


def _get_price_distribution_from_helpful_reports(
    helpful_reports_df: Optional[pd.DataFrame],
) -> Tuple[List[Dict[str, Any]], Optional[int], Optional[float]]:
    """
    Parse Helpful Reports sheet for Edition (Product) / Sum of Quantity (effective) / Sum of Total license price.
    Returns (price_distribution_list, grand_total_quantity, grand_total_cost).
    """
    if helpful_reports_df is None or helpful_reports_df.empty:
        return [], None, None
    df = helpful_reports_df.copy()
    cols_lower = {str(c).lower().replace(" ", "_"): c for c in df.columns}
    # Find edition/product column
    edition_col = None
    for key in ["edition_product", "edition", "product", "product_name", "license_type", "type"]:
        for ckey, col in cols_lower.items():
            if key in ckey or ckey in key:
                edition_col = col
                break
        if edition_col is not None:
            break
    # Find quantity column (Sum of Quantity (effective) -> sum_of_quantity_effective)
    qty_col = None
    for key in ["sum_of_quantity_effective", "quantity_effective", "sum_of_quantity", "quantity"]:
        for ckey, col in cols_lower.items():
            if key in ckey or ckey in key:
                qty_col = col
                break
        if qty_col is not None:
            break
    # Find total license price column
    price_col = None
    for key in ["sum_of_total_license_price", "total_license_price", "total_license_cost", "sum_of_total", "license_price"]:
        for ckey, col in cols_lower.items():
            if key in ckey or ckey in key:
                price_col = col
                break
        if price_col is not None:
            break
    if edition_col is None or qty_col is None or price_col is None:
        return [], None, None
    edition_vals = df[edition_col].astype(str).str.strip()
    qty_vals = pd.to_numeric(df[qty_col], errors="coerce").fillna(0)
    cost_vals = pd.to_numeric(df[price_col].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
    distribution = []
    grand_qty, grand_cost = None, None
    for i in range(len(df)):
        ed = edition_vals.iloc[i].lower()
        if "grand" in ed and "total" in ed:
            qv, cv = qty_vals.iloc[i], cost_vals.iloc[i]
            if not pd.isna(qv) and qv >= 0:
                grand_qty = int(qv)
            if not pd.isna(cv) and cv >= 0:
                grand_cost = float(cv)
            continue
        if ed in ("developer", "enterprise", "standard"):
            typ = ed.capitalize()
        elif "developer" in ed or "dev" in ed:
            typ = "Developer"
        elif "enterprise" in ed or "ent" in ed:
            typ = "Enterprise"
        elif "standard" in ed or "std" in ed:
            typ = "Standard"
        else:
            continue
        q = float(qty_vals.iloc[i])
        c = float(cost_vals.iloc[i])
        avg = round(c / q, 2) if q and q > 0 else 0
        distribution.append({"type": typ, "quantity": int(q), "total_cost": round(c, 2), "avg_price": avg})
    if not distribution:
        return [], grand_qty, grand_cost
    distribution.sort(key=lambda x: (x["type"] != "Standard", x["type"] != "Developer", x["type"] != "Enterprise", x["type"]))
    return distribution, grand_qty, grand_cost


def _get_actual_demand_from_helpful_reports(helpful_reports_df: Optional[pd.DataFrame]) -> Optional[int]:
    """
    Try to get actual total demand from the Helpful Reports sheet (sheet 5).
    Looks for numeric columns that might represent total demand / license count.
    Returns None if sheet is missing or no suitable value found.
    """
    if helpful_reports_df is None or helpful_reports_df.empty:
        return None
    df = helpful_reports_df.copy()
    demand_col_candidates = [
        "total_demand", "demand", "license_count", "total_licenses", "actual_demand",
        "total", "license_demand", "quantity_total", "total_quantity",
    ]
    cols_lower = {str(c).lower().replace(" ", "_"): c for c in df.columns}
    for key in demand_col_candidates:
        for ckey, col in cols_lower.items():
            if key in ckey or ckey in key:
                try:
                    vals = pd.to_numeric(df[col], errors="coerce").dropna()
                    if len(vals) > 0:
                        total = int(vals.sum()) if len(vals) > 1 else int(vals.iloc[0])
                        if total >= 0:
                            return total
                except (ValueError, TypeError):
                    pass
    # Fallback: first numeric column that looks like a total
    for col in df.columns:
        try:
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(vals) > 0 and vals.max() < 1e9:
                total = int(vals.sum()) if len(vals) > 1 else int(vals.iloc[0])
                if total >= 0:
                    return total
        except (ValueError, TypeError):
            pass
    return None


def _classify_license_type(product_name: str) -> str:
    """Classify product into Standard, Developer, or Enterprise from name. Default 'Other'."""
    if not product_name or not isinstance(product_name, str):
        return "Other"
    p = product_name.lower()

    # Explicit edition keywords take priority
    if LICENSE_TYPE_DEVELOPER in p or "dev " in p:
        return "Developer"
    if LICENSE_TYPE_ENTERPRISE in p or "ent " in p or "enterprise edition" in p:
        return "Enterprise"
    if LICENSE_TYPE_STANDARD in p or "std " in p or "standard edition" in p:
        return "Standard"

    # MySQL / Oracle MySQL product classification by product type
    if "mysql" in p or "oracle mysql" in p:
        # Enterprise-grade MySQL products
        if any(k in p for k in ("enterprise", "cluster", "cge", "monitor", "backup", "firewall")):
            return "Enterprise"
        # Developer / connectivity tools
        if any(k in p for k in ("connector", "odbc", "jdbc", "python", "net", ".net", "workbench", "router", "shell", "utilities")):
            return "Developer"
        # Everything else (server, community, …) → Standard
        return "Standard"

    return "Other"


def compute_license_metrics(
    demand_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    helpful_reports_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Compute total license demand and total license cost.
    Demand: prefer actual demand from Helpful Reports (sheet 5); else use demand row count to avoid overcounting.
    Formula: Total license price = (Product price × Quantity effective) / 2
    """
    if demand_df is None or demand_df.empty:
        return {
            "total_demand_quantity": 0,
            "total_license_cost": 0.0,
            "by_product": [],
            "demand_row_count": 0,
            "price_distribution": [],
            "cost_reduction_tips": [],
        }
    if prices_df is None or prices_df.empty:
        actual = _get_actual_demand_from_helpful_reports(helpful_reports_df)
        qty = int(actual) if actual is not None else int(demand_df.shape[0])
        return {
            "total_demand_quantity": qty,
            "total_license_cost": 0.0,
            "by_product": [],
            "demand_row_count": int(demand_df.shape[0]),
            "price_distribution": [],
            "cost_reduction_tips": [],
        }

    try:
        qty_col = _find_column(demand_df, QUANTITY_ALIASES + ["quantity"])
        prod_col = _find_column(demand_df, PRODUCT_NAME_ALIASES)
        price_col = _find_column(prices_df, PRICE_ALIASES + ["yearly_byol", "byol"])
    except ValueError as e:
        logger.warning("License metrics column resolution failed: %s", e)
        actual = _get_actual_demand_from_helpful_reports(helpful_reports_df)
        qty = int(actual) if actual is not None else int(demand_df.shape[0])
        return {
            "total_demand_quantity": qty,
            "total_license_cost": 0.0,
            "by_product": [],
            "demand_row_count": int(demand_df.shape[0]),
            "price_distribution": [],
            "cost_reduction_tips": [],
        }

    # Product column in prices (may differ from demand)
    try:
        prod_col_prices = _find_column(prices_df, PRODUCT_NAME_ALIASES)
    except ValueError:
        prod_col_prices = prices_df.columns[0]
    if price_col not in prices_df.columns:
        price_col = next((c for c in prices_df.columns if "price" in c.lower() or "cost" in c.lower()), prices_df.columns[1] if len(prices_df.columns) > 1 else prices_df.columns[0])

    # Prefer price distribution and totals from Helpful Reports (sheet 5) when available
    reports_distribution, reports_grand_qty, reports_grand_cost = _get_price_distribution_from_helpful_reports(helpful_reports_df)

    demand_df = demand_df.copy()
    prices_df = prices_df.copy()
    demand_df["_prod"] = demand_df[prod_col].astype(str).str.strip()
    prices_df["_prod"] = prices_df[prod_col_prices].astype(str).str.strip()

    merged = demand_df.merge(prices_df[["_prod", price_col]], on="_prod", how="left")
    qty = pd.to_numeric(merged[qty_col], errors="coerce").fillna(0)
    price = pd.to_numeric(merged[price_col], errors="coerce").fillna(0)
    merged["_line_cost"] = (price * qty) / 2.0
    # Use product_edition as the primary classification signal, but only when it
    # yields a meaningful result (non-Other). Fall back to product_name otherwise.
    if "product_edition" in merged.columns:
        def _classify_row(row):
            edition = str(row.get("product_edition") or "").strip()
            if edition:
                t = _classify_license_type(edition)
                if t != "Other":
                    return t
            return _classify_license_type(str(row["_prod"]))
        merged["_license_type"] = merged.apply(_classify_row, axis=1)
    else:
        merged["_license_type"] = merged["_prod"].map(_classify_license_type)

    total_cost = float(merged["_line_cost"].sum())
    sum_qty = float(qty.sum())
    demand_row_count = len(demand_df)

    if reports_grand_cost is not None:
        total_cost = reports_grand_cost
    if reports_grand_qty is not None:
        total_demand_quantity = int(reports_grand_qty)
    else:
        actual_demand = _get_actual_demand_from_helpful_reports(helpful_reports_df)
        if actual_demand is not None:
            total_demand_quantity = int(actual_demand)
        else:
            total_demand_quantity = int(demand_row_count)

    by_product = (
        merged.groupby("_prod")
        .agg({qty_col: "sum", "_line_cost": "sum"})
        .reset_index()
        .rename(columns={"_prod": "product", qty_col: "quantity", "_line_cost": "cost"})
    )
    by_product_list = by_product.to_dict("records")

    # Price distribution: from Helpful Reports if available, else from merged demand+prices
    if reports_distribution:
        price_distribution = reports_distribution
    else:
        type_agg = (
            merged.groupby("_license_type", dropna=False)
            .agg(quantity=(qty_col, "sum"), cost=("_line_cost", "sum"))
            .reset_index()
        )
        price_distribution = []
        for _, row in type_agg.iterrows():
            lic_type = str(row["_license_type"]) if row["_license_type"] else "Other"
            q = float(row["quantity"]) if row["quantity"] is not None else 0
            c = float(row["cost"]) if row["cost"] is not None else 0
            avg_price = round(c / q, 2) if q and q > 0 else 0
            price_distribution.append({
                "type": lic_type,
                "quantity": int(q),
                "total_cost": round(c, 2),
                "avg_price": avg_price,
            })
        price_distribution.sort(key=lambda x: (x["type"] != "Standard", x["type"] != "Developer", x["type"] != "Enterprise", x["type"]))

    # Ensure all four required types are always present (with zeroes if missing)
    _existing_types = {r["type"] for r in price_distribution}
    for _required_type in ("Standard", "Developer", "Enterprise", "Other"):
        if _required_type not in _existing_types:
            price_distribution.append({"type": _required_type, "quantity": 0, "total_cost": 0.00, "avg_price": 0.00})
    price_distribution.sort(key=lambda x: (x["type"] != "Standard", x["type"] != "Developer", x["type"] != "Enterprise", x["type"]))

    # Cost reduction tips based on data
    cost_reduction_tips = []
    dev_row = next((r for r in price_distribution if r["type"] == "Developer"), None)
    std_row = next((r for r in price_distribution if r["type"] == "Standard"), None)
    ent_row = next((r for r in price_distribution if r["type"] == "Enterprise"), None)
    if dev_row and dev_row["avg_price"] and (std_row or ent_row):
        if std_row and std_row["avg_price"] and dev_row["avg_price"] < std_row["avg_price"]:
            cost_reduction_tips.append(
                "Use Developer licenses for dev/test instead of Standard to save cost (Developer avg price is lower)."
            )
        if ent_row and ent_row["avg_price"] and dev_row["avg_price"] < ent_row["avg_price"]:
            cost_reduction_tips.append(
                "Use Developer licenses for non-production instead of Enterprise to reduce cost."
            )
    if std_row and ent_row and std_row["avg_price"] and ent_row["avg_price"] and std_row["avg_price"] < ent_row["avg_price"]:
        cost_reduction_tips.append(
            "Where Enterprise features are not required, prefer Standard over Enterprise to lower cost."
        )
    if not cost_reduction_tips:
        cost_reduction_tips.append(
            "Review PAYG candidates and retired devices to reduce over-licensing and align demand with actual usage."
        )

    return {
        "total_demand_quantity": total_demand_quantity,
        "total_license_cost": round(total_cost, 2),
        "by_product": by_product_list,
        "demand_row_count": demand_row_count,
        "price_distribution": price_distribution,
        "cost_reduction_tips": cost_reduction_tips,
    }


def run_rules(installations_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Run Rule 1 (Azure PAYG) and Rule 2 (Retired devices) on installations dataframe.
    Returns dict with keys: azure_payg, retired_devices, azure_payg_count, retired_count.
    """
    azure_payg = pd.DataFrame()
    retired_devices = pd.DataFrame()
    azure_error = None
    retired_error = None

    if installations_df is None or installations_df.empty:
        return {
            "azure_payg": [],
            "azure_payg_count": 0,
            "retired_devices": [],
            "retired_count": 0,
            "azure_error": "No installation data",
            "retired_error": "No installation data",
        }

    try:
        azure_df = find_azure_payg_candidates(installations_df)
        azure_payg = azure_df
    except Exception as e:
        logger.exception("Rule 1 (Azure PAYG) failed")
        azure_error = str(e)

    try:
        retired_df = find_retired_devices_with_installations(installations_df)
        retired_devices = retired_df
    except Exception as e:
        logger.exception("Rule 2 (Retired devices) failed")
        retired_error = str(e)

    def to_records(df: pd.DataFrame) -> List[Dict]:
        if df is None or df.empty:
            return []
        return df.replace({pd.NA: None}).to_dict("records")

    return {
        "azure_payg": to_records(azure_payg),
        "azure_payg_count": len(azure_payg),
        "retired_devices": to_records(retired_devices),
        "retired_count": len(retired_devices),
        "azure_error": azure_error,
        "retired_error": retired_error,
    }
