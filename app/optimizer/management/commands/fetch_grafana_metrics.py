"""
Management command: fetch_grafana_metrics
==========================================
Queries the Grafana-managed Mimir (Prometheus) cluster directly via the
Prometheus HTTP API and saves raw metric readings into grafana_metric_snapshot.

Architecture -- Grafana Mimir (NOT the Grafana frontend proxy):
  This command talks directly to the Mimir Prometheus endpoint:
    {GRAFANA_BASE_URL}/api/prom/api/v1/query_range

  Auth  : HTTP Basic Auth
          username = GRAFANA_USER  (e.g. 2834315)
          password = GRAFANA_TOKEN (glc_eyJ...)

  Header: X-Scope-OrgID = GRAFANA_TENANT_ID
          (Mimir multi-tenancy -- required for every request)

Prometheus range_query response:
  {
    "status": "success",
    "data": {
      "resultType": "matrix",
      "result": [
        {
          "metric": {"instance": "host:port", "job": "mysql", ...},
          "values": [[unix_ts, "value"], [unix_ts, "value"], ...]
        }
      ]
    }
  }

Each series in "result" = one server/instance.
Each [timestamp, value] pair = one GrafanaMetricSnapshot row.
Duplicate rows are silently ignored (ignore_conflicts=True) so overlapping
fetch windows never cause constraint errors.

Cron schedule (settings.py CRONJOBS): every hour at minute 0.
  Range  : now-2h   (2-hour overlap window prevents data gaps on delayed runs)
  Step   : 5m       (12 data points per hour per metric per server)

Register : python manage.py crontab add
Remove   : python manage.py crontab remove
Show     : python manage.py crontab show

Usage:
  python manage.py fetch_grafana_metrics
  python manage.py fetch_grafana_metrics --dry-run
  python manage.py fetch_grafana_metrics --range now-6h --step 1m
  python manage.py fetch_grafana_metrics --range now-24h --step 1h
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import httpx
from django.conf import settings as django_settings
from django.core.management.base import BaseCommand
from django.db import transaction

from optimizer.models import GrafanaMetricSnapshot, Server, Tenant

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULT_BASE_URL   = "https://prometheus-dedicated-64-prod-eu-west-5.grafana.net"
_DEFAULT_DASHBOARD  = "primary"
_DEFAULT_RANGE      = "now-2h"    # 2h overlap window covers any run delay up to 1h
_DEFAULT_STEP       = "5m"        # 5-min resolution = 12 data points per hour per metric
_DEFAULT_TENANT     = "default"   # Django Tenant name (not Grafana tenant)
_DEFAULT_TIMEOUT    = 30
DB_BATCH_SIZE       = 500
MAX_RETRIES         = 3
RETRY_BACKOFF       = 5   # seconds

# ── Metric registry ───────────────────────────────────────────────────────────
# Internal metric_name → (PromQL expression, unit string)
#
# ⚠ Verify these PromQL expressions match the metric names actually exposed
#   by your exporters.  Use Grafana Explore on the -prom datasource to test.
#
# Exporters assumed:
#   mysqld_exporter   → mysql_*
#   node_exporter     → node_* (Linux) or windows_* (Windows)

GRAFANA_METRICS: dict[str, tuple[str, str]] = {
    # Active DB connections — mssql_connections has a 'database' label so
    # we can later filter per DB (O11Y, master, msdb, etc.)
    "connections": (
        "mssql_connections",
        "",
    ),

    # Batch requests per second — mssql_batch_requests_total is a counter,
    # so rate() converts it to the per-second rate seen in the Grafana panel (~1.4 req/s)
    "batch_requests": (
        "rate(mssql_batch_requests_total[5m])",
        "req/s",
    ),

    # OS-level memory reported by SQL Server — mssql_os_memory is in bytes,
    # dividing by 1 GiB converts to GiB (panel shows ~22 GiB available, ~8 GiB used)
    "os_memory_available_gib": (
        "mssql_os_memory / 1073741824",
        "GiB",
    ),

    # Total memory SQL Server has acquired from the OS (server_total_memory_bytes).
    # Dividing by 1 GiB gives GiB. This is what the Memory Manager panel tracks.
    "memory_manager_total_gib": (
        "mssql_server_total_memory_bytes / 1073741824",
        "GiB",
    ),

    # SQL Server page life expectancy — how long (seconds) a page stays in buffer pool.
    # Low PLE (< 300s) indicates memory pressure; panel shows ~2000s = healthy.
    "page_life_expectancy": (
        "mssql_page_life_expectancy_seconds",
        "s",
    ),

    # Active running queries — mssql_running_queries directly matches
    # the Grafana panel showing 47–70 active queries
    "running_queries": (
        "mssql_running_queries",
        "",
    ),

    # SQL Server's own memory utilization % — mssql_memory_utilization_percentage
    # is a built-in SQL Server counter (panel shows ~100%, meaning SQL Server
    # is using all the memory it has been granted by the OS)
    "memory_utilization_pct": (
        "mssql_memory_utilization_percentage",
        "%",
    ),

    # Total database size in MiB — mssql_database_size_bytes has a 'database'
    # label so each DB (O11Y, master, msdb, etc.) gets its own time series row.
    # Dividing by 1 MiB converts bytes to MiB.
    "database_size_mib": (
        "mssql_database_size_bytes / 1048576",
        "MiB",
    ),
}


# ── Time-range helper ─────────────────────────────────────────────────────────

def _parse_range(range_str: str) -> tuple[str, str]:
    """
    Convert a Prometheus-style range string into (start_rfc3339, end_rfc3339).

    Supports: 'now-Xh', 'now-Xd', 'now-Xm'.
    Returns ISO-8601 UTC strings that the Prometheus API accepts.
    """
    now = datetime.now(tz=timezone.utc)

    if range_str.startswith("now-"):
        suffix = range_str[4:]
        if suffix.endswith("h"):
            delta = timedelta(hours=int(suffix[:-1]))
        elif suffix.endswith("d"):
            delta = timedelta(days=int(suffix[:-1]))
        elif suffix.endswith("m"):
            delta = timedelta(minutes=int(suffix[:-1]))
        else:
            delta = timedelta(hours=24)   # safe default
        start = now - delta
    else:
        start = now - timedelta(hours=24)

    # Prometheus API expects RFC3339 or Unix timestamps
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Prometheus HTTP API query ─────────────────────────────────────────────────

def _query_range(
    client: httpx.Client,
    base_url: str,
    promql: str,
    start: str,
    end: str,
    step: str,
) -> list[dict]:
    """
    Call the Prometheus range-query endpoint on the Mimir cluster.

    Endpoint: GET {base_url}/api/prom/api/v1/query_range

    Parameters:
      query : PromQL expression
      start : RFC3339 start time
      end   : RFC3339 end time
      step  : resolution step  (e.g. '1h', '30m')

    Returns a list of metric series, each:
      {
        "metric": {"instance": "...", "job": "...", ...},
        "values": [[unix_ts, "value_str"], ...]
      }

    Raises on non-2xx after MAX_RETRIES attempts.
    """
    params = {
        "query": promql,
        "start": start,
        "end":   end,
        "step":  step,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.get(
                f"{base_url}/api/prom/api/v1/query_range",
                params=params,
            )
            resp.raise_for_status()
            body = resp.json()

            # Prometheus always wraps results: {"status": "success", "data": {...}}
            if body.get("status") != "success":
                raise ValueError(f"Prometheus returned status={body.get('status')}: "
                                 f"{body.get('error', 'unknown error')}")

            return body.get("data", {}).get("result", [])

        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = attempt * RETRY_BACKOFF
            logger.warning(
                "Prometheus query failed (attempt %d/%d): %s — retrying in %ds",
                attempt, MAX_RETRIES, exc, wait,
            )
            time.sleep(wait)

    return []   # unreachable but keeps type checker happy


# ── Server resolution ─────────────────────────────────────────────────────────

def _resolve_server(tenant: Tenant, metric_labels: dict) -> Server:
    """
    Map Prometheus metric labels to a Server row (get_or_create).

    Label priority:
      1. 'instance'  — most exporters set this to hostname:port
      2. 'host'      — some exporters use this instead
      3. 'job'       — fallback when no host label present

    The hostname (without port) becomes the server_key.
    """
    raw_instance = (
        metric_labels.get("instance")
        or metric_labels.get("host")
        or metric_labels.get("job")
        or "unknown"
    )
    # Strip the exporter port (e.g. 'myserver:9104' → 'myserver')
    server_name = raw_instance.split(":")[0].strip() or raw_instance
    server_key  = server_name.lower()

    server, created = Server.objects.get_or_create(
        tenant=tenant,
        server_key=server_key,
        defaults={
            "server_name":    server_name,
            "source_systems": ["grafana"],
        },
    )
    if created:
        logger.debug("Auto-created Server from Grafana label: %s", server_key)
    return server


# ── Decimal helper ────────────────────────────────────────────────────────────

def _to_decimal(value) -> Decimal | None:
    """Safely coerce a float or string metric value to Decimal."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


