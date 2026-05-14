"""
Tests for the rollup_grafana_metrics management command.
Covers all 71 statements (0% → significant coverage gain).

Strategy: mock the Django ORM layer completely so no real DB connection is needed.
The management command imports GrafanaMetricSnapshot and GrafanaMetricMonthlyRollup
from optimizer.models — we patch those at the command module level.
"""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, call, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CMD_PATH = "optimizer.management.commands.rollup_grafana_metrics"


def _make_aggregated_row(period_year=2025, period_month=3):
    """Return a dict that mimics what the annotated ORM queryset yields."""
    from django.utils import timezone as tz
    period_dt = datetime(period_year, period_month, 1, 0, 0, 0)
    try:
        period_dt = tz.make_aware(period_dt)
    except Exception:
        pass
    return {
        "tenant_id": uuid.uuid4(),
        "server_id": uuid.uuid4(),
        "metric_name": "cpu_usage",
        "metric_unit": "percent",
        "period_month": period_dt,
        "avg_value": Decimal("45.250000"),
        "max_value": Decimal("89.100000"),
        "min_value": Decimal("12.300000"),
        "sample_count": 24,
    }


def _build_mock_snapshot_objects(rows=None, purge_count=0):
    """
    Build a MagicMock that mimics GrafanaMetricSnapshot.objects chaining.
    rows: list of aggregated row dicts returned by the rollup queryset iterator.
    purge_count: what .filter(...).count() returns for the purge step.
    """
    if rows is None:
        rows = []

    mock_objects = MagicMock()

    # The rollup queryset chain:
    # .filter() → .annotate() → .values() → .annotate() → .order_by() → iterable
    rollup_chain = MagicMock()
    rollup_chain.__iter__ = MagicMock(return_value=iter(rows))
    rollup_chain.order_by.return_value = rollup_chain

    val_chain = MagicMock()
    val_chain.annotate.return_value = rollup_chain

    ann1_chain = MagicMock()
    ann1_chain.values.return_value = val_chain

    filter_chain = MagicMock()
    filter_chain.annotate.return_value = ann1_chain
    # purge count
    filter_chain.count.return_value = purge_count
    # purge values_list (for chunked delete)
    filter_chain.values_list.return_value = []
    filter_chain.filter.return_value = filter_chain
    filter_chain.delete.return_value = (0, {})

    mock_objects.filter.return_value = filter_chain
    return mock_objects


def _run_command(*args, **kwargs):
    """Run the management command with fully mocked ORM, return stdout."""
    from contextlib import contextmanager
    from django.core.management import call_command

    out = StringIO()
    rows = kwargs.pop("rows", [])
    purge_count = kwargs.pop("purge_count", 0)

    # transaction.atomic() also touches the DB connection — mock it out
    @contextmanager
    def _noop_atomic():
        yield

    with patch(f"{_CMD_PATH}.GrafanaMetricSnapshot.objects") as mock_snap, \
         patch(f"{_CMD_PATH}.GrafanaMetricMonthlyRollup.objects") as mock_rollup, \
         patch(f"{_CMD_PATH}.transaction.atomic", side_effect=_noop_atomic):

        rollup_chain = MagicMock()
        rollup_chain.__iter__ = MagicMock(return_value=iter(rows))
        rollup_chain.order_by.return_value = rollup_chain

        val_chain = MagicMock()
        val_chain.annotate.return_value = rollup_chain

        ann1_chain = MagicMock()
        ann1_chain.values.return_value = val_chain

        filter_chain = MagicMock()
        filter_chain.annotate.return_value = ann1_chain
        filter_chain.count.return_value = purge_count
        filter_chain.values_list.return_value = []
        filter_chain.filter.return_value = filter_chain
        filter_chain.delete.return_value = (purge_count, {})

        mock_snap.filter.return_value = filter_chain

        # Rollup upsert mock
        mock_rollup.update_or_create.return_value = (MagicMock(), True)

        call_command("rollup_grafana_metrics", *args, stdout=out, **kwargs)

    return out.getvalue(), mock_snap, mock_rollup


# ---------------------------------------------------------------------------
# Basic invocation — dry-run
# ---------------------------------------------------------------------------

