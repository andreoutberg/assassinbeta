"""
Configuration Management
Loads environment variables and provides type-safe configuration
"""
from pydantic_settings import BaseSettings
from typing import List
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application configuration"""

    # Environment
    ENVIRONMENT: str = "production"  # Changed from "development" to prevent auto-reload loops

    # Webhook Configuration
    WEBHOOK_SECRET: str = "change_me_in_production"
    WEBHOOK_PORT: int = 5001

    # PostgreSQL Database Configuration
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "andre_assassin"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"

    # Database Connection Pooling (for multi-strategy scale)
    # Pool size: Max concurrent database connections
    # Designed for 1000 concurrent trades with WebSocket price tracking
    # Connection leak fixed - can now safely use larger pool
    DATABASE_POOL_SIZE: int = 150  # Base pool for high concurrency
    DATABASE_MAX_OVERFLOW: int = 150  # Overflow capacity (total 300 connections max)
    DATABASE_POOL_RECYCLE: int = 3600  # Recycle connections every hour (seconds)
    DATABASE_POOL_PRE_PING: bool = True  # Test connections before use (detect stale connections)
    DATABASE_POOL_TIMEOUT: int = 30  # Max seconds to wait for connection from pool
    DATABASE_ECHO: bool = False  # Set to True for SQL query logging (debug only)

    @property
    def DATABASE_URL(self) -> str:
        """Construct database URL"""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def DATABASE_URL_ASYNC(self) -> str:
        """Construct async database URL for asyncpg"""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # AI/ML Configuration
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # Analysis Configuration
    MIN_CANDLES_FOR_ANALYSIS: int = 50
    CONFIDENCE_THRESHOLD: float = 0.75

    # AO Dashboard Integration
    AO_DASHBOARD_URL: str = "http://localhost:5000"
    AO_API_KEY: str = ""
    ENABLE_DASHBOARD_INTEGRATION: bool = False

    # Security
    API_KEY: str = "dev_api_key_change_in_production"
    ALLOWED_IPS: str = "127.0.0.1,localhost"  # Comma-separated list

    @property
    def ALLOWED_IPS_LIST(self) -> List[str]:
        """Parse comma-separated IPs"""
        return [ip.strip() for ip in self.ALLOWED_IPS.split(",")]

    # CORS Configuration
    CORS_ORIGINS: str = "http://localhost:5000,http://localhost:3000"  # Comma-separated

    @property
    def CORS_ORIGINS_LIST(self) -> List[str]:
        """Parse comma-separated origins"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"

    # Feature Flags
    ENABLE_REAL_TIME_ANALYSIS: bool = True
    ENABLE_ML_PREDICTIONS: bool = True
    ENABLE_NOTIFICATIONS: bool = False

    # Beta System Forwarding
    ENABLE_BETA_FORWARDING: bool = False
    BETA_WEBHOOK_URL: str = "http://localhost:5002/api/webhook/tradingview"
    BETA_FORWARD_TIMEOUT: float = 5.0
    BETA_FORWARD_RETRY_COUNT: int = 1
    BETA_FORWARD_RATE_LIMIT: int = 100  # Max forwards per minute

    # Account Risk Management (V2 Architecture)
    ACCOUNT_BALANCE_USD: float = 100000.0
    MAX_RISK_PER_TRADE_PCT: float = 0.1
    MAX_CONCURRENT_TRADES: int = 1000  # Paper trading - allow many concurrent trades (was 10)
    MAX_EXPOSURE_PCT: float = 1000.0  # Paper trading - effectively unlimited (was 20%)
    MIN_RISK_REWARD_RATIO: float = 1.0  # Changed from 1.5 to 1.0 for high-WR optimization
    DEFAULT_SL_PCT: float = 3.0
    LEVERAGE: float = 5.0  # 5x leverage for all trades

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Create global settings instance
settings = Settings()


# Ensure logs directory exists
Path("logs").mkdir(exist_ok=True)
