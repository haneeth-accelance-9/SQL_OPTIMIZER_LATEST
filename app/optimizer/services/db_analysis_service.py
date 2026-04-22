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
      - "Public Cloud"      (isin target in find_azure_payg_candidates)
      - "Private Cloud AVS" (isin target in find_azure_payg_candidates)
    Anything else is returned as-is (will not match the PAYG filter).
    """
    z = str(zone or "").strip().lower()
    if not z:
        return ""
    if "public" in z:
        return "Public Cloud"
    if "avs" in z or ("private" in z and "cloud" in z):
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
    """
    from optimizer.models import USUInstallation

    rows = USUInstallation.objects.filter(
        server__is_active=True
    ).select_related("server").values(
        "inv_status_std_name",
        "device_status",
        "no_license_required",
        "product_description",
        "product_edition",
        "product_family",
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
            # ── columns required by existing rules ───────────────────────────
            # Rule 1: exact isin(["Public Cloud", "Private Cloud AVS"])
            "u_hosting_zone": _normalize_hosting_zone(r["server__hosting_zone"]),
            # Rule 1: != "license included" (case-insensitive)
            "inventory_status_standard": r["inv_status_std_name"] or "",
            # Rule 2: == "retired" (case-insensitive) — prefer device_status,
            #         fall back to server-level status fields
            "install_status": _normalize_install_status(
                r["device_status"],
                r["server__installed_status_usu"],
                r["server__installed_status_boones"],
            ),
            # Both rules: == 0 means license IS required → include in candidates
            "no_license_required": nlr_num,
            # ── pass-through columns shown in result table ────────────────────
            "server_name":     r["server__server_name"] or "",
            "product_name":    r["product_description"] or "",
            "product_description": r["product_description"] or "",
            "product_edition": r["product_edition"] or "",
            "product_family":  r["product_family"] or "",
            "cpu_core_count":  float(r["cpu_core_count"] or 0),
            "cpu_socket_count": r["cpu_socket_count"] or 0,
            "topology_type":   r["topology_type"] or "",
            "environment":     r["server__environment"] or "",
            "cloud_provider":  r["server__cloud_provider"] or "",
            "is_cloud_device": r["server__is_cloud_device"],
        })

    return pd.DataFrame(records)


