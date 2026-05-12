"""Optimizer middleware stack.

Classes (in MIDDLEWARE order):
  JWTAuthMiddleware          – validates Bearer JWT; sets request.user for API clients
  RequestIdMiddleware        – attaches a correlation UUID to every request/response
  PayloadEncryptionMiddleware – decrypts AES-256-GCM request bodies / encrypts responses

Logging filters (attached via LOGGING config):
  RequestIdFilter    – stamps request_id on every LogRecord
  PiiRedactingFilter – regex-redacts email addresses from log messages/args
"""
import functools
import logging
import re
import time
import uuid

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# RequestIdFilter
# ─────────────────────────────────────────────────────────────────────────────

class RequestIdFilter(logging.Filter):
    """
    Stamps ``record.request_id`` on every LogRecord using the ContextVar set by
    RequestIdMiddleware at the start of each request.

    A single instance is attached to ``logging.root`` inside
    ``RequestIdMiddleware.__init__`` so every logger that propagates to root
    (the entire application stack) automatically carries the request-ID for the
    full request lifecycle — no per-handler filter config needed.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        from optimizer.logger import get_request_id
        record.request_id = get_request_id()
        return True


# Attached to logging.root once per worker process (see RequestIdMiddleware.__init__)
_request_id_filter = RequestIdFilter()


# ─────────────────────────────────────────────────────────────────────────────
# PiiRedactingFilter
# ─────────────────────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)
_EMAIL_PLACEHOLDER = "[email redacted]"


class PiiRedactingFilter(logging.Filter):
    """
    Redacts email addresses from log messages before they reach any handler.

    Covers plain email strings as well as key=value patterns such as
    ``notified_to_email=user@example.com`` logged by the MVP6 notification flow.

    Operates by calling ``record.getMessage()`` (merges format string + args),
    applying the regex, then storing the redacted string back into ``record.msg``
    and clearing ``record.args`` so downstream formatters see only the safe form.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = _EMAIL_RE.sub(_EMAIL_PLACEHOLDER, message)
        record.args = None
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Rate-limiting helpers (used by the rate_limit decorator in views)
# ─────────────────────────────────────────────────────────────────────────────

def _get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _check_rate_limit(key: str, limit: int, window_seconds: int):
    """Sliding-window rate check. Returns (allowed, retry_after_seconds)."""
    now = time.time()
    timestamps = cache.get(key) or []
    cutoff = now - window_seconds
    timestamps = [t for t in timestamps if t > cutoff]
    if len(timestamps) >= limit:
        retry_after = max(1, int(window_seconds - (now - min(timestamps))) + 1)
        return False, retry_after
    timestamps.append(now)
    cache.set(key, timestamps, window_seconds + 1)
    return True, 0


def _build_rate_limit_response(request, retry_after: int, limit: int):
    is_json = (
        request.path.startswith("/api/")
        or "application/json" in request.META.get("HTTP_ACCEPT", "")
        or getattr(request, "content_type", "") == "application/json"
    )
    if is_json:
        resp = JsonResponse(
            {"error": "Too many requests. Please slow down.", "retry_after_seconds": retry_after},
            status=429,
        )
    else:
        resp = HttpResponse("Too many requests. Please try again later.", status=429, content_type="text/plain")
    resp["Retry-After"] = str(retry_after)
    resp["X-RateLimit-Limit"] = str(limit)
    resp["X-RateLimit-Remaining"] = "0"
    return resp


def rate_limit(key_prefix: str, limit: int, window_seconds: int, use_user: bool = True, use_ip: bool = False):
    """
    View decorator: sliding-window rate limit backed by Django cache.

    key_prefix     – unique name (e.g. "login", "agent_run")
    limit          – max requests in window_seconds
    window_seconds – rolling window length in seconds
    use_user       – include authenticated user PK in cache key
    use_ip         – include client IP in cache key
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            parts = [key_prefix]
            if use_user and request.user.is_authenticated:
                parts.append(f"u{request.user.pk}")
            if use_ip:
                parts.append(f"ip{_get_client_ip(request)}")
            key = "rl:" + ":".join(parts)
            allowed, retry_after = _check_rate_limit(key, limit, window_seconds)
            if not allowed:
                logger.warning(
                    "Rate limit hit prefix=%s ip=%s user=%s",
                    key_prefix, _get_client_ip(request),
                    request.user.pk if request.user.is_authenticated else "anon",
                )
                return _build_rate_limit_response(request, retry_after, limit)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# JWTAuthMiddleware
# ─────────────────────────────────────────────────────────────────────────────

class JWTAuthMiddleware:
    """
    Authenticate API clients via OAuth2 Bearer JWT tokens.

    - Runs after Django's AuthenticationMiddleware.
    - If request.user is already authenticated (session), does nothing.
    - If Authorization: Bearer <token> is present, validates the JWT and
      sets request.user to the matching User instance.
    - On invalid/expired token returns 401 JSON; does NOT redirect.
    - Browser-rendered views are unaffected (no Authorization header).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                user, error = self._validate_jwt(token)
                if user:
                    request.user = user
                elif error:
                    return JsonResponse({"error": error}, status=401)
        return self.get_response(request)

    @staticmethod
    def _validate_jwt(token: str):
        """Return (user, None) on success, (None, error_str) on failure."""
        import jwt as pyjwt
        from django.contrib.auth import get_user_model

        try:
            payload = pyjwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except pyjwt.ExpiredSignatureError:
            return None, "Token has expired."
        except pyjwt.InvalidTokenError as exc:
            return None, f"Invalid token: {exc}"

        if payload.get("type") != "access":
            return None, "Token is not an access token."

        User = get_user_model()
        try:
            user = User.objects.get(pk=payload["user_id"], is_active=True)
        except User.DoesNotExist:
            return None, "User not found or inactive."

        return user, None


