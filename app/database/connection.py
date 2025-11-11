"""
Database connection management with async PostgreSQL pool
"""
import os
from typing import AsyncGenerator, Optional, Any
import asyncpg
from asyncpg.pool import Pool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from contextlib import asynccontextmanager
import redis.asyncio as redis
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)

# Database configuration from settings
DATABASE_URL = settings.get_database_url()
REDIS_URL = settings.REDIS_URL

# SQLAlchemy setup
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()

# Redis client
redis_client = None

async def init_redis() -> redis.Redis:
    """Initialize Redis connection"""
    global redis_client
    if not redis_client:
        redis_client = redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return redis_client

async def get_redis() -> redis.Redis:
    """Get Redis client"""
    if not redis_client:
        await init_redis()
    return redis_client

# AsyncPG connection pool for raw queries
asyncpg_pool: Pool = None

async def init_asyncpg_pool() -> Pool:
    """Initialize asyncpg connection pool"""
    global asyncpg_pool
    if not asyncpg_pool:
        asyncpg_pool = await asyncpg.create_pool(
            os.getenv(
                "DATABASE_URL_ASYNCPG",
                "postgresql://postgres:postgres@localhost:5432/high_wr_trading"
            ),
            min_size=10,
            max_size=30,
            command_timeout=60,
            max_queries=50000,
            max_cached_statement_lifetime=300,
        )
    return asyncpg_pool

async def get_asyncpg_pool() -> Pool:
    """Get asyncpg pool"""
    if not asyncpg_pool:
        await init_asyncpg_pool()
    return asyncpg_pool

# Dependency for FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Database session dependency"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

@asynccontextmanager
async def get_db_context():
    """Context manager for database sessions"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def close_connections():
    """Close all database connections"""
    global asyncpg_pool, redis_client

    if asyncpg_pool:
        await asyncpg_pool.close()
        asyncpg_pool = None

    if redis_client:
        await redis_client.close()
        redis_client = None

    await engine.dispose()

# Health check functions
async def check_database_health() -> bool:
    """Check if database is healthy"""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception:
        return False

async def check_redis_health() -> bool:
    """Check if Redis is healthy"""
    try:
        client = await get_redis()
        return await client.ping()
    except Exception:
        return False


class DatabaseManager:
    """
    Centralized database connection manager
    Handles both SQLAlchemy and raw asyncpg connections
    """

    def __init__(self):
        self.engine = None
        self.asyncpg_pool: Optional[Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.session_factory = None

    async def initialize(self):
        """Initialize all database connections"""
        try:
            # Initialize SQLAlchemy engine
            logger.info("Initializing SQLAlchemy engine...")
            self.engine = create_async_engine(
                DATABASE_URL,
                echo=settings.DEBUG,
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                pool_timeout=settings.DATABASE_POOL_TIMEOUT,
                pool_recycle=settings.DATABASE_POOL_RECYCLE,
                pool_pre_ping=True,
            )

            # Create session factory
            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False,
            )

            # Initialize asyncpg pool for raw queries
            logger.info("Initializing asyncpg connection pool...")
            db_url = DATABASE_URL.replace("+asyncpg", "")  # Remove SQLAlchemy driver
            self.asyncpg_pool = await asyncpg.create_pool(
                db_url,
                min_size=10,
                max_size=settings.DATABASE_POOL_SIZE,
                command_timeout=60,
                max_queries=50000,
                max_cached_statement_lifetime=300,
            )

            # Initialize Redis
            logger.info("Initializing Redis connection...")
            self.redis_client = redis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=settings.REDIS_POOL_SIZE,
            )

            # Test connections
            await self.test_connections()
            logger.info("All database connections initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database connections: {e}")
            raise

    async def test_connections(self):
        """Test all database connections"""
        # Test SQLAlchemy
        async with self.session_factory() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1

        # Test asyncpg
        async with self.asyncpg_pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1

        # Test Redis
        assert await self.redis_client.ping()

    async def close(self):
        """Close all database connections"""
        try:
            if self.asyncpg_pool:
                await self.asyncpg_pool.close()

            if self.redis_client:
                await self.redis_client.close()

            if self.engine:
                await self.engine.dispose()

            logger.info("All database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")

    async def get_session(self) -> AsyncSession:
        """Get a new database session"""
        if not self.session_factory:
            raise RuntimeError("Database not initialized")
        return self.session_factory()

    async def execute(self, query: str, *args) -> Any:
        """Execute a raw SQL query using asyncpg"""
        if not self.asyncpg_pool:
            raise RuntimeError("Database pool not initialized")
        async with self.asyncpg_pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def execute_many(self, query: str, values: list):
        """Execute multiple queries"""
        if not self.asyncpg_pool:
            raise RuntimeError("Database pool not initialized")
        async with self.asyncpg_pool.acquire() as conn:
            return await conn.executemany(query, values)

    @asynccontextmanager
    async def transaction(self):
        """Create a database transaction context"""
        async with self.session_factory() as session:
            async with session.begin():
                yield session

    async def health_check(self) -> dict:
        """Check health of all connections"""
        status = {
            "postgresql": "unknown",
            "redis": "unknown",
            "asyncpg": "unknown"
        }

        try:
            async with self.session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                status["postgresql"] = "healthy" if result.scalar() == 1 else "unhealthy"
        except Exception as e:
            status["postgresql"] = f"error: {str(e)}"

        try:
            async with self.asyncpg_pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                status["asyncpg"] = "healthy" if result == 1 else "unhealthy"
        except Exception as e:
            status["asyncpg"] = f"error: {str(e)}"

        try:
            status["redis"] = "healthy" if await self.redis_client.ping() else "unhealthy"
        except Exception as e:
            status["redis"] = f"error: {str(e)}"

        return status