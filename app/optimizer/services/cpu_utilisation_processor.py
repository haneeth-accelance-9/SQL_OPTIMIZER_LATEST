"""
Process a validated Boones workbook:
  Step 1 — UPDATE public.server  (matched by server_name)
  Step 2 — UPSERT public.cpu_utilisation  (unpivot wide → long, 12 rows per server)

Server UPDATE column mapping
  DB column                CSV column           Transform
  boones_number            Number               Direct
  hosting_zone             Hosting Zone         Direct
  environment              Environment type     Direct
  platform                 Platform / Class     Direct
  is_virtual               Is Virtual?          "FALSE" → false; everything else → true
  cluster_name             Cluster Name         "0" → null; else direct
  criticality              Criticality          Direct
  location                 Location             Direct
  installed_status_boones  Installed Status     Direct
  last_synced_at           —                    NOW() at import time

Column layout (0-indexed) matches EXPECTED_HEADERS in upload_validator.py:
  0    Number
  1    Server Name  ← match key
  2    Is Virtual?
  3    Cluster Name
  4    Criticality
  5    Environment type
  6    Hosting Zone
  7    Installed Status
  8    Location
  9    Platform / Class
  10-21  Logical CPU            Apr-25 → Mar-26
  22     <empty separator>
  23-34  Average CPU Util (%)   Apr-25 → Mar-26
  35     <empty>
  36-47  Maximum CPU Util (%)   Apr-25 → Mar-26
  48     <empty>
  49-60  Physical RAM (GiB)     Apr-25 → Mar-26
  61     <empty>
  62-73  Avg free Memory (%)    Apr-25 → Mar-26
  74     <empty>
  75-86  Max free Memory (%)    Apr-25 → Mar-26
  87     <empty>
  88-99  Min free Memory (%)    Apr-25 → Mar-26
  100    <empty>
  101    Allocated Storage (GB) Feb-26
  102    Allocated Storage (GB) Mar-26
  103    <empty>
  104    Used Storage (GB)      Feb-26
  105    Used Storage (GB)      Mar-26
  106-109 Trailing fixed columns

Transaction strategy
  Outer transaction.atomic() — single DB commit for performance.
  Inner transaction.atomic() per server — acts as a savepoint.
  If one server's data causes a DB error (e.g. out-of-range value), that
  server's savepoint is rolled back and the next server continues cleanly.
  Without savepoints a single DB error aborts the whole PostgreSQL transaction
  and every subsequent query fails, losing all remaining data.
"""
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Metadata column indices (0-based) ────────────────────────────────────────

COL_NUMBER           = 0   # → boones_number
COL_SERVER_NAME      = 1   # match key
COL_IS_VIRTUAL       = 2   # → is_virtual
COL_CLUSTER_NAME     = 3   # → cluster_name
COL_CRITICALITY      = 4   # → criticality
COL_ENVIRONMENT      = 5   # → environment
COL_HOSTING_ZONE     = 6   # → hosting_zone
COL_INSTALLED_STATUS = 7   # → installed_status_boones
COL_LOCATION         = 8   # → location
COL_PLATFORM         = 9   # → platform

# ── cpu_utilisation metric column start indices (0-based) ────────────────────

# 12-month window: Apr-25 (index 0) → Mar-26 (index 11)
PERIOD_MONTHS = [
    date(2025, 4, 1), date(2025, 5, 1), date(2025, 6, 1),
    date(2025, 7, 1), date(2025, 8, 1), date(2025, 9, 1),
    date(2025, 10, 1), date(2025, 11, 1), date(2025, 12, 1),
    date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1),
]

COL_LOGICAL_CPU_START  = 10   # cols 10-21
COL_AVG_CPU_START      = 23   # cols 23-34
COL_MAX_CPU_START      = 36   # cols 36-47
COL_PHYSICAL_RAM_START = 49   # cols 49-60
COL_AVG_MEM_START      = 62   # cols 62-73
COL_MAX_MEM_START      = 75   # cols 75-86
COL_MIN_MEM_START      = 88   # cols 88-99

