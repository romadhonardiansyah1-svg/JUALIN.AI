"""
Template pack install tracking — idempotency per seller per pack.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func

from models.database import Base


class TemplatePackInstall(Base):
    __tablename__ = "template_pack_installs"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    pack_id = Column(String(50), nullable=False, index=True)
    niche = Column(String(50), default="")
    installed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("seller_id", "pack_id", name="uq_template_pack_install"),
    )
