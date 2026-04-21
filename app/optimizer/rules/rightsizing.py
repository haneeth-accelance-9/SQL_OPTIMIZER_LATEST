"""
Rule 3: VM Right-Sizing (CPU & RAM).

Identifies virtual machines that are over-provisioned in CPU or RAM based on
12-month utilisation metrics. Expects normalized column names with monthly
Average/Peak CPU and Average/Minimum free Memory columns.

Enterprise use cases:
  UC 3.1 – CPU Right-Sizing: reduce vCPU count for under-utilised VMs.
  UC 3.2 – RAM Right-Sizing: reduce RAM allocation for under-utilised VMs.

PROD eligibility (UC 3.1):
- Avg_CPU_12m  < 15%
- Peak_CPU_12m <= 70%
- Current_vCPU > 2

NON-PROD eligibility (UC 3.1):
- Avg_CPU_12m  < 15%
- Peak_CPU_12m <= 80%
- Current_vCPU > 2

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


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Metric computation ────────────────────────────────────────────────────────

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
    df["Current_vCPU"]    = df[lcpu].ffill(axis=1).iloc[:, -1]
    df["Current_RAM_GiB"] = df[ram].ffill(axis=1).iloc[:, -1]

    logger.info("Utilisation metrics computed for %d rows.", len(df))
    return df


# ── UC 3.1 – CPU eligibility ──────────────────────────────────────────────────

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
        (prod["Current_vCPU"] > 2)
    ].copy()


def _cpu_nonprod_eligible(df: pd.DataFrame, non_prod_envs: List[str]) -> pd.DataFrame:
    nonprod = df[df["Environment"].isin(non_prod_envs)]
    return nonprod[
        (nonprod["Avg_CPU_12m"]  < 15) &
        (nonprod["Peak_CPU_12m"] <= 80) &
        (nonprod["Current_vCPU"] > 2)
    ].copy()


def _cpu_prod_recommendation(eligible_df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.1 PROD recommendations:
      Avg < 10% AND Peak in [50%–70%]  → reduce vCPU by ~50%, min 2
      Avg in [10%–15%) AND Peak <= 60% → reduce vCPU by ~25%, min 2
      Peak > 70%                       → no reduction (peak protection)
    """
    df = eligible_df.copy()
    if df.empty:
        df["CPU_Recommendation"] = pd.Series(dtype="object")
        df["Recommended_vCPU"] = pd.Series(dtype="float")
        return df

    def _rec(row):
        avg, peak, vcpu = row["Avg_CPU_12m"], row["Peak_CPU_12m"], row["Current_vCPU"]
        if pd.isna(avg) or pd.isna(peak) or pd.isna(vcpu):
            return "Insufficient data", np.nan
        vcpu = float(vcpu)
        if peak > 70:
            return "No reduction – Peak > 70% (protect peak performance)", int(vcpu)
        if avg < 10 and peak >= 50:
            new = max(2, round(vcpu * 0.50))
            return f"Reduce vCPU by ~50% → {int(new)}", int(new)
        if 10 <= avg < 15 and peak <= 60:
            new = max(2, round(vcpu * 0.75))
            return f"Reduce vCPU by ~25% → {int(new)}", int(new)
        return "No specific recommendation", int(vcpu)

    result = df.apply(_rec, axis=1, result_type="expand")
    df["CPU_Recommendation"] = result[0]
    df["Recommended_vCPU"]   = result[1]
    return df


