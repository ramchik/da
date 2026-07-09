"""Binds the request user and IP to the current thread for audit attribution.

Model signals have no access to the request, so this middleware stashes
the authenticated user and client IP in thread-local storage where
``apps.audit.registry`` can pick them up when writing ``AuditLog`` rows.
"""

import threading

_state = threading.local()


def get_current_actor():
    actor = getattr(_state, "actor", None)
    if actor is not None and getattr(actor, "is_authenticated", False):
        return actor
    return None


def get_current_ip():
    return getattr(_state, "ip", None)


def set_current_actor(actor, ip=None):
    """Used by non-request code paths (management commands, tests)."""
    _state.actor = actor
    _state.ip = ip


def _client_ip(request):
    # Behind the production proxy the first X-Forwarded-For entry is the
    # client; direct connections fall back to REMOTE_ADDR.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AuditActorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _state.actor = getattr(request, "user", None)
        _state.ip = _client_ip(request)
        try:
            return self.get_response(request)
        finally:
            _state.actor = None
            _state.ip = None
