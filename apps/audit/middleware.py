"""Binds the request user to the current thread for audit attribution.

Model signals have no access to the request, so this middleware stashes
the authenticated user in thread-local storage where
``apps.audit.registry`` can pick it up when writing ``AuditLog`` rows.
"""

import threading

_state = threading.local()


def get_current_actor():
    actor = getattr(_state, "actor", None)
    if actor is not None and getattr(actor, "is_authenticated", False):
        return actor
    return None


def set_current_actor(actor):
    """Used by non-request code paths (management commands, tests)."""
    _state.actor = actor


class AuditActorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _state.actor = getattr(request, "user", None)
        try:
            return self.get_response(request)
        finally:
            _state.actor = None