# Storage only exists for Feb-26 (month index 10) and Mar-26 (month index 11)
_STORAGE_COLS: dict[int, tuple[int, int]] = {
    10: (101, 104),  # (allocated_storage_col, used_storage_col) for Feb-26
    11: (102, 105),  # Mar-26
}

# Server fields written by bulk_update
_SERVER_UPDATE_FIELDS = [
    "boones_number",
    "hosting_zone",
    "environment",
    "platform",
    "is_virtual",
    "cluster_name",
    "criticality",
    "location",
    "installed_status_boones",
    "last_synced_at",
]

# Excel formula error strings — openpyxl returns these as raw strings
# when data_only=True and the cached value is an error token.
_EXCEL_ERRORS = frozenset({
    "#N/A", "#REF!", "#VALUE!", "#DIV/0!",
    "#NAME?", "#NUM!", "#NULL!", "#ERROR!",
})


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class ProcessingResult:
    servers_updated: int = 0   # server rows updated in DB
    servers_failed: int = 0    # server rows skipped due to DB error
    created: int = 0           # cpu_utilisation rows inserted
    updated: int = 0           # cpu_utilisation rows updated
    skipped: int = 0           # file rows where server was not found in DB
    errors: list[str] = field(default_factory=list)

    @property
    def total_file_rows(self) -> int:
        return self.servers_updated + self.servers_failed + self.skipped

    def summary(self) -> str:
        parts = [
            f"Processed {self.total_file_rows} server rows — "
            f"{self.servers_updated} servers updated, "
            f"{self.skipped} skipped (not in DB)",
        ]
        if self.servers_failed:
            parts.append(f"{self.servers_failed} failed (DB error)")
        parts.append(
            f"cpu_utilisation: {self.created} inserted, {self.updated} updated"
        )
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        return "; ".join(parts) + "."


# ── Transform helpers ─────────────────────────────────────────────────────────

