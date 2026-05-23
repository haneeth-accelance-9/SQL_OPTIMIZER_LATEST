"""
Additional view tests covering: signup, logout, home, dashboard, profile, alerts,
analysis_logs, JWT auth API, savings-summary API, rule1/rule2 data APIs,
download_rule_data, api_strategy3_rightsizing error paths, and view helpers.
"""
import json
import time

import jwt as pyjwt
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from optimizer.views import (
    _build_profile_initials,
    _eu_currency,
    _make_json_serializable,
)

User = get_user_model()

# ── Minimal fake context returned by compute_live_db_metrics ─────────────────

FAKE_METRICS = {
    "total_devices_analyzed": 10,
    "rule_results": {
        "azure_payg_count": 2,
        "azure_payg": [
            {"device_name": "vm-01", "cpu_cores_overall_device": 8},
        ],
        "retired_count": 1,
        "retired_devices": [
            {"device_name": "old-01", "inventory_status_standard": "Retired"},
        ],
        "retired_devices_savings_eur": 100.0,
    },
    "rule_wise_savings": {
        "azure_payg": 500.0,
        "retired_devices": 100.0,
        "rightsizing": 200.0,
    },
    "license_metrics": {
        "total_demand_quantity": 5,
        "total_license_cost": 10000.0,
        "by_product": [],
        "price_distribution": [],
        "cost_reduction_tips": [],
    },
    "rightsizing": {
        "cpu_optimizations": [],
        "ram_optimizations": [],
        "screen_summaries": {},
        "cpu_chart_data": [],
        "ram_chart_data": [],
        "cpu_count": 0,
        "cpu_prod_count": 0,
        "cpu_nonprod_count": 0,
        "ram_count": 0,
        "ram_prod_count": 0,
        "ram_nonprod_count": 0,
        "total_vcpu_reduction": 0,
        "total_ram_reduction_gib": 0.0,
        "error": None,
        "default_filter_by_workload": {"CPU": "PROD_CPU_Rightsizing", "RAM": "PROD_RAM_Rightsizing"},
        "screen_filter_options": {
            "CPU": ["PROD_CPU_Rightsizing", "NONPROD_CPU_Rightsizing"],
            "RAM": ["PROD_RAM_Rightsizing", "NONPROD_RAM_Rightsizing"],
        },
    },
    "rightsizing_meta": {},
    "data_refreshed_at": None,
}


def _patch_metrics(monkeypatch, ctx=None):
    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.compute_live_db_metrics",
        lambda: ctx or FAKE_METRICS,
    )


# ── Pure helper function tests ─────────────────────────────────────────────────

class TestEuCurrency:
    def test_formats_number(self):
        result = _eu_currency(1234567.89)
        assert "1.234.567,89" in result and "€" in result

    def test_small_number(self):
        result = _eu_currency(345.6)
        assert "345,60" in result and "€" in result

    def test_zero(self):
        result = _eu_currency(0)
        assert "0,00" in result and "€" in result

    def test_non_numeric_passthrough(self):
        result = _eu_currency("N/A")
        assert result == "N/A"


class TestMakeJsonSerializable:
    def test_dict(self):
        assert _make_json_serializable({"a": 1}) == {"a": 1}

    def test_list(self):
        assert _make_json_serializable([1, 2, 3]) == [1, 2, 3]

    def test_none(self):
        assert _make_json_serializable(None) is None

    def test_string(self):
        assert _make_json_serializable("hello") == "hello"

    def test_nested(self):
        result = _make_json_serializable({"key": [1, None, "x"]})
        assert result == {"key": [1, None, "x"]}

    def test_pandas_na_becomes_none(self):
        import pandas as pd
        assert _make_json_serializable(pd.NA) is None

    def test_unknown_type_stringified(self):
        class Custom:
            def __str__(self):
                return "custom-val"
        assert _make_json_serializable(Custom()) == "custom-val"


