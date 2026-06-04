"""
JUALIN.AI — Order Model
Orders created by AI agent from chat conversations.

Status Flow:
    PENDING → CONFIRMED → PAID → PROCESSING → SHIPPED → DELIVERED → DONE
                                                                   ↓
    Any status ──────────────────────────────────────────→ CANCELLED
    PAID/PROCESSING ─────────────────────────────────────→ REFUNDED
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum as SAEnum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from models.database import Base


class OrderStatus(str, enum.Enum):
    """
    Order lifecycle status.
    Each transition is validated by VALID_TRANSITIONS below.
    """
    PENDING = "pending"          # Order dibuat, belum dikonfirmasi
    CONFIRMED = "confirmed"      # Seller konfirmasi order
    PAID = "paid"                # Pembayaran diterima
    PROCESSING = "processing"    # Sedang diproses/dikemas
    SHIPPED = "shipped"          # Sudah dikirim
    DELIVERED = "delivered"      # Sudah sampai ke customer
    DONE = "done"                # Selesai (customer konfirmasi)
    CANCELLED = "cancelled"      # Dibatalkan
    REFUNDED = "refunded"        # Dikembalikan dananya


# ── Valid Status Transitions ──
# Key = current status, Value = set of allowed next statuses
VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {
        OrderStatus.CONFIRMED,
        OrderStatus.PAID,       # Direct payment (skip confirmation)
        OrderStatus.CANCELLED,
    },
    OrderStatus.CONFIRMED: {
        OrderStatus.PAID,
        OrderStatus.CANCELLED,
    },
    OrderStatus.PAID: {
        OrderStatus.PROCESSING,
        OrderStatus.SHIPPED,    # Skip processing for simple stores
        OrderStatus.CANCELLED,
        OrderStatus.REFUNDED,
    },
    OrderStatus.PROCESSING: {
        OrderStatus.SHIPPED,
        OrderStatus.CANCELLED,
        OrderStatus.REFUNDED,
    },
    OrderStatus.SHIPPED: {
        OrderStatus.DELIVERED,
        OrderStatus.DONE,       # Skip delivered for COD-like flow
    },
    OrderStatus.DELIVERED: {
        OrderStatus.DONE,
        OrderStatus.REFUNDED,
    },
    OrderStatus.DONE: set(),         # Terminal state
    OrderStatus.CANCELLED: set(),    # Terminal state
    OrderStatus.REFUNDED: set(),     # Terminal state
}


def is_valid_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
    """
    Check if a status transition is valid.
    Returns True if the transition is allowed.
    """
    allowed = VALID_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def get_allowed_transitions(current_status: OrderStatus) -> list[str]:
    """
    Get list of allowed next statuses for the current status.
    Used by frontend to show available action buttons.
    """
    allowed = VALID_TRANSITIONS.get(current_status, set())
    return sorted([s.value for s in allowed])


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)

    # Customer info
    customer_name = Column(String(255), nullable=False)
    customer_phone = Column(String(20), default="")
    customer_address = Column(Text, default="")

    # Order details
    items = Column(JSON, nullable=False)  # [{"product_id": 1, "nama": "Baju Pink", "qty": 2, "harga": 89000}]
    total = Column(Float, nullable=False)

    # Status
    status = Column(SAEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    notes = Column(Text, default="")

    # Payment info (populated after payment is created)
    payment_method = Column(String(50), nullable=True)   # "qris", "va_bca", "gopay", "snap"
    payment_provider = Column(String(20), nullable=True)  # "midtrans", "cashi"
    payment_invoice_id = Column(String(100), nullable=True, index=True)  # Provider order/invoice id
    payment_access_token = Column(String(100), nullable=True, index=True)  # Public payment page token
    payment_url = Column(String(500), nullable=True)      # URL or QR data
    payment_qr_data = Column(Text, nullable=True)
    payment_va_number = Column(String(100), nullable=True)
    payment_expires_at = Column(String(100), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    # Follow-up tracking
    followup_count = Column(Integer, default=0)
    last_followup_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    seller = relationship("User", back_populates="orders")
    conversation = relationship("Conversation", back_populates="orders")
    status_history = relationship(
        "OrderStatusHistory",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusHistory.created_at",
    )
