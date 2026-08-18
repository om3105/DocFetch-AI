"""
Firebase Authentication middleware for FastAPI.

Verifies Firebase ID tokens from the Authorization header
and extracts user information.
"""

import base64
import json
import logging
import os

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import firebase_admin
from firebase_admin import auth, credentials

load_dotenv()
logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    project_id = os.getenv("FIREBASE_PROJECT_ID", "adaptive-rag-5c629")
    svc_acct = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

    if svc_acct and os.path.exists(svc_acct):
        cred = credentials.Certificate(svc_acct)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin initialized with service account certificate")
    else:
        # Initialize with project ID (allows public cert verification)
        firebase_admin.initialize_app(options={"projectId": project_id})
        logger.info("Firebase Admin initialized with project ID: %s", project_id)

security = HTTPBearer()


def _decode_jwt_payload_fallback(token: str) -> dict:
    """Fallback decoder to extract claims from JWT payload if cert fetch fails."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT structure")
        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        if "user_id" in payload and "uid" not in payload:
            payload["uid"] = payload["user_id"]
        elif "sub" in payload and "uid" not in payload:
            payload["uid"] = payload["sub"]
        return payload
    except Exception as e:
        logger.error("JWT payload fallback decoding error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token payload",
        )


async def verify_firebase_token(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    FastAPI dependency that verifies Firebase ID tokens.

    Extracts the Bearer token from the Authorization header,
    verifies it with Firebase, and returns the decoded token.
    """
    raw_token = creds.credentials
    try:
        decoded_token = auth.verify_id_token(
            raw_token,
            clock_skew_seconds=10,
        )
        return decoded_token
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
        )
    except auth.RevokedIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked",
        )
    except Exception as e:
        # Only allow unsigned JWT fallback if explicitly enabled (dev/testing only)
        allow_fallback = os.getenv("ALLOW_JWT_FALLBACK", "false").lower() == "true"
        if not allow_fallback:
            logger.error(
                "Firebase token verification failed and JWT fallback is disabled: %s", e
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed — please sign in again",
            )
        logger.warning(
            "Firebase Admin token verification fallback triggered (ALLOW_JWT_FALLBACK=true): %s", e
        )
        # Decode payload safely as fallback so valid Firebase tokens pass
        return _decode_jwt_payload_fallback(raw_token)
