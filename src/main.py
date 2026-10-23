"""
Main FastAPI application entry point.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.api.chat_routes import chat_router
from src.api.routes import router
from src.core.error_handler import ErrorHandlerMiddleware
from src.core.rate_limiter import limiter
from src.core.request_guard import RequestGuardMiddleware
from src.core.security_headers import SecurityHeadersMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── App initialization ──────────────────────────────────────────────────────

debug = os.getenv("DEBUG", "false").lower() == "true"

app = FastAPI(
    title="DocFetch AI API",
    docs_url="/docs" if debug else None,
    redoc_url="/redoc" if debug else None,
    openapi_url="/openapi.json" if debug else None,
)

# Register rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware stack (first added runs innermost; CORS, added last, is outermost) ──

# 0. Error handler — innermost, so its 500 responses still get CORS headers
app.add_middleware(ErrorHandlerMiddleware)

# 1. Request guard — blocks oversized/suspicious requests early
app.add_middleware(RequestGuardMiddleware)

# 2. Security headers — added to every response
app.add_middleware(SecurityHeadersMiddleware)

# 3. CORS — hardened to specific methods and headers only
allowed_origins_env = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        *allowed_origins_env,
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Description"],
    max_age=600,  # Cache preflight for 10 minutes
)

# ── Routes ──────────────────────────────────────────────────────────────────

app.include_router(router)
app.include_router(chat_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint to verify API is running."""
    return {"message": "DocFetch AI API is running"}
