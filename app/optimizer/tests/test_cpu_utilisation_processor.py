"""
Tests for optimizer.services.cpu_utilisation_processor
Covers helper functions, object builders, batch writers, and the main pipeline.

Patching note: Server, CPUUtilisation, USUDemandDetail, USUInstallation are imported
*inside* functions (lazy imports), so they must be patched at their source:
  optimizer.models.Server  / optimizer.models.CPUUtilisation  etc.
"""
import io
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from optimizer.services.cpu_utilisation_processor import (
    BATCH_SIZE,
    COL_AVG_CPU_START,
    COL_AVG_MEM_START,
    COL_LOGICAL_CPU_START,
    COL_MAX_CPU_START,
    COL_MAX_MEM_START,
    COL_MIN_MEM_START,
    COL_PHYSICAL_RAM_START,
    PERIOD_MONTHS,
    ProcessingResult,
    _CPU_UPDATE_FIELDS,
    _SERVER_UPDATE_FIELDS,
    _apply_server_fields,
    _build_cpu_objects,
    _to_cluster_name,
    _to_decimal,
    _to_int,
    _to_is_virtual,
    _to_str,
    _write_cpu_batch,
    _write_server_batch,
    process_cpu_utilisation,
)


# ── _to_str ───────────────────────────────────────────────────────────────────

class TestToStr:
    def test_none_returns_none(self):
        assert _to_str(None) is None

    def test_empty_string_returns_none(self):
        assert _to_str("") is None
        assert _to_str("   ") is None

    def test_strips_whitespace(self):
        assert _to_str("  hello  ") == "hello"

    def test_int_value(self):
        assert _to_str(42) == "42"

    def test_float_value(self):
        assert _to_str(3.14) == "3.14"

    def test_normal_string(self):
        assert _to_str("SQL-Server-01") == "SQL-Server-01"


# ── _to_is_virtual ────────────────────────────────────────────────────────────

class TestToIsVirtual:
    def test_none_returns_true(self):
        assert _to_is_virtual(None) is True

    def test_false_string_returns_false(self):
        assert _to_is_virtual("FALSE") is False
        assert _to_is_virtual("false") is False
        assert _to_is_virtual("False") is False

    def test_true_string_returns_true(self):
        assert _to_is_virtual("TRUE") is True
        assert _to_is_virtual("true") is True

    def test_empty_string_returns_true(self):
        assert _to_is_virtual("") is True

    def test_other_values_return_true(self):
        assert _to_is_virtual("Yes") is True
        assert _to_is_virtual("1") is True
        assert _to_is_virtual("NO") is True

    def test_false_with_whitespace(self):
        assert _to_is_virtual("  FALSE  ") is False


# ── _to_cluster_name ──────────────────────────────────────────────────────────

class TestToClusterName:
    def test_none_returns_none(self):
        assert _to_cluster_name(None) is None

    def test_zero_string_returns_none(self):
        assert _to_cluster_name("0") is None

    def test_empty_string_returns_none(self):
        assert _to_cluster_name("") is None
        assert _to_cluster_name("   ") is None

    def test_valid_name_returned(self):
        assert _to_cluster_name("CLUSTER-A") == "CLUSTER-A"

    def test_zero_integer_strips_to_zero_string(self):
        # int 0 → str "0" → None
        assert _to_cluster_name(0) is None

    def test_non_zero_integer(self):
        assert _to_cluster_name(1) == "1"

    def test_strips_whitespace(self):
        assert _to_cluster_name("  my-cluster  ") == "my-cluster"


# ── _to_decimal ───────────────────────────────────────────────────────────────

class TestToDecimal:
    def test_none_returns_none(self):
        assert _to_decimal(None) is None

    def test_empty_string_returns_none(self):
        assert _to_decimal("") is None
        assert _to_decimal("  ") is None

    def test_excel_errors_return_none(self):
        for err in ("#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!", "#ERROR!"):
            assert _to_decimal(err) is None

    def test_valid_float_string(self):
        assert _to_decimal("45.6") == pytest.approx(45.6)

    def test_valid_int(self):
        assert _to_decimal(8) == pytest.approx(8.0)

    def test_valid_float(self):
        assert _to_decimal(3.14) == pytest.approx(3.14)

    def test_non_numeric_string_returns_none(self):
        assert _to_decimal("abc") is None

    def test_zero(self):
        assert _to_decimal(0) == pytest.approx(0.0)


