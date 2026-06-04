"""
Human QA Review Queue model.
Items enter queue when: low confidence, action failure, complaint, feedback down,
payment conflict, or sensitive discount attempt.
Approval/reject must be audit logged.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.sql import func

from models.database import Base


class QAReviewItem(Base):
    __tablename__ = "qa_review_items"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)  # low_confidence, action_failed, complaint, feedback_down, payment_conflict, sensitive_discount
    status = Column(String(20), default="pending", index=True)  # pending, approved, rejected, edited
    priority = Column(String(10), default="medium")  # low, medium, high, urgent

    # Context
    thread_id = Column(Integer, ForeignKey("inbox_threads.id"), nullable=True)
    message_id = Column(Integer, ForeignKey("inbox_messages.id"), nullable=True)
    trace_id = Column(Integer, ForeignKey("ai_traces.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)

    original_content = Column(Text, default="")
    edited_content = Column(Text, default="")
    reason = Column(Text, default="")
    reviewer_notes = Column(Text, default="")
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
