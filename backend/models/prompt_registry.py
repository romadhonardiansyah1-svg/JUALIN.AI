"""
Prompt registry for versioned AI prompts.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.sql import func

from models.database import Base


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True, index=True)
    prompt_key = Column(String(100), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    content = Column(Text, nullable=False, default="")
    description = Column(String(500), default="")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
