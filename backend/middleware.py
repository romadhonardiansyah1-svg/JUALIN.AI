"""
JUALIN.AI — Middleware Stack
Provides: Rate limiting, request logging, security headers, request ID tracking.

Middleware execution order (outermost processes first):
    1. RequestLoggingMiddleware  — logs every request + injects Request-ID
    2. RateLimitMiddleware       — blocks excessive requests
    3. CORSMiddleware            — handles cross-origin (added in main.py)
"""
import time
import uuid
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from cache import check_rate_limit, get_rate_limit_info
from core.logging_config import get_logger, request_id_var, request_path_var

logger = get_logger("middleware")


def get_client_ip(request: Request) -> str:
    """Return best-effort client IP behind Nginx/reverse proxies."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


# ══════════════════════════════════════════════════
# Request Logging + ID Middleware
# ══════════════════════════════════════════════════

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    - Generates a unique Request-ID (UUID4) per request
    - Sets context variables for structured logging (request_id, path)
    - Logs request start/end with duration and status code
    - Catches unhandled exceptions and returns safe 500 response
    - Adds security headers to every response
    """

    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        req_id = uuid.uuid4().hex
        start_time = time.monotonic()

        # Set context variables (available to all loggers in this request)
        request_id_var.set(req_id)
        request_path_var.set(request.url.path)

        # Client identification
        client_ip = get_client_ip(request)
        method = request.method
        path = request.url.path

        # Skip logging for health checks and static assets (reduce noise)
        is_noisy = path in ("/health", "/ready", "/favicon.ico") or path.startswith("/uploads/")

        if not is_noisy:
            logger.info(
                f"→ {method} {path}",
                extra={"client_ip": client_ip},
            )

        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = round((time.monotonic() - start_time) * 1000, 1)

            # Log response (skip noisy endpoints)
            if not is_noisy:
                log_method = logger.info if response.status_code < 400 else logger.warning
                log_method(
                    f"← {method} {path} → {response.status_code} ({duration_ms}ms)",
                    extra={
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        "client_ip": client_ip,
                    },
                )

            # Inject headers
            response.headers["X-Request-ID"] = req_id
            response.headers["X-Process-Time"] = f"{duration_ms}"
            response.headers["X-Powered-By"] = "JUALIN.AI"

            # Security headers (defense in depth)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

            return response

        except Exception as exc:
            # Catch ANY unhandled exception — never let it crash the server
            duration_ms = round((time.monotonic() - start_time) * 1000, 1)
            logger.critical(
                f"✘ {method} {path} → Unhandled exception ({duration_ms}ms)",
                extra={
                    "client_ip": client_ip,
                    "duration_ms": duration_ms,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_error",
                    "message": "Terjadi kesalahan internal. Tim kami sudah diberitahu.",
                },
                headers={"X-Request-ID": req_id},
            )


# ══════════════════════════════════════════════════
# Rate Limit Middleware
# ══════════════════════════════════════════════════

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-backed rate limiter with per-endpoint configuration.
    Gracefully degrades (allows all) if Redis is unavailable.

    Rate limits:
    - /api/chat/send   → 10 req/min (prevent chat spam)
    - /api/auth/*      → 5 req/min  (prevent brute force)
    - /api/payments/*  → 10 req/min (prevent payment spam)
    - /api/*           → 60 req/min (general API)
    - Other            → 120 req/min (static assets, etc.)
    """

    # Endpoint rate limit configuration
    RATE_LIMITS = [
        # (path_prefix, max_requests, window_seconds)
        ("/api/chat/send", 10, 60),
        ("/api/auth", 5, 60),
        ("/api/payments", 10, 60),
        ("/api/", 60, 60),
    ]
    DEFAULT_LIMIT = (120, 60)

    async def dispatch(self, request: Request, call_next):
        client_ip = get_client_ip(request)
        path = request.url.path

        # Find matching rate limit config
        max_req, window = self.DEFAULT_LIMIT
        for prefix, limit, win in self.RATE_LIMITS:
            if path.startswith(prefix):
                max_req, window = limit, win
                break

        # Build rate limit key: ip + route group
        path_parts = path.strip("/").split("/")
        route_key = path_parts[1] if len(path_parts) > 1 else (path_parts[0] if path_parts else "root")
        identifier = f"{client_ip}:{route_key}"

        # Check rate limit (gracefully degrades if Redis unavailable)
        allowed = await check_rate_limit(identifier, max_req, window)

        if not allowed:
            info = await get_rate_limit_info(identifier, max_req, window)
            logger.warning(
                f"Rate limit exceeded: {client_ip} on {path}",
                extra={"identifier": identifier, "limit": max_req},
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "message": "Terlalu banyak request. Coba lagi nanti.",
                    "retry_after": info["reset"],
                },
                headers={
                    "Retry-After": str(info["reset"]),
                    "X-RateLimit-Limit": str(max_req),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        return response
