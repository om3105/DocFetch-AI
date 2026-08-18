"""Request guard middleware — blocks oversized and suspicious requests."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MAX_BODY_SIZE = 15 * 1024 * 1024  # 15 MB (slightly above file upload limit)


class RequestGuardMiddleware(BaseHTTPMiddleware):
    """Block oversized requests and add request-level protections."""

    async def dispatch(self, request: Request, call_next):
        # Block oversized Content-Length headers before reading body
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_SIZE:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"},
                )

        # Block requests with missing or suspiciously long User-Agent
        user_agent = request.headers.get("user-agent", "")
        if not user_agent or len(user_agent) > 500:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid request"},
            )

        return await call_next(request)
