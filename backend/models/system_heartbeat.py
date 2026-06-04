"""
System heartbeat model for worker health monitoring.
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func

from models.database import Base


class SystemHeartbeat(Base):
    __tablename__ = "system_heartbeats"

    id = Column(Integer, primary_key=True, index=True)
    service = Column(String(100), nullable=False, unique=True, index=True)
    status = Column(String(20), default="alive")
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    metadata_json = Column(JSON, default=dict)
