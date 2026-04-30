"""
Rule 3: VM Right-Sizing (CPU & RAM).

Identifies virtual machines that are over-provisioned in CPU or RAM based on
12-month utilisation metrics. Expects normalized column names with monthly
Average/Peak CPU and Average/Minimum free Memory columns.

Enterprise use cases:
  UC 3.1 – CPU Right-Sizing: reduce vCPU count for under-utilised VMs.
  UC 3.2 – RAM Right-Sizing: reduce RAM allocation for under-utilised VMs.
  UC 3.3 – Criticality-Aware CPU Optimization (split into 2 outputs):
      UC 3.3a – Criticality-Aware CPU Downsize  (Avg_CPU < 10%)
      UC 3.3b – Criticality-Aware CPU Upsize    (Avg_CPU > 80%)
  UC 3.4 – Criticality-Aware RAM Optimization (split into 2 outputs):
      UC 3.4a – Criticality-Aware RAM Downsize  (Avg_FreeMem > 80%)
      UC 3.4b – Criticality-Aware RAM Upsize    (Avg_FreeMem < 20%)

PROD eligibility (UC 3.1):
- Avg_CPU_12m  < 15%
- Peak_CPU_12m <= 70%
- Current_vCPU >= 4   (was > 2; updated to match business rule)

NON-PROD eligibility (UC 3.1):
- Avg_CPU_12m  < 25%  (expanded to 25% so the 15-25% recommendation tier is reachable)
- Peak_CPU_12m <= 80%
- Current_vCPU >= 4   (was > 2; updated to match business rule)

PROD eligibility (UC 3.2):
- Avg_FreeMem_12m >= 35%
- Min_FreeMem_12m >= 20%
- Current_RAM_GiB > 8

NON-PROD eligibility (UC 3.2):
- Avg_FreeMem_12m >= 30%
- Min_FreeMem_12m >= 15%
- Current_RAM_GiB > 4
"""
import logging
from typing import Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

NON_PROD_ENVS: List[str] = [
    "Development",
    "Disaster recovery",
    "Test",
    "QA",
    "UAT",
]

PRACTICAL_RAM_SIZES: List[int] = [
    4, 6, 8, 10, 12, 16, 20, 24, 32, 48,
    64, 96, 128, 192, 256, 384, 512, 768, 1024, 2048,
]

MONTH_ORDER: Dict[str, int] = {
    "Mar": 1, "Apr": 2, "May": 3, "June": 4, "July": 5, "Aug": 6,
    "Sept": 7, "Oct": 8, "Nov": 9, "Dec": 10, "Jan": 11, "Feb": 12,
}

WORKLOAD_CPU = "CPU"
WORKLOAD_RAM = "RAM"
DETAIL_OPTIMIZATION = "Optimization"
DETAIL_RECOMMENDATION = "Recommendation"

# -- Criticality constants -----------------------------------------------------
COL_CRITICALITY   = "Criticality"
COL_IS_VIRTUAL    = "Is Virtual?"

CRITICAL_VALS:     List[str] = ["Business Critical", "Mission Critical"]
MFG_CRITICAL_VALS: List[str] = ["Manufacturing Critical"]
ALL_CRITICAL_VALS: List[str] = CRITICAL_VALS + MFG_CRITICAL_VALS


# -- Helpers -------------------------------------------------------------------

def _is_monthly_col(col: str) -> bool:
    return any(month in col for month in MONTH_ORDER)


def _chron_sort(cols: List[str]) -> List[str]:
    return sorted(cols, key=lambda c: next(
        (n for m, n in MONTH_ORDER.items() if m in c), 99
    ))


def _clean_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
              .str.replace("%", "", regex=False)
              .str.replace(",", "", regex=False)
              .str.strip()
              .replace({"NA": np.nan, "N/A": np.nan, "nan": np.nan,
                        "None": np.nan, "-": np.nan, "": np.nan}),
        errors="coerce",
    )


def _round_ram(value: float, min_gib: float) -> float:
    value = max(float(value), float(min_gib))
    result = float(min_gib)
    for size in PRACTICAL_RAM_SIZES:
        if size >= min_gib and size <= value:
            result = size
    return result


