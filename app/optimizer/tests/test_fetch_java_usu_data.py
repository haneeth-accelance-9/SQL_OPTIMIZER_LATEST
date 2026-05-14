"""
Tests for optimizer/management/commands/fetch_java_usu_data.py

Covers:
  - _str(), _bool(), _decimal(), _int(), _date(), _beat_ids() helpers
    (identical implementations to fetch_usu_data, tested from this module's namespace)
  - Command.handle() with --dry-run, --skip-demand, --skip-install flags
    (HTTP mocked; DB writes exercised via @pytest.mark.django_db)
"""
import io
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from optimizer.management.commands.fetch_java_usu_data import (
    _bool,
    _date,
    _decimal,
    _int,
    _str,
    _beat_ids,
)


# ---------------------------------------------------------------------------
# _str
# ---------------------------------------------------------------------------

class TestStr:
    def test_none_returns_none(self):
        assert _str(None) is None

    def test_blank_returns_none(self):
        assert _str("") is None

    def test_whitespace_only_returns_none(self):
        assert _str("   ") is None

    def test_normal_string(self):
        assert _str("hello") == "hello"

    def test_strips_whitespace(self):
        assert _str("  hello  ") == "hello"

    def test_truncation(self):
        assert _str("abcdefgh", max_len=3) == "abc"

    def test_no_truncation_without_max_len(self):
        s = "x" * 500
        assert _str(s) == s

    def test_non_string_coerced(self):
        assert _str(7) == "7"

    def test_zero_becomes_string(self):
        assert _str(0) == "0"


# ---------------------------------------------------------------------------
# _bool
# ---------------------------------------------------------------------------

class TestBool:
    def test_none_returns_none(self):
        assert _bool(None) is None

    def test_bool_true_passthrough(self):
        assert _bool(True) is True

    def test_bool_false_passthrough(self):
        assert _bool(False) is False

    def test_string_1(self):
        assert _bool("1") is True

    def test_string_0(self):
        assert _bool("0") is False

    def test_string_true(self):
        assert _bool("true") is True

    def test_string_false(self):
        assert _bool("false") is False

    def test_string_yes(self):
        assert _bool("yes") is True

    def test_string_no(self):
        assert _bool("no") is False

    def test_unknown_value(self):
        assert _bool("unknown") is None

    def test_mixed_case_true(self):
        assert _bool("TRUE") is True

    def test_whitespace_stripped(self):
        assert _bool("  0  ") is False


# ---------------------------------------------------------------------------
# _decimal
# ---------------------------------------------------------------------------

class TestDecimal:
    def test_none_returns_none(self):
        assert _decimal(None) is None

    def test_valid_float_string(self):
        assert _decimal("1.5") == Decimal("1.5")

    def test_integer_string(self):
        assert _decimal("10") == Decimal("10")

    def test_invalid_string_returns_none(self):
        assert _decimal("abc") is None

    def test_decimal_passthrough(self):
        d = Decimal("3.14")
        assert _decimal(d) == d

    def test_strips_spaces(self):
        assert _decimal("  2.0  ") == Decimal("2.0")

    def test_negative(self):
        assert _decimal("-5.5") == Decimal("-5.5")


# ---------------------------------------------------------------------------
# _int
# ---------------------------------------------------------------------------

class TestInt:
    def test_none_returns_none(self):
        assert _int(None) is None

    def test_valid_string(self):
        assert _int("8") == 8

    def test_float_string_truncated(self):
        assert _int("8.9") == 8

    def test_invalid_string_returns_none(self):
        assert _int("xyz") is None


# ---------------------------------------------------------------------------
# _date
# ---------------------------------------------------------------------------

class TestDate:
    def test_none_returns_none(self):
        assert _date(None) is None

    def test_empty_returns_none(self):
        assert _date("") is None

    def test_iso_date(self):
        from datetime import date
        assert _date("2026-01-15") == date(2026, 1, 15)

    def test_datetime_string(self):
        from datetime import date
        assert _date("2026-01-15 10:00:00") == date(2026, 1, 15)

    def test_invalid_returns_none(self):
        assert _date("not-a-date") is None


