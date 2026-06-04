"""
Inbox productization models: labels, internal notes, canned replies.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.sql import func

from models.database import Base


class InboxThreadLabel(Base):
    __tablename__ = "inbox_thread_labels"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    thread_id = Column(Integer, ForeignKey("inbox_threads.id"), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("thread_id", "label", name="uq_thread_label"),
    )


class InboxInternalNote(Base):
    __tablename__ = "inbox_internal_notes"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    thread_id = Column(Integer, ForeignKey("inbox_threads.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CannedReply(Base):
    __tablename__ = "canned_replies"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False, default="")
    category = Column(String(100), default="general")
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
