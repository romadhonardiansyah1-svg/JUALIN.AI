"""
JUALIN.AI — Configuration
Loads environment variables from .env file
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "JUALIN.AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    SECRET_KEY: str = "jualin-ai-secret-key-change-in-production"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/jualin_ai"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # JWT
    JWT_SECRET_KEY: str = "jwt-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours
    
    # LLM (9Router or direct)
    LLM_BASE_URL: str = "http://localhost:20128/v1"  # 9Router
    LLM_API_KEY: str = "not-needed"  # 9Router handles keys
    LLM_MODEL: str = "llama-3.1-8b-instant"
    
    # Gemini (backup / image AI)
    GEMINI_API_KEY: str = ""
    
    # Embedding
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    
    # Quota limits per tier
    QUOTA_FREE: int = 50
    QUOTA_STARTER: int = 500
    QUOTA_PRO: int = 2000
    QUOTA_BISNIS: int = 10000
    
    # Product limits per tier
    PRODUCT_LIMIT_FREE: int = 10
    PRODUCT_LIMIT_STARTER: int = 50
    PRODUCT_LIMIT_PRO: int = 200
    PRODUCT_LIMIT_BISNIS: int = 999999  # unlimited
    
    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
