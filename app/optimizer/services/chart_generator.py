"""
Generate chart images server-side with matplotlib. Returns base64-encoded PNG or GIF
strings for embedding in the dashboard template. Animated charts use GIF (bars grow
from 0, pie/doughnut fill counter-clockwise).
"""
import base64
import io
import logging
import os
import tempfile
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Use non-interactive backend for server
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.animation as mplanim

# Animation settings
ANIM_FRAMES = 24
ANIM_INTERVAL_MS = 42
# Slower fill for pie/doughnut so user can see each wedge
PIE_ANIM_FRAMES = 24
PIE_ANIM_INTERVAL_MS = 120

# High-visibility color scheme (no grey)
COLORS = {
    "primary": "#0ea5e9",
    "secondary": "#0f172a",
    "accent1": "#14b8a6",
    "accent2": "#8b5cf6",
    "accent3": "#f59e0b",
    "text_muted": "#334155",
    "other": "#38bdf8",
}
PALETTE = [
    "#0369a1", "#0d9488", "#0f172a", "#6366f1",
    "#8b5cf6", "#0ea5e9", "#14b8a6", "#06b6d4",
    "#f59e0b", "#ec4899", "#22c55e", "#f97316",
]


def _zone_colors(labels: List[str]) -> List[str]:
    colors = []
    for index, label in enumerate(labels):
        normalized = str(label).strip().lower()
        if "avs" in normalized:
            colors.append("#18AEEF")
        elif "public" in normalized:
            colors.append("#84D91D")
        elif "private" in normalized:
            colors.append("#153E5C")
        else:
            colors.append(PALETTE[index % len(PALETTE)])
    return colors

# ─── Shared legend style ──────────────────────────────────────────────────────
# Applied consistently to every chart that has a legend.
LEGEND_STYLE = dict(
    loc="upper left",
    bbox_to_anchor=(1.01, 1.0),   # just outside the right edge of the axes
    borderaxespad=0,
    frameon=True,
    framealpha=0.9,
    edgecolor="#e2e8f0",
    fontsize=8,
)

# Figure widths – wider than before so the legend column fits without clipping
FIG_W_NORMAL  = 6.4   # bar / histogram charts
FIG_W_PIE     = 6.0   # pie / doughnut (needs room for right-side legend)
FIG_H         = 3.6   # shared height


def _find_key(row: Dict[str, Any], patterns: List[str]) -> str:
    """Return first key in row that contains any of the patterns (case-insensitive)."""
    if not row or not isinstance(row, dict):
        return ""
    keys = list(row.keys())
    for p in patterns:
        p_lower = p.lower()
        for k in keys:
            if p_lower in k.lower():
                return k
    return ""


def _fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    # bbox_inches="tight" ensures the legend (outside axes) is included in the export
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _anim_to_gif_base64(anim, fig):
    """Save matplotlib Animation as GIF. Returns (format, base64). format is 'gif' or 'png' on fallback."""
    path = None
    try:
        fd, path = tempfile.mkstemp(suffix=".gif")
        os.close(fd)
        # extra_args passes bbox_inches to the Pillow writer so the legend isn't cropped
        anim.save(path, writer="pillow", dpi=100, savefig_kwargs={"bbox_inches": "tight"})
        # Force GIF to play once: remove Netscape loop block (no loop = play once in most browsers)
        try:
            with open(path, "rb") as f:
                data = bytearray(f.read())
            netscape = b"NETSCAPE2.0"
            idx = data.find(netscape)
            if idx != -1:
                start = idx - 3
                if start >= 0 and data[start] == 0x21 and data[start + 1] == 0xFF and data[start + 2] == 0x0B:
                    del data[start : start + 19]
                    with open(path, "wb") as f:
                        f.write(data)
        except Exception:
            pass
        with open(path, "rb") as rf:
            return ("gif", base64.b64encode(rf.read()).decode("utf-8"))
    except Exception as e:
        logger.warning("GIF animation save failed, using static frame: %s", e)
        return ("png", _fig_to_base64(fig))
    finally:
        plt.close(fig)
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