def _build_raw_detail_type(env_type: str, workload: str, detail_kind: str) -> str:
    normalized_env = str(env_type or "").upper().replace("-", "").replace(" ", "")
    return f"{normalized_env}_{workload}_{detail_kind}"


# -- Metric computation --------------------------------------------------------

def compute_utilisation_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive 12-month CPU and memory summary columns from raw monthly columns.

    Adds: Avg_CPU_12m, Peak_CPU_12m, Avg_FreeMem_12m, Min_FreeMem_12m,
          Current_vCPU, Current_RAM_GiB.
    """
    df = df.copy()
    df["Environment"] = df["Environment"].astype(str).str.strip()

    avg_cpu = _chron_sort([c for c in df.columns if "Average CPU Utilisation (%)" in c and _is_monthly_col(c)])
    max_cpu = _chron_sort([c for c in df.columns if "Maximum CPU Utilisation (%)" in c and _is_monthly_col(c)])
    avg_mem = _chron_sort([c for c in df.columns if "Average free Memory (%)"     in c and _is_monthly_col(c)])
    min_mem = _chron_sort([c for c in df.columns if "Minimum free Memory (%)"     in c and _is_monthly_col(c)])
    ram     = _chron_sort([c for c in df.columns if "Physical RAM (GiB)"          in c and _is_monthly_col(c)])
    lcpu    = _chron_sort([c for c in df.columns if "Logical CPU"                 in c and _is_monthly_col(c)])

    for col in avg_cpu + max_cpu + avg_mem + min_mem + ram + lcpu:
        df[col] = _clean_numeric(df[col])

    df["Avg_CPU_12m"]     = df[avg_cpu].mean(axis=1, skipna=True)
    df["Peak_CPU_12m"]    = df[max_cpu].max(axis=1,  skipna=True)
    df["Avg_FreeMem_12m"] = df[avg_mem].mean(axis=1, skipna=True)
    df["Min_FreeMem_12m"] = df[min_mem].min(axis=1,  skipna=True)
    df["Current_vCPU"]    = df[lcpu].ffill(axis=1).iloc[:, -1] if lcpu else np.nan
    df["Current_RAM_GiB"] = df[ram].ffill(axis=1).iloc[:, -1] if ram else np.nan

    logger.info("Utilisation metrics computed for %d rows.", len(df))
    return df


# -- UC 3.1 - CPU eligibility --------------------------------------------------

def find_cpu_rightsizing_optimizations(
    df: pd.DataFrame,
    non_prod_envs: List[str] = NON_PROD_ENVS,
) -> pd.DataFrame:
    """
    Identify VMs eligible for CPU right-sizing (UC 3.1) across PROD and NON-PROD.

    Returns a single DataFrame with an added 'Env_Type' column
    ('PROD' or 'NON-PROD') plus raw-detail type labels used by the UI filters.
    """
    prod_eligible    = _cpu_prod_eligible(df, non_prod_envs)
    nonprod_eligible = _cpu_nonprod_eligible(df, non_prod_envs)

    prod_rec    = _cpu_prod_recommendation(prod_eligible)
    nonprod_rec = _cpu_nonprod_recommendation(nonprod_eligible)

    prod_rec["Env_Type"]    = "PROD"
    nonprod_rec["Env_Type"] = "NON-PROD"
    prod_rec["Optimization_Type"] = _build_raw_detail_type("PROD", WORKLOAD_CPU, DETAIL_OPTIMIZATION)
    prod_rec["Recommendation_Type"] = _build_raw_detail_type("PROD", WORKLOAD_CPU, DETAIL_RECOMMENDATION)
    nonprod_rec["Optimization_Type"] = _build_raw_detail_type("NONPROD", WORKLOAD_CPU, DETAIL_OPTIMIZATION)
    nonprod_rec["Recommendation_Type"] = _build_raw_detail_type("NONPROD", WORKLOAD_CPU, DETAIL_RECOMMENDATION)

    result = pd.concat([prod_rec, nonprod_rec], ignore_index=True)
    logger.info(
        "CPU right-sizing optimizations - PROD: %d, NON-PROD: %d, TOTAL: %d",
        len(prod_rec), len(nonprod_rec), len(result),
    )
    return result


def find_cpu_rightsizing_candidates(
    df: pd.DataFrame,
    non_prod_envs: List[str] = NON_PROD_ENVS,
) -> pd.DataFrame:
    """Backward-compatible alias for CPU right-sizing optimizations."""
    return find_cpu_rightsizing_optimizations(df, non_prod_envs=non_prod_envs)


def _cpu_prod_eligible(df: pd.DataFrame, non_prod_envs: List[str]) -> pd.DataFrame:
    prod = df[~df["Environment"].isin(non_prod_envs)]
    return prod[
        (prod["Avg_CPU_12m"]  < 15) &
        (prod["Peak_CPU_12m"] <= 70) &
        (prod["Current_vCPU"] >= 4)   # UC 3.1: Current vCPU >= 4
    ].copy()


def _cpu_nonprod_eligible(df: pd.DataFrame, non_prod_envs: List[str]) -> pd.DataFrame:
    # Eligibility expanded to Avg_CPU_12m < 25% (was < 15%) so that the
    # second recommendation tier (Avg in 15-25%) is reachable and not dead code.
    nonprod = df[df["Environment"].isin(non_prod_envs)]
    return nonprod[
        (nonprod["Avg_CPU_12m"]  < 25) &
        (nonprod["Peak_CPU_12m"] <= 80) &
        (nonprod["Current_vCPU"] >= 4)  # UC 3.1: Current vCPU >= 4
    ].copy()


def _cpu_prod_recommendation(eligible_df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.1 PROD recommendations (ALL eligible rows are returned):
      Avg < 10%                      -> reduce vCPU by ~50%, never below 4
      Avg in [10%-15%) AND Peak <= 60% -> reduce vCPU by ~25%, never below 4
      Avg in [10%-15%) AND Peak (60-70%] -> Eligible but no specific reduction band matched

    All eligible rows are returned, including those where no specific band applies.
    Peak > 70% is already blocked by eligibility and needs no check here.
    """
    df = eligible_df.copy()
    if df.empty:
        df["CPU_Recommendation"] = pd.Series(dtype="object")
        df["Recommended_vCPU"]   = pd.Series(dtype="float")
        return df

    def _rec(row):
        avg, peak, vcpu = row["Avg_CPU_12m"], row["Peak_CPU_12m"], row["Current_vCPU"]
        if pd.isna(avg) or pd.isna(vcpu):
            return None, np.nan
        vcpu = float(vcpu)
        if avg < 10:
            new = max(4, round(vcpu * 0.50))   # never below 4 vCPU
            return f"Reduce vCPU by ~50% -> {int(new)}", int(new)
        if 10 <= avg < 15 and (pd.isna(peak) or peak <= 60):
            new = max(4, round(vcpu * 0.75))   # never below 4 vCPU
            return f"Reduce vCPU by ~25% -> {int(new)}", int(new)
        # Avg 10-15% with Peak 60-70%: eligible but no specific band matched
        return "Eligible - No specific reduction band matched (Peak 60-70% with Avg 10-15%)", int(vcpu)

    result = df.apply(_rec, axis=1, result_type="expand")
    df["CPU_Recommendation"] = result[0]
    df["Recommended_vCPU"]   = result[1]
    # Return ALL eligible rows (including those with no specific band)
    df = df[df["CPU_Recommendation"].notna()].copy()
    return df


