"""Error handler middleware — turns unhandled exceptions into JSON 500s."""

import logging
import traceback

from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Catch unhandled errors inside the CORS middleware.

    FastAPI's @app.exception_handler(Exception) runs outside all middleware,
    so its 500 responses lack CORS headers and browsers report them only as
    "Failed to fetch". Handling them here keeps the CORS headers.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error("Database unreachable on %s %s: %s", request.method, request.url, e)
            return JSONResponse(
                status_code=503,
                content={"detail": "The database is unavailable right now. Please try again shortly."},
            )
        except Exception:
            # Log the full traceback — never leak details to the client
            logger.error("Unhandled error on %s %s:\n%s", request.method, request.url, traceback.format_exc())
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})
