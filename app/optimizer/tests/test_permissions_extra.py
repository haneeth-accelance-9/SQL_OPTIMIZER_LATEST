"""
Unit tests for pure/semi-pure functions in optimizer.permissions.
No database required — only mocks.
"""
import pytest

from optimizer.permissions import (
    get_user_role,
    _is_api_request,
    editor_or_above,
    admin_only,
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_VIEWER,
)


# ===========================================================================
# get_user_role
# ===========================================================================

class TestGetUserRole:
    def _user(self, role, authenticated=True):
        class FakeProfile:
            def __init__(self, r):
                self.role = r

        class FakeUser:
            def __init__(self, r, auth):
                self.is_authenticated = auth
                self.optimizer_profile = FakeProfile(r)

        return FakeUser(role, authenticated)

    def test_none_user_returns_viewer(self):
        assert get_user_role(None) == ROLE_VIEWER

    def test_unauthenticated_user_returns_viewer(self):
        user = self._user(ROLE_ADMIN, authenticated=False)
        assert get_user_role(user) == ROLE_VIEWER

    def test_admin_role_returned(self):
        user = self._user(ROLE_ADMIN)
        assert get_user_role(user) == ROLE_ADMIN

    def test_editor_role_returned(self):
        user = self._user(ROLE_EDITOR)
        assert get_user_role(user) == ROLE_EDITOR

    def test_viewer_role_returned(self):
        user = self._user(ROLE_VIEWER)
        assert get_user_role(user) == ROLE_VIEWER

    def test_none_role_defaults_to_viewer(self):
        user = self._user(None)
        assert get_user_role(user) == ROLE_VIEWER

    def test_exception_returns_viewer(self):
        class BrokenUser:
            is_authenticated = True
            @property
            def optimizer_profile(self):
                raise AttributeError("no profile")

        assert get_user_role(BrokenUser()) == ROLE_VIEWER


# ===========================================================================
# _is_api_request
# ===========================================================================

class _FakeRequest:
    def __init__(self, path="/", accept="", content_type="", auth_header=""):
        self.path = path
        self.META = {"HTTP_ACCEPT": accept}
        self.content_type = content_type
        self.headers = {"Authorization": auth_header}


class TestIsApiRequest:
    def test_api_path_returns_true(self):
        req = _FakeRequest(path="/api/data")
        assert _is_api_request(req) is True

    def test_non_api_path_returns_false(self):
        req = _FakeRequest(path="/dashboard")
        assert _is_api_request(req) is False

    def test_json_accept_header_returns_true(self):
        req = _FakeRequest(accept="application/json")
        assert _is_api_request(req) is True

    def test_json_content_type_returns_true(self):
        req = _FakeRequest(content_type="application/json")
        assert _is_api_request(req) is True

    def test_bearer_auth_returns_true(self):
        req = _FakeRequest(auth_header="Bearer some-token")
        assert _is_api_request(req) is True

    def test_html_request_returns_false(self):
        req = _FakeRequest(path="/results", accept="text/html")
        assert _is_api_request(req) is False


# ===========================================================================
# editor_or_above / admin_only (smoke test the decorators work)
# ===========================================================================

class TestDecoratorSmoke:
    def test_editor_or_above_returns_callable(self):
        def dummy_view(request):
            return "ok"
        wrapped = editor_or_above(dummy_view)
        assert callable(wrapped)

    def test_admin_only_returns_callable(self):
        def dummy_view(request):
            return "ok"
        wrapped = admin_only(dummy_view)
        assert callable(wrapped)

    def test_editor_or_above_preserves_function_name(self):
        def my_view(request):
            return "ok"
        wrapped = editor_or_above(my_view)
        assert wrapped.__name__ == "my_view"

    def test_admin_only_preserves_function_name(self):
        def another_view(request):
            return "ok"
        wrapped = admin_only(another_view)
        assert wrapped.__name__ == "another_view"
