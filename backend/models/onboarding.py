"""
Seller onboarding wizard models.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.sql import func

from models.database import Base


class SellerOnboarding(Base):
    __tablename__ = "seller_onboarding"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    # Step completion flags
    step_profile = Column(Boolean, default=False, nullable=False)
    step_product = Column(Boolean, default=False, nullable=False)
    step_payment = Column(Boolean, default=False, nullable=False)
    step_whatsapp = Column(Boolean, default=False, nullable=False)
    step_ai_persona = Column(Boolean, default=False, nullable=False)
    step_test_chat = Column(Boolean, default=False, nullable=False)
    step_go_live = Column(Boolean, default=False, nullable=False)

    current_step = Column(String(50), default="profile")
    completed = Column(Boolean, default=False, nullable=False)
    metadata_json = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