class TestBuildProfileInitials:
    def test_first_and_last_name(self):
        user = User(first_name="Alice", last_name="Brown")
        assert _build_profile_initials(user) == "AB"

    def test_only_username(self):
        user = User(username="john_doe", first_name="", last_name="")
        assert _build_profile_initials(user) == "JD"

    def test_single_word_username(self):
        user = User(username="alice", first_name="", last_name="")
        assert _build_profile_initials(user) == "A"

    def test_empty_everything(self):
        user = User(username="", first_name="", last_name="")
        assert _build_profile_initials(user) == "U"


# ── signup_view ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_signup_get_redirects_to_login_tab(client):
    response = client.get(reverse("optimizer:signup"))
    assert response.status_code == 302
    assert "tab=signup" in response.url


@pytest.mark.django_db
def test_signup_get_when_authenticated_redirects_to_dashboard(client):
    user = User.objects.create_user(username="already_in", password="pass1234!")
    client.force_login(user)
    response = client.get(reverse("optimizer:signup"))
    assert response.status_code == 302
    assert "dashboard" in response.url


@pytest.mark.django_db
def test_signup_post_valid_creates_user_and_redirects(client):
    data = {
        "username": "newuser_signup",
        "password1": "StrongPass123!",
        "password2": "StrongPass123!",
        "email": "newuser@example.com",
    }
    response = client.post(reverse("optimizer:signup"), data)
    assert response.status_code == 302
    assert "registered=1" in response.url
    assert User.objects.filter(username="newuser_signup").exists()


@pytest.mark.django_db
def test_signup_post_invalid_rerenders_with_form(client):
    data = {
        "username": "x",
        "password1": "abc",
        "password2": "different",
    }
    response = client.post(reverse("optimizer:signup"), data)
    assert response.status_code == 200


# ── logout_view ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_logout_redirects_to_login(client):
    user = User.objects.create_user(username="logout_user", password="pass1234!")
    client.force_login(user)
    response = client.get(reverse("optimizer:logout"))
    assert response.status_code == 302
    assert reverse("optimizer:login") in response.url


@pytest.mark.django_db
def test_logout_works_for_anonymous(client):
    response = client.get(reverse("optimizer:logout"))
    assert response.status_code == 302


# ── home view ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_home_returns_200_for_authenticated_user(client):
    from optimizer.models import UserProfile
    user = User.objects.create_user(username="homeuser", password="pass1234!")
    UserProfile.objects.update_or_create(user=user, defaults={"role": "editor"})
    client.force_login(user)
    response = client.get(reverse("optimizer:home"))
    assert response.status_code == 200


# ── dashboard view ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_dashboard_returns_200(client, monkeypatch):
    user = User.objects.create_user(username="dash_user", password="pass1234!")
    client.force_login(user)
    _patch_metrics(monkeypatch)
    monkeypatch.setattr(
        "optimizer.services.db_analysis_service.get_latest_agentic_context",
        lambda: {"has_agentic_data": False},
    )
    response = client.get(reverse("optimizer:dashboard"))
    assert response.status_code == 200


# ── analysis_logs ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_analysis_logs_returns_json(client):
    user = User.objects.create_user(username="log_user", password="pass1234!")
    client.force_login(user)
    response = client.get(reverse("optimizer:analysis_logs"))
    assert response.status_code == 200
    body = json.loads(response.content)
    assert "logs" in body


# ── alerts view ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_alerts_returns_200(client, monkeypatch):
    user = User.objects.create_user(username="alerts_user", password="pass1234!")
    client.force_login(user)
    monkeypatch.setattr(
        "optimizer.services.alerts.build_alert_page_context",
        lambda qs: {"alerts": [], "total": 0},
    )
    response = client.get(reverse("optimizer:alerts"))
    assert response.status_code == 200