# ---------------------------------------------------------------------------
# _beat_ids
# ---------------------------------------------------------------------------

class TestBeatIds:
    def test_none_returns_empty(self):
        assert _beat_ids(None) == []

    def test_empty_string_returns_empty(self):
        assert _beat_ids("") == []

    def test_single_id(self):
        assert _beat_ids("BEAT001") == ["BEAT001"]

    def test_multiple_ids_newline_separated(self):
        assert _beat_ids("BEAT001\nBEAT002") == ["BEAT001", "BEAT002"]

    def test_strips_each_id(self):
        assert _beat_ids("  B1  \n  B2  ") == ["B1", "B2"]

    def test_blank_lines_ignored(self):
        assert _beat_ids("B1\n\nB2\n") == ["B1", "B2"]


# ---------------------------------------------------------------------------
# Command.handle() — mocked HTTP
# ---------------------------------------------------------------------------

def _make_response(rows):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "data": rows,
        "metadata": {"pagination": {"next_page_uri": None}},
    }
    return resp


_JAVA_INSTALL_ROW = {
    "devices_device_key": "JDEV001",
    "devices_device_name": "JAVA-SERVER01",
    "device_man_systems_name": "AVS",
    "device_statuses_name": "Active",
    "device_types_name": "Physical",
    "dt_is_cloud_device_type": "0",
    "pdt_cloud_provider_type": None,
    "loc_countries_name": "Germany",
    "loc_regions_name": "EU",
    "locations_name": "Munich",
    "topology_type": "Standalone",
    "cdev_device_key": None,
    "beatid": "BEAT_JAVA_001",
    "device_purposes_name": "Production",
    "manufacturers_name": "Oracle",
    "product_families_description": "Java",
    "products_description": "Java SE 17",
    "products_edition": "Standard",
    "license_metrics_description": "Processor",
    "calc_license_metrics_me": "Named User Plus",
    "inv_statuses_name": "Installed",
    "inv_statuses_std_name": "Active",
    "ignore_usage_flag": "0",
    "ignore_usage_reason": None,
    "no_license_required_flag": "0",
    "devices_cpu_socket_count": "1",
    "devices_cpu_core_count": "4",
    "devices_hyper_threading_factor": "1",
    "source_key": "JSRC001",
    "devices_inventory_date": "2025-06-01",
    "creation_date": "2025-06-01 08:00:00",
}

_JAVA_DEMAND_ROW = {
    "devices_device_key": "JDEV002",
    "devices_device_name": "JAVA-SERVER02",
    "device_man_systems_name": "Private Cloud",
    "device_purposes_name": "Development",
    "device_types_name": "Virtual",
    "device_types_virt_type": "VMware",
    "dt_is_cloud_device_type": "0",
    "pdt_cloud_provider_type": None,
    "topology_type": "Cluster",
    "cdev_device_key": None,
    "center_dev_dev_name": "JAVA-CLUSTER",
    "man_name": "Oracle",
    "pf_description": "Java",
    "products_description": "Java SE 11",
    "products_edition": "SE",
    "imec_eff_quantity": "4.0",
    "calc_no_license_required_flag": "0",
    "devices_cpu_core_count": "8",
    "virt_type": "VMware",
    "is_cloud_device": "0",
    "cloud_provider": None,
    "devices_cpu_thread_count": "16",
    "devices_hyper_threading_factor": "2",
}


