from typing import Any, Dict, List, Union

from django.utils import timezone

from optimizer.models import AnalysisSession
from optimizer.services.analysis_service import build_dashboard_context


def build_analysis_summary_metrics(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a compact, log-friendly snapshot of the major analysis metrics."""
    safe_context = context if isinstance(context, dict) else {}
    dashboard = build_dashboard_context(safe_context)
    return {
        "total_devices_analyzed": int(safe_context.get("total_devices_analyzed", 0) or 0),
        "total_demand_quantity": int(dashboard.get("total_demand_quantity", 0) or 0),
        "total_license_cost": float(dashboard.get("total_license_cost", 0) or 0),
        "azure_payg_count": int(dashboard.get("azure_payg_count", 0) or 0),
        "retired_count": int(dashboard.get("retired_count", 0) or 0),
        "total_savings": float(dashboard.get("total_savings", 0) or 0),
        "azure_payg_savings": float(dashboard.get("azure_payg_savings", 0) or 0),
        "retired_devices_savings": float(dashboard.get("retired_devices_savings", 0) or 0),
    }


def serialize_analysis_log(analysis: AnalysisSession) -> Dict[str, Any]:
    """Return a JSON-friendly log payload for one persisted analysis run."""
    uploaded_at = timezone.localtime(analysis.created_at) if analysis.created_at else None
    completed_at = timezone.localtime(analysis.completed_at) if analysis.completed_at else None
    duration_seconds = None
    if analysis.created_at and analysis.completed_at:
        duration_seconds = round((analysis.completed_at - analysis.created_at).total_seconds(), 2)

    return {
        "analysis_id": analysis.id,
        "user_id": analysis.user_id,
        "username": getattr(analysis.user, "username", ""),
        "file_name": analysis.file_name,
        "status": analysis.status,
        "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "duration_seconds": duration_seconds,
        "error_message": analysis.error_message,
        "summary_metrics": analysis.summary_metrics if isinstance(analysis.summary_metrics, dict) else {},
    }


def get_user_analysis_logs(user: Union[int, Any]) -> List[Dict[str, Any]]:
    """Return all analysis logs for one user, newest first."""
    user_id = getattr(user, "id", user)
    queryset = (
        AnalysisSession.objects.filter(user_id=user_id)
        .select_related("user")
        .order_by("-created_at")
    )
    return [serialize_analysis_log(analysis) for analysis in queryset]
