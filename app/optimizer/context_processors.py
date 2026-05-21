"""Shared template context for header-level UI elements."""

from optimizer.services.alerts import build_alert_summary, get_dummy_alerts


def notification_context(request):
    """Expose dummy notification data for the shared navbar drawer."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            "header_alerts": [],
            "header_alert_summary": {"total": 0, "high": 0, "medium": 0, "low": 0},
            "header_alert_count": 0,
            "is_viewer_only": False,
        }

    all_alerts = get_dummy_alerts()
    try:
        is_viewer_only = request.user.optimizer_profile.is_viewer_only
    except Exception:
        is_viewer_only = False

    try:
        is_admin = request.user.optimizer_profile.is_admin
    except Exception:
        is_admin = False

    return {
        "header_alerts": all_alerts[:4],
        "header_alert_summary": build_alert_summary(all_alerts),
        "header_alert_count": len(all_alerts),
        "is_viewer_only": is_viewer_only,
        "is_admin": is_admin,
    }
