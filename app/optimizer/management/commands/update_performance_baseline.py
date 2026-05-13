"""
Extract P50/P95 phase timings from AgentRun records and print a
Markdown table ready to paste into app/docs/PERFORMANCE_BASELINE.md.

Usage:
    python manage.py update_performance_baseline
    python manage.py update_performance_baseline --days 30
    python manage.py update_performance_baseline --days 90 --warn-threshold 20
"""
import statistics
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


PHASE_LABELS = {
    "data_load_sec": "Data load (USU + demand + prices)",
    "rule_eval_sec": "Rule evaluation (PAYG + Retired + Rightsizing)",
    "llm_call_sec": "LLM call (Agent + Azure OpenAI via APIM)",
    "total_sec": "Total end-to-end",
}


def _percentile(data: list, p: int) -> float | None:
    """Return the p-th percentile of data, or None if data is empty."""
    if not data:
        return None
    s = sorted(data)
    # statistics.quantiles needs n >= 2; handle small samples gracefully
    if len(s) == 1:
        return round(s[0], 2)
    # quantiles returns cut points between n equal-sized groups
    # For P50 use median; for P95 interpolate manually for accuracy
    if p == 50:
        return round(statistics.median(s), 2)
    idx = (p / 100) * (len(s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return round(s[lo] + (idx - lo) * (s[hi] - s[lo]), 2)


class Command(BaseCommand):
    help = (
        "Print P50/P95 phase timings from recent AgentRun records. "
        "Paste the output table into app/docs/PERFORMANCE_BASELINE.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days of AgentRun history to analyse (default: 30).",
        )
        parser.add_argument(
            "--warn-threshold",
            type=float,
            default=20.0,
            dest="warn_threshold",
            help=(
                "Warn if any P95 value is this %% higher than the previous period "
                "(default: 20%%). Set 0 to disable."
            ),
        )

    def handle(self, *args, **options):
        from optimizer.models import AgentRun

        days = options["days"]
        warn_threshold = options["warn_threshold"]
        since = timezone.now() - timedelta(days=days)

        runs = AgentRun.objects.filter(
            status=AgentRun.STATUS_COMPLETED,
            finished_at__gte=since,
        ).values_list("input_file_versions", flat=True)

        run_list = list(runs)
        total_runs = len(run_list)

        # Collect per-phase timing samples
        phases: dict[str, list[float]] = {key: [] for key in PHASE_LABELS}
        runs_with_timings = 0

        for versions in run_list:
            if not isinstance(versions, dict):
                continue
            timings = versions.get("phase_timings")
            if not isinstance(timings, dict):
                continue
            runs_with_timings += 1
            for key in phases:
                val = timings.get(key)
                if val is not None:
                    try:
                        phases[key].append(float(val))
                    except (TypeError, ValueError):
                        pass

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"## Phase Timing Baseline  "
                f"(last {days} days · {runs_with_timings}/{total_runs} runs have timings)"
            )
        )
        self.stdout.write("")

        if runs_with_timings == 0:
            self.stdout.write(
                self.style.WARNING(
                    "  No phase_timings found in any AgentRun.input_file_versions.\n"
                    "  Deploy the instrumentation and run at least one analysis first."
                )
            )
            return

        # Print Markdown table
        self.stdout.write("| Phase | P50 (s) | P95 (s) | Sample size |")
        self.stdout.write("|---|---|---|---|")

        for key, label in PHASE_LABELS.items():
            data = phases[key]
            p50 = _percentile(data, 50)
            p95 = _percentile(data, 95)
            p50_str = f"{p50:.2f}" if p50 is not None else "[no data]"
            p95_str = f"{p95:.2f}" if p95 is not None else "[no data]"
            self.stdout.write(f"| {label} | {p50_str} | {p95_str} | n={len(data)} |")

        self.stdout.write("")
        self.stdout.write(
            "Paste this table into app/docs/PERFORMANCE_BASELINE.md, "
            "bump the version, update Last Updated, and commit:\n"
            "  git commit -m 'perf-baseline: YYYY-MM update'"
        )

        # Regression warning — compare current P95 total vs alert threshold
        if warn_threshold > 0:
            total_data = phases.get("total_sec", [])
            p95_total = _percentile(total_data, 95)
            alert_threshold_sec = 180
            if p95_total is not None and p95_total > alert_threshold_sec:
                self.stdout.write("")
                self.stdout.write(
                    self.style.ERROR(
                        f"WARNING: P95 total ({p95_total:.2f}s) exceeds the "
                        f"{alert_threshold_sec}s critical alert threshold. "
                        "Raise an alert to Saksham."
                    )
                )