# ─────────────────────────────────────────────────────────────────────────────
# RequestIdMiddleware
# ─────────────────────────────────────────────────────────────────────────────

class RequestIdMiddleware:
    """
    Attaches a UUID correlation ID to every request/response.

    On startup (``__init__``) the singleton ``_request_id_filter`` is added to
    ``logging.root`` so that *all* loggers automatically carry ``request_id``
    for the entire request lifecycle without any per-handler filter wiring.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Attach once per worker — idempotent guard avoids duplicate filters
        # on hot-reload or multi-middleware instantiation.
        if _request_id_filter not in logging.root.filters:
            logging.root.addFilter(_request_id_filter)

    def __call__(self, request):
        request.request_id = getattr(request, "request_id", None) or str(uuid.uuid4())[:12]
        from optimizer.logger import set_request_id
        set_request_id(request.request_id)
        response = self.get_response(request)
        if hasattr(response, "headers"):
            response["X-Request-ID"] = request.request_id
        return response


# ─────────────────────────────────────────────────────────────────────────────
# PayloadEncryptionMiddleware
# ─────────────────────────────────────────────────────────────────────────────

_ENCRYPTED_REQUEST_HEADER = "HTTP_X_PAYLOAD_ENCRYPTED"
_ENCRYPT_RESPONSE_HEADER = "HTTP_X_ENCRYPT_RESPONSE"
_API_PREFIX = "/api/"


class PayloadEncryptionMiddleware:
    """
    AES-256-GCM payload encryption layer for API clients.

    Request decryption
      Triggered by:  X-Payload-Encrypted: 1  request header.
      Expects:       request body = raw base64(nonce || ciphertext+tag).
      Effect:        replaces request._stream so view reads plaintext JSON.

    Response encryption
      Triggered when: (a) the request was encrypted, OR
                      (b) X-Encrypt-Response: 1 request header is present.
      Only applied to: JSON responses on /api/* paths.
      Response body is replaced with base64(nonce || ciphertext+tag).
      Sets header:   X-Payload-Encrypted: 1 on the response.

    No-op when:
      - PAYLOAD_ENCRYPTION_KEY is not configured.
      - Request path does not start with /api/.
      - Neither trigger header is present on a plain request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from optimizer.encryption import is_encryption_configured

        if not is_encryption_configured() or not request.path.startswith(_API_PREFIX):
            return self.get_response(request)

        wants_encrypted_response = (
            request.META.get(_ENCRYPTED_REQUEST_HEADER, "") in ("1", "true", "True")
            or request.META.get(_ENCRYPT_RESPONSE_HEADER, "") in ("1", "true", "True")
        )

        # ── Decrypt incoming request body ──────────────────────────────────
        if request.META.get(_ENCRYPTED_REQUEST_HEADER, "") in ("1", "true", "True"):
            try:
                from optimizer.encryption import decrypt_payload
                import io
                raw_body = request.body  # read once; caches internally
                plaintext = decrypt_payload(raw_body.decode("utf-8").strip())
                # Patch the cached body so views see plaintext
                request._body = plaintext
                request.META["CONTENT_TYPE"] = "application/json"
            except ValueError as exc:
                logger.warning("Request decryption failed ip=%s: %s", _get_client_ip(request), exc)
                return JsonResponse({"error": "Request payload decryption failed.", "detail": str(exc)}, status=400)

        response = self.get_response(request)

        # ── Encrypt outgoing response ───────────────────────────────────────
        if wants_encrypted_response and self._is_json_response(response):
            try:
                from optimizer.encryption import encrypt_payload
                encrypted = encrypt_payload(response.content)
                enc_response = HttpResponse(
                    encrypted,
                    status=response.status_code,
                    content_type="application/octet-stream",
                )
                enc_response["X-Payload-Encrypted"] = "1"
                enc_response["X-Request-ID"] = getattr(request, "request_id", "")
                return enc_response
            except Exception as exc:
                logger.error("Response encryption failed: %s", exc)

        return response

    @staticmethod
    def _is_json_response(response) -> bool:
        ct = response.get("Content-Type", "")
        return "application/json" in ct
