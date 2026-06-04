"""
Customer Scoring model.
Score computed from real events: chat recency, order history, paid status, campaign response, tags.
Score must be explainable — reason codes included in response.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, JSON
from sqlalchemy.sql import func

from models.database import Base


class CustomerScore(Base):
    __tablename__ = "customer_scores"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, unique=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    purchase_likelihood = Column(Float, default=0)  # 0-100
    repeat_likelihood = Column(Float, default=0)
    churn_risk = Column(Float, default=0)
    value_score = Column(Float, default=0)
    support_risk = Column(Float, default=0)

    overall_score = Column(Float, default=0)  # weighted average
    tier = Column(String(20), default="unknown")  # hot, warm, cold, unknown

    reason_codes = Column(JSON, default=list)  # [{code, label, impact}]
    input_signals = Column(JSON, default=dict)  # raw signals used for scoring

    computed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
