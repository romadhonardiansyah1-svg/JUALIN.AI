"""
Internal AI quality, tracing, and evaluation models.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Float
from sqlalchemy.sql import func

from models.database import Base


class AITrace(Base):
    __tablename__ = "ai_traces"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True, index=True)
    trace_id = Column(String(100), nullable=False, unique=True, index=True)
    provider = Column(String(50), default="")
    model = Column(String(100), default="")
    stage = Column(String(50), default="")
    status = Column(String(20), default="ok", index=True)
    prompt_preview = Column(Text, default="")
    response_preview = Column(Text, default="")
    latency_ms = Column(Integer, default=0)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    confidence = Column(Float, default=0)
    error_message = Column(Text, default="")
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIToolCall(Base):
    __tablename__ = "ai_tool_calls"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String(100), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False)
    status = Column(String(20), default="ok")
    input_json = Column(JSON, default=dict)
    output_json = Column(JSON, default=dict)
    error_message = Column(Text, default="")
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIRetrievalLog(Base):
    __tablename__ = "ai_retrieval_logs"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String(100), nullable=False, index=True)
    query = Column(Text, default="")
    product_ids = Column(JSON, default=list)
    scores = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIFeedback(Base):
    __tablename__ = "ai_feedback"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message_id = Column(Integer, nullable=True, index=True)
    trace_id = Column(String(100), default="", index=True)
    rating = Column(String(20), nullable=False)
    reason = Column(String(100), default="")
    note = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIEvalCase(Base):
    __tablename__ = "ai_eval_cases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), default="")
    prompt = Column(Text, nullable=False)
    expected_behavior = Column(Text, default="")
    metadata_json = Column(JSON, default=dict)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIEvalRun(Base):
    __tablename__ = "ai_eval_runs"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    status = Column(String(20), default="queued")
    total_cases = Column(Integer, default=0)
    passed_cases = Column(Integer, default=0)
    failed_cases = Column(Integer, default=0)
    result_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
