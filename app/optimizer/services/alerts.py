"""Dummy alerts data and filtering helpers for the notification UI."""

from __future__ import annotations

from typing import Dict, List


def _alert(
    alert_id: str,
    title: str,
    message: str,
    severity: str,
    category: str,
    status: str,
    source: str,
    created_at: str,
) -> Dict[str, str]:
    return {
        "alert_id": alert_id,
        "title": title,
        "message": message,
        "severity": severity,
        "category": category,
        "status": status,
        "source": source,
        "created_at": created_at,
    }


def get_dummy_alerts() -> List[Dict[str, str]]:
    """Return a stable list of dummy alerts for the UI scaffolding."""
    alerts = [
        _alert(
            "ALT-1008",
            "Enterprise cost spike detected",
            "Estimated SQL licensing cost increased by 8.2% compared with the previous uploaded batch.",
            "High",
            "Cost",
            "Open",
            "Results Dashboard",
            "2026-04-19 10:18",
        ),
        _alert(
            "ALT-1007",
            "Retired devices still reporting",
            "13 retired devices are still showing active SQL software installations and require review.",
            "High",
            "Compliance",
            "Open",
            "Retired Devices Rule",
            "2026-04-19 09:42",
        ),
        _alert(
            "ALT-1006",
            "PAYG candidate cluster expanded",
            "Azure BYOL to PAYG candidate count increased after the latest optimization workbook run.",
            "Medium",
            "Optimization",
            "Investigating",
            "PAYG Recommendation",
            "2026-04-19 08:55",
        ),
        _alert(
            "ALT-1005",
            "CPU rightsizing export pending validation",
            "The rightsizing workbook download flow should be revalidated after the latest sheet mapping update.",
            "Medium",
            "Operations",
            "Open",
            "CPU Rightsizing",
            "2026-04-18 18:20",
        ),
        _alert(
            "ALT-1004",
            "Low developer license utilization",
            "Developer edition usage remains below expected targets in non-production environments.",
            "Low",
            "Optimization",
            "Open",
            "Dashboard Insights",
            "2026-04-18 16:40",
        ),
        _alert(
            "ALT-1003",
            "Report generation fallback used",
            "The executive summary used the fallback report content instead of AI-generated recommendations.",
            "Low",
            "AI Report",
            "Resolved",
            "Executive Report",
            "2026-04-18 14:12",
        ),
        _alert(
            "ALT-1002",
            "Private cloud demand anomaly",
            "A notable shift in private cloud demand was detected across the latest analyzed file.",
            "High",
            "Demand",
            "Investigating",
            "Dashboard Charting",
            "2026-04-18 12:05",
        ),
        _alert(
            "ALT-1001",
            "Workbook upload completed",
            "The most recent workbook finished processing and the dashboard is ready for review.",
            "Low",
            "System",
            "Resolved",
            "Upload Pipeline",
            "2026-04-18 11:41",
        ),
    ]
    return alerts


def _normalize_filter(value: str) -> str:
    return (value or "").strip().lower()


def filter_alerts(alerts: List[Dict[str, str]], *, severity: str = "", category: str = "", status: str = "", query: str = "") -> List[Dict[str, str]]:
    """Filter alerts using simple case-insensitive matching."""
    severity_filter = _normalize_filter(severity)
    category_filter = _normalize_filter(category)
    status_filter = _normalize_filter(status)
    query_filter = _normalize_filter(query)

    filtered: List[Dict[str, str]] = []
    for alert in alerts:
        if severity_filter and _normalize_filter(alert["severity"]) != severity_filter:
            continue
        if category_filter and _normalize_filter(alert["category"]) != category_filter:
            continue
        if status_filter and _normalize_filter(alert["status"]) != status_filter:
            continue
        if query_filter:
            haystack = " ".join(
                [
                    alert["alert_id"],
                    alert["title"],
                    alert["message"],
                    alert["source"],
                    alert["category"],
                ]
            ).lower()
            if query_filter not in haystack:
                continue
        filtered.append(alert)
    return filtered


def build_alert_summary(alerts: List[Dict[str, str]]) -> Dict[str, int]:
    """Return top-level counts used in the drawer summary."""
    return {
        "total": len(alerts),
        "high": sum(1 for item in alerts if item["severity"] == "High"),
        "medium": sum(1 for item in alerts if item["severity"] == "Medium"),
        "low": sum(1 for item in alerts if item["severity"] == "Low"),
    }


def build_alert_page_context(query_params) -> Dict[str, object]:
    """Build filtered alert data for the detailed alerts page."""
    all_alerts = get_dummy_alerts()
    selected_severity = (query_params.get("severity") or "").strip()
    selected_category = (query_params.get("category") or "").strip()
    selected_status = (query_params.get("status") or "").strip()
    search_query = (query_params.get("q") or "").strip()
    filtered_alerts = filter_alerts(
        all_alerts,
        severity=selected_severity,
        category=selected_category,
        status=selected_status,
        query=search_query,
    )
    categories = sorted({item["category"] for item in all_alerts})
    severities = ["High", "Medium", "Low"]
    statuses = ["Open", "Investigating", "Resolved"]
    return {
        "title": "Alerts",
        "alerts": filtered_alerts,
        "alert_summary": build_alert_summary(all_alerts),
        "alert_total_count": len(all_alerts),
        "selected_severity": selected_severity,
        "selected_category": selected_category,
        "selected_status": selected_status,
        "search_query": search_query,
        "alert_filter_options": {
            "severities": severities,
            "categories": categories,
            "statuses": statuses,
        },
    }
