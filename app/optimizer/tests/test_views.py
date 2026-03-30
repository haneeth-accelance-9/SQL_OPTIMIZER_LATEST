"""View tests: health, ready, auth redirect."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from optimizer.models import AnalysisSession


@pytest.mark.django_db
def test_health_returns_200(client):
    response = client.get(reverse("optimizer:health"))
    assert response.status_code == 200
    assert b"ok" in response.content


@pytest.mark.django_db
def test_ready_returns_200_when_db_ok(client):
    response = client.get(reverse("optimizer:ready"))
    assert response.status_code == 200
    assert b"ready" in response.content


@pytest.mark.django_db
def test_home_redirects_to_login_when_anonymous(client):
    response = client.get(reverse("optimizer:home"))
    assert response.status_code == 302
    assert reverse("optimizer:login") in response.url


@pytest.mark.django_db
def test_results_uses_persisted_analysis_data(client):
    user = get_user_model().objects.create_user(username="analyst", password="secret123")
    analysis = AnalysisSession.objects.create(
        user=user,
        file_name="uploaded.xlsx",
        file_path="uploaded.xlsx",
        status="completed",
        result_data={
            "file_name": "customer-analysis.xlsx",
            "sheet_names_used": {"installations": "Installations"},
            "total_devices_analyzed": 42,
            "rule_results": {
                "azure_payg_count": 2,
                "azure_payg": [
                    {"device_name": "vm-01", "cpu_cores_overall_device": 8},
                    {"device_name": "vm-02", "cpu_cores_overall_device": 16},
                ],
                "retired_count": 1,
                "retired_devices": [
                    {"device_name": "old-sql-01", "inventory_status_standard": "Retired"},
                ],
            },
            "license_metrics": {
                "total_demand_quantity": 12,
                "total_license_cost": 345.6,
                "by_product": [],
                "price_distribution": [],
                "cost_reduction_tips": [],
            },
        },
    )

    client.force_login(user)
    session = client.session
    session["optimizer_analysis_id"] = analysis.id
    session.save()

    response = client.get(reverse("optimizer:results"), {"rule1_page": "bad-page", "rule2_page": "5"})

    assert response.status_code == 200
    assert response.context["analysis_id"] == analysis.id
    assert response.context["analysis_source_file_name"] == "customer-analysis.xlsx"
    assert response.context["analysis_sheet_names"] == {"installations": "Installations"}
    assert response.context["total_devices_analyzed"] == 42
    assert response.context["azure_payg_count"] == 2
    assert response.context["retired_count"] == 1
    assert response.context["total_demand_quantity"] == 12
    assert response.context["total_license_cost"] == 345.6
    assert response.context["rule1_page"] == 1
    assert response.context["rule2_page"] == 1
    assert response.context["rule1_keys"] == ["device_name", "cpu_cores_overall_device"]
    assert response.context["rule2_keys"] == ["device_name", "inventory_status_standard"]
    assert response.context["azure_payg_page"] == [["vm-01", 8], ["vm-02", 16]]
    assert response.context["retired_devices_page"] == [["old-sql-01", "Retired"]]
