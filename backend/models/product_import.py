"""
Product import batch model for the preview-then-import flow.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func

from models.database import Base


class ProductImportBatch(Base):
    __tablename__ = "product_import_batches"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    preview_token = Column(String(100), nullable=False, unique=True, index=True)
    filename = Column(String(255), default="")
    rows_json = Column(JSON, default=list)
    errors_json = Column(JSON, default=list)
    status = Column(String(20), default="preview")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
