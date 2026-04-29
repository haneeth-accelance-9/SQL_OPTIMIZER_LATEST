"""
Rule 3: VM Right-Sizing (CPU & RAM).

Identifies virtual machines that are over-provisioned in CPU or RAM based on
12-month utilisation metrics. Expects normalized column names with monthly
Average/Peak CPU and Average/Minimum free Memory columns.

Enterprise use cases:
  UC 3.1 – CPU Right-Sizing: reduce vCPU count for under-utilised VMs.
  UC 3.2 – RAM Right-Sizing: reduce RAM allocation for under-utilised VMs.
  UC 3.3 – Criticality-Aware CPU Optimization.
  UC 3.4 – Criticality-Aware RAM Optimization.

PROD eligibility (UC 3.1):
- Avg_CPU_12m  < 15%
- Peak_CPU_12m <= 70%
- Current_vCPU >= 4   (was > 2; updated to match business rule)

NON-PROD eligibility (UC 3.1):
- Avg_CPU_12m  < 25%  (expanded to 25% so the 15–25% recommendation tier is reachable)
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

# ── Criticality constants ─────────────────────────────────────────────────────
COL_CRITICALITY   = "Criticality"
COL_IS_VIRTUAL    = "Is Virtual?"

CRITICAL_VALS:     List[str] = ["Business Critical", "Mission Critical"]
MFG_CRITICAL_VALS: List[str] = ["Manufacturing Critical"]
ALL_CRITICAL_VALS: List[str] = CRITICAL_VALS + MFG_CRITICAL_VALS


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
    df["Current_vCPU"]    = df[lcpu].ffill(axis=1).iloc[:, -1] if lcpu else np.nan
    df["Current_RAM_GiB"] = df[ram].ffill(axis=1).iloc[:, -1] if ram else np.nan

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
        (prod["Current_vCPU"] >= 4)   # UC 3.1: Current vCPU >= 4
    ].copy()


def _cpu_nonprod_eligible(df: pd.DataFrame, non_prod_envs: List[str]) -> pd.DataFrame:
    # FIX 1: Eligibility expanded to Avg_CPU_12m < 25% (was < 15%) so that the
    # second recommendation tier (Avg in 15–25%) is reachable and not dead code.
    nonprod = df[df["Environment"].isin(non_prod_envs)]
    return nonprod[
        (nonprod["Avg_CPU_12m"]  < 25) &
        (nonprod["Peak_CPU_12m"] <= 80) &
        (nonprod["Current_vCPU"] >= 4)  # UC 3.1: Current vCPU >= 4
    ].copy()


def _cpu_prod_recommendation(eligible_df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.1 PROD recommendations:
      Avg < 10%                        → reduce vCPU by ~50%, never below 4
      Avg in [10%–15%) AND Peak <= 60% → reduce vCPU by ~25%, never below 4
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
        if avg < 10:
            new = max(4, round(vcpu * 0.50))   # never below 4 vCPU
            return f"Reduce vCPU by ~50% → {int(new)}", int(new)
        if 10 <= avg < 15 and peak <= 60:
            new = max(4, round(vcpu * 0.75))   # never below 4 vCPU
            return f"Reduce vCPU by ~25% → {int(new)}", int(new)
        return "No specific recommendation", int(vcpu)

    result = df.apply(_rec, axis=1, result_type="expand")
    df["CPU_Recommendation"] = result[0]
    df["Recommended_vCPU"]   = result[1]
    return df


def _cpu_nonprod_recommendation(eligible_df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.1 NON-PROD recommendations:
      Avg < 15% AND Peak < 60%          → reduce by ~50–60% (keep 45%), never below 4
      Avg in [15%–25%) AND Peak <= 70%  → reduce by ~25–33% (keep 71%), never below 4
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
            new = max(4, round(vcpu * 0.45))   # never below 4 vCPU
            return f"Reduce vCPU by ~50-60% → {int(new)}", int(new)
        if 15 <= avg < 25 and peak <= 70:
            new = max(4, round(vcpu * 0.71))   # never below 4 vCPU
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


# ── UC 3.3 – Criticality-Aware CPU Optimization ───────────────────────────────

def find_criticality_cpu_optimizations(df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.3 Criticality-Aware CPU Optimization.
    Applies to ALL rows (all environments, all criticality levels).

    Eligible rows = any of:
      Avg_CPU_12m  < 20%    → normal systems candidate for downsize
      Avg_CPU_12m  < 10%    → critical systems candidate for cautious downsize
      Avg_CPU_12m  > 80%    → candidate for upsize flag
      Peak_CPU_12m > 95%    → lifecycle / blocking flag
    """
    eligible = _criticality_cpu_eligible(df)
    rec = _criticality_cpu_recommendation(eligible)
    rec["Optimization_Type"] = "Crit_CPU_Optimization"
    rec["Recommendation_Type"] = "Crit_CPU_Recommendation"
    logger.info("UC 3.3 criticality CPU optimizations: %d rows.", len(rec))
    return rec