# ── _to_int ───────────────────────────────────────────────────────────────────

class TestToInt:
    def test_none_returns_none(self):
        assert _to_int(None) is None

    def test_int_passthrough(self):
        assert _to_int(8) == 8

    def test_float_rounds(self):
        assert _to_int(7.6) == 8
        assert _to_int(7.4) == 7

    def test_string_integer(self):
        assert _to_int("16") == 16

    def test_excel_error_returns_none(self):
        assert _to_int("#N/A") is None


# ── ProcessingResult ──────────────────────────────────────────────────────────

class TestProcessingResult:
    def test_defaults(self):
        r = ProcessingResult()
        assert r.servers_updated == 0
        assert r.servers_failed == 0
        assert r.skipped == 0
        assert r.cpu_processed == 0
        assert r.cpu_failed == 0
        assert r.errors == []

    def test_summary_no_errors(self):
        r = ProcessingResult(servers_updated=5, skipped=2, cpu_processed=60)
        s = r.summary()
        assert "updated=5" in s
        assert "skipped(not in DB)=2" in s
        assert "processed=60" in s
        assert "errors" not in s

    def test_summary_with_errors(self):
        r = ProcessingResult(servers_failed=1, errors=["something went wrong"])
        s = r.summary()
        assert "errors=1" in s


# ── _apply_server_fields ──────────────────────────────────────────────────────

class TestApplyServerFields:
    def _make_row(self):
        row = [None] * 110
        row[0] = "BOO-001"       # Number
        row[1] = "SQL-SERVER-01" # Server Name
        row[2] = "FALSE"         # Is Virtual?
        row[3] = "CLUSTER-A"     # Cluster Name
        row[4] = "High"          # Criticality
        row[5] = "PROD"          # Environment type
        row[6] = "Azure"         # Hosting Zone
        row[7] = "Active"        # Installed Status
        row[8] = "EU-West"       # Location
        row[9] = "Windows"       # Platform / Class
        return row

    def test_fields_set_correctly(self):
        server = MagicMock()
        row = self._make_row()
        now = MagicMock()
        _apply_server_fields(server, row, now)

        assert server.boones_number == "BOO-001"
        assert server.hosting_zone == "Azure"
        assert server.environment == "PROD"
        assert server.platform == "Windows"
        assert server.is_virtual is False
        assert server.cluster_name == "CLUSTER-A"
        assert server.criticality == "High"
        assert server.location == "EU-West"
        assert server.installed_status_boones == "Active"
        assert server.last_synced_at is now

    def test_none_cells_produce_none(self):
        server = MagicMock()
        row = [None] * 110
        _apply_server_fields(server, row, MagicMock())

        assert server.boones_number is None
        assert server.is_virtual is True  # None → virtual=True
        assert server.cluster_name is None

    def test_zero_cluster_produces_none(self):
        server = MagicMock()
        row = [None] * 110
        row[3] = "0"
        _apply_server_fields(server, row, MagicMock())
        assert server.cluster_name is None


# ── _build_cpu_objects ────────────────────────────────────────────────────────

