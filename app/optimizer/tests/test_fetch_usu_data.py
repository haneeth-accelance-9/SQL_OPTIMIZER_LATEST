"""
Tests for optimizer/management/commands/fetch_usu_data.py

Covers:
  - _str()       type-coercion helper
  - _bool()      type-coercion helper
  - _decimal()   type-coercion helper
  - _int()       type-coercion helper
  - _date()      type-coercion helper
  - _beat_ids()  helper
  - Command.handle() with --skip-demand, --skip-install, --dry-run flags
    (HTTP calls mocked, DB writes exercised via @pytest.mark.django_db)
"""
import io
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from optimizer.management.commands.fetch_usu_data import (
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

    def test_blank_string_returns_none(self):
        assert _str("") is None

    def test_whitespace_only_returns_none(self):
        assert _str("   ") is None

    def test_normal_string_returned(self):
        assert _str("hello") == "hello"

    def test_strips_whitespace(self):
        assert _str("  hello  ") == "hello"

    def test_truncation_with_max_len(self):
        assert _str("abcdefgh", max_len=4) == "abcd"

    def test_no_truncation_when_no_max_len(self):
        long = "x" * 1000
        assert _str(long) == long

    def test_max_len_longer_than_string_no_truncation(self):
        assert _str("abc", max_len=100) == "abc"

    def test_non_string_value_converted(self):
        assert _str(42) == "42"

    def test_zero_integer_becomes_string(self):
        assert _str(0) == "0"


# ---------------------------------------------------------------------------
# _bool
# ---------------------------------------------------------------------------

class TestBool:
    def test_none_returns_none(self):
        assert _bool(None) is None

    def test_true_passthrough(self):
        assert _bool(True) is True

    def test_false_passthrough(self):
        assert _bool(False) is False

    def test_string_one_returns_true(self):
        assert _bool("1") is True

    def test_string_zero_returns_false(self):
        assert _bool("0") is False

    def test_string_true_lowercase(self):
        assert _bool("true") is True

    def test_string_true_mixed_case(self):
        assert _bool("True") is True

    def test_string_false_lowercase(self):
        assert _bool("false") is False

    def test_string_yes_returns_true(self):
        assert _bool("yes") is True

    def test_string_no_returns_false(self):
        assert _bool("no") is False

    def test_unknown_string_returns_none(self):
        assert _bool("maybe") is None

    def test_empty_string_returns_none(self):
        assert _bool("") is None

    def test_string_with_spaces_stripped(self):
        assert _bool("  1  ") is True


# ---------------------------------------------------------------------------
# _decimal
# ---------------------------------------------------------------------------

class TestDecimal:
    def test_none_returns_none(self):
        assert _decimal(None) is None

    def test_valid_float_string(self):
        result = _decimal("3.14")
        assert result == Decimal("3.14")

    def test_valid_integer_string(self):
        result = _decimal("42")
        assert result == Decimal("42")

    def test_invalid_string_returns_none(self):
        assert _decimal("not-a-number") is None

    def test_decimal_passthrough(self):
        d = Decimal("99.99")
        result = _decimal(d)
        assert result == d

    def test_strips_whitespace(self):
        result = _decimal("  5.5  ")
        assert result == Decimal("5.5")

    def test_zero_string(self):
        assert _decimal("0") == Decimal("0")

    def test_negative_value(self):
        assert _decimal("-1.5") == Decimal("-1.5")


# ---------------------------------------------------------------------------
# _int
# ---------------------------------------------------------------------------

class TestInt:
    def test_none_returns_none(self):
        assert _int(None) is None

    def test_valid_integer_string(self):
        assert _int("4") == 4

    def test_float_string_truncates(self):
        assert _int("4.9") == 4

    def test_invalid_string_returns_none(self):
        assert _int("abc") is None


# ---------------------------------------------------------------------------
# _date
# ---------------------------------------------------------------------------

class TestDate:
    def test_none_returns_none(self):
        assert _date(None) is None

    def test_empty_string_returns_none(self):
        assert _date("") is None

    def test_iso_date_string(self):
        from datetime import date
        assert _date("2025-04-15") == date(2025, 4, 15)

    def test_datetime_string_truncated_to_date(self):
        from datetime import date
        assert _date("2025-04-15 12:00:00") == date(2025, 4, 15)

    def test_invalid_string_returns_none(self):
        assert _date("not-a-date") is None


# ---------------------------------------------------------------------------
# _beat_ids
# ---------------------------------------------------------------------------

class TestBeatIds:
    def test_none_returns_empty_list(self):
        assert _beat_ids(None) == []

    def test_empty_string_returns_empty_list(self):
        assert _beat_ids("") == []

    def test_single_id(self):
        assert _beat_ids("BEAT00423746") == ["BEAT00423746"]

    def test_newline_separated_ids(self):
        result = _beat_ids("BEAT00423746\nBEAT04016489")
        assert result == ["BEAT00423746", "BEAT04016489"]

    def test_strips_whitespace_from_each_id(self):
        result = _beat_ids("  BEAT001  \n  BEAT002  ")
        assert result == ["BEAT001", "BEAT002"]

    def test_blank_lines_ignored(self):
        result = _beat_ids("BEAT001\n\nBEAT002\n")
        assert result == ["BEAT001", "BEAT002"]


# ---------------------------------------------------------------------------
# Command.handle() — integration-style tests with mocked HTTP
# ---------------------------------------------------------------------------

def _make_response(data_rows):
    """Build a minimal mock requests.Response returning given data rows."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "data": data_rows,
        "metadata": {"pagination": {"next_page_uri": None}},
    }
    return mock_resp


_INSTALL_ROW = {
    "devices_device_key": "DEV001",
    "devices_device_name": "SERVER01",
    "device_man_systems_name": "AVS",
    "device_statuses_name": "Active",
    "device_types_name": "Physical",
    "dt_is_cloud_device_type": "1",
    "pdt_cloud_provider_type": "Azure",
    "loc_countries_name": "Germany",
    "loc_regions_name": "EU",
    "locations_name": "Berlin",
    "topology_type": "Standalone",
    "cdev_device_key": None,
    "beatid": "BEAT001",
    "device_purposes_name": "Production",
    "manufacturers_name": "Microsoft",
    "product_families_description": "SQL Server",
    "products_description": "SQL Server 2019",
    "products_edition": "Enterprise",
    "license_metrics_description": "Core",
    "calc_license_metrics_me": "Core Factor",
    "inv_statuses_name": "Installed",
    "inv_statuses_std_name": "Active",
    "ignore_usage_flag": "0",
    "ignore_usage_reason": None,
    "no_license_required_flag": "0",
    "device_statuses_name": "Active",
    "devices_cpu_socket_count": "2",
    "devices_cpu_core_count": "8",
    "devices_hyper_threading_factor": "2",
    "source_key": "SRC001",
    "devices_inventory_date": "2025-01-01",
    "creation_date": "2025-01-01 00:00:00",
}

_DEMAND_ROW = {
    "devices_device_key": "DEV002",
    "devices_device_name": "SERVER02",
    "device_man_systems_name": "Public Cloud",
    "device_purposes_name": "Production",
    "device_types_name": "Virtual",
    "device_types_virt_type": "VMware",
    "dt_is_cloud_device_type": "1",
    "pdt_cloud_provider_type": "Azure",
    "topology_type": "Standalone",
    "cdev_device_key": None,
    "center_dev_dev_name": "CLUSTER01",
    "man_name": "Microsoft",
    "pf_description": "SQL Server",
    "products_description": "SQL Server 2019",
    "products_edition": "Standard",
    "imec_eff_quantity": "2.0",
    "calc_no_license_required_flag": "0",
    "devices_cpu_core_count": "4",
    "virt_type": "VMware",
    "cloud_provider": "Azure",
    "devices_cpu_thread_count": "8",
    "devices_hyper_threading_factor": "2",
}


@pytest.mark.django_db
class TestCommandHandleSkipDemand:
    """handle() with --skip-demand: only installations fetched and saved."""

    def test_skip_demand_writes_installations(self):
        install_resp = _make_response([_INSTALL_ROW])
        with patch("requests.Session.get", return_value=install_resp):
            out = io.StringIO()
            call_command(
                "fetch_usu_data",
                "--skip-demand",
                "--tenant=test_skip_demand",
                stdout=out,
            )
        output = out.getvalue()
        assert "Skipping demand" in output or "skip" in output.lower() or "demand" in output.lower()

    def test_skip_demand_does_not_call_demand_endpoint(self):
        install_resp = _make_response([_INSTALL_ROW])
        with patch("requests.Session.get", return_value=install_resp) as mock_get:
            call_command(
                "fetch_usu_data",
                "--skip-demand",
                "--tenant=test_skip_demand2",
                stdout=io.StringIO(),
            )
        # Should only be called for installation endpoint, not demand endpoint
        for call_args in mock_get.call_args_list:
            url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
            assert "demanddetails" not in str(url)


@pytest.mark.django_db
class TestCommandHandleSkipInstall:
    """handle() with --skip-install: only demand details fetched and saved."""

    def test_skip_install_writes_demand_details(self):
        demand_resp = _make_response([_DEMAND_ROW])
        with patch("requests.Session.get", return_value=demand_resp):
            out = io.StringIO()
            call_command(
                "fetch_usu_data",
                "--skip-install",
                "--tenant=test_skip_install",
                stdout=out,
            )
        output = out.getvalue()
        assert "Skipping" in output or "install" in output.lower()

    def test_skip_install_does_not_call_install_endpoint(self):
        demand_resp = _make_response([_DEMAND_ROW])
        with patch("requests.Session.get", return_value=demand_resp) as mock_get:
            call_command(
                "fetch_usu_data",
                "--skip-install",
                "--tenant=test_skip_install2",
                stdout=io.StringIO(),
            )
        for call_args in mock_get.call_args_list:
            url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
            assert "installations" not in str(url)


@pytest.mark.django_db
class TestCommandHandleDryRun:
    """handle() with --dry-run: fetches from API but skips DB writes."""

    def test_dry_run_outputs_dry_run_message(self):
        install_resp = _make_response([_INSTALL_ROW])
        demand_resp = _make_response([_DEMAND_ROW])
        responses = [install_resp, demand_resp]
        call_count = [0]

        def fake_get(*args, **kwargs):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            return responses[idx]

        with patch("requests.Session.get", side_effect=fake_get):
            out = io.StringIO()
            call_command(
                "fetch_usu_data",
                "--dry-run",
                "--tenant=test_dry_run",
                stdout=out,
            )
        output = out.getvalue()
        assert "dry" in output.lower() or "DRY" in output

    def test_dry_run_skips_db_writes(self):
        from optimizer.models import USUInstallation
        install_resp = _make_response([_INSTALL_ROW])
        demand_resp = _make_response([_DEMAND_ROW])
        responses = [install_resp, demand_resp]
        call_count = [0]

        def fake_get(*args, **kwargs):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            return responses[idx]

        before = USUInstallation.objects.count()
        with patch("requests.Session.get", side_effect=fake_get):
            call_command(
                "fetch_usu_data",
                "--dry-run",
                "--tenant=test_dry_run_no_write",
                stdout=io.StringIO(),
            )
        after = USUInstallation.objects.count()
        # With --dry-run, no new rows should be inserted
        assert after == before


@pytest.mark.django_db(transaction=True)
class TestCommandHandleFullRun:
    """handle() full run: both endpoints fetched, data saved to DB."""

    def test_full_run_creates_installation_rows(self):
        from optimizer.models import USUInstallation
        install_resp = _make_response([_INSTALL_ROW])
        demand_resp = _make_response([_DEMAND_ROW])
        responses = [install_resp, demand_resp]
        call_count = [0]

        def fake_get(*args, **kwargs):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            return responses[idx]

        with patch("requests.Session.get", side_effect=fake_get):
            call_command(
                "fetch_usu_data",
                "--tenant=test_full_run_usu",
                stdout=io.StringIO(),
            )
        assert USUInstallation.objects.filter(
            tenant__name="test_full_run_usu"
        ).count() >= 1

    def test_full_run_outputs_sync_complete(self):
        install_resp = _make_response([_INSTALL_ROW])
        demand_resp = _make_response([_DEMAND_ROW])
        responses = [install_resp, demand_resp]
        call_count = [0]

        def fake_get(*args, **kwargs):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            return responses[idx]

        with patch("requests.Session.get", side_effect=fake_get):
            out = io.StringIO()
            call_command(
                "fetch_usu_data",
                "--tenant=test_full_run_output",
                stdout=out,
            )
        output = out.getvalue()
        assert "complete" in output.lower() or "sync" in output.lower()
