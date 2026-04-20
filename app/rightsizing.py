from io import BytesIO
from pathlib import Path
import sys

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
FILE_PATH = BASE_DIR / "sample_data" / "Copy-Sheet 1.xlsx"
OUTPUT = "Rightsizing_Results1.xlsx"

RIGHTSIZING_SHEETS = [
    ("prod_cpu_optimization", "PROD_CPU_Optimization", "Prod Cpu Optimization"),
    ("prod_cpu_recommendation", "PROD_CPU_Recommendation", "Prod Cpu Recommendation"),
    ("nonprod_cpu_optimization", "NONPROD_CPU_Optimization", "Nonprod Cpu Optimization"),
    ("nonprod_cpu_recommendation", "NONPROD_CPU_Recommendation", "Nonprod Cpu Recommendation"),
    ("prod_ram_optimization", "PROD_RAM_Optimization", "Prod Ram Optimization"),
    ("prod_ram_recommendation", "PROD_RAM_Recommendation", "Prod Ram Recommendation"),
    ("nonprod_ram_optimization", "NONPROD_RAM_Optimization", "Nonprod Ram Optimization"),
    ("nonprod_ram_recommendation", "NONPROD_RAM_Recommendation", "Nonprod Ram Recommendation"),
]

NON_PROD_ENVS = ["Development", "Disaster recovery", "Test", "QA", "UAT"]
PRACTICAL_RAM = [4, 6, 8, 10, 12, 16, 20, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 2048]
MONTH_ORDER = {"Mar": 1, "Apr": 2, "May": 3, "June": 4, "July": 5, "Aug": 6, "Sept": 7, "Oct": 8, "Nov": 9, "Dec": 10, "Jan": 11, "Feb": 12}


def is_monthly(col):
    return any(month in col for month in MONTH_ORDER)


def chron_sort(cols):
    return sorted(cols, key=lambda col: next((order for month, order in MONTH_ORDER.items() if month in col), 99))


def clean(series):
    return pd.to_numeric(
        series.astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False).str.strip().replace(
            {"NA": np.nan, "N/A": np.nan, "nan": np.nan, "None": np.nan, "-": np.nan, "": np.nan}
        ),
        errors="coerce",
    )


def round_ram(value, min_gib):
    value = max(float(value), float(min_gib))
    result = float(min_gib)
    for size in PRACTICAL_RAM:
        if min_gib <= size <= value:
            result = size
    return result


def score_rightsizing_sheet(columns):
    score = 0
    if "Environment" in columns:
        score += 3
    checks = [
        "Average CPU Utilisation (%)",
        "Maximum CPU Utilisation (%)",
        "Average free Memory (%)",
        "Minimum free Memory (%)",
        "Physical RAM (GiB)",
        "Logical CPU",
    ]
    for label in checks:
        if any(label in col for col in columns):
            score += 1
    return score


def load_rightsizing_source(file_path):
    excel = pd.ExcelFile(file_path)
    best_df = None
    best_score = -1

    for sheet_name in excel.sheet_names:
        df = pd.read_excel(excel, sheet_name=sheet_name)
        score = score_rightsizing_sheet(df.columns)
        if score > best_score:
            best_df = df
            best_score = score
        if score >= 9:
            return df

    if best_df is None or best_score < 4:
        raise ValueError("Could not find a sheet with the expected rightsizing columns.")
    return best_df


def load_and_compute(file_path):
    df = load_rightsizing_source(file_path).copy()
    if "Environment" not in df.columns:
        raise ValueError("The detected rightsizing sheet is missing the 'Environment' column.")
    df["Environment"] = df["Environment"].astype(str).str.strip()

    avg_cpu = chron_sort([col for col in df.columns if "Average CPU Utilisation (%)" in col and is_monthly(col)])
    max_cpu = chron_sort([col for col in df.columns if "Maximum CPU Utilisation (%)" in col and is_monthly(col)])
    avg_mem = chron_sort([col for col in df.columns if "Average free Memory (%)" in col and is_monthly(col)])
    min_mem = chron_sort([col for col in df.columns if "Minimum free Memory (%)" in col and is_monthly(col)])
    ram = chron_sort([col for col in df.columns if "Physical RAM (GiB)" in col and is_monthly(col)])
    lcpu = chron_sort([col for col in df.columns if "Logical CPU" in col and is_monthly(col)])

    for col in avg_cpu + max_cpu + avg_mem + min_mem + ram + lcpu:
        df[col] = clean(df[col])

    metrics = pd.DataFrame(
        {
            "Avg_CPU_12m": df[avg_cpu].mean(axis=1, skipna=True),
            "Peak_CPU_12m": df[max_cpu].max(axis=1, skipna=True),
            "Avg_FreeMem_12m": df[avg_mem].mean(axis=1, skipna=True),
            "Min_FreeMem_12m": df[min_mem].min(axis=1, skipna=True),
            "Current_vCPU": df[lcpu].ffill(axis=1).iloc[:, -1],
            "Current_RAM_GiB": df[ram].ffill(axis=1).iloc[:, -1],
        },
        index=df.index,
    )
    return pd.concat([df, metrics], axis=1)