# ── Management command ────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Hourly Grafana/Mimir sync: query Prometheus metrics for the last 2 hours "
        "(5-min step) and save raw readings into grafana_metric_snapshot. "
        "Duplicate rows are silently ignored so overlapping windows are safe."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Query the API but skip all DB writes.",
        )
        parser.add_argument(
            "--range", default=None, dest="time_range",
            help="Time window to fetch, e.g. 'now-6h', 'now-24h'. "
                 "Default: GRAFANA_FETCH_RANGE setting.",
        )
        parser.add_argument(
            "--step", default=None,
            help="Query resolution step, e.g. '1h', '30m'. "
                 "Default: GRAFANA_STEP setting.",
        )
        parser.add_argument(
            "--tenant", default=_DEFAULT_TENANT,
            help="Django Tenant name for saved rows. Default: 'default'",
        )

    def handle(self, *_args, **options):
        dry_run   = options["dry_run"]
        tenant_nm = options["tenant"]
        run_start = time.time()

        # ── Step 1: Load Mimir credentials from settings (.env) ──────────────
        base_url    = getattr(django_settings, "GRAFANA_BASE_URL",  _DEFAULT_BASE_URL).rstrip("/")
        tenant_id   = getattr(django_settings, "GRAFANA_TENANT_ID", "")
        gf_user     = getattr(django_settings, "GRAFANA_USER",      "")
        gf_token    = getattr(django_settings, "GRAFANA_TOKEN",     "")
        timeout     = getattr(django_settings, "GRAFANA_TIMEOUT",   _DEFAULT_TIMEOUT)
        dashboard   = getattr(django_settings, "GRAFANA_DASHBOARD", _DEFAULT_DASHBOARD)
        time_range  = options["time_range"] or getattr(django_settings, "GRAFANA_FETCH_RANGE", _DEFAULT_RANGE)
        step        = options["step"]       or getattr(django_settings, "GRAFANA_STEP", _DEFAULT_STEP)
        metrics     = getattr(django_settings, "GRAFANA_METRICS",   GRAFANA_METRICS)

        # Guard: fail fast if required credentials are missing
        if not gf_token:
            self.stderr.write(self.style.ERROR("GRAFANA_TOKEN is not set in .env — aborting."))
            return
        if not tenant_id:
            self.stderr.write(self.style.ERROR("GRAFANA_TENANT_ID is not set in .env — aborting."))
            return

        # Convert 'now-24h' → actual RFC3339 timestamps for the Prometheus API
        start_str, end_str = _parse_range(time_range)

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n==============================================\n"
            "  Grafana / Mimir Metrics Fetch\n"
            "=============================================="
        ))
        self.stdout.write(f"  Endpoint  : {base_url}/api/prom/api/v1/query_range")
        self.stdout.write(f"  Tenant ID : {tenant_id}")
        self.stdout.write(f"  User      : {gf_user}")
        self.stdout.write(f"  Window    : {start_str}  ->  {end_str}")
        self.stdout.write(f"  Step      : {step}")
        self.stdout.write(f"  Dashboard : {dashboard}")
        self.stdout.write(f"  Metrics   : {list(metrics.keys())}")
        if dry_run:
            self.stdout.write(self.style.WARNING("  [!] DRY RUN -- no DB writes"))

        # ── Step 2: Resolve Django tenant row ─────────────────────────────────
        tenant, _ = Tenant.objects.get_or_create(
            name=tenant_nm,
            defaults={"description": "Auto-created by fetch_grafana_metrics", "is_active": True},
        )

        # ── Step 3: Build httpx client ────────────────────────────────────────
        # Basic Auth  : username=GRAFANA_USER, password=GRAFANA_TOKEN
        # X-Scope-OrgID header is mandatory for Mimir multi-tenancy.
        # Without it the cluster returns 401 or routes to the wrong tenant.
        client_kwargs = {
            "auth":    (gf_user, gf_token),
            "headers": {
                "X-Scope-OrgID": tenant_id,
                "Accept":        "application/json",
            },
            "timeout": float(timeout),
        }

        total_saved = 0

        with httpx.Client(**client_kwargs) as client:

            # ── Step 4: Query each metric from Prometheus ─────────────────────
            for metric_name, (promql, unit) in metrics.items():
                self.stdout.write(f"\n  -- {metric_name}")
                self.stdout.write(f"     PromQL : {promql}")

                try:
                    series_list = _query_range(
                        client, base_url, promql, start_str, end_str, step
                    )
                except Exception as exc:
                    logger.error("Metric '%s' query failed: %s", metric_name, exc)
                    self.stderr.write(self.style.ERROR(f"     FAILED: {exc}"))
                    continue

                self.stdout.write(f"     Series : {len(series_list)} instances returned")

                if not series_list:
                    self.stdout.write("     No data — skipping.")
                    continue

                # ── Step 5: Parse series → build snapshot objects ─────────────
                objs    = []
                written = 0

                for series in series_list:
                    # 'metric' dict holds Prometheus labels: instance, job, etc.
                    metric_labels = series.get("metric", {})

                    # Map the Prometheus instance label to a Server row
                    server = _resolve_server(tenant, metric_labels)

                    # 'values' is [[unix_timestamp, "value_string"], ...]
                    # Prometheus returns values as strings to preserve precision.
                    for unix_ts, val_str in series.get("values", []):
                        metric_ts = datetime.fromtimestamp(
                            float(unix_ts), tz=timezone.utc
                        )

                        objs.append(GrafanaMetricSnapshot(
                            tenant       = tenant,
                            server       = server,
                            dashboard    = dashboard,
                            metric_name  = metric_name,
                            metric_value = _to_decimal(val_str),
                            metric_unit  = unit,
                            metric_ts    = metric_ts,
                        ))

                        # Flush once the batch is full — avoids holding large lists in RAM
                        if len(objs) >= DB_BATCH_SIZE and not dry_run:
                            with transaction.atomic():
                                GrafanaMetricSnapshot.objects.bulk_create(
                                    objs, ignore_conflicts=True
                                )
                            written     += len(objs)
                            total_saved += len(objs)
                            objs = []

                # Final partial batch for this metric
                if objs and not dry_run:
                    with transaction.atomic():
                        GrafanaMetricSnapshot.objects.bulk_create(
                            objs, ignore_conflicts=True
                        )
                    written     += len(objs)
                    total_saved += len(objs)

                self.stdout.write(self.style.SUCCESS(
                    f"     OK: {written:,} rows -> grafana_metric_snapshot"
                    if not dry_run else
                    f"     [dry-run] Would save ~{len(objs) + written:,} rows"
                ))

        # ── Step 6: Final summary ─────────────────────────────────────────────
        elapsed = time.time() - run_start
        self.stdout.write(self.style.SUCCESS(
            f"\n== Done: {total_saved:,} total snapshot rows saved "
            f"in {int(elapsed // 60)}m {int(elapsed % 60)}s ==\n"
        ))
        logger.info(
            "fetch_grafana_metrics: %d rows saved, elapsed=%.1fs, dry_run=%s",
            total_saved, elapsed, dry_run,
        )