def _cpu_nonprod_recommendation(eligible_df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.1 NON-PROD recommendations (ALL eligible rows are returned):
      Avg < 15% AND Peak < 60%          -> reduce by ~50-60% (keep 45%), never below 4
      Avg in [15%-25%) AND Peak <= 70%  -> reduce by ~25-33% (keep 71%), never below 4
      Other eligible rows               -> Eligible but no specific reduction band matched

    All eligible rows are returned, including those where no specific band applies.
    Peak > 80% is already blocked by eligibility and needs no check here.
    """
    df = eligible_df.copy()
    if df.empty:
        df["CPU_Recommendation"] = pd.Series(dtype="object")
        df["Recommended_vCPU"]   = pd.Series(dtype="float")
        return df

    def _rec(row):
        avg, peak, vcpu = row["Avg_CPU_12m"], row["Peak_CPU_12m"], row["Current_vCPU"]
        if pd.isna(avg) or pd.isna(vcpu):
            return None, np.nan
        vcpu = float(vcpu)
        if avg < 15 and (pd.isna(peak) or peak < 60):
            new = max(4, round(vcpu * 0.45))   # never below 4 vCPU
            return f"Reduce vCPU by ~50-60% -> {int(new)}", int(new)
        if 15 <= avg < 25 and (pd.isna(peak) or peak <= 70):
            new = max(4, round(vcpu * 0.71))   # never below 4 vCPU
            return f"Reduce vCPU by ~25-33% -> {int(new)}", int(new)
        # Eligible but no specific band matched
        return "Eligible - No specific reduction band matched", int(vcpu)

    result = df.apply(_rec, axis=1, result_type="expand")
    df["CPU_Recommendation"] = result[0]
    df["Recommended_vCPU"]   = result[1]
    # Return ALL eligible rows (including those with no specific band)
    df = df[df["CPU_Recommendation"].notna()].copy()
    return df


# -- UC 3.2 - RAM eligibility --------------------------------------------------

def find_ram_rightsizing_optimizations(
    df: pd.DataFrame,
    non_prod_envs: List[str] = NON_PROD_ENVS,
) -> pd.DataFrame:
    """
    Identify VMs eligible for RAM right-sizing (UC 3.2) across PROD and NON-PROD.

    Returns a single DataFrame with an added 'Env_Type' column
    ('PROD' or 'NON-PROD') plus raw-detail type labels used by the UI filters.
    """
    prod_eligible    = _ram_prod_eligible(df, non_prod_envs)
    nonprod_eligible = _ram_nonprod_eligible(df, non_prod_envs)

    prod_rec    = _ram_prod_recommendation(prod_eligible)
    nonprod_rec = _ram_nonprod_recommendation(nonprod_eligible)

    prod_rec["Env_Type"]    = "PROD"
    nonprod_rec["Env_Type"] = "NON-PROD"
    prod_rec["Optimization_Type"] = _build_raw_detail_type("PROD", WORKLOAD_RAM, DETAIL_OPTIMIZATION)
    prod_rec["Recommendation_Type"] = _build_raw_detail_type("PROD", WORKLOAD_RAM, DETAIL_RECOMMENDATION)
    nonprod_rec["Optimization_Type"] = _build_raw_detail_type("NONPROD", WORKLOAD_RAM, DETAIL_OPTIMIZATION)
    nonprod_rec["Recommendation_Type"] = _build_raw_detail_type("NONPROD", WORKLOAD_RAM, DETAIL_RECOMMENDATION)

    result = pd.concat([prod_rec, nonprod_rec], ignore_index=True)
    logger.info(
        "RAM right-sizing optimizations - PROD: %d, NON-PROD: %d, TOTAL: %d",
        len(prod_rec), len(nonprod_rec), len(result),
    )
    return result


def find_ram_rightsizing_candidates(
    df: pd.DataFrame,
    non_prod_envs: List[str] = NON_PROD_ENVS,
) -> pd.DataFrame:
    """Backward-compatible alias for RAM right-sizing optimizations."""
    return find_ram_rightsizing_optimizations(df, non_prod_envs=non_prod_envs)


def _ram_prod_eligible(df: pd.DataFrame, non_prod_envs: List[str]) -> pd.DataFrame:
    prod = df[~df["Environment"].isin(non_prod_envs)]
    return prod[
        (prod["Avg_FreeMem_12m"] >= 35) &
        (prod["Min_FreeMem_12m"] >= 20) &
        (prod["Current_RAM_GiB"] > 8)
    ].copy()


def _ram_nonprod_eligible(df: pd.DataFrame, non_prod_envs: List[str]) -> pd.DataFrame:
    nonprod = df[df["Environment"].isin(non_prod_envs)]
    return nonprod[
        (nonprod["Avg_FreeMem_12m"] >= 30) &
        (nonprod["Min_FreeMem_12m"] >= 15) &
        (nonprod["Current_RAM_GiB"] > 4)
    ].copy()


def _ram_prod_recommendation(eligible_df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.2 PROD recommendations (only rows with an actionable recommendation are returned):
      Avg_FreeMem in [35%-50%]              -> reduce by ~25%, rounded, min 8 GiB
      Avg_FreeMem > 50% AND Min >= 30%      -> reduce by ~40-50%, rounded, min 8 GiB

    Rows with Avg_FreeMem > 50% but Min_FreeMem < 30% have no defined recommendation
    in the use-case doc and are excluded from the output.
    """
    df = eligible_df.copy()
    if df.empty:
        df["RAM_Recommendation"]  = pd.Series(dtype="object")
        df["Recommended_RAM_GiB"] = pd.Series(dtype="float")
        return df

    def _rec(row):
        avg_mem, min_mem, ram = row["Avg_FreeMem_12m"], row["Min_FreeMem_12m"], row["Current_RAM_GiB"]
        if pd.isna(avg_mem) or pd.isna(ram):
            return None, np.nan
        if 35 <= avg_mem <= 50:                                    # inclusive upper bound per doc
            target = _round_ram(ram * 0.75, 8)
            return f"Reduce RAM by ~25% -> {target} GiB", target
        if avg_mem > 50 and pd.notna(min_mem) and min_mem >= 30:
            target = _round_ram(ram * 0.55, 8)
            return f"Reduce RAM by ~40-50% -> {target} GiB", target
        return None, np.nan  # no recommendation defined for this combination

    result = df.apply(_rec, axis=1, result_type="expand")
    df["RAM_Recommendation"]  = result[0]
    df["Recommended_RAM_GiB"] = result[1]
    # Only return rows that received an actionable recommendation
    df = df[df["RAM_Recommendation"].notna()].copy()
    return df


def _ram_nonprod_recommendation(eligible_df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.2 NON-PROD recommendations (only rows with an actionable recommendation are returned):
      Avg_FreeMem in [30%-50%]              -> reduce by ~33%, rounded, min 4 GiB
      Avg_FreeMem > 50% AND Min >= 25%      -> reduce by ~40-60%, rounded, min 4 GiB

    Rows with Avg_FreeMem > 50% but Min_FreeMem < 25% have no defined recommendation
    in the use-case doc and are excluded from the output.
    """
    df = eligible_df.copy()
    if df.empty:
        df["RAM_Recommendation"]  = pd.Series(dtype="object")
        df["Recommended_RAM_GiB"] = pd.Series(dtype="float")
        return df

    def _rec(row):
        avg_mem, min_mem, ram = row["Avg_FreeMem_12m"], row["Min_FreeMem_12m"], row["Current_RAM_GiB"]
        if pd.isna(avg_mem) or pd.isna(ram):
            return None, np.nan
        if 30 <= avg_mem <= 50:                                    # inclusive upper bound per doc
            target = _round_ram(ram * 0.67, 4)
            return f"Reduce RAM by ~33% -> {target} GiB", target
        if avg_mem > 50 and pd.notna(min_mem) and min_mem >= 25:
            target = _round_ram(ram * 0.50, 4)
            return f"Reduce RAM by ~40-60% -> {target} GiB", target
        return None, np.nan  # no recommendation defined for this combination

    result = df.apply(_rec, axis=1, result_type="expand")
    df["RAM_Recommendation"]  = result[0]
    df["Recommended_RAM_GiB"] = result[1]
    # Only return rows that received an actionable recommendation
    df = df[df["RAM_Recommendation"].notna()].copy()
    return df


# -- UC 3.3a - Criticality-Aware CPU Downsize ----------------------------------

def find_criticality_cpu_downsize_optimizations(df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.3a - Criticality-Aware CPU Downsize.

    Rule: Critical systems (Business Critical / Mission Critical / Manufacturing Critical)
    with Avg_CPU_12m < 10% -> Downsize by ~25% cautiously, never below 4 vCPU.
    Human Intervention Required for all critical downsizes.

    Only critical systems are included. Normal systems are excluded.
    """
    has_criticality = COL_CRITICALITY in df.columns
    if not has_criticality:
        return pd.DataFrame(columns=list(df.columns) + [
            "CPU_Recommendation", "Recommended_vCPU", "Lifecycle_Flag",
            "Optimization_Type", "Recommendation_Type"
        ])

    # Filter: critical systems only + Avg_CPU < 10%
    crit_mask = df[COL_CRITICALITY].isin(ALL_CRITICAL_VALS)
    eligible = df[crit_mask & (df["Avg_CPU_12m"].fillna(100) < 10)].copy()

    if eligible.empty:
        for col in ("CPU_Recommendation", "Recommended_vCPU", "Lifecycle_Flag",
                    "Optimization_Type", "Recommendation_Type"):
            eligible[col] = pd.Series(dtype="object")
        return eligible

    def _rec(row):
        avg         = row["Avg_CPU_12m"]
        vcpu        = row["Current_vCPU"]
        criticality = str(row.get(COL_CRITICALITY, ""))
        is_mfg      = criticality in MFG_CRITICAL_VALS
        is_bc_mc    = criticality in CRITICAL_VALS

        if pd.isna(avg) or pd.isna(vcpu):
            return "Insufficient data", np.nan, ""

        vcpu = float(vcpu)
        new  = max(4, round(vcpu * 0.75))
        note = "Critical System - Cautious Downsizing by ~25%"
        if is_mfg:
            note += " (Manufacturing Critical - Extra Conservatism; Human Review Required)"
        elif is_bc_mc:
            note += " (Human Intervention Required)"
        return f"{note} -> {int(new)} vCPU", int(new), ""

    result = eligible.apply(_rec, axis=1, result_type="expand")
    eligible["CPU_Recommendation"]  = result[0]
    eligible["Recommended_vCPU"]    = result[1]
    eligible["Lifecycle_Flag"]      = result[2]
    eligible["Optimization_Type"]   = "Crit_CPU_Downsize_Optimization"
    eligible["Recommendation_Type"] = "Crit_CPU_Downsize_Recommendation"

    logger.info("UC 3.3a criticality CPU downsize optimizations: %d rows.", len(eligible))
    return eligible


# -- UC 3.3b - Criticality-Aware CPU Upsize ------------------------------------

def find_criticality_cpu_upsize_optimizations(df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.3b - Criticality-Aware CPU Upsize.

    Rule: Critical systems (Business Critical / Mission Critical) with
    Avg_CPU_12m > 80% -> Upsize by ~25% (flag only, Human Intervention Required).

    Only Business Critical and Mission Critical systems are included.
    Manufacturing Critical and normal systems are excluded.
    """
    has_criticality = COL_CRITICALITY in df.columns
    if not has_criticality:
        return pd.DataFrame(columns=list(df.columns) + [
            "CPU_Recommendation", "Recommended_vCPU", "Lifecycle_Flag",
            "Optimization_Type", "Recommendation_Type"
        ])

    # Filter: Bus/Mission Critical only + Avg_CPU > 80%
    crit_mask = df[COL_CRITICALITY].isin(CRITICAL_VALS)
    eligible  = df[crit_mask & (df["Avg_CPU_12m"].fillna(0) > 80)].copy()

    if eligible.empty:
        for col in ("CPU_Recommendation", "Recommended_vCPU", "Lifecycle_Flag",
                    "Optimization_Type", "Recommendation_Type"):
            eligible[col] = pd.Series(dtype="object")
        return eligible

    def _rec(row):
        vcpu = row["Current_vCPU"]
        if pd.isna(vcpu):
            return "Insufficient data", np.nan, "Upsize Flag"
        vcpu = float(vcpu)
        new  = round(vcpu * 1.25)
        return (
            f"Critical System - Upsize by ~25% - Flag Only (Human Intervention Required) -> {int(new)} vCPU",
            int(new),
            "Upsize Flag",
        )

    result = eligible.apply(_rec, axis=1, result_type="expand")
    eligible["CPU_Recommendation"]  = result[0]
    eligible["Recommended_vCPU"]    = result[1]
    eligible["Lifecycle_Flag"]      = result[2]
    eligible["Optimization_Type"]   = "Crit_CPU_Upsize_Optimization"
    eligible["Recommendation_Type"] = "Crit_CPU_Upsize_Recommendation"

    logger.info("UC 3.3b criticality CPU upsize optimizations: %d rows.", len(eligible))
    return eligible


# -- UC 3.4a - Criticality-Aware RAM Downsize ----------------------------------

def find_criticality_ram_downsize_optimizations(df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.4a - Criticality-Aware RAM Downsize.

    Rule: Critical systems (Business Critical / Mission Critical / Manufacturing Critical)
    with Avg_FreeMem_12m > 80% -> Downsize by ~25%, never below 8 GiB.
    Human Intervention Required for all critical downsizes.

    Only critical systems are included. Normal systems are excluded.
    """
    has_criticality = COL_CRITICALITY in df.columns
    if not has_criticality:
        return pd.DataFrame(columns=list(df.columns) + [
            "RAM_Recommendation", "Recommended_RAM_GiB", "Lifecycle_Flag",
            "Optimization_Type", "Recommendation_Type"
        ])

    # Filter: critical systems only + Avg_FreeMem > 80%
    crit_mask = df[COL_CRITICALITY].isin(ALL_CRITICAL_VALS)
    eligible  = df[crit_mask & (df["Avg_FreeMem_12m"].fillna(0) > 80)].copy()

    if eligible.empty:
        for col in ("RAM_Recommendation", "Recommended_RAM_GiB", "Lifecycle_Flag",
                    "Optimization_Type", "Recommendation_Type"):
            eligible[col] = pd.Series(dtype="object")
        return eligible

    def _rec(row):
        avg_mem     = row["Avg_FreeMem_12m"]
        ram         = row["Current_RAM_GiB"]
        criticality = str(row.get(COL_CRITICALITY, ""))
        is_mfg      = criticality in MFG_CRITICAL_VALS
        is_bc_mc    = criticality in CRITICAL_VALS

        if pd.isna(avg_mem) or pd.isna(ram):
            return "Insufficient data", np.nan, ""

        human_note = ""
        if is_bc_mc:
            human_note = " (Human Intervention Required)"
        elif is_mfg:
            human_note = " (Manufacturing Critical - Extra Conservatism; Human Review Required)"

        target = _round_ram(ram * 0.75, 8)
        return (
            f"Critical System - Downsize RAM by ~25%{human_note} -> {target} GiB",
            target,
            "",
        )

    result = eligible.apply(_rec, axis=1, result_type="expand")
    eligible["RAM_Recommendation"]  = result[0]
    eligible["Recommended_RAM_GiB"] = result[1]
    eligible["Lifecycle_Flag"]      = result[2]
    eligible["Optimization_Type"]   = "Crit_RAM_Downsize_Optimization"
    eligible["Recommendation_Type"] = "Crit_RAM_Downsize_Recommendation"

    logger.info("UC 3.4a criticality RAM downsize optimizations: %d rows.", len(eligible))
    return eligible


# -- UC 3.4b - Criticality-Aware RAM Upsize ------------------------------------

def find_criticality_ram_upsize_optimizations(df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.4b - Criticality-Aware RAM Upsize.

    Rule: Critical systems (Business Critical / Mission Critical) with
    Avg_FreeMem_12m < 20% -> Upsize flag only (Human Intervention Required).

    Only Business Critical and Mission Critical systems are included.
    Manufacturing Critical and normal systems are excluded.
    """
    has_criticality = COL_CRITICALITY in df.columns
    if not has_criticality:
        return pd.DataFrame(columns=list(df.columns) + [
            "RAM_Recommendation", "Recommended_RAM_GiB", "Lifecycle_Flag",
            "Optimization_Type", "Recommendation_Type"
        ])

    # Filter: Bus/Mission Critical only + Avg_FreeMem < 20%
    crit_mask = df[COL_CRITICALITY].isin(CRITICAL_VALS)
    eligible  = df[crit_mask & (df["Avg_FreeMem_12m"].fillna(100) < 20)].copy()

    if eligible.empty:
        for col in ("RAM_Recommendation", "Recommended_RAM_GiB", "Lifecycle_Flag",
                    "Optimization_Type", "Recommendation_Type"):
            eligible[col] = pd.Series(dtype="object")
        return eligible

    def _rec(row):
        avg_mem = row["Avg_FreeMem_12m"]
        ram     = row["Current_RAM_GiB"]

        if pd.isna(avg_mem) or pd.isna(ram):
            return "Insufficient data", np.nan, "Upsize Flag"

        return (
            "Critical System - Upsize RAM - Flag Only (Avg Free Mem < 20%) (Human Intervention Required)",
            int(ram),
            "Upsize Flag",
        )

    result = eligible.apply(_rec, axis=1, result_type="expand")
    eligible["RAM_Recommendation"]  = result[0]
    eligible["Recommended_RAM_GiB"] = result[1]
    eligible["Lifecycle_Flag"]      = result[2]
    eligible["Optimization_Type"]   = "Crit_RAM_Upsize_Optimization"
    eligible["Recommendation_Type"] = "Crit_RAM_Upsize_Recommendation"

    logger.info("UC 3.4b criticality RAM upsize optimizations: %d rows.", len(eligible))
    return eligible


def find_criticality_cpu_optimizations(df: pd.DataFrame) -> pd.DataFrame:
    """Combined UC 3.3a + 3.3b: downsize and upsize criticality CPU results."""
    down = find_criticality_cpu_downsize_optimizations(df)
    up   = find_criticality_cpu_upsize_optimizations(df)
    if down.empty and up.empty:
        return down
    return pd.concat([down, up], ignore_index=True)


def find_criticality_ram_optimizations(df: pd.DataFrame) -> pd.DataFrame:
    """Combined UC 3.4a + 3.4b: downsize and upsize criticality RAM results."""
    down = find_criticality_ram_downsize_optimizations(df)
    up   = find_criticality_ram_upsize_optimizations(df)
    if down.empty and up.empty:
        return down
    return pd.concat([down, up], ignore_index=True)


# -- Lifecycle Risk Flags ------------------------------------------------------

LC_CRITICAL_VALS = ["Business Critical", "Mission Critical"]


def find_lifecycle_risk_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.5 - Lifecycle Risk Detection.

    All three filters applied sequentially (AND logic):
      Filter 1: Criticality = Business Critical OR Mission Critical
      Filter 2: Peak_CPU_12m > 95%
      Filter 3: Min_FreeMem_12m < 5%

    Only rows that pass ALL three filters are returned.
    Returns a DataFrame with 'Lifecycle_Risk_Reasons' and 'Human_Review_Required'.
    """
    has_criticality = COL_CRITICALITY in df.columns

    if not has_criticality:
        return pd.DataFrame(columns=list(df.columns) + [
            "Lifecycle_Risk_Reasons", "Human_Review_Required"
        ])

    # Sequential AND filters
    step1 = df[df[COL_CRITICALITY].isin(LC_CRITICAL_VALS)].copy()
    step2 = step1[step1["Peak_CPU_12m"].fillna(0) > 95].copy()
    step3 = step2[step2["Min_FreeMem_12m"].fillna(100) < 5].copy()
    flagged = step3

    if flagged.empty:
        flagged["Lifecycle_Risk_Reasons"] = pd.Series(dtype="object")
        flagged["Human_Review_Required"]  = pd.Series(dtype="object")
        return flagged

    flagged = flagged.copy()
    flagged["Lifecycle_Risk_Reasons"] = flagged.apply(
        lambda row: (
            f"Critical System ({row[COL_CRITICALITY]}); "
            "High Peak CPU (>95%); "
            "Low Minimum Memory (<5%)"
        ),
        axis=1,
    )
    flagged["Human_Review_Required"] = "Yes"
    logger.info("Lifecycle risk flags (AND sequential): %d systems flagged.", len(flagged))
    return flagged


# -- Physical Systems Flag -----------------------------------------------------

def find_physical_systems_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identify physical systems for human review.

    IsVirtual == "false" (case-insensitive) -> Physical -> flag for human review.
    All other values including blank/NaN -> treated as Virtual (not flagged here).

    Column checked: 'Is Virtual?' (COL_IS_VIRTUAL) or 'is_virtual' (DB model field).
    """
    # Support both Excel column name and DB-normalized column name
    col = None
    for candidate in (COL_IS_VIRTUAL, "is_virtual", "IsVirtual"):
        if candidate in df.columns:
            col = candidate
            break

    if col is None:
        logger.warning("find_physical_systems_flags: no IsVirtual column found.")
        return pd.DataFrame(columns=list(df.columns) + ["IsVirtual_Status", "Human_Review_Required", "Review_Reason"])

    is_physical = df[col].astype(str).str.strip().str.lower() == "false"
    physical = df[is_physical].copy()
    physical["IsVirtual_Status"]      = "Physical"
    physical["Human_Review_Required"] = "Yes - Physical System"
    physical["Review_Reason"]         = (
        "Physical system detected. Human review required before any "
        "rightsizing action is taken."
    )
    logger.info("Physical systems flagged: %d.", len(physical))
    return physical