def cpu_prod_optimization(df):
    prod = df[~df["Environment"].isin(NON_PROD_ENVS)]
    return prod[(prod["Avg_CPU_12m"] < 15) & (prod["Peak_CPU_12m"] <= 70) & (prod["Current_vCPU"] > 2)].copy()


def cpu_nonprod_optimization(df):
    nonprod = df[df["Environment"].isin(NON_PROD_ENVS)]
    return nonprod[(nonprod["Avg_CPU_12m"] < 15) & (nonprod["Peak_CPU_12m"] <= 80) & (nonprod["Current_vCPU"] > 2)].copy()


def ram_prod_optimization(df):
    prod = df[~df["Environment"].isin(NON_PROD_ENVS)]
    return prod[(prod["Avg_FreeMem_12m"] >= 35) & (prod["Min_FreeMem_12m"] >= 20) & (prod["Current_RAM_GiB"] > 8)].copy()


def ram_nonprod_optimization(df):
    nonprod = df[df["Environment"].isin(NON_PROD_ENVS)]
    return nonprod[(nonprod["Avg_FreeMem_12m"] >= 30) & (nonprod["Min_FreeMem_12m"] >= 15) & (nonprod["Current_RAM_GiB"] > 4)].copy()


def cpu_prod_recommendation(eligible_df):
    df = eligible_df.copy()

    def _rec(row):
        avg = row["Avg_CPU_12m"]
        peak = row["Peak_CPU_12m"]
        vcpu = row["Current_vCPU"]
        if pd.isna(avg) or pd.isna(peak) or pd.isna(vcpu):
            return "Insufficient data", np.nan
        vcpu = float(vcpu)
        if peak > 70:
            return "No reduction - Peak > 70% (protect peak performance)", int(vcpu)
        if avg < 10 and peak >= 50:
            new = max(2, round(vcpu * 0.50))
            return f"Reduce vCPU by ~50% -> {int(new)}", int(new)
        if 10 <= avg < 15 and peak <= 60:
            new = max(2, round(vcpu * 0.75))
            return f"Reduce vCPU by ~25% -> {int(new)}", int(new)
        return "No specific recommendation", int(vcpu)

    result = df.apply(_rec, axis=1, result_type="expand")
    df["CPU_Recommendation"] = result[0]
    df["Recommended_vCPU"] = result[1]
    return df


def cpu_nonprod_recommendation(eligible_df):
    df = eligible_df.copy()

    def _rec(row):
        avg = row["Avg_CPU_12m"]
        peak = row["Peak_CPU_12m"]
        vcpu = row["Current_vCPU"]
        if pd.isna(avg) or pd.isna(peak) or pd.isna(vcpu):
            return "Insufficient data", np.nan
        vcpu = float(vcpu)
        if peak > 80:
            return "No reduction - Peak > 80%", int(vcpu)
        if avg < 15 and peak < 60:
            new = max(2, round(vcpu * 0.45))
            return f"Reduce vCPU by ~50-60% -> {int(new)}", int(new)
        if 15 <= avg < 25 and peak <= 70:
            new = max(2, round(vcpu * 0.71))
            return f"Reduce vCPU by ~25-33% -> {int(new)}", int(new)
        return "No specific recommendation", int(vcpu)

    result = df.apply(_rec, axis=1, result_type="expand")
    df["CPU_Recommendation"] = result[0]
    df["Recommended_vCPU"] = result[1]
    return df


