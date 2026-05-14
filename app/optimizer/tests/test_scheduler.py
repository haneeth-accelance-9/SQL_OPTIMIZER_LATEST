"""
Unit tests for optimizer.scheduler.
All tests use pure mocks — no Django DB, no real APScheduler.
"""
import logging
import os
from unittest.mock import MagicMock, call, patch

import pytest

import optimizer.scheduler as sched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_scheduler():
    """Reset the module-level _scheduler global to None after each test."""
    sched._scheduler = None


# ---------------------------------------------------------------------------
# _run()
# ---------------------------------------------------------------------------

class TestRun:
    def test_success_calls_call_command(self):
        with patch("optimizer.scheduler.call_command") as mock_cmd:
            sched._run("fetch_usu_data")
        mock_cmd.assert_called_once_with("fetch_usu_data")

    def test_success_does_not_raise(self):
        with patch("optimizer.scheduler.call_command"):
            sched._run("rollup_grafana_metrics")  # should not raise

    def test_exception_is_swallowed_and_logged(self):
        with patch("optimizer.scheduler.call_command", side_effect=RuntimeError("boom")):
            with patch.object(sched.logger, "error") as mock_log:
                sched._run("bad_command")
        assert mock_log.called
        args = mock_log.call_args[0]
        assert "bad_command" in args[1]

    def test_exception_does_not_propagate(self):
        with patch("optimizer.scheduler.call_command", side_effect=Exception("err")):
            try:
                sched._run("any_command")
            except Exception:
                pytest.fail("_run() should not propagate exceptions")

    def test_logs_start_message(self):
        with patch("optimizer.scheduler.call_command"):
            with patch.object(sched.logger, "info") as mock_info:
                sched._run("fetch_usu_data")
        # First call should mention starting the command
        first_msg = mock_info.call_args_list[0][0]
        assert "fetch_usu_data" in str(first_msg)


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------

