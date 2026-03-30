import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from optimizer.models import AnalysisSession
from optimizer.services.analysis_logs import build_analysis_summary_metrics, get_user_analysis_logs


def test_build_analysis_summary_metrics_extracts_major_points():
    summary = build_analysis_summary_metrics(
        {
            "total_devices_analyzed": 42,
            "rule_results": {
                "azure_payg_count": 10,
                "retired_count": 5,
            },
            "license_metrics": {
                "total_demand_quantity": 100,
                "total_license_cost": 1000,
            },
        }
    )

    assert summary["total_devices_analyzed"] == 42
    assert summary["total_demand_quantity"] == 100
    assert summary["total_license_cost"] == 1000.0
    assert summary["azure_payg_count"] == 10
    assert summary["retired_count"] == 5
    assert summary["azure_payg_savings"] == 28.0
    assert summary["retired_devices_savings"] == 2.5
    assert summary["total_savings"] == 30.5


@pytest.mark.django_db
def test_get_user_analysis_logs_returns_only_requested_user_logs():
    user_model = get_user_model()
    user = user_model.objects.create_user(username="log-user", password="secret123")
    other_user = user_model.objects.create_user(username="other-log-user", password="secret123")

    completed = AnalysisSession.objects.create(
        user=user,
        file_name="completed.xlsx",
        file_path="completed.xlsx",
        status="completed",
        completed_at=timezone.now(),
        summary_metrics={
            "total_devices_analyzed": 42,
            "total_demand_quantity": 100,
            "total_license_cost": 1000.0,
            "azure_payg_count": 10,
            "retired_count": 5,
            "total_savings": 30.5,
            "azure_payg_savings": 28.0,
            "retired_devices_savings": 2.5,
        },
    )
    AnalysisSession.objects.create(
        user=other_user,
        file_name="other.xlsx",
        file_path="other.xlsx",
        status="completed",
        completed_at=timezone.now(),
        summary_metrics={"total_devices_analyzed": 1},
    )

    logs = get_user_analysis_logs(user)

    assert len(logs) == 1
    assert logs[0]["analysis_id"] == completed.id
    assert logs[0]["username"] == "log-user"
    assert logs[0]["file_name"] == "completed.xlsx"
    assert logs[0]["status"] == "completed"
    assert logs[0]["summary_metrics"]["total_devices_analyzed"] == 42
    assert logs[0]["summary_metrics"]["total_savings"] == 30.5
    assert logs[0]["uploaded_at"] is not None
    assert logs[0]["completed_at"] is not None