def _criticality_cpu_eligible(df: pd.DataFrame) -> pd.DataFrame:
    # FIX 2: Expanded mask from < 10 to < 20 to capture normal systems
    # (normal systems downsize at Avg_CPU < 20%; critical systems at < 10%).
    mask = (
        (df["Avg_CPU_12m"].fillna(0)  < 20) |   # covers both normal (< 20%) and critical (< 10%)
        (df["Avg_CPU_12m"].fillna(0)  > 80) |
        (df["Peak_CPU_12m"].fillna(0) > 95)
    )
    return df[mask].copy()


def _criticality_cpu_recommendation(eligible_df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.3 recommendations:
      Peak_CPU > 95%                      → Downsize BLOCKED; lifecycle flag triggered
      Critical/Mfg systems, Avg_CPU < 10% → Cautious downsize by ~25%, never below 4 vCPU
      Normal systems, Avg_CPU < 20%       → Downsize by ~25%, never below 4 vCPU
      Avg_CPU > 80%                       → Upsize by ~25% (flag only)
    """
    df = eligible_df.copy()
    if df.empty:
        for col in ("CPU_Recommendation", "Recommended_vCPU", "Lifecycle_Flag"):
            df[col] = pd.Series(dtype="object")
        return df

    has_criticality = COL_CRITICALITY in df.columns

    def _rec(row):
        avg        = row["Avg_CPU_12m"]
        peak       = row["Peak_CPU_12m"]
        vcpu       = row["Current_vCPU"]
        criticality = str(row.get(COL_CRITICALITY, "")) if has_criticality else ""
        is_mfg     = criticality in MFG_CRITICAL_VALS
        is_bc_mc   = criticality in CRITICAL_VALS
        # FIX 3: Distinguish critical vs normal systems for downsize threshold.
        is_critical_system = is_bc_mc or is_mfg

        if pd.isna(avg) or pd.isna(vcpu):
            return "Insufficient data", np.nan, ""

        vcpu = float(vcpu)
        lifecycle = ""

        if not pd.isna(peak) and peak > 95:
            lifecycle = "Lifecycle Risk: High Peak CPU (>95%)"
            return (
                "High Peak CPU (>95%) – Downsizing BLOCKED; Lifecycle Flag Triggered",
                int(vcpu),
                lifecycle,
            )

        if is_critical_system:
            # Critical / Manufacturing-Critical: only downsize when Avg_CPU < 10%
            if avg < 10:
                new = max(4, round(vcpu * 0.75))
                note = "Critical System – Cautious Downsizing by ~25%"
                if is_mfg:
                    note += " (Manufacturing Critical – Extra Conservatism; Human Review Required)"
                elif is_bc_mc:
                    note += " (Human Intervention Required)"
                return f"{note} → {int(new)} vCPU", int(new), lifecycle
        else:
            # Normal systems: downsize when Avg_CPU < 20%
            if avg < 20:
                new = max(4, round(vcpu * 0.75))
                return f"Normal System – Downsize by ~25% → {int(new)} vCPU", int(new), lifecycle

        if avg > 80:
            new = round(vcpu * 1.25)
            note = "Upsize by ~25% – Flag Only"
            if is_bc_mc or is_mfg:
                note += " (Human Intervention Required)"
            return f"{note} → {int(new)} vCPU", int(new), "Upsize Flag"

        return "No specific recommendation", int(vcpu), lifecycle

    result = df.apply(_rec, axis=1, result_type="expand")
    df["CPU_Recommendation"] = result[0]
    df["Recommended_vCPU"]   = result[1]
    df["Lifecycle_Flag"]     = result[2]
    return df


# ── UC 3.4 – Criticality-Aware RAM Optimization ───────────────────────────────

def find_criticality_ram_optimizations(df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.4 Criticality-Aware RAM Optimization.
    Applies to ALL rows (all environments, all criticality levels).

    Eligible rows = any of:
      Avg_FreeMem_12m > 60%   → normal systems candidate for downsize
      Avg_FreeMem_12m > 80%   → critical systems candidate for downsize
      Avg_FreeMem_12m < 30%   → normal systems candidate for upsize flag
      Avg_FreeMem_12m < 20%   → critical systems candidate for upsize flag
      Min_FreeMem_12m < 5%    → lifecycle risk flag
    """
    eligible = _criticality_ram_eligible(df)
    rec = _criticality_ram_recommendation(eligible)
    rec["Optimization_Type"] = "Crit_RAM_Optimization"
    rec["Recommendation_Type"] = "Crit_RAM_Recommendation"
    logger.info("UC 3.4 criticality RAM optimizations: %d rows.", len(rec))
    return rec


def _criticality_ram_eligible(df: pd.DataFrame) -> pd.DataFrame:
    # FIX 4: Expanded mask to capture normal system thresholds:
    #   Normal downsize: Avg_FreeMem > 60% (critical uses > 80%, covered by > 60%)
    #   Normal upsize:   Avg_FreeMem < 30% (critical uses < 20%, covered by < 30%)
    mask = (
        (df["Avg_FreeMem_12m"].fillna(0) > 60) |   # covers normal (>60%) and critical (>80%)
        (df["Avg_FreeMem_12m"].fillna(0) < 30) |   # covers normal (<30%) and critical (<20%)
        (df["Min_FreeMem_12m"].fillna(0) < 5)
    )
    return df[mask].copy()


def _criticality_ram_recommendation(eligible_df: pd.DataFrame) -> pd.DataFrame:
    """
    UC 3.4 recommendations:
      Critical systems:
        Avg_FreeMem > 80%   → Downsize by ~25%, rounded to practical size, min 8 GiB
        Avg_FreeMem < 20%   → Upsize flag only (no automated action)
      Normal systems:
        Avg_FreeMem > 60% AND Min_FreeMem > 5%  → Downsize by ~25%, rounded, min 8 GiB
        Avg_FreeMem < 30%   → Upsize flag only (no automated action)
      Min_FreeMem < 5%    → Lifecycle risk flag (can co-exist with other recommendations)
    """
    df = eligible_df.copy()
    if df.empty:
        for col in ("RAM_Recommendation", "Recommended_RAM_GiB", "Lifecycle_Flag"):
            df[col] = pd.Series(dtype="object")
        return df

    has_criticality = COL_CRITICALITY in df.columns

    def _rec(row):
        avg_mem    = row["Avg_FreeMem_12m"]
        min_mem    = row["Min_FreeMem_12m"]
        ram        = row["Current_RAM_GiB"]
        criticality = str(row.get(COL_CRITICALITY, "")) if has_criticality else ""
        is_mfg     = criticality in MFG_CRITICAL_VALS
        is_bc_mc   = criticality in CRITICAL_VALS
        # FIX 5: Branch on critical vs normal for downsize/upsize thresholds.
        is_critical_system = is_bc_mc or is_mfg

        if pd.isna(avg_mem) or pd.isna(ram):
            return "Insufficient data", np.nan, ""

        lifecycle = ""
        if not pd.isna(min_mem) and min_mem < 5:
            lifecycle = "Lifecycle Risk: Low Minimum Memory (<5%)"

        human_note = ""
        if is_bc_mc:
            human_note = " (Human Intervention Required)"
        elif is_mfg:
            human_note = " (Manufacturing Critical – Extra Conservatism; Human Review Required)"

        if is_critical_system:
            # Critical systems: downsize only when Avg_FreeMem > 80%
            if avg_mem > 80:
                target = _round_ram(ram * 0.75, 8)
                return (
                    f"Critical System – Downsize RAM by ~25%{human_note} → {target} GiB",
                    target,
                    lifecycle,
                )
            # Critical systems: upsize flag when Avg_FreeMem < 20%
            if avg_mem < 20:
                upsize_note = f"Upsize RAM – Flag Only (Avg Free Mem < 20%){human_note}"
                return upsize_note, int(ram), lifecycle or "Upsize Flag"
        else:
            # Normal systems: downsize when Avg_FreeMem > 60% AND Min_FreeMem > 5%
            if avg_mem > 60 and (pd.isna(min_mem) or min_mem > 5):
                target = _round_ram(ram * 0.75, 8)
                return (
                    f"Normal System – Downsize RAM by ~25% → {target} GiB",
                    target,
                    lifecycle,
                )
            # Normal systems: upsize flag when Avg_FreeMem < 30%
            if avg_mem < 30:
                upsize_note = "Upsize RAM – Flag Only (Avg Free Mem < 30%)"
                return upsize_note, int(ram), lifecycle or "Upsize Flag"

        return "No specific recommendation", int(ram), lifecycle

    result = df.apply(_rec, axis=1, result_type="expand")
    df["RAM_Recommendation"]  = result[0]
    df["Recommended_RAM_GiB"] = result[1]
    df["Lifecycle_Flag"]      = result[2]
    return df


# ── Lifecycle Risk Flags ──────────────────────────────────────────────────────

def find_lifecycle_risk_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag ALL systems (not just critical) that meet ANY lifecycle risk condition:
      • Is a Critical system (Business Critical / Mission Critical / Manufacturing Critical)
      • Peak_CPU_12m > 95%
      • Min_FreeMem_12m < 5%

    Returns a DataFrame with 'Lifecycle_Risk_Reasons' and 'Human_Review_Required'.
    """
    has_criticality = COL_CRITICALITY in df.columns

    is_critical = (
        df[COL_CRITICALITY].isin(ALL_CRITICAL_VALS)
        if has_criticality
        else pd.Series(False, index=df.index)
    )
    high_peak   = df["Peak_CPU_12m"].fillna(0)    > 95
    low_min_mem = df["Min_FreeMem_12m"].fillna(100) < 5

    flagged = df[is_critical | high_peak | low_min_mem].copy()
    if flagged.empty:
        flagged["Lifecycle_Risk_Reasons"] = pd.Series(dtype="object")
        flagged["Human_Review_Required"]  = pd.Series(dtype="object")
        return flagged

    def _flag(row):
        reasons = []
        if has_criticality and row.get(COL_CRITICALITY, "") in ALL_CRITICAL_VALS:
            reasons.append(f"Critical System ({row[COL_CRITICALITY]})")
        if not pd.isna(row["Peak_CPU_12m"]) and row["Peak_CPU_12m"] > 95:
            reasons.append("High Peak CPU (>95%)")
        if not pd.isna(row["Min_FreeMem_12m"]) and row["Min_FreeMem_12m"] < 5:
            reasons.append("Low Minimum Memory (<5%)")
        return "; ".join(reasons)

    flagged["Lifecycle_Risk_Reasons"] = flagged.apply(_flag, axis=1)
    flagged["Human_Review_Required"]  = "Yes"
    logger.info("Lifecycle risk flags: %d systems flagged.", len(flagged))
    return flagged


# ── Physical Systems Flag ─────────────────────────────────────────────────────

def find_physical_systems_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identify physical systems for human review.

    IsVirtual == "false" (case-insensitive) → Physical → flag for human review.
    All other values including blank/NaN → treated as Virtual (not flagged here).

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
    physical["Human_Review_Required"] = "Yes – Physical System"
    physical["Review_Reason"]         = (
        "Physical system detected. Human review required before any "
        "rightsizing action is taken."
    )
    logger.info("Physical systems flagged: %d.", len(physical))
    return physical
