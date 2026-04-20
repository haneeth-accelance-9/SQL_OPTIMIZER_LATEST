"""
Management command: fetch_usu_data
===================================
Pulls MySQL installation and demand-detail records from the USU API
and stores them in the correct PostgreSQL tables:

  API endpoint          → Django model      → DB table
  ─────────────────────────────────────────────────────
  /installations        → USUInstallation   → usu_installation
  /demanddetails        → USUDemandDetail   → usu_demand_detail

Both endpoints also create/update the parent Server row so that
every installation/demand record has a valid FK before insertion.

Record volumes:
  - Installations  : ~36 182   → 2 pages   (page size 35 000), sequential
  - Demand Details : ~7 703 892 → ~309 pages (page size 25 000), parallel

Scheduling — django-crontab (works on Windows, Linux, Mac):
    Configured in settings.py → CRONJOBS (runs every Monday at 02:00).
    Register : python manage.py crontab add
    Remove   : python manage.py crontab remove
    Show     : python manage.py crontab show

Settings (read from .env via settings.py):
    USU_API_BASE_URL   — default: https://lima.bayer.cloud.usu.com
    USU_API_USERNAME   — default: myusudata
    USU_API_PASSWORD   — default: test123Usu

Usage:
    python manage.py fetch_usu_data               # full sync
    python manage.py fetch_usu_data --dry-run     # fetch but skip DB writes
    python manage.py fetch_usu_data --skip-demand # installations only
    python manage.py fetch_usu_data --skip-install# demand details only
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings as django_settings
from django.core.management.base import BaseCommand
from django.db import transaction
from requests.auth import HTTPBasicAuth

from optimizer.models import Server, Tenant, USUDemandDetail, USUInstallation

logger = logging.getLogger(__name__)

# ── API endpoints ─────────────────────────────────────────────────────────────

BASE_URL           = "https://lima.bayer.cloud.usu.com"
INSTALL_ENDPOINT   = "/prod/index.php/api/customization/v1.0/installations"
DEMAND_ENDPOINT    = "/prod/index.php/api/customization/v1.0/demanddetails"
PRODUCT_FAMILY     = "MySQL"

# Installations: ~36 182 records. 35 000 per page = 2 pages — sequential is fine.
INSTALL_PAGE_SIZE  = 35_000

# Demand details: ~7.7 M records. 25 000 per page = ~309 pages.
# Fetched in parallel using DEMAND_WORKERS threads to finish in minutes, not hours.
DEMAND_PAGE_SIZE   = 25_000
DEMAND_WORKERS     = 5        # concurrent HTTP workers for demand pages

# How many ORM objects to pass to bulk_create in a single DB call.
# 500 rows × ~20 fields is safely under PostgreSQL's 65 535 parameter limit.
DB_BATCH_SIZE      = 500

# Network settings
REQUEST_TIMEOUT    = 120   # seconds per HTTP request
MAX_RETRIES        = 4     # retries on transient failures
RETRY_BACKOFF      = 5     # seconds — multiplied by attempt number for back-off


# ── Type-coercion helpers ─────────────────────────────────────────────────────

def _str(value, max_len: int | None = None) -> str | None:
    """Strip and truncate a string field. Returns None for blank/null values."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len] if max_len else s


def _bool(value) -> bool | None:
    """
    Convert API boolean representations to Python bool.
    The API returns "0"/"1" strings for flag fields (e.g. calc_no_license_required_flag).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("1", "true", "yes"):
        return True
    if s in ("0", "false", "no"):
        return False
    return None


def _decimal(value) -> Decimal | None:
    """Safely parse a decimal/float string. Returns None on failure."""
    if value is None:
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _int(value) -> int | None:
    """Safely parse an integer. Returns None on failure."""
    if value is None:
        return None
    try:
        return int(Decimal(str(value).strip()))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _date(value) -> date | None:
    """
    Parse date strings from the API. Handles both:
      - 'YYYY-MM-DD'              (inventory_date)
      - 'YYYY-MM-DD HH:MM:SS'    (creation_date)
    Returns None for blank / unparseable values.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (ValueError, TypeError):
        return None


