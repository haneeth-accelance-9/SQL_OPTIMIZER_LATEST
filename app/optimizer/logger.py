"""PyLogger — centralised logging for SQL License Optimizer.

Drop-in usage (already used everywhere in the codebase):
    from optimizer.logger import get_logger
    logger = get_logger(__name__)

All calls (debug / info / warning / error / critical) are routed
automatically by Django's LOGGING config in settings.py to:

    logs/
      YYYY-MM-DD/
        debug.log      ← DEBUG records
        info.log       ← INFO records
        warning.log    ← WARNING records
        error.log      ← ERROR + CRITICAL records

A new date-directory is opened automatically at midnight; the previous
day's files are never touched again (zero-dependency rotation).

The handler is thread-safe (RLock per instance) and gunicorn-safe
(each worker keeps its own file descriptor, all writing to the same
append-mode file — safe on Linux/Windows for log files).
"""
from __future__ import annotations

import contextvars
import json
import logging
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Core handler
# ─────────────────────────────────────────────────────────────────────────────

class DailyLevelFileHandler(logging.Handler):
    """
    Writes log records to  <log_dir>/YYYY-MM-DD/<filename>.

    Parameters
    ----------
    log_dir  : str | Path
        Root directory that will contain the daily sub-directories.
    filename : str
        Log file name inside each daily directory (e.g. ``"debug.log"``).
    min_level : str | int
        Minimum level this handler will emit (e.g. ``"DEBUG"``, ``"ERROR"``).
        The handler also respects the level set by Django's LOGGING config via
        ``handler.setLevel()``, whichever is higher wins.
    """

    def __init__(self, log_dir: str | Path, filename: str, min_level: str | int = "DEBUG") -> None:
        super().__init__()
        self._log_dir = Path(log_dir)
        self._filename = filename
        self._min_level: int = (
            logging.getLevelName(min_level) if isinstance(min_level, str) else min_level
        )
        self._current_date: Optional[str] = None
        self._file: Optional[object] = None
        self._lock = threading.RLock()

    # ── internal ──────────────────────────────────────────────────────────────

    def _open_file(self, today: str):
        """Open (or re-open) the file for *today*, creating the directory."""
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
        day_dir = self._log_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        self._file = open(day_dir / self._filename, "a", encoding="utf-8")  # noqa: WPS515
        self._current_date = today

    def _ensure_open(self) -> None:
        today = date.today().isoformat()
        if today != self._current_date:
            self._open_file(today)

    # ── public logging.Handler interface ─────────────────────────────────────

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < self._min_level:
            return
        with self._lock:
            try:
                self._ensure_open()
                msg = self.format(record)
                self._file.write(msg + "\n")
                self._file.flush()
            except Exception:
                self.handleError(record)

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None
        super().close()


# ─────────────────────────────────────────────────────────────────────────────
# Request-ID context  (set by RequestIdMiddleware; read by RequestIdFilter)
# ─────────────────────────────────────────────────────────────────────────────

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def set_request_id(rid: str) -> None:
    """Called by RequestIdMiddleware to bind the current request-ID to this thread/task."""
    _request_id_var.set(rid)


def get_request_id() -> str:
    """Return the request-ID for the currently executing request, or '-' outside a request."""
    return _request_id_var.get()


# ─────────────────────────────────────────────────────────────────────────────
# JsonFormatter — structured one-line JSON per log record
# ─────────────────────────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """
    Emits each log record as a single JSON line with exactly these fields::

        {
          "time":       "2026-05-11T16:24:37.123+00:00",   ← ISO-8601 UTC ms
          "level":      "INFO",
          "logger":     "optimizer.views",
          "request_id": "a1b2c3d4e5f6",                   ← '-' outside a request
          "message":    "Agent run started run_id=abc"
        }

    If the record carries exception info a sixth field ``"exc_info"`` is appended.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = (
            datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
        )
        payload: dict = {
            "time":       ts,
            "level":      record.levelname,
            "logger":     record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message":    record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger wired to all handlers configured in settings.LOGGING.

    Usage (module-level, same pattern already used across the codebase)::

        from optimizer.logger import get_logger
        logger = get_logger(__name__)

    Then use normally::

        logger.debug("detailed trace")
        logger.info("agent run started run_id=%s", run_id)
        logger.warning("cache miss for key=%s", key)
        logger.error("DB query failed: %s", exc, exc_info=True)
        logger.critical("unrecoverable error — shutting down")
    """
    return logging.getLogger(name)
