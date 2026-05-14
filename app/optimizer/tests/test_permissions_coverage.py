"""
Coverage tests for optimizer.permissions — focuses on the branches missed:
  - _forbidden_response(): API path (lines 55-61) and HTML redirect (lines 63-64)
  - require_role() wrapper: role not in allowed_roles → blocked (lines 75-78)
                            role in allowed roles → view called

Uses RequestFactory + in-memory message storage.
No @pytest.mark.django_db — we use CookieStorage (no DB) for messages.
"""
import pytest
from django.contrib.messages.storage.cookie import CookieStorage
from django.http import JsonResponse
from django.test import RequestFactory

from optimizer.permissions import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_VIEWER,
    _forbidden_response,
    require_role,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeUser:
    def __init__(self, role, authenticated=True):
        self.is_authenticated = authenticated
        self.username = "testuser"

        class _Profile:
            pass
        profile = _Profile()
        profile.role = role
        self.optimizer_profile = profile


def _attach_messages(request):
    """Attach a cookie-based (no-DB) message storage to the request."""
    request._messages = CookieStorage(request)


def _make_api_request(path="/api/data/"):
    factory = RequestFactory()
    request = factory.get(path)
    request.user = _FakeUser(ROLE_VIEWER, authenticated=False)
    _attach_messages(request)
    return request


def _make_html_request(path="/results/"):
    factory = RequestFactory()
    request = factory.get(path)
    request.user = _FakeUser(ROLE_VIEWER, authenticated=True)
    _attach_messages(request)
    return request


# ---------------------------------------------------------------------------
# _forbidden_response — API branch (lines 55-61)
# ---------------------------------------------------------------------------

class TestForbiddenResponseApi:
    def test_api_request_returns_json_response(self):
        request = _make_api_request()
        response = _forbidden_response(request, ROLE_VIEWER, [ROLE_EDITOR])
        assert isinstance(response, JsonResponse)

    def test_api_request_returns_403_status(self):
        request = _make_api_request()
        response = _forbidden_response(request, ROLE_VIEWER, [ROLE_EDITOR])
        assert response.status_code == 403

    def test_api_response_body_has_error_key(self):
        import json
        request = _make_api_request()
        response = _forbidden_response(request, ROLE_VIEWER, [ROLE_EDITOR])
        data = json.loads(response.content)
        assert "error" in data

    def test_api_response_body_has_detail_key(self):
        import json
        request = _make_api_request()
        response = _forbidden_response(request, ROLE_VIEWER, [ROLE_EDITOR])
        data = json.loads(response.content)
        assert "detail" in data

    def test_api_response_detail_mentions_role(self):
        import json
        request = _make_api_request()
        response = _forbidden_response(request, ROLE_VIEWER, [ROLE_EDITOR])
        data = json.loads(response.content)
        assert ROLE_VIEWER in data["detail"]

    def test_json_accept_header_triggers_api_branch(self):
        import json
        factory = RequestFactory()
        request = factory.get("/some-page/", HTTP_ACCEPT="application/json")
        request.user = _FakeUser(ROLE_VIEWER)
        _attach_messages(request)
        response = _forbidden_response(request, ROLE_VIEWER, [ROLE_ADMIN])
        assert isinstance(response, JsonResponse)
        assert response.status_code == 403

    def test_bearer_auth_header_triggers_api_branch(self):
        factory = RequestFactory()
        request = factory.get("/some-view/", HTTP_AUTHORIZATION="Bearer token123")
        request.user = _FakeUser(ROLE_VIEWER)
        _attach_messages(request)
        response = _forbidden_response(request, ROLE_VIEWER, [ROLE_ADMIN])
        assert isinstance(response, JsonResponse)

    def test_json_content_type_triggers_api_branch(self):
        factory = RequestFactory()
        request = factory.post("/api/trigger/", content_type="application/json")
        request.user = _FakeUser(ROLE_VIEWER)
        _attach_messages(request)
        response = _forbidden_response(request, ROLE_VIEWER, [ROLE_ADMIN])
        assert isinstance(response, JsonResponse)


# ---------------------------------------------------------------------------
# _forbidden_response — HTML (redirect) branch (lines 63-64)
# ---------------------------------------------------------------------------

