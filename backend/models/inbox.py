"""
WhatsApp-first inbox models.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, UniqueConstraint
from sqlalchemy.sql import func

from models.database import Base


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    external_id = Column(String(255), default="", index=True)
    display_name = Column(String(255), default="")
    status = Column(String(20), default="inactive", nullable=False)
    config_encrypted = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("seller_id", "type", "provider", "external_id", name="uq_channel_external"),
    )


class ChannelContact(Base):
    __tablename__ = "channel_contacts"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False, index=True)
    external_id = Column(String(255), nullable=False, index=True)
    phone = Column(String(50), default="", index=True)
    name = Column(String(255), default="Customer")
    profile = Column(JSON, default=dict)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("seller_id", "channel_id", "external_id", name="uq_channel_contact_external"),
    )


class InboxThread(Base):
    __tablename__ = "inbox_threads"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey("channel_contacts.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    external_thread_id = Column(String(255), default="", index=True)
    mode = Column(String(20), default="ai", nullable=False)
    status = Column(String(20), default="open", nullable=False)
    stage = Column(String(50), default="new")
    last_message_preview = Column(String(500), default="")
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    unread_count = Column(Integer, default=0)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("seller_id", "channel_id", "contact_id", name="uq_inbox_thread_contact"),
    )


class InboxMessage(Base):
    __tablename__ = "inbox_messages"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    thread_id = Column(Integer, ForeignKey("inbox_threads.id"), nullable=False, index=True)
    direction = Column(String(20), nullable=False)
    role = Column(String(20), nullable=False)
    content_type = Column(String(50), default="text")
    content = Column(Text, default="")
    external_message_id = Column(String(255), default="", index=True)
    status = Column(String(20), default="received")
    raw_payload = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
