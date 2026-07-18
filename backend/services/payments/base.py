"""Shared payment contracts for the Midtrans Snap integration."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class PaymentMethod(str, Enum):
    """Supported payment methods."""
    QRIS = "qris"
    QRIS_CUSTOM = "qris_custom"
    VA_BCA = "va_bca"
    VA_BNI = "va_bni"
    VA_BRI = "va_bri"
    VA_MANDIRI = "va_mandiri"
    VA_PERMATA = "va_permata"
    GOPAY = "gopay"
    SHOPEEPAY = "shopeepay"
    SNAP = "snap"           # Midtrans Snap (all-in-one)


class PaymentStatus(str, Enum):
    """Unified payment status across all providers."""
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    CANCELLED = "cancelled"


@dataclass
class PaymentCreateResult:
    """Unified result from creating a payment."""
    success: bool
    order_id: str                # Our internal order ID / invoice ID
    provider: str                # "midtrans"
    method: str                  # Payment method used
    amount: int                  # Amount in IDR (int — no decimals)
    payment_url: Optional[str]   # URL for customer to pay (checkout page or QR)
    qr_data: Optional[str]       # QR image data (base64) if applicable
    token: Optional[str]         # Payment token (Midtrans snap_token)
    expires_at: Optional[str]    # Expiry time string
    error_message: Optional[str] # Error message if failed
    raw_response: Optional[dict] # Full provider response for debugging


@dataclass
class PaymentStatusResult:
    """Unified result from checking payment status."""
    order_id: str
    status: PaymentStatus
    provider: str
    amount: Optional[int]
    paid_at: Optional[str]
    method: Optional[str]
    raw_response: Optional[dict]
    verified: bool = True


@dataclass
class WebhookResult:
    """Unified result from processing a webhook callback."""
    valid: bool                  # Was the webhook signature valid?
    order_id: Optional[str]
    status: Optional[PaymentStatus]
    amount: Optional[int]
    error_message: Optional[str]


class PaymentGateway(ABC):
    """Abstract contract implemented by the Midtrans gateway."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier: 'midtrans'."""
        ...

    @abstractmethod
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
        Create a new payment.
        Returns PaymentCreateResult with payment URL / QR / token.
        """
        ...

    @abstractmethod
    async def check_status(self, order_id: str) -> PaymentStatusResult:
        """
        Check payment status by order ID.
        Returns PaymentStatusResult with current status.
        """
        ...

    @abstractmethod
    async def validate_webhook(self, payload: dict, headers: dict = None) -> WebhookResult:
        """
        Validate and process a webhook callback.
        Returns WebhookResult with validated order info.
        MUST validate signature/hash to prevent forged callbacks.
        """
        ...

    def get_supported_methods(self) -> list[str]:
        """Return list of supported payment methods for this provider."""
        return []