class TestBuildCpuObjects:
    def _make_row(self, logical=8, avg_cpu=45.0, max_cpu=80.0,
                  ram=32.0, avg_mem=60.0, max_mem=75.0, min_mem=40.0):
        row = [None] * 110
        for i in range(12):
            row[COL_LOGICAL_CPU_START + i] = logical
            row[COL_AVG_CPU_START + i]      = avg_cpu
            row[COL_MAX_CPU_START + i]      = max_cpu
            row[COL_PHYSICAL_RAM_START + i] = ram
            row[COL_AVG_MEM_START + i]      = avg_mem
            row[COL_MAX_MEM_START + i]      = max_mem
            row[COL_MIN_MEM_START + i]      = min_mem
        # Storage columns for month 10 (Feb-26) and 11 (Mar-26)
        row[101] = 500.0
        row[102] = 600.0
        row[104] = 200.0
        row[105] = 250.0
        return row

    def _build(self, row, **kw):
        server = MagicMock()
        tenant = MagicMock()
        with patch("optimizer.models.CPUUtilisation") as MockCPU:
            MockCPU.SOURCE_BOONES_PRIVATE = "boones_private"
            MockCPU.side_effect = lambda **kwargs: kwargs
            return _build_cpu_objects(server, tenant, row, None)

    def test_returns_12_objects(self):
        row = self._make_row()
        server = MagicMock()
        tenant = MagicMock()
        with patch("optimizer.models.CPUUtilisation") as MockCPU:
            MockCPU.SOURCE_BOONES_PRIVATE = "boones_private"
            MockCPU.side_effect = lambda **kwargs: kwargs
            objs = _build_cpu_objects(server, tenant, row, None)
        assert len(objs) == 12

    def test_period_months_match_constants(self):
        row = self._make_row()
        server = MagicMock()
        tenant = MagicMock()
        with patch("optimizer.models.CPUUtilisation") as MockCPU:
            MockCPU.SOURCE_BOONES_PRIVATE = "boones_private"
            MockCPU.side_effect = lambda **kwargs: kwargs
            objs = _build_cpu_objects(server, tenant, row, None)
        assert [o["period_month"] for o in objs] == PERIOD_MONTHS

    def test_logical_cpu_and_avg_cpu_correct(self):
        row = self._make_row(logical=16, avg_cpu=25.5)
        server = MagicMock()
        tenant = MagicMock()
        with patch("optimizer.models.CPUUtilisation") as MockCPU:
            MockCPU.SOURCE_BOONES_PRIVATE = "boones_private"
            MockCPU.side_effect = lambda **kwargs: kwargs
            objs = _build_cpu_objects(server, tenant, row, None)
        assert objs[0]["logical_cpu_count"] == 16
        assert objs[0]["avg_cpu_pct"] == pytest.approx(25.5)

    def test_storage_cols_only_for_last_two_months(self):
        row = self._make_row()
        server = MagicMock()
        tenant = MagicMock()
        with patch("optimizer.models.CPUUtilisation") as MockCPU:
            MockCPU.SOURCE_BOONES_PRIVATE = "boones_private"
            MockCPU.side_effect = lambda **kwargs: kwargs
            objs = _build_cpu_objects(server, tenant, row, None)

        # Months 0-9 have no storage
        for obj in objs[:10]:
            assert obj["allocated_storage_gb"] is None
            assert obj["used_storage_gb"] is None

        assert objs[10]["allocated_storage_gb"] == pytest.approx(500.0)
        assert objs[10]["used_storage_gb"] == pytest.approx(200.0)
        assert objs[11]["allocated_storage_gb"] == pytest.approx(600.0)
        assert objs[11]["used_storage_gb"] == pytest.approx(250.0)

    def test_excel_error_in_cpu_produces_none(self):
        row = self._make_row()
        row[COL_AVG_CPU_START] = "#N/A"
        server = MagicMock()
        tenant = MagicMock()
        with patch("optimizer.models.CPUUtilisation") as MockCPU:
            MockCPU.SOURCE_BOONES_PRIVATE = "boones_private"
            MockCPU.side_effect = lambda **kwargs: kwargs
            objs = _build_cpu_objects(server, tenant, row, None)
        assert objs[0]["avg_cpu_pct"] is None

    def test_min_cpu_pct_always_none(self):
        row = self._make_row()
        server = MagicMock()
        tenant = MagicMock()
        with patch("optimizer.models.CPUUtilisation") as MockCPU:
            MockCPU.SOURCE_BOONES_PRIVATE = "boones_private"
            MockCPU.side_effect = lambda **kwargs: kwargs
            objs = _build_cpu_objects(server, tenant, row, None)
        for obj in objs:
            assert obj["min_cpu_pct"] is None


