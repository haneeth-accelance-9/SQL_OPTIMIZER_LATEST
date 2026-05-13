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

Performance strategy (handles large files with 10,000+ rows):
  Phase 1 — Pure Python loop: read rows, match servers, build objects in memory.
             Zero DB queries in this phase.
  Phase 2 — Chunked DB writes (BATCH_SIZE servers per batch):
             Each batch is its own transaction.atomic() so commits happen frequently
             and no single transaction stays open long enough to drop the Azure
             PostgreSQL connection.
             cpu_utilisation: bulk_create with update_conflicts=True
               → one INSERT ... ON CONFLICT DO UPDATE per batch (~1 SQL statement
                 for BATCH_SIZE × 12 records).
             On bulk failure: fall back to individual update_or_create for that
               batch so bad rows in one batch don't lose good rows.
             server fields: bulk_update per batch; individual save fallback.

Data-safety guarantees:
  - Missing/blank/Excel-error cells → NULL (never crash).
  - One bad value in a batch triggers fallback, not data loss.
  - Skipped servers (not in DB) are counted separately.
"""
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Batch size ────────────────────────────────────────────────────────────────
# Number of matched server rows processed per DB transaction.
# 100 servers × 12 months = 1,200 records per bulk INSERT statement.
BATCH_SIZE = 100

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

PERIOD_MONTHS = [
    date(2025, 4, 1), date(2025, 5, 1), date(2025, 6, 1),
    date(2025, 7, 1), date(2025, 8, 1), date(2025, 9, 1),
    date(2025, 10, 1), date(2025, 11, 1), date(2025, 12, 1),
    date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1),
]

COL_LOGICAL_CPU_START  = 10
COL_AVG_CPU_START      = 23
COL_MAX_CPU_START      = 36
COL_PHYSICAL_RAM_START = 49
COL_AVG_MEM_START      = 62
COL_MAX_MEM_START      = 75
COL_MIN_MEM_START      = 88

_STORAGE_COLS: dict[int, tuple[int, int]] = {
    10: (101, 104),
    11: (102, 105),
}

_SERVER_UPDATE_FIELDS = [
    "boones_number", "hosting_zone", "environment", "platform",
    "is_virtual", "cluster_name", "criticality", "location",
    "installed_status_boones", "last_synced_at",
]

# Fields written to cpu_utilisation on conflict (everything except the key fields)
_CPU_UPDATE_FIELDS = [
    "logical_cpu_count", "avg_cpu_pct", "max_cpu_pct", "min_cpu_pct",
    "physical_ram_gib", "avg_free_memory_pct", "max_free_memory_pct",
    "min_free_memory_pct", "allocated_storage_gb", "used_storage_gb", "tenant",
]

_EXCEL_ERRORS = frozenset({
    "#N/A", "#REF!", "#VALUE!", "#DIV/0!",
    "#NAME?", "#NUM!", "#NULL!", "#ERROR!",
})


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class ProcessingResult:
    servers_updated: int = 0
    servers_failed: int = 0
    skipped: int = 0           # server name not found in DB
    cpu_processed: int = 0     # cpu_utilisation rows inserted or updated
    cpu_failed: int = 0        # cpu_utilisation rows that could not be saved
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [
            f"servers matched={self.servers_updated + self.servers_failed + self.skipped} "
            f"updated={self.servers_updated} failed={self.servers_failed} "
            f"skipped(not in DB)={self.skipped}",
            f"cpu_utilisation processed={self.cpu_processed} failed={self.cpu_failed}",
        ]
        if self.errors:
            parts.append(f"errors={len(self.errors)}")
        return "; ".join(parts) + "."


# ── Transform helpers ─────────────────────────────────────────────────────────

def _to_str(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _to_is_virtual(value) -> bool:
    if value is None:
        return True
    return str(value).strip().upper() != "FALSE"


def _to_cluster_name(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s == "0":
        return None
    return s


def _to_decimal(value) -> Optional[float]:
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


# ── Object builders (pure Python, no DB) ─────────────────────────────────────

def _build_cpu_objects(server, tenant, row, now_unused) -> list:
    """Build 12 CPUUtilisation instances for one server row. No DB access."""
    from optimizer.models import CPUUtilisation
    objects = []
    for month_idx, period_month in enumerate(PERIOD_MONTHS):
        storage_cols = _STORAGE_COLS.get(month_idx)
        alloc_col    = storage_cols[0] if storage_cols else None
        used_col     = storage_cols[1] if storage_cols else None
        objects.append(CPUUtilisation(
            server=server,
            period_month=period_month,
            source=CPUUtilisation.SOURCE_BOONES_PRIVATE,
            tenant=tenant,
            logical_cpu_count    = _to_int(row[COL_LOGICAL_CPU_START  + month_idx]),
            avg_cpu_pct          = _to_decimal(row[COL_AVG_CPU_START   + month_idx]),
            max_cpu_pct          = _to_decimal(row[COL_MAX_CPU_START   + month_idx]),
            min_cpu_pct          = None,
            physical_ram_gib     = _to_decimal(row[COL_PHYSICAL_RAM_START + month_idx]),
            avg_free_memory_pct  = _to_decimal(row[COL_AVG_MEM_START   + month_idx]),
            max_free_memory_pct  = _to_decimal(row[COL_MAX_MEM_START   + month_idx]),
            min_free_memory_pct  = _to_decimal(row[COL_MIN_MEM_START   + month_idx]),
            allocated_storage_gb = _to_decimal(row[alloc_col]) if alloc_col is not None else None,
            used_storage_gb      = _to_decimal(row[used_col])  if used_col  is not None else None,
        ))
    return objects


def _apply_server_fields(server, row, now) -> None:
    """Mutate server fields from the row. No DB access."""
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


# ── Batch DB writers ──────────────────────────────────────────────────────────

def _write_cpu_batch(cpu_records: list, result: "ProcessingResult") -> None:
    """
    Bulk-upsert a batch of CPUUtilisation objects.
    Falls back to individual update_or_create if bulk fails so no records are lost.
    """
    from optimizer.models import CPUUtilisation
    try:
        CPUUtilisation.objects.bulk_create(
            cpu_records,
            update_conflicts=True,
            unique_fields=["server", "period_month", "source"],
            update_fields=_CPU_UPDATE_FIELDS,
        )
        result.cpu_processed += len(cpu_records)
    except Exception as bulk_exc:
        logger.warning(
            "cpu_utilisation_processor: bulk_create failed (%s) — falling back to individual upserts",
            bulk_exc,
        )
        for rec in cpu_records:
            try:
                CPUUtilisation.objects.update_or_create(
                    server=rec.server,
                    period_month=rec.period_month,
                    source=rec.source,
                    defaults={f: getattr(rec, f) for f in _CPU_UPDATE_FIELDS},
                )
                result.cpu_processed += 1
            except Exception as exc:
                result.cpu_failed += 1
                result.errors.append(
                    f"cpu_utilisation server={rec.server.server_name} "
                    f"month={rec.period_month}: {exc}"
                )


def _write_server_batch(servers: list, result: "ProcessingResult") -> None:
    """
    Bulk-update server metadata fields.
    Falls back to individual save if bulk fails.
    """
    from optimizer.models import Server
    try:
        Server.objects.bulk_update(servers, _SERVER_UPDATE_FIELDS)
        result.servers_updated += len(servers)
    except Exception as bulk_exc:
        logger.warning(
            "cpu_utilisation_processor: server bulk_update failed (%s) — falling back to individual saves",
            bulk_exc,
        )
        for srv in servers:
            try:
                srv.save(update_fields=_SERVER_UPDATE_FIELDS)
                result.servers_updated += 1
            except Exception as exc:
                result.servers_failed += 1
                result.errors.append(f"server save failed ({srv.server_name}): {exc}")


# ── Public API ────────────────────────────────────────────────────────────────

def process_cpu_utilisation(file, uploaded_by=None) -> ProcessingResult:
    """
    Parse the validated Boones workbook, update matched Server rows, then
    upsert CPUUtilisation rows (one per server per month).

    Processes in batches of BATCH_SIZE servers. Each batch is its own
    transaction so the Azure PostgreSQL connection is never held open for
    longer than a few seconds at a time, regardless of file size.

    Args:
        file        — Django UploadedFile (already validated by validate_upload)
        uploaded_by — Django User instance (optional); logged for audit trail
    """
    from optimizer.models import Server

    uploader  = getattr(uploaded_by, "email", None) or getattr(uploaded_by, "username", None) or "unknown"
    file_name = getattr(file, "name", "unknown")
    result    = ProcessingResult()

    logger.info("FILE UPLOAD STARTED — file=%s uploaded_by=%s", file_name, uploader)

    # ── Phase 1: read file ────────────────────────────────────────────────────
    try:
        rows = _read_data_rows(file)
    except Exception as exc:
        logger.exception(
            "FILE UPLOAD FAILED — file=%s uploaded_by=%s error=%s",
            file_name, uploader, exc,
        )
        result.errors.append(f"Could not read workbook: {exc}")
        return result

    # ── Phase 2: collect server names and fetch matched servers ───────────────
    file_server_names: set[str] = set()
    for row in rows:
        if len(row) > COL_SERVER_NAME and row[COL_SERVER_NAME]:
            file_server_names.add(str(row[COL_SERVER_NAME]).strip())

    if not file_server_names:
        logger.info("FILE UPLOAD COMPLETED — file=%s uploaded_by=%s no server names found", file_name, uploader)
        return result

    # Fetch only servers that have SQL Server records in usu_demand_detail
    # OR usu_installation, and whose name appears in the uploaded file.
    # Equivalent SQL:
    #   SELECT DISTINCT s.*
    #   FROM server s
    #   WHERE s.id IN (
    #       SELECT server_id FROM usu_demand_detail  WHERE product_family = 'SQL Server'
    #       UNION
    #       SELECT server_id FROM usu_installation   WHERE product_family = 'SQL Server'
    #   )
    #   AND s.server_name IN (<file_server_names>)
    from optimizer.models import USUDemandDetail, USUInstallation
    from django.db.models import Q

    sql_server_via_demand = USUDemandDetail.objects.filter(
        product_family="SQL Server"
    ).values("server_id")

    sql_server_via_install = USUInstallation.objects.filter(
        product_family="SQL Server"
    ).values("server_id")

    server_map: dict[str, Any] = {
        s.server_name.strip().lower(): s
        for s in Server.objects.filter(
            Q(id__in=sql_server_via_demand) | Q(id__in=sql_server_via_install),
            server_name__in=file_server_names,
        ).select_related("tenant")
    }

    # Warn on duplicate server_names in DB
    seen: dict[str, int] = {}
    for s in server_map.values():
        key = s.server_name.strip().lower()
        seen[key] = seen.get(key, 0) + 1
    for name, count in seen.items():
        if count > 1:
            logger.warning(
                "cpu_utilisation_processor: %d DB rows share server_name=%r — last one used",
                count, name,
            )

    now = timezone.now()

    # ── Phase 3: pure Python — build all objects in memory ───────────────────
    # Pair each matched row with its server and pre-built objects.
    # No DB access here at all.
    matched: list[tuple[Any, list]] = []   # [(server, [CPUUtilisation × 12]), ...]

    for row in rows:
        if len(row) < 110:
            row = row + [None] * (110 - len(row))

        server_name_raw = row[COL_SERVER_NAME]
        if not server_name_raw:
            continue

        server_name = str(server_name_raw).strip()
        server = server_map.get(server_name.lower())

        if server is None:
            result.skipped += 1
            continue

        _apply_server_fields(server, row, now)
        cpu_objects = _build_cpu_objects(server, server.tenant, row, now)
        matched.append((server, cpu_objects))

    logger.info(
        "cpu_utilisation_processor: file=%s matched=%d skipped=%d — starting DB writes in batches of %d",
        file_name, len(matched), result.skipped, BATCH_SIZE,
    )

    # ── Phase 4: chunked DB writes — one transaction per batch ───────────────
    for batch_start in range(0, len(matched), BATCH_SIZE):
        batch = matched[batch_start: batch_start + BATCH_SIZE]

        servers_in_batch = [item[0] for item in batch]
        cpu_in_batch     = [obj for _, objs in batch for obj in objs]

        try:
            with transaction.atomic():
                _write_cpu_batch(cpu_in_batch, result)
                _write_server_batch(servers_in_batch, result)
        except Exception as exc:
            # Outer atomic failed (e.g. connection lost mid-batch).
            # Log it and continue — remaining batches will attempt their own connections.
            batch_end = min(batch_start + BATCH_SIZE, len(matched))
            logger.warning(
                "cpu_utilisation_processor: batch %d-%d failed — %s",
                batch_start, batch_end, exc,
            )
            result.servers_failed += len(servers_in_batch)
            result.cpu_failed     += len(cpu_in_batch)
            result.errors.append(f"Batch {batch_start}-{batch_end}: {exc}")

    logger.info(
        "FILE UPLOAD COMPLETED — file=%s uploaded_by=%s "
        "servers_matched=%d servers_updated=%d servers_failed=%d servers_skipped=%d "
        "cpu_processed=%d cpu_failed=%d errors=%d",
        file_name, uploader,
        len(matched) + result.skipped,
        result.servers_updated,
        result.servers_failed,
        result.skipped,
        result.cpu_processed,
        result.cpu_failed,
        len(result.errors),
    )
    return result
