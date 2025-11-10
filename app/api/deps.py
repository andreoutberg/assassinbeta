"""
FastAPI dependencies for the High-WR Trading System
"""
from typing import AsyncGenerator, Optional, Dict, Any
from fastapi import Depends, HTTPException, status, Header, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from datetime import datetime, timedelta
import json
from app.database.connection import get_db, get_redis, get_asyncpg_pool
from asyncpg.pool import Pool


# Security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Get current user from JWT token (simplified for demo)
    In production, implement proper JWT validation
    """
    if not credentials:
        # For demo purposes, return a default user
        return {"user_id": "demo_user", "role": "trader"}

    # In production: Validate JWT token here
    return {"user_id": "authenticated_user", "role": "trader"}


async def require_auth(user: Dict = Depends(get_current_user)) -> Dict:
    """Require authentication"""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(user: Dict = Depends(get_current_user)) -> Dict:
    """Require admin role"""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


class RateLimiter:
    """Rate limiting dependency"""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute

    async def __call__(
        self,
        redis_client: redis.Redis = Depends(get_redis),
        user: Dict = Depends(get_current_user),
        x_forwarded_for: Optional[str] = Header(None),
        x_real_ip: Optional[str] = Header(None),
    ) -> bool:
        """Check rate limit"""
        # Get client identifier
        client_id = user.get("user_id", "anonymous")
        if not client_id or client_id == "anonymous":
            client_id = x_forwarded_for or x_real_ip or "unknown"

        # Rate limit key
        key = f"rate_limit:{client_id}"

        # Check current count
        try:
            current = await redis_client.incr(key)
            if current == 1:
                # Set expiry for new key
                await redis_client.expire(key, 60)

            if current > self.requests_per_minute:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Max {self.requests_per_minute} requests per minute.",
                )

            return True
        except redis.RedisError:
            # If Redis is down, allow the request
            return True


# Create rate limiters with different limits
rate_limit_standard = RateLimiter(requests_per_minute=60)
rate_limit_high = RateLimiter(requests_per_minute=300)
rate_limit_low = RateLimiter(requests_per_minute=20)


class CacheManager:
    """Cache management dependency"""

    def __init__(self, default_ttl: int = 300):
        self.default_ttl = default_ttl

    async def get(
        self,
        key: str,
        redis_client: redis.Redis = None,
    ) -> Optional[Any]:
        """Get cached value"""
        if not redis_client:
            redis_client = await get_redis()

        try:
            value = await redis_client.get(key)
            if value:
                return json.loads(value)
        except (redis.RedisError, json.JSONDecodeError):
            pass
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        redis_client: redis.Redis = None,
    ) -> bool:
        """Set cached value"""
        if not redis_client:
            redis_client = await get_redis()

        ttl = ttl or self.default_ttl

        try:
            await redis_client.setex(
                key,
                ttl,
                json.dumps(value, default=str),
            )
            return True
        except (redis.RedisError, json.JSONEncodeError):
            return False

    async def delete(
        self,
        key: str,
        redis_client: redis.Redis = None,
    ) -> bool:
        """Delete cached value"""
        if not redis_client:
            redis_client = await get_redis()

        try:
            await redis_client.delete(key)
            return True
        except redis.RedisError:
            return False

    async def invalidate_pattern(
        self,
        pattern: str,
        redis_client: redis.Redis = None,
    ) -> int:
        """Invalidate all keys matching pattern"""
        if not redis_client:
            redis_client = await get_redis()

        try:
            keys = await redis_client.keys(pattern)
            if keys:
                return await redis_client.delete(*keys)
        except redis.RedisError:
            pass
        return 0


# Create cache managers with different TTLs
cache_short = CacheManager(default_ttl=30)  # 30 seconds
cache_medium = CacheManager(default_ttl=300)  # 5 minutes
cache_long = CacheManager(default_ttl=1800)  # 30 minutes


class PaginationParams:
    """Pagination parameters"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=1000, description="Items per page"),
        sort_by: Optional[str] = Query(None, description="Sort field"),
        sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    ):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size
        self.sort_by = sort_by
        self.sort_order = sort_order


class DateRangeParams:
    """Date range parameters"""

    def __init__(
        self,
        start_date: Optional[datetime] = Query(None, description="Start date"),
        end_date: Optional[datetime] = Query(None, description="End date"),
        last_hours: Optional[int] = Query(None, ge=1, le=720, description="Last N hours"),
        last_days: Optional[int] = Query(None, ge=1, le=365, description="Last N days"),
    ):
        # Handle different date range options
        if last_hours:
            self.start_date = datetime.utcnow() - timedelta(hours=last_hours)
            self.end_date = datetime.utcnow()
        elif last_days:
            self.start_date = datetime.utcnow() - timedelta(days=last_days)
            self.end_date = datetime.utcnow()
        else:
            self.start_date = start_date or datetime.utcnow() - timedelta(days=7)
            self.end_date = end_date or datetime.utcnow()


async def get_asyncpg_connection(pool: Pool = Depends(get_asyncpg_pool)):
    """Get asyncpg connection from pool"""
    async with pool.acquire() as connection:
        yield connection


# WebSocket connection manager dependency
class WebSocketManager:
    """WebSocket connection manager"""

    def __init__(self):
        self.active_connections: Dict[str, list] = {}

    async def connect(self, websocket, client_id: str):
        """Connect client"""
        await websocket.accept()
        if client_id not in self.active_connections:
            self.active_connections[client_id] = []
        self.active_connections[client_id].append(websocket)

    def disconnect(self, websocket, client_id: str):
        """Disconnect client"""
        if client_id in self.active_connections:
            self.active_connections[client_id].remove(websocket)
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]

    async def send_personal_message(self, message: str, client_id: str):
        """Send message to specific client"""
        if client_id in self.active_connections:
            for connection in self.active_connections[client_id]:
                await connection.send_text(message)

    async def broadcast(self, message: str):
        """Broadcast to all connections"""
        for connections in self.active_connections.values():
            for connection in connections:
                await connection.send_text(message)


# Global WebSocket manager instance
ws_manager = WebSocketManager()