"""
Build Plotly.js chart specs (data + layout) for interactive dashboard charts.
Specs are JSON-serializable and rendered client-side with Plotly.newPlot().
Hover shows value and name by default; layout tuned for visibility.
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Enterprise palette (matches dashboard UI)
COLORS = {
    "primary": "#0d9488",
    "secondary": "#1f2937",
    "accent1": "#0d9488",
    "accent2": "#e07c5c",
    "accent3": "#eab308",
    "other": "#94a3b8",
}
PALETTE = ["#0d9488", "#1f2937", "#e07c5c", "#eab308", "#0f766e", "#475569", "#ea580c", "#ca8a04"]


def _zone_colors(labels: List[str]) -> List[str]:
    colors = []
    for index, label in enumerate(labels):
        normalized = str(label).strip().lower()
        if "avs" in normalized or "private cloud avs" in normalized:
            colors.append("#89D329")  # requested green for Private Cloud AVS
        elif "public" in normalized:
            colors.append("#00BCFF")  # sky blue for Public Cloud
        elif "private" in normalized:
            colors.append("#89D329")  # requested green for Private Cloud
        else:
            colors.append(PALETTE[index % len(PALETTE)])
    return colors

# Default layout: room for axis titles; height matches large containers so chart fits in one view
CHART_HEIGHT = 420
AXIS_TITLE_FONT = {"size": 10}
# Bar/line: margins leave room for axis labels so nothing is clipped
DEFAULT_LAYOUT = {
    "autosize": True,
    "margin": {"t": 56, "b": 60, "l": 64, "r": 32, "pad": 0},
    "height": CHART_HEIGHT,
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "Inter, system-ui, sans-serif", "size": 11},
    "title": {"font": {"size": 12}, "x": 0.5, "xanchor": "center"},
    "hovermode": "closest",
    "showlegend": True,
    "legend": {"orientation": "h", "yanchor": "top", "y": 1.02, "xanchor": "center", "x": 0.5, "font": {"size": 9}},
    "xaxis": {
        "title": {"text": "", "font": AXIS_TITLE_FONT},
        "tickfont": {"size": 9},
        "gridcolor": "rgba(0,0,0,0.06)",
        "automargin": True,
        "showline": True,
        "linecolor": "rgba(0,0,0,0.2)",
        "mirror": True,
    },
    "yaxis": {
        "title": {"text": "", "font": AXIS_TITLE_FONT},
        "tickfont": {"size": 9},
        "gridcolor": "rgba(0,0,0,0.06)",
        "automargin": True,
        "showline": True,
        "linecolor": "rgba(0,0,0,0.2)",
        "mirror": True,
    },
}


def _find_key(row: Dict[str, Any], patterns: List[str]) -> str:
    if not row or not isinstance(row, dict):
        return ""
    for p in patterns:
        p_lower = p.lower()
        for k in list(row.keys()):
            if p_lower in k.lower():
                return k
    return ""


def _layout(title: str, **overrides) -> Dict[str, Any]:
    # out = {**DEFAULT_LAYOUT, "title": {"text": title, **DEFAULT_LAYOUT["title"]}}  # heading shown
    out = {**DEFAULT_LAYOUT, "title": {"text": "", **DEFAULT_LAYOUT["title"]}}  # heading hidden
    for k, v in overrides.items():
        if k in ("xaxis", "yaxis") and k in out and isinstance(v, dict) and isinstance(out[k], dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


# Pie/donut: generous margins so the circle is centered and clearly visible
PIE_MARGIN = {"t": 56, "b": 56, "l": 80, "r": 80, "pad": 0}


def _layout_pie(title: str, **overrides) -> Dict[str, Any]:
    # out = {**DEFAULT_LAYOUT, "title": {"text": title, **DEFAULT_LAYOUT["title"]}, "margin": PIE_MARGIN}  # heading shown
    out = {**DEFAULT_LAYOUT, "title": {"text": "", **DEFAULT_LAYOUT["title"]}, "margin": PIE_MARGIN}  # heading hidden
    out.update(overrides)
    return out


def get_all_plotly_specs(
    rule_results: Dict[str, Any],
    license_metrics: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Return dict of chart_id -> {data: [...], layout: {...}} for Plotly.newPlot()."""
    specs = {}
    azure = rule_results.get("azure_payg") or []
    retired = rule_results.get("retired_devices") or []
    by_product = license_metrics.get("by_product") or []
    azure_count = rule_results.get("azure_payg_count", 0)
    retired_count = rule_results.get("retired_count", 0)
    total_demand = license_metrics.get("total_demand_quantity") or 0
    total_cost = float(license_metrics.get("total_license_cost") or 0)
    total_demand = total_demand or 1
    payg_share = (azure_count / total_demand) if total_demand else 0
    payg_zone_breakdown = rule_results.get("payg_zone_breakdown") or {}

    # Zones from Rule 1
    zones = {"Public Cloud": 0, "Private Cloud AVS": 0}
    if azure and len(azure) > 0:
        zone_key = _find_key(azure[0], ["hosting", "zone", "u_hosting"])
        for r in azure:
            z_raw = str((r.get(zone_key) if zone_key else None) or "").strip()
            z_norm = z_raw.lower()
            if "avs" in z_norm:
                zone_label = "Private Cloud AVS"
            elif "public" in z_norm:
                zone_label = "Public Cloud"
            else:
                continue  # skip other zones like Private Cloud
            zones[zone_label] = zones.get(zone_label, 0) + 1

    zone_names = list(zones.keys())
    zone_counts = list(zones.values())
    payg_zone_labels = payg_zone_breakdown.get("labels") or ["Public Cloud", "Private Cloud AVS"]
    payg_zone_current = payg_zone_breakdown.get("current") or [
        zones.get("Public Cloud", 0),
        zones.get("Private Cloud AVS", 0),
    ]
    payg_zone_estimated = payg_zone_breakdown.get("estimated") or [
        zones.get("Public Cloud", 0),
        zones.get("Private Cloud AVS", 0),
    ]

    try:
        # --- chart_azure_cores: bar (device vs CPU cores) ---
        labels_cores = ["No data"]
        values_cores = [0]
        if azure and len(azure) > 0:
            r0 = azure[0]
            cores_key = _find_key(r0, ["cpu", "core", "u_cpu"])
            device_key = _find_key(r0, ["device_name", "device_ci", "device"])
            if cores_key or device_key:
                top = azure[:15]
                labels_cores = [str((r.get(device_key) if device_key else "Device") or "Device")[:14] for r in top]
                values_cores = [float(r.get(cores_key, 0) or 0) for r in top] if cores_key else [0] * len(top)
        specs["chart_azure_cores"] = {
            "data": [{
                "type": "bar",
                "x": labels_cores,
                "y": values_cores,
                "marker": {"color": "#0EA5E9"},  # sky-blue tone like other charts
                "text": values_cores,
                "texttemplate": "%{y}",
                "textposition": "inside",
                "hovertemplate": "<b>%{x}</b><br>CPU Cores: %{y}<extra></extra>",
            }],
            "layout": _layout("CPU Core Distribution", xaxis={"title": {"text": "Device", "font": AXIS_TITLE_FONT}, "tickangle": -35}, yaxis={"title": {"text": "CPU Cores", "font": AXIS_TITLE_FONT}}),
        }

        # --- chart_azure_zones: pie (hosting zone breakdown) ---
        specs["chart_azure_zones"] = {
            "data": [{
                "type": "pie",
                "labels": zone_names,
                "values": zone_counts,
                "hole": 0.5,
                "marker": {"colors": _zone_colors(zone_names)},
                "textinfo": "label+percent",
                "hovertemplate": "<b>%{label}</b><br>Devices: %{value}<br>%{percent}<extra></extra>",
            }],
            "layout": _layout_pie("Hosting Zone Breakdown"),
        }

        # --- chart_retired: pie ---
        specs["chart_retired"] = {
            "data": [{
                "type": "pie",
                "labels": ["Retired with installs", "Other"],
                "values": [retired_count, max(1, 100 - retired_count)],
                "marker": {"colors": [COLORS["accent3"], COLORS["other"]]},
                "hovertemplate": "<b>%{label}</b><br>%{value}<extra></extra>",
            }],
            "layout": _layout_pie("Status Comparison"),
        }

        # --- chart_retired_env: horizontal bar ---
        env_counts = {}
        if retired and len(retired) > 0:
            env_key = _find_key(retired[0], ["environment", "env"])
            for r in retired:
                e = str((r.get(env_key) if env_key else None) or "N/A")
                env_counts[e] = env_counts.get(e, 0) + 1
        if not env_counts:
            env_counts = {"Retired": retired_count} if retired_count else {"No data": 0}
        env_labels = list(env_counts.keys())
        env_vals = list(env_counts.values())
        env_colors = []
        for label in env_labels:
            normalized = str(label).strip().lower()
            if "dev" in normalized:
                env_colors.append("#1EA7E1")
            elif "prod" in normalized:
                env_colors.append("#84D91D")
            elif "test" in normalized:
                env_colors.append("#DCE3EC")
            else:
                env_colors.append(PALETTE[len(env_colors) % len(PALETTE)])
        specs["chart_retired_env"] = {
            "data": [{
                "type": "bar",
                "orientation": "h",
                "y": env_labels,
                "x": env_vals,
                "marker": {"color": env_colors},
                "hovertemplate": "<b>%{y}</b><br>Count: %{x}<extra></extra>",
            }],
            "layout": _layout("Risk By Environment", xaxis={"title": {"text": "Count", "font": AXIS_TITLE_FONT}}, yaxis={"title": {"text": "Environment", "font": AXIS_TITLE_FONT}}),
        }

        # --- chart_demand: bar (demand by product) ---
        labels_bp = [str(p.get("product", ""))[:16] for p in by_product[:15]]
        qty_data = [float(p.get("quantity", 0) or 0) for p in by_product[:15]]
        if not labels_bp:
            labels_bp, qty_data = ["No data"], [0]
        specs["chart_demand"] = {
            "data": [{
                "type": "bar",
                "x": labels_bp,
                "y": qty_data,
                "marker": {"color": COLORS["primary"]},
                "hovertemplate": "<b>%{x}</b><br>Quantity: %{y:,.0f}<extra></extra>",
            }],
            "layout": _layout("Demand by Product Line", xaxis={"title": {"text": "Product", "font": AXIS_TITLE_FONT}, "tickangle": -35}, yaxis={"title": {"text": "Quantity", "font": AXIS_TITLE_FONT}}),
        }

        # --- chart_cost: bar (cost by product) ---
        cost_data = [float(p.get("cost", 0) or 0) for p in by_product[:15]]
        if len(cost_data) != len(labels_bp):
            cost_data = (cost_data[: len(labels_bp)] or [0]) + [0] * (len(labels_bp) - len(cost_data))
        if not cost_data:
            cost_data = [0]
        specs["chart_cost"] = {
            "data": [{
                "type": "bar",
                "x": labels_bp[: len(cost_data)],
                "y": cost_data,
                "marker": {"color": COLORS["accent2"]},
                "hovertemplate": "<b>%{x}</b><br>Cost: %{y:,.0f}<extra></extra>",
            }],
            "layout": _layout("Cost Projection Matrix", xaxis={"title": {"text": "Product", "font": AXIS_TITLE_FONT}, "tickangle": -35}, yaxis={"title": {"text": "Cost", "font": AXIS_TITLE_FONT}}),
        }

        # --- chart_overview: donut ---
        specs["chart_overview"] = {
            "data": [{
                "type": "pie",
                "labels": ["Azure PAYG", "Retired"],
                "values": [azure_count, retired_count] if (azure_count or retired_count) else [0],
                "hole": 0.6,
                "marker": {"colors": [COLORS["primary"], COLORS["accent3"]]},
                "hovertemplate": "<b>%{label}</b><br>%{value}<extra></extra>",
            }],
            "layout": _layout_pie("Optimization vs Risk"),
        }

        # --- chart_devices: donut ---
        specs["chart_devices"] = {
            "data": [{
                "type": "pie",
                "labels": ["Azure PAYG", "Retired Issues", "Standard"],
                "values": [azure_count, retired_count, total_demand] if (azure_count or retired_count or total_demand) else [0],
                "hole": 0.6,
                "marker": {"colors": [COLORS["primary"], COLORS["accent3"], COLORS["other"]]},
                "hovertemplate": "<b>%{label}</b><br>%{value}<extra></extra>",
            }],
            "layout": _layout_pie("Global Device Fleet State"),
        }

        # --- chart_license_cost_donut ---
        cost_labels = [str(p.get("product", ""))[:14] for p in by_product[:10]]
        cost_vals = [float(p.get("cost", 0) or 0) for p in by_product[:10]]
        if not cost_labels or not any(c > 0 for c in cost_vals):
            cost_labels, cost_vals = ["No data"], [1]
        specs["chart_license_cost_donut"] = {
            "data": [{
                "type": "pie",
                "labels": cost_labels,
                "values": cost_vals,
                "hole": 0.6,
                "marker": {"colors": PALETTE[: len(cost_labels)]},
                "hovertemplate": "<b>%{label}</b><br>Cost: %{value:,.0f}<br>%{percent}<extra></extra>",
            }],
            "layout": _layout_pie("License Cost by Product"),
        }

        # --- chart_azure_by_zone_bar ---
        specs["chart_azure_by_zone_bar"] = {
            "data": [
                {
                    "type": "bar",
                    "name": "Current",
                    "x": payg_zone_labels,
                    "y": payg_zone_current,
                    "marker": {"color": "#00BCFF"},
                    "hovertemplate": "<b>%{x}</b><br>Current: %{y}<extra></extra>",
                },
                {
                    "type": "bar",
                    "name": "Estimated",
                    "x": payg_zone_labels,
                    "y": payg_zone_estimated,
                    "marker": {"color": "#89D329"},
                    "hovertemplate": "<b>%{x}</b><br>Estimated: %{y}<extra></extra>",
                },
            ],
            "layout": _layout(
                "Azure PAYG Candidates by Hosting Zone",
                barmode="group",
                xaxis={"title": {"text": "Hosting Zone", "font": AXIS_TITLE_FONT}},
                yaxis={"title": {"text": "Devices", "font": AXIS_TITLE_FONT}},
            ),
        }

        # --- chart_byol_vs_payg ---
        payg_val = total_cost * (1 - payg_share * 0.28) if payg_share else total_cost * 0.85
        specs["chart_byol_vs_payg"] = {
            "data": [{
                "type": "bar",
                "x": ["BYOL", "PAYG (est.)"],
                "y": [total_cost, payg_val],
                "marker": {"color": [COLORS["secondary"], COLORS["accent1"]]},
                "text": [f"{total_cost:,.0f}", f"{payg_val:,.0f}"],
                "textposition": "inside",
                "hovertemplate": "<b>%{x}</b><br>Cost: %{y:,.0f}<extra></extra>",
            }],
            "layout": _layout("Cost: BYOL vs PAYG", xaxis={"title": {"text": "Model", "font": AXIS_TITLE_FONT}}, yaxis={"title": {"text": "Cost", "font": AXIS_TITLE_FONT}}),
        }

        # --- chart_retired_services ---
        specs["chart_retired_services"] = {
            "data": [{
                "type": "bar",
                "orientation": "h",
                "y": ["SQL Server"] if retired_count else ["No retired with software"],
                "x": [retired_count] if retired_count else [0],
                "marker": {"color": COLORS["accent3"]},
                "hovertemplate": "<b>%{y}</b><br>Count: %{x}<extra></extra>",
            }],
            "layout": _layout("Retired Devices Still Running Software", xaxis={"title": {"text": "Count", "font": AXIS_TITLE_FONT}}, yaxis={"title": {"text": "Software", "font": AXIS_TITLE_FONT}}),
        }

        # --- chart_cpu_histogram ---
        core_buckets = {"2": 0, "4": 0, "8": 0, "16": 0, "16+": 0}
        if azure and len(azure) > 0:
            cores_key = _find_key(azure[0], ["cpu", "core", "u_cpu"])
            if cores_key:
                for r in azure:
                    c = float(r.get(cores_key, 0) or 0)
                    if c <= 2:
                        core_buckets["2"] += 1
                    elif c <= 4:
                        core_buckets["4"] += 1
                    elif c <= 8:
                        core_buckets["8"] += 1
                    elif c <= 16:
                        core_buckets["16"] += 1
                    else:
                        core_buckets["16+"] += 1
        bin_labels = ["2 cores", "4 cores", "8 cores", "16 cores", "16+ cores"]
        bin_counts = [core_buckets["2"], core_buckets["4"], core_buckets["8"], core_buckets["16"], core_buckets["16+"]]
        specs["chart_cpu_histogram"] = {
            "data": [{
                "type": "bar",
                "x": bin_labels,
                "y": bin_counts,
                "marker": {"color": COLORS["primary"]},
                "hovertemplate": "<b>%{x}</b><br>Devices: %{y}<extra></extra>",
            }],
            "layout": _layout("Device Distribution by CPU Cores", xaxis={"title": {"text": "Core bucket", "font": AXIS_TITLE_FONT}}, yaxis={"title": {"text": "Devices", "font": AXIS_TITLE_FONT}}),
        }

        # --- chart_env_pie ---
        env_labels = list(zones.keys()) if zones else ["Azure", "On-Prem", "Private Cloud"]
        env_vals = list(zones.values()) if zones else [azure_count, max(0, total_demand - azure_count), 0]
        if not env_vals or all(v == 0 for v in env_vals):
            env_labels, env_vals = ["No data"], [1]
        specs["chart_env_pie"] = {
            "data": [{
                "type": "pie",
                "labels": env_labels,
                "values": env_vals,
                "marker": {"colors": _zone_colors(env_labels)},
                "hovertemplate": "<b>%{label}</b><br>%{value}<extra></extra>",
            }],
            "layout": _layout_pie("Device Environment Distribution"),
        }

        # --- chart_top10_cost ---
        sorted_product = sorted(by_product, key=lambda p: float(p.get("cost", 0) or 0), reverse=True)[:10]
        top_labels = [str(p.get("product", ""))[:16] for p in sorted_product]
        top_costs = [float(p.get("cost", 0) or 0) for p in sorted_product]
        if not top_labels or not any(c > 0 for c in top_costs):
            top_labels, top_costs = ["No data"], [0]
        specs["chart_top10_cost"] = {
            "data": [{
                "type": "bar",
                "x": top_labels,
                "y": top_costs,
                "marker": {"color": COLORS["accent2"]},
                "hovertemplate": "<b>%{x}</b><br>Cost: %{y:,.0f}<extra></extra>",
            }],
            "layout": _layout("Top 10 by License Cost", xaxis={"title": {"text": "Product", "font": AXIS_TITLE_FONT}, "tickangle": -35}, yaxis={"title": {"text": "Cost", "font": AXIS_TITLE_FONT}}),
        }

        # --- chart_waterfall: bar chart (waterfall-style with positive/negative and total) ---
        payg_savings_est = total_cost * payg_share * 0.28 if payg_share else 0
        retired_savings_est = (retired_count / max(1, total_demand)) * total_cost * 0.05 if total_demand else 0
        final_cost = total_cost - payg_savings_est - retired_savings_est
        wf_labels = ["Current Cost", "PAYG Savings", "Retired Savings", "Final Cost"]
        wf_vals = [total_cost, -payg_savings_est, -retired_savings_est, final_cost]
        wf_colors = [COLORS["secondary"], COLORS["accent3"], COLORS["accent3"], COLORS["accent1"]]
        specs["chart_waterfall"] = {
            "data": [{
                "type": "bar",
                "x": wf_labels,
                "y": wf_vals,
                "marker": {"color": wf_colors},
                "text": [f"{v:,.0f}" for v in wf_vals],
                "textposition": "inside",
                "hovertemplate": "<b>%{x}</b><br>%{y:,.0f}<extra></extra>",
            }],
            "layout": _layout("Cost Before vs After Optimization", xaxis={"title": {"text": "Category", "font": AXIS_TITLE_FONT}, "tickangle": -25}, yaxis={"title": {"text": "Amount", "font": AXIS_TITLE_FONT}, "zeroline": True}),
        }
    except Exception as e:
        logger.exception("Plotly spec build failed: %s", e)
        # Placeholder spec for missing charts
        placeholder = {
            "data": [{"type": "bar", "x": ["No data"], "y": [0], "hovertemplate": "%{x}<extra></extra>"}],
            "layout": _layout("Chart unavailable"),
        }
        all_ids = [
            "chart_azure_cores", "chart_azure_zones", "chart_retired", "chart_retired_env", "chart_demand", "chart_cost",
            "chart_overview", "chart_devices", "chart_license_cost_donut", "chart_azure_by_zone_bar", "chart_byol_vs_payg",
            "chart_retired_services", "chart_cpu_histogram", "chart_env_pie", "chart_top10_cost", "chart_waterfall",
        ]
        for cid in all_ids:
            if cid not in specs:
                specs[cid] = placeholder

    return specs
