"""
Management command: fetch_demand_data
======================================
Streams all demand-detail records from the USU API in 10 000-record chunks
and writes them to:
  1. A rolling JSON checkpoint file   (always, for auditing / replay)
  2. The usu_demand_detail DB table   (default; disable with --no-db)

Pagination strategy
-------------------
The endpoint supports offset-based pagination via $skip / $top query params:

    GET /demanddetails?product_family=MySQL&$top=10000&$skip=0
    GET /demanddetails?product_family=MySQL&$top=10000&$skip=10000
    ...

10 000 rows per request keeps each API call well within the 120 s server
timeout while processing ~7.66 M records in ~767 pages.

Resumability
------------
After each page the command writes a small JSON checkpoint file
(<output>.checkpoint).  Pass --resume to restart from the last saved
$skip position instead of from the beginning.  If the checkpoint is
stale or corrupt the command re-starts automatically.

Scheduling (django-crontab):
    Configured in settings.py -> CRONJOBS.
    Register : python manage.py crontab add
    Show     : python manage.py crontab show

Usage:
    python manage.py fetch_demand_data                    # full run, save to DB + JSON
    python manage.py fetch_demand_data --resume           # continue from checkpoint
    python manage.py fetch_demand_data --no-db            # JSON only, no DB writes
    python manage.py fetch_demand_data --dry-run          # no writes at all
    python manage.py fetch_demand_data --concurrency 4    # 4 parallel page fetches
    python manage.py fetch_demand_data --demand-count N   # override total count for ETA
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings as django_settings
from django.core.management.base import BaseCommand
from django.db import transaction
from requests.auth import HTTPBasicAuth

from optimizer.models import Server, Tenant, USUDemandDetail

logger = logging.getLogger(__name__)

# -- API constants -------------------------------------------------------------

BASE_URL        = "https://lima.bayer.cloud.usu.com"
ENDPOINT        = "/prod/index.php/api/customization/v1.0/demanddetails"
PRODUCT_FAMILY  = "MySQL"

# 10 K rows/request keeps API response times well under 120 s for 7.6 M records.
PAGE_SIZE       = 10_000

# How many ORM objects per bulk_create call (<= 65 535 PG params).
DB_BATCH_SIZE   = 500

# HTTP settings
REQUEST_TIMEOUT = 120
MAX_RETRIES     = 5
RETRY_BACKOFF   = 5   # seconds x attempt number

# Default total count -- used for ETA; updated from API response if possible.
DEFAULT_DEMAND_COUNT = 7_659_558


# -- Type helpers --------------------------------------------------------------

def _str(v, max_len: int | None = None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return (s[:max_len] if max_len else s) or None


def _bool(v) -> bool | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("1", "true", "yes"):
        return True
    if s in ("0", "false", "no"):
        return False
    return None


def _decimal(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        return None


# -- HTTP session --------------------------------------------------------------

def _build_session(username: str, password: str) -> requests.Session:
    s = requests.Session()
    s.auth = HTTPBasicAuth(username, password)
    s.headers["Accept"] = "application/json"
    return s


def _fetch_page_with_retry(
    session: requests.Session,
    skip: int,
    stdout,
) -> tuple[list[dict], int | None]:
    """
    Fetch exactly PAGE_SIZE records starting at $skip.

    Returns (records, total_count_from_api).
    total_count is read from the first page's metadata and may be None on later pages.
    """
    url = BASE_URL + ENDPOINT
    params = {
        "product_family": PRODUCT_FAMILY,
        "$top": PAGE_SIZE,
        "$skip": skip,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            records = data.get("data") or []
            # Extract total count from metadata if present
            meta = data.get("metadata") or {}
            total = meta.get("count") or meta.get("total") or None
            if total:
                try:
                    total = int(total)
                except (ValueError, TypeError):
                    total = None
            return records, total
        except Exception as exc:
            if attempt == MAX_RETRIES:
                logger.error("Page $skip=%d failed after %d retries: %s", skip, MAX_RETRIES, exc)
                raise
            wait = attempt * RETRY_BACKOFF
            stdout.write(
                f"    [WARN] $skip={skip} attempt {attempt}/{MAX_RETRIES}: {exc} "
                f"-- retrying in {wait}s"
            )
            time.sleep(wait)


# -- Checkpoint helpers --------------------------------------------------------

def _checkpoint_path(output_file: str) -> str:
    return output_file + ".checkpoint"


def _read_checkpoint(output_file: str) -> int:
    """Return the last successfully processed $skip value, or 0 if none."""
    cp = _checkpoint_path(output_file)
    if not os.path.exists(cp):
        return 0
    try:
        with open(cp) as f:
            data = json.load(f)
        skip = int(data.get("next_skip", 0))
        logger.info("Resuming from checkpoint: next_skip=%d", skip)
        return skip
    except Exception as e:
        logger.warning("Checkpoint unreadable (%s) -- starting from scratch", e)
        return 0


def _write_checkpoint(output_file: str, next_skip: int, total_written: int) -> None:
    cp = {
        "next_skip": next_skip,
        "total_written": total_written,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(_checkpoint_path(output_file), "w") as f:
        json.dump(cp, f, indent=2)


# -- Tenant / Server resolution ------------------------------------------------

def _get_or_create_tenant(name: str) -> Tenant:
    tenant, created = Tenant.objects.get_or_create(
        name=name,
        defaults={"description": "Auto-created by fetch_demand_data", "is_active": True},
    )
    if created:
        logger.info("Created tenant: %s", name)
    return tenant


def _resolve_server(tenant: Tenant, raw: dict) -> Server:
    usu_key     = _str(raw.get("devices_device_key"), 512)
    server_name = _str(raw.get("devices_device_name"), 255) or "unknown"
    environment = _str(raw.get("device_purposes_name"), 80)
    hosting     = _str(raw.get("device_man_systems_name"), 120)
    virt_type   = _str(raw.get("device_types_virt_type"), 80)
    server_key  = usu_key or f"{server_name}|{environment or ''}|{hosting or ''}".lower()

    server, _ = Server.objects.get_or_create(
        tenant=tenant,
        server_key=server_key,
        defaults={
            "server_name":        server_name,
            "usu_device_key":     usu_key,
            "hosting_zone":       hosting,
            "environment":        environment,
            "device_type":        _str(raw.get("device_types_name"), 120),
            "is_virtual":         True if virt_type else None,
            "is_cloud_device":    _bool(raw.get("dt_is_cloud_device_type")),
            "cloud_provider":     _str(raw.get("pdt_cloud_provider_type"), 80),
            "topology_type":      _str(raw.get("topology_type"), 80),
            "cluster_device_key": _str(raw.get("cdev_device_key"), 512),
            "cluster_name":       _str(raw.get("center_dev_dev_name"), 255),
            "source_systems":     ["usu"],
        },
    )
    return server


# -- DB persistence for one chunk ----------------------------------------------

def _save_chunk_to_db(tenant: Tenant, records: list[dict]) -> int:
    """
    Resolve servers + bulk_create USUDemandDetail rows for a single 10 K chunk.
    Returns the number of rows inserted.
    """
    objs:    list[USUDemandDetail] = []
    written: int = 0

    for raw in records:
        try:
            server = _resolve_server(tenant, raw)
        except Exception as exc:
            logger.warning("Server resolution failed for record -- skipped: %s", exc)
            continue

        objs.append(USUDemandDetail(
            tenant              = tenant,
            server              = server,
            manufacturer        = _str(raw.get("man_name"), 120),
            product_family      = _str(raw.get("pf_description"), 120),
            product_description = _str(raw.get("products_description"), 255),
            product_edition     = _str(raw.get("products_edition"), 120),
            eff_quantity        = _decimal(raw.get("imec_eff_quantity")),
            no_license_required = _bool(raw.get("calc_no_license_required_flag")),
            device_purpose      = _str(raw.get("device_purposes_name"), 80),
            topology_type       = _str(raw.get("topology_type"), 80),
            cpu_core_count      = _decimal(raw.get("devices_cpu_core_count")),
            virt_type           = _str(raw.get("device_types_virt_type"), 80),
            is_cloud_device     = _bool(raw.get("dt_is_cloud_device_type")),
            cloud_provider      = _str(raw.get("pdt_cloud_provider_type"), 80),
            cpu_thread_count    = _decimal(raw.get("devices_cpu_thread_count")),
            hyper_threading_factor = _decimal(raw.get("devices_hyper_threading_factor")),
        ))

        if len(objs) >= DB_BATCH_SIZE:
            with transaction.atomic():
                USUDemandDetail.objects.bulk_create(objs, ignore_conflicts=True)
            written += len(objs)
            objs = []

    if objs:
        with transaction.atomic():
            USUDemandDetail.objects.bulk_create(objs, ignore_conflicts=True)
        written += len(objs)

    return written


# -- JSON output helpers -------------------------------------------------------

def _append_to_json(output_file: str, records: list[dict], first_chunk: bool) -> None:
    """
    Stream-append records to a JSON array file without loading the whole file.
    On first_chunk the file is (re)created with '['; subsequent calls append.
    """
    mode = "w" if first_chunk else "a"
    with open(output_file, mode, encoding="utf-8") as f:
        if first_chunk:
            f.write("[\n")
        else:
            f.write(",\n")
        f.write(",\n".join(json.dumps(r, ensure_ascii=False) for r in records))


def _close_json(output_file: str) -> None:
    """Write the closing bracket to the JSON array file."""
    with open(output_file, "a", encoding="utf-8") as f:
        f.write("\n]\n")


# -- Main command --------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Stream all USU demand-detail records (~7.66 M) in 10 000-record chunks "
        "to usu_demand_detail DB table and a JSON checkpoint file. "
        "Safe to interrupt and resume with --resume."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", default=None,
            help="Path to output JSON file. Default: <BASE_DIR>/demand_data.json",
        )
        parser.add_argument(
            "--demand-count", type=int, default=DEFAULT_DEMAND_COUNT,
            help=f"Expected total record count (ETA only). Default: {DEFAULT_DEMAND_COUNT:,}",
        )
        parser.add_argument(
            "--tenant", default="default",
            help="Tenant name for DB rows. Default: 'default'",
        )
        parser.add_argument(
            "--concurrency", type=int, default=1,
            help=(
                "Number of parallel page-fetch workers (1 = sequential). "
                "Use 2-4 for faster throughput if the API allows it. Default: 1"
            ),
        )
        parser.add_argument(
            "--resume", action="store_true",
            help="Resume from the last checkpoint instead of starting over.",
        )
        parser.add_argument(
            "--no-db", action="store_true",
            help="Skip all DB writes -- only write the JSON output file.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Fetch from API but do not write to DB or JSON.",
        )

    # -- Entry point -----------------------------------------------------------

    def handle(self, *args, **options):
        output_file  = options["output"] or os.path.join(
            getattr(django_settings, "BASE_DIR", "."), "demand_data.json"
        )
        demand_count = options["demand_count"]
        tenant_name  = options["tenant"]
        concurrency  = max(1, min(options["concurrency"], 8))
        resume       = options["resume"]
        no_db        = options["no_db"]
        dry_run      = options["dry_run"]

        username = getattr(django_settings, "USU_API_USERNAME", "myusudata")
        password = getattr(django_settings, "USU_API_PASSWORD", "test123Usu")

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n============================================================\n"
            "  USU Demand-Detail Streaming Sync\n"
            "============================================================"
        ))
        self.stdout.write(f"  Output     : {output_file}")
        self.stdout.write(f"  Concurrency: {concurrency} worker(s)")
        self.stdout.write(f"  Page size  : {PAGE_SIZE:,} records/page")
        self.stdout.write(f"  Expected   : {demand_count:,} records")
        if dry_run:
            self.stdout.write(self.style.WARNING("  [!] DRY RUN -- no DB or file writes"))
        elif no_db:
            self.stdout.write(self.style.WARNING("  [!] --no-db -- skipping DB writes"))

        # Determine start offset
        start_skip = 0
        if resume and not dry_run:
            start_skip = _read_checkpoint(output_file)
            if start_skip:
                self.stdout.write(
                    self.style.WARNING(f"  Resuming from $skip={start_skip:,}")
                )

        # Resolve tenant and wipe stale rows only on a fresh (non-resume) run
        tenant = None
        if not dry_run and not no_db:
            tenant = _get_or_create_tenant(tenant_name)
            if start_skip == 0:
                deleted, _ = USUDemandDetail.objects.filter(
                    tenant=tenant, product_family=PRODUCT_FAMILY
                ).delete()
                self.stdout.write(
                    f"  Deleted {deleted:,} stale rows from usu_demand_detail"
                )

        session      = _build_session(username, password)
        t_start      = time.time()
        total_fetched = 0
        total_written = 0
        page_num     = (start_skip // PAGE_SIZE) + 1
        is_first_chunk = (start_skip == 0)

        # Build list of $skip values to fetch
        # We do not know the exact total until the first response, so we
        # generate offsets up to demand_count and stop when an empty page arrives.
        skip_values = list(range(start_skip, demand_count, PAGE_SIZE))

        self.stdout.write(
            f"  Pages to fetch: {len(skip_values):,} "
            f"($skip {start_skip:,} -> {skip_values[-1]:,})\n"
        )

        if concurrency == 1:
            # -- Sequential path -----------------------------------------------
            for skip in skip_values:
                page_start = time.time()
                try:
                    records, api_total = _fetch_page_with_retry(session, skip, self.stdout)
                except Exception as exc:
                    self.stderr.write(
                        self.style.ERROR(
                            f"  FATAL: page $skip={skip:,} failed -- "
                            f"progress saved up to $skip={skip:,}. Error: {exc}"
                        )
                    )
                    break

                if not records:
                    self.stdout.write("  API returned 0 records -- end of data.")
                    break

                # Update total count from API if available
                if api_total and api_total != demand_count:
                    demand_count = api_total

                total_fetched += len(records)

                # JSON write
                if not dry_run:
                    _append_to_json(output_file, records, first_chunk=is_first_chunk)
                    is_first_chunk = False

                # DB write
                db_written = 0
                if not dry_run and not no_db and tenant:
                    db_written = _save_chunk_to_db(tenant, records)
                    total_written += db_written

                # Checkpoint
                next_skip = skip + PAGE_SIZE
                if not dry_run:
                    _write_checkpoint(output_file, next_skip, total_fetched)

                # Progress line
                elapsed  = time.time() - t_start
                rate     = total_fetched / elapsed if elapsed else 0
                eta_sec  = (demand_count - total_fetched) / rate if rate else 0
                page_sec = time.time() - page_start
                self.stdout.write(
                    f"  Page {page_num:>4} | $skip={skip:>9,} | "
                    f"got {len(records):>6,} | "
                    f"total {total_fetched:>9,}/{demand_count:,} | "
                    f"DB +{db_written:>6,} | "
                    f"{rate:>7,.0f} rec/s | "
                    f"ETA {int(eta_sec // 60)}m {int(eta_sec % 60)}s | "
                    f"{page_sec:.1f}s"
                )

                page_num += 1

                if len(records) < PAGE_SIZE:
                    # Last partial page -- no more data
                    break

                time.sleep(0.2)   # polite pause between requests

        else:
            # -- Concurrent path (N workers) -----------------------------------
            # Workers fetch pages; results are collected in order and written
            # sequentially to preserve JSON array integrity and checkpoint order.
            self.stdout.write(f"  Using {concurrency} concurrent fetch workers\n")

            def _fetch(skip: int) -> tuple[int, list[dict], int | None]:
                recs, total = _fetch_page_with_retry(session, skip, self.stdout)
                return skip, recs, total

            # Process in windows of `concurrency` pages at a time to keep
            # memory bounded and maintain sequential JSON/checkpoint writes.
            i = 0
            stop = False
            while i < len(skip_values) and not stop:
                window = skip_values[i : i + concurrency]
                results: dict[int, tuple[list[dict], int | None]] = {}

                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures = {pool.submit(_fetch, sk): sk for sk in window}
                    for future in as_completed(futures):
                        sk = futures[future]
                        try:
                            skip_ret, recs, api_total = future.result()
                            results[skip_ret] = (recs, api_total)
                        except Exception as exc:
                            self.stderr.write(
                                self.style.ERROR(f"  Worker $skip={sk:,} failed: {exc}")
                            )
                            results[sk] = ([], None)

                # Write results in ascending $skip order for correctness
                for sk in sorted(window):
                    recs, api_total = results.get(sk, ([], None))

                    if not recs:
                        self.stdout.write(f"  $skip={sk:,}: 0 records -- stopping.")
                        stop = True
                        break

                    if api_total and api_total != demand_count:
                        demand_count = api_total

                    total_fetched += len(recs)

                    if not dry_run:
                        _append_to_json(output_file, recs, first_chunk=is_first_chunk)
                        is_first_chunk = False

                    db_written = 0
                    if not dry_run and not no_db and tenant:
                        db_written = _save_chunk_to_db(tenant, recs)
                        total_written += db_written

                    next_skip = sk + PAGE_SIZE
                    if not dry_run:
                        _write_checkpoint(output_file, next_skip, total_fetched)

                    elapsed = time.time() - t_start
                    rate    = total_fetched / elapsed if elapsed else 0
                    eta_sec = (demand_count - total_fetched) / rate if rate else 0
                    self.stdout.write(
                        f"  Page {page_num:>4} | $skip={sk:>9,} | "
                        f"got {len(recs):>6,} | "
                        f"total {total_fetched:>9,}/{demand_count:,} | "
                        f"DB +{db_written:>6,} | "
                        f"{rate:>7,.0f} rec/s | "
                        f"ETA {int(eta_sec // 60)}m {int(eta_sec % 60)}s"
                    )
                    page_num += 1

                    if len(recs) < PAGE_SIZE:
                        stop = True
                        break

                i += concurrency

        # Close JSON array
        if not dry_run and not is_first_chunk:
            _close_json(output_file)

        total_time = time.time() - t_start
        self.stdout.write(self.style.SUCCESS(
            f"\n  Done. Fetched: {total_fetched:,} | "
            f"DB written: {total_written:,} | "
            f"Time: {int(total_time // 60)}m {int(total_time % 60)}s\n"
        ))
        logger.info(
            "fetch_demand_data completed: fetched=%d db_written=%d time=%.1fs",
            total_fetched, total_written, total_time,
        )
