"""
Configuration settings for Andre Assassin High-WR Trading System
Uses Pydantic Settings for environment variable management
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
import os
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application Settings
    APP_NAME: str = "Andre Assassin High-WR Trading System"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")
    DEBUG: bool = Field(True, env="DEBUG")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")

    # Server Settings
    HOST: str = Field("0.0.0.0", env="HOST")
    PORT: int = Field(8000, env="PORT")
    WEBHOOK_PORT: int = Field(8000, env="WEBHOOK_PORT")
    WORKERS: int = Field(4, env="WORKERS")

    # Security
    SECRET_KEY: str = Field("your-secret-key-here", env="SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    CORS_ORIGINS: List[str] = Field(
        ["http://localhost:3000", "http://localhost:8080", "http://localhost:8000"],
        env="CORS_ORIGINS"
    )
    ALLOWED_HOSTS: List[str] = Field(["*"], env="ALLOWED_HOSTS")

    # Database Settings
    DATABASE_URL: str = Field(
        "postgresql+asyncpg://postgres:password@localhost:5432/andre_assassin",
        env="DATABASE_URL"
    )
    DATABASE_POOL_SIZE: int = Field(10, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(20, env="DATABASE_MAX_OVERFLOW")
    DATABASE_POOL_TIMEOUT: int = Field(30, env="DATABASE_POOL_TIMEOUT")
    DATABASE_POOL_RECYCLE: int = Field(3600, env="DATABASE_POOL_RECYCLE")

    # Redis Settings
    REDIS_URL: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    REDIS_POOL_SIZE: int = Field(10, env="REDIS_POOL_SIZE")
    REDIS_CACHE_TTL: int = Field(300, env="REDIS_CACHE_TTL")  # 5 minutes

    # Bybit API Settings
    BYBIT_API_KEY: str = Field("", env="BYBIT_API_KEY")
    BYBIT_API_SECRET: str = Field("", env="BYBIT_API_SECRET")
    BYBIT_TESTNET: bool = Field(True, env="BYBIT_TESTNET")
    BYBIT_RECV_WINDOW: int = Field(5000, env="BYBIT_RECV_WINDOW")

    # Trading Settings
    DEFAULT_SYMBOL: str = Field("BTCUSDT", env="DEFAULT_SYMBOL")
    DEFAULT_LEVERAGE: int = Field(5, env="DEFAULT_LEVERAGE")
    DEFAULT_POSITION_SIZE: float = Field(100.0, env="DEFAULT_POSITION_SIZE")
    MAX_POSITIONS: int = Field(5, env="MAX_POSITIONS")
    RISK_PER_TRADE: float = Field(0.01, env="RISK_PER_TRADE")  # 1% risk per trade

    # Demo Trading Settings
    DEMO_STARTING_BALANCE: float = Field(10000.0, env="DEMO_STARTING_BALANCE")
    DEMO_MAX_LEVERAGE: int = Field(10, env="DEMO_MAX_LEVERAGE")
    DEMO_MAKER_FEE: float = Field(0.0002, env="DEMO_MAKER_FEE")
    DEMO_TAKER_FEE: float = Field(0.00055, env="DEMO_TAKER_FEE")

    # Account & Risk Settings
    ACCOUNT_BALANCE_USD: float = Field(10000.0, env="ACCOUNT_BALANCE_USD")
    MAX_RISK_PER_TRADE_PCT: float = Field(2.0, env="MAX_RISK_PER_TRADE_PCT")
    MAX_EXPOSURE_PCT: float = Field(20.0, env="MAX_EXPOSURE_PCT")
    LEVERAGE: float = Field(5.0, env="LEVERAGE")
    MIN_RISK_REWARD_RATIO: float = Field(1.5, env="MIN_RISK_REWARD_RATIO")
    DEFAULT_SL_PCT: float = Field(3.0, env="DEFAULT_SL_PCT")

    # Phase Configuration
    PHASE_I_ENABLED: bool = Field(True, env="PHASE_I_ENABLED")
    PHASE_II_ENABLED: bool = Field(True, env="PHASE_II_ENABLED")
    PHASE_III_ENABLED: bool = Field(False, env="PHASE_III_ENABLED")

    # Signal Generation Settings
    SIGNAL_GENERATION_INTERVAL: int = Field(60, env="SIGNAL_GENERATION_INTERVAL")  # seconds
    SIGNAL_MIN_CONFIDENCE: float = Field(0.7, env="SIGNAL_MIN_CONFIDENCE")
    SIGNAL_HISTORY_DAYS: int = Field(30, env="SIGNAL_HISTORY_DAYS")

    # Strategy Settings
    MIN_WIN_RATE: float = Field(0.85, env="MIN_WIN_RATE")
    MIN_TRADES_FOR_STATS: int = Field(10, env="MIN_TRADES_FOR_STATS")
    STRATEGY_OPTIMIZATION_INTERVAL: int = Field(3600, env="STRATEGY_OPTIMIZATION_INTERVAL")  # 1 hour
    MAX_STRATEGIES_ACTIVE: int = Field(3, env="MAX_STRATEGIES_ACTIVE")

    # WebSocket Settings
    WS_HEARTBEAT_INTERVAL: int = Field(30, env="WS_HEARTBEAT_INTERVAL")
    WS_MAX_CONNECTIONS: int = Field(100, env="WS_MAX_CONNECTIONS")
    WS_MESSAGE_QUEUE_SIZE: int = Field(1000, env="WS_MESSAGE_QUEUE_SIZE")

    # Market Data Settings
    OHLCV_INTERVALS: List[str] = Field(
        ["1m", "5m", "15m", "1h", "4h", "1d"],
        env="OHLCV_INTERVALS"
    )
    MAX_CANDLES_FETCH: int = Field(1000, env="MAX_CANDLES_FETCH")
    PRICE_UPDATE_INTERVAL: int = Field(1, env="PRICE_UPDATE_INTERVAL")  # seconds

    # Monitoring & Metrics
    ENABLE_METRICS: bool = Field(True, env="ENABLE_METRICS")
    METRICS_PORT: int = Field(9090, env="METRICS_PORT")
    HEALTH_CHECK_INTERVAL: int = Field(60, env="HEALTH_CHECK_INTERVAL")

    # Notification Settings
    ENABLE_NOTIFICATIONS: bool = Field(False, env="ENABLE_NOTIFICATIONS")
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(None, env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: Optional[str] = Field(None, env="TELEGRAM_CHAT_ID")
    DISCORD_WEBHOOK_URL: Optional[str] = Field(None, env="DISCORD_WEBHOOK_URL")

    # AI/ML Settings
    ENABLE_AI_ANALYSIS: bool = Field(False, env="ENABLE_AI_ANALYSIS")
    AI_MODEL_PATH: Optional[str] = Field(None, env="AI_MODEL_PATH")
    AI_CONFIDENCE_THRESHOLD: float = Field(0.8, env="AI_CONFIDENCE_THRESHOLD")

    # Testing Settings
    TESTING: bool = Field(False, env="TESTING")
    TEST_DATABASE_URL: str = Field(
        "postgresql+asyncpg://postgres:password@localhost:5432/andre_assassin_test",
        env="TEST_DATABASE_URL"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    def get_database_url(self) -> str:
        """Get the appropriate database URL based on environment"""
        if self.TESTING:
            return self.TEST_DATABASE_URL
        return self.DATABASE_URL

    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT.lower() == "production"

    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.ENVIRONMENT.lower() == "development"

    def get_redis_settings(self) -> dict:
        """Get Redis connection settings"""
        return {
            "url": self.REDIS_URL,
            "max_connections": self.REDIS_POOL_SIZE,
            "decode_responses": True,
            "health_check_interval": 30
        }

    def get_bybit_settings(self) -> dict:
        """Get Bybit API settings"""
        return {
            "api_key": self.BYBIT_API_KEY,
            "api_secret": self.BYBIT_API_SECRET,
            "testnet": self.BYBIT_TESTNET,
            "recv_window": self.BYBIT_RECV_WINDOW
        }

    def get_cors_settings(self) -> dict:
        """Get CORS middleware settings"""
        return {
            "allow_origins": self.CORS_ORIGINS,
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"]
        }


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Create global settings instance
settings = get_settings()