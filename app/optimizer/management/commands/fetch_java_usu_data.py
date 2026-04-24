"""
Management command: fetch_java_usu_data
========================================
Pulls Java (Oracle) installation and demand-detail records from the USU API
and stores them in the correct PostgreSQL tables:

  API endpoint          → Django model      → DB table
  ─────────────────────────────────────────────────────
  /installations        → USUInstallation   → usu_installation
  /demanddetails        → USUDemandDetail   → usu_demand_detail

Both endpoints also create/update the parent Server row so that
every installation/demand record has a valid FK before insertion.

Note on product_family mapping:
  pf_description == "Java"  →  Oracle Server Data  (this command)
  pf_description == "MySQL" →  MySQL Server Data   (fetch_usu_data command)

Record volumes (as of 2026-04-24):
  - Installations  : 1 230   → single page  ($top=30 000)
  - Demand Details : 1 230   → single page  ($top=30 000)
  No pagination needed — both fit in one API response.

Scheduling — django-crontab:
    Cron name  : fetch_java_usu_data
    Schedule   : Every Tuesday at 02:30 AM (offset from MySQL sync on Monday)
    Register   : python manage.py crontab add
    Remove     : python manage.py crontab remove
    Show       : python manage.py crontab show

One-time manual run:
    python manage.py fetch_java_usu_data
    python manage.py fetch_java_usu_data --dry-run
    python manage.py fetch_java_usu_data --skip-demand
    python manage.py fetch_java_usu_data --skip-install
"""

import logging
import time
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

BASE_URL         = "https://lima.bayer.cloud.usu.com"
INSTALL_ENDPOINT = "/prod/index.php/api/customization/v1.0/installations"
DEMAND_ENDPOINT  = "/prod/index.php/api/customization/v1.0/demanddetails"
PRODUCT_FAMILY   = "Java"          # maps to Oracle Server Data in the UI

# All 1 230 records fit in a single page — $top=30 000 covers them entirely.
INSTALL_PAGE_SIZE = 30_000
DEMAND_PAGE_SIZE  = 30_000

# How many ORM objects to pass to bulk_create in a single DB call.
DB_BATCH_SIZE = 500

# Network settings
REQUEST_TIMEOUT = 120   # seconds per HTTP request
MAX_RETRIES     = 4     # retries on transient failures
RETRY_BACKOFF   = 5     # seconds — multiplied by attempt number for back-off


# ── Type-coercion helpers (identical to fetch_usu_data) ──────────────────────

def _str(value, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len] if max_len else s


def _bool(value) -> bool | None:
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
    if value is None:
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(Decimal(str(value).strip()))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (ValueError, TypeError):
        return None


def _beat_ids(value) -> list[str]:
    if not value:
        return []
    return [b.strip() for b in str(value).split("\n") if b.strip()]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _build_session(username: str, password: str) -> requests.Session:
    session = requests.Session()
    session.auth = HTTPBasicAuth(username, password)
    session.headers.update({"Accept": "application/json"})
    return session


def _fetch_page(session: requests.Session, url: str, params: dict | None = None) -> dict:
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
    tenant, created = Tenant.objects.get_or_create(
        name=name,
        defaults={"description": "Auto-created by fetch_java_usu_data", "is_active": True},
    )
    if created:
        logger.info("Created tenant: %s", name)
    return tenant


def _resolve_server_from_installation(tenant: Tenant, raw: dict) -> Server:
    usu_key     = _str(raw.get("devices_device_key"), 512)
    server_name = _str(raw.get("devices_device_name"), 255) or "unknown"
    environment = _str(raw.get("device_purposes_name"), 80)
    hosting     = _str(raw.get("device_man_systems_name"), 120)
    server_key  = usu_key or f"{server_name}|{environment or ''}|{hosting or ''}".lower()

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


# ── Installations: fetch ──────────────────────────────────────────────────────

