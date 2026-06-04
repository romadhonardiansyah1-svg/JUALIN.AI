"""
JUALIN.AI — Chat Analytics Model
Tracks per-interaction metrics for funnel analysis, response quality,
and sales stage monitoring.

Every AI response creates one record here, enabling:
- Conversion funnel: visit → chat → order
- Intent distribution (what customers ask about)
- Sales stage progression analysis
- Response time monitoring
- Token usage tracking
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func

from models.database import Base


class ChatAnalytics(Base):
    __tablename__ = "chat_analytics"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # What was detected
    intent = Column(String(30), default="general")          # product, policy, smalltalk, order, general
    sales_stage = Column(String(30), default="greeting")     # greeting, discovery, presentation, negotiation, closing, post_sale

    # Performance metrics
    response_time_ms = Column(Integer, default=0)            # Time from request to full response
    tokens_used = Column(Integer, default=0)                 # Approximate LLM tokens consumed

    # Outcome tracking
    converted_to_order = Column(Boolean, default=False)      # Did this chat lead to an order?
    customer_sentiment = Column(String(20), default="neutral")  # positive, neutral, negative

    # Message info
    user_message_length = Column(Integer, default=0)         # Character count of user message
    ai_response_length = Column(Integer, default=0)          # Character count of AI response

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())
