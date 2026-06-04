"""
Knowledge Base / RAG Builder models.
Retrieval traces source to ai_retrieval_logs.
AI must not fabricate if source not found — respond safely and handoff.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean, Text
from sqlalchemy.sql import func

from models.database import Base


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(30), nullable=False, index=True)  # manual, faq, policy, product_note, import_note
    title = Column(String(255), nullable=False)
    content = Column(Text, default="")
    status = Column(String(20), default="active", index=True)  # active, indexing, error
    chunk_count = Column(Integer, default=0)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)
    token_count = Column(Integer, default=0)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