def _to_str(value) -> Optional[str]:
    """Strip whitespace; return None for empty/None."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _to_is_virtual(value) -> bool:
    """
    "FALSE" (case-insensitive) → False.
    Everything else — "TRUE", "N/A", "-", blank, None → True.
    """
    if value is None:
        return True
    return str(value).strip().upper() != "FALSE"


def _to_cluster_name(value) -> Optional[str]:
    """
    "0" or empty/None → None (no cluster).
    Anything else → stripped string.
    """
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s == "0":
        return None
    return s


def _to_decimal(value) -> Optional[float]:
    """
    Coerce to float or return None.
    Handles: None, blank strings, Excel error tokens (#N/A etc.),
    non-numeric strings, and actual numeric types.
    """
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped in _EXCEL_ERRORS:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> Optional[int]:
    v = _to_decimal(value)
    return int(round(v)) if v is not None else None


# ── File reader ───────────────────────────────────────────────────────────────

def _read_data_rows(file) -> list[list[Any]]:
    """Return all data rows (skip header row 1) from the first worksheet."""
    import openpyxl
    file.seek(0)
    wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        rows: list[list[Any]] = []
        skip_first = True
        for row in ws.iter_rows(values_only=True):
            if skip_first:
                skip_first = False
                continue
            rows.append(list(row))
        return rows
    finally:
        wb.close()
        file.seek(0)


# ── Per-server processing (isolated in its own savepoint) ─────────────────────

def _process_server_row(server, tenant, row, row_num, now, result) -> None:
    """
    Update server metadata and upsert 12 cpu_utilisation rows for one file row.
    Runs inside an inner transaction.atomic() so a DB error on this server
    rolls back only this server's writes, leaving the outer transaction intact.
    """
    from optimizer.models import CPUUtilisation, Server

    server_name = server.server_name

    # ── Step 1: mutate server fields (written later via bulk_update) ──────────
    server.boones_number           = _to_str(row[COL_NUMBER])
    server.hosting_zone            = _to_str(row[COL_HOSTING_ZONE])
    server.environment             = _to_str(row[COL_ENVIRONMENT])
    server.platform                = _to_str(row[COL_PLATFORM])
    server.is_virtual              = _to_is_virtual(row[COL_IS_VIRTUAL])
    server.cluster_name            = _to_cluster_name(row[COL_CLUSTER_NAME])
    server.criticality             = _to_str(row[COL_CRITICALITY])
    server.location                = _to_str(row[COL_LOCATION])
    server.installed_status_boones = _to_str(row[COL_INSTALLED_STATUS])
    server.last_synced_at          = now

    # ── Step 2: upsert 12 cpu_utilisation rows ────────────────────────────────
    for month_idx, period_month in enumerate(PERIOD_MONTHS):
        storage_cols = _STORAGE_COLS.get(month_idx)
        alloc_col    = storage_cols[0] if storage_cols else None
        used_col     = storage_cols[1] if storage_cols else None

        defaults = {
            "logical_cpu_count":    _to_int(row[COL_LOGICAL_CPU_START  + month_idx]),
            "avg_cpu_pct":          _to_decimal(row[COL_AVG_CPU_START   + month_idx]),
            "max_cpu_pct":          _to_decimal(row[COL_MAX_CPU_START   + month_idx]),
            "min_cpu_pct":          None,  # not present in Boones file
            "physical_ram_gib":     _to_decimal(row[COL_PHYSICAL_RAM_START + month_idx]),
            "avg_free_memory_pct":  _to_decimal(row[COL_AVG_MEM_START   + month_idx]),
            "max_free_memory_pct":  _to_decimal(row[COL_MAX_MEM_START   + month_idx]),
            "min_free_memory_pct":  _to_decimal(row[COL_MIN_MEM_START   + month_idx]),
            "allocated_storage_gb": _to_decimal(row[alloc_col]) if alloc_col is not None else None,
            "used_storage_gb":      _to_decimal(row[used_col])  if used_col  is not None else None,
            "tenant":               tenant,
        }

        _, created = CPUUtilisation.objects.update_or_create(
            server=server,
            period_month=period_month,
            source=CPUUtilisation.SOURCE_BOONES_PRIVATE,
            defaults=defaults,
        )
        if created:
            result.created += 1
        else:
            result.updated += 1

    result.servers_updated += 1


# ── Public API ────────────────────────────────────────────────────────────────

def process_cpu_utilisation(file, uploaded_by=None) -> ProcessingResult:
    """
    Parse the validated Boones workbook, update matched Server rows, then
    upsert CPUUtilisation rows (one per server per month).

    Tenant is derived from each matched Server row's own tenant FK —
    no separate tenant lookup is performed.

    Transaction strategy:
      - Outer transaction.atomic(): single DB commit, all-or-nothing on clean runs.
      - Inner transaction.atomic() per server: savepoint isolation.
        A DB error (e.g. out-of-range value) on server X rolls back only
        that server; the outer transaction continues for all remaining servers.

    Args:
        file        — Django UploadedFile (already validated by validate_upload)
        uploaded_by — Django User instance (optional); logged for audit trail

    Returns ProcessingResult with full counts and error details.
    """
    from optimizer.models import Server

    # Resolve a stable string identity for the uploader for all log lines.
    uploader = getattr(uploaded_by, "email", None) or getattr(uploaded_by, "username", None) or "unknown"
    file_name = getattr(file, "name", "unknown")

    result = ProcessingResult()

    logger.info(
        "FILE UPLOAD STARTED — file=%s uploaded_by=%s",
        file_name, uploader,
    )

    try:
        rows = _read_data_rows(file)
    except Exception as exc:
        logger.exception(
            "FILE UPLOAD FAILED — file=%s uploaded_by=%s reason=could not read workbook error=%s",
            file_name, uploader, exc,
        )
        result.errors.append(f"Could not read workbook: {exc}")
        return result

    # ── Collect server names present in file ──────────────────────────────────
    file_server_names: set[str] = set()
    for row in rows:
        if len(row) > COL_SERVER_NAME and row[COL_SERVER_NAME]:
            file_server_names.add(str(row[COL_SERVER_NAME]).strip())

    if not file_server_names:
        logger.info("cpu_utilisation_processor: no server names found in file")
        return result

    # Single query — only servers whose names appear in the file, tenant pre-loaded.
    db_servers = list(
        Server.objects.filter(server_name__in=file_server_names).select_related("tenant")
    )

    # Warn if multiple DB rows share the same server_name (last one wins in the map).
    seen: dict[str, int] = {}
    for s in db_servers:
        key = s.server_name.strip().lower()
        seen[key] = seen.get(key, 0) + 1
    for name, count in seen.items():
        if count > 1:
            logger.warning(
                "cpu_utilisation_processor: %d DB rows share server_name=%r — last one used",
                count, name,
            )

    server_map: dict[str, Any] = {
        s.server_name.strip().lower(): s for s in db_servers
    }

    now = timezone.now()
    servers_to_update: list[Any] = []

    # ── Outer transaction: one commit for all writes ──────────────────────────
    with transaction.atomic():

        for row_num, row in enumerate(rows, start=2):
            if len(row) < 110:
                row = row + [None] * (110 - len(row))

            server_name_raw = row[COL_SERVER_NAME]
            if not server_name_raw:
                continue

            server_name = str(server_name_raw).strip()
            server = server_map.get(server_name.lower())

            if server is None:
                logger.debug(
                    "cpu_utilisation_processor: server not found — %r (row %d)",
                    server_name, row_num,
                )
                result.skipped += 1
                continue

            tenant = server.tenant

            # Inner transaction = savepoint for this server.
            # A DB error here rolls back only this server's 12 rows
            # and leaves the outer transaction open for the next server.
            try:
                with transaction.atomic():
                    _process_server_row(server, tenant, row, row_num, now, result)
                servers_to_update.append(server)
            except Exception as exc:
                logger.warning(
                    "cpu_utilisation_processor: skipping server=%r row=%d — %s",
                    server_name, row_num, exc,
                )
                result.servers_failed += 1
                result.errors.append(f"Row {row_num} ({server_name}): {exc}")

        # ── Flush server metadata updates in one bulk statement ───────────────
        if servers_to_update:
            try:
                with transaction.atomic():
                    Server.objects.bulk_update(servers_to_update, _SERVER_UPDATE_FIELDS)
            except Exception as exc:
                # Bulk failed — fall back to individual saves so partial data is not lost.
                logger.warning(
                    "cpu_utilisation_processor: bulk_update failed (%s), falling back to individual saves",
                    exc,
                )
                for srv in servers_to_update:
                    try:
                        srv.save(update_fields=_SERVER_UPDATE_FIELDS)
                    except Exception as save_exc:
                        logger.warning(
                            "cpu_utilisation_processor: individual save failed server=%r — %s",
                            srv.server_name, save_exc,
                        )
                        result.errors.append(f"Server save failed ({srv.server_name}): {save_exc}")

    logger.info(
        "FILE UPLOAD COMPLETED — file=%s uploaded_by=%s "
        "servers_matched=%d servers_updated=%d servers_failed=%d servers_skipped=%d "
        "cpu_utilisation_inserted=%d cpu_utilisation_updated=%d errors=%d",
        file_name, uploader,
        result.servers_updated + result.servers_failed,
        result.servers_updated,
        result.servers_failed,
        result.skipped,
        result.created,
        result.updated,
        len(result.errors),
    )
    return result
