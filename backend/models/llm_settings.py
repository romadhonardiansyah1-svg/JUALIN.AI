"""
JUALIN.AI — Konfigurasi LLM yang bisa diatur admin dari dashboard (singleton row id=1).
is_enabled=False berarti seluruh sistem memakai konfigurasi .env seperti sebelumnya (rollback aman).
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, text
from sqlalchemy.sql import func

from models.database import Base


class LLMProvider(Base):
    """Provider LLM multi-endpoint (Groq/OpenRouter/OpenAI-compatible/dll).

    Router mencoba provider yang aktif secara berurutan menurut `priority`
    (angka kecil = didahulukan), dengan failover antar-provider dan antar-key.
    Bila tidak ada baris aktif, sistem jatuh ke singleton LLMSettings lalu .env.
    """
    __tablename__ = "llm_providers"

    id = Column(Integer, primary_key=True)
    label = Column(String(60), server_default="")            # nama bebas untuk UI (mis. "Groq", "OpenRouter")
    base_url = Column(String(255), server_default="")         # endpoint OpenAI-compatible (…/v1)
    model = Column(String(100), server_default="")            # model utama
    light_model = Column(String(100), server_default="")      # model ringan (nego); kosong = model utama
    fallback_model = Column(String(100), server_default="")   # dicoba bila model utama gagal
    api_keys_json = Column(JSON, default=list)                # ["sk-…", …] — dirotasi + failover
    priority = Column(Integer, nullable=False, default=100, server_default="100")
    is_enabled = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class LLMSettings(Base):
    __tablename__ = "llm_settings"

    id = Column(Integer, primary_key=True)          # selalu 1 (singleton)
    is_enabled = Column(Boolean, default=False, nullable=False)

    provider_label = Column(String(50), default="9router")   # label bebas utk UI
    base_url = Column(String(255), default="")                # kosong = pakai env LLM_BASE_URL
    model = Column(String(100), default="")                   # model utama (chat penjualan, brief)
    light_model = Column(String(100), default="")             # model ringan/cepat (phrasing nego); kosong = pakai model utama
    fallback_model = Column(String(100), default="")          # dicoba bila model utama gagal di semua key

    api_keys_json = Column(JSON, default=list)                # ["sk-xxx", "sk-yyy", ...] — DITUMPUK, dirotasi

    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