def fetch_java_installations(session: requests.Session, stdout) -> list[dict]:
    """
    Fetch all Java/Oracle installation records from USU API.
    Total: ~1 230 records — fits in a single $top=30 000 page.
    Falls back to next_page_uri pagination if records ever exceed page size.

    Cron function name: fetch_java_usu_data  (via management command)
    """
    all_records = []
    params = {"product_family": PRODUCT_FAMILY, "$top": INSTALL_PAGE_SIZE, "$skip": 0}
    url    = BASE_URL + INSTALL_ENDPOINT
    page   = 1

    stdout.write("-- Fetching Java/Oracle Installations ------------------")

    while url:
        t0   = time.time()
        data = _fetch_page(session, url, params)

        records       = data.get("data") or []
        next_page_uri = data.get("metadata", {}).get("pagination", {}).get("next_page_uri")

        all_records.extend(records)
        stdout.write(
            f"  Page {page} | got {len(records):,} | "
            f"total {len(all_records):,} | {time.time() - t0:.1f}s"
        )

        if next_page_uri and len(records) == INSTALL_PAGE_SIZE:
            url    = BASE_URL + next_page_uri
            params = None
            page  += 1
            time.sleep(0.5)
        else:
            break

    stdout.write(f"  Java Installations total: {len(all_records):,}")
    return all_records


# ── Demand details: fetch ─────────────────────────────────────────────────────

def fetch_java_demand_details(session: requests.Session, stdout) -> list[dict]:
    """
    Fetch all Java/Oracle demand-detail records from USU API.
    Total: ~1 230 records — fits in a single $top=30 000 page.
    Falls back to next_page_uri pagination if records ever exceed page size.

    Cron function name: fetch_java_usu_data  (via management command)
    """
    all_records = []
    params = {"product_family": PRODUCT_FAMILY, "$top": DEMAND_PAGE_SIZE, "$skip": 0}
    url    = BASE_URL + DEMAND_ENDPOINT
    page   = 1
    t_start = time.time()

    stdout.write("-- Fetching Java/Oracle Demand Details -----------------")

    while url:
        t0   = time.time()
        data = _fetch_page(session, url, params)

        records       = data.get("data") or []
        next_page_uri = data.get("metadata", {}).get("pagination", {}).get("next_page_uri")

        all_records.extend(records)
        stdout.write(
            f"  Page {page} | got {len(records):,} | "
            f"total {len(all_records):,} | {time.time() - t0:.1f}s"
        )

        if next_page_uri and len(records) == DEMAND_PAGE_SIZE:
            url    = BASE_URL + next_page_uri
            params = None
            page  += 1
            time.sleep(0.3)
        else:
            break

    elapsed = time.time() - t_start
    stdout.write(
        f"  Java Demand total: {len(all_records):,} records "
        f"in {int(elapsed // 60)}m {int(elapsed % 60)}s"
    )
    return all_records


# ── DB persistence ────────────────────────────────────────────────────────────

def save_java_installations(
    tenant: Tenant, records: list[dict], dry_run: bool, stdout
) -> None:
    """
    Persist Java/Oracle installation records into usu_installation.
    Full-refresh: deletes all existing Java rows first, then bulk-inserts.
    """
    if dry_run:
        stdout.write(f"  [dry-run] Would write {len(records):,} Java installations — skipped")
        return

    stdout.write(f"  Writing {len(records):,} Java installations -> usu_installation ...")
    t0 = time.time()

    deleted, _ = USUInstallation.objects.filter(
        tenant=tenant, product_family=PRODUCT_FAMILY
    ).delete()
    stdout.write(f"  Deleted {deleted:,} stale rows from usu_installation (product_family=Java)")

    objs    = []
    written = 0

    for raw in records:
        server = _resolve_server_from_installation(tenant, raw)

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

        if len(objs) >= DB_BATCH_SIZE:
            with transaction.atomic():
                USUInstallation.objects.bulk_create(objs, ignore_conflicts=True)
            written += len(objs)
            objs = []

    if objs:
        with transaction.atomic():
            USUInstallation.objects.bulk_create(objs, ignore_conflicts=True)
        written += len(objs)

    stdout.write(
        f"  OK: usu_installation (Java): {written:,} rows saved in {time.time() - t0:.1f}s"
    )


