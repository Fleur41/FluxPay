from .services import request_context


class AuditContextMiddleware:
    """Makes the caller's IP address and user agent available to audit.services.record."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # REMOTE_ADDR only: X-Forwarded-For is client-controlled unless a trusted proxy sets it.
        token = request_context.set(
            {
                "ip_address": request.META.get("REMOTE_ADDR") or None,
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
            }
        )
        try:
            return self.get_response(request)
        finally:
            request_context.reset(token)
