"""
Database Session Management with Connection Pooling

Provides async database sessions with proper connection pooling for multi-strategy scale.

Connection Pool Configuration:
- Pool Size: 30 concurrent connections (base)
- Max Overflow: 20 additional connections (total 50 max)
- Pool Recycle: 3600 seconds (1 hour)
- Pre-Ping: Enabled (detect stale connections)

Performance:
- Handles 50-100 concurrent trades
- Automatic connection recycling
- Stale connection detection
- Connection timeout protection
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Create async engine with connection pooling
engine = create_async_engine(
    settings.DATABASE_URL_ASYNC,
    echo=settings.DATABASE_ECHO,  # Set to True for SQL query logging (debug)

    # Connection pooling settings (critical for multi-strategy scale)
    pool_size=settings.DATABASE_POOL_SIZE,  # 30 connections (base)
    max_overflow=settings.DATABASE_MAX_OVERFLOW,  # +20 overflow (50 total)
    pool_recycle=settings.DATABASE_POOL_RECYCLE,  # Recycle every hour
    pool_pre_ping=settings.DATABASE_POOL_PRE_PING,  # Test before use
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,  # 30 seconds max wait

    # Connection settings
    connect_args={
        "server_settings": {
            "application_name": "andre_assassin"
        }
    }
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
    autocommit=False,
    autoflush=False
)

# Base class for models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """
    Get database session (dependency injection for FastAPI)

    Usage in FastAPI routes:
        @router.get("/trades")
        async def get_trades(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(TradeSetup))
            return result.scalars().all()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def init_db():
    """
    Initialize database (create all tables)

    NOTE: In production, use Alembic migrations instead of this function.
    This is useful for testing/development only.
    """
    from app.database.models import Base as ModelsBase

    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(ModelsBase.metadata.create_all)

    logger.info("✅ Database initialized")


async def close_db():
    """
    Close database connections (cleanup on shutdown)

    Call this during FastAPI shutdown:
        @app.on_event("shutdown")
        async def shutdown():
            await close_db()
    """
    await engine.dispose()
    logger.info("✅ Database connections closed")


async def check_db_health() -> bool:
    """
    Check database connectivity (health check endpoint)

    Returns:
        True if database is reachable, False otherwise
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


# Connection pool statistics (for monitoring)
def get_pool_stats() -> dict:
    """
    Get connection pool statistics

    Returns:
        {
            "pool_size": 30,
            "checked_out": 15,  # Currently in use
            "checked_in": 15,   # Available
            "overflow": 5,      # Overflow connections in use
            "total": 35         # Total connections (base + overflow)
        }
    """
    pool = engine.pool

    return {
        "pool_size": pool.size(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "total": pool.size() + pool.overflow(),
        "max_overflow": settings.DATABASE_MAX_OVERFLOW,
        "status": "healthy" if pool.checkedout() < pool.size() else "near_capacity"
    }
