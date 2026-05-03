"""
Dynamic data-source adapter: builds DataFrames from DB tables and feeds them
into the existing Rule 1 / Rule 2 / compute_license_metrics / _calculate_savings pipeline.

Column mapping (DB → DataFrame column expected by rules):
  Server.hosting_zone            → u_hosting_zone
  USUInstallation.inv_status_std_name → inventory_status_standard
  USUInstallation.device_status  → install_status
  USUInstallation.no_license_required (bool) → no_license_required (0/1)
  USUDemandDetail.eff_quantity   → quantity_effective
  USUDemandDetail.product_description → product_name
  LicenseRule.cost_per_core_pair_eur  → price
"""
import logging
from datetime import date
from typing import Any

import pandas as pd
from django.utils import timezone

from optimizer.rules.rule_azure_payg import find_azure_payg_candidates_from_db
from optimizer.rules.rule_retired_devices import find_retired_devices_with_installations_from_db
from optimizer.services.analysis_service import _build_payg_zone_breakdown, _calculate_savings
from optimizer.services.rule_engine import compute_license_metrics, run_rules

logger = logging.getLogger(__name__)

# Product families that are stored in the DB for showcase/display purposes only.
# They must NOT be included in UC1 (PAYG), UC2 (Retired Assets), or the
# demand/cost metrics that feed savings calculations.
SHOWCASE_ONLY_PRODUCT_FAMILIES = frozenset({"Java"})
RIGHTSIZING_CPU_LICENSE_COSTS_EUR = {
    "enterprise": 2637.96,
    "standard": 687.96,
}

RIGHTSIZING_REPORT_METADATA_HEADERS = [
    "Number",
    "Server name",
    "is_virtual",
    "Cluster name",
    "Criticality",
    "Environment",
    "Hosting Zone",
    "Installed Status",
    "Apps ID Mapped",
    "App name",
    "Server Owner",
    "App Owner",
    "Business Owner",
    "Business Division",
    "Location",
    "Platform",
]

RIGHTSIZING_LOGICAL_CPU_HEADER_BY_MONTH = {
    date(2025, 3, 1): "Logical CPU Mar-25",
    date(2025, 4, 1): "Logical CPU  Apr-25",
    date(2025, 5, 1): "Logical CPU  May-25",
    date(2025, 6, 1): "Logical CPU  June-25",
    date(2025, 7, 1): "Logical CPU  July-25",
    date(2025, 8, 1): "Logical CPU Aug-25",
    date(2025, 9, 1): "Logical CPU Sept-25",
    date(2025, 10, 1): "Logical CPU Oct-25",
    date(2025, 11, 1): "Logical CPU Nov-25",
    date(2025, 12, 1): "Logical CPU Dec-25",
    date(2026, 1, 1): "Logical CPU Jan -26",
    date(2026, 2, 1): "Logical CPU Feb -26",
}

RIGHTSIZING_AVG_CPU_HEADER_BY_MONTH = {
    date(2025, 3, 1): "Average CPU Utilisation (%) - Mar-25",
    date(2025, 4, 1): "Average CPU Utilisation (%) - Apr-25",
    date(2025, 5, 1): "Average CPU Utilisation (%) - May-25",
    date(2025, 6, 1): "Average CPU Utilisation (%) - June-25",
    date(2025, 7, 1): "Average CPU Utilisation (%) - July-25",
    date(2025, 8, 1): "Average CPU Utilisation (%) - Aug-25",
    date(2025, 9, 1): "Average CPU Utilisation (%) - Sept-25",
    date(2025, 10, 1): "Average CPU Utilisation (%) - Oct-25",
    date(2025, 11, 1): "Average CPU Utilisation (%) - Nov-25",
    date(2025, 12, 1): "Average CPU Utilisation (%) - Dec-25",
    date(2026, 1, 1): "Average CPU Utilisation (%) - Jan-26",
    date(2026, 2, 1): "Average CPU Utilisation (%) - Feb-26",
}

RIGHTSIZING_MAX_CPU_HEADER_BY_MONTH = {
    date(2025, 3, 1): "Maximum CPU Utilisation (%) - Mar-25",
    date(2025, 4, 1): "Maximum CPU Utilisation (%) - Apr-25",
    date(2025, 5, 1): "Maximum CPU Utilisation (%) - May-25",
    date(2025, 6, 1): "Maximum CPU Utilisation (%) - June-25",
    date(2025, 7, 1): "Maximum CPU Utilisation (%) - July-25",
    date(2025, 8, 1): "Maximum CPU Utilisation (%) - Aug-25",
    date(2025, 9, 1): "Maximum CPU Utilisation (%) - Sept-25",
    date(2025, 10, 1): "Maximum CPU Utilisation (%) - Oct-25",
    date(2025, 11, 1): "Maximum CPU Utilisation (%) - Nov-25",
    date(2025, 12, 1): "Maximum CPU Utilisation (%) - Dec-25",
    date(2026, 1, 1): "Maximum CPU Utilisation (%) -Jan-26",
    date(2026, 2, 1): "Maximum CPU Utilisation (%) -Feb-26",
}

RIGHTSIZING_RAM_HEADER_BY_MONTH = {
    date(2025, 3, 1): "Physical RAM (GiB) - Mar-25",
    date(2025, 4, 1): "Physical RAM (GiB) - Apr-25",
    date(2025, 5, 1): "Physical RAM (GiB) - May-25",
    date(2025, 6, 1): "Physical RAM (GiB) - June-25",
    date(2025, 7, 1): "Physical RAM (GiB) - July-25",
    date(2025, 8, 1): "Physical RAM (GiB) -Aug-25",
    date(2025, 9, 1): "Physical RAM (GiB) -Sept-25",
    date(2025, 10, 1): "Physical RAM (GiB) -Oct-25",
    date(2025, 11, 1): "Physical RAM (GiB) -Nov-25",
    date(2025, 12, 1): "Physical RAM (GiB) -Dec-25",
    date(2026, 1, 1): "Physical RAM (GiB) -Jan-26",
    date(2026, 2, 1): "Physical RAM (GiB) -Feb-26",
}

RIGHTSIZING_AVG_FREE_MEM_HEADER_BY_MONTH = {
    date(2025, 3, 1): "Average free Memory (%) - Mar-25",
    date(2025, 4, 1): "Average free Memory (%) - Apr-25",
    date(2025, 5, 1): "Average free Memory (%) - May-25",
    date(2025, 6, 1): "Average free Memory (%) - June-25",
    date(2025, 7, 1): "Average free Memory (%) - July-25",
    date(2025, 8, 1): "Average free Memory (%) -Aug-25",
    date(2025, 9, 1): "Average free Memory (%) -Sept-25",
    date(2025, 10, 1): "Average free Memory (%) -Oct-25",
    date(2025, 11, 1): "Average free Memory (%) -Nov-25",
    date(2025, 12, 1): "Average free Memory (%) -Dec-25",
    date(2026, 1, 1): "Average free Memory (%) -Jan-26",
    date(2026, 2, 1): "Average free Memory (%) -Feb-26",
}

RIGHTSIZING_MAX_FREE_MEM_HEADER_BY_MONTH = {
    date(2025, 3, 1): "Maximum free Memory (%) - Mar-25",
    date(2025, 4, 1): "Maximum free Memory (%) - Apr-25",
    date(2025, 5, 1): "Maximum free Memory (%) - May-25",
    date(2025, 6, 1): "Maximum free Memory (%) - June-25",
    date(2025, 7, 1): "Maximum free Memory (%) - July-25",
    date(2025, 8, 1): "Maximum free Memory (%) - Aug-25",
    date(2025, 9, 1): "Maximum free Memory (%) - Sept-25",
    date(2025, 10, 1): "Maximum free Memory (%) - Oct-25",
    date(2025, 11, 1): "Maximum free Memory (%) - Nov-25",
    date(2025, 12, 1): "Maximum free Memory (%) - Dec-25",
    date(2026, 1, 1): "Maximum free Memory (%) - Jan-26",
    date(2026, 2, 1): "Maximum free Memory (%) - Feb-26",
}

RIGHTSIZING_MIN_FREE_MEM_HEADER_BY_MONTH = {
    date(2025, 3, 1): "Minimum free Memory (%) - Mar-24",
    date(2025, 4, 1): "Minimum free Memory (%) - Apr-25",
    date(2025, 5, 1): "Minimum free Memory (%) - May-25",
    date(2025, 6, 1): "Minimum free Memory (%) - June-25",
    date(2025, 7, 1): "Minimum free Memory (%) - July-25",
    date(2025, 8, 1): "Minimum free Memory (%) - Aug-25",
    date(2025, 9, 1): "Minimum free Memory (%) - Sept-25",
    date(2025, 10, 1): "Minimum free Memory (%) - Oct-25",
    date(2025, 11, 1): "Minimum free Memory (%) - Nov-25",
    date(2025, 12, 1): "Minimum free Memory (%) - Dec-25",
    date(2026, 1, 1): "Minimum free Memory (%) -Jan-26",
    date(2026, 2, 1): "Minimum free Memory (%) -Feb-26",
}

RIGHTSIZING_ALLOCATED_STORAGE_HEADER_BY_MONTH = {
    date(2026, 1, 1): "Allocated Storage (GB) -Jan - 26",
    date(2026, 2, 1): "Allocated Storage (GB) -Feb - 26",
}

RIGHTSIZING_USED_STORAGE_HEADER_BY_MONTH = {
    date(2026, 1, 1): "Used Storage (GB) -Jan-26",
    date(2026, 2, 1): "Used Storage (GB) -Feb-26",
}

