"""
JUALIN.AI — Cashi.id Payment Gateway
Integration with Cashi.id API for QRIS, QRIS Custom, and Virtual Account.

API Docs: https://cashi.id/docs (v1.2.0)

Endpoints:
- POST /api/create-order          → Standard QRIS
- POST /api/create-order-custom   → QRIS with custom merchant name
- POST /api/create-va             → Virtual Account (BCA, BNI, BRI, Mandiri, Permata)
- GET  /api/check-payment/:id     → Check payment status

Authentication: x-api-key header with secret key
"""
import httpx
import hmac
import hashlib
import secrets
from typing import Optional

from config import get_settings
from core.logging_config import get_logger
from services.payments.base import (
    PaymentGateway, PaymentCreateResult, PaymentStatusResult,
    WebhookResult, PaymentStatus,
)

settings = get_settings()
logger = get_logger(__name__)


class CashiGateway(PaymentGateway):
    """Cashi.id payment gateway implementation."""

    def __init__(self):
        self.api_key = settings.CASHI_API_KEY
        self.base_url = settings.CASHI_BASE_URL.rstrip("/")

    @property
    def provider_name(self) -> str:
        return "cashi"

    def _headers(self) -> dict:
        """Standard headers for Cashi.id API."""
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_payment(
        self,
        order_id: int,
        amount: int,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        items: list[dict],
        method: str = "qris",
        payment_token: str = "",
    ) -> PaymentCreateResult:
        """
        Create a payment via Cashi.id.

        Methods:
        - "qris"         → Standard QRIS (auto-adds unique amount suffix)
        - "qris_custom"  → QRIS with custom merchant name
        - "va_bca", "va_bni", "va_bri", "va_mandiri", "va_permata" → Virtual Account
        """
        invoice_id = f"JUALIN-{order_id}"

        try:
            if method.startswith("va_"):
                return await self._create_va(
                    invoice_id=invoice_id,
                    amount=amount,
                    customer_name=customer_name,
                    bank=method.replace("va_", ""),
                    order_id=order_id,
                )
            elif method == "qris_custom":
                return await self._create_qris_custom(
                    invoice_id=invoice_id,
                    amount=amount,
                    order_id=order_id,
                )
            else:
                # Default: standard QRIS
                return await self._create_qris(
                    invoice_id=invoice_id,
                    amount=amount,
                    order_id=order_id,
                )

        except httpx.TimeoutException:
            logger.error(f"Cashi timeout for order #{order_id}")
            return PaymentCreateResult(
                success=False, order_id=invoice_id, provider="cashi",
                method=method, amount=amount, payment_url=None, qr_data=None,
                token=None, expires_at=None,
                error_message="Payment gateway timeout. Coba lagi.",
                raw_response=None,
            )
        except Exception as e:
            logger.error(f"Cashi error: {e}", exc_info=True)
            return PaymentCreateResult(
                success=False, order_id=invoice_id, provider="cashi",
                method=method, amount=amount, payment_url=None, qr_data=None,
                token=None, expires_at=None,
                error_message=f"Gagal membuat pembayaran: {str(e)}",
                raw_response=None,
            )

    async def _create_qris(self, invoice_id: str, amount: int, order_id: int) -> PaymentCreateResult:
        """Standard QRIS payment (amount may have unique suffix)."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.base_url}/create-order",
                json={
                    "amount": int(amount),
                    "order_id": invoice_id,
                },
                headers=self._headers(),
            )

            data = response.json()

            if not data.get("success"):
                logger.error(
                    f"Cashi QRIS failed: {data}",
                    extra={"order_id": order_id},
                )
                return PaymentCreateResult(
                    success=False, order_id=invoice_id, provider="cashi",
                    method="qris", amount=amount, payment_url=None, qr_data=None,
                    token=None, expires_at=None,
                    error_message=data.get("message", "Cashi QRIS error"),
                    raw_response=data,
                )

            logger.info(
                f"Cashi QRIS created: {invoice_id}",
                extra={
                    "order_id": order_id,
                    "amount": data.get("amount", amount),
                    "checkout_url": data.get("checkout_url"),
                },
            )

            return PaymentCreateResult(
                success=True,
                order_id=invoice_id,
                provider="cashi",
                method="qris",
                amount=int(data.get("amount", amount)),
                payment_url=data.get("checkout_url"),
                qr_data=data.get("qrUrl"),
                token=None,
                expires_at=data.get("expires_at"),
                error_message=None,
                raw_response=data,
            )

    async def _create_qris_custom(self, invoice_id: str, amount: int, order_id: int) -> PaymentCreateResult:
        """QRIS with custom merchant name."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.base_url}/create-order-custom",
                json={
                    "amount": int(amount),
                    "order_id": invoice_id,
                    "custom_name": "JUALIN.AI",
                },
                headers=self._headers(),
            )

            data = response.json()

            if not data.get("success"):
                return PaymentCreateResult(
                    success=False, order_id=invoice_id, provider="cashi",
                    method="qris_custom", amount=amount, payment_url=None, qr_data=None,
                    token=None, expires_at=None,
                    error_message=data.get("message", "Cashi QRIS Custom error"),
                    raw_response=data,
                )

            return PaymentCreateResult(
                success=True,
                order_id=invoice_id,
                provider="cashi",
                method="qris_custom",
                amount=int(data.get("amount", amount)),
                payment_url=data.get("checkout_url"),
                qr_data=data.get("qrUrl"),
                token=None,
                expires_at=data.get("expires_at"),
                error_message=None,
                raw_response=data,
            )

    async def _create_va(
        self,
        invoice_id: str,
        amount: int,
        customer_name: str,
        bank: str,
        order_id: int,
    ) -> PaymentCreateResult:
        """Virtual Account payment."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.base_url}/create-va",
                json={
                    "amount": int(amount),
                    "order_id": invoice_id,
                    "bank": bank.upper(),
                    "name": customer_name[:40],
                },
                headers=self._headers(),
            )

            data = response.json()

            if not data.get("success"):
                return PaymentCreateResult(
                    success=False, order_id=invoice_id, provider="cashi",
                    method=f"va_{bank}", amount=amount, payment_url=None, qr_data=None,
                    token=None, expires_at=None,
                    error_message=data.get("message", f"Cashi VA {bank.upper()} error"),
                    raw_response=data,
                )

            logger.info(
                f"Cashi VA created: {invoice_id} ({bank.upper()})",
                extra={
                    "order_id": order_id,
                    "bank": bank,
                    "va_number": data.get("va_number"),
                },
            )

            return PaymentCreateResult(
                success=True,
                order_id=invoice_id,
                provider="cashi",
                method=f"va_{bank}",
                amount=int(data.get("amount", amount)),
                payment_url=data.get("checkout_url"),
                qr_data=None,
                token=data.get("va_number"),  # Store VA number in token field
                expires_at=data.get("expires_at"),
                error_message=None,
                raw_response=data,
            )

    async def check_status(self, order_id: str) -> PaymentStatusResult:
        """Check payment status via Cashi.id API."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/check-payment/{order_id}",
                    headers=self._headers(),
                )

                data = response.json()
                cashi_status = data.get("status", "pending")

                status_map = {
                    "pending": PaymentStatus.PENDING,
                    "paid": PaymentStatus.PAID,
                    "success": PaymentStatus.PAID,
                    "expired": PaymentStatus.EXPIRED,
                    "failed": PaymentStatus.FAILED,
                    "cancelled": PaymentStatus.CANCELLED,
                }

                return PaymentStatusResult(
                    order_id=order_id,
                    status=status_map.get(cashi_status, PaymentStatus.PENDING),
                    provider="cashi",
                    amount=int(data.get("amount", 0)),
                    paid_at=data.get("paid_at"),
                    method=data.get("payment_method"),
                    raw_response=data,
                )

        except Exception as e:
            logger.error(f"Cashi check_status error: {e}", exc_info=True)
            return PaymentStatusResult(
                order_id=order_id,
                status=PaymentStatus.PENDING,
                provider="cashi",
                amount=0,
                paid_at=None,
                method=None,
                raw_response=None,
            )

    async def validate_webhook(self, payload: dict, headers: dict = None) -> WebhookResult:
        """
        Validate Cashi.id webhook callback.
        Cashi.id sends webhook with x-api-key header for authentication.
        Additional validation: check status via API for double-verification.
        """
        # Method 1: Validate API key in headers
        received_key = headers.get("x-api-key", "") if headers else ""
        if not received_key or not self.api_key or not secrets.compare_digest(received_key, self.api_key):
            logger.warning("Cashi webhook: invalid or missing API key")
            return WebhookResult(
                valid=False,
                order_id=None,
                status=None,
                amount=None,
                error_message="Invalid API key",
            )

        order_id = payload.get("order_id", "")
        cashi_status = payload.get("status", "")
        amount = payload.get("amount")

        if not order_id:
            return WebhookResult(
                valid=False, order_id=None, status=None,
                amount=None, error_message="Missing order_id",
            )

        # Method 2: Double-verify by checking status via API
        verified_status = await self.check_status(order_id)

        status_map = {
            "pending": PaymentStatus.PENDING,
            "paid": PaymentStatus.PAID,
            "success": PaymentStatus.PAID,
            "expired": PaymentStatus.EXPIRED,
            "failed": PaymentStatus.FAILED,
        }

        # Use API-verified status instead of webhook payload (more trustworthy)
        final_status = verified_status.status

        logger.info(
            f"Cashi webhook valid: {order_id} → {final_status.value}",
            extra={
                "order_id": order_id,
                "webhook_status": cashi_status,
                "verified_status": final_status.value,
            },
        )

        return WebhookResult(
            valid=True,
            order_id=order_id,
            status=final_status,
            amount=int(amount) if amount else verified_status.amount,
            error_message=None,
        )

    def get_supported_methods(self) -> list[str]:
        return ["qris", "qris_custom", "va_bca", "va_bni", "va_bri", "va_mandiri", "va_permata"]
