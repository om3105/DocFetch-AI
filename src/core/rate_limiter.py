"""
Rate limiter instance — shared between main.py and routes.py.

Separated into its own module to avoid circular imports.
"""

import logging

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def _get_rate_limit_key(request: Request) -> str:
    """
    Use Firebase UID as rate-limit key for authenticated requests,
    falling back to client IP for unauthenticated requests.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from firebase_admin import auth
            token = auth_header.split(" ", 1)[1]
            decoded = auth.verify_id_token(token)
            return f"uid:{decoded['uid']}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=_get_rate_limit_key)