class TestStart:
    def setup_method(self):
        _reset_scheduler()

    def teardown_method(self):
        _reset_scheduler()

    def test_run_scheduler_false_env_var_skips_start(self):
        with patch.dict(os.environ, {"RUN_SCHEDULER": "false"}):
            with patch("optimizer.scheduler.BackgroundScheduler") as mock_bs:
                sched.start()
        mock_bs.assert_not_called()
        assert sched._scheduler is None

    def test_run_scheduler_false_case_insensitive(self):
        with patch.dict(os.environ, {"RUN_SCHEDULER": "FALSE"}):
            with patch("optimizer.scheduler.BackgroundScheduler") as mock_bs:
                sched.start()
        mock_bs.assert_not_called()

    def test_run_scheduler_false_logs_disabled_message(self):
        with patch.dict(os.environ, {"RUN_SCHEDULER": "false"}):
            with patch("optimizer.scheduler.BackgroundScheduler"):
                with patch.object(sched.logger, "info") as mock_info:
                    sched.start()
        logged_msgs = " ".join(str(c) for c in mock_info.call_args_list)
        assert "disabled" in logged_msgs or "false" in logged_msgs.lower()

    def test_already_running_is_idempotent(self):
        fake_scheduler = MagicMock()
        fake_scheduler.running = True
        sched._scheduler = fake_scheduler

        with patch("optimizer.scheduler.BackgroundScheduler") as mock_bs:
            sched.start()
        mock_bs.assert_not_called()

    def test_normal_start_creates_scheduler(self):
        with patch.dict(os.environ, {"RUN_SCHEDULER": "true"}):
            fake_scheduler = MagicMock()
            fake_scheduler.get_jobs.return_value = [
                MagicMock(id="fetch_usu_data"),
                MagicMock(id="fetch_java_usu_data"),
                MagicMock(id="fetch_grafana_metrics"),
                MagicMock(id="rollup_grafana_metrics"),
            ]
            with patch("optimizer.scheduler.BackgroundScheduler", return_value=fake_scheduler):
                with patch("optimizer.scheduler.CronTrigger"):
                    sched.start()
        fake_scheduler.start.assert_called_once()

    def test_normal_start_adds_four_jobs(self):
        with patch.dict(os.environ, {"RUN_SCHEDULER": "true"}):
            fake_scheduler = MagicMock()
            fake_scheduler.get_jobs.return_value = [
                MagicMock(id="fetch_usu_data"),
                MagicMock(id="fetch_java_usu_data"),
                MagicMock(id="fetch_grafana_metrics"),
                MagicMock(id="rollup_grafana_metrics"),
            ]
            with patch("optimizer.scheduler.BackgroundScheduler", return_value=fake_scheduler):
                with patch("optimizer.scheduler.CronTrigger"):
                    sched.start()
        assert fake_scheduler.add_job.call_count == 4

    def test_normal_start_job_ids_correct(self):
        with patch.dict(os.environ, {"RUN_SCHEDULER": "true"}):
            fake_scheduler = MagicMock()
            fake_scheduler.get_jobs.return_value = []
            with patch("optimizer.scheduler.BackgroundScheduler", return_value=fake_scheduler):
                with patch("optimizer.scheduler.CronTrigger"):
                    sched.start()
        job_ids = [c.kwargs.get("id") or c[1].get("id") for c in fake_scheduler.add_job.call_args_list]
        # Collect ids from keyword args
        ids_passed = [c.kwargs["id"] for c in fake_scheduler.add_job.call_args_list]
        expected = {"fetch_usu_data", "fetch_java_usu_data", "fetch_grafana_metrics", "rollup_grafana_metrics"}
        assert set(ids_passed) == expected

    def test_normal_start_logs_started_message(self):
        with patch.dict(os.environ, {"RUN_SCHEDULER": "true"}):
            fake_scheduler = MagicMock()
            fake_scheduler.get_jobs.return_value = []
            with patch("optimizer.scheduler.BackgroundScheduler", return_value=fake_scheduler):
                with patch("optimizer.scheduler.CronTrigger"):
                    with patch.object(sched.logger, "info") as mock_info:
                        sched.start()
        logged = " ".join(str(c) for c in mock_info.call_args_list)
        assert "started" in logged.lower()

    def test_default_run_scheduler_env_is_true(self):
        """When RUN_SCHEDULER is not set, scheduler should start."""
        env_without_var = {k: v for k, v in os.environ.items() if k != "RUN_SCHEDULER"}
        fake_scheduler = MagicMock()
        fake_scheduler.get_jobs.return_value = []
        with patch.dict(os.environ, env_without_var, clear=True):
            with patch("optimizer.scheduler.BackgroundScheduler", return_value=fake_scheduler):
                with patch("optimizer.scheduler.CronTrigger"):
                    sched.start()
        fake_scheduler.start.assert_called_once()


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------

class TestStop:
    def setup_method(self):
        _reset_scheduler()

    def teardown_method(self):
        _reset_scheduler()

    def test_stop_when_running_calls_shutdown(self):
        fake_scheduler = MagicMock()
        fake_scheduler.running = True
        sched._scheduler = fake_scheduler

        sched.stop()
        fake_scheduler.shutdown.assert_called_once_with(wait=False)

    def test_stop_when_running_logs_stopped(self):
        fake_scheduler = MagicMock()
        fake_scheduler.running = True
        sched._scheduler = fake_scheduler

        with patch.object(sched.logger, "info") as mock_info:
            sched.stop()
        logged = " ".join(str(c) for c in mock_info.call_args_list)
        assert "stopped" in logged.lower()

    def test_stop_when_no_scheduler_is_noop(self):
        sched._scheduler = None
        # Should not raise
        sched.stop()

    def test_stop_when_scheduler_not_running_is_noop(self):
        fake_scheduler = MagicMock()
        fake_scheduler.running = False
        sched._scheduler = fake_scheduler

        sched.stop()
        fake_scheduler.shutdown.assert_not_called()

    def test_stop_when_scheduler_is_none_does_not_raise(self):
        sched._scheduler = None
        try:
            sched.stop()
        except Exception:
            pytest.fail("stop() should not raise when _scheduler is None")
