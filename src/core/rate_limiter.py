"""
Rate limiter instance — shared between main.py and routes.py.

Separated into its own module to avoid circular imports.
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _get_rate_limit_key(request: Request) -> str:
    """
    Use the Firebase UID as rate-limit key for authenticated requests,
    falling back to client IP for unauthenticated requests.

    The uid is set on request.state by verify_firebase_token, which runs
    as a route dependency before the limiter check — so the token is
    verified only once per request.
    """
    uid = getattr(request.state, "uid", None)
    if uid:
        return f"uid:{uid}"
    return get_remote_address(request)


limiter = Limiter(key_func=_get_rate_limit_key)
