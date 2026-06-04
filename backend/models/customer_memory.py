"""
JUALIN.AI — Customer Memory Model
Ringkasan hemat per customer (~200 byte each)
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Float
from sqlalchemy.sql import func

from models.database import Base


class CustomerMemory(Base):
    __tablename__ = "customer_memories"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Identifier (match by phone > name > session)
    phone = Column(String(20), default="", index=True)
    name = Column(String(100), default="Customer")
    session_ids = Column(JSON, default=list)  # ["sess-1", "sess-2"] — riwayat session

    # Ringkasan HEMAT (bukan full history)
    total_orders = Column(Integer, default=0)
    total_spent = Column(Float, default=0)
    last_products = Column(JSON, default=list)     # ["Baju Pink", "Kaos Oversize"] max 5
    preferences = Column(JSON, default=list)       # ["pink", "satin", "M"] max 5
    tags = Column(JSON, default=list)              # ["repeat_buyer", "high_value", "price_sensitive"] auto-generated
    sentiment = Column(String(20), default="neutral")  # positive, neutral, negative
    notes = Column(String(500), default="")        # Ringkasan singkat

    # Visit tracking
    visit_count = Column(Integer, default=1)
    first_visit = Column(DateTime(timezone=True), server_default=func.now())
    last_visit = Column(DateTime(timezone=True), server_default=func.now())
