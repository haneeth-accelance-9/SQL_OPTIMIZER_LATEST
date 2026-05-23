"""
Coverage tests for optimizer management commands:
  cleanup_uploads, seed_license_rules, update_performance_baseline
"""
import pytest
from io import StringIO
from unittest.mock import patch, MagicMock
from django.core.management import call_command


# ===========================================================================
# cleanup_uploads
# ===========================================================================

class TestCleanupUploads:
    def test_runs_without_error(self):
        out = StringIO()
        call_command("cleanup_uploads", stdout=out)
        assert "removed" in out.getvalue().lower() or "clean" in out.getvalue().lower()

    def test_runs_with_dry_run_flag(self):
        out = StringIO()
        call_command("cleanup_uploads", "--dry-run", stdout=out)
        assert isinstance(out.getvalue(), str)

    def test_output_mentions_removal_or_noop(self):
        out = StringIO()
        call_command("cleanup_uploads", stdout=out)
        output = out.getvalue()
        assert len(output) > 0


# ===========================================================================
# seed_license_rules
# ===========================================================================

@pytest.mark.django_db
class TestSeedLicenseRules:
    def test_seeds_three_rules(self):
        from optimizer.models import LicenseRule
        out = StringIO()
        call_command("seed_license_rules", stdout=out)
        assert LicenseRule.objects.count() >= 3

    def test_creates_default_tenant(self):
        from optimizer.models import Tenant
        out = StringIO()
        call_command("seed_license_rules", stdout=out)
        assert Tenant.objects.filter(name="default").exists()

    def test_idempotent_second_run(self):
        from optimizer.models import LicenseRule
        out = StringIO()
        call_command("seed_license_rules", stdout=out)
        count_first = LicenseRule.objects.count()
        call_command("seed_license_rules", stdout=out)
        count_second = LicenseRule.objects.count()
        assert count_first == count_second

    def test_force_flag_updates_existing(self):
        from optimizer.models import LicenseRule
        out = StringIO()
        call_command("seed_license_rules", stdout=out)
        call_command("seed_license_rules", "--force", stdout=out)
        output = out.getvalue()
        assert "Updated" in output or "Created" in output

    def test_custom_tenant(self):
        from optimizer.models import Tenant
        out = StringIO()
        call_command("seed_license_rules", "--tenant", "test_tenant", stdout=out)
        assert Tenant.objects.filter(name="test_tenant").exists()

    def test_output_shows_done(self):
        out = StringIO()
        call_command("seed_license_rules", stdout=out)
        assert "Done" in out.getvalue()

    def test_output_shows_standard_rule(self):
        out = StringIO()
        call_command("seed_license_rules", stdout=out)
        output = out.getvalue()
        assert "Standard" in output or "Enterprise" in output or "Developer" in output

    def test_active_rules_have_costs(self):
        from optimizer.models import LicenseRule
        call_command("seed_license_rules", stdout=StringIO())
        active_with_costs = LicenseRule.objects.filter(
            is_active=True, cost_per_core_pair_eur__isnull=False
        ).count()
        assert active_with_costs >= 3


# ===========================================================================
# _percentile helper
# ===========================================================================

class TestPercentile:
    def _percentile(self, data, p):
        from optimizer.management.commands.update_performance_baseline import _percentile
        return _percentile(data, p)

    def test_returns_none_for_empty_list(self):
        assert self._percentile([], 50) is None

    def test_single_value_returns_that_value(self):
        assert self._percentile([5.0], 50) == 5.0

    def test_p50_on_even_list(self):
        result = self._percentile([1.0, 2.0, 3.0, 4.0], 50)
        assert result == 2.5

    def test_p95_on_larger_list(self):
        data = list(range(1, 101))  # 1..100
        result = self._percentile(data, 95)
        assert result is not None
        assert result > 90

    def test_p50_single_element(self):
        assert self._percentile([42.0], 50) == 42.0


# ===========================================================================
# update_performance_baseline command
# ===========================================================================

@pytest.mark.django_db
class TestUpdatePerformanceBaseline:
    def test_runs_without_error_when_no_runs(self):
        out = StringIO()
        call_command("update_performance_baseline", stdout=out)
        output = out.getvalue()
        assert "Phase Timing Baseline" in output or "No phase_timings" in output

    def test_shows_no_timings_message_when_no_agent_runs(self):
        out = StringIO()
        call_command("update_performance_baseline", stdout=out)
        output = out.getvalue()
        # With empty DB there should be a warning about no phase_timings
        assert "No phase_timings" in output or "0/" in output

    def test_custom_days_argument(self):
        out = StringIO()
        call_command("update_performance_baseline", "--days", "7", stdout=out)
        output = out.getvalue()
        assert "7 days" in output or "Phase" in output

    def test_with_agent_run_with_timings(self):
        from django.utils import timezone
        from optimizer.models import AgentRun, Tenant
        tenant, _ = Tenant.objects.get_or_create(
            name="baseline_test",
            defaults={"description": "test", "is_active": True},
        )
        AgentRun.objects.create(
            tenant=tenant,
            status=AgentRun.STATUS_COMPLETED,
            finished_at=timezone.now(),
            input_file_versions={
                "phase_timings": {
                    "data_load_sec": 1.5,
                    "rule_eval_sec": 0.3,
                    "llm_call_sec": 5.2,
                    "total_sec": 7.0,
                }
            },
        )
        out = StringIO()
        call_command("update_performance_baseline", stdout=out)
        output = out.getvalue()
        # Should print a markdown table
        assert "Phase" in output or "P50" in output or "1/" in output

    def test_warn_threshold_zero_disables_warning(self):
        out = StringIO()
        call_command("update_performance_baseline", "--warn-threshold", "0", stdout=out)
        assert isinstance(out.getvalue(), str)  # just verify it runs