# ── _write_cpu_batch ──────────────────────────────────────────────────────────

class TestWriteCpuBatch:
    def _make_cpu_rec(self, server_name="sql-01", month=date(2025, 4, 1)):
        rec = MagicMock()
        rec.server.server_name = server_name
        rec.period_month = month
        rec.source = "boones_private"
        for f in _CPU_UPDATE_FIELDS:
            setattr(rec, f, None)
        return rec

    def test_bulk_create_success_increments_count(self):
        records = [self._make_cpu_rec() for _ in range(3)]
        result = ProcessingResult()
        with patch("optimizer.models.CPUUtilisation") as MockCPU:
            MockCPU.objects.bulk_create.return_value = None
            _write_cpu_batch(records, result)

        assert result.cpu_processed == 3
        assert result.cpu_failed == 0

    def test_bulk_create_failure_falls_back_to_individual(self):
        records = [self._make_cpu_rec(f"sql-0{i}") for i in range(3)]
        result = ProcessingResult()
        with patch("optimizer.models.CPUUtilisation") as MockCPU:
            MockCPU.objects.bulk_create.side_effect = Exception("bulk failed")
            MockCPU.objects.update_or_create.return_value = (MagicMock(), True)
            _write_cpu_batch(records, result)

        assert result.cpu_processed == 3
        assert result.cpu_failed == 0
        assert MockCPU.objects.update_or_create.call_count == 3

    def test_individual_fallback_failure_increments_failed(self):
        records = [self._make_cpu_rec()]
        result = ProcessingResult()
        with patch("optimizer.models.CPUUtilisation") as MockCPU:
            MockCPU.objects.bulk_create.side_effect = Exception("bulk failed")
            MockCPU.objects.update_or_create.side_effect = Exception("individual failed")
            _write_cpu_batch(records, result)

        assert result.cpu_failed == 1
        assert result.cpu_processed == 0
        assert len(result.errors) == 1


# ── _write_server_batch ───────────────────────────────────────────────────────

class TestWriteServerBatch:
    def _make_server(self, name="sql-01"):
        s = MagicMock()
        s.server_name = name
        return s

    def test_bulk_update_success(self):
        servers = [self._make_server(f"sql-0{i}") for i in range(3)]
        result = ProcessingResult()
        with patch("optimizer.models.Server") as MockServer:
            MockServer.objects.bulk_update.return_value = None
            _write_server_batch(servers, result)

        assert result.servers_updated == 3
        assert result.servers_failed == 0

    def test_bulk_update_failure_falls_back(self):
        servers = [self._make_server(f"sql-0{i}") for i in range(2)]
        result = ProcessingResult()
        with patch("optimizer.models.Server") as MockServer:
            MockServer.objects.bulk_update.side_effect = Exception("bulk failed")
            _write_server_batch(servers, result)

        for srv in servers:
            srv.save.assert_called_once_with(update_fields=_SERVER_UPDATE_FIELDS)
        assert result.servers_updated == 2
        assert result.servers_failed == 0

    def test_individual_fallback_failure_increments_failed(self):
        servers = [self._make_server()]
        result = ProcessingResult()
        with patch("optimizer.models.Server") as MockServer:
            MockServer.objects.bulk_update.side_effect = Exception("bulk failed")
            servers[0].save.side_effect = Exception("save failed")
            _write_server_batch(servers, result)

        assert result.servers_failed == 1
        assert result.servers_updated == 0
        assert len(result.errors) == 1


# ── Helpers for process_cpu_utilisation tests ─────────────────────────────────