# ── profile_page ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_profile_page_get_returns_200(client):
    user = User.objects.create_user(username="prof_user", password="pass1234!")
    client.force_login(user)
    response = client.get(reverse("optimizer:profile"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_profile_page_post_valid_redirects(client):
    user = User.objects.create_user(username="prof_post_user", password="pass1234!")
    client.force_login(user)
    response = client.post(
        reverse("optimizer:profile"),
        {"team_name": "Engineering", "image_url": ""},
    )
    assert response.status_code in (200, 302)


# ── JWT api_auth_token ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_api_auth_token_valid_credentials_returns_tokens(client):
    User.objects.create_user(username="jwt_user", password="JwtPass123!")
    response = client.post(
        reverse("optimizer:api_auth_token"),
        data={"grant_type": "password", "username": "jwt_user", "password": "JwtPass123!"},
    )
    assert response.status_code == 200
    body = json.loads(response.content)
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "Bearer"


@pytest.mark.django_db
def test_api_auth_token_json_body(client):
    User.objects.create_user(username="jwt_json_user", password="JwtPass123!")
    response = client.post(
        reverse("optimizer:api_auth_token"),
        data=json.dumps({"grant_type": "password", "username": "jwt_json_user", "password": "JwtPass123!"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = json.loads(response.content)
    assert "access_token" in body


@pytest.mark.django_db
def test_api_auth_token_invalid_credentials_returns_401(client):
    response = client.post(
        reverse("optimizer:api_auth_token"),
        data={"grant_type": "password", "username": "ghost", "password": "wrong"},
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_api_auth_token_missing_username_returns_400(client):
    response = client.post(
        reverse("optimizer:api_auth_token"),
        data={"grant_type": "password", "password": "JwtPass123!"},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_auth_token_wrong_grant_type_returns_400(client):
    response = client.post(
        reverse("optimizer:api_auth_token"),
        data={"grant_type": "client_credentials", "username": "u", "password": "p"},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_auth_token_invalid_json_returns_400(client):
    response = client.post(
        reverse("optimizer:api_auth_token"),
        data=b"not-json{{",
        content_type="application/json",
    )
    assert response.status_code == 400


# ── JWT api_auth_token_refresh ────────────────────────────────────────────────

def _make_refresh_token(user_id, expired=False):
    now = int(time.time())
    exp = now - 10 if expired else now + 3600
    payload = {"type": "refresh", "user_id": user_id, "iat": now, "exp": exp}
    return pyjwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _make_access_token_raw(user_id):
    now = int(time.time())
    payload = {"type": "access", "user_id": user_id, "iat": now, "exp": now + 3600}
    return pyjwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.mark.django_db
def test_api_auth_token_refresh_valid_returns_new_access(client):
    user = User.objects.create_user(username="refresh_user", password="pass!")
    token = _make_refresh_token(user.pk)
    response = client.post(
        reverse("optimizer:api_auth_token_refresh"),
        data=json.dumps({"refresh_token": token}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = json.loads(response.content)
    assert "access_token" in body


@pytest.mark.django_db
def test_api_auth_token_refresh_invalid_json_returns_400(client):
    response = client.post(
        reverse("optimizer:api_auth_token_refresh"),
        data=b"bad-json",
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_auth_token_refresh_missing_token_returns_400(client):
    response = client.post(
        reverse("optimizer:api_auth_token_refresh"),
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_auth_token_refresh_expired_returns_401(client):
    user = User.objects.create_user(username="exp_ref_user", password="pass!")
    token = _make_refresh_token(user.pk, expired=True)
    response = client.post(
        reverse("optimizer:api_auth_token_refresh"),
        data=json.dumps({"refresh_token": token}),
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_api_auth_token_refresh_wrong_type_returns_400(client):
    user = User.objects.create_user(username="wrong_type_user", password="pass!")
    access_token = _make_access_token_raw(user.pk)
    response = client.post(
        reverse("optimizer:api_auth_token_refresh"),
        data=json.dumps({"refresh_token": access_token}),
        content_type="application/json",
    )
    assert response.status_code == 400


# ── JWT api_auth_token_verify ─────────────────────────────────────────────────

@pytest.mark.django_db
def test_api_auth_token_verify_valid_returns_valid_true(client):
    user = User.objects.create_user(username="verify_user", password="pass!")
    token = _make_access_token_raw(user.pk)
    response = client.post(
        reverse("optimizer:api_auth_token_verify"),
        data=json.dumps({"token": token}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["valid"] is True


@pytest.mark.django_db
def test_api_auth_token_verify_invalid_json_returns_400(client):
    response = client.post(
        reverse("optimizer:api_auth_token_verify"),
        data=b"bad",
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_auth_token_verify_missing_token_returns_400(client):
    response = client.post(
        reverse("optimizer:api_auth_token_verify"),
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_auth_token_verify_expired_returns_valid_false(client):
    now = int(time.time())
    payload = {"type": "access", "user_id": 999, "iat": now, "exp": now - 10}
    token = pyjwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    response = client.post(
        reverse("optimizer:api_auth_token_verify"),
        data=json.dumps({"token": token}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["valid"] is False


@pytest.mark.django_db
def test_api_auth_token_verify_refresh_token_returns_valid_false(client):
    user = User.objects.create_user(username="verify_ref_user", password="pass!")
    token = _make_refresh_token(user.pk)
    response = client.post(
        reverse("optimizer:api_auth_token_verify"),
        data=json.dumps({"token": token}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["valid"] is False


# ── api_savings_summary ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_api_savings_summary_returns_three_strategies(client, monkeypatch):
    user = User.objects.create_user(username="savings_user", password="pass1234!")
    client.force_login(user)
    _patch_metrics(monkeypatch)
    response = client.get(reverse("optimizer:api_savings_summary"))
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["status"] == "completed"
    assert len(body["result"]["strategies"]) == 3
    ids = [s["id"] for s in body["result"]["strategies"]]
    assert "byol_to_payg" in ids
    assert "retired_but_reporting" in ids
    assert "rightsizing" in ids


@pytest.mark.django_db
def test_api_savings_summary_total_savings_correct(client, monkeypatch):
    user = User.objects.create_user(username="savings_sum_user", password="pass1234!")
    client.force_login(user)
    _patch_metrics(monkeypatch)
    response = client.get(reverse("optimizer:api_savings_summary"))
    body = json.loads(response.content)
    total = body["result"]["total_savings_eur"]
    assert total == pytest.approx(500.0 + 100.0 + 200.0)


@pytest.mark.django_db
def test_api_savings_summary_requires_login(client):
    response = client.get(reverse("optimizer:api_savings_summary"))
    assert response.status_code == 302


# ── api_rule1_data ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_api_rule1_data_returns_paginated_json(client, monkeypatch):
    user = User.objects.create_user(username="rule1_user", password="pass1234!")
    client.force_login(user)
    _patch_metrics(monkeypatch)
    response = client.get(reverse("optimizer:api_rule1_data"))
    assert response.status_code == 200
    body = json.loads(response.content)
    assert "rows" in body
    assert "total" in body
    assert body["total"] == 1


@pytest.mark.django_db
def test_api_rule1_data_sort_order_invalid_defaults_to_asc(client, monkeypatch):
    user = User.objects.create_user(username="rule1_sort_user", password="pass1234!")
    client.force_login(user)
    _patch_metrics(monkeypatch)
    response = client.get(reverse("optimizer:api_rule1_data") + "?sort_order=sideways")
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["sort_order"] == "asc"


@pytest.mark.django_db
def test_api_rule1_data_requires_login(client):
    response = client.get(reverse("optimizer:api_rule1_data"))
    assert response.status_code == 302


# ── api_rule2_data ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_api_rule2_data_returns_paginated_json(client, monkeypatch):
    user = User.objects.create_user(username="rule2_user", password="pass1234!")
    client.force_login(user)
    _patch_metrics(monkeypatch)
    response = client.get(reverse("optimizer:api_rule2_data"))
    assert response.status_code == 200
    body = json.loads(response.content)
    assert "rows" in body
    assert body["total"] == 1


@pytest.mark.django_db
def test_api_rule2_data_pagination(client, monkeypatch):
    user = User.objects.create_user(username="rule2_page_user", password="pass1234!")
    client.force_login(user)
    _patch_metrics(monkeypatch)
    response = client.get(reverse("optimizer:api_rule2_data") + "?page=1&page_size=10")
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["page"] == 1
    assert body["page_size"] == 10


# ── api_strategy3_rightsizing error paths ─────────────────────────────────────

@pytest.mark.django_db
def test_api_strategy3_invalid_workload_returns_400(client, monkeypatch):
    user = User.objects.create_user(username="rs3_err_user", password="pass1234!")
    client.force_login(user)
    _patch_metrics(monkeypatch)
    response = client.get(
        reverse("optimizer:api_strategy3_rightsizing") + "?workload=INVALID"
    )
    assert response.status_code == 400
    body = json.loads(response.content)
    assert "error" in body["error"].lower() or "invalid" in body["error"].lower()


@pytest.mark.django_db
def test_api_strategy3_requires_login(client):
    response = client.get(reverse("optimizer:api_strategy3_rightsizing"))
    assert response.status_code == 302


# ── download_rule_data ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_download_rule_data_invalid_rule_id_returns_400(client):
    user = User.objects.create_user(username="download_err_user", password="pass1234!")
    client.force_login(user)
    response = client.get(reverse("optimizer:download_rule_data", kwargs={"rule_id": "rule99"}))
    assert response.status_code == 400


@pytest.mark.django_db
def test_download_rule_data_no_data_returns_404(client, monkeypatch):
    user = User.objects.create_user(username="download_empty_user", password="pass1234!")
    client.force_login(user)
    empty_ctx = dict(FAKE_METRICS)
    empty_ctx["rule_results"] = {"azure_payg": [], "retired_devices": [], "azure_payg_count": 0, "retired_count": 0}
    _patch_metrics(monkeypatch, ctx=empty_ctx)
    response = client.get(reverse("optimizer:download_rule_data", kwargs={"rule_id": "rule1"}))
    assert response.status_code == 404


# ── ready endpoint degraded path ──────────────────────────────────────────────

@pytest.mark.django_db
def test_ready_returns_503_when_db_fails(client, monkeypatch):
    from django.db import connection as _conn
    monkeypatch.setattr(_conn, "ensure_connection", lambda: (_ for _ in ()).throw(Exception("down")))
    response = client.get(reverse("optimizer:ready"))
    assert response.status_code == 503


# ── upload_view processing paths ──────────────────────────────────────────────

@pytest.mark.django_db
def test_upload_validated_file_but_processor_error_shows_error(client, monkeypatch):
    user = User.objects.create_user(username="upload_proc_err", password="pass1234!")
    client.force_login(user)

    from optimizer.services.upload_validator import ValidationResult
    monkeypatch.setattr(
        "optimizer.services.upload_validator.validate_upload",
        lambda f: ValidationResult(valid=True, error=None),
    )
    monkeypatch.setattr(
        "optimizer.services.cpu_utilisation_processor.process_cpu_utilisation",
        lambda f, uploaded_by=None: (_ for _ in ()).throw(RuntimeError("db error")),
    )

    import io, openpyxl
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    from django.core.files.uploadedfile import SimpleUploadedFile
    f = SimpleUploadedFile("test.xlsx", buf.read(),
                           content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response = client.post(reverse("optimizer:upload"), {"excel_file": f})
    assert response.status_code == 200
    assert b"error" in response.content.lower()


@pytest.mark.django_db
def test_upload_validation_exception_shows_error(client, monkeypatch):
    user = User.objects.create_user(username="upload_val_exc", password="pass1234!")
    client.force_login(user)

    monkeypatch.setattr(
        "optimizer.services.upload_validator.validate_upload",
        lambda f: (_ for _ in ()).throw(RuntimeError("validation crash")),
    )

    import io, openpyxl
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    from django.core.files.uploadedfile import SimpleUploadedFile
    f = SimpleUploadedFile("test.xlsx", buf.read(),
                           content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response = client.post(reverse("optimizer:upload"), {"excel_file": f})
    assert response.status_code == 200
    assert b"error" in response.content.lower()
