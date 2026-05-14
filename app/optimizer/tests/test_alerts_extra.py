"""
Unit tests for optimizer.services.alerts — all pure functions, no DB required.
"""
import pytest

from optimizer.services.alerts import (
    _alert,
    _normalize_filter,
    build_alert_page_context,
    build_alert_summary,
    filter_alerts,
    get_dummy_alerts,
)


# ===========================================================================
# _alert factory
# ===========================================================================

class TestAlertFactory:
    def test_returns_dict_with_all_keys(self):
        a = _alert("A1", "Title", "Msg", "High", "Cost", "Open", "Src", "2026-01-01")
        assert a["alert_id"] == "A1"
        assert a["title"] == "Title"
        assert a["message"] == "Msg"
        assert a["severity"] == "High"
        assert a["category"] == "Cost"
        assert a["status"] == "Open"
        assert a["source"] == "Src"
        assert a["created_at"] == "2026-01-01"

    def test_all_eight_keys_present(self):
        a = _alert("X", "T", "M", "Low", "Cat", "Resolved", "Src", "2026-01-01")
        assert set(a.keys()) == {"alert_id", "title", "message", "severity", "category", "status", "source", "created_at"}


# ===========================================================================
# get_dummy_alerts
# ===========================================================================

class TestGetDummyAlerts:
    def test_returns_list(self):
        alerts = get_dummy_alerts()
        assert isinstance(alerts, list)

    def test_returns_at_least_one_alert(self):
        alerts = get_dummy_alerts()
        assert len(alerts) > 0

    def test_each_alert_has_required_keys(self):
        required = {"alert_id", "title", "message", "severity", "category", "status", "source", "created_at"}
        for alert in get_dummy_alerts():
            assert required.issubset(set(alert.keys()))

    def test_contains_high_severity(self):
        severities = {a["severity"] for a in get_dummy_alerts()}
        assert "High" in severities

    def test_contains_medium_severity(self):
        severities = {a["severity"] for a in get_dummy_alerts()}
        assert "Medium" in severities

    def test_contains_low_severity(self):
        severities = {a["severity"] for a in get_dummy_alerts()}
        assert "Low" in severities

    def test_deterministic(self):
        assert get_dummy_alerts() == get_dummy_alerts()


# ===========================================================================
# _normalize_filter
# ===========================================================================

class TestNormalizeFilter:
    def test_lowercases(self):
        assert _normalize_filter("HIGH") == "high"

    def test_strips_whitespace(self):
        assert _normalize_filter("  high  ") == "high"

    def test_none_returns_empty_string(self):
        assert _normalize_filter(None) == ""

    def test_empty_string_stays_empty(self):
        assert _normalize_filter("") == ""


# ===========================================================================
# build_alert_summary
# ===========================================================================

class TestBuildAlertSummary:
    def test_empty_list(self):
        summary = build_alert_summary([])
        assert summary == {"total": 0, "high": 0, "medium": 0, "low": 0}

    def test_counts_severities(self):
        alerts = [
            {"severity": "High"},
            {"severity": "High"},
            {"severity": "Medium"},
            {"severity": "Low"},
        ]
        summary = build_alert_summary(alerts)
        assert summary["total"] == 4
        assert summary["high"] == 2
        assert summary["medium"] == 1
        assert summary["low"] == 1

    def test_full_dummy_alerts(self):
        alerts = get_dummy_alerts()
        summary = build_alert_summary(alerts)
        assert summary["total"] == len(alerts)
        assert summary["high"] + summary["medium"] + summary["low"] <= summary["total"]

    def test_keys_present(self):
        s = build_alert_summary([])
        assert set(s.keys()) == {"total", "high", "medium", "low"}


# ===========================================================================
# filter_alerts
# ===========================================================================

