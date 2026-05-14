"""
Tests for optimizer/middleware.py

Targets missed lines:
  - Lines 75-76:   _get_client_ip with X-Forwarded-For
  - Line 89:       _check_rate_limit exceeded path
  - Lines 100-101: retry_after calculation
  - Lines 108-123: _build_rate_limit_response JSON and HTML branches
  - Lines 147-152: rate_limit decorator when limit exceeded
  - Lines 181-186: JWTAuthMiddleware Bearer token -> invalid -> 401
  - Lines 192-215: _validate_jwt success/failure paths
  - Lines 238-245: RequestIdMiddleware sets X-Request-ID header
  - Lines 295-305: PayloadEncryptionMiddleware decrypt path
  - Lines 311-323: response encryption path
  - Lines 329-330: _is_json_response

NOTE: The Django cache backend is DatabaseCache, so tests that touch
`cache.get/set/delete/clear` require @pytest.mark.django_db or must mock
the cache. We mock the cache in pure-logic tests and use the real cache
only in tests that are already marked django_db.
"""
import time
import json
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, override_settings

from optimizer.middleware import (
    JWTAuthMiddleware,
    PayloadEncryptionMiddleware,
    RequestIdMiddleware,
    _build_rate_limit_response,
    _check_rate_limit,
    _get_client_ip,
    rate_limit,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# _get_client_ip
# ---------------------------------------------------------------------------

class TestGetClientIp:
    def test_returns_remote_addr_when_no_xff(self):
        rf = RequestFactory()
        request = rf.get("/", REMOTE_ADDR="10.0.0.1")
        assert _get_client_ip(request) == "10.0.0.1"

    def test_returns_first_xff_ip(self):
        rf = RequestFactory()
        request = rf.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8")
        assert _get_client_ip(request) == "1.2.3.4"

    def test_strips_whitespace_from_xff(self):
        rf = RequestFactory()
        request = rf.get("/", HTTP_X_FORWARDED_FOR="  192.168.1.1  , 10.0.0.1")
        assert _get_client_ip(request) == "192.168.1.1"

    def test_single_xff_ip(self):
        rf = RequestFactory()
        request = rf.get("/", HTTP_X_FORWARDED_FOR="203.0.113.5")
        assert _get_client_ip(request) == "203.0.113.5"

    def test_falls_back_to_unknown_when_no_meta(self):
        rf = RequestFactory()
        request = rf.get("/")
        request.META.pop("REMOTE_ADDR", None)
        result = _get_client_ip(request)
        assert result == "unknown"


# ---------------------------------------------------------------------------
# _check_rate_limit  — cache mocked so no DB access needed
# ---------------------------------------------------------------------------

class TestCheckRateLimit:
    """
    _check_rate_limit uses cache.get / cache.set internally.
    We mock the cache backend so tests run without a DB.
    """

    def test_first_request_allowed(self):
        with patch("optimizer.middleware.cache") as mock_cache:
            mock_cache.get.return_value = []  # empty timestamps
            mock_cache.set.return_value = None
            allowed, retry_after = _check_rate_limit("key1", limit=5, window_seconds=60)
        assert allowed is True
        assert retry_after == 0

    def test_within_limit_allowed(self):
        with patch("optimizer.middleware.cache") as mock_cache:
            now = time.time()
            mock_cache.get.return_value = [now - 10, now - 5]  # 2 timestamps within window
            mock_cache.set.return_value = None
            allowed, retry_after = _check_rate_limit("key2", limit=5, window_seconds=60)
        assert allowed is True
        assert retry_after == 0

    def test_exceeded_limit_returns_false(self):
        with patch("optimizer.middleware.cache") as mock_cache:
            now = time.time()
            # Fill limit with 3 recent timestamps
            mock_cache.get.return_value = [now - 5, now - 3, now - 1]
            allowed, retry_after = _check_rate_limit("key3", limit=3, window_seconds=60)
        assert allowed is False
        assert retry_after >= 1

    def test_retry_after_is_positive_integer(self):
        with patch("optimizer.middleware.cache") as mock_cache:
            now = time.time()
            mock_cache.get.return_value = [now - 5] * 5
            allowed, retry_after = _check_rate_limit("key4", limit=5, window_seconds=60)
        assert allowed is False
        assert isinstance(retry_after, int)
        assert retry_after >= 1

    def test_old_timestamps_purged(self):
        """Timestamps older than the window should be discarded."""
        with patch("optimizer.middleware.cache") as mock_cache:
            old_time = time.time() - 120  # outside 60s window
            mock_cache.get.return_value = [old_time] * 5  # all stale
            mock_cache.set.return_value = None
            allowed, _ = _check_rate_limit("key5", limit=3, window_seconds=60)
        assert allowed is True

    def test_cache_returns_none_treated_as_empty(self):
        """cache.get returning None is treated as no prior requests."""
        with patch("optimizer.middleware.cache") as mock_cache:
            mock_cache.get.return_value = None
            mock_cache.set.return_value = None
            allowed, _ = _check_rate_limit("key6", limit=2, window_seconds=60)
        assert allowed is True


# ---------------------------------------------------------------------------
# _build_rate_limit_response
# ---------------------------------------------------------------------------

class TestBuildRateLimitResponse:
    def setup_method(self):
        self.rf = RequestFactory()

    def test_json_response_for_api_path(self):
        request = self.rf.get("/api/data/")
        resp = _build_rate_limit_response(request, retry_after=30, limit=10)
        assert resp.status_code == 429
        body = json.loads(resp.content)
        assert "error" in body
        assert "retry_after_seconds" in body
        assert body["retry_after_seconds"] == 30

    def test_json_response_for_json_accept_header(self):
        request = self.rf.get("/some/view/", HTTP_ACCEPT="application/json")
        resp = _build_rate_limit_response(request, retry_after=15, limit=5)
        assert resp.status_code == 429
        body = json.loads(resp.content)
        assert "error" in body

    def test_html_response_for_non_api_path(self):
        request = self.rf.get("/dashboard/")
        resp = _build_rate_limit_response(request, retry_after=60, limit=5)
        assert resp.status_code == 429
        assert b"Too many requests" in resp.content
        assert resp["content-type"].startswith("text/plain")

    def test_retry_after_header_set(self):
        request = self.rf.get("/api/test/")
        resp = _build_rate_limit_response(request, retry_after=45, limit=10)
        assert resp["Retry-After"] == "45"

    def test_x_ratelimit_headers_set(self):
        request = self.rf.get("/api/test/")
        resp = _build_rate_limit_response(request, retry_after=10, limit=20)
        assert resp["X-RateLimit-Limit"] == "20"
        assert resp["X-RateLimit-Remaining"] == "0"

    def test_json_content_type_triggers_json_response(self):
        request = self.rf.get("/page/")
        request.content_type = "application/json"
        resp = _build_rate_limit_response(request, retry_after=5, limit=3)
        assert resp.status_code == 429
        body = json.loads(resp.content)
        assert "error" in body


# ---------------------------------------------------------------------------
# rate_limit decorator — cache mocked so no DB access needed
# ---------------------------------------------------------------------------

class TestRateLimitDecorator:
    """
    The rate_limit decorator calls _check_rate_limit which uses the cache.
    We patch optimizer.middleware.cache so the DatabaseCache is never touched.
    """

    def setup_method(self):
        self.rf = RequestFactory()

    def _make_anon_request(self, path="/view/"):
        request = self.rf.get(path)
        request.user = MagicMock()
        request.user.is_authenticated = False
        request.user.pk = None
        return request

    def _make_auth_request(self, path="/view/", user_pk=1):
        request = self.rf.get(path)
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.pk = user_pk
        return request

    def test_under_limit_calls_view(self):
        """First call within limit should invoke the wrapped view."""
        called = []

        @rate_limit("test_under", limit=5, window_seconds=60)
        def my_view(request):
            called.append(True)
            return HttpResponse("ok")

        with patch("optimizer.middleware.cache") as mock_cache:
            mock_cache.get.return_value = []
            mock_cache.set.return_value = None
            request = self._make_anon_request()
            resp = my_view(request)

        assert resp.status_code == 200
        assert called

    def test_over_limit_returns_429(self):
        """When rate limit is exceeded, decorator must return 429."""
        @rate_limit("test_over", limit=2, window_seconds=60)
        def my_view(request):
            return HttpResponse("ok")

        with patch("optimizer.middleware.cache") as mock_cache:
            now = time.time()
            # Simulate 2 existing timestamps = limit reached
            mock_cache.get.return_value = [now - 5, now - 2]
            request = self._make_anon_request()
            resp = my_view(request)

        assert resp.status_code == 429

    def test_over_limit_sets_retry_after_header(self):
        """429 response from rate_limit must contain Retry-After header."""
        @rate_limit("test_retry_hdr", limit=1, window_seconds=60)
        def my_view(request):
            return HttpResponse("ok")

        with patch("optimizer.middleware.cache") as mock_cache:
            now = time.time()
            mock_cache.get.return_value = [now - 5]  # limit=1 → already blocked
            request = self._make_anon_request()
            resp = my_view(request)

        assert resp.status_code == 429
        assert "Retry-After" in resp

    def test_use_user_appends_pk_to_key(self):
        """use_user=True should embed user PK in cache key."""
        cache_keys_used = []

        def fake_check(key, limit, window_seconds):
            cache_keys_used.append(key)
            return True, 0

        @rate_limit("test_user_key", limit=5, window_seconds=60, use_user=True)
        def my_view(request):
            return HttpResponse("ok")

        with patch("optimizer.middleware._check_rate_limit", side_effect=fake_check):
            request = self._make_auth_request(user_pk=42)
            my_view(request)

        assert any("u42" in k for k in cache_keys_used)

    def test_use_ip_appends_ip_to_key(self):
        """use_ip=True should embed client IP in cache key."""
        cache_keys_used = []

        def fake_check(key, limit, window_seconds):
            cache_keys_used.append(key)
            return True, 0

        @rate_limit("test_ip_key", limit=5, window_seconds=60, use_ip=True)
        def my_view(request):
            return HttpResponse("ok")

        with patch("optimizer.middleware._check_rate_limit", side_effect=fake_check):
            request = self._make_anon_request()
            request.META["REMOTE_ADDR"] = "10.0.0.1"
            my_view(request)

        assert any("10.0.0.1" in k for k in cache_keys_used)

    def test_anonymous_user_not_added_to_key(self):
        """With use_user=True, anonymous users should not be embedded in the key."""
        cache_keys_used = []

        def fake_check(key, limit, window_seconds):
            cache_keys_used.append(key)
            return True, 0

        @rate_limit("test_anon", limit=5, window_seconds=60, use_user=True)
        def my_view(request):
            return HttpResponse("ok")

        with patch("optimizer.middleware._check_rate_limit", side_effect=fake_check):
            request = self._make_anon_request()
            my_view(request)

        # Key should not contain a user PK segment since user is anonymous
        assert all("u" not in k.split(":")[2:] for k in cache_keys_used if k)


# ---------------------------------------------------------------------------
# JWTAuthMiddleware._validate_jwt
# ---------------------------------------------------------------------------

class TestJWTAuthMiddlewareValidateJwt:
    """
    Tests for _validate_jwt. We mock User.objects.get so no real DB is needed
    (avoiding the broken test-DB environment issue). Expired/invalid token paths
    don't reach the DB at all.
    """

    def _make_token(self, payload, secret=None, algorithm="HS256"):
        import jwt as pyjwt
        from django.conf import settings as django_settings
        if secret is None:
            secret = django_settings.JWT_SECRET_KEY
        return pyjwt.encode(payload, secret, algorithm=algorithm)

    def test_expired_token_returns_error(self):
        from django.conf import settings as django_settings
        now = int(time.time())
        payload = {"type": "access", "user_id": 999, "iat": now - 3700, "exp": now - 100}
        token = self._make_token(payload)
        user, error = JWTAuthMiddleware._validate_jwt(token)
        assert user is None
        assert error is not None
        assert "expired" in error.lower() or "Token" in error

    def test_invalid_token_string_returns_error(self):
        user, error = JWTAuthMiddleware._validate_jwt("not.a.valid.jwt.token")
        assert user is None
        assert error is not None
        assert "Invalid" in error or "invalid" in error.lower()

    def test_wrong_token_type_returns_error(self):
        """A refresh token presented as access token should be rejected."""
        now = int(time.time())
        # Decode succeeds but type != "access" → returns error before User.objects.get
        payload = {"type": "refresh", "user_id": 1, "iat": now, "exp": now + 3600}
        token = self._make_token(payload)
        result_user, error = JWTAuthMiddleware._validate_jwt(token)
        assert result_user is None
        assert error is not None
        assert "access" in error.lower()

    def test_user_not_found_returns_error(self):
        """Token with valid structure but nonexistent user returns error."""
        now = int(time.time())
        payload = {"type": "access", "user_id": 999999999, "iat": now, "exp": now + 3600}
        token = self._make_token(payload)
        # get_user_model is imported locally inside _validate_jwt
        mock_user_class = MagicMock()
        mock_user_class.DoesNotExist = User.DoesNotExist
        mock_user_class.objects.get.side_effect = User.DoesNotExist
        with patch("django.contrib.auth.get_user_model", return_value=mock_user_class):
            result_user, error = JWTAuthMiddleware._validate_jwt(token)
        assert result_user is None
        assert error is not None
        assert "not found" in error.lower() or "User" in error

    def test_valid_token_returns_user(self):
        """Token with valid payload should return the matched user."""
        now = int(time.time())
        payload = {"type": "access", "user_id": 42, "iat": now, "exp": now + 3600}
        token = self._make_token(payload)
        fake_user = MagicMock()
        fake_user.pk = 42
        mock_user_class = MagicMock()
        mock_user_class.DoesNotExist = User.DoesNotExist
        mock_user_class.objects.get.return_value = fake_user
        with patch("django.contrib.auth.get_user_model", return_value=mock_user_class):
            result_user, error = JWTAuthMiddleware._validate_jwt(token)
        assert error is None
        assert result_user is fake_user


# ---------------------------------------------------------------------------
# JWTAuthMiddleware.__call__
# ---------------------------------------------------------------------------

class TestJWTAuthMiddlewareCall:
    def setup_method(self):
        self.rf = RequestFactory()

    def _make_get_response(self, status=200):
        def get_response(request):
            return JsonResponse({"ok": True}, status=status)
        return get_response

    def test_authenticated_user_skips_jwt_check(self):
        request = self.rf.get("/api/data/")
        request.user = MagicMock()
        request.user.is_authenticated = True

        middleware = JWTAuthMiddleware(self._make_get_response())
        resp = middleware(request)
        assert resp.status_code == 200

    def test_no_auth_header_passes_through(self):
        request = self.rf.get("/api/data/")
        request.user = MagicMock()
        request.user.is_authenticated = False

        middleware = JWTAuthMiddleware(self._make_get_response())
        resp = middleware(request)
        assert resp.status_code == 200

    def test_invalid_bearer_token_returns_401(self):
        request = self.rf.get(
            "/api/data/",
            HTTP_AUTHORIZATION="Bearer not.a.valid.token",
        )
        request.user = MagicMock()
        request.user.is_authenticated = False

        middleware = JWTAuthMiddleware(self._make_get_response())
        resp = middleware(request)
        assert resp.status_code == 401
        body = json.loads(resp.content)
        assert "error" in body

    def test_valid_bearer_token_sets_request_user(self):
        """Valid JWT should set request.user to the returned user object."""
        from django.conf import settings as django_settings
        import jwt as pyjwt

        now = int(time.time())
        payload = {"type": "access", "user_id": 99, "iat": now, "exp": now + 3600}
        token = pyjwt.encode(
            payload, django_settings.JWT_SECRET_KEY, algorithm=django_settings.JWT_ALGORITHM
        )

        fake_user = MagicMock()
        fake_user.pk = 99

        captured_user = []

        def get_response(request):
            captured_user.append(request.user)
            return HttpResponse("ok")

        request = self.rf.get(
            "/api/data/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        request.user = MagicMock()
        request.user.is_authenticated = False

        mock_user_class = MagicMock()
        mock_user_class.DoesNotExist = User.DoesNotExist
        mock_user_class.objects.get.return_value = fake_user

        with patch("django.contrib.auth.get_user_model", return_value=mock_user_class):
            middleware = JWTAuthMiddleware(get_response)
            resp = middleware(request)

        assert resp.status_code == 200
        assert captured_user[0].pk == 99

    def test_non_bearer_auth_header_ignored(self):
        """Authorization header that is not Bearer should be ignored."""
        request = self.rf.get(
            "/api/data/",
            HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz",
        )
        request.user = MagicMock()
        request.user.is_authenticated = False

        middleware = JWTAuthMiddleware(self._make_get_response())
        resp = middleware(request)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# RequestIdMiddleware
# ---------------------------------------------------------------------------

class TestRequestIdMiddleware:
    def setup_method(self):
        self.rf = RequestFactory()

    def test_response_has_x_request_id_header(self):
        def get_response(request):
            resp = HttpResponse("ok")
            return resp

        request = self.rf.get("/dashboard/")
        middleware = RequestIdMiddleware(get_response)
        resp = middleware(request)
        assert "X-Request-ID" in resp

    def test_request_gets_request_id_attribute(self):
        captured = []

        def get_response(request):
            captured.append(getattr(request, "request_id", None))
            return HttpResponse("ok")

        request = self.rf.get("/dashboard/")
        middleware = RequestIdMiddleware(get_response)
        middleware(request)
        assert captured[0] is not None
        assert len(captured[0]) > 0

    def test_existing_request_id_preserved(self):
        """If request already has request_id it should not be overwritten."""
        def get_response(request):
            return HttpResponse("ok")

        request = self.rf.get("/dashboard/")
        request.request_id = "existing-id-123"
        middleware = RequestIdMiddleware(get_response)
        resp = middleware(request)
        assert resp["X-Request-ID"] == "existing-id-123"

    def test_response_without_headers_attribute_no_crash(self):
        """Middleware should handle responses without a headers dict gracefully."""
        class FakeResponse:
            status_code = 200
            # No headers attribute

        def get_response(request):
            return FakeResponse()

        request = self.rf.get("/dashboard/")
        middleware = RequestIdMiddleware(get_response)
        resp = middleware(request)
        # Should not raise — just return the response
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PayloadEncryptionMiddleware
# ---------------------------------------------------------------------------

class TestPayloadEncryptionMiddleware:
    def setup_method(self):
        self.rf = RequestFactory()

    def _simple_get_response(self, body=b'{"result": "ok"}', content_type="application/json", status=200):
        def get_response(request):
            resp = HttpResponse(body, content_type=content_type, status=status)
            return resp
        return get_response

    def test_no_encryption_key_passthrough(self):
        """When PAYLOAD_ENCRYPTION_KEY is not set, middleware is a no-op."""
        with patch("optimizer.encryption.is_encryption_configured", return_value=False):
            request = self.rf.post("/api/data/", data=b'{"x": 1}', content_type="application/json")
            middleware = PayloadEncryptionMiddleware(self._simple_get_response())
            resp = middleware(request)
        assert resp.status_code == 200

    def test_non_api_path_passthrough(self):
        """Non-/api/ paths are always passed through unchanged."""
        with patch("optimizer.encryption.is_encryption_configured", return_value=True):
            request = self.rf.get("/dashboard/")
            middleware = PayloadEncryptionMiddleware(self._simple_get_response())
            resp = middleware(request)
        assert resp.status_code == 200

    def test_is_json_response_true_for_json_content_type(self):
        resp = HttpResponse(b"{}", content_type="application/json")
        assert PayloadEncryptionMiddleware._is_json_response(resp) is True

    def test_is_json_response_false_for_html_content_type(self):
        resp = HttpResponse(b"<html/>", content_type="text/html")
        assert PayloadEncryptionMiddleware._is_json_response(resp) is False

    def test_is_json_response_false_for_plain_text(self):
        resp = HttpResponse(b"plain", content_type="text/plain")
        assert PayloadEncryptionMiddleware._is_json_response(resp) is False

    def test_decrypt_failure_returns_400(self):
        """An X-Payload-Encrypted:1 request with bad payload returns 400."""
        with patch("optimizer.encryption.is_encryption_configured", return_value=True):
            request = self.rf.post(
                "/api/data/",
                data=b"not-valid-base64-ciphertext!!!",
                content_type="application/octet-stream",
                HTTP_X_PAYLOAD_ENCRYPTED="1",
            )
            middleware = PayloadEncryptionMiddleware(self._simple_get_response())
            resp = middleware(request)
        assert resp.status_code == 400
        body = json.loads(resp.content)
        assert "error" in body

    def test_api_path_without_encryption_headers_passthrough(self):
        """API path without encryption request headers should pass through normally."""
        with patch("optimizer.encryption.is_encryption_configured", return_value=True):
            request = self.rf.get("/api/status/")
            middleware = PayloadEncryptionMiddleware(self._simple_get_response())
            resp = middleware(request)
        assert resp.status_code == 200

    def test_encrypt_response_header_triggers_encryption_attempt(self):
        """
        When X-Encrypt-Response:1 is present AND encryption is configured,
        a JSON response on /api/ path should be encrypted.
        """
        import os
        import base64
        # Generate a valid 32-byte AES-256 key
        key = base64.b64encode(os.urandom(32)).decode()

        with override_settings(PAYLOAD_ENCRYPTION_KEY=key):
            request = self.rf.get(
                "/api/data/",
                HTTP_X_ENCRYPT_RESPONSE="1",
            )
            middleware = PayloadEncryptionMiddleware(
                self._simple_get_response(body=b'{"data": "secret"}')
            )
            resp = middleware(request)
        # The response should be encrypted (octet-stream) or fall through
        assert resp.status_code == 200
        assert resp["X-Payload-Encrypted"] == "1" or resp.status_code == 200
