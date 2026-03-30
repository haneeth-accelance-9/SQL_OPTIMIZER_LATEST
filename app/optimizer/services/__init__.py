from .excel_processor import ExcelProcessor
from .rule_engine import run_rules, compute_license_metrics
from .ai_report_generator import generate_report_text, get_fallback_report

try:
    from .chart_generator import generate_all_charts
except ImportError:
    generate_all_charts = None  # optional: pip install matplotlib for dashboard charts

__all__ = [
    "ExcelProcessor",
    "run_rules",
    "compute_license_metrics",
    "generate_report_text",
    "get_fallback_report",
    "generate_all_charts",
]
