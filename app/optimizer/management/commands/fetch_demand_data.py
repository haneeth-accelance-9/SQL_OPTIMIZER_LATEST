"""
Management command: fetch all demand-detail records from the USU API
and save them to response_full.json (overwrites each run).

Schedule via cron (twice daily — midnight and noon):
    0 0,12 * * * /path/to/venv/bin/python /path/to/app/manage.py fetch_demand_data

Settings (optional overrides via env or settings.py):
    DEMAND_API_BASE_URL      — default: https://lima.bayer.cloud.usu.com
    DEMAND_API_START_URI     — default: /prod/index.php/api/customization/v1.0/demanddetails?$skip=0&$top=10000
    DEMAND_API_AUTH_HEADER   — default: Basic dXN1ZGF0YXVzZXI6QlVFUFdFZkw2JCM5eVEh
    DEMAND_API_OUTPUT_FILE   — default: response_full.json (relative to manage.py directory)
"""
import json
import logging
import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://lima.bayer.cloud.usu.com"
_DEFAULT_START_URI = "/prod/index.php/api/customization/v1.0/demanddetails?$skip=0&$top=10000"
_DEFAULT_AUTH_HEADER = "Basic dXN1ZGF0YXVzZXI6QlVFUFdFZkw2JCM5eVEh"
_MAX_RETRIES = 5
_REQUEST_TIMEOUT = 120
_INTER_PAGE_SLEEP = 1


class Command(BaseCommand):
    help = (
        "Fetch all demand-detail records from the USU API and save to response_full.json. "
        "Intended to run via cron twice daily (midnight and noon)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=None,
            help="Path to output JSON file. Defaults to DEMAND_API_OUTPUT_FILE setting or response_full.json.",
        )

    def handle(self, *args, **options):
        try:
            import httpx
        except ImportError:
            self.stderr.write(self.style.ERROR("httpx is required: pip install httpx"))
            return

        base_url = getattr(settings, "DEMAND_API_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
        start_uri = getattr(settings, "DEMAND_API_START_URI", _DEFAULT_START_URI)
        auth_header = getattr(settings, "DEMAND_API_AUTH_HEADER", _DEFAULT_AUTH_HEADER)

        output_file = (
            options.get("output")
            or getattr(settings, "DEMAND_API_OUTPUT_FILE", None)
            or os.path.join(settings.BASE_DIR, "response_full.json")
        )

        headers = {"Authorization": auth_header}
        all_records = []
        next_page = start_uri
        page_num = 1
        total_start = time.time()

        self.stdout.write(f"Starting demand data fetch → {output_file}")

        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            while next_page:
                full_url = base_url + next_page
                page_start = time.time()
                self.stdout.write(f"\nPage {page_num} | {full_url}")

                data = None
                for attempt in range(1, _MAX_RETRIES + 1):
                    try:
                        response = client.get(full_url, headers=headers)
                        response.raise_for_status()
                        data = response.json()
                        break
                    except Exception as exc:
                        wait = attempt * 5
                        self.stdout.write(
                            self.style.WARNING(
                                f"  Attempt {attempt}/{_MAX_RETRIES} failed: {exc} — retrying in {wait}s"
                            )
                        )
                        if attempt < _MAX_RETRIES:
                            time.sleep(wait)

                if data is None:
                    self.stderr.write(
                        self.style.ERROR(
                            f"Failed after {_MAX_RETRIES} retries at page {page_num}. Saving progress so far."
                        )
                    )
                    break

                records = data.get("data", [])
                all_records.extend(records)

                next_page = data.get("metadata", {}).get("pagination", {}).get("next_page_uri")

                elapsed = time.time() - total_start
                page_time = time.time() - page_start
                self.stdout.write(
                    f"  Fetched {len(records)} records | Total: {len(all_records)} | "
                    f"Page time: {page_time:.1f}s | Elapsed: {int(elapsed // 60)}m {int(elapsed % 60)}s"
                )

                # Save progress after every page (same file, overwrite)
                with open(output_file, "w") as f:
                    json.dump(all_records, f, indent=2)
                self.stdout.write(f"  Saved {len(all_records)} records to {output_file}")

                if not records:
                    self.stdout.write("  No more records.")
                    break

                page_num += 1
                if next_page:
                    time.sleep(_INTER_PAGE_SLEEP)

        total_time = time.time() - total_start
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Total records saved: {len(all_records)} | "
                f"Time: {int(total_time // 60)}m {int(total_time % 60)}s"
            )
        )
        logger.info(
            "fetch_demand_data completed: %d records written to %s in %.1fs",
            len(all_records), output_file, total_time,
        )
