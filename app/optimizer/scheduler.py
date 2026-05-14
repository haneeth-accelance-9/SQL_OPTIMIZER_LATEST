"""
Background scheduler for SQL Optimizer.

Uses APScheduler (BackgroundScheduler) started inside Django's AppConfig.ready().
Runs automatically when the Django process starts — no external cron, no Azure
infrastructure setup required.

Schedules (all UTC):
  fetch_usu_data           every Saturday at 02:00
  fetch_java_usu_data      every Saturday at 02:30
  fetch_grafana_metrics    every hour, Monday–Friday
  rollup_grafana_metrics   1st of every month at 03:00
"""

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management import call_command

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run(command: str) -> None:
    """Wrapper so APScheduler can call a management command by name."""
    logger.info("scheduler: starting %s", command)
    try:
        call_command(command)
        logger.info("scheduler: %s completed successfully", command)
    except Exception as exc:
        logger.error("scheduler: %s failed — %s", command, exc, exc_info=True)


def start() -> None:
    """Start the background scheduler. Safe to call multiple times (no-op after first call)."""
    global _scheduler

    # Guard: skip in test runs and management commands that are not gunicorn/runserver.
    # RUN_SCHEDULER env var can be set to "false" to disable (e.g. during migrations).
    if os.environ.get("RUN_SCHEDULER", "true").lower() == "false":
        logger.info("scheduler: disabled via RUN_SCHEDULER=false")
        return

    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="UTC")

    # ── fetch_usu_data — every Saturday at 02:00 UTC ─────────────────────────
    _scheduler.add_job(
        _run,
        trigger=CronTrigger(day_of_week="sat", hour=2, minute=0, timezone="UTC"),
        args=["fetch_usu_data"],
        id="fetch_usu_data",
        replace_existing=True,
        misfire_grace_time=3600,    # run even if up to 1h late (container restart)
    )

    # ── fetch_java_usu_data — every Saturday at 02:30 UTC ────────────────────
    _scheduler.add_job(
        _run,
        trigger=CronTrigger(day_of_week="sat", hour=2, minute=30, timezone="UTC"),
        args=["fetch_java_usu_data"],
        id="fetch_java_usu_data",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── fetch_grafana_metrics — every hour, Monday–Friday UTC ────────────────
    _scheduler.add_job(
        _run,
        trigger=CronTrigger(day_of_week="mon-fri", hour="*", minute=0, timezone="UTC"),
        args=["fetch_grafana_metrics"],
        id="fetch_grafana_metrics",
        replace_existing=True,
        misfire_grace_time=1800,    # run even if up to 30 min late
    )

    # ── rollup_grafana_metrics — 1st of every month at 03:00 UTC ─────────────
    _scheduler.add_job(
        _run,
        trigger=CronTrigger(day=1, hour=3, minute=0, timezone="UTC"),
        args=["rollup_grafana_metrics"],
        id="rollup_grafana_metrics",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(
        "scheduler: started with %d jobs: %s",
        len(_scheduler.get_jobs()),
        [j.id for j in _scheduler.get_jobs()],
    )


def stop() -> None:
    """Gracefully shut down the scheduler (called on Django shutdown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler: stopped")