@pytest.mark.django_db
class TestCommandHandleDryRun:
    def test_dry_run_shows_message(self):
        install_resp = _make_response([_JAVA_INSTALL_ROW])
        demand_resp = _make_response([_JAVA_DEMAND_ROW])
        responses = [install_resp, demand_resp]
        call_count = [0]

        def fake_get(*args, **kwargs):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            return responses[idx]

        with patch("requests.Session.get", side_effect=fake_get):
            out = io.StringIO()
            call_command(
                "fetch_java_usu_data",
                "--dry-run",
                "--tenant=test_java_dry",
                stdout=out,
            )
        output = out.getvalue()
        assert "dry" in output.lower() or "DRY" in output

    def test_dry_run_skips_db_write(self):
        from optimizer.models import USUInstallation
        install_resp = _make_response([_JAVA_INSTALL_ROW])
        demand_resp = _make_response([_JAVA_DEMAND_ROW])
        responses = [install_resp, demand_resp]
        call_count = [0]

        def fake_get(*args, **kwargs):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            return responses[idx]

        before = USUInstallation.objects.count()
        with patch("requests.Session.get", side_effect=fake_get):
            call_command(
                "fetch_java_usu_data",
                "--dry-run",
                "--tenant=test_java_dry_no_write",
                stdout=io.StringIO(),
            )
        assert USUInstallation.objects.count() == before


@pytest.mark.django_db
class TestCommandHandleSkipDemand:
    def test_skip_demand_does_not_hit_demand_endpoint(self):
        install_resp = _make_response([_JAVA_INSTALL_ROW])
        with patch("requests.Session.get", return_value=install_resp) as mock_get:
            call_command(
                "fetch_java_usu_data",
                "--skip-demand",
                "--tenant=test_java_skip_demand",
                stdout=io.StringIO(),
            )
        for call_args in mock_get.call_args_list:
            url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
            assert "demanddetails" not in str(url)

    def test_skip_demand_outputs_skipping_message(self):
        install_resp = _make_response([_JAVA_INSTALL_ROW])
        with patch("requests.Session.get", return_value=install_resp):
            out = io.StringIO()
            call_command(
                "fetch_java_usu_data",
                "--skip-demand",
                "--tenant=test_java_skip_demand2",
                stdout=out,
            )
        output = out.getvalue()
        assert "skip" in output.lower() or "demand" in output.lower()


@pytest.mark.django_db
class TestCommandHandleSkipInstall:
    def test_skip_install_does_not_hit_install_endpoint(self):
        demand_resp = _make_response([_JAVA_DEMAND_ROW])
        with patch("requests.Session.get", return_value=demand_resp) as mock_get:
            call_command(
                "fetch_java_usu_data",
                "--skip-install",
                "--tenant=test_java_skip_install",
                stdout=io.StringIO(),
            )
        for call_args in mock_get.call_args_list:
            url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
            assert "installations" not in str(url)

    def test_skip_install_outputs_skipping_message(self):
        demand_resp = _make_response([_JAVA_DEMAND_ROW])
        with patch("requests.Session.get", return_value=demand_resp):
            out = io.StringIO()
            call_command(
                "fetch_java_usu_data",
                "--skip-install",
                "--tenant=test_java_skip_install2",
                stdout=out,
            )
        output = out.getvalue()
        assert "skip" in output.lower() or "install" in output.lower()


@pytest.mark.django_db
class TestCommandHandleFullRun:
    def test_full_run_creates_installation(self):
        from optimizer.models import USUInstallation
        install_resp = _make_response([_JAVA_INSTALL_ROW])
        demand_resp = _make_response([_JAVA_DEMAND_ROW])
        responses = [install_resp, demand_resp]
        call_count = [0]

        def fake_get(*args, **kwargs):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            return responses[idx]

        with patch("requests.Session.get", side_effect=fake_get):
            call_command(
                "fetch_java_usu_data",
                "--tenant=test_java_full_run",
                stdout=io.StringIO(),
            )
        assert USUInstallation.objects.filter(
            tenant__name="test_java_full_run"
        ).count() >= 1

    def test_full_run_outputs_complete_message(self):
        install_resp = _make_response([_JAVA_INSTALL_ROW])
        demand_resp = _make_response([_JAVA_DEMAND_ROW])
        responses = [install_resp, demand_resp]
        call_count = [0]

        def fake_get(*args, **kwargs):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            return responses[idx]

        with patch("requests.Session.get", side_effect=fake_get):
            out = io.StringIO()
            call_command(
                "fetch_java_usu_data",
                "--tenant=test_java_full_output",
                stdout=out,
            )
        output = out.getvalue()
        assert "complete" in output.lower() or "sync" in output.lower()
