"""
Application Configuration
Environment variables and settings for Andre Assassin trading system
"""
import os
from typing import Optional
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    DATABASE_URL: Optional[str] = "postgresql+asyncpg://postgres:postgres@localhost/andre_assassin"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # API Keys
    ANTHROPIC_API_KEY: Optional[str] = None

    # Exchange API Keys (CCXT Pro)
    BINANCE_API_KEY: Optional[str] = None
    BINANCE_SECRET: Optional[str] = None

    BYBIT_API_KEY: Optional[str] = None
    BYBIT_SECRET: Optional[str] = None

    OKX_API_KEY: Optional[str] = None
    OKX_SECRET: Optional[str] = None
    OKX_PASSWORD: Optional[str] = None

    MEXC_API_KEY: Optional[str] = None
    MEXC_SECRET: Optional[str] = None

    # Application Settings
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Worker Settings
    GRID_SEARCH_WORKERS: int = 2
    AI_WORKERS: int = 1

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"  # Allow extra fields from .env


# Global settings instance
settings = Settings()
