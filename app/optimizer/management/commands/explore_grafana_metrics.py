"""
Management command: explore_grafana_metrics
============================================
Helper utility to discover what Prometheus metrics are actually available
in the Mimir cluster — run this ONCE to find the correct metric names, then
update GRAFANA_METRICS in fetch_grafana_metrics.py with real PromQL expressions.

Usage:
  # List ALL metric names (can be thousands)
  python manage.py explore_grafana_metrics

  # Filter by keyword (recommended — narrow it down)
  python manage.py explore_grafana_metrics --filter mysql
  python manage.py explore_grafana_metrics --filter memory
  python manage.py explore_grafana_metrics --filter connection
  python manage.py explore_grafana_metrics --filter node

  # Test a specific PromQL expression to see if it returns data
  python manage.py explore_grafana_metrics --test "mysql_global_status_threads_connected"
  python manage.py explore_grafana_metrics --test "up{job=~'.*mysql.*'}"
"""

import logging

import httpx
from django.conf import settings as django_settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://prometheus-dedicated-64-prod-eu-west-5.grafana.net"


class Command(BaseCommand):
    help = "Discover available Prometheus metric names in the Mimir cluster."

    def add_arguments(self, parser):
        parser.add_argument(
            "--filter", default=None, dest="keyword",
            help="Case-insensitive keyword to filter metric names (e.g. 'mysql', 'memory').",
        )
        parser.add_argument(
            "--test", default=None, dest="promql",
            help="Test a specific PromQL expression — shows labels of matching series.",
        )
        parser.add_argument(
            "--jobs", action="store_true",
            help="List all distinct job label values (shows what exporters are active).",
        )

    def handle(self, *_args, **options):
        base_url  = getattr(django_settings, "GRAFANA_BASE_URL",  _DEFAULT_BASE_URL).rstrip("/")
        tenant_id = getattr(django_settings, "GRAFANA_TENANT_ID", "")
        gf_user   = getattr(django_settings, "GRAFANA_USER",      "")
        gf_token  = getattr(django_settings, "GRAFANA_TOKEN",     "")
        timeout   = float(getattr(django_settings, "GRAFANA_TIMEOUT", 30))

        if not gf_token:
            self.stderr.write(self.style.ERROR("GRAFANA_TOKEN not set in .env"))
            return

        headers = {
            "X-Scope-OrgID": tenant_id,
            "Accept":        "application/json",
        }

        with httpx.Client(auth=(gf_user, gf_token), headers=headers, timeout=timeout) as client:

            # ── Option A: list all job label values (what exporters are running) ──
            if options["jobs"]:
                self.stdout.write(self.style.MIGRATE_HEADING("\n── Active Prometheus jobs (exporters) ──"))
                resp = client.get(f"{base_url}/api/prom/api/v1/label/job/values")
                resp.raise_for_status()
                jobs = resp.json().get("data", [])
                for job in sorted(jobs):
                    self.stdout.write(f"  {job}")
                self.stdout.write(f"\nTotal: {len(jobs)} jobs\n")
                return

            # ── Option B: test a specific PromQL expression ───────────────────
            if options["promql"]:
                promql = options["promql"]
                self.stdout.write(self.style.MIGRATE_HEADING(f"\n── Testing PromQL: {promql} ──"))
                resp = client.get(
                    f"{base_url}/api/prom/api/v1/query",
                    params={"query": promql, "time": "now"},
                )
                resp.raise_for_status()
                body    = resp.json()
                results = body.get("data", {}).get("result", [])
                self.stdout.write(f"  Status  : {body.get('status')}")
                self.stdout.write(f"  Matches : {len(results)} series")
                for r in results[:10]:    # show first 10 series
                    self.stdout.write(f"  Labels  : {r.get('metric', {})}")
                    val = r.get("value", [None, None])
                    self.stdout.write(f"  Value   : {val[1]}")
                    self.stdout.write("")
                if len(results) > 10:
                    self.stdout.write(f"  … and {len(results) - 10} more series")
                return

            # ── Option C: list all metric names (with optional keyword filter) ─
            keyword = (options["keyword"] or "").lower()
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n── Metric names"
                + (f" matching '{keyword}'" if keyword else " (ALL)")
                + " ──"
            ))

            # GET /api/prom/api/v1/label/__name__/values returns every metric name
            resp = client.get(f"{base_url}/api/prom/api/v1/label/__name__/values")
            resp.raise_for_status()
            all_names = resp.json().get("data", [])

            # Apply keyword filter if provided
            filtered = [n for n in all_names if keyword in n.lower()] if keyword else all_names
            filtered.sort()

            for name in filtered:
                self.stdout.write(f"  {name}")

            self.stdout.write(
                f"\nShowing {len(filtered)} of {len(all_names)} total metrics.\n"
            )
            if not keyword:
                self.stdout.write(
                    "Tip: use --filter <keyword> to narrow results, e.g.:\n"
                    "  python manage.py explore_grafana_metrics --filter mysql\n"
                    "  python manage.py explore_grafana_metrics --filter memory\n"
                    "  python manage.py explore_grafana_metrics --jobs\n"
                )
