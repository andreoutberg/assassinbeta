"""
Optimized Redis Storage Manager for Liquidation Detector
Designed for VPS with 256MB Redis memory constraint
"""

import asyncio
import struct
import time
import statistics
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import redis.asyncio as redis
import msgpack
import zlib

logger = logging.getLogger(__name__)


class StorageMode(Enum):
    """Storage optimization modes based on memory pressure"""
    NORMAL = "normal"       # < 75% memory usage
    OPTIMIZED = "optimized"  # 75-85% memory usage
    CRITICAL = "critical"    # > 85% memory usage


@dataclass
class LiquidationEvent:
    """Liquidation event data structure"""
    symbol: str
    side: str  # 'buy' or 'sell'
    size: float
    price: float
    timestamp: float
    exchange: str


class OptimizedRedisManager:
    """
    Memory-efficient Redis manager for liquidation data
    Optimized for 256MB VPS constraint
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis: Optional[redis.Redis] = None
        self.pipeline: Optional[redis.client.Pipeline] = None

        # Memory thresholds
        self.max_memory_mb = 240  # Leave 16MB buffer from 256MB
        self.warning_threshold = 0.75
        self.critical_threshold = 0.85

        # Storage mode
        self.storage_mode = StorageMode.NORMAL

        # Configuration
        self.stream_max_len = 10000
        self.batch_size = 50
        self.batch_timeout = 0.1  # 100ms

        # Percentile tracking
        self.percentile_bucket_size = 100
        self.percentile_retention_hours = 24

    async def connect(self):
        """Initialize Redis connection with optimized settings"""
        pool = redis.ConnectionPool.from_url(
            self.redis_url,
            max_connections=50,
            socket_keepalive=True,
            socket_keepalive_options={
                1: 1,  # TCP_KEEPIDLE
                2: 2,  # TCP_KEEPINTVL
                3: 2,  # TCP_KEEPCNT
            },
            decode_responses=False  # Use binary for efficiency
        )
        self.redis = redis.Redis(connection_pool=pool)
        await self.configure_redis()
        logger.info("Redis connection established with optimized settings")

    async def configure_redis(self):
        """Apply VPS-optimized Redis configuration"""
        try:
            config_commands = [
                ('maxmemory', '240mb'),
                ('maxmemory-policy', 'volatile-ttl'),
                ('maxmemory-samples', '10'),
                ('lazyfree-lazy-eviction', 'yes'),
                ('lazyfree-lazy-expire', 'yes'),
                ('hz', '100'),
                ('hash-max-ziplist-entries', '512'),
                ('zset-max-ziplist-entries', '128'),
            ]

            for key, value in config_commands:
                await self.redis.config_set(key, value)

            logger.info("Redis configuration optimized for VPS")
        except Exception as e:
            logger.warning(f"Could not apply all Redis configs: {e}")

    async def add_liquidation(self, event: LiquidationEvent) -> bool:
        """
        Add liquidation event with memory-aware storage
        Returns True if stored, False if rejected due to memory pressure
        """
        # Check memory pressure
        memory_ok = await self.check_memory_pressure()
        if not memory_ok and not self._is_critical_event(event):
            logger.warning(f"Rejecting event due to memory pressure: {event.symbol}")
            return False

        # Encode based on storage mode
        if self.storage_mode == StorageMode.CRITICAL:
            data = self._encode_minimal(event)
        elif self.storage_mode == StorageMode.OPTIMIZED:
            data = self._encode_binary(event)
        else:
            data = self._encode_normal(event)

        # Add to stream with auto-trimming
        stream_key = f"liq:{event.symbol}"
        await self.redis.xadd(
            stream_key,
            data,
            maxlen=self.stream_max_len,
            approximate=True  # Allow ~10% over limit for performance
        )

        # Update VWAP data
        await self._update_vwap(event)

        # Track for percentile calculation if significant
        if self._is_significant_size(event):
            await self._track_percentile(event)

        return True

    async def add_liquidations_batch(self, events: List[LiquidationEvent]) -> int:
        """
        Batch add liquidations with pipelining for high performance
        Returns number of events successfully stored
        """
        if not events:
            return 0

        # Check memory once for the batch
        memory_ok = await self.check_memory_pressure()
        if not memory_ok:
            # Filter to only critical events
            events = [e for e in events if self._is_critical_event(e)]
            if not events:
                return 0

        pipe = self.redis.pipeline(transaction=False)
        stored_count = 0

        for event in events:
            # Encode event
            if self.storage_mode == StorageMode.CRITICAL:
                data = self._encode_minimal(event)
            else:
                data = self._encode_binary(event)

            # Add to stream
            stream_key = f"liq:{event.symbol}"
            pipe.xadd(
                stream_key,
                data,
                maxlen=self.stream_max_len,
                approximate=True
            )

            # Update VWAP
            vwap_key = f"vwap:{event.symbol}"
            pipe.hincrby(vwap_key, b'count', 1)
            pipe.hincrbyfloat(vwap_key, b'volume', event.size)
            pipe.hincrbyfloat(vwap_key, b'price_volume', event.price * event.size)
            pipe.expire(vwap_key, 3600)  # 1 hour TTL

            # Track percentiles for significant sizes
            if self._is_significant_size(event):
                size_key = f"sizes:{event.symbol}:{int(event.timestamp // 3600)}"
                pipe.zadd(size_key, {f"{event.timestamp}".encode(): event.size})
                pipe.expire(size_key, 7200)  # 2 hour TTL

            stored_count += 1

        # Execute pipeline
        try:
            await pipe.execute()
            logger.debug(f"Batch stored {stored_count} liquidation events")
            return stored_count
        except Exception as e:
            logger.error(f"Batch storage failed: {e}")
            return 0

    async def get_vwap(self, symbol: str) -> Optional[Dict[str, float]]:
        """Calculate current VWAP for symbol"""
        vwap_key = f"vwap:{symbol}"
        data = await self.redis.hgetall(vwap_key)

        if not data:
            return None

        try:
            count = int(data.get(b'count', 0))
            volume = float(data.get(b'volume', 0))
            price_volume = float(data.get(b'price_volume', 0))

            if volume > 0:
                vwap = price_volume / volume
                return {
                    'vwap': vwap,
                    'volume': volume,
                    'count': count
                }
        except (ValueError, ZeroDivisionError):
            pass

        return None

    async def calculate_percentile(
        self,
        symbol: str,
        percentile: float,
        hours: int = 24
    ) -> Optional[float]:
        """
        Calculate size percentile for filtering
        Uses bucketed sorted sets for memory efficiency
        """
        if not 0 <= percentile <= 100:
            raise ValueError("Percentile must be between 0 and 100")

        current_time = int(time.time())
        bucket_keys = []

        # Gather relevant buckets
        for h in range(min(hours, self.percentile_retention_hours)):
            bucket_time = current_time - (h * 3600)
            bucket_key = f"sizes:{symbol}:{bucket_time // 3600}"
            if await self.redis.exists(bucket_key):
                bucket_keys.append(bucket_key)

        if not bucket_keys:
            return None

        # Create temporary union
        temp_key = f"temp:percentile:{symbol}:{current_time}"

        try:
            if len(bucket_keys) == 1:
                # Single bucket, use directly
                total = await self.redis.zcard(bucket_keys[0])
                if total > 0:
                    rank = int(total * percentile / 100)
                    result = await self.redis.zrange(
                        bucket_keys[0],
                        rank, rank,
                        withscores=True
                    )
                    if result:
                        return result[0][1]
            else:
                # Multiple buckets, union them
                await self.redis.zunionstore(temp_key, bucket_keys)
                await self.redis.expire(temp_key, 60)

                total = await self.redis.zcard(temp_key)
                if total > 0:
                    rank = int(total * percentile / 100)
                    result = await self.redis.zrange(
                        temp_key,
                        rank, rank,
                        withscores=True
                    )
                    if result:
                        return result[0][1]
        finally:
            # Clean up temp key
            await self.redis.delete(temp_key)

        return None

    async def get_recent_liquidations(
        self,
        symbol: str,
        count: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent liquidation events from stream"""
        stream_key = f"liq:{symbol}"

        # Get latest entries
        entries = await self.redis.xrevrange(stream_key, count=count)

        liquidations = []
        for entry_id, data in entries:
            try:
                # Decode based on format
                if b'minimal' in data:
                    decoded = self._decode_minimal(data)
                elif b'binary' in data:
                    decoded = self._decode_binary(data)
                else:
                    decoded = self._decode_normal(data)

                if decoded:
                    decoded['id'] = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                    liquidations.append(decoded)
            except Exception as e:
                logger.error(f"Failed to decode entry: {e}")
                continue

        return liquidations

    async def get_liquidation_stats(
        self,
        symbol: str,
        window_minutes: int = 60
    ) -> Dict[str, Any]:
        """Get aggregated statistics for liquidations"""
        stats = {
            'symbol': symbol,
            'window_minutes': window_minutes,
            'total_count': 0,
            'buy_count': 0,
            'sell_count': 0,
            'total_volume': 0.0,
            'buy_volume': 0.0,
            'sell_volume': 0.0,
            'avg_size': 0.0,
            'max_size': 0.0,
            'percentile_80': None,
            'percentile_90': None
        }

        # Get recent liquidations
        liquidations = await self.get_recent_liquidations(symbol, count=1000)

        if not liquidations:
            return stats

        # Filter by time window
        cutoff_time = time.time() - (window_minutes * 60)
        recent = [
            liq for liq in liquidations
            if liq.get('timestamp', 0) > cutoff_time
        ]

        if not recent:
            return stats

        # Calculate statistics
        sizes = []
        for liq in recent:
            side = liq.get('side', '')
            size = liq.get('size', 0)

            stats['total_count'] += 1
            stats['total_volume'] += size
            sizes.append(size)

            if side == 'buy':
                stats['buy_count'] += 1
                stats['buy_volume'] += size
            else:
                stats['sell_count'] += 1
                stats['sell_volume'] += size

        if sizes:
            stats['avg_size'] = statistics.mean(sizes)
            stats['max_size'] = max(sizes)

            # Calculate percentiles
            stats['percentile_80'] = await self.calculate_percentile(symbol, 80, 1)
            stats['percentile_90'] = await self.calculate_percentile(symbol, 90, 1)

        return stats

    async def check_memory_pressure(self) -> bool:
        """
        Check Redis memory usage and adjust storage mode
        Returns True if memory is OK, False if critical
        """
        try:
            info = await self.redis.info('memory')
            used_memory = int(info['used_memory']) / (1024 * 1024)  # Convert to MB
            usage_ratio = used_memory / self.max_memory_mb

            # Update storage mode based on usage
            if usage_ratio > self.critical_threshold:
                self.storage_mode = StorageMode.CRITICAL
                await self._emergency_cleanup()
                logger.warning(f"Critical memory usage: {used_memory:.1f}MB ({usage_ratio:.1%})")
                return False
            elif usage_ratio > self.warning_threshold:
                self.storage_mode = StorageMode.OPTIMIZED
                logger.info(f"Optimized mode activated: {used_memory:.1f}MB ({usage_ratio:.1%})")
            else:
                self.storage_mode = StorageMode.NORMAL

            return True

        except Exception as e:
            logger.error(f"Memory check failed: {e}")
            return True  # Assume OK if check fails

    async def cleanup_old_data(self, aggressive: bool = False):
        """
        Clean up old data based on retention policy
        Aggressive mode for emergency memory recovery
        """
        try:
            if aggressive:
                # Emergency cleanup - delete non-critical data
                patterns = [
                    'temp:*',
                    'debug:*',
                    'stats:old:*'
                ]

                for pattern in patterns:
                    cursor = 0
                    while True:
                        cursor, keys = await self.redis.scan(
                            cursor,
                            match=pattern,
                            count=100
                        )
                        if keys:
                            await self.redis.delete(*keys)
                        if cursor == 0:
                            break

                # Trim streams aggressively
                symbols = await self._get_active_symbols()
                for symbol in symbols:
                    stream_key = f"liq:{symbol}"
                    await self.redis.xtrim(stream_key, maxlen=1000, approximate=False)

                logger.info("Aggressive cleanup completed")

            else:
                # Normal cleanup - respect TTLs and trim streams
                symbols = await self._get_active_symbols()
                for symbol in symbols:
                    stream_key = f"liq:{symbol}"
                    await self.redis.xtrim(
                        stream_key,
                        maxlen=self.stream_max_len,
                        approximate=True
                    )

                # Clean old percentile buckets
                current_hour = int(time.time() // 3600)
                cutoff_hour = current_hour - self.percentile_retention_hours

                cursor = 0
                while True:
                    cursor, keys = await self.redis.scan(
                        cursor,
                        match='sizes:*',
                        count=100
                    )

                    for key in keys:
                        # Parse hour from key
                        parts = key.decode().split(':')
                        if len(parts) >= 3:
                            try:
                                hour = int(parts[-1])
                                if hour < cutoff_hour:
                                    await self.redis.delete(key)
                            except ValueError:
                                continue

                    if cursor == 0:
                        break

                logger.info("Normal cleanup completed")

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    async def get_memory_stats(self) -> Dict[str, Any]:
        """Get detailed memory usage statistics"""
        try:
            info = await self.redis.info('memory')

            used_mb = int(info['used_memory']) / (1024 * 1024)
            peak_mb = int(info['used_memory_peak']) / (1024 * 1024)
            rss_mb = int(info['used_memory_rss']) / (1024 * 1024)

            return {
                'used_mb': round(used_mb, 2),
                'used_pct': round(used_mb / self.max_memory_mb * 100, 2),
                'peak_mb': round(peak_mb, 2),
                'rss_mb': round(rss_mb, 2),
                'fragmentation_ratio': float(info.get('mem_fragmentation_ratio', 1.0)),
                'evicted_keys': int(info.get('evicted_keys', 0)),
                'storage_mode': self.storage_mode.value
            }
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {}

    # Private helper methods

    def _encode_normal(self, event: LiquidationEvent) -> Dict[bytes, bytes]:
        """Standard encoding for normal mode"""
        return {
            b's': event.side.encode(),
            b'sz': str(event.size).encode(),
            b'p': str(event.price).encode(),
            b'e': event.exchange[:8].encode(),
            b't': str(int(event.timestamp)).encode()
        }

    def _encode_binary(self, event: LiquidationEvent) -> Dict[bytes, bytes]:
        """Binary encoding for optimized mode"""
        # Pack into binary: side(1) + size(4) + price(4) + exchange_hash(2)
        binary = struct.pack(
            '!Bff',
            1 if event.side == 'buy' else 0,
            event.size,
            event.price
        )
        return {
            b'b': binary,
            b'e': event.exchange[:3].encode(),
            b't': str(int(event.timestamp)).encode()
        }

    def _encode_minimal(self, event: LiquidationEvent) -> Dict[bytes, bytes]:
        """Minimal encoding for critical mode - only essential data"""
        return {
            b'minimal': b'1',
            b's': b'b' if event.side == 'buy' else b's',
            b'z': str(int(event.size)).encode(),  # Round to integer
            b'p': str(int(event.price)).encode()   # Round to integer
        }

    def _decode_normal(self, data: Dict[bytes, bytes]) -> Dict[str, Any]:
        """Decode normal format"""
        return {
            'side': data.get(b's', b'').decode(),
            'size': float(data.get(b'sz', b'0')),
            'price': float(data.get(b'p', b'0')),
            'exchange': data.get(b'e', b'').decode(),
            'timestamp': float(data.get(b't', b'0'))
        }

    def _decode_binary(self, data: Dict[bytes, bytes]) -> Dict[str, Any]:
        """Decode binary format"""
        if b'b' in data:
            side_byte, size, price = struct.unpack('!Bff', data[b'b'])
            return {
                'side': 'buy' if side_byte == 1 else 'sell',
                'size': size,
                'price': price,
                'exchange': data.get(b'e', b'').decode(),
                'timestamp': float(data.get(b't', b'0'))
            }
        return {}

    def _decode_minimal(self, data: Dict[bytes, bytes]) -> Dict[str, Any]:
        """Decode minimal format"""
        return {
            'side': 'buy' if data.get(b's') == b'b' else 'sell',
            'size': float(data.get(b'z', b'0')),
            'price': float(data.get(b'p', b'0')),
            'exchange': 'unknown',
            'timestamp': time.time()  # Use current time if not stored
        }

    def _is_critical_event(self, event: LiquidationEvent) -> bool:
        """Determine if event is critical and must be stored"""
        # Large liquidations are always critical
        thresholds = {
            'BTC': 50000,
            'ETH': 20000,
            'default': 10000
        }

        symbol_base = event.symbol[:3]
        threshold = thresholds.get(symbol_base, thresholds['default'])

        return event.size >= threshold

    def _is_significant_size(self, event: LiquidationEvent) -> bool:
        """Check if size is significant for percentile tracking"""
        # Track top 20% of typical sizes
        min_sizes = {
            'BTC': 10000,
            'ETH': 5000,
            'default': 1000
        }

        symbol_base = event.symbol[:3]
        min_size = min_sizes.get(symbol_base, min_sizes['default'])

        return event.size >= min_size

    async def _update_vwap(self, event: LiquidationEvent):
        """Update VWAP calculation data"""
        vwap_key = f"vwap:{event.symbol}"

        pipe = self.redis.pipeline()
        pipe.hincrby(vwap_key, b'count', 1)
        pipe.hincrbyfloat(vwap_key, b'volume', event.size)
        pipe.hincrbyfloat(vwap_key, b'price_volume', event.price * event.size)
        pipe.expire(vwap_key, 3600)  # 1 hour TTL

        await pipe.execute()

    async def _track_percentile(self, event: LiquidationEvent):
        """Track size for percentile calculation"""
        bucket_key = f"sizes:{event.symbol}:{int(event.timestamp // 3600)}"

        # Add to sorted set
        await self.redis.zadd(
            bucket_key,
            {f"{event.timestamp}:{event.size}".encode(): event.size}
        )

        # Trim bucket to max size
        card = await self.redis.zcard(bucket_key)
        if card > self.percentile_bucket_size:
            await self.redis.zremrangebyrank(
                bucket_key,
                0,
                -self.percentile_bucket_size - 1
            )

        # Set TTL
        await self.redis.expire(bucket_key, 7200)  # 2 hours

    async def _get_active_symbols(self) -> List[str]:
        """Get list of active trading symbols"""
        symbols = set()

        # Scan for liquidation streams
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor,
                match='liq:*',
                count=100
            )

            for key in keys:
                # Extract symbol from key
                symbol = key.decode().split(':')[-1]
                symbols.add(symbol)

            if cursor == 0:
                break

        return list(symbols)

    async def _emergency_cleanup(self):
        """Emergency memory recovery procedure"""
        logger.warning("Initiating emergency memory cleanup")

        # 1. Delete all temporary keys
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor,
                match='temp:*',
                count=100
            )
            if keys:
                await self.redis.delete(*keys)
            if cursor == 0:
                break

        # 2. Aggressively trim streams
        symbols = await self._get_active_symbols()
        for symbol in symbols:
            await self.redis.xtrim(f"liq:{symbol}", maxlen=500, approximate=False)

        # 3. Clear old percentile data
        current_hour = int(time.time() // 3600)
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor,
                match='sizes:*',
                count=100
            )

            for key in keys:
                parts = key.decode().split(':')
                if len(parts) >= 3:
                    try:
                        hour = int(parts[-1])
                        if hour < current_hour - 2:  # Keep only last 2 hours
                            await self.redis.delete(key)
                    except ValueError:
                        continue

            if cursor == 0:
                break

        # 4. Force memory defragmentation if supported
        try:
            await self.redis.memory_purge()
        except:
            pass  # Not all Redis versions support this

        logger.info("Emergency cleanup completed")

    async def close(self):
        """Clean up resources"""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")