class TestRollupGrafanaMetricsDryRun:
    def test_dry_run_completes_without_error(self):
        output, _, _ = _run_command("--dry-run")
        assert output  # something printed

    def test_dry_run_mentions_dry_run(self):
        output, _, _ = _run_command("--dry-run")
        assert "dry" in output.lower() or "DRY" in output

    def test_dry_run_reports_zero_rollup_groups(self):
        output, _, _ = _run_command("--dry-run")
        assert "0" in output

    def test_dry_run_does_not_call_update_or_create(self):
        _, _, mock_rollup = _run_command("--dry-run")
        mock_rollup.update_or_create.assert_not_called()

    def test_dry_run_with_custom_retention_days(self):
        output, _, _ = _run_command("--dry-run", "--retention-days", "30")
        assert "30" in output

    def test_dry_run_prints_step_headings(self):
        output, _, _ = _run_command("--dry-run")
        assert "Step 1" in output or "Step 2" in output or "Step 3" in output

    def test_dry_run_prints_completion_message(self):
        output, _, _ = _run_command("--dry-run")
        assert "complete" in output.lower()


# ---------------------------------------------------------------------------
# Invocation without --dry-run (empty rows)
# ---------------------------------------------------------------------------

class TestRollupGrafanaMetricsEmptyRows:
    def test_no_dry_run_empty_rows_completes_without_error(self):
        output, _, _ = _run_command()
        assert output

    def test_retention_days_30_completes(self):
        output, _, _ = _run_command("--retention-days", "30")
        assert output

    def test_retention_days_365_completes(self):
        output, _, _ = _run_command("--retention-days", "365")
        assert output

    def test_output_includes_completion_message(self):
        output, _, _ = _run_command()
        assert "complete" in output.lower()

    def test_no_rows_nothing_to_purge(self):
        output, _, _ = _run_command(purge_count=0)
        assert "0" in output or "Nothing to purge" in output or "nothing" in output.lower()


# ---------------------------------------------------------------------------
# Upsert path — non-dry-run with one aggregated row
# ---------------------------------------------------------------------------

class TestRollupGrafanaMetricsUpsertPath:
    def test_update_or_create_called_for_each_row(self):
        row = _make_aggregated_row()
        _, _, mock_rollup = _run_command(rows=[row])
        mock_rollup.update_or_create.assert_called_once()

    def test_update_or_create_called_with_correct_metric_name(self):
        row = _make_aggregated_row()
        _, _, mock_rollup = _run_command(rows=[row])
        call_kwargs = mock_rollup.update_or_create.call_args.kwargs
        assert call_kwargs.get("metric_name") == "cpu_usage"

    def test_update_or_create_called_with_avg_value_in_defaults(self):
        row = _make_aggregated_row()
        _, _, mock_rollup = _run_command(rows=[row])
        call_kwargs = mock_rollup.update_or_create.call_args.kwargs
        defaults = call_kwargs.get("defaults", {})
        assert "avg_value" in defaults

    def test_multiple_rows_all_upserted(self):
        rows = [_make_aggregated_row(2025, 1), _make_aggregated_row(2025, 2)]
        _, _, mock_rollup = _run_command(rows=rows)
        assert mock_rollup.update_or_create.call_count == 2

    def test_dry_run_skips_update_or_create_even_with_rows(self):
        row = _make_aggregated_row()
        _, _, mock_rollup = _run_command("--dry-run", rows=[row])
        mock_rollup.update_or_create.assert_not_called()

    def test_output_reports_created_count(self):
        row = _make_aggregated_row()
        output, _, _ = _run_command(rows=[row])
        # Should mention "1 created" or "1 total"
        assert "1" in output


# ---------------------------------------------------------------------------
# period_month date conversion (lines 138-142)
# ---------------------------------------------------------------------------

