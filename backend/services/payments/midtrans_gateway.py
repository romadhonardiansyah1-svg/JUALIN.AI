"""
JUALIN.AI — Midtrans Payment Gateway
Integration with Midtrans Snap API for multi-method payments.

Midtrans Snap provides an all-in-one payment page supporting:
- QRIS, GoPay, ShopeePay
- Bank Transfer (VA BCA, BNI, BRI, Mandiri, Permata)
- Credit/Debit Card
- E-wallets

API Docs: https://docs.midtrans.com/reference/backend-integration
Sandbox: https://simulator.sandbox.midtrans.com/
"""
import hashlib
import httpx
import base64
from typing import Optional

from config import get_settings
from core.logging_config import get_logger
from services.payments.base import (
    PaymentGateway, PaymentCreateResult, PaymentStatusResult,
    WebhookResult, PaymentStatus,
)

settings = get_settings()
logger = get_logger(__name__)


class MidtransGateway(PaymentGateway):
    """Midtrans Snap payment gateway implementation."""

    def __init__(self):
        self.server_key = settings.MIDTRANS_SERVER_KEY
        self.client_key = settings.MIDTRANS_CLIENT_KEY
        self.is_production = settings.MIDTRANS_IS_PRODUCTION

        # API URLs
        if self.is_production:
            self.snap_url = "https://app.midtrans.com/snap/v1"
            self.api_url = "https://api.midtrans.com/v2"
        else:
            self.snap_url = "https://app.sandbox.midtrans.com/snap/v1"
            self.api_url = "https://api.sandbox.midtrans.com/v2"

        # Auth header (Base64 encoded server_key:)
        self._auth_header = base64.b64encode(
            f"{self.server_key}:".encode()
        ).decode()

    @property
    def provider_name(self) -> str:
        return "midtrans"

    async def create_payment(
        self,
        order_id: int,
        amount: int,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        items: list[dict],
        method: str = "snap",
        payment_token: str = "",
    ) -> PaymentCreateResult:
        """
        Create a Midtrans Snap transaction.
        Returns a snap_token and redirect_url for the payment page.
        """
        invoice_id = f"JUALIN-{order_id}-{int(__import__('time').time())}"
        frontend_url = settings.FRONTEND_URL.rstrip("/")
        token_query = f"&token={payment_token}" if payment_token else ""

        # Build item details for Midtrans
        midtrans_items = []
        for item in items:
            midtrans_items.append({
                "id": str(item.get("product_id", "item")),
                "price": int(item.get("harga", 0)),
                "quantity": int(item.get("qty", 1)),
                "name": str(item.get("nama", "Produk"))[:50],  # Max 50 chars
            })

        payload = {
            "transaction_details": {
                "order_id": invoice_id,
                "gross_amount": int(amount),
            },
            "item_details": midtrans_items,
            "customer_details": {
                "first_name": customer_name[:40],
                "email": customer_email or "customer@jualin.ai",
                "phone": customer_phone or "",
            },
            "callbacks": {
                "finish": f"{frontend_url}/pay/{order_id}?status=finish{token_query}",
                "error": f"{frontend_url}/pay/{order_id}?status=error{token_query}",
                "pending": f"{frontend_url}/pay/{order_id}?status=pending{token_query}",
            },
            "expiry": {
                "unit": "minutes",
                "duration": 60,  # 1 hour expiry
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self.snap_url}/transactions",
                    json=payload,
                    headers={
                        "Authorization": f"Basic {self._auth_header}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )

                if response.status_code != 201:
                    error_data = response.json() if response.text else {}
                    logger.error(
                        f"Midtrans create_payment failed: {response.status_code}",
                        extra={"response": error_data, "order_id": order_id},
                    )
                    return PaymentCreateResult(
                        success=False,
                        order_id=invoice_id,
                        provider="midtrans",
                        method=method,
                        amount=amount,
                        payment_url=None,
                        qr_data=None,
                        token=None,
                        expires_at=None,
                        error_message=error_data.get("error_messages", ["Midtrans error"])[0]
                            if isinstance(error_data.get("error_messages"), list)
                            else str(error_data),
                        raw_response=error_data,
                    )

                data = response.json()
                snap_token = data.get("token")
                redirect_url = data.get("redirect_url")

                logger.info(
                    f"Midtrans payment created: {invoice_id}",
                    extra={
                        "order_id": order_id,
                        "invoice_id": invoice_id,
                        "amount": amount,
                        "snap_token": snap_token[:10] + "..." if snap_token else None,
                    },
                )

                return PaymentCreateResult(
                    success=True,
                    order_id=invoice_id,
                    provider="midtrans",
                    method=method,
                    amount=amount,
                    payment_url=redirect_url,
                    qr_data=None,
                    token=snap_token,
                    expires_at=None,
                    error_message=None,
                    raw_response=data,
                )

        except httpx.TimeoutException:
            logger.error(f"Midtrans timeout for order #{order_id}")
            return PaymentCreateResult(
                success=False, order_id=invoice_id, provider="midtrans",
                method=method, amount=amount, payment_url=None, qr_data=None,
                token=None, expires_at=None,
                error_message="Payment gateway timeout. Coba lagi.",
                raw_response=None,
            )
        except Exception as e:
            logger.error(f"Midtrans error: {e}", exc_info=True)
            return PaymentCreateResult(
                success=False, order_id=invoice_id, provider="midtrans",
                method=method, amount=amount, payment_url=None, qr_data=None,
                token=None, expires_at=None,
                error_message=f"Gagal membuat pembayaran: {str(e)}",
                raw_response=None,
            )

    async def check_status(self, order_id: str) -> PaymentStatusResult:
        """Check payment status via Midtrans Status API."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.api_url}/{order_id}/status",
                    headers={
                        "Authorization": f"Basic {self._auth_header}",
                        "Accept": "application/json",
                    },
                )

                data = response.json()
                mt_status = data.get("transaction_status", "")
                fraud = data.get("fraud_status", "accept")

                # Map Midtrans status to our unified status
                status_map = {
                    "capture": PaymentStatus.PAID if fraud == "accept" else PaymentStatus.PENDING,
                    "settlement": PaymentStatus.PAID,
                    "pending": PaymentStatus.PENDING,
                    "deny": PaymentStatus.FAILED,
                    "cancel": PaymentStatus.CANCELLED,
                    "expire": PaymentStatus.EXPIRED,
                    "refund": PaymentStatus.REFUNDED,
                    "partial_refund": PaymentStatus.REFUNDED,
                }

                return PaymentStatusResult(
                    order_id=order_id,
                    status=status_map.get(mt_status, PaymentStatus.PENDING),
                    provider="midtrans",
                    amount=int(float(data.get("gross_amount", 0))),
                    paid_at=data.get("settlement_time"),
                    method=data.get("payment_type"),
                    raw_response=data,
                )

        except Exception as e:
            logger.error(f"Midtrans check_status error: {e}", exc_info=True)
            return PaymentStatusResult(
                order_id=order_id,
                status=PaymentStatus.PENDING,
                provider="midtrans",
                amount=0,
                paid_at=None,
                method=None,
                raw_response=None,
            )

    async def validate_webhook(self, payload: dict, headers: dict = None) -> WebhookResult:
        """
        Validate Midtrans webhook notification.
        Signature: SHA512(order_id + status_code + gross_amount + server_key)
        """
        order_id = payload.get("order_id", "")
        status_code = payload.get("status_code", "")
        gross_amount = payload.get("gross_amount", "")
        signature_key = payload.get("signature_key", "")

        # Verify signature
        raw = f"{order_id}{status_code}{gross_amount}{self.server_key}"
        expected_sig = hashlib.sha512(raw.encode()).hexdigest()

        if signature_key != expected_sig:
            logger.warning(
                f"Midtrans webhook signature mismatch: {order_id}",
                extra={"received": signature_key[:20], "expected": expected_sig[:20]},
            )
            return WebhookResult(
                valid=False,
                order_id=order_id,
                status=None,
                amount=None,
                error_message="Invalid signature",
            )

        # Map status
        transaction_status = payload.get("transaction_status", "")
        fraud_status = payload.get("fraud_status", "accept")

        status_map = {
            "capture": PaymentStatus.PAID if fraud_status == "accept" else PaymentStatus.PENDING,
            "settlement": PaymentStatus.PAID,
            "pending": PaymentStatus.PENDING,
            "deny": PaymentStatus.FAILED,
            "cancel": PaymentStatus.CANCELLED,
            "expire": PaymentStatus.EXPIRED,
            "refund": PaymentStatus.REFUNDED,
        }

        status = status_map.get(transaction_status, PaymentStatus.PENDING)

        logger.info(
            f"Midtrans webhook valid: {order_id} → {status.value}",
            extra={"order_id": order_id, "transaction_status": transaction_status},
        )

        return WebhookResult(
            valid=True,
            order_id=order_id,
            status=status,
            amount=int(float(gross_amount)) if gross_amount else None,
            error_message=None,
        )

    def get_supported_methods(self) -> list[str]:
        return [
            "snap", "qris", "gopay", "shopeepay",
            "va_bca", "va_bni", "va_bri", "va_mandiri", "va_permata",
        ]
