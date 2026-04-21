"""Shared template context for header-level UI elements."""

from optimizer.services.alerts import build_alert_summary, get_dummy_alerts


def notification_context(request):
    """Expose dummy notification data for the shared navbar drawer."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            "header_alerts": [],
            "header_alert_summary": {"total": 0, "high": 0, "medium": 0, "low": 0},
            "header_alert_count": 0,
        }

    all_alerts = get_dummy_alerts()
    return {
        "header_alerts": all_alerts[:4],
        "header_alert_summary": build_alert_summary(all_alerts),
        "header_alert_count": len(all_alerts),
    }