RIGHTSIZING_REPORT_BASE_HEADERS = (
    RIGHTSIZING_REPORT_METADATA_HEADERS
    + list(RIGHTSIZING_LOGICAL_CPU_HEADER_BY_MONTH.values())
    + ["Unnamed: 28"]
    + list(RIGHTSIZING_AVG_CPU_HEADER_BY_MONTH.values())
    + ["Unnamed: 41"]
    + list(RIGHTSIZING_MAX_CPU_HEADER_BY_MONTH.values())
    + ["Unnamed: 54"]
    + list(RIGHTSIZING_RAM_HEADER_BY_MONTH.values())
    + ["Unnamed: 67"]
    + list(RIGHTSIZING_AVG_FREE_MEM_HEADER_BY_MONTH.values())
    + ["Unnamed: 80"]
    + list(RIGHTSIZING_MAX_FREE_MEM_HEADER_BY_MONTH.values())
    + ["Unnamed: 93"]
    + list(RIGHTSIZING_MIN_FREE_MEM_HEADER_BY_MONTH.values())
    + ["Unnamed: 106"]
    + list(RIGHTSIZING_ALLOCATED_STORAGE_HEADER_BY_MONTH.values())
    + ["Unnamed: 109"]
    + list(RIGHTSIZING_USED_STORAGE_HEADER_BY_MONTH.values())
    + [
        "Comments for Allocation (GB)",
        "Comments for Usage (GB)",
        "Decom check",
        "Avg_CPU_12m",
        "Peak_CPU_12m",
        "Avg_FreeMem_12m",
        "Min_FreeMem_12m",
        "Current_vCPU",
        "Current_RAM_GiB",
    ]
)


def _normalize_hosting_zone(zone: Any) -> str:
    """
    Map DB hosting_zone free-text to the exact labels the PAYG rule expects:
      - "Public Cloud"      → hosting_zone contains "public"
      - "Private Cloud AVS" → hosting_zone contains "avs" (must have AVS suffix)
    "Private Cloud" (without AVS) is intentionally NOT mapped to Private Cloud AVS.
    Anything else is returned as-is (will not match the PAYG filter).
    """
    z = str(zone or "").strip().lower()
    if not z:
        return ""
    if "public" in z:
        return "Public Cloud"
    if "avs" in z:
        return "Private Cloud AVS"
    return str(zone or "").strip()


def _normalize_install_status(device_status: Any, usu_status: Any, boones_status: Any) -> str:
    """
    Map DB status fields to the label the retired-devices rule expects: "retired".
    Rule does case-insensitive match, so just pick the first non-empty value.
    """
    for val in (device_status, usu_status, boones_status):
        s = str(val or "").strip()
        if s:
            return s  # rule lowercases, so any casing works
    return ""


def _build_installations_df() -> pd.DataFrame:
    """
    Build an installations DataFrame from USUInstallation + Server, matching
    the column schema expected by rule_azure_payg and rule_retired_devices.
    Excludes showcase-only product families (e.g. Java/Oracle) so they do not
    affect UC1 (PAYG), UC2 (Retired Assets), or savings calculations.
    """
    from optimizer.models import USUInstallation

    rows = USUInstallation.objects.filter(
        server__is_active=True
    ).exclude(
        product_family__in=SHOWCASE_ONLY_PRODUCT_FAMILIES
    ).select_related("server").order_by(
        "server__server_name", "product_description"
    ).values(
        "server_id",
        "inv_status_std_name",
        "device_status",
        "no_license_required",
        "manufacturer",
        "product_description",
        "product_edition",
        "product_family",
        "product_group",
        "license_metric",
        "cpu_core_count",
        "cpu_socket_count",
        "topology_type",
        "server__server_name",
        "server__hosting_zone",
        "server__environment",
        "server__cloud_provider",
        "server__is_cloud_device",
        "server__installed_status_usu",
        "server__installed_status_boones",
    )

    if not rows:
        return pd.DataFrame()

    records = []
    for r in rows:
        # no_license_required: True→1, False→0, None→NaN (excluded by rule)
        nlr = r["no_license_required"]
        nlr_num = (1 if nlr else 0) if nlr is not None else float("nan")

        records.append({
            "server_id":       str(r["server_id"]),
            # display order matches RULE1_DISPLAY_COLS / user reference
            "server_name":     r["server__server_name"] or "",
            "topology_type":   r["topology_type"] or "",
            "cpu_core_count":  float(r["cpu_core_count"] or 0),
            "cpu_socket_count": r["cpu_socket_count"] or 0,
            "manufacturer":    r["manufacturer"] or "",
            "product_family":  r["product_family"] or "",
            "product_group":   r["product_group"] or "",
            "product_description": r["product_description"] or "",
            "product_edition": r["product_edition"] or "",
            "license_metric":  r["license_metric"] or "",
            "no_license_required": nlr_num,
            "install_status": _normalize_install_status(
                r["device_status"],
                r["server__installed_status_usu"],
                r["server__installed_status_boones"],
            ),
            "no_license_required_product": nlr_num,
            "server_name":     r["server__server_name"] or "",
            "environment":     r["server__environment"] or "",
            "u_hosting_zone":  _normalize_hosting_zone(r["server__hosting_zone"]),
            "cloud_provider":  r["server__cloud_provider"] or "",
            "is_cloud_device": r["server__is_cloud_device"],
            "inventory_status_standard": r["inv_status_std_name"] or "",
            # duplicate kept for backward compat with rule logic
            "product_name":    r["product_description"] or "",
        })

    return pd.DataFrame(records)


# def _build_raw_installations_df() -> pd.DataFrame:
#     """
#     Raw export of USUInstallation + Server for the Rule 2 input data download.
#     Returns un-normalized field values matching the CSV format:
#     server_name, hosting_zone, installed_status_boones, installed_status_usu,
#     installation_id, product_family, no_license_required.
#     """
#     from optimizer.models import USUInstallation

#     rows = USUInstallation.objects.select_related("server").values(
#         "id",
#         "product_family",
#         "no_license_required",
#         "server__server_name",
#         "server__hosting_zone",
#         "server__installed_status_boones",
#         "server__installed_status_usu",
#     )

#     if not rows:
#         return pd.DataFrame()

#     records = [
#         {
#             "server_name":             r["server__server_name"],
#             "hosting_zone":            r["server__hosting_zone"],
#             "installed_status_boones": r["server__installed_status_boones"],
#             "installed_status_usu":    r["server__installed_status_usu"],
#             "installation_id":         str(r["id"]) if r["id"] else None,
#             "product_family":          r["product_family"],
#             "no_license_required":     r["no_license_required"],
#         }
#         for r in rows
#     ]

#     return pd.DataFrame(records, columns=[
#         "server_name",
#         "hosting_zone",
#         "installed_status_boones",
#         "installed_status_usu",
#         "installation_id",
#         "product_family",
#         "no_license_required",
#     ])


# def _build_raw_rule1_df() -> pd.DataFrame:
#     """
#     Raw export of USUInstallation + Server for the Rule 1 input data download.
#     Returns un-normalized field values for all columns Rule 1 filters on:
#     hosting_zone (raw, before normalization), inv_status_std_name, no_license_required.
#     """
#     from optimizer.models import USUInstallation

#     rows = USUInstallation.objects.select_related("server").values(
#         "id",
#         "product_family",
#         "no_license_required",
#         "inv_status_std_name",
#         "device_status",
#         "manufacturer",
#         "product_description",
#         "server__server_name",
#         "server__hosting_zone",
#         "server__installed_status_boones",
#         "server__installed_status_usu",
#         "server__environment",
#         "server__cloud_provider",
#         "server__is_cloud_device",
#     )

#     if not rows:
#         return pd.DataFrame()

#     records = [
#         {
#             "server_name":             r["server__server_name"],
#             "hosting_zone":            r["server__hosting_zone"],
#             "inv_status_std_name":     r["inv_status_std_name"],
#             "installed_status_usu":    r["server__installed_status_usu"],
#             "installed_status_boones": r["server__installed_status_boones"],
#             "installation_id":         str(r["id"]) if r["id"] else None,
#             "product_family":          r["product_family"],
#             "no_license_required":     r["no_license_required"],
#             "device_status":           r["device_status"],
#             "manufacturer":            r["manufacturer"],
#             "product_description":     r["product_description"],
#             "environment":             r["server__environment"],
#             "cloud_provider":          r["server__cloud_provider"],
#             "is_cloud_device":         r["server__is_cloud_device"],
#         }
#         for r in rows
#     ]

#     return pd.DataFrame(records, columns=[
#         "server_name",
#         "hosting_zone",
#         "inv_status_std_name",
#         "installed_status_usu",
#         "installed_status_boones",
#         "installation_id",
#         "product_family",
#         "no_license_required",
#         "device_status",
#         "manufacturer",
#         "product_description",
#         "environment",
#         "cloud_provider",
#         "is_cloud_device",
#     ])


def _build_demand_df() -> pd.DataFrame:
    """
    Build a demand DataFrame from USUDemandDetail.
    Excludes showcase-only product families (e.g. Java/Oracle) so they do not
    inflate Total Demand or Current Cost metrics.
    """
    from optimizer.models import USUDemandDetail

    rows = USUDemandDetail.objects.filter(
        server__is_active=True
    ).exclude(
        product_family__in=SHOWCASE_ONLY_PRODUCT_FAMILIES
    ).select_related("server").values(
        "product_description",
        "product_edition",
        "product_family",
        "eff_quantity",
        "cpu_core_count",
        "no_license_required",
    )

    if not rows:
        return pd.DataFrame()

    records = [
        {
            "product_name":       r["product_description"] or "",
            "quantity_effective": float(r["eff_quantity"] or 0),
            "cpu_core_count":     float(r["cpu_core_count"] or 0),
            "product_edition":    r["product_edition"] or "",
            "product_family":     r["product_family"] or "",
        }
        for r in rows
    ]
    return pd.DataFrame(records)


def _build_prices_df() -> pd.DataFrame:
    """Build a prices DataFrame from LicenseRule.cost_per_core_pair_eur."""
    from optimizer.models import LicenseRule

    rows = LicenseRule.objects.filter(
        is_active=True,
        cost_per_core_pair_eur__isnull=False,
    ).values("product_family", "rule_name", "cost_per_core_pair_eur")

    if not rows:
        return pd.DataFrame()

    records = [
        {
            "product_name": r["product_family"] or r["rule_name"] or "",
            "price":        float(r["cost_per_core_pair_eur"]),
        }
        for r in rows
    ]
    return pd.DataFrame(records)