def _make_fake_xlsx(rows_data: list[list]) -> io.BytesIO:
    """Build a minimal in-memory xlsx with a header row + data rows."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Number", "Server Name"] + [""] * 108)
    for row in rows_data:
        padded = list(row) + [None] * (110 - len(row))
        ws.append(padded[:110])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = "test_upload.xlsx"
    return buf


def _make_server_mock(name="sql-01", tenant=None):
    s = MagicMock()
    s.server_name = name
    s.tenant = tenant or MagicMock()
    return s


def _build_minimal_row(server_name="sql-01"):
    row = [None] * 110
    row[0] = "BOO-001"
    row[1] = server_name
    row[2] = "TRUE"
    row[3] = "0"
    row[4] = "Medium"
    row[5] = "PROD"
    row[6] = "Azure"
    row[7] = "Active"
    row[8] = "EU"
    row[9] = "Windows"
    for i in range(12):
        row[COL_LOGICAL_CPU_START + i]  = 8
        row[COL_AVG_CPU_START + i]      = 20.0
        row[COL_MAX_CPU_START + i]      = 50.0
        row[COL_PHYSICAL_RAM_START + i] = 32.0
        row[COL_AVG_MEM_START + i]      = 55.0
        row[COL_MAX_MEM_START + i]      = 70.0
        row[COL_MIN_MEM_START + i]      = 40.0
    return row


def _patch_db(server_list):
    """Return a dict of active patches for the DB layer, given a server list."""
    patches = {}

    mock_server = MagicMock()
    mock_server.objects.filter.return_value.select_related.return_value = server_list
    mock_server.objects.bulk_update.return_value = None

    mock_demand = MagicMock()
    mock_demand.objects.filter.return_value.values.return_value = []

    mock_install = MagicMock()
    mock_install.objects.filter.return_value.values.return_value = []

    mock_cpu = MagicMock()
    mock_cpu.SOURCE_BOONES_PRIVATE = "boones_private"
    mock_cpu.objects.bulk_create.return_value = None

    mock_tx = MagicMock()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=None)
    cm.__exit__ = MagicMock(return_value=False)
    mock_tx.atomic.return_value = cm

    return {
        "mock_server": mock_server,
        "mock_demand": mock_demand,
        "mock_install": mock_install,
        "mock_cpu": mock_cpu,
        "mock_tx": mock_tx,
    }


# ── process_cpu_utilisation ───────────────────────────────────────────────────

class TestProcessCpuUtilisation:

    def test_file_read_error_returns_result_with_error(self):
        bad_file = io.BytesIO(b"not an xlsx")
        bad_file.name = "bad.xlsx"
        result = process_cpu_utilisation(bad_file)
        assert len(result.errors) == 1
        assert "Could not read workbook" in result.errors[0]
        assert result.servers_updated == 0

    def test_empty_file_returns_empty_result(self):
        f = _make_fake_xlsx([])
        db = _patch_db([])
        with patch("optimizer.models.Server", db["mock_server"]), \
             patch("optimizer.models.USUDemandDetail", db["mock_demand"]), \
             patch("optimizer.models.USUInstallation", db["mock_install"]), \
             patch("optimizer.models.CPUUtilisation", db["mock_cpu"]), \
             patch("optimizer.services.cpu_utilisation_processor.transaction", db["mock_tx"]):
            result = process_cpu_utilisation(f)

        assert result.servers_updated == 0
        assert result.skipped == 0
        assert result.cpu_processed == 0

    def test_server_not_in_db_is_skipped(self):
        row = _build_minimal_row("unknown-server")
        f = _make_fake_xlsx([row])
        # server_map is empty → no match
        db = _patch_db([])
        with patch("optimizer.models.Server", db["mock_server"]), \
             patch("optimizer.models.USUDemandDetail", db["mock_demand"]), \
             patch("optimizer.models.USUInstallation", db["mock_install"]), \
             patch("optimizer.models.CPUUtilisation", db["mock_cpu"]), \
             patch("optimizer.services.cpu_utilisation_processor.transaction", db["mock_tx"]):
            result = process_cpu_utilisation(f)

        assert result.skipped == 1
        assert result.servers_updated == 0

    def test_matched_server_writes_cpu_and_server(self):
        server = _make_server_mock("sql-01")
        row = _build_minimal_row("sql-01")
        f = _make_fake_xlsx([row])
        db = _patch_db([server])
        with patch("optimizer.models.Server", db["mock_server"]), \
             patch("optimizer.models.USUDemandDetail", db["mock_demand"]), \
             patch("optimizer.models.USUInstallation", db["mock_install"]), \
             patch("optimizer.models.CPUUtilisation", db["mock_cpu"]), \
             patch("optimizer.services.cpu_utilisation_processor.transaction", db["mock_tx"]):
            result = process_cpu_utilisation(f)

        assert result.cpu_processed == 12
        assert result.servers_updated == 1
        assert result.skipped == 0

    def test_batch_outer_failure_marks_servers_and_cpu_failed(self):
        server = _make_server_mock("sql-01")
        row = _build_minimal_row("sql-01")
        f = _make_fake_xlsx([row])
        db = _patch_db([server])

        # Make the transaction.atomic() context manager raise on __enter__
        cm = MagicMock()
        cm.__enter__ = MagicMock(side_effect=Exception("connection lost"))
        cm.__exit__ = MagicMock(return_value=False)
        db["mock_tx"].atomic.return_value = cm

        with patch("optimizer.models.Server", db["mock_server"]), \
             patch("optimizer.models.USUDemandDetail", db["mock_demand"]), \
             patch("optimizer.models.USUInstallation", db["mock_install"]), \
             patch("optimizer.models.CPUUtilisation", db["mock_cpu"]), \
             patch("optimizer.services.cpu_utilisation_processor.transaction", db["mock_tx"]):
            result = process_cpu_utilisation(f)

        assert result.servers_failed == 1
        assert result.cpu_failed == 12
        assert len(result.errors) == 1

    def test_multiple_servers_split_into_two_batches(self):
        n = BATCH_SIZE + 5
        servers = [_make_server_mock(f"sql-{i:03d}") for i in range(n)]
        rows = [_build_minimal_row(f"sql-{i:03d}") for i in range(n)]
        f = _make_fake_xlsx(rows)
        db = _patch_db(servers)
        with patch("optimizer.models.Server", db["mock_server"]), \
             patch("optimizer.models.USUDemandDetail", db["mock_demand"]), \
             patch("optimizer.models.USUInstallation", db["mock_install"]), \
             patch("optimizer.models.CPUUtilisation", db["mock_cpu"]), \
             patch("optimizer.services.cpu_utilisation_processor.transaction", db["mock_tx"]):
            result = process_cpu_utilisation(f)

        assert result.cpu_processed == n * 12
        assert result.servers_updated == n
        # Two batches → bulk_create called twice
        assert db["mock_cpu"].objects.bulk_create.call_count == 2

    def test_case_insensitive_server_name_lookup(self):
        server = _make_server_mock("SQL-SERVER-01")
        row = _build_minimal_row("sql-server-01")  # lowercase in file
        f = _make_fake_xlsx([row])
        db = _patch_db([server])
        with patch("optimizer.models.Server", db["mock_server"]), \
             patch("optimizer.models.USUDemandDetail", db["mock_demand"]), \
             patch("optimizer.models.USUInstallation", db["mock_install"]), \
             patch("optimizer.models.CPUUtilisation", db["mock_cpu"]), \
             patch("optimizer.services.cpu_utilisation_processor.transaction", db["mock_tx"]):
            result = process_cpu_utilisation(f)

        assert result.servers_updated == 1
        assert result.skipped == 0

    def test_row_shorter_than_110_padded_with_none(self):
        server = _make_server_mock("sql-short")
        # Row with only 20 columns — processor must pad without crashing
        row = [None] * 20
        row[1] = "sql-short"
        f = _make_fake_xlsx([row])
        db = _patch_db([server])
        with patch("optimizer.models.Server", db["mock_server"]), \
             patch("optimizer.models.USUDemandDetail", db["mock_demand"]), \
             patch("optimizer.models.USUInstallation", db["mock_install"]), \
             patch("optimizer.models.CPUUtilisation", db["mock_cpu"]), \
             patch("optimizer.services.cpu_utilisation_processor.transaction", db["mock_tx"]):
            result = process_cpu_utilisation(f)

        # All CPU fields will be None, but 12 objects still written
        assert result.cpu_processed == 12