# ─── Bar chart (vertical, static) ────────────────────────────────────────────

def _bar_chart(
    labels: List[str],
    values: List[float],
    title: str,
    color: str = COLORS["primary"],
    xlabel: str = "Category",
    ylabel: str = "Count",
) -> str:
    fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
    if not labels or not values:
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
    else:
        x = range(len(labels))
        bars = ax.bar(x, values, color=color, edgecolor="white", linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_facecolor("white")
        # Single-series bar: place a compact legend to the right
        ax.legend(
            handles=[mpatches.Patch(color=color, label=ylabel)],
            **LEGEND_STYLE,
        )
    fig.subplots_adjust(right=0.80)   # reserve ~20 % of figure width for legend
    plt.tight_layout(rect=[0, 0, 0.80, 1])
    out = _fig_to_base64(fig)
    plt.close(fig)
    return out


# ─── Bar chart (vertical, animated) ──────────────────────────────────────────

def _bar_chart_animated(
    labels: List[str],
    values: List[float],
    title: str,
    color: str = COLORS["primary"],
    xlabel: str = "Category",
    ylabel: str = "Count",
) -> str:
    """Bar chart animated: bars grow from x-axis (0) to their values."""
    if not labels or not values:
        fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
        plt.tight_layout()
        b64 = _fig_to_base64(fig)
        plt.close(fig)
        return ("png", b64)

    fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
    x = range(len(labels))
    y_max = max(values) * 1.05 if max(values) > 0 else 1
    ax.set_ylim(0, y_max)
    ax.set_facecolor("white")
    # Reserve space for the right-side legend on every frame
    fig.subplots_adjust(right=0.78, bottom=0.28)

    _legend_handle = [mpatches.Patch(color=color, label=ylabel)]

    def update(frame: int):
        ax.clear()
        ax.set_ylim(0, y_max)
        ax.set_facecolor("white")
        t = (frame + 1) / ANIM_FRAMES
        animated_heights = [v * t for v in values]
        ax.bar(x, animated_heights, color=color, edgecolor="white", linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.legend(handles=_legend_handle, **LEGEND_STYLE)
        return ax.containers

    anim = mplanim.FuncAnimation(
        fig, update, frames=ANIM_FRAMES, interval=ANIM_INTERVAL_MS, blit=False
    )
    return _anim_to_gif_base64(anim, fig)


# ─── Bar chart (horizontal, static) ──────────────────────────────────────────

def _bar_chart_horizontal(
    labels: List[str],
    values: List[float],
    title: str,
    colors: List[str] = None,
    xlabel: str = "Count",
    ylabel: str = "Category",
) -> str:
    fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
    if not labels or not values:
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
    else:
        colors = colors or PALETTE[: len(labels)]
        y = range(len(labels))
        ax.barh(y, values, color=colors[: len(values)], edgecolor="white", linewidth=0.5)
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_facecolor("white")
        handles = [mpatches.Patch(color=c, label=l) for c, l in zip(colors[: len(labels)], labels)]
        ax.legend(handles=handles, **LEGEND_STYLE)
    fig.subplots_adjust(right=0.78)
    plt.tight_layout(rect=[0, 0, 0.78, 1])
    out = _fig_to_base64(fig)
    plt.close(fig)
    return out


# ─── Bar chart (horizontal, animated) ────────────────────────────────────────

def _bar_chart_horizontal_animated(
    labels: List[str],
    values: List[float],
    title: str,
    colors: List[str] = None,
    xlabel: str = "Count",
    ylabel: str = "Category",
) -> str:
    """Horizontal bar chart animated: bars grow from 0 to their values."""
    if not labels or not values:
        fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
        plt.tight_layout()
        b64 = _fig_to_base64(fig)
        plt.close(fig)
        return ("png", b64)

    fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
    colors = colors or PALETTE[: len(labels)]
    y_pos = range(len(labels))
    x_max = max(values) * 1.05 if max(values) > 0 else 1
    ax.set_xlim(0, x_max)
    ax.set_facecolor("white")
    fig.subplots_adjust(left=0.22, right=0.78)

    _handles = [mpatches.Patch(color=c, label=l) for c, l in zip(colors[: len(labels)], labels)]

    def update(frame: int):
        ax.clear()
        ax.set_xlim(0, x_max)
        ax.set_facecolor("white")
        t = (frame + 1) / ANIM_FRAMES
        animated_widths = [v * t for v in values]
        ax.barh(y_pos, animated_widths, color=colors[: len(values)], edgecolor="white", linewidth=0.5)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.legend(handles=_handles, **LEGEND_STYLE)
        return ax.containers

    anim = mplanim.FuncAnimation(
        fig, update, frames=ANIM_FRAMES, interval=ANIM_INTERVAL_MS, blit=False
    )
    return _anim_to_gif_base64(anim, fig)


# ─── Pie chart (static) ───────────────────────────────────────────────────────

def _pie_chart(labels: List[str], values: List[float], title: str, colors: List[str] = None) -> str:
    fig, ax = plt.subplots(figsize=(FIG_W_PIE, FIG_H), facecolor="white")
    if not labels or not values or all(v == 0 for v in values):
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
    else:
        colors = colors or (PALETTE[: len(labels)] if len(labels) <= len(PALETTE) else None)
        wedges, texts, autotexts = ax.pie(
            values, autopct="%1.0f%%", startangle=90, colors=colors,
            textprops={"fontsize": 8}, pctdistance=0.75,
        )
        # Legend to the right of the pie, outside the axes
        ax.legend(
            wedges, labels,
            **LEGEND_STYLE,
        )
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_facecolor("white")
    fig.subplots_adjust(right=0.72)
    out = _fig_to_base64(fig)
    plt.close(fig)
    return out


# ─── Pie chart (animated) ─────────────────────────────────────────────────────

def _pie_chart_animated(labels: List[str], values: List[float], title: str, colors: List[str] = None) -> str:
    """Pie chart animated: all wedges grow together from 0 to their values."""
    if not labels or not values or all(v == 0 for v in values):
        fig, ax = plt.subplots(figsize=(FIG_W_PIE, FIG_H), facecolor="white")
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
        plt.tight_layout()
        b64 = _fig_to_base64(fig)
        plt.close(fig)
        return ("png", b64)

    colors = colors or (PALETTE[: len(labels)] if len(labels) <= len(PALETTE) else None)
    n_frames = PIE_ANIM_FRAMES

    fig, ax = plt.subplots(figsize=(FIG_W_PIE, FIG_H), facecolor="white")
    ax.set_facecolor("white")
    fig.subplots_adjust(right=0.72)   # constant reservation so legend never shifts

    def update(frame: int):
        ax.clear()
        ax.set_facecolor("white")
        t = (frame + 1) / n_frames
        anim_values = [v * t for v in values]
        wedges, texts, autotexts = ax.pie(
            anim_values, autopct="%1.0f%%", startangle=90, colors=colors,
            textprops={"fontsize": 8}, pctdistance=0.75,
        )
        # Right-side legend – consistent position on every frame
        ax.legend(wedges, labels, **LEGEND_STYLE)
        ax.set_title(title, fontsize=11, fontweight="bold")
        return ax.containers

    anim = mplanim.FuncAnimation(
        fig, update, frames=n_frames, interval=PIE_ANIM_INTERVAL_MS, blit=False
    )
    return _anim_to_gif_base64(anim, fig)


# ─── Doughnut chart (static) ──────────────────────────────────────────────────

def _doughnut_chart(labels: List[str], values: List[float], title: str, colors: List[str] = None) -> str:
    fig, ax = plt.subplots(figsize=(FIG_W_PIE, FIG_H), facecolor="white")
    if not labels or not values or all(v == 0 for v in values):
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
    else:
        colors = colors or (PALETTE[: len(labels)] if len(labels) <= len(PALETTE) else None)
        wedges, texts, autotexts = ax.pie(
            values, autopct="%1.0f%%", startangle=90, colors=colors,
            textprops={"fontsize": 8}, pctdistance=0.75,
            wedgeprops=dict(width=0.6),
        )
        ax.legend(wedges, labels, **LEGEND_STYLE)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_facecolor("white")
    fig.subplots_adjust(right=0.72)
    out = _fig_to_base64(fig)
    plt.close(fig)
    return out


# ─── Doughnut chart (animated) ────────────────────────────────────────────────

def _doughnut_chart_animated(labels: List[str], values: List[float], title: str, colors: List[str] = None) -> str:
    """Doughnut chart animated: all wedges grow together from 0 to their values."""
    if not labels or not values or all(v == 0 for v in values):
        fig, ax = plt.subplots(figsize=(FIG_W_PIE, FIG_H), facecolor="white")
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
        plt.tight_layout()
        b64 = _fig_to_base64(fig)
        plt.close(fig)
        return ("png", b64)

    colors = colors or (PALETTE[: len(labels)] if len(labels) <= len(PALETTE) else None)
    n_frames = PIE_ANIM_FRAMES

    fig, ax = plt.subplots(figsize=(FIG_W_PIE, FIG_H), facecolor="white")
    ax.set_facecolor("white")
    fig.subplots_adjust(right=0.72)

    def update(frame: int):
        ax.clear()
        ax.set_facecolor("white")
        t = (frame + 1) / n_frames
        anim_values = [v * t for v in values]
        wedges, texts, autotexts = ax.pie(
            anim_values, autopct="%1.0f%%", startangle=90, colors=colors,
            textprops={"fontsize": 8}, pctdistance=0.75,
            wedgeprops=dict(width=0.6),
        )
        ax.legend(wedges, labels, **LEGEND_STYLE)
        ax.set_title(title, fontsize=11, fontweight="bold")
        return ax.containers

    anim = mplanim.FuncAnimation(
        fig, update, frames=n_frames, interval=PIE_ANIM_INTERVAL_MS, blit=False
    )
    return _anim_to_gif_base64(anim, fig)


# ─── Comparison bar chart ─────────────────────────────────────────────────────

def _comparison_bar_chart(
    labels: List[str],
    values: List[float],
    title: str,
    colors: List[str] = None,
    ylabel: str = "Cost",
) -> str:
    """Two or more bars for comparison (e.g. BYOL vs PAYG)."""
    if not labels or not values:
        fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
        plt.tight_layout()
        return _fig_to_base64(fig)

    fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
    colors = colors or [COLORS["primary"], COLORS["accent1"]]
    x = range(len(labels))
    bars = ax.bar(x, values, color=colors[: len(labels)], edgecolor="white", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_facecolor("white")
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + (max(values) * 0.02 if values else 0),
            f"{val:,.0f}", ha="center", va="bottom", fontsize=9, fontweight="bold",
        )
    # Multi-series legend to the right
    handles = [mpatches.Patch(color=c, label=l) for c, l in zip(colors[: len(labels)], labels)]
    ax.legend(handles=handles, **LEGEND_STYLE)
    fig.subplots_adjust(right=0.78)
    plt.tight_layout(rect=[0, 0, 0.78, 1])
    out = _fig_to_base64(fig)
    plt.close(fig)
    return out


# ─── Waterfall chart ──────────────────────────────────────────────────────────

def _grouped_bar_chart(
    labels: List[str],
    series: List[Dict[str, Any]],
    title: str,
    xlabel: str = "Category",
    ylabel: str = "Count",
) -> str:
    """Grouped bar chart for side-by-side comparisons within the same categories."""
    fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
    if not labels or not series:
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
        plt.tight_layout()
        return _fig_to_base64(fig)

    x = list(range(len(labels)))
    width = 0.35 if len(series) == 2 else max(0.2, 0.8 / max(1, len(series)))
    offset_base = (len(series) - 1) / 2
    handles = []

    for index, item in enumerate(series):
        name = item.get("name") or f"Series {index + 1}"
        values = list(item.get("values") or [0] * len(labels))
        if len(values) < len(labels):
            values = values + [0] * (len(labels) - len(values))
        elif len(values) > len(labels):
            values = values[: len(labels)]
        color = item.get("color") or PALETTE[index % len(PALETTE)]
        positions = [value + ((index - offset_base) * width) for value in x]
        ax.bar(positions, values, width * 0.92, color=color, edgecolor="white", linewidth=0.8)
        handles.append(mpatches.Patch(color=color, label=name))

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_facecolor("white")
    ax.legend(handles=handles, **LEGEND_STYLE)
    fig.subplots_adjust(right=0.78)
    plt.tight_layout(rect=[0, 0, 0.78, 1])
    out = _fig_to_base64(fig)
    plt.close(fig)
    return out


def _waterfall_chart(
    stage_labels: List[str],
    values: List[float],
    title: str,
) -> str:
    """Waterfall: first = current cost, then deltas (negative = savings), last = final cost."""
    if not stage_labels or not values or len(stage_labels) != len(values):
        fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
        plt.tight_layout()
        return _fig_to_base64(fig)

    fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
    n = len(values)
    x = range(n)
    heights, bottoms, colors_list = [], [], []
    cum = 0.0
    for i, v in enumerate(values):
        if i == 0:
            heights.append(v); bottoms.append(0); cum = v
            colors_list.append(COLORS["secondary"])
        elif i == n - 1:
            heights.append(v); bottoms.append(0)
            colors_list.append(COLORS["accent1"])
        else:
            heights.append(v); bottoms.append(cum); cum += v
            colors_list.append(COLORS["accent3"] if v < 0 else COLORS["primary"])

    ax.bar(x, heights, bottom=bottoms, color=colors_list, edgecolor="white", linewidth=0.5)
    ax.axhline(y=0, color="gray", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(stage_labels, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("Cost", fontsize=10)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_facecolor("white")

    legend_labels = ["Starting Cost", "Savings", "Additions", "Final Cost"]
    legend_colors = [COLORS["secondary"], COLORS["accent3"], COLORS["primary"], COLORS["accent1"]]
    handles = [mpatches.Patch(color=c, label=l) for c, l in zip(legend_colors, legend_labels)]
    ax.legend(handles=handles, **LEGEND_STYLE)
    fig.subplots_adjust(right=0.78)
    plt.tight_layout(rect=[0, 0, 0.78, 1])
    out = _fig_to_base64(fig)
    plt.close(fig)
    return out


# ─── Histogram chart ──────────────────────────────────────────────────────────

def _histogram_chart(
    bin_labels: List[str],
    counts: List[float],
    title: str,
    xlabel: str = "Cores",
    ylabel: str = "Devices",
) -> str:
    """Histogram-style bar chart (e.g. device count by CPU core bucket)."""
    if not bin_labels or not counts:
        fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center", fontsize=12, color=COLORS["text_muted"])
        plt.tight_layout()
        return _fig_to_base64(fig)

    fig, ax = plt.subplots(figsize=(FIG_W_NORMAL, FIG_H), facecolor="white")
    x = range(len(bin_labels))
    ax.bar(x, counts, color=COLORS["primary"], edgecolor="white", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(bin_labels, fontsize=9)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_facecolor("white")
    ax.legend(
        handles=[mpatches.Patch(color=COLORS["primary"], label=ylabel)],
        **LEGEND_STYLE,
    )
    fig.subplots_adjust(right=0.80)
    plt.tight_layout(rect=[0, 0, 0.80, 1])
    out = _fig_to_base64(fig)
    plt.close(fig)
    return out


# ─── Main entry point ─────────────────────────────────────────────────────────

def generate_all_charts(
    rule_results: Dict[str, Any],
    license_metrics: Dict[str, Any],
):
    """
    Build all dashboard charts with matplotlib. Returns (charts_dict, formats_dict).
    charts_dict: chart_id -> base64 string; formats_dict: chart_id -> 'gif' or 'png'.
    """
    charts = {}
    formats = {}
    azure = rule_results.get("azure_payg") or []
    retired = rule_results.get("retired_devices") or []
    by_product = license_metrics.get("by_product") or []
    azure_count = rule_results.get("azure_payg_count", 0)
    retired_count = rule_results.get("retired_count", 0)

    try:
        # --- Rule 1: CPU cores bar ---
        labels_cores = ["No data"]
        values_cores = [0]
        if azure and len(azure) > 0:
            r0 = azure[0]
            cores_key = _find_key(r0, ["cpu", "core", "u_cpu"])
            device_key = _find_key(r0, ["device_name", "device_ci", "device"])
            if cores_key or device_key:
                top = azure[:15]
                labels_cores = [str((r.get(device_key) if device_key else "Device") or "Device")[:12] for r in top]
                values_cores = [float(r.get(cores_key, 0) or 0) for r in top] if cores_key else [0] * len(top)
        fmt, b64 = _bar_chart_animated(
            labels_cores, values_cores, "CPU Core Distribution", COLORS["primary"],
            xlabel="Device", ylabel="CPU Cores",
        )
        charts["chart_azure_cores"] = b64
        formats["chart_azure_cores"] = fmt

        # --- Rule 1: Hosting zone pie ---
        zones = {}
        if azure and len(azure) > 0:
            zone_key = _find_key(azure[0], ["hosting", "zone", "u_hosting"])
            for r in azure:
                z = str((r.get(zone_key) if zone_key else None) or "Other")
                zones[z] = zones.get(z, 0) + 1
        if not zones:
            zones = {"No data": 1}
        fmt, b64 = _pie_chart_animated(
            list(zones.keys()), list(zones.values()), "Hosting Zone Breakdown", _zone_colors(list(zones.keys()))
        )
        charts["chart_azure_zones"] = b64
        formats["chart_azure_zones"] = fmt

        # --- Rule 2: Retired vs other pie ---
        fmt, b64 = _pie_chart_animated(
            ["Retired with installs", "Other"],
            [retired_count, max(1, 100 - retired_count)],
            "Status Comparison",
            [COLORS["accent3"], COLORS["other"]],
        )
        charts["chart_retired"] = b64
        formats["chart_retired"] = fmt

        # --- Rule 2: By environment bar (horizontal) ---
        env_counts = {}
        if retired and len(retired) > 0:
            env_key = _find_key(retired[0], ["environment", "env"])
            for r in retired:
                e = str((r.get(env_key) if env_key else None) or "N/A")
                env_counts[e] = env_counts.get(e, 0) + 1
        if not env_counts:
            env_counts = {"Retired": retired_count} if retired_count else {"No data": 0}
        env_labels = list(env_counts.keys())
        env_values = list(env_counts.values())
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
        fmt, b64 = _bar_chart_horizontal_animated(
            env_labels, env_values, "Risk By Environment",
            env_colors,
            xlabel="Count", ylabel="Environment",
        )
        charts["chart_retired_env"] = b64
        formats["chart_retired_env"] = fmt

        # --- Combined: Demand by product ---
        labels_bp = [str(p.get("product", ""))[:15] for p in by_product[:15]]
        qty_data = [float(p.get("quantity", 0) or 0) for p in by_product[:15]]
        if not labels_bp:
            labels_bp, qty_data = ["No data"], [0]
        fmt, b64 = _bar_chart_animated(
            labels_bp, qty_data, "Demand by Product Line", COLORS["primary"],
            xlabel="Product", ylabel="Quantity",
        )
        charts["chart_demand"] = b64
        formats["chart_demand"] = fmt

        # --- Combined: Cost by product ---
        cost_data = [float(p.get("cost", 0) or 0) for p in by_product[:15]]
        if not labels_bp or not cost_data:
            labels_bp, cost_data = ["No data"], [0]
        elif len(cost_data) != len(labels_bp):
            cost_data = cost_data[: len(labels_bp)] or [0]
        fmt, b64 = _bar_chart_animated(
            labels_bp, cost_data, "Cost Projection Matrix", COLORS["accent2"],
            xlabel="Product", ylabel="Cost",
        )
        charts["chart_cost"] = b64
        formats["chart_cost"] = fmt

        # --- Combined: Overview (Azure vs Retired) ---
        fmt, b64 = _doughnut_chart_animated(
            ["Azure PAYG", "Retired"],
            [azure_count, retired_count] if (azure_count or retired_count) else [0],
            "Optimization vs Risk",
            [COLORS["primary"], COLORS["accent3"]],
        )
        charts["chart_overview"] = b64
        formats["chart_overview"] = fmt

        # --- Combined: Device fleet state ---
        total_demand = license_metrics.get("total_demand_quantity") or 0
        fmt, b64 = _doughnut_chart_animated(
            ["Azure PAYG", "Retired Issues", "Standard"],
            [azure_count, retired_count, total_demand] if (azure_count or retired_count or total_demand) else [0],
            "Global Device Fleet State",
            [COLORS["primary"], COLORS["accent3"], COLORS["other"]],
        )
        charts["chart_devices"] = b64
        formats["chart_devices"] = fmt

        # --- License cost by product (donut) ---
        cost_labels = [str(p.get("product", ""))[:12] for p in by_product[:10]]
        cost_vals = [float(p.get("cost", 0) or 0) for p in by_product[:10]]
        if cost_labels and any(c > 0 for c in cost_vals):
            fmt, b64 = _doughnut_chart_animated(cost_labels, cost_vals, "License Cost by Product")
            charts["chart_license_cost_donut"] = b64
            formats["chart_license_cost_donut"] = fmt
        else:
            b64 = _doughnut_chart(["No data"], [1], "License Cost by Product")
            charts["chart_license_cost_donut"] = b64
            formats["chart_license_cost_donut"] = "png"

        # --- Azure: devices by hosting zone (grouped current vs estimated) ---
        payg_zone_breakdown = rule_results.get("payg_zone_breakdown") or {}
        zone_names = payg_zone_breakdown.get("labels") or ["Public Cloud", "Private Cloud AVS"]
        current_zone_counts = payg_zone_breakdown.get("current") or [
            zones.get("Public Cloud", 0),
            zones.get("Private Cloud AVS", 0),
        ]
        estimated_zone_counts = payg_zone_breakdown.get("estimated") or [
            zones.get("Public Cloud", 0),
            zones.get("Private Cloud AVS", 0),
        ]
        if zone_names and any(c > 0 for c in current_zone_counts + estimated_zone_counts):
            b64 = _grouped_bar_chart(
                zone_names,
                [
                    {"name": "Current", "values": current_zone_counts, "color": "#00BCFF"},
                    {"name": "Estimated", "values": estimated_zone_counts, "color": "#89D329"},
                ],
                "Azure PAYG Candidates by Hosting Zone",
                xlabel="Hosting Zone",
                ylabel="Devices",
            )
            charts["chart_azure_by_zone_bar"] = b64
            formats["chart_azure_by_zone_bar"] = "png"
        else:
            b64 = _grouped_bar_chart(
                ["Public Cloud", "Private Cloud AVS"],
                [
                    {"name": "Current", "values": [0, 0], "color": "#00BCFF"},
                    {"name": "Estimated", "values": [0, 0], "color": "#89D329"},
                ],
                "Azure PAYG Candidates by Hosting Zone",
                xlabel="Hosting Zone",
                ylabel="Devices",
            )
            charts["chart_azure_by_zone_bar"] = b64
            formats["chart_azure_by_zone_bar"] = "png"

        # --- BYOL vs PAYG cost comparison ---
        total_cost = float(license_metrics.get("total_license_cost") or 0)
        payg_share = (azure_count / total_demand) if total_demand and total_demand > 0 else 0
        byol_val = total_cost
        payg_val = total_cost * (1 - payg_share * 0.28) if payg_share else total_cost * 0.85
        b64 = _comparison_bar_chart(
            ["BYOL", "PAYG (est.)"], [byol_val, payg_val],
            "Cost: BYOL vs PAYG",
            [COLORS["secondary"], COLORS["accent1"]],
            ylabel="Cost",
        )
        charts["chart_byol_vs_payg"] = b64
        formats["chart_byol_vs_payg"] = "png"

        # --- Retired: services still running (horizontal bar) ---
        if retired_count > 0:
            b64 = _bar_chart_horizontal(
                ["SQL Server"], [retired_count],
                "Retired Devices Still Running Software",
                [COLORS["accent3"]], xlabel="Count", ylabel="Service",
            )
        else:
            b64 = _bar_chart_horizontal(
                ["No retired with software"], [0],
                "Retired Devices Still Running Software",
                [COLORS["text_muted"]],
            )
        charts["chart_retired_services"] = b64
        formats["chart_retired_services"] = "png"

        # --- CPU core distribution (histogram) ---
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
        if any(bin_counts):
            b64 = _histogram_chart(bin_labels, bin_counts, "Device Distribution by CPU Cores", xlabel="Cores", ylabel="Devices")
            charts["chart_cpu_histogram"] = b64
            formats["chart_cpu_histogram"] = "png"
        else:
            b64 = _histogram_chart(["No data"], [0], "Device Distribution by CPU Cores")
            charts["chart_cpu_histogram"] = b64
            formats["chart_cpu_histogram"] = "png"

        # --- Device environment distribution (pie) ---
        env_labels = list(zones.keys()) if zones else ["Azure", "On-Prem", "Private Cloud"]
        env_vals = list(zones.values()) if zones else [azure_count, max(0, total_demand - azure_count), 0]
        if not env_vals or all(v == 0 for v in env_vals):
            env_labels, env_vals = ["No data"], [1]
        fmt, b64 = _pie_chart_animated(env_labels, env_vals, "Device Environment Distribution", _zone_colors(env_labels))
        charts["chart_env_pie"] = b64
        formats["chart_env_pie"] = fmt

        # --- Top 10 most expensive (by product cost) ---
        sorted_product = sorted(by_product, key=lambda p: float(p.get("cost", 0) or 0), reverse=True)[:10]
        top_labels = [str(p.get("product", ""))[:14] for p in sorted_product]
        top_costs = [float(p.get("cost", 0) or 0) for p in sorted_product]
        if top_labels and any(c > 0 for c in top_costs):
            fmt, b64 = _bar_chart_animated(
                top_labels, top_costs, "Top 10 by License Cost", COLORS["accent2"],
                xlabel="Product", ylabel="Cost",
            )
            charts["chart_top10_cost"] = b64
            formats["chart_top10_cost"] = fmt
        else:
            b64 = _bar_chart(["No data"], [0], "Top 10 by License Cost", COLORS["accent2"])
            charts["chart_top10_cost"] = b64
            formats["chart_top10_cost"] = "png"

        # --- Waterfall: current → PAYG savings → retired savings → final ---
        payg_savings_est = total_cost * payg_share * 0.28 if payg_share else 0
        retired_savings_est = (retired_count / max(1, total_demand)) * total_cost * 0.05 if total_demand else 0
        final_cost = total_cost - payg_savings_est - retired_savings_est
        wf_labels = ["Current Cost", "PAYG Savings", "Retired Savings", "Final Cost"]
        wf_vals = [total_cost, -payg_savings_est, -retired_savings_est, final_cost]
        b64 = _waterfall_chart(wf_labels, wf_vals, "Cost Before vs After Optimization")
        charts["chart_waterfall"] = b64
        formats["chart_waterfall"] = "png"

    except Exception as e:
        logger.exception("Chart generation failed: %s", e)
        fig, ax = plt.subplots(figsize=(4, 3), facecolor="white")
        ax.text(0.5, 0.5, "Chart unavailable", ha="center", va="center", fontsize=12)
        placeholder_b64 = _fig_to_base64(fig)
        plt.close(fig)
        all_cids = [
            "chart_azure_cores", "chart_azure_zones", "chart_retired", "chart_retired_env",
            "chart_demand", "chart_cost", "chart_overview", "chart_devices",
            "chart_license_cost_donut", "chart_azure_by_zone_bar", "chart_byol_vs_payg",
            "chart_retired_services", "chart_cpu_histogram", "chart_env_pie",
            "chart_top10_cost", "chart_waterfall",
        ]
        for cid in all_cids:
            if cid not in charts:
                charts[cid] = placeholder_b64
                formats[cid] = "png"

    return (charts, formats)