def _prepare_db_prices_for_demand(
    demand_df: pd.DataFrame,
    prices_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Align DB price rows to demand products before handing off to the shared
    license-metrics engine.

    DB pricing is much smaller than the Excel price sheet:
    - a price may be stored against a product family (for example, "MySQL")
      while demand rows carry concrete product descriptions
    - some environments currently expose only a single active DB price row

    To preserve existing correct matches and avoid zero-cost dashboards:
    1. keep exact price rows as-is
    2. expand family-level prices to concrete demand product names
    3. only if nothing matches demand and there is exactly one active price row,
       broadcast that single price to demand product names as a narrow fallback
    """
    if demand_df is None or demand_df.empty or prices_df is None or prices_df.empty:
        return prices_df
    if "product_name" not in demand_df.columns or "product_name" not in prices_df.columns or "price" not in prices_df.columns:
        return prices_df

    def _key(value: Any) -> str:
        return str(value or "").strip().lower()

    aligned_prices = prices_df.copy()
    aligned_prices["product_name"] = aligned_prices["product_name"].fillna("").astype(str).str.strip()

    demand_names = demand_df.get("product_name", pd.Series(dtype=object)).fillna("").astype(str).str.strip()
    demand_families = demand_df.get("product_family", pd.Series(dtype=object)).fillna("").astype(str).str.strip()

    price_lookup = {
        _key(row["product_name"]): float(row["price"] or 0)
        for _, row in aligned_prices.iterrows()
        if _key(row["product_name"])
    }
    if not price_lookup:
        return aligned_prices

    alias_records = []
    if "product_family" in demand_df.columns:
        family_pairs = (
            demand_df[["product_name", "product_family"]]
            .fillna("")
            .drop_duplicates()
            .itertuples(index=False, name=None)
        )
        for product_name, product_family in family_pairs:
            product_name = str(product_name or "").strip()
            product_family = str(product_family or "").strip()
            if not product_name:
                continue
            if _key(product_name) in price_lookup:
                continue
            family_price = price_lookup.get(_key(product_family))
            if family_price is not None:
                alias_records.append({
                    "product_name": product_name,
                    "price": family_price,
                })

    if alias_records:
        aligned_prices = pd.concat(
            [aligned_prices, pd.DataFrame(alias_records)],
            ignore_index=True,
        )

    demand_keys = {_key(value) for value in demand_names.tolist() if _key(value)}
    price_keys = {_key(value) for value in aligned_prices["product_name"].tolist() if _key(value)}
    unique_price_rows = aligned_prices[["product_name", "price"]].drop_duplicates()

    if demand_keys.isdisjoint(price_keys) and len(unique_price_rows) == 1:
        fallback_price = float(unique_price_rows.iloc[0]["price"] or 0)
        fallback_records = [
            {"product_name": product_name, "price": fallback_price}
            for product_name in sorted({value for value in demand_names.tolist() if str(value).strip()})
        ]
        if fallback_records:
            logger.warning(
                "DB price data did not match demand products; broadcasting the single active DB price to %s demand products.",
                len(fallback_records),
            )
            aligned_prices = pd.concat(
                [aligned_prices, pd.DataFrame(fallback_records)],
                ignore_index=True,
            )

    return aligned_prices.drop_duplicates(subset=["product_name"], keep="first").reset_index(drop=True)


_INSTALLED_STATUSES = frozenset({"install", "installed"})

_UC1_VALID_LICENSE_TYPES = frozenset({"standard", "enterprise"})


def _filter_to_standard_enterprise_servers(df: pd.DataFrame) -> pd.DataFrame:
    """
    UC1 initial filter: keep only rows whose server has a product_edition of
    Standard or Enterprise (case-insensitive). Servers with any other license
    type (or no edition at all) are excluded before UC1 rules are applied.
    """
    if df.empty or "server_id" not in df.columns:
        return df

    all_server_ids = [s for s in df["server_id"].dropna().unique().tolist() if s]
    if not all_server_ids:
        return df

    edition_map = _build_server_product_edition_map(all_server_ids)

    valid_server_ids = {
        sid for sid in all_server_ids
        if edition_map.get(sid, "").strip().lower() in _UC1_VALID_LICENSE_TYPES
    }

    excluded = len(all_server_ids) - len(valid_server_ids)
    logger.info(
        "[UC1 PAYG] License-type pre-filter — total servers: %d | Standard/Enterprise: %d | other/none (excluded): %d",
        len(all_server_ids),
        len(valid_server_ids),
        excluded,
    )

    return df[df["server_id"].isin(valid_server_ids)].copy()


def _compute_device_cost_from_df(df: pd.DataFrame) -> float:
    """
    Sum of (Price × eff_quantity) / 2 over unique servers in df.
    Price comes from product_edition; eff_quantity from usu_demand_detail.
    """
    if df.empty or "server_id" not in df.columns:
        return 0.0
    server_ids = [s for s in df["server_id"].dropna().unique().tolist() if s]
    if not server_ids:
        return 0.0
    eff_qty_map = _build_server_eff_quantity_map(server_ids)
    edition_map = _build_server_product_edition_map(server_ids)
    total = 0.0
    for server_id in server_ids:
        eff_qty = float(eff_qty_map.get(server_id, 0) or 0)
        edition = edition_map.get(server_id, "")
        price = _get_rightsizing_cpu_license_cost_eur(edition)
        total += (price * eff_qty) / 2
    return round(total, 2)


def compute_retired_devices_extended_metrics(
    installations_df: pd.DataFrame,
    retired_df: pd.DataFrame,
) -> dict:
    """
    Extended UC2 metrics built from Server + usu_demand_detail.

    Step 1 – Total retired devices count
    Step 2 – Installed devices count  (install_status = 'install' / 'installed')
    Step 3 – Savings for Retired Devices: sum of (Price × eff_quantity) / 2
    Step 4 – Cost for Installed Devices: sum of (Price × eff_quantity) / 2
    """
    if retired_df is None:
        retired_df = pd.DataFrame()

    # Step 1 — total retired count
    total_retired_count = len(retired_df)

    # Step 2 — installed devices from full installations DataFrame
    if not installations_df.empty and "install_status" in installations_df.columns:
        install_mask = (
            installations_df["install_status"]
            .astype(str).str.strip().str.lower()
            .isin(_INSTALLED_STATUSES)
        )
        installed_df = installations_df[install_mask].copy()
        installed_count = len(installed_df)
    else:
        installed_df = pd.DataFrame()
        installed_count = 0

    # Step 3 & 4 — cost calculations
    retired_savings = _compute_device_cost_from_df(retired_df)
    installed_devices_cost = _compute_device_cost_from_df(installed_df)

    return {
        "total_retired_count": total_retired_count,
        "installed_count": installed_count,
        "retired_devices_savings_eur": retired_savings,
        "installed_devices_cost_eur": installed_devices_cost,
    }


def compute_azure_payg_cost_metrics(azure_payg_df: pd.DataFrame) -> dict:
    """
    UC1 PAYG cost metrics.

    Cost calculation — only servers that have Standard/Enterprise in usu_demand_detail
    (eff_quantity is sourced from demand_detail; servers without it have eff_quantity=0
    and are excluded to avoid misleading zero-cost rows).

    PROD candidates count — unique servers with environment='Production' across the
    full pre-filtered PAYG set (1281 rows), returned as a separate response field.

      Actual_Line_Cost per server = (Price × eff_quantity) / 2
      Total_PAYG_Cost             = SUM(Actual_Line_Cost)
      Total_PAYG_Savings          = 80% of Total_PAYG_Cost
    """
    if azure_payg_df.empty:
        return {
            "azure_payg_total_cost_eur": 0.0,
            "azure_payg_savings_eur": 0.0,
            "azure_payg_prod_candidates_count": 0,
        }

    from optimizer.models import USUDemandDetail

    all_server_ids = [s for s in azure_payg_df["server_id"].dropna().unique().tolist() if s]

    # Restrict cost calculation to servers with eff_quantity data (demand_detail only)
    demand_server_ids = set(
        str(sid)
        for sid in USUDemandDetail.objects
        .filter(server_id__in=all_server_ids)
        .filter(product_edition__iregex=r"^(standard|enterprise)$")
        .values_list("server_id", flat=True)
        .distinct()
    )
    cost_df = azure_payg_df[azure_payg_df["server_id"].isin(demand_server_ids)]
    total_cost = _compute_device_cost_from_df(cost_df)
    payg_savings = round(total_cost * 0.80, 2)

    # PROD candidates: unique servers with environment = 'Production'
    prod_candidates_count = 0
    if "environment" in azure_payg_df.columns:
        prod_mask = (
            azure_payg_df["environment"].astype(str).str.strip().str.lower() == "production"
        )
        prod_candidates_count = int(
            azure_payg_df.loc[prod_mask, "server_id"].dropna().nunique()
        )

    logger.info(
        "[UC1 PAYG] Cost servers (demand_detail Standard/Enterprise): %d | PROD candidates: %d",
        len(demand_server_ids),
        prod_candidates_count,
    )

    return {
        "azure_payg_total_cost_eur": total_cost,
        "azure_payg_savings_eur": payg_savings,
        "azure_payg_prod_candidates_count": prod_candidates_count,
    }


def compute_db_metrics() -> dict:
    """
    Run the full analysis pipeline using DB tables as data source.
    Reuses run_rules, compute_license_metrics, _calculate_savings, and
    _build_payg_zone_breakdown — identical to the upload path.
    """
    # ── Build DataFrames from DB ──────────────────────────────────────────────
    installations_df = _build_installations_df()
    demand_df = _build_demand_df()
    prices_df = _build_prices_df()
    prices_df = _prepare_db_prices_for_demand(demand_df, prices_df)

    from optimizer.models import USUDemandDetail as _UDD, USUInstallation as _USUInst
    _dd_server_ids = set(
        _UDD.objects
        .filter(server__is_active=True)
        .exclude(product_family__in=SHOWCASE_ONLY_PRODUCT_FAMILIES)
        .values_list("server_id", flat=True).distinct()
    )
    _inst_server_ids = set(
        _USUInst.objects
        .filter(server__is_active=True)
        .exclude(product_family__in=SHOWCASE_ONLY_PRODUCT_FAMILIES)
        .values_list("server_id", flat=True).distinct()
    )
    total_devices = len(_dd_server_ids | _inst_server_ids)

    # ── Run existing rule engine (same as upload path) ────────────────────────
    azure_df_uc1 = pd.DataFrame()
    retired_df_uc2 = pd.DataFrame()
    if not installations_df.empty:
        rule_results = run_rules(installations_df)
        rule_results["payg_zone_breakdown"] = _build_payg_zone_breakdown(
            installations_df,
            rule_results.get("azure_payg") or [],
        )
        try:
            uc1_installations_df = _filter_to_standard_enterprise_servers(installations_df)
            azure_df_uc1 = find_azure_payg_candidates_from_db(uc1_installations_df)
        except Exception:
            pass
        try:
            retired_df_uc2 = find_retired_devices_with_installations_from_db(installations_df)
        except Exception:
            pass
    else:
        logger.warning("No USUInstallation rows found — returning empty rule results.")
        rule_results = {
            "azure_payg": [],
            "azure_payg_count": 0,
            "retired_devices": [],
            "retired_count": 0,
            "azure_error": "No installation data found in database.",
            "retired_error": "No installation data found in database.",
            "payg_zone_breakdown": {
                "labels": ["Public Cloud", "Private Cloud AVS"],
                "current": [0, 0],
                "estimated": [0, 0],
            },
        }

    rule_results.update(compute_azure_payg_cost_metrics(azure_df_uc1))
    rule_results.update(
        compute_retired_devices_extended_metrics(installations_df, retired_df_uc2)
    )

    # ── Run existing license metrics (same as upload path) ────────────────────
    license_metrics = compute_license_metrics(
        demand_df if not demand_df.empty else pd.DataFrame(),
        prices_df if not prices_df.empty else pd.DataFrame(),
    )

    # ── Calculate savings (same formula as upload path) ───────────────────────
    rightsizing = compute_rightsizing_metrics()

    avg_cost_per_core_pair_eur = 0.0
    if not prices_df.empty and "price" in prices_df.columns:
        valid_prices = prices_df["price"].dropna()
        if not valid_prices.empty:
            avg_cost_per_core_pair_eur = round(float(valid_prices.mean()), 2)

    avg_cost_per_gib_eur = 0.0
    total_current_ram_gib = float(rightsizing.get("total_current_ram_gib") or 0)
    total_license_cost = float(license_metrics.get("total_license_cost") or 0)
    if total_current_ram_gib > 0 and total_license_cost > 0:
        avg_cost_per_gib_eur = round(total_license_cost / total_current_ram_gib, 2)

    rightsizing["avg_cost_per_core_pair_eur"] = avg_cost_per_core_pair_eur
    rightsizing["avg_cost_per_gib_eur"] = avg_cost_per_gib_eur
    _apply_rightsizing_cost_savings(rightsizing, avg_cost_per_gib_eur=avg_cost_per_gib_eur)

    rightsizing_for_savings = {
        "total_vcpu_reduction": rightsizing.get("total_vcpu_reduction") or 0,
        "total_ram_reduction_gib": rightsizing.get("total_ram_reduction_gib") or 0,
        "cpu_count": rightsizing.get("cpu_count") or 0,
        "ram_count": rightsizing.get("ram_count") or 0,
        "avg_cost_per_core_pair_eur": avg_cost_per_core_pair_eur,
        "avg_cost_per_gib_eur": avg_cost_per_gib_eur,
        "cpu_savings_eur": rightsizing.get("cpu_savings_eur"),
        "ram_savings_eur": rightsizing.get("ram_savings_eur"),
    }

    context = {
        "rule_results": rule_results,
        "license_metrics": license_metrics,
        "total_devices_analyzed": total_devices,
        "file_name": "",
        "sheet_names_used": {},
        "report_text": "",
        "report_used_fallback": False,
        "cost_reduction_ai_recommendations": "",
        "data_source": "database",
        "data_refreshed_at": timezone.now(),
        "rightsizing": rightsizing,
    }
    context.update(_calculate_savings(rule_results, license_metrics, rightsizing=rightsizing_for_savings))

    # Flatten per-strategy savings — UC1 uses new formula (80% of total line cost)
    rws = context.get("rule_wise_savings") or {}
    context["azure_payg_savings"] = float(rule_results.get("azure_payg_savings_eur") or 0)
    context["retired_devices_savings"] = float(rws.get("retired_devices") or 0)
    context["rightsizing_savings"] = float(rws.get("rightsizing") or 0)
    context["rightsizing_cpu_savings"] = float(rws.get("rightsizing_cpu") or 0)

    # ── Strategy 3: CPU & RAM right-sizing ────────────────────────────────────
    return context


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 3 – CPU & RAM Right-Sizing
# Data source: CPUUtilisation + Server
# ─────────────────────────────────────────────────────────────────────────────

def _classify_rightsizing_license_type(product_edition: Any) -> str:
    edition = str(product_edition or "").strip().lower()
    if not edition:
        return ""
    if edition == "enterprise" or "enterprise" in edition or "enterprise edition" in edition:
        return "enterprise"
    if edition == "standard" or "standard" in edition or "standard edition" in edition:
        return "standard"
    if edition in {"ent", "enterprise"} or " ent " in f" {edition} ":
        return "enterprise"
    if edition in {"std", "standard"} or " std " in f" {edition} ":
        return "standard"
    return ""


def _get_rightsizing_cpu_license_cost_eur(product_edition: Any) -> float:
    license_type = _classify_rightsizing_license_type(product_edition)
    return float(RIGHTSIZING_CPU_LICENSE_COSTS_EUR.get(license_type, 0.0))


def _coerce_non_negative_float(value: Any) -> float:
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0



def _calculate_cpu_rightsizing_costs_eur(
    product_edition: Any,
    *,
    eff_quantity=None,
    recommended_vcpu=None,
    reduction=None,
) -> tuple:
    """
    Returns (actual_line_cost, recommended_line_cost, savings).

    Actual_Line_Cost      = (Price × eff_quantity) / 2
    Recommended_Line_Cost = (Price × Recommended_vCPU) / 2
    Savings               = Actual_Line_Cost − Recommended_Line_Cost

    eff_quantity is sourced from usu_demand_detail.eff_quantity via server_id.
    Null/absent eff_quantity is treated as zero (no fallback).
    Price is determined by product_edition: Enterprise=2637.96, Standard=687.96.
    """
    price = _get_rightsizing_cpu_license_cost_eur(product_edition)
    effective_qty = _coerce_non_negative_float(eff_quantity)

    if recommended_vcpu is not None:
        try:
            recommended = max(float(recommended_vcpu), 0.0)
        except (TypeError, ValueError):
            recommended = 0.0
    elif reduction is not None:
        recommended = max(effective_qty - _coerce_non_negative_float(reduction), 0.0)
    else:
        recommended = effective_qty

    if price <= 0:
        return 0.0, 0.0, 0.0

    actual = round((price * effective_qty) / 2, 2)
    recommended_cost = round((price * recommended) / 2, 2)
    savings = round(max(actual - recommended_cost, 0.0), 2)
    return actual, recommended_cost, savings


def _calculate_cpu_rightsizing_savings_eur(
    product_edition: Any,
    *,
    eff_quantity=None,
    recommended_vcpu=None,
    reduction=None,
) -> float:
    _, _, savings = _calculate_cpu_rightsizing_costs_eur(
        product_edition,
        eff_quantity=eff_quantity,
        recommended_vcpu=recommended_vcpu,
        reduction=reduction,
    )
    return savings


def _build_server_product_edition_map(server_ids: list[Any]) -> dict[Any, str]:
    from optimizer.models import USUDemandDetail, USUInstallation

    unique_server_ids = list(dict.fromkeys(str(s) for s in (server_ids or []) if s))
    if not unique_server_ids:
        return {}

    def _select_best_editions(rows) -> dict[Any, str]:
        preferred: dict[Any, str] = {}
        fallback: dict[Any, str] = {}
        for row in rows:
            server_id = str(row["server_id"])
            edition = str(row.get("product_edition") or "").strip()
            if not edition:
                continue
            fallback.setdefault(server_id, edition)
            if server_id not in preferred and _get_rightsizing_cpu_license_cost_eur(edition) > 0:
                preferred[server_id] = edition
        return {
            server_id: preferred.get(server_id) or edition
            for server_id, edition in fallback.items()
        }

    demand_rows = (
        USUDemandDetail.objects.filter(server_id__in=unique_server_ids)
        .exclude(product_edition__isnull=True)
        .exclude(product_edition__exact="")
        .order_by("server_id", "-fetched_at")
        .values("server_id", "product_edition")
    )
    edition_map = _select_best_editions(demand_rows)

    remaining_server_ids = [server_id for server_id in unique_server_ids if server_id not in edition_map]
    if not remaining_server_ids:
        return edition_map

    installation_rows = (
        USUInstallation.objects.filter(server_id__in=remaining_server_ids)
        .exclude(product_edition__isnull=True)
        .exclude(product_edition__exact="")
        .order_by("server_id", "-fetched_at")
        .values("server_id", "product_edition")
    )
    edition_map.update(_select_best_editions(installation_rows))
    return edition_map


def _build_server_eff_quantity_map(server_ids: list[Any]) -> dict[Any, float]:
    """
    Returns {server_id: total eff_quantity} from usu_demand_detail.
    Sums eff_quantity across all demand rows for the same server.
    Null/missing values are treated as zero.
    """
    from django.db.models import Sum
    from optimizer.models import USUDemandDetail

    unique_ids = list(dict.fromkeys(str(s) for s in (server_ids or []) if s))
    if not unique_ids:
        return {}

    rows = (
        USUDemandDetail.objects
        .filter(server_id__in=unique_ids)
        .exclude(product_family__in=SHOWCASE_ONLY_PRODUCT_FAMILIES)
        .values("server_id")
        .annotate(total_eff_quantity=Sum("eff_quantity"))
    )
    return {
        str(row["server_id"]): float(row["total_eff_quantity"] or 0)
        for row in rows
    }


def _apply_rightsizing_cost_savings(rightsizing: dict, *, avg_cost_per_gib_eur: float = 0.0) -> dict:
    if not isinstance(rightsizing, dict):
        return rightsizing

    seen_lists: set[int] = set()

    def _visit_record_lists(keys, callback):
        for key in keys:
            records = rightsizing.get(key) or []
            if not isinstance(records, list) or id(records) in seen_lists:
                continue
            seen_lists.add(id(records))
            for record in records:
                if isinstance(record, dict):
                    callback(record)

    def _apply_cpu_cost(record: dict):
        actual, recommended_cost, savings = _calculate_cpu_rightsizing_costs_eur(
            record.get("product_edition"),
            eff_quantity=record.get("eff_quantity"),
            recommended_vcpu=record.get("Recommended_vCPU"),
            reduction=record.get("Potential_vCPU_Reduction"),
        )
        record["Actual_Line_Cost"] = actual
        record["Recommended_Line_Cost"] = recommended_cost
        record["Cost_Savings_EUR"] = savings

    def _apply_ram_cost(record: dict):
        reduction_value = _coerce_non_negative_float(record.get("Potential_RAM_Reduction_GiB"))
        record["Cost_Savings_EUR"] = round(reduction_value * float(avg_cost_per_gib_eur or 0), 2)

    _visit_record_lists(("cpu_optimizations", "cpu_candidates", "crit_cpu_optimizations"), _apply_cpu_cost)
    _visit_record_lists(("ram_optimizations", "ram_candidates", "crit_ram_optimizations"), _apply_ram_cost)

    def _sum_cost_savings(records) -> float:
        total = 0.0
        for record in records or []:
            total += _coerce_non_negative_float(record.get("Cost_Savings_EUR"))
        return round(total, 2)

    cpu_source_records = rightsizing.get("cpu_optimizations") or rightsizing.get("cpu_candidates") or []
    ram_source_records = rightsizing.get("ram_optimizations") or rightsizing.get("ram_candidates") or []
    rightsizing["cpu_savings_eur"] = _sum_cost_savings(cpu_source_records)
    rightsizing["ram_savings_eur"] = _sum_cost_savings(ram_source_records)
    rightsizing["total_cost_savings_eur"] = round(
        float(rightsizing.get("cpu_savings_eur") or 0) + float(rightsizing.get("ram_savings_eur") or 0),
        2,
    )
    return rightsizing


def _build_rightsizing_df() -> pd.DataFrame:
    """
    Build the wide rightsizing report DataFrame so exports can mirror the
    reference workbook while the rules still operate on derived 12-month fields.
    """
    from optimizer.models import CPUUtilisation

    def _set_if_present(record: dict, header_map: dict, month_key, value):
        header = header_map.get(month_key)
        if not header or value is None:
            return
        if record.get(header) in (None, ""):
            record[header] = value

    rows = list(
        CPUUtilisation.objects.filter(
            server__is_active=True,
            period_month__in=list(RIGHTSIZING_LOGICAL_CPU_HEADER_BY_MONTH.keys()),
        ).select_related("server")
    )

    if not rows:
        return pd.DataFrame()

    server_ids_for_rows = [util.server_id for util in rows]

    # UC3 license-type pre-filter: keep only servers with Standard or Enterprise
    # product_edition in usu_demand_detail (same rule as UC1).
    from optimizer.models import USUDemandDetail as _UDD
    _valid_server_ids = set(
        str(sid)
        for sid in _UDD.objects
        .filter(server_id__in=server_ids_for_rows)
        .filter(product_edition__iregex=r"^(standard|enterprise)$")
        .values_list("server_id", flat=True)
        .distinct()
    )
    total_before = len(set(str(sid) for sid in server_ids_for_rows))
    rows = [util for util in rows if str(util.server_id) in _valid_server_ids]
    logger.info(
        "[UC3 Rightsizing] License-type pre-filter — total servers: %d | Standard/Enterprise: %d | excluded: %d",
        total_before,
        len(_valid_server_ids),
        total_before - len(_valid_server_ids),
    )
    if not rows:
        return pd.DataFrame()
    server_ids_for_rows = [util.server_id for util in rows]

    product_edition_by_server_id = _build_server_product_edition_map(server_ids_for_rows)
    eff_quantity_by_server_id = _build_server_eff_quantity_map(server_ids_for_rows)
    server_records: dict = {}
    for util in rows:
        server = util.server
        if server.id not in server_records:
            record = {header: None for header in RIGHTSIZING_REPORT_BASE_HEADERS}
            record.update({
                "Number": server.boones_number or "",
                "Server name": server.server_name or "",
                "is_virtual": server.is_virtual,
                "Cluster name": server.cluster_name or "",
                "Criticality": server.criticality or "",
                "Environment": server.environment or "",
                "Hosting Zone": _normalize_hosting_zone(server.hosting_zone or ""),
                "Installed Status": server.installed_status_boones or server.installed_status_usu or "",
                "Apps ID Mapped": server.apps_id or "",
                "App name": server.app_name or "",
                "Server Owner": server.server_owner_email or "",
                "App Owner": server.app_owner_email or "",
                "Business Owner": server.business_owner_email or "",
                "Business Division": server.business_division or "",
                "Location": server.location or "",
                "Platform": server.platform or "",
                "Comments for Allocation (GB)": "",
                "Comments for Usage (GB)": "",
                "Decom check": "",
                "server_name": server.server_name or "",
                "hosting_zone": _normalize_hosting_zone(server.hosting_zone or ""),
                "installed_status_usu": server.installed_status_usu or "",
                "product_edition": product_edition_by_server_id.get(str(server.id), ""),
                "eff_quantity": eff_quantity_by_server_id.get(str(server.id), 0.0),
            })
            server_records[server.id] = record

        record = server_records[server.id]
        month_key = util.period_month
        _set_if_present(record, RIGHTSIZING_LOGICAL_CPU_HEADER_BY_MONTH, month_key, util.logical_cpu_count)
        _set_if_present(record, RIGHTSIZING_AVG_CPU_HEADER_BY_MONTH, month_key, util.avg_cpu_pct)
        _set_if_present(record, RIGHTSIZING_MAX_CPU_HEADER_BY_MONTH, month_key, util.max_cpu_pct)
        _set_if_present(record, RIGHTSIZING_RAM_HEADER_BY_MONTH, month_key, util.physical_ram_gib)
        _set_if_present(record, RIGHTSIZING_AVG_FREE_MEM_HEADER_BY_MONTH, month_key, util.avg_free_memory_pct)
        _set_if_present(record, RIGHTSIZING_MAX_FREE_MEM_HEADER_BY_MONTH, month_key, util.max_free_memory_pct)
        _set_if_present(record, RIGHTSIZING_MIN_FREE_MEM_HEADER_BY_MONTH, month_key, util.min_free_memory_pct)
        _set_if_present(record, RIGHTSIZING_ALLOCATED_STORAGE_HEADER_BY_MONTH, month_key, util.allocated_storage_gb)
        _set_if_present(record, RIGHTSIZING_USED_STORAGE_HEADER_BY_MONTH, month_key, util.used_storage_gb)

    # Enrich each server record with product fields from USUInstallation
    from optimizer.models import USUInstallation as _USUInst
    _product_qs = (
        _USUInst.objects
        .filter(server_id__in=list(server_records.keys()))
        .exclude(product_family__in=SHOWCASE_ONLY_PRODUCT_FAMILIES)
        .values("server_id", "product_family", "product_group", "product_description")
    )
    _product_lookup: dict = {}
    for _row in _product_qs:
        _sid = _row["server_id"]
        if _sid not in _product_lookup:
            _product_lookup[_sid] = {
                "product_family": _row.get("product_family") or "",
                "product_group": _row.get("product_group") or "",
                "product_name": _row.get("product_description") or "",
                "product_description": _row.get("product_description") or "",
            }
    for _sid, _rec in server_records.items():
        _prod = _product_lookup.get(_sid, {})
        _rec["product_family"] = _prod.get("product_family", "")
        _rec["product_group"] = _prod.get("product_group", "")
        _rec["product_name"] = _prod.get("product_name", "")
        _rec["product_description"] = _prod.get("product_description", "")

    df = pd.DataFrame(server_records.values())
    for header in RIGHTSIZING_REPORT_BASE_HEADERS:
        if header not in df.columns:
            df[header] = None

    from optimizer.rules.rightsizing import compute_utilisation_metrics

    df = compute_utilisation_metrics(df)
    df["server_name"] = df.get("Server name", "").fillna("")
    return df


def compute_rightsizing_metrics() -> dict:
    """
    Run UC 3.1–3.4 right-sizing rules + lifecycle/physical flags using CPUUtilisation data.
    Returns a dict consumed by the results view and dashboard template.
    """
    from optimizer.rules.rightsizing import (
        find_cpu_rightsizing_optimizations,
        find_ram_rightsizing_optimizations,
        find_criticality_cpu_downsize_optimizations,
        find_criticality_cpu_upsize_optimizations,
        find_criticality_ram_downsize_optimizations,
        find_criticality_ram_upsize_optimizations,
    )

    workload_options = ["CPU", "RAM"]
    default_workload = "CPU"
    default_filter_by_workload = {
        "CPU": "PROD_CPU_Rightsizing",
        "RAM": "PROD_RAM_Rightsizing",
    }
    cpu_filter_options = [
        "PROD_CPU_Rightsizing",
        "NONPROD_CPU_Rightsizing",
    ]
    ram_filter_options = [
        "PROD_RAM_Rightsizing",
        "NONPROD_RAM_Rightsizing",
    ]
    screen_filter_options = {
        "CPU": cpu_filter_options,
        "RAM": ram_filter_options,
    }

    _EMPTY: dict = {
        "cpu_optimizations": [],
        "cpu_candidates": [], "cpu_count": 0,
        "cpu_optimization_count": 0,
        "cpu_prod_count": 0, "cpu_nonprod_count": 0,
        "cpu_prod_optimization_count": 0, "cpu_nonprod_optimization_count": 0,
        "ram_optimizations": [],
        "ram_candidates": [], "ram_count": 0,
        "ram_optimization_count": 0,
        "ram_prod_count": 0, "ram_nonprod_count": 0,
        "ram_prod_optimization_count": 0, "ram_nonprod_optimization_count": 0,
        "crit_cpu_optimizations": [], "crit_cpu_count": 0,
        "crit_ram_optimizations": [], "crit_ram_count": 0,
        "workload_options": workload_options,
        "default_workload": default_workload,
        "default_filter_by_workload": default_filter_by_workload,
        "screen_filter_options": screen_filter_options,
        "cpu_filter_options": cpu_filter_options,
        "ram_filter_options": ram_filter_options,
        "screen_summaries": {
            "CPU": {k: {"count": 0, "prod_count": 0, "nonprod_count": 0, "reduction_total": 0.0} for k in cpu_filter_options},
            "RAM": {k: {"count": 0, "prod_count": 0, "nonprod_count": 0, "reduction_total": 0.0} for k in ram_filter_options},
        },
        "cpu_savings_eur": 0.0,
        "ram_savings_eur": 0.0,
        "total_cost_savings_eur": 0.0,
        "total_vcpu_reduction": 0,
        "total_ram_reduction_gib": 0.0,
        "total_current_ram_gib": 0.0,
        "cpu_chart_data": [],
        "ram_chart_data": [],
        "error": None,
    }

    df = _build_rightsizing_df()
    if df.empty:
        logger.warning("No CPUUtilisation rows — right-sizing skipped.")
        _EMPTY["error"] = "No utilisation data found in the database."
        return _EMPTY

    # ── Run rules ─────────────────────────────────────────────────────────────
    cpu_df = pd.DataFrame()
    ram_df = pd.DataFrame()
    crit_cpu_df = pd.DataFrame()
    crit_ram_df = pd.DataFrame()
    try:
        cpu_df = find_cpu_rightsizing_optimizations(df)
        if not cpu_df.empty:
            before = len(cpu_df)
            # Filter 1: no-op rows where recommendation equals current
            cpu_df = cpu_df[
                cpu_df["Recommended_vCPU"].notna() &
                (cpu_df["Recommended_vCPU"] != cpu_df["Current_vCPU"])
            ]
            # Filter 2: neither current nor recommended can be below 4
            cpu_df = cpu_df[
                (cpu_df["Current_vCPU"] >= 4) &
                (cpu_df["Recommended_vCPU"] >= 4)
            ]
            logger.info(
                "[UC3 CPU] Post-rule filter: %d → %d rows (removed %d)",
                before, len(cpu_df), before - len(cpu_df),
            )
    except Exception as exc:
        logger.exception("UC 3.1 CPU right-sizing rule failed: %s", exc)

    try:
        ram_df = find_ram_rightsizing_optimizations(df)
        if not ram_df.empty:
            before = len(ram_df)
            # Filter 1: no-op rows where recommendation equals current
            ram_df = ram_df[
                ram_df["Recommended_RAM_GiB"].notna() &
                (ram_df["Recommended_RAM_GiB"] != ram_df["Current_RAM_GiB"])
            ]
            # Filter 2: neither current nor recommended can be below 8
            ram_df = ram_df[
                (ram_df["Current_RAM_GiB"] >= 8) &
                (ram_df["Recommended_RAM_GiB"] >= 8)
            ]
            logger.info(
                "[UC3 RAM] Post-rule filter: %d → %d rows (removed %d)",
                before, len(ram_df), before - len(ram_df),
            )
    except Exception as exc:
        logger.exception("UC 3.2 RAM right-sizing rule failed: %s", exc)

    try:
        crit_cpu_df = pd.concat(
            [find_criticality_cpu_downsize_optimizations(df),
             find_criticality_cpu_upsize_optimizations(df)],
            ignore_index=True,
        )
        if not crit_cpu_df.empty:
            before = len(crit_cpu_df)
            crit_cpu_df = crit_cpu_df[
                crit_cpu_df["Recommended_vCPU"].notna() &
                (crit_cpu_df["Recommended_vCPU"] != crit_cpu_df["Current_vCPU"])
            ]
            crit_cpu_df = crit_cpu_df[
                (crit_cpu_df["Current_vCPU"] >= 4) &
                (crit_cpu_df["Recommended_vCPU"] >= 4)
            ]
            logger.info(
                "[UC3 Crit-CPU] Post-rule filter: %d → %d rows (removed %d)",
                before, len(crit_cpu_df), before - len(crit_cpu_df),
            )
    except Exception as exc:
        logger.exception("UC 3.3 criticality CPU rule failed: %s", exc)

    try:
        crit_ram_df = pd.concat(
            [find_criticality_ram_downsize_optimizations(df),
             find_criticality_ram_upsize_optimizations(df)],
            ignore_index=True,
        )
        if not crit_ram_df.empty:
            before = len(crit_ram_df)
            crit_ram_df = crit_ram_df[
                crit_ram_df["Recommended_RAM_GiB"].notna() &
                (crit_ram_df["Recommended_RAM_GiB"] != crit_ram_df["Current_RAM_GiB"])
            ]
            crit_ram_df = crit_ram_df[
                (crit_ram_df["Current_RAM_GiB"] >= 8) &
                (crit_ram_df["Recommended_RAM_GiB"] >= 8)
            ]
            logger.info(
                "[UC3 Crit-RAM] Post-rule filter: %d → %d rows (removed %d)",
                before, len(crit_ram_df), before - len(crit_ram_df),
            )
    except Exception as exc:
        logger.exception("UC 3.4 criticality RAM rule failed: %s", exc)

    # ── Column subsets for display ─────────────────────────────────────────────
    _CPU_COLS = [
        "server_name",
        "product_family",
        "product_name",
        "product_description",
        "hosting_zone",
        "installed_status_usu",
        "is_virtual",
        "Environment",
        "Env_Type",
        "Avg_CPU_12m",
        "Peak_CPU_12m",
        "Current_vCPU",
        "Recommended_vCPU",
        "Potential_vCPU_Reduction",
        "CPU_Recommendation",
        "product_edition",
        "eff_quantity",
        "Actual_Line_Cost",
        "Recommended_Line_Cost",
        "Cost_Savings_EUR",
        "Optimization_Type",
        "Recommendation_Type",
    ]
    _RAM_COLS = [
        "server_name",
        "product_family",
        "product_name",
        "product_description",
        "hosting_zone",
        "installed_status_usu",
        "is_virtual",
        "Environment",
        "Env_Type",
        "Avg_FreeMem_12m",
        "Min_FreeMem_12m",
        "Current_RAM_GiB",
        "Recommended_RAM_GiB",
        "Potential_RAM_Reduction_GiB",
        "RAM_Recommendation",
        "Cost_Savings_EUR",
        "Optimization_Type",
        "Recommendation_Type",
    ]
    _CRIT_CPU_COLS = [
        "server_name",
        "product_family",
        "product_description",
        "is_virtual",
        "Criticality",
        "Environment",
        "Avg_CPU_12m",
        "Peak_CPU_12m",
        "Current_vCPU",
        "Recommended_vCPU",
        "CPU_Recommendation",
        "product_edition",
        "eff_quantity",
        "Actual_Line_Cost",
        "Recommended_Line_Cost",
        "Cost_Savings_EUR",
        "Lifecycle_Flag",
        "Optimization_Type",
    ]
    _CRIT_RAM_COLS = [
        "server_name",
        "product_family",
        "product_description",
        "is_virtual",
        "Criticality",
        "Environment",
        "Avg_FreeMem_12m",
        "Min_FreeMem_12m",
        "Current_RAM_GiB",
        "Recommended_RAM_GiB",
        "RAM_Recommendation",
        "Cost_Savings_EUR",
        "Lifecycle_Flag",
        "Optimization_Type",
    ]
    def _to_records(
        src: pd.DataFrame,
        cols: list,
        *,
        current_col: str,
        recommended_col: str,
        reduction_col: str,
    ) -> list:
        if src.empty:
            return []
        prepared = src.copy()
        current = pd.to_numeric(prepared[current_col], errors="coerce").fillna(0)
        # Don't fill NaN recommended with 0 — rows without a valid recommendation
        # have no quantified savings and should contribute 0, not their full current value.
        recommended = pd.to_numeric(prepared[recommended_col], errors="coerce")
        prepared[reduction_col] = (current - recommended).clip(lower=0).fillna(0)
        keep = [c for c in cols if c in prepared.columns]
        return (
            prepared[keep]
            .round(2)
            .replace({float("nan"): None})
            .to_dict("records")
        )

    cpu_records = _to_records(
        cpu_df,
        _CPU_COLS,
        current_col="Current_vCPU",
        recommended_col="Recommended_vCPU",
        reduction_col="Potential_vCPU_Reduction",
    )
    ram_records = _to_records(
        ram_df,
        _RAM_COLS,
        current_col="Current_RAM_GiB",
        recommended_col="Recommended_RAM_GiB",
        reduction_col="Potential_RAM_Reduction_GiB",
    )
    crit_cpu_records = _to_records(
        crit_cpu_df,
        _CRIT_CPU_COLS,
        current_col="Current_vCPU",
        recommended_col="Recommended_vCPU",
        reduction_col="Potential_vCPU_Reduction",
    )
    crit_ram_records = _to_records(
        crit_ram_df,
        _CRIT_RAM_COLS,
        current_col="Current_RAM_GiB",
        recommended_col="Recommended_RAM_GiB",
        reduction_col="Potential_RAM_Reduction_GiB",
    )

    # ── PROD / NON-PROD breakdown ──────────────────────────────────────────────
    def _filter_records(records: list, filter_value: str) -> list:
        fv = str(filter_value or "")
        if fv.endswith("_Rightsizing"):
            env_type = "NON-PROD" if fv.startswith("NONPROD_") else "PROD"
            return [r for r in records if str(r.get("Env_Type") or "") == env_type]
        filter_field = (
            "Recommendation_Type"
            if fv.endswith("_Recommendation")
            else "Optimization_Type"
        )
        return [r for r in records if str(r.get(filter_field) or "") == fv]

    def _screen_summary(records: list, filter_value: str, reduction_key: str) -> dict:
        selected = _filter_records(records, filter_value)
        reduction_total = 0.0
        for record in selected:
            try:
                reduction_total += float(record.get(reduction_key) or 0)
            except (TypeError, ValueError):
                continue
        return {
            "count": len(selected),
            "prod_count": sum(str(record.get("Env_Type") or "") == "PROD" for record in selected),
            "nonprod_count": sum(str(record.get("Env_Type") or "") == "NON-PROD" for record in selected),
            "reduction_total": round(reduction_total, 1),
        }

    cpu_screen_summaries = {
        filter_name: _screen_summary(cpu_records, filter_name, "Potential_vCPU_Reduction")
        for filter_name in cpu_filter_options
    }
    ram_screen_summaries = {
        filter_name: _screen_summary(ram_records, filter_name, "Potential_RAM_Reduction_GiB")
        for filter_name in ram_filter_options
    }

    def _count(src, val):
        if src.empty or "Env_Type" not in src.columns:
            return 0
        return int((src["Env_Type"] == val).sum())

    # ── Reduction totals ───────────────────────────────────────────────────────
    def _reduction(src, cur_col, rec_col):
        if src.empty or cur_col not in src.columns or rec_col not in src.columns:
            return 0
        cur = pd.to_numeric(src[cur_col], errors="coerce").fillna(0)
        rec = pd.to_numeric(src[rec_col], errors="coerce")
        return (cur - rec).clip(lower=0).fillna(0).sum()

    vcpu_reduction = int(_reduction(cpu_df, "Current_vCPU", "Recommended_vCPU"))
    ram_reduction = round(float(_reduction(ram_df, "Current_RAM_GiB", "Recommended_RAM_GiB")), 1)
    total_current_ram_gib = round(float(pd.to_numeric(df.get("Current_RAM_GiB"), errors="coerce").fillna(0).sum()), 1) if "Current_RAM_GiB" in df.columns else 0.0

    # ── Chart data: all servers (not just candidates) for context ─────────────
    cpu_chart: list = []
    ram_chart: list = []
    if not cpu_df.empty:
        for _, row in cpu_df[
            [
                "server_name",
                "Environment",
                "Env_Type",
                "Optimization_Type",
                "Recommendation_Type",
                "Avg_CPU_12m",
                "Peak_CPU_12m",
                "Current_vCPU",
            ]
        ].dropna(subset=["Avg_CPU_12m"]).head(300).iterrows():
            cpu_chart.append({
                "name": str(row.get("server_name", "")),
                "env": str(row.get("Environment", "")),
                "env_type": str(row.get("Env_Type", "")),
                "optimization_type": str(row.get("Optimization_Type", "")),
                "recommendation_type": str(row.get("Recommendation_Type", "")),
                "avg": round(float(row["Avg_CPU_12m"]), 1),
                "peak": round(float(row.get("Peak_CPU_12m") or 0), 1),
                "vcpu": int(row.get("Current_vCPU") or 0),
            })
    if not ram_df.empty:
        for _, row in ram_df[
            [
                "server_name",
                "Environment",
                "Env_Type",
                "Optimization_Type",
                "Recommendation_Type",
                "Avg_FreeMem_12m",
                "Min_FreeMem_12m",
                "Current_RAM_GiB",
            ]
        ].dropna(subset=["Avg_FreeMem_12m"]).head(300).iterrows():
            ram_chart.append({
                "name": str(row.get("server_name", "")),
                "env": str(row.get("Environment", "")),
                "env_type": str(row.get("Env_Type", "")),
                "optimization_type": str(row.get("Optimization_Type", "")),
                "recommendation_type": str(row.get("Recommendation_Type", "")),
                "avg_free": round(float(row["Avg_FreeMem_12m"]), 1),
                "min_free": round(float(row.get("Min_FreeMem_12m") or 0), 1),
                "ram": round(float(row.get("Current_RAM_GiB") or 0), 1),
            })

    result = {
        "cpu_optimizations": cpu_records,
        "cpu_candidates": cpu_records,
        "cpu_optimization_count": len(cpu_records),
        "cpu_count": len(cpu_records),
        "cpu_prod_optimization_count": _count(cpu_df, "PROD"),
        "cpu_prod_count": _count(cpu_df, "PROD"),
        "cpu_nonprod_optimization_count": _count(cpu_df, "NON-PROD"),
        "cpu_nonprod_count": _count(cpu_df, "NON-PROD"),
        "ram_optimizations": ram_records,
        "ram_candidates": ram_records,
        "ram_optimization_count": len(ram_records),
        "ram_count": len(ram_records),
        "ram_prod_optimization_count": _count(ram_df, "PROD"),
        "ram_prod_count": _count(ram_df, "PROD"),
        "ram_nonprod_optimization_count": _count(ram_df, "NON-PROD"),
        "ram_nonprod_count": _count(ram_df, "NON-PROD"),
        "crit_cpu_optimizations": crit_cpu_records,
        "crit_cpu_count": len(crit_cpu_records),
        "crit_ram_optimizations": crit_ram_records,
        "crit_ram_count": len(crit_ram_records),
        "workload_options": workload_options,
        "default_workload": default_workload,
        "default_filter_by_workload": default_filter_by_workload,
        "screen_filter_options": screen_filter_options,
        "cpu_filter_options": cpu_filter_options,
        "ram_filter_options": ram_filter_options,
        "screen_summaries": {
            "CPU": cpu_screen_summaries,
            "RAM": ram_screen_summaries,
        },
        "total_vcpu_reduction": vcpu_reduction,
        "total_ram_reduction_gib": ram_reduction,
        "total_current_ram_gib": total_current_ram_gib,
        "cpu_chart_data": cpu_chart,
        "ram_chart_data": ram_chart,
        "error": None,
    }
    _apply_rightsizing_cost_savings(result, avg_cost_per_gib_eur=0.0)
    return result


# Download sheet keys use "Rightsizing" suffix; the rule stamps "Optimization" suffix.
# This map translates sheet keys back to the actual Optimization_Type column values.
_SHEET_KEY_TO_OPT_TYPE = {
    "PROD_CPU_Rightsizing":    "PROD_CPU_Optimization",
    "NONPROD_CPU_Rightsizing": "NONPROD_CPU_Optimization",
    "PROD_RAM_Rightsizing":    "PROD_RAM_Optimization",
    "NONPROD_RAM_Rightsizing": "NONPROD_RAM_Optimization",
}


def _get_rightsizing_sheet_export_headers(sheet_key: str) -> list[str]:
    headers = list(RIGHTSIZING_REPORT_BASE_HEADERS)
    normalized_sheet_key = str(sheet_key or "").strip().upper()
    if "_RAM_" in normalized_sheet_key:
        headers.extend(["RAM_Recommendation", "Recommended_RAM_GiB"])
    else:
        headers.extend(["CPU_Recommendation", "Recommended_vCPU"])
    return headers


def build_rightsizing_sheet_export(sheet_key: str) -> pd.DataFrame:
    """
    Build a workbook-style export for one Strategy 3 sheet.
    Returns a DataFrame with the same column order as the reference report.
    """
    from optimizer.rules.rightsizing import (
        find_cpu_rightsizing_optimizations,
        find_ram_rightsizing_optimizations,
    )

    normalized_sheet_key = str(sheet_key or "").strip()
    headers = _get_rightsizing_sheet_export_headers(normalized_sheet_key)
    source_df = _build_rightsizing_df()
    if source_df.empty:
        return pd.DataFrame(columns=headers)

    if "_RAM_" in normalized_sheet_key.upper():
        result_df = find_ram_rightsizing_optimizations(source_df)
    else:
        result_df = find_cpu_rightsizing_optimizations(source_df)

    # Translate the "Rightsizing" sheet key to the actual column value stamped by the rule
    actual_filter_value = _SHEET_KEY_TO_OPT_TYPE.get(normalized_sheet_key, normalized_sheet_key)
    filtered_df = result_df[result_df["Optimization_Type"] == actual_filter_value].copy()

    # Apply the same post-rule filters used on the dashboard so export matches screen data
    if "_RAM_" in normalized_sheet_key.upper():
        if not filtered_df.empty and "Recommended_RAM_GiB" in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df["Recommended_RAM_GiB"].notna()
                & (filtered_df["Recommended_RAM_GiB"] != filtered_df["Current_RAM_GiB"])
                & (filtered_df["Current_RAM_GiB"] >= 8)
                & (filtered_df["Recommended_RAM_GiB"] >= 8)
            ]
    else:
        if not filtered_df.empty and "Recommended_vCPU" in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df["Recommended_vCPU"].notna()
                & (filtered_df["Recommended_vCPU"] != filtered_df["Current_vCPU"])
                & (filtered_df["Current_vCPU"] >= 4)
                & (filtered_df["Recommended_vCPU"] >= 4)
            ]

    filtered_df = filtered_df.reindex(columns=headers).copy()
    numeric_columns = filtered_df.select_dtypes(include="number").columns
    if len(numeric_columns):
        filtered_df.loc[:, numeric_columns] = filtered_df[numeric_columns].round(2)
    return filtered_df.where(pd.notna(filtered_df), None)


def get_latest_agentic_context() -> dict:
    """
    Build a context dict from the most-recent completed AgentRun and its
    OptimizationCandidates + OptimizationDecisions.

    Returns an empty dict with has_agentic_data=False when no completed run exists.
    """
    from optimizer.models import AgentRun, OptimizationCandidate, OptimizationDecision

    run = (
        AgentRun.objects.filter(status=AgentRun.STATUS_COMPLETED)
        .order_by("-started_at")
        .first()
    )
    if not run:
        return {"has_agentic_data": False}

    candidates_qs = (
        OptimizationCandidate.objects.filter(agent_run=run)
        .select_related("server", "rule")
        .order_by("-estimated_saving_eur")
    )

    candidates = []
    for c in candidates_qs:
        decision = None
        try:
            decision = {
                "decision": c.decision.decision,
                "decided_by_email": c.decision.decided_by_email or "",
                "decided_at": c.decision.decided_at.isoformat() if c.decision.decided_at else None,
                "decision_notes": c.decision.decision_notes or "",
                "snow_ticket_id": c.decision.snow_ticket_id or "",
            }
        except OptimizationDecision.DoesNotExist:
            pass
        candidates.append({
            "id": str(c.id),
            "use_case": c.use_case,
            "server_name": c.server.server_name if c.server else "",
            "rule_name": c.rule.rule_name if c.rule else "",
            "rule_code": c.rule.rule_code if c.rule else "",
            "recommendation": c.recommendation,
            "rationale": c.rationale,
            "estimated_saving_eur": float(c.estimated_saving_eur) if c.estimated_saving_eur is not None else None,
            "status": c.status,
            "detected_on": c.detected_on.isoformat() if c.detected_on else None,
            "decision": decision,
        })

    total_saving = sum(
        c["estimated_saving_eur"] for c in candidates if c["estimated_saving_eur"] is not None
    )
    accepted = [c for c in candidates if c["status"] == OptimizationCandidate.STATUS_ACCEPTED]
    pending = [c for c in candidates if c["status"] == OptimizationCandidate.STATUS_PENDING]
    rejected = [c for c in candidates if c["status"] == OptimizationCandidate.STATUS_REJECTED]

    return {
        "has_agentic_data": True,
        "agent_run": {
            "id": str(run.id),
            "run_label": run.run_label,
            "status": run.status,
            "triggered_by": run.triggered_by,
            "servers_evaluated": run.servers_evaluated,
            "candidates_found": run.candidates_found,
            "llm_model": run.llm_model,
            "llm_tokens_used": run.llm_tokens_used,
            "llm_used": run.llm_used,
            "run_duration_sec": float(run.run_duration_sec) if run.run_duration_sec else None,
            "agent_endpoint": run.agent_endpoint,
            "report_markdown": run.report_markdown,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "error_detail": run.error_detail,
        },
        "candidates": candidates,
        "candidates_total": len(candidates),
        "candidates_accepted": len(accepted),
        "candidates_pending": len(pending),
        "candidates_rejected": len(rejected),
        "total_estimated_saving_eur": round(total_saving, 2),
    }


def get_agent_run_list(limit: int = 20) -> list:
    """Return a summary list of recent agent runs for the API."""
    from optimizer.models import AgentRun

    runs = AgentRun.objects.order_by("-started_at")[:limit]
    result = []
    for run in runs:
        result.append({
            "id": str(run.id),
            "run_label": run.run_label,
            "status": run.status,
            "triggered_by": run.triggered_by,
            "servers_evaluated": run.servers_evaluated,
            "candidates_found": run.candidates_found,
            "llm_model": run.llm_model,
            "llm_tokens_used": run.llm_tokens_used,
            "llm_used": run.llm_used,
            "run_duration_sec": float(run.run_duration_sec) if run.run_duration_sec else None,
            "agent_endpoint": run.agent_endpoint,
            "has_report": bool(run.report_markdown),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "error_detail": run.error_detail,
        })
    return result


def compute_live_db_metrics() -> dict:
    """
    Live dashboard/report metrics sourced only from the current database tables.

    Rule 1 and Rule 2 both read normalized installation data built from Server
    and USUInstallation, and cost/savings are derived from USUDemandDetail and
    LicenseRule.
    """
    installations_df = _build_installations_df()
    demand_df = _build_demand_df()
    prices_df = _build_prices_df()
    prices_df = _prepare_db_prices_for_demand(demand_df, prices_df)

    from optimizer.models import USUDemandDetail as _UDD, USUInstallation as _USUInst
    _dd_server_ids = set(
        _UDD.objects
        .filter(server__is_active=True)
        .exclude(product_family__in=SHOWCASE_ONLY_PRODUCT_FAMILIES)
        .values_list("server_id", flat=True).distinct()
    )
    _inst_server_ids = set(
        _USUInst.objects
        .filter(server__is_active=True)
        .exclude(product_family__in=SHOWCASE_ONLY_PRODUCT_FAMILIES)
        .values_list("server_id", flat=True).distinct()
    )
    total_devices = len(_dd_server_ids | _inst_server_ids)

    def _to_records(df: pd.DataFrame) -> list[dict]:
        if df is None or df.empty:
            return []
        return df.replace({pd.NA: None}).to_dict("records")

    azure_df = pd.DataFrame()
    retired_df = pd.DataFrame()

    if not installations_df.empty:
        azure_error = None
        retired_error = None

        try:
            uc1_installations_df = _filter_to_standard_enterprise_servers(installations_df)
            azure_df = find_azure_payg_candidates_from_db(uc1_installations_df)
        except Exception as exc:
            logger.exception("Rule 1 (Azure PAYG) failed against DB-backed installation data.")
            azure_error = str(exc)

        try:
            retired_df = find_retired_devices_with_installations_from_db(installations_df)
        except Exception as exc:
            logger.exception("Rule 2 (Retired devices) failed against DB-backed installation data.")
            retired_error = str(exc)

        rule_results = {
            "azure_payg": _to_records(azure_df),
            "azure_payg_count": len(azure_df),
            "retired_devices": _to_records(retired_df),
            "retired_count": len(retired_df),
            "azure_error": azure_error,
            "retired_error": retired_error,
        }
        rule_results["payg_zone_breakdown"] = _build_payg_zone_breakdown(
            installations_df,
            rule_results.get("azure_payg") or [],
        )
    else:
        logger.warning("No USUInstallation rows found - returning empty rule results.")
        rule_results = {
            "azure_payg": [],
            "azure_payg_count": 0,
            "retired_devices": [],
            "retired_count": 0,
            "azure_error": "No installation data found in database.",
            "retired_error": "No installation data found in database.",
            "payg_zone_breakdown": {
                "labels": ["Public Cloud", "Private Cloud AVS"],
                "current": [0, 0],
                "estimated": [0, 0],
            },
        }

    rule_results.update(
        compute_retired_devices_extended_metrics(installations_df, retired_df)
    )
    rule_results.update(compute_azure_payg_cost_metrics(azure_df))

    license_metrics = compute_license_metrics(
        demand_df if not demand_df.empty else pd.DataFrame(),
        prices_df if not prices_df.empty else pd.DataFrame(),
    )

    # Strategy 3: run rightsizing first so we can include its savings in the totals
    rightsizing = compute_rightsizing_metrics()

    # Derive avg cost per core pair from the active LicenseRule prices
    avg_cost_per_core_pair_eur = 0.0
    if not prices_df.empty and "price" in prices_df.columns:
        valid_prices = prices_df["price"].dropna()
        if not valid_prices.empty:
            avg_cost_per_core_pair_eur = round(float(valid_prices.mean()), 2)

    # Approximate RAM unit cost using observed license spend spread across the
    # currently allocated RAM footprint in the live rightsizing inventory.
    avg_cost_per_gib_eur = 0.0
    total_current_ram_gib = float(rightsizing.get("total_current_ram_gib") or 0)
    total_license_cost = float(license_metrics.get("total_license_cost") or 0)
    if total_current_ram_gib > 0 and total_license_cost > 0:
        avg_cost_per_gib_eur = round(total_license_cost / total_current_ram_gib, 2)

    rightsizing["avg_cost_per_core_pair_eur"] = avg_cost_per_core_pair_eur
    rightsizing["avg_cost_per_gib_eur"] = avg_cost_per_gib_eur
    _apply_rightsizing_cost_savings(rightsizing, avg_cost_per_gib_eur=avg_cost_per_gib_eur)

    rightsizing_for_savings = {
        "total_vcpu_reduction": rightsizing.get("total_vcpu_reduction") or 0,
        "total_ram_reduction_gib": rightsizing.get("total_ram_reduction_gib") or 0,
        "cpu_count": rightsizing.get("cpu_count") or 0,
        "ram_count": rightsizing.get("ram_count") or 0,
        "avg_cost_per_core_pair_eur": avg_cost_per_core_pair_eur,
        "avg_cost_per_gib_eur": avg_cost_per_gib_eur,
        "cpu_savings_eur": rightsizing.get("cpu_savings_eur"),
        "ram_savings_eur": rightsizing.get("ram_savings_eur"),
    }

    context = {
        "rule_results": rule_results,
        "license_metrics": license_metrics,
        "total_devices_analyzed": total_devices,
        "file_name": "",
        "sheet_names_used": {},
        "report_text": "",
        "report_used_fallback": False,
        "cost_reduction_ai_recommendations": "",
        "data_source": "database",
        "data_refreshed_at": timezone.now(),
    }
    context.update(_calculate_savings(rule_results, license_metrics, rightsizing=rightsizing_for_savings))
    context["rightsizing"] = rightsizing

    # Flatten per-strategy savings so build_agent_strategy_results_payload can read them
    rws = context.get("rule_wise_savings") or {}
    context["azure_payg_savings"] = float(rule_results.get("azure_payg_savings_eur") or 0)
    context["retired_devices_savings"] = float(rws.get("retired_devices") or 0)
    context["rightsizing_savings"] = float(rws.get("rightsizing") or 0)
    context["rightsizing_cpu_savings"] = float(rws.get("rightsizing_cpu") or 0)

    return context
