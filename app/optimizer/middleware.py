"""Optimizer middleware: request ID for correlation in logs."""
import logging
import uuid

logger = logging.getLogger(__name__)


class RequestIdMiddleware:
    """Set request.request_id for correlation; do not log PII or session data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = getattr(request, "request_id", None) or str(uuid.uuid4())[:12]
        response = self.get_response(request)
        if hasattr(response, "headers"):
            response["X-Request-ID"] = request.request_id
        return response
