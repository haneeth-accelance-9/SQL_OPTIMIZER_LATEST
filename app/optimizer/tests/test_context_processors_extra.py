"""
Unit tests for optimizer.context_processors — no DB required.
"""
import pytest

from optimizer.context_processors import notification_context


class _AuthenticatedRequest:
    class _User:
        is_authenticated = True

    user = _User()


class _UnauthenticatedRequest:
    class _User:
        is_authenticated = False

    user = _User()


class _NoUserRequest:
    pass


class TestNotificationContext:
    def test_unauthenticated_returns_empty_context(self):
        ctx = notification_context(_UnauthenticatedRequest())
        assert ctx["header_alerts"] == []
        assert ctx["header_alert_count"] == 0
        assert ctx["header_alert_summary"]["total"] == 0

    def test_no_user_returns_empty_context(self):
        ctx = notification_context(_NoUserRequest())
        assert ctx["header_alerts"] == []
        assert ctx["header_alert_count"] == 0

    def test_authenticated_returns_alerts(self):
        ctx = notification_context(_AuthenticatedRequest())
        assert isinstance(ctx["header_alerts"], list)
        assert len(ctx["header_alerts"]) > 0

    def test_authenticated_alert_count_positive(self):
        ctx = notification_context(_AuthenticatedRequest())
        assert ctx["header_alert_count"] > 0

    def test_authenticated_summary_has_required_keys(self):
        ctx = notification_context(_AuthenticatedRequest())
        summary = ctx["header_alert_summary"]
        assert set(summary.keys()) == {"total", "high", "medium", "low"}

    def test_authenticated_alerts_capped_at_four(self):
        ctx = notification_context(_AuthenticatedRequest())
        assert len(ctx["header_alerts"]) <= 4
