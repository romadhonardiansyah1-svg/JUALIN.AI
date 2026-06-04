"""
JUALIN.AI — Order Status History Model
Immutable audit log of every order status change.

Every status transition creates a new record here.
This provides:
- Full audit trail for disputes
- Timeline visualization for customers
- Analytics on order processing speed
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.database import Base


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)

    # Status transition
    from_status = Column(String(20), nullable=False)  # Previous status value
    to_status = Column(String(20), nullable=False)     # New status value

    # Who made the change
    changed_by = Column(String(50), default="system")  # "seller", "system", "payment_webhook"

    # Optional note about why the change was made
    note = Column(Text, default="")

    # When the change happened (immutable — never updated)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    order = relationship("Order", back_populates="status_history")