class TestFilterAlerts:
    def _alerts(self):
        return get_dummy_alerts()

    def test_no_filters_returns_all(self):
        all_alerts = self._alerts()
        result = filter_alerts(all_alerts)
        assert result == all_alerts

    def test_severity_filter_high(self):
        result = filter_alerts(self._alerts(), severity="High")
        assert all(a["severity"] == "High" for a in result)
        assert len(result) > 0

    def test_severity_filter_case_insensitive(self):
        result_upper = filter_alerts(self._alerts(), severity="HIGH")
        result_lower = filter_alerts(self._alerts(), severity="high")
        assert result_upper == result_lower

    def test_severity_filter_medium(self):
        result = filter_alerts(self._alerts(), severity="Medium")
        assert all(a["severity"] == "Medium" for a in result)

    def test_status_filter_open(self):
        result = filter_alerts(self._alerts(), status="Open")
        assert all(a["status"] == "Open" for a in result)

    def test_status_filter_resolved(self):
        result = filter_alerts(self._alerts(), status="Resolved")
        assert all(a["status"] == "Resolved" for a in result)

    def test_category_filter(self):
        result = filter_alerts(self._alerts(), category="Cost")
        assert all(a["category"] == "Cost" for a in result)

    def test_query_filter_matches_title(self):
        result = filter_alerts(self._alerts(), query="cost spike")
        assert len(result) > 0
        for a in result:
            haystack = (a["alert_id"] + a["title"] + a["message"] + a["source"] + a["category"]).lower()
            assert "cost spike" in haystack

    def test_query_filter_no_match(self):
        result = filter_alerts(self._alerts(), query="XXXXXXXX_IMPOSSIBLE_STRING_XXXXX")
        assert result == []

    def test_combined_severity_and_status(self):
        result = filter_alerts(self._alerts(), severity="High", status="Open")
        assert all(a["severity"] == "High" and a["status"] == "Open" for a in result)

    def test_empty_alerts_returns_empty(self):
        assert filter_alerts([], severity="High") == []


# ===========================================================================
# build_alert_page_context
# ===========================================================================

class TestBuildAlertPageContext:
    def _params(self, **kwargs):
        class FakeParams(dict):
            def get(self, key, default=None):
                return super().get(key, default)
        return FakeParams(kwargs)

    def test_returns_dict_with_required_keys(self):
        ctx = build_alert_page_context(self._params())
        assert "alerts" in ctx
        assert "alert_summary" in ctx
        assert "alert_total_count" in ctx
        assert "alert_filter_options" in ctx

    def test_no_filters_returns_all_alerts(self):
        ctx = build_alert_page_context(self._params())
        all_alerts = get_dummy_alerts()
        assert ctx["alert_total_count"] == len(all_alerts)
        assert len(ctx["alerts"]) == len(all_alerts)

    def test_severity_filter_applied(self):
        ctx = build_alert_page_context(self._params(severity="High"))
        assert all(a["severity"] == "High" for a in ctx["alerts"])
        assert ctx["selected_severity"] == "High"

    def test_status_filter_applied(self):
        ctx = build_alert_page_context(self._params(status="Open"))
        assert all(a["status"] == "Open" for a in ctx["alerts"])

    def test_search_query_applied(self):
        ctx = build_alert_page_context(self._params(q="retired"))
        assert len(ctx["alerts"]) > 0

    def test_filter_options_has_severities(self):
        ctx = build_alert_page_context(self._params())
        opts = ctx["alert_filter_options"]
        assert "severities" in opts
        assert "High" in opts["severities"]

    def test_filter_options_has_categories(self):
        ctx = build_alert_page_context(self._params())
        opts = ctx["alert_filter_options"]
        assert "categories" in opts
        assert len(opts["categories"]) > 0

    def test_filter_options_has_statuses(self):
        ctx = build_alert_page_context(self._params())
        opts = ctx["alert_filter_options"]
        assert "statuses" in opts
        assert "Open" in opts["statuses"]

    def test_title_is_alerts(self):
        ctx = build_alert_page_context(self._params())
        assert ctx["title"] == "Alerts"