# Usage Example
async def example_usage():
    """Example of using the optimized Redis manager"""

    # Initialize manager
    manager = OptimizedRedisManager("redis://localhost:6379/0")
    await manager.connect()

    # Add single liquidation
    event = LiquidationEvent(
        symbol="BTCUSDT",
        side="sell",
        size=75000,
        price=42150.5,
        timestamp=time.time(),
        exchange="binance"
    )
    await manager.add_liquidation(event)

    # Batch add liquidations
    events = [
        LiquidationEvent(
            symbol="ETHUSDT",
            side="buy",
            size=25000,
            price=2250.5,
            timestamp=time.time(),
            exchange="binance"
        )
        for _ in range(10)
    ]
    await manager.add_liquidations_batch(events)

    # Get VWAP
    vwap_data = await manager.get_vwap("BTCUSDT")
    print(f"VWAP: {vwap_data}")

    # Calculate percentiles
    p80 = await manager.calculate_percentile("BTCUSDT", 80)
    p90 = await manager.calculate_percentile("BTCUSDT", 90)
    print(f"80th percentile: {p80}, 90th percentile: {p90}")

    # Get statistics
    stats = await manager.get_liquidation_stats("BTCUSDT", window_minutes=60)
    print(f"Stats: {stats}")

    # Check memory
    memory_stats = await manager.get_memory_stats()
    print(f"Memory: {memory_stats}")

    # Cleanup
    await manager.cleanup_old_data()

    # Close connection
    await manager.close()


if __name__ == "__main__":
    asyncio.run(example_usage())