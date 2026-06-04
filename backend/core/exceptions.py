"""
JUALIN.AI — Custom Exceptions & Global Error Handling
Provides consistent error responses across the entire API.

Exception Hierarchy:
    JualinError (base)
    ├── NotFoundError          → 404
    ├── ValidationError        → 422
    ├── AuthenticationError    → 401
    ├── AuthorizationError     → 403
    ├── QuotaExceededError     → 429
    ├── PaymentError           → 402
    ├── ExternalServiceError   → 502
    └── RateLimitError         → 429

Usage:
    from core.exceptions import NotFoundError
    raise NotFoundError("Produk", product_id)
    # → {"error": "not_found", "message": "Produk #42 tidak ditemukan", "detail": {...}}
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from core.logging_config import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════
# Base Exception
# ══════════════════════════════════════════════════

class JualinError(Exception):
    """
    Base exception for all JUALIN.AI application errors.
    Subclass this for specific error types.
    """
    status_code: int = 500
    error_code: str = "internal_error"
    message: str = "Terjadi kesalahan internal"

    def __init__(self, message: str = None, detail: dict = None):
        self.message = message or self.__class__.message
        self.detail = detail or {}
        super().__init__(self.message)

    def to_response(self) -> dict:
        """Convert exception to API response body."""
        body = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.detail:
            body["detail"] = self.detail
        return body


# ══════════════════════════════════════════════════
# Specific Exceptions
# ══════════════════════════════════════════════════

class NotFoundError(JualinError):
    """Resource not found (404)."""
    status_code = 404
    error_code = "not_found"

    def __init__(self, resource: str = "Resource", resource_id: int | str = None):
        detail = {"resource": resource}
        if resource_id is not None:
            detail["id"] = resource_id
            message = f"{resource} #{resource_id} tidak ditemukan"
        else:
            message = f"{resource} tidak ditemukan"
        super().__init__(message=message, detail=detail)


class ValidationError(JualinError):
    """Input validation error (422)."""
    status_code = 422
    error_code = "validation_error"

    def __init__(self, message: str = "Data tidak valid", fields: dict = None):
        detail = {}
        if fields:
            detail["fields"] = fields
        super().__init__(message=message, detail=detail)


class AuthenticationError(JualinError):
    """Authentication failure (401)."""
    status_code = 401
    error_code = "authentication_error"
    message = "Autentikasi gagal. Silakan login kembali."

    def __init__(self, message: str = None):
        super().__init__(message=message)


class AuthorizationError(JualinError):
    """Authorization / permission denied (403)."""
    status_code = 403
    error_code = "authorization_error"
    message = "Akses ditolak. Anda tidak memiliki izin untuk aksi ini."

    def __init__(self, message: str = None):
        super().__init__(message=message)


class QuotaExceededError(JualinError):
    """Quota exceeded (429)."""
    status_code = 429
    error_code = "quota_exceeded"

    def __init__(self, resource: str = "Chat", used: int = 0, limit: int = 0):
        message = f"Kuota {resource} sudah habis ({used}/{limit})"
        detail = {"resource": resource, "used": used, "limit": limit}
        super().__init__(message=message, detail=detail)


class RateLimitError(JualinError):
    """Rate limit exceeded (429)."""
    status_code = 429
    error_code = "rate_limited"

    def __init__(self, retry_after: int = 60):
        message = "Terlalu banyak request. Coba lagi nanti."
        detail = {"retry_after": retry_after}
        super().__init__(message=message, detail=detail)


class PaymentError(JualinError):
    """Payment processing error (402)."""
    status_code = 402
    error_code = "payment_error"
    message = "Gagal memproses pembayaran"

    def __init__(self, message: str = None, provider: str = None, detail: dict = None):
        extra_detail = detail or {}
        if provider:
            extra_detail["provider"] = provider
        super().__init__(message=message, detail=extra_detail)


class ExternalServiceError(JualinError):
    """External service failure (502)."""
    status_code = 502
    error_code = "external_service_error"

    def __init__(self, service: str = "External service", message: str = None):
        msg = message or f"{service} tidak tersedia. Coba lagi nanti."
        detail = {"service": service}
        super().__init__(message=msg, detail=detail)


class OrderTransitionError(JualinError):
    """Invalid order status transition (400)."""
    status_code = 400
    error_code = "invalid_status_transition"

    def __init__(self, from_status: str, to_status: str):
        message = f"Tidak bisa mengubah status dari '{from_status}' ke '{to_status}'"
        detail = {"from_status": from_status, "to_status": to_status}
        super().__init__(message=message, detail=detail)


# ══════════════════════════════════════════════════
# Global Exception Handlers (register in FastAPI app)
# ══════════════════════════════════════════════════

async def jualin_error_handler(request: Request, exc: JualinError) -> JSONResponse:
    """
    Handle all JualinError subclasses consistently.
    Logs the error with appropriate severity based on status code.
    """
    # Log based on severity
    if exc.status_code >= 500:
        logger.error(
            f"Server error: {exc.message}",
            extra={"error_code": exc.error_code, "detail": exc.detail},
            exc_info=True,
        )
    elif exc.status_code >= 400:
        logger.warning(
            f"Client error: {exc.message}",
            extra={"error_code": exc.error_code, "detail": exc.detail},
        )

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_response(),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all for unhandled exceptions.
    Logs full traceback but returns safe message to client.
    NEVER expose internal error details to the client.
    """
    logger.critical(
        f"Unhandled exception: {type(exc).__name__}: {exc}",
        exc_info=True,
        extra={
            "path": str(request.url.path),
            "method": request.method,
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Terjadi kesalahan internal. Tim kami sudah diberitahu.",
        },
    )


def register_exception_handlers(app):
    """
    Register all custom exception handlers with the FastAPI app.
    Call this once during app initialization.

    Usage (in main.py):
        from core.exceptions import register_exception_handlers
        register_exception_handlers(app)
    """
    app.add_exception_handler(JualinError, jualin_error_handler)
    # Note: We intentionally do NOT register a catch-all Exception handler here
    # because it would interfere with FastAPI's built-in validation error handling.
    # Unhandled exceptions are caught by the RequestLoggingMiddleware instead.