def save_java_demand_details(
    tenant: Tenant, records: list[dict], dry_run: bool, stdout
) -> None:
    """
    Persist Java/Oracle demand-detail records into usu_demand_detail.
    Full-refresh: deletes all existing Java rows first, then bulk-inserts.
    """
    if dry_run:
        stdout.write(f"  [dry-run] Would write {len(records):,} Java demand rows — skipped")
        return

    stdout.write(f"  Writing {len(records):,} Java demand details -> usu_demand_detail ...")
    t0 = time.time()

    deleted, _ = USUDemandDetail.objects.filter(
        tenant=tenant, product_family=PRODUCT_FAMILY
    ).delete()
    stdout.write(f"  Deleted {deleted:,} stale rows from usu_demand_detail (product_family=Java)")

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

    if objs:
        with transaction.atomic():
            USUDemandDetail.objects.bulk_create(objs, ignore_conflicts=True)
        written += len(objs)

    elapsed = time.time() - t0
    stdout.write(
        f"  OK: usu_demand_detail (Java): {written:,} rows saved "
        f"in {int(elapsed // 60)}m {int(elapsed % 60)}s"
    )


# ── Management command entry point ────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Weekly USU sync for Java/Oracle: fetch installations (~1 230) and "
        "demand details (~1 230) and store them in usu_installation and "
        "usu_demand_detail tables. "
        "Cron function name: fetch_java_usu_data"
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
            "--tenant", default="default",
            help="Tenant name for all ingested records. Default: 'default'",
        )

    def handle(self, *_args, **options):
        dry_run      = options["dry_run"]
        skip_install = options["skip_install"]
        skip_demand  = options["skip_demand"]
        tenant_name  = options["tenant"]
        run_start    = time.time()

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n==============================================\n"
            "  USU Java/Oracle Data Sync\n"
            "  Cron function name: fetch_java_usu_data\n"
            "=============================================="
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING("  [!] DRY RUN -- no DB writes"))

        # ── Step 1: Read credentials from Django settings ─────────────────────
        username = getattr(django_settings, "USU_API_USERNAME", "myusudata")
        password = getattr(django_settings, "USU_API_PASSWORD", "test123Usu")

        # ── Step 2: Build shared HTTP session with Basic Auth ─────────────────
        session = _build_session(username, password)

        # ── Step 3: Resolve tenant row ────────────────────────────────────────
        tenant = _get_or_create_tenant(tenant_name)
        self.stdout.write(f"  Tenant       : {tenant.name}")
        self.stdout.write(f"  Product family: {PRODUCT_FAMILY} (Oracle Server Data)")

        # ── Step 4: Installations → usu_installation ──────────────────────────
        if not skip_install:
            t0 = time.time()
            try:
                records = fetch_java_installations(session, self.stdout)
                save_java_installations(tenant, records, dry_run, self.stdout)
                self.stdout.write(self.style.SUCCESS(
                    f"  Installations done in {time.time() - t0:.1f}s"
                ))
            except Exception as exc:
                logger.exception("Java installations sync failed")
                self.stderr.write(self.style.ERROR(f"  FAILED: Installations: {exc}"))
        else:
            self.stdout.write("  Skipping installations (--skip-install)")

        # ── Step 5: Demand details → usu_demand_detail ────────────────────────
        if not skip_demand:
            t0 = time.time()
            try:
                records = fetch_java_demand_details(session, self.stdout)
                save_java_demand_details(tenant, records, dry_run, self.stdout)
                self.stdout.write(self.style.SUCCESS(
                    f"  Demand details done in {int((time.time()-t0)//60)}m "
                    f"{int((time.time()-t0)%60)}s"
                ))
            except Exception as exc:
                logger.exception("Java demand details sync failed")
                self.stderr.write(self.style.ERROR(f"  FAILED: Demand details: {exc}"))
        else:
            self.stdout.write("  Skipping demand details (--skip-demand)")

        # ── Step 6: Done ──────────────────────────────────────────────────────
        total = time.time() - run_start
        self.stdout.write(self.style.SUCCESS(
            f"\n== Java/Oracle sync complete in {int(total//60)}m {int(total%60)}s ==\n"
        ))
        logger.info("fetch_java_usu_data finished in %.1fs (dry_run=%s)", total, dry_run)