def _beat_ids(value) -> list[str]:
    """
    Split a newline-separated BEAT ID string into a clean list.
    Example: "BEAT00423746\\nBEAT04016489" → ["BEAT00423746", "BEAT04016489"]
    Stored in Server.beat_ids (ArrayField).
    """
    if not value:
        return []
    return [b.strip() for b in str(value).split("\n") if b.strip()]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _build_session(username: str, password: str) -> requests.Session:
    """
    Create a reusable requests.Session with Basic Auth pre-configured.
    A single session reuses the underlying TCP connection across pages
    (HTTP keep-alive), which significantly reduces per-request overhead.
    """
    session = requests.Session()
    session.auth = HTTPBasicAuth(username, password)
    session.headers.update({"Accept": "application/json"})
    return session


def _fetch_page(session: requests.Session, url: str, params: dict | None = None) -> dict:
    """
    GET a single API page with exponential-ish back-off retry.

    Retries up to MAX_RETRIES times on any exception (network timeout,
    5xx server error, JSON decode error, etc.).
    Raises the last exception if all retries are exhausted.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = attempt * RETRY_BACKOFF
            logger.warning(
                "Fetch failed (attempt %d/%d) for %s: %s — retrying in %ds",
                attempt, MAX_RETRIES, url, exc, wait,
            )
            time.sleep(wait)


# ── Tenant / Server resolution ────────────────────────────────────────────────

def _get_or_create_tenant(name: str) -> Tenant:
    """
    Return the Tenant row for the given name, creating it if absent.
    All USU records are tied to this tenant during the weekly sync.
    """
    tenant, created = Tenant.objects.get_or_create(
        name=name,
        defaults={"description": "Auto-created by fetch_usu_data", "is_active": True},
    )
    if created:
        logger.info("Created tenant: %s", name)
    return tenant


def _resolve_server_from_installation(tenant: Tenant, raw: dict) -> Server:
    """
    Find or create the Server row using fields from an installations API record.

    Field mapping (API → Server model):
        devices_device_key       → server_key, usu_device_key
        devices_device_name      → server_name
        device_man_systems_name  → hosting_zone
        device_statuses_name     → installed_status_usu
        device_types_name        → device_type
        dt_is_cloud_device_type  → is_cloud_device
        pdt_cloud_provider_type  → cloud_provider
        loc_countries_name       → country
        loc_regions_name         → region
        locations_name           → location
        topology_type            → topology_type
        cdev_device_key          → cluster_device_key
        beatid                   → beat_ids  (split on \\n)
    """
    usu_key     = _str(raw.get("devices_device_key"), 512)
    server_name = _str(raw.get("devices_device_name"), 255) or "unknown"
    environment = _str(raw.get("device_purposes_name"), 80)
    hosting     = _str(raw.get("device_man_systems_name"), 120)

    # Canonical cross-source key: prefer the USU device key
    server_key = usu_key or f"{server_name}|{environment or ''}|{hosting or ''}".lower()

    server, _ = Server.objects.get_or_create(
        tenant=tenant,
        server_key=server_key,
        defaults={
            "server_name":          server_name,
            "usu_device_key":       usu_key,
            "hosting_zone":         hosting,
            "environment":          environment,
            "device_type":          _str(raw.get("device_types_name"), 120),
            "is_cloud_device":      _bool(raw.get("dt_is_cloud_device_type")),
            "cloud_provider":       _str(raw.get("pdt_cloud_provider_type"), 80),
            "country":              _str(raw.get("loc_countries_name"), 80),
            "region":               _str(raw.get("loc_regions_name"), 80),
            "location":             _str(raw.get("locations_name"), 120),
            "topology_type":        _str(raw.get("topology_type"), 80),
            "cluster_device_key":   _str(raw.get("cdev_device_key"), 512),
            "installed_status_usu": _str(raw.get("device_statuses_name"), 80),
            "beat_ids":             _beat_ids(raw.get("beatid")),
            "source_systems":       ["usu"],
        },
    )
    return server


def _resolve_server_from_demand(tenant: Tenant, raw: dict) -> Server:
    """
    Find or create the Server row using fields from a demanddetails API record.

    Field mapping (API → Server model):
        devices_device_key       → server_key, usu_device_key
        devices_device_name      → server_name
        device_man_systems_name  → hosting_zone
        device_purposes_name     → environment
        device_types_name        → device_type
        device_types_virt_type   → (used to set is_virtual)
        dt_is_cloud_device_type  → is_cloud_device
        pdt_cloud_provider_type  → cloud_provider
        topology_type            → topology_type
        cdev_device_key          → cluster_device_key
        center_dev_dev_name      → cluster_name
    """
    usu_key     = _str(raw.get("devices_device_key"), 512)
    server_name = _str(raw.get("devices_device_name"), 255) or "unknown"
    environment = _str(raw.get("device_purposes_name"), 80)
    hosting     = _str(raw.get("device_man_systems_name"), 120)
    virt_type   = _str(raw.get("device_types_virt_type"), 80)

    server_key = usu_key or f"{server_name}|{environment or ''}|{hosting or ''}".lower()

    server, _ = Server.objects.get_or_create(
        tenant=tenant,
        server_key=server_key,
        defaults={
            "server_name":        server_name,
            "usu_device_key":     usu_key,
            "hosting_zone":       hosting,
            "environment":        environment,
            "device_type":        _str(raw.get("device_types_name"), 120),
            # A VMware/Partition virt_type means it is a virtual machine
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


# ── Installations: fetch ──────────────────────────────────────────────────────

def fetch_installations(session: requests.Session, stdout) -> list[dict]:
    """
    Sequentially page through the installations endpoint until exhausted.

    Pagination: follow metadata.pagination.next_page_uri returned by each response.
    With ~36 182 records at 35 000/page this completes in 2 HTTP calls.
    """
    all_records = []
    params = {"product_family": PRODUCT_FAMILY, "$top": INSTALL_PAGE_SIZE, "$skip": 0}
    url    = BASE_URL + INSTALL_ENDPOINT
    page   = 1

    stdout.write("-- Fetching Installations ------------------------------")

    while url:
        t0   = time.time()
        data = _fetch_page(session, url, params)

        records      = data.get("data") or []
        next_page_uri = data.get("metadata", {}).get("pagination", {}).get("next_page_uri")

        all_records.extend(records)
        stdout.write(
            f"  Page {page} | got {len(records):,} | "
            f"total {len(all_records):,} | {time.time() - t0:.1f}s"
        )

        # next_page_uri is a full relative path — build the next absolute URL
        if next_page_uri and len(records) == INSTALL_PAGE_SIZE:
            url    = BASE_URL + next_page_uri
            params = None   # params are embedded in next_page_uri
            page  += 1
            time.sleep(0.5)
        else:
            break   # last page or no more data

    stdout.write(f"  Installations total: {len(all_records):,}")
    return all_records


# ── Demand details: concurrent fetch ─────────────────────────────────────────

def _fetch_demand_page_worker(
    session: requests.Session, skip: int
) -> tuple[int, list[dict]]:
    """
    Thread worker: fetch one demand-detail page at the given $skip offset.
    Returns (skip, records) so the caller can sort results back into order.
    """
    params = {"product_family": PRODUCT_FAMILY, "$top": DEMAND_PAGE_SIZE, "$skip": skip}
    data   = _fetch_page(session, BASE_URL + DEMAND_ENDPOINT, params)
    return skip, data.get("data") or []


def fetch_demand_details(
    session: requests.Session, total_count: int, stdout
) -> list[dict]:
    """
    Fetch all demand-detail records using a thread pool for parallel HTTP requests.

    Why parallel?
      309 pages × ~3 s/page = ~15 min sequentially.
      With 5 concurrent workers it drops to ~3–4 min.

    Strategy:
      1. Pre-compute every $skip offset from 0 to total_count.
      2. Submit all as futures to ThreadPoolExecutor.
      3. Collect results as they complete (as_completed = whichever finishes first).
      4. Sort by skip offset at the end to restore chronological order.
    """
    stdout.write("-- Fetching Demand Details (parallel) ------------------")

    offsets      = list(range(0, total_count + DEMAND_PAGE_SIZE, DEMAND_PAGE_SIZE))
    total_pages  = len(offsets)
    page_results = {}   # skip → list[dict]
    failed       = []
    done         = 0
    t_start      = time.time()

    stdout.write(
        f"  {total_count:,} records | {DEMAND_PAGE_SIZE:,}/page "
        f"| {total_pages} pages | {DEMAND_WORKERS} workers"
    )

    with ThreadPoolExecutor(max_workers=DEMAND_WORKERS) as pool:
        # Submit every page as an independent future
        futures = {
            pool.submit(_fetch_demand_page_worker, session, skip): skip
            for skip in offsets
        }

        for future in as_completed(futures):
            skip = futures[future]
            try:
                skip_val, records = future.result()
                page_results[skip_val] = records
                done += 1

                # Progress log every 10 completed pages to avoid console flood
                if done % 10 == 0 or done == total_pages:
                    elapsed  = time.time() - t_start
                    fetched  = sum(len(v) for v in page_results.values())
                    rate     = fetched / elapsed if elapsed else 0
                    eta_sec  = (total_count - fetched) / rate if rate else 0
                    stdout.write(
                        f"  Page {done}/{total_pages} | "
                        f"fetched {fetched:,} | "
                        f"{rate:,.0f} rec/s | "
                        f"ETA {int(eta_sec // 60)}m {int(eta_sec % 60)}s"
                    )
            except Exception as exc:
                logger.error("Demand page skip=%d failed: %s", skip, exc)
                failed.append(skip)

    if failed:
        stdout.write(
            f"  WARNING: {len(failed)} pages could not be fetched "
            f"(offsets: {failed[:5]}{'...' if len(failed) > 5 else ''})"
        )

    # Merge pages in ascending skip order → preserves natural record order
    all_records = []
    for skip in sorted(page_results):
        all_records.extend(page_results[skip])

    elapsed = time.time() - t_start
    stdout.write(
        f"  Demand total: {len(all_records):,} records "
        f"in {int(elapsed // 60)}m {int(elapsed % 60)}s"
    )
    return all_records


# ── DB persistence ────────────────────────────────────────────────────────────

def save_installations(
    tenant: Tenant, records: list[dict], dry_run: bool, stdout
) -> None:
    """
    Persist installation records into the usu_installation table.

    Full-refresh strategy:
      1. DELETE all existing rows for this product_family + tenant.
      2. For each API record: resolve/create the parent Server row.
      3. Build USUInstallation objects in memory.
      4. bulk_create in DB_BATCH_SIZE chunks inside atomic transactions.

    Field mapping (API → USUInstallation):
        manufacturers_name           → manufacturer
        product_families_description → product_family
        products_description         → product_description
        products_edition             → product_edition
        license_metrics_description  → license_metric
        calc_license_metrics_me      → calc_license_metric
        inv_statuses_name            → inv_status_name
        inv_statuses_std_name        → inv_status_std_name
        ignore_usage_flag            → ignore_usage
        ignore_usage_reason          → ignore_usage_reason
        no_license_required_flag     → no_license_required
        device_statuses_name         → device_status
        devices_cpu_socket_count     → cpu_socket_count
        devices_cpu_core_count       → cpu_core_count
        devices_hyper_threading_factor → hyper_threading_factor
        topology_type                → topology_type
        source_key                   → source_key
        devices_inventory_date       → inventory_date
        creation_date                → creation_date
    """
    if dry_run:
        stdout.write(f"  [dry-run] Would write {len(records):,} installations — skipped")
        return

    stdout.write(f"  Writing {len(records):,} installations -> usu_installation ...")
    t0 = time.time()

    # Wipe stale rows for this product family so weekly re-runs stay clean
    deleted, _ = USUInstallation.objects.filter(
        tenant=tenant, product_family=PRODUCT_FAMILY
    ).delete()
    stdout.write(f"  Deleted {deleted:,} stale rows from usu_installation")

    objs    = []
    written = 0

    for raw in records:
        # Resolve (or create) the server this installation belongs to
        server = _resolve_server_from_installation(tenant, raw)

        # Map every API field to its corresponding model field
        objs.append(USUInstallation(
            tenant              = tenant,
            server              = server,
            manufacturer        = _str(raw.get("manufacturers_name"), 120),
            product_family      = _str(raw.get("product_families_description"), 120),
            product_description = _str(raw.get("products_description"), 255),
            product_edition     = _str(raw.get("products_edition"), 120),
            license_metric      = _str(raw.get("license_metrics_description"), 120),
            calc_license_metric = _str(raw.get("calc_license_metrics_me"), 80),
            inv_status_name     = _str(raw.get("inv_statuses_name"), 120),
            inv_status_std_name = _str(raw.get("inv_statuses_std_name"), 80),
            ignore_usage        = _bool(raw.get("ignore_usage_flag")),
            ignore_usage_reason = _str(raw.get("ignore_usage_reason"), 255),
            no_license_required = _bool(raw.get("no_license_required_flag")),
            device_status       = _str(raw.get("device_statuses_name"), 80),
            cpu_socket_count    = _int(raw.get("devices_cpu_socket_count")),
            cpu_core_count      = _decimal(raw.get("devices_cpu_core_count")),
            hyper_threading_factor = _decimal(raw.get("devices_hyper_threading_factor")),
            topology_type       = _str(raw.get("topology_type"), 80),
            source_key          = _str(raw.get("source_key"), 255),
            inventory_date      = _date(raw.get("devices_inventory_date")),
            creation_date       = _date(raw.get("creation_date")),
        ))

        # Flush batch to DB when it's full — avoids excessive memory use
        if len(objs) >= DB_BATCH_SIZE:
            with transaction.atomic():
                USUInstallation.objects.bulk_create(objs, ignore_conflicts=True)
            written += len(objs)
            objs = []

    # Final partial batch
    if objs:
        with transaction.atomic():
            USUInstallation.objects.bulk_create(objs, ignore_conflicts=True)
        written += len(objs)

    stdout.write(
        f"  OK: usu_installation: {written:,} rows saved in {time.time() - t0:.1f}s"
    )


def save_demand_details(
    tenant: Tenant, records: list[dict], dry_run: bool, stdout
) -> None:
    """
    Persist demand-detail records into the usu_demand_detail table.

    Same full-refresh + bulk_create strategy as save_installations.
    For 7.7 M rows, progress is logged every 100 000 inserts.

    Field mapping (API → USUDemandDetail):
        man_name                     → manufacturer
        pf_description               → product_family
        products_description         → product_description
        products_edition             → product_edition
        imec_eff_quantity            → eff_quantity
        calc_no_license_required_flag→ no_license_required
        device_purposes_name         → device_purpose
        topology_type                → topology_type
        devices_cpu_core_count       → cpu_core_count
        device_types_virt_type       → virt_type
        dt_is_cloud_device_type      → is_cloud_device
        pdt_cloud_provider_type      → cloud_provider
        devices_cpu_thread_count     → cpu_thread_count
        devices_hyper_threading_factor → hyper_threading_factor
    """
    if dry_run:
        stdout.write(f"  [dry-run] Would write {len(records):,} demand rows — skipped")
        return

    stdout.write(f"  Writing {len(records):,} demand details -> usu_demand_detail ...")
    t0 = time.time()

    # Wipe stale rows for this product family
    deleted, _ = USUDemandDetail.objects.filter(
        tenant=tenant, product_family=PRODUCT_FAMILY
    ).delete()
    stdout.write(f"  Deleted {deleted:,} stale rows from usu_demand_detail")

    objs    = []
    written = 0

    for raw in records:
        server = _resolve_server_from_demand(tenant, raw)

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

            # Log progress every 100 000 rows — important for 7.7 M record runs
            if written % 100_000 == 0:
                elapsed = time.time() - t0
                rate    = written / elapsed if elapsed else 0
                eta     = (len(records) - written) / rate if rate else 0
                stdout.write(
                    f"  Progress: {written:,}/{len(records):,} | "
                    f"{rate:,.0f} rows/s | "
                    f"ETA {int(eta // 60)}m {int(eta % 60)}s"
                )

    if objs:
        with transaction.atomic():
            USUDemandDetail.objects.bulk_create(objs, ignore_conflicts=True)
        written += len(objs)

    elapsed = time.time() - t0
    stdout.write(
        f"  OK: usu_demand_detail: {written:,} rows saved "
        f"in {int(elapsed // 60)}m {int(elapsed % 60)}s"
    )


# ── Management command entry point ────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Weekly USU sync: fetch MySQL installations (~36K) and demand details (~7.7M) "
        "and store them in usu_installation and usu_demand_detail tables."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Fetch from API but skip all database writes.",
        )
        parser.add_argument(
            "--skip-install", action="store_true",
            help="Skip installations — only fetch demand details.",
        )
        parser.add_argument(
            "--skip-demand", action="store_true",
            help="Skip demand details — only fetch installations.",
        )
        parser.add_argument(
            "--demand-count", type=int, default=7_703_892,
            help="Known total demand-detail count (pre-computes page offsets). Default: 7703892",
        )
        parser.add_argument(
            "--tenant", default="default",
            help="Tenant name for all ingested records. Default: 'default'",
        )

    def handle(self, *_args, **options):
        dry_run      = options["dry_run"]
        skip_install = options["skip_install"]
        skip_demand  = options["skip_demand"]
        demand_count = options["demand_count"]
        tenant_name  = options["tenant"]
        run_start    = time.time()

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n==============================================\n"
            "  USU Weekly Data Sync\n"
            "=============================================="
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING("  [!] DRY RUN -- no DB writes"))

        # ── Step 1: Read credentials from Django settings (loaded from .env) ──
        username = getattr(django_settings, "USU_API_USERNAME", "myusudata")
        password = getattr(django_settings, "USU_API_PASSWORD", "test123Usu")

        # ── Step 2: Build a shared HTTP session with Basic Auth ───────────────
        # One session = one TCP connection pool → faster than per-request connections.
        session = _build_session(username, password)

        # ── Step 3: Resolve the tenant row (creates it if first run) ─────────
        tenant = _get_or_create_tenant(tenant_name)
        self.stdout.write(f"  Tenant : {tenant.name}")

        # ── Step 4: Installations → usu_installation ─────────────────────────
        if not skip_install:
            t0 = time.time()
            try:
                records = fetch_installations(session, self.stdout)
                save_installations(tenant, records, dry_run, self.stdout)
                self.stdout.write(self.style.SUCCESS(
                    f"  Installations done in {time.time() - t0:.1f}s"
                ))
            except Exception as exc:
                logger.exception("Installations sync failed")
                self.stderr.write(self.style.ERROR(f"  FAILED: Installations: {exc}"))
        else:
            self.stdout.write("  Skipping installations (--skip-install)")

        # ── Step 5: Demand details → usu_demand_detail ───────────────────────
        if not skip_demand:
            t0 = time.time()
            try:
                records = fetch_demand_details(session, demand_count, self.stdout)
                save_demand_details(tenant, records, dry_run, self.stdout)
                self.stdout.write(self.style.SUCCESS(
                    f"  Demand details done in {int((time.time()-t0)//60)}m "
                    f"{int((time.time()-t0)%60)}s"
                ))
            except Exception as exc:
                logger.exception("Demand details sync failed")
                self.stderr.write(self.style.ERROR(f"  FAILED: Demand details: {exc}"))
        else:
            self.stdout.write("  Skipping demand details (--skip-demand)")

        # ── Step 6: Done ──────────────────────────────────────────────────────
        total = time.time() - run_start
        self.stdout.write(self.style.SUCCESS(
            f"\n== Sync complete in {int(total//60)}m {int(total%60)}s ==\n"
        ))
        logger.info("fetch_usu_data finished in %.1fs (dry_run=%s)", total, dry_run)