def ram_prod_recommendation(eligible_df):
    df = eligible_df.copy()

    def _rec(row):
        avg_mem = row["Avg_FreeMem_12m"]
        min_mem = row["Min_FreeMem_12m"]
        ram = row["Current_RAM_GiB"]
        if pd.isna(avg_mem) or pd.isna(ram):
            return "Insufficient data", np.nan
        if 35 <= avg_mem < 50:
            target = round_ram(ram * 0.75, 8)
            return f"Reduce RAM by ~25% -> {target} GiB", target
        if avg_mem > 50 and pd.notna(min_mem) and min_mem >= 30:
            target = round_ram(ram * 0.55, 8)
            return f"Reduce RAM by ~40-50% -> {target} GiB", target
        return "No specific recommendation", int(ram)

    result = df.apply(_rec, axis=1, result_type="expand")
    df["RAM_Recommendation"] = result[0]
    df["Recommended_RAM_GiB"] = result[1]
    return df


def ram_nonprod_recommendation(eligible_df):
    df = eligible_df.copy()

    def _rec(row):
        avg_mem = row["Avg_FreeMem_12m"]
        min_mem = row["Min_FreeMem_12m"]
        ram = row["Current_RAM_GiB"]
        if pd.isna(avg_mem) or pd.isna(ram):
            return "Insufficient data", np.nan
        if 30 <= avg_mem < 50:
            target = round_ram(ram * 0.67, 4)
            return f"Reduce RAM by ~33% -> {target} GiB", target
        if avg_mem > 50 and pd.notna(min_mem) and min_mem >= 25:
            target = round_ram(ram * 0.50, 4)
            return f"Reduce RAM by ~40-60% -> {target} GiB", target
        return "No specific recommendation", int(ram)

    result = df.apply(_rec, axis=1, result_type="expand")
    df["RAM_Recommendation"] = result[0]
    df["Recommended_RAM_GiB"] = result[1]
    return df


def build_rightsizing_report(file_path):
    df = load_and_compute(file_path)

    prod_cpu_opt = cpu_prod_optimization(df)
    nonprod_cpu_opt = cpu_nonprod_optimization(df)
    prod_ram_opt = ram_prod_optimization(df)
    nonprod_ram_opt = ram_nonprod_optimization(df)

    prod_cpu_rec = cpu_prod_recommendation(prod_cpu_opt)
    nonprod_cpu_rec = cpu_nonprod_recommendation(nonprod_cpu_opt)
    prod_ram_rec = ram_prod_recommendation(prod_ram_opt)
    nonprod_ram_rec = ram_nonprod_recommendation(nonprod_ram_opt)

    sheet_frames = {
        "prod_cpu_optimization": prod_cpu_opt,
        "prod_cpu_recommendation": prod_cpu_rec,
        "nonprod_cpu_optimization": nonprod_cpu_opt,
        "nonprod_cpu_recommendation": nonprod_cpu_rec,
        "prod_ram_optimization": prod_ram_opt,
        "prod_ram_recommendation": prod_ram_rec,
        "nonprod_ram_optimization": nonprod_ram_opt,
        "nonprod_ram_recommendation": nonprod_ram_rec,
    }

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_key, excel_name, _label in RIGHTSIZING_SHEETS:
            sheet_frames[sheet_key].to_excel(writer, sheet_name=excel_name, index=False)
    buf.seek(0)

    summary = {
        "prod_cpu_optimization": len(prod_cpu_opt),
        "nonprod_cpu_optimization": len(nonprod_cpu_opt),
        "prod_ram_optimization": len(prod_ram_opt),
        "nonprod_ram_optimization": len(nonprod_ram_opt),
    }
    return buf.getvalue(), summary, sheet_frames


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (LookupError, OSError, ValueError):
            pass

    content, summary, _sheet_frames = build_rightsizing_report(FILE_PATH)
    with open(OUTPUT, "wb") as output_file:
        output_file.write(content)

    print("===== UC 3.1 CPU RIGHT SIZING =====")
    print(f"  PROD CPU Optimization    : {summary['prod_cpu_optimization']:,}")
    print(f"  NONPROD CPU Optimization : {summary['nonprod_cpu_optimization']:,}")
    print(f"  TOTAL                    : {summary['prod_cpu_optimization'] + summary['nonprod_cpu_optimization']:,}")
    print()
    print("===== UC 3.2 RAM RIGHT SIZING =====")
    print(f"  PROD RAM Optimization    : {summary['prod_ram_optimization']:,}")
    print(f"  NONPROD RAM Optimization : {summary['nonprod_ram_optimization']:,}")
    print(f"  TOTAL                    : {summary['prod_ram_optimization'] + summary['nonprod_ram_optimization']:,}")
    print(f"\n✓ Saved → {OUTPUT}")
    print("  Sheets: PROD/NONPROD × CPU/RAM × Optimization/Recommendation (8 total)")


if __name__ == "__main__":
    main()
