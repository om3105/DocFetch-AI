"""
Firebase Authentication middleware for FastAPI.

Verifies Firebase ID tokens from the Authorization header
and extracts user information.

Tokens are verified against Google's public signing certificates, so no
service-account credentials are needed — only FIREBASE_PROJECT_ID.
"""

import logging
import os

import cachecontrol
import requests
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

load_dotenv()
logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "adaptive-rag-5c629")
EXPECTED_ISSUER = f"https://securetoken.google.com/{PROJECT_ID}"

# Cache Google's signing certificates per their Cache-Control headers
_google_request = google_requests.Request(session=cachecontrol.CacheControl(requests.Session()))

security = HTTPBearer()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def verify_firebase_token(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    FastAPI dependency that verifies Firebase ID tokens.

    Extracts the Bearer token from the Authorization header, verifies its
    signature, audience and issuer, and returns the decoded claims with
    "uid" set.
    """
    try:
        claims = id_token.verify_firebase_token(
            creds.credentials,
            _google_request,
            audience=PROJECT_ID,
            clock_skew_in_seconds=10,
        )
    except ValueError as e:
        # google-auth raises ValueError for bad signatures, audience and expiry
        if "expired" in str(e).lower():
            raise _unauthorized("Authentication token has expired")
        logger.warning("Rejected invalid Firebase token: %s", e)
        raise _unauthorized("Invalid authentication token")
    except google_auth_exceptions.GoogleAuthError as e:
        logger.error("Firebase token verification failed: %s", e)
        raise _unauthorized("Authentication failed — please sign in again")

    if claims.get("iss") != EXPECTED_ISSUER or not claims.get("sub"):
        raise _unauthorized("Invalid authentication token")

    claims["uid"] = claims["sub"]
    # Expose the verified uid so the rate limiter doesn't re-verify the token
    request.state.uid = claims["uid"]
    return claims