def _build_demand_df() -> pd.DataFrame:
    """Build a demand DataFrame from USUDemandDetail."""
    from optimizer.models import USUDemandDetail

    rows = USUDemandDetail.objects.filter(
        server__is_active=True
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


def compute_db_metrics() -> dict:
    """
    Run the full analysis pipeline using DB tables as data source.
    Reuses run_rules, compute_license_metrics, _calculate_savings, and
    _build_payg_zone_breakdown — identical to the upload path.
    """
    from optimizer.models import Server

    # ── Build DataFrames from DB ──────────────────────────────────────────────
    installations_df = _build_installations_df()
    demand_df = _build_demand_df()
    prices_df = _build_prices_df()
    prices_df = _prepare_db_prices_for_demand(demand_df, prices_df)

    total_devices = Server.objects.filter(is_active=True).count()

    # ── Run existing rule engine (same as upload path) ────────────────────────
    if not installations_df.empty:
        rule_results = run_rules(installations_df)
        rule_results["payg_zone_breakdown"] = _build_payg_zone_breakdown(
            installations_df,
            rule_results.get("azure_payg") or [],
        )
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

    # ── Run existing license metrics (same as upload path) ────────────────────
    license_metrics = compute_license_metrics(
        demand_df if not demand_df.empty else pd.DataFrame(),
        prices_df if not prices_df.empty else pd.DataFrame(),
    )

    # ── Calculate savings (same formula as upload path) ───────────────────────
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
    context.update(_calculate_savings(rule_results, license_metrics))

    # ── Strategy 3: CPU & RAM right-sizing ────────────────────────────────────
    context["rightsizing"] = compute_rightsizing_metrics()

    return context


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 3 – CPU & RAM Right-Sizing
# Data source: CPUUtilisation + Server
# ─────────────────────────────────────────────────────────────────────────────

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
                "Hosting Zone": server.hosting_zone or "",
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
        find_criticality_cpu_optimizations,
        find_criticality_ram_optimizations,
        find_lifecycle_risk_flags,
        find_physical_systems_flags,
    )

    workload_options = ["CPU", "RAM"]
    default_workload = "CPU"
    default_filter_by_workload = {
        "CPU": "PROD_CPU_Optimization",
        "RAM": "PROD_RAM_Optimization",
    }
    cpu_filter_options = [
        "PROD_CPU_Optimization",
        "PROD_CPU_Recommendation",
        "NONPROD_CPU_Optimization",
        "NONPROD_CPU_Recommendation",
    ]
    ram_filter_options = [
        "PROD_RAM_Optimization",
        "PROD_RAM_Recommendation",
        "NONPROD_RAM_Optimization",
        "NONPROD_RAM_Recommendation",
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
        "lifecycle_risk_flags": [], "lifecycle_count": 0,
        "physical_system_flags": [], "physical_count": 0,
        "workload_options": workload_options,
        "default_workload": default_workload,
        "default_filter_by_workload": default_filter_by_workload,
        "screen_filter_options": screen_filter_options,
        "cpu_filter_options": cpu_filter_options,
        "ram_filter_options": ram_filter_options,
        "screen_summaries": {"CPU": {}, "RAM": {}},
        "total_vcpu_reduction": 0,
        "total_ram_reduction_gib": 0.0,
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
    lifecycle_df = pd.DataFrame()
    physical_df = pd.DataFrame()

    try:
        cpu_df = find_cpu_rightsizing_optimizations(df)
    except Exception as exc:
        logger.exception("UC 3.1 CPU right-sizing rule failed: %s", exc)

    try:
        ram_df = find_ram_rightsizing_optimizations(df)
    except Exception as exc:
        logger.exception("UC 3.2 RAM right-sizing rule failed: %s", exc)

    try:
        crit_cpu_df = find_criticality_cpu_optimizations(df)
    except Exception as exc:
        logger.exception("UC 3.3 criticality CPU rule failed: %s", exc)

    try:
        crit_ram_df = find_criticality_ram_optimizations(df)
    except Exception as exc:
        logger.exception("UC 3.4 criticality RAM rule failed: %s", exc)

    try:
        lifecycle_df = find_lifecycle_risk_flags(df)
    except Exception as exc:
        logger.exception("Lifecycle risk flags failed: %s", exc)

    try:
        physical_df = find_physical_systems_flags(df)
    except Exception as exc:
        logger.exception("Physical systems flags failed: %s", exc)

    # ── Column subsets for display ─────────────────────────────────────────────
    _CPU_COLS = [
        "server_name",
        "is_virtual",
        "Environment",
        "Env_Type",
        "Avg_CPU_12m",
        "Peak_CPU_12m",
        "Current_vCPU",
        "Recommended_vCPU",
        "Potential_vCPU_Reduction",
        "CPU_Recommendation",
        "Optimization_Type",
        "Recommendation_Type",
    ]
    _RAM_COLS = [
        "server_name",
        "is_virtual",
        "Environment",
        "Env_Type",
        "Avg_FreeMem_12m",
        "Min_FreeMem_12m",
        "Current_RAM_GiB",
        "Recommended_RAM_GiB",
        "Potential_RAM_Reduction_GiB",
        "RAM_Recommendation",
        "Optimization_Type",
        "Recommendation_Type",
    ]
    _CRIT_CPU_COLS = [
        "server_name",
        "is_virtual",
        "Criticality",
        "Environment",
        "Avg_CPU_12m",
        "Peak_CPU_12m",
        "Current_vCPU",
        "Recommended_vCPU",
        "CPU_Recommendation",
        "Lifecycle_Flag",
        "Optimization_Type",
    ]
    _CRIT_RAM_COLS = [
        "server_name",
        "is_virtual",
        "Criticality",
        "Environment",
        "Avg_FreeMem_12m",
        "Min_FreeMem_12m",
        "Current_RAM_GiB",
        "Recommended_RAM_GiB",
        "RAM_Recommendation",
        "Lifecycle_Flag",
        "Optimization_Type",
    ]
    _LIFECYCLE_COLS = [
        "server_name",
        "is_virtual",
        "Criticality",
        "Environment",
        "Peak_CPU_12m",
        "Min_FreeMem_12m",
        "Lifecycle_Risk_Reasons",
        "Human_Review_Required",
    ]
    _PHYSICAL_COLS = [
        "server_name",
        "is_virtual",
        "Environment",
        "Criticality",
        "IsVirtual_Status",
        "Human_Review_Required",
        "Review_Reason",
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
        recommended = pd.to_numeric(prepared[recommended_col], errors="coerce").fillna(0)
        prepared[reduction_col] = (current - recommended).clip(lower=0)
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

    def _simple_records(src: pd.DataFrame, cols: list) -> list:
        if src.empty:
            return []
        keep = [c for c in cols if c in src.columns]
        return (
            src[keep]
            .round(2)
            .replace({float("nan"): None})
            .to_dict("records")
        )

    lifecycle_records = _simple_records(lifecycle_df, _LIFECYCLE_COLS)
    physical_records  = _simple_records(physical_df,  _PHYSICAL_COLS)

    # ── PROD / NON-PROD breakdown ──────────────────────────────────────────────
    def _filter_records(records: list, filter_value: str) -> list:
        filter_field = (
            "Recommendation_Type"
            if str(filter_value or "").endswith("_Recommendation")
            else "Optimization_Type"
        )
        return [
            record
            for record in records
            if str(record.get(filter_field) or "") == str(filter_value or "")
        ]

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
        rec = pd.to_numeric(src[rec_col], errors="coerce").fillna(0)
        return (cur - rec).clip(lower=0).sum()

    vcpu_reduction = int(_reduction(cpu_df, "Current_vCPU", "Recommended_vCPU"))
    ram_reduction = round(float(_reduction(ram_df, "Current_RAM_GiB", "Recommended_RAM_GiB")), 1)

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

    return {
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
        "lifecycle_risk_flags": lifecycle_records,
        "lifecycle_count": len(lifecycle_records),
        "physical_system_flags": physical_records,
        "physical_count": len(physical_records),
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
        "cpu_chart_data": cpu_chart,
        "ram_chart_data": ram_chart,
        "error": None,
    }


def _get_rightsizing_sheet_export_headers(sheet_key: str) -> list[str]:
    headers = list(RIGHTSIZING_REPORT_BASE_HEADERS)
    normalized_sheet_key = str(sheet_key or "").strip().upper()
    if normalized_sheet_key.endswith("_RECOMMENDATION"):
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

    filter_field = (
        "Recommendation_Type"
        if normalized_sheet_key.endswith("_Recommendation")
        else "Optimization_Type"
    )
    filtered_df = result_df[result_df[filter_field] == normalized_sheet_key].copy()

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
    from optimizer.models import Server

    installations_df = _build_installations_df()
    demand_df = _build_demand_df()
    prices_df = _build_prices_df()
    prices_df = _prepare_db_prices_for_demand(demand_df, prices_df)

    total_devices = Server.objects.filter(is_active=True).count()

    def _to_records(df: pd.DataFrame) -> list[dict]:
        if df is None or df.empty:
            return []
        return df.replace({pd.NA: None}).to_dict("records")

    if not installations_df.empty:
        azure_df = pd.DataFrame()
        retired_df = pd.DataFrame()
        azure_error = None
        retired_error = None

        try:
            azure_df = find_azure_payg_candidates_from_db(installations_df)
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

    license_metrics = compute_license_metrics(
        demand_df if not demand_df.empty else pd.DataFrame(),
        prices_df if not prices_df.empty else pd.DataFrame(),
    )

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
    context.update(_calculate_savings(rule_results, license_metrics))
    context["rightsizing"] = compute_rightsizing_metrics()
    return context