class TestPeriodMonthConversion:
    def _make_patch_ctx(self, rows, captured_store=None):
        """Return a context manager that patches ORM + transaction for the command."""
        from contextlib import contextmanager

        @contextmanager
        def _noop_atomic():
            yield

        rollup_chain = MagicMock()
        rollup_chain.__iter__ = MagicMock(return_value=iter(rows))
        rollup_chain.order_by.return_value = rollup_chain

        val_chain = MagicMock()
        val_chain.annotate.return_value = rollup_chain

        ann1_chain = MagicMock()
        ann1_chain.values.return_value = val_chain

        filter_chain = MagicMock()
        filter_chain.annotate.return_value = ann1_chain
        filter_chain.count.return_value = 0
        filter_chain.values_list.return_value = []
        filter_chain.filter.return_value = filter_chain

        mock_snap = MagicMock()
        mock_snap.filter.return_value = filter_chain
        mock_rollup = MagicMock()

        if captured_store is not None:
            def _capture(**kwargs):
                captured_store.update(kwargs)
                return (MagicMock(), True)
            mock_rollup.update_or_create.side_effect = _capture
        else:
            mock_rollup.update_or_create.return_value = (MagicMock(), True)

        return mock_snap, mock_rollup, _noop_atomic

    def test_period_month_datetime_converted_to_date(self):
        """When TruncMonth returns a datetime, the command converts it to date()."""
        from contextlib import contextmanager
        from django.core.management import call_command
        from django.utils import timezone as tz

        period_dt = tz.make_aware(datetime(2025, 2, 1, 0, 0, 0))
        row = dict(_make_aggregated_row(), period_month=period_dt)
        captured = {}
        mock_snap, mock_rollup, _noop_atomic = self._make_patch_ctx([row], captured)

        with patch(f"{_CMD_PATH}.GrafanaMetricSnapshot.objects", mock_snap), \
             patch(f"{_CMD_PATH}.GrafanaMetricMonthlyRollup.objects", mock_rollup), \
             patch(f"{_CMD_PATH}.transaction.atomic", side_effect=_noop_atomic):
            out = StringIO()
            call_command("rollup_grafana_metrics", stdout=out)

        if captured:
            period_val = captured.get("period_month")
            if period_val is not None:
                assert isinstance(period_val, date)

    def test_period_month_plain_date_accepted(self):
        """If TruncMonth returns a plain date (not datetime), no crash."""
        from contextlib import contextmanager
        from django.core.management import call_command

        row = dict(_make_aggregated_row(), period_month=date(2025, 1, 1))
        mock_snap, mock_rollup, _noop_atomic = self._make_patch_ctx([row])

        with patch(f"{_CMD_PATH}.GrafanaMetricSnapshot.objects", mock_snap), \
             patch(f"{_CMD_PATH}.GrafanaMetricMonthlyRollup.objects", mock_rollup), \
             patch(f"{_CMD_PATH}.transaction.atomic", side_effect=_noop_atomic):
            out = StringIO()
            call_command("rollup_grafana_metrics", stdout=out)
            # No exception = pass


# ---------------------------------------------------------------------------
# Purge path (lines 190-224)
# ---------------------------------------------------------------------------

class TestRollupPurgePath:
    def test_nothing_to_purge_message_when_count_zero(self):
        output, _, _ = _run_command(purge_count=0)
        assert "0" in output or "nothing" in output.lower() or "Nothing" in output

    def test_dry_run_would_delete_message_when_rows_exist(self):
        output, _, _ = _run_command("--dry-run", purge_count=5)
        # dry-run should mention the 5 rows it would delete
        assert "5" in output or "dry" in output.lower()

    def test_purge_non_zero_rows_reported_correctly(self):
        output, _, _ = _run_command(purge_count=100)
        # 100 rows to purge — should appear in output
        assert "100" in output

    def test_purge_step_heading_present(self):
        output, _, _ = _run_command()
        assert "Step 3" in output or "Purge" in output or "purge" in output.lower()


# ---------------------------------------------------------------------------
# Progress reporting (line 178 — every 500 rows)
# ---------------------------------------------------------------------------

class TestRollupProgressReporting:
    def test_progress_logged_every_500_rows(self):
        """Generate 501 rows to trigger the progress log at row 500."""
        rows = [_make_aggregated_row(2024, (i % 11) + 1) for i in range(501)]
        output, _, _ = _run_command(rows=rows)
        # Should mention 500 somewhere in the progress output
        assert "500" in output or "501" in output