def _cpu_nonprod_recommendation(eligible_df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.1 NON-PROD recommendations:
      Avg < 15% AND Peak < 60%          → reduce by ~50–60% (keep 45%), min 2
      Avg in [15%–25%) AND Peak <= 70%  → reduce by ~25–33% (keep 71%), min 2
      Peak > 80%                        → no reduction
    """
    df = eligible_df.copy()
    if df.empty:
        df["CPU_Recommendation"] = pd.Series(dtype="object")
        df["Recommended_vCPU"] = pd.Series(dtype="float")
        return df

    def _rec(row):
        avg, peak, vcpu = row["Avg_CPU_12m"], row["Peak_CPU_12m"], row["Current_vCPU"]
        if pd.isna(avg) or pd.isna(peak) or pd.isna(vcpu):
            return "Insufficient data", np.nan
        vcpu = float(vcpu)
        if peak > 80:
            return "No reduction – Peak > 80%", int(vcpu)
        if avg < 15 and peak < 60:
            new = max(2, round(vcpu * 0.45))
            return f"Reduce vCPU by ~50-60% → {int(new)}", int(new)
        if 15 <= avg < 25 and peak <= 70:
            new = max(2, round(vcpu * 0.71))
            return f"Reduce vCPU by ~25-33% → {int(new)}", int(new)
        return "No specific recommendation", int(vcpu)

    result = df.apply(_rec, axis=1, result_type="expand")
    df["CPU_Recommendation"] = result[0]
    df["Recommended_vCPU"]   = result[1]
    return df


# ── UC 3.2 – RAM eligibility ──────────────────────────────────────────────────

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
    UC 3.2 PROD recommendations:
      Avg_FreeMem in [35%–50%)              → reduce by ~25%, rounded, min 8 GiB
      Avg_FreeMem > 50% AND Min >= 30%      → reduce by ~40–50%, rounded, min 8 GiB
    """
    df = eligible_df.copy()
    if df.empty:
        df["RAM_Recommendation"] = pd.Series(dtype="object")
        df["Recommended_RAM_GiB"] = pd.Series(dtype="float")
        return df

    def _rec(row):
        avg_mem, min_mem, ram = row["Avg_FreeMem_12m"], row["Min_FreeMem_12m"], row["Current_RAM_GiB"]
        if pd.isna(avg_mem) or pd.isna(ram):
            return "Insufficient data", np.nan
        if 35 <= avg_mem < 50:
            target = _round_ram(ram * 0.75, 8)
            return f"Reduce RAM by ~25% → {target} GiB", target
        if avg_mem > 50 and pd.notna(min_mem) and min_mem >= 30:
            target = _round_ram(ram * 0.55, 8)
            return f"Reduce RAM by ~40-50% → {target} GiB", target
        return "No specific recommendation", int(ram)

    result = df.apply(_rec, axis=1, result_type="expand")
    df["RAM_Recommendation"]  = result[0]
    df["Recommended_RAM_GiB"] = result[1]
    return df


def _ram_nonprod_recommendation(eligible_df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.2 NON-PROD recommendations:
      Avg_FreeMem in [30%–50%)              → reduce by ~33%, rounded, min 4 GiB
      Avg_FreeMem > 50% AND Min >= 25%      → reduce by ~40–60%, rounded, min 4 GiB
    """
    df = eligible_df.copy()
    if df.empty:
        df["RAM_Recommendation"] = pd.Series(dtype="object")
        df["Recommended_RAM_GiB"] = pd.Series(dtype="float")
        return df

    def _rec(row):
        avg_mem, min_mem, ram = row["Avg_FreeMem_12m"], row["Min_FreeMem_12m"], row["Current_RAM_GiB"]
        if pd.isna(avg_mem) or pd.isna(ram):
            return "Insufficient data", np.nan
        if 30 <= avg_mem < 50:
            target = _round_ram(ram * 0.67, 4)
            return f"Reduce RAM by ~33% → {target} GiB", target
        if avg_mem > 50 and pd.notna(min_mem) and min_mem >= 25:
            target = _round_ram(ram * 0.50, 4)
            return f"Reduce RAM by ~40-60% → {target} GiB", target
        return "No specific recommendation", int(ram)

    result = df.apply(_rec, axis=1, result_type="expand")
    df["RAM_Recommendation"]  = result[0]
    df["Recommended_RAM_GiB"] = result[1]
    return df