class TestForbiddenResponseHtml:
    def test_html_request_returns_redirect(self):
        request = _make_html_request("/results/")
        response = _forbidden_response(request, ROLE_VIEWER, [ROLE_EDITOR])
        assert response.status_code == 302

    def test_html_redirect_goes_to_dashboard(self):
        request = _make_html_request("/results/")
        response = _forbidden_response(request, ROLE_VIEWER, [ROLE_EDITOR])
        assert "dashboard" in response["Location"]

    def test_html_request_adds_error_message(self):
        from django.contrib.messages import get_messages
        request = _make_html_request("/upload/")
        _forbidden_response(request, ROLE_VIEWER, [ROLE_EDITOR])
        msgs = list(get_messages(request))
        assert len(msgs) >= 1
        assert any("permission" in str(m).lower() for m in msgs)

    def test_html_with_html_accept_returns_redirect(self):
        factory = RequestFactory()
        request = factory.get("/dashboard/", HTTP_ACCEPT="text/html")
        request.user = _FakeUser(ROLE_VIEWER)
        _attach_messages(request)
        response = _forbidden_response(request, ROLE_VIEWER, [ROLE_EDITOR])
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# require_role() — wrapper behaviour (lines 75-78)
# ---------------------------------------------------------------------------

class TestRequireRoleWrapper:
    def _make_request(self, role, path="/dashboard/", is_api=False):
        factory = RequestFactory()
        if is_api:
            request = factory.get(path, HTTP_ACCEPT="application/json")
        else:
            request = factory.get(path)
        request.user = _FakeUser(role)
        _attach_messages(request)
        return request

    def test_viewer_blocked_from_editor_only_view(self):
        @require_role(ROLE_EDITOR, ROLE_ADMIN)
        def editor_view(request):
            return "ok"

        request = self._make_request(ROLE_VIEWER, path="/results/")
        response = editor_view(request)
        # Should be a redirect (HTML) or 403 (API)
        assert response.status_code in (302, 403)

    def test_viewer_blocked_from_admin_only_view(self):
        @require_role(ROLE_ADMIN)
        def admin_view(request):
            return "ok"

        request = self._make_request(ROLE_VIEWER, path="/admin-page/")
        response = admin_view(request)
        assert response.status_code in (302, 403)

    def test_editor_blocked_from_admin_only_view(self):
        @require_role(ROLE_ADMIN)
        def admin_view(request):
            return "ok"

        request = self._make_request(ROLE_EDITOR, path="/admin-page/")
        response = admin_view(request)
        assert response.status_code in (302, 403)

    def test_editor_allowed_for_editor_view(self):
        @require_role(ROLE_EDITOR, ROLE_ADMIN)
        def editor_view(request):
            return "allowed"

        request = self._make_request(ROLE_EDITOR)
        result = editor_view(request)
        assert result == "allowed"

    def test_admin_allowed_for_editor_view(self):
        @require_role(ROLE_EDITOR, ROLE_ADMIN)
        def editor_view(request):
            return "allowed"

        request = self._make_request(ROLE_ADMIN)
        result = editor_view(request)
        assert result == "allowed"

    def test_admin_allowed_for_admin_only_view(self):
        @require_role(ROLE_ADMIN)
        def admin_view(request):
            return "admin-ok"

        request = self._make_request(ROLE_ADMIN)
        result = admin_view(request)
        assert result == "admin-ok"

    def test_viewer_api_request_gets_403_json(self):
        """Viewer hitting an API endpoint should get JSON 403, not a redirect."""
        @require_role(ROLE_EDITOR)
        def api_view(request):
            return "ok"

        request = self._make_request(ROLE_VIEWER, path="/api/run/", is_api=True)
        response = api_view(request)
        assert response.status_code == 403
        assert isinstance(response, JsonResponse)

    def test_blocked_response_is_not_the_view_result(self):
        """When blocked, the wrapped view function is never called."""
        called = []

        @require_role(ROLE_ADMIN)
        def sensitive_view(request):
            called.append(True)
            return "sensitive"

        request = self._make_request(ROLE_VIEWER)
        sensitive_view(request)
        assert called == []

    def test_allowed_view_is_actually_called(self):
        """When permitted, the wrapped view function is called exactly once."""
        called = []

        @require_role(ROLE_EDITOR)
        def my_view(request):
            called.append(True)
            return "result"

        request = self._make_request(ROLE_EDITOR)
        my_view(request)
        assert called == [True]
