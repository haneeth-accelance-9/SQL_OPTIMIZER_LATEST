"""Role-based access control for the SQL License Optimizer.

Roles (ascending privilege):
  viewer  – read-only; cannot trigger actions or create users
  editor  – all viewer access + can trigger runs/decisions; cannot create users
  admin   – full access
"""
import functools
import logging

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect

logger = logging.getLogger(__name__)

ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"

ROLE_CHOICES = [
    (ROLE_ADMIN, "Admin"),
    (ROLE_EDITOR, "Editor"),
    (ROLE_VIEWER, "Viewer"),
]


def get_user_role(user) -> str:
    """Return the role string for an authenticated user. Defaults to viewer."""
    if not user or not user.is_authenticated:
        return ROLE_VIEWER
    try:
        return user.optimizer_profile.role or ROLE_VIEWER
    except Exception:
        return ROLE_VIEWER


def _is_api_request(request) -> bool:
    return (
        request.path.startswith("/api/")
        or "application/json" in request.META.get("HTTP_ACCEPT", "")
        or getattr(request, "content_type", "") == "application/json"
        or request.headers.get("Authorization", "").startswith("Bearer ")
    )


def _forbidden_response(request, role, required):
    logger.warning(
        "Permission denied user=%s role=%s required=%s path=%s",
        getattr(request.user, "username", "anon"),
        role,
        required,
        request.path,
    )
    if _is_api_request(request):
        return JsonResponse(
            {
                "error": "Forbidden.",
                "detail": f"Your role '{role}' does not permit this action. Required: {list(required)}.",
            },
            status=403,
        )
    messages.error(request, "You do not have permission to perform this action.")
    return redirect("optimizer:dashboard")


def require_role(*allowed_roles):
    """
    Decorator that restricts a view to users whose role is in allowed_roles.
    Must be placed after @login_required so request.user is authenticated.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            role = get_user_role(request.user)
            if role not in allowed_roles:
                return _forbidden_response(request, role, allowed_roles)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def editor_or_above(view_func):
    """Allow Admin and Editor; block Viewer."""
    return require_role(ROLE_ADMIN, ROLE_EDITOR)(view_func)


def admin_only(view_func):
    """Allow Admin only."""
    return require_role(ROLE_ADMIN)(view_func)
