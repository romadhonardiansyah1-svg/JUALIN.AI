"""
JUALIN.AI — Middleware
Rate limiting, request logging, and security headers
"""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time

from cache import check_rate_limit, get_rate_limit_info


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit middleware using Redis token bucket."""

    async def dispatch(self, request: Request, call_next):
        # Get client identifier
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Different rate limits per endpoint
        if path.startswith("/api/chat/send"):
            max_req, window = 10, 60  # 10 chat messages per minute
        elif path.startswith("/api/auth"):
            max_req, window = 5, 60  # 5 auth attempts per minute
        elif path.startswith("/api/"):
            max_req, window = 60, 60  # 60 API calls per minute
        else:
            max_req, window = 120, 60  # 120 for static assets

        # Check rate limit
        path_parts = path.strip("/").split("/")
        route_key = path_parts[1] if len(path_parts) > 1 else (path_parts[0] if path_parts else "root")
        identifier = f"{client_ip}:{route_key}"
        allowed = await check_rate_limit(identifier, max_req, window)

        if not allowed:
            info = await get_rate_limit_info(identifier, max_req, window)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Terlalu banyak request. Coba lagi nanti.",
                    "retry_after": info["reset"],
                },
                headers={
                    "Retry-After": str(info["reset"]),
                    "X-RateLimit-Limit": str(max_req),
                    "X-RateLimit-Remaining": "0",
                },
            )

        # Process request
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        # Add headers
        response.headers["X-Process-Time"] = f"{process_time:.3f}"
        response.headers["X-Powered-By"] = "JUALIN.AI"

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response
