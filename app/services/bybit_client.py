"""
CCXT Bybit Client for Demo Trading

Provides real-time market data and demo trading capabilities using Bybit.
Integrates with the high-WR trading system for signal validation.
"""

import ccxt.async_support as ccxt
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from asyncio import Semaphore
import time
from collections import deque
import aiohttp

logger = logging.getLogger(__name__)


class BybitClient:
    """
    Async CCXT client for Bybit exchange with enhanced features.

    Supports:
    - Real-time price fetching with connection pooling
    - Rate limiting (10 req/sec)
    - Exponential backoff error handling
    - Exchange health monitoring
    - Demo trading (paper trading)
    - OHLCV data retrieval
    - Market analysis for signal generation
    """

    # Rate limiting configuration
    MAX_REQUESTS_PER_SECOND = 10
    MAX_RETRIES = 3
    BASE_RETRY_DELAY = 1.0  # seconds

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, testnet: bool = True,
                 demo_trading: bool = False, max_connections: int = 10):
        """
        Initialize Bybit client with enhanced features.

        Args:
            api_key: Bybit API key (optional for public data)
            api_secret: Bybit API secret (optional for public data)
            testnet: Use testnet environment (default: True)
            demo_trading: Use demo trading on live endpoint (default: False)
            max_connections: Maximum concurrent connections (default: 10)
        """
        # Initialize exchange with connection limits
        self.exchange = ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'rateLimit': 100,  # milliseconds between requests
            'options': {
                'defaultType': 'linear',  # USDT perpetual
                'testnet': testnet if not demo_trading else False,  # Demo uses live endpoint
                'adjustForTimeDifference': True,  # Auto-adjust for time sync issues
            },
            # Connection pool settings
            'aiohttp': {
                'connector': aiohttp.TCPConnector(
                    limit=max_connections,
                    limit_per_host=max_connections,
                    ttl_dns_cache=300
                )
            }
        })

        # Enable demo trading if requested (must be after initialization)
        if demo_trading:
            self.exchange.enable_demo_trading(True)
            logger.info("🎮 Demo trading enabled (using live API with virtual funds)")

        self.is_connected = False
        self.testnet = testnet
        self.demo_trading = demo_trading

        # Rate limiting
        self.rate_limiter = Semaphore(self.MAX_REQUESTS_PER_SECOND)
        self.request_times = deque(maxlen=100)  # Track last 100 request times

        # Health monitoring
        self.health_check_interval = 60  # seconds
        self.last_health_check = None
        self.health_status = {
            'is_healthy': False,
            'last_check': None,
            'latency_ms': None,
            'error_count': 0,
            'success_count': 0,
            'uptime_percent': 100.0
        }

        # Error tracking
        self.error_counts = {}  # Track errors by type
        self.total_requests = 0
        self.failed_requests = 0

    async def connect(self) -> bool:
        """
        Test connection to Bybit and load markets.

        Returns:
            True if connection successful
        """
        try:
            await self._execute_with_retry(self.exchange.load_markets)
            self.is_connected = True
            await self._update_health_status(True)
            logger.info(f"✅ Connected to Bybit ({'testnet' if self.testnet else 'mainnet'})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to Bybit: {e}")
            self.is_connected = False
            await self._update_health_status(False, error=str(e))
            return False

    async def close(self):
        """Close exchange connection."""
        await self.exchange.close()
        self.is_connected = False

    async def _execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with exponential backoff retry logic.

        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Exception after max retries exceeded
        """
        last_exception = None

        for attempt in range(self.MAX_RETRIES):
            try:
                # Rate limiting
                async with self.rate_limiter:
                    # Track request time
                    self.request_times.append(time.time())
                    self.total_requests += 1

                    # Execute function
                    result = await func(*args, **kwargs)

                    # Update success count
                    self.health_status['success_count'] += 1

                    return result

            except (ccxt.NetworkError, ccxt.RequestTimeout) as e:
                last_exception = e
                retry_delay = self.BASE_RETRY_DELAY * (2 ** attempt)  # Exponential backoff

                logger.warning(
                    f"Network error (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}. "
                    f"Retrying in {retry_delay}s..."
                )

                # Track error
                error_type = type(e).__name__
                self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
                self.failed_requests += 1

                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

            except ccxt.ExchangeError as e:
                # Don't retry exchange errors (bad request, insufficient balance, etc.)
                self.failed_requests += 1
                self.health_status['error_count'] += 1
                logger.error(f"Exchange error: {e}")
                raise

            except Exception as e:
                # Unexpected error
                self.failed_requests += 1
                self.health_status['error_count'] += 1
                logger.error(f"Unexpected error: {e}")
                raise

        # All retries failed
        raise last_exception

    async def _update_health_status(self, is_healthy: bool, error: Optional[str] = None):
        """
        Update exchange health status.

        Args:
            is_healthy: Whether exchange is healthy
            error: Error message if unhealthy
        """
        self.health_status['is_healthy'] = is_healthy
        self.health_status['last_check'] = datetime.now().isoformat()

        if error:
            self.health_status['error_count'] += 1

        # Calculate uptime percentage
        if self.total_requests > 0:
            success_rate = (self.total_requests - self.failed_requests) / self.total_requests
            self.health_status['uptime_percent'] = round(success_rate * 100, 2)

    async def check_health(self) -> Dict[str, Any]:
        """
        Perform health check on exchange connection.

        Returns:
            Health status dict
        """
        try:
            # Skip if recently checked
            if self.last_health_check:
                elapsed = (datetime.now() - self.last_health_check).seconds
                if elapsed < self.health_check_interval:
                    return self.health_status

            # Measure latency
            start_time = time.time()
            ticker = await self._execute_with_retry(self.exchange.fetch_ticker, 'BTC/USDT')
            latency_ms = (time.time() - start_time) * 1000

            # Update status
            self.health_status['is_healthy'] = True
            self.health_status['latency_ms'] = round(latency_ms, 2)
            self.last_health_check = datetime.now()

            logger.info(f"📊 Health check passed. Latency: {latency_ms:.0f}ms")

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.health_status['is_healthy'] = False
            self.health_status['last_error'] = str(e)

        return self.health_status

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limiting status.

        Returns:
            Rate limit status dict
        """
        now = time.time()

        # Remove old request times (older than 1 second)
        recent_requests = [t for t in self.request_times if now - t < 1.0]

        return {
            'requests_per_second': len(recent_requests),
            'max_requests_per_second': self.MAX_REQUESTS_PER_SECOND,
            'available_slots': self.MAX_REQUESTS_PER_SECOND - len(recent_requests),
            'total_requests': self.total_requests,
            'failed_requests': self.failed_requests,
            'success_rate': round((1 - self.failed_requests / self.total_requests) * 100, 2) if self.total_requests > 0 else 100
        }

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker data for symbol.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')

        Returns:
            Ticker data with bid, ask, last price, volume, etc.
        """
        try:
            ticker = await self._execute_with_retry(self.exchange.fetch_ticker, symbol)
            return {
                'symbol': symbol,
                'bid': float(ticker['bid']) if ticker['bid'] else None,
                'ask': float(ticker['ask']) if ticker['ask'] else None,
                'last': float(ticker['last']) if ticker['last'] else None,
                'volume': float(ticker['baseVolume']) if ticker['baseVolume'] else None,
                'timestamp': ticker['timestamp'],
                'datetime': ticker['datetime'],
            }
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return None

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1h',
        limit: int = 100,
        since: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV (candlestick) data.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe ('1m', '5m', '15m', '1h', '4h', '1d')
            limit: Number of candles to fetch (max 200)
            since: Timestamp in milliseconds to fetch from

        Returns:
            List of OHLCV candles
        """
        try:
            ohlcv = await self._execute_with_retry(self.exchange.fetch_ohlcv, symbol, timeframe, since, limit)
            return [
                {
                    'timestamp': candle[0],
                    'datetime': datetime.fromtimestamp(candle[0] / 1000).isoformat(),
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'volume': float(candle[5]),
                }
                for candle in ohlcv
            ]
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol}: {e}")
            return []

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """
        Fetch order book (market depth).

        Args:
            symbol: Trading pair
            limit: Depth limit

        Returns:
            Order book with bids and asks
        """
        try:
            orderbook = await self._execute_with_retry(self.exchange.fetch_order_book, symbol, limit)
            return {
                'symbol': symbol,
                'bids': [[float(price), float(amount)] for price, amount in orderbook['bids'][:limit]],
                'asks': [[float(price), float(amount)] for price, amount in orderbook['asks'][:limit]],
                'timestamp': orderbook['timestamp'],
                'datetime': orderbook['datetime'],
            }
        except Exception as e:
            logger.error(f"Error fetching order book for {symbol}: {e}")
            return None

    async def get_market_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get detailed market information for symbol.

        Args:
            symbol: Trading pair

        Returns:
            Market info including limits, precision, fees
        """
        try:
            if not self.is_connected:
                await self.connect()

            market = self.exchange.market(symbol)
            return {
                'symbol': market['symbol'],
                'base': market['base'],
                'quote': market['quote'],
                'active': market['active'],
                'precision': {
                    'price': market['precision']['price'],
                    'amount': market['precision']['amount'],
                },
                'limits': {
                    'amount': {
                        'min': market['limits']['amount']['min'],
                        'max': market['limits']['amount']['max'],
                    },
                    'price': {
                        'min': market['limits']['price']['min'],
                        'max': market['limits']['price']['max'],
                    },
                    'cost': {
                        'min': market['limits']['cost']['min'],
                        'max': market['limits']['cost']['max'],
                    },
                },
                'maker_fee': market.get('maker', 0.001),
                'taker_fee': market.get('taker', 0.001),
            }
        except Exception as e:
            logger.error(f"Error fetching market info for {symbol}: {e}")
            return None

    async def calculate_volatility(self, symbol: str, timeframe: str = '1h', periods: int = 24) -> float:
        """
        Calculate recent price volatility (standard deviation).

        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            periods: Number of periods to analyze

        Returns:
            Volatility as percentage
        """
        try:
            ohlcv = await self.fetch_ohlcv(symbol, timeframe, limit=periods)
            if not ohlcv or len(ohlcv) < 2:
                return 0.0

            closes = [candle['close'] for candle in ohlcv]
            returns = [(closes[i] - closes[i-1]) / closes[i-1] * 100 for i in range(1, len(closes))]

            # Standard deviation of returns
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            volatility = variance ** 0.5

            return round(volatility, 2)
        except Exception as e:
            logger.error(f"Error calculating volatility for {symbol}: {e}")
            return 0.0

    async def get_available_symbols(self, quote: str = 'USDT') -> List[str]:
        """
        Get list of available trading symbols.

        Args:
            quote: Quote currency to filter by (e.g., 'USDT')

        Returns:
            List of symbols
        """
        try:
            if not self.is_connected:
                await self.connect()

            markets = self.exchange.markets
            symbols = [
                symbol for symbol, market in markets.items()
                if market['quote'] == quote and market['active']
            ]
            return sorted(symbols)
        except Exception as e:
            logger.error(f"Error fetching available symbols: {e}")
            return []


class DemoTrader:
    """
    Paper trading engine using real Bybit prices.

    Simulates trades without real capital, perfect for testing
    strategies and signal quality validation.
    """

    def __init__(self, bybit_client: BybitClient, initial_balance: float = 10000.0):
        """
        Initialize demo trader.

        Args:
            bybit_client: Connected BybitClient instance
            initial_balance: Starting balance in USDT
        """
        self.client = bybit_client
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.positions: Dict[str, Dict] = {}
        self.trade_history: List[Dict] = []
        self.pnl_history: List[Dict] = []

    def get_balance(self) -> Dict[str, float]:
        """Get current balance and equity."""
        unrealized_pnl = sum(pos.get('unrealized_pnl', 0) for pos in self.positions.values())
        return {
            'balance': self.balance,
            'unrealized_pnl': unrealized_pnl,
            'equity': self.balance + unrealized_pnl,
            'available': self.balance,
        }

    async def open_position(
        self,
        symbol: str,
        direction: str,
        size: float,
        entry_price: Optional[float] = None,
        tp_percent: Optional[float] = None,
        sl_percent: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Open a demo position.

        Args:
            symbol: Trading pair
            direction: 'LONG' or 'SHORT'
            size: Position size in USDT
            entry_price: Entry price (None = market price)
            tp_percent: Take profit percentage
            sl_percent: Stop loss percentage (negative)

        Returns:
            Position details
        """
        try:
            # Get current market price
            if entry_price is None:
                ticker = await self.client.fetch_ticker(symbol)
                if not ticker or not ticker.get('last'):
                    raise ValueError(f"Could not fetch ticker for {symbol}")
                entry_price = ticker['last']

            if not entry_price:
                raise ValueError("Could not fetch entry price")

            # Check available balance
            if size > self.balance:
                raise ValueError(f"Insufficient balance: {self.balance} < {size}")

            # Calculate TP/SL prices
            tp_price = None
            sl_price = None

            if tp_percent:
                if direction == 'LONG':
                    tp_price = entry_price * (1 + tp_percent / 100)
                else:
                    tp_price = entry_price * (1 - tp_percent / 100)

            if sl_percent:
                if direction == 'LONG':
                    sl_price = entry_price * (1 + sl_percent / 100)  # sl_percent is negative
                else:
                    sl_price = entry_price * (1 - sl_percent / 100)

            # Create position
            position_id = f"{symbol}_{direction}_{datetime.now().timestamp()}"
            position = {
                'id': position_id,
                'symbol': symbol,
                'direction': direction,
                'size': size,
                'entry_price': entry_price,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'tp_percent': tp_percent,
                'sl_percent': sl_percent,
                'opened_at': datetime.now().isoformat(),
                'status': 'open',
                'unrealized_pnl': 0.0,
            }

            self.positions[position_id] = position
            self.balance -= size  # Lock up capital

            logger.info(f"📈 Opened {direction} position on {symbol} at {entry_price} (size: ${size})")
            return position

        except Exception as e:
            logger.error(f"Error opening position: {e}")
            return None

    async def update_positions(self):
        """Update all open positions with current prices."""
        for position_id, position in list(self.positions.items()):
            try:
                symbol = position['symbol']
                ticker = await self.client.fetch_ticker(symbol)
                current_price = ticker['last']

                if not current_price:
                    continue

                # Calculate unrealized PnL
                entry_price = position['entry_price']
                size = position['size']
                direction = position['direction']

                if direction == 'LONG':
                    pnl_percent = (current_price - entry_price) / entry_price * 100
                else:  # SHORT
                    pnl_percent = (entry_price - current_price) / entry_price * 100

                unrealized_pnl = size * (pnl_percent / 100)
                position['unrealized_pnl'] = unrealized_pnl
                position['current_price'] = current_price
                position['pnl_percent'] = pnl_percent

                # Check TP/SL hits
                hit_tp = False
                hit_sl = False

                if position['tp_price']:
                    if direction == 'LONG' and current_price >= position['tp_price']:
                        hit_tp = True
                    elif direction == 'SHORT' and current_price <= position['tp_price']:
                        hit_tp = True

                if position['sl_price']:
                    if direction == 'LONG' and current_price <= position['sl_price']:
                        hit_sl = True
                    elif direction == 'SHORT' and current_price >= position['sl_price']:
                        hit_sl = True

                # Close position if TP or SL hit
                if hit_tp or hit_sl:
                    exit_reason = 'TP' if hit_tp else 'SL'
                    await self.close_position(position_id, exit_reason, current_price)

            except Exception as e:
                logger.error(f"Error updating position {position_id}: {e}")

    async def close_position(
        self,
        position_id: str,
        reason: str = 'manual',
        exit_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Close a demo position.

        Args:
            position_id: Position ID to close
            reason: Close reason ('TP', 'SL', 'manual')
            exit_price: Exit price (None = market price)

        Returns:
            Closed position details with PnL
        """
        try:
            if position_id not in self.positions:
                raise ValueError(f"Position {position_id} not found")

            position = self.positions[position_id]

            # Get exit price
            if exit_price is None:
                ticker = await self.client.fetch_ticker(position['symbol'])
                exit_price = ticker['last']

            # Calculate final PnL
            entry_price = position['entry_price']
            size = position['size']
            direction = position['direction']

            if direction == 'LONG':
                pnl_percent = (exit_price - entry_price) / entry_price * 100
            else:  # SHORT
                pnl_percent = (entry_price - exit_price) / entry_price * 100

            realized_pnl = size * (pnl_percent / 100)

            # Update position
            position['exit_price'] = exit_price
            position['closed_at'] = datetime.now().isoformat()
            position['status'] = 'closed'
            position['close_reason'] = reason
            position['realized_pnl'] = realized_pnl
            position['pnl_percent'] = pnl_percent

            # Release capital and add PnL
            self.balance += size + realized_pnl

            # Record trade
            self.trade_history.append(position.copy())
            self.pnl_history.append({
                'timestamp': datetime.now().isoformat(),
                'symbol': position['symbol'],
                'pnl': realized_pnl,
                'pnl_percent': pnl_percent,
                'balance': self.balance,
            })

            # Remove from open positions
            del self.positions[position_id]

            result_emoji = '✅' if realized_pnl > 0 else '❌'
            logger.info(
                f"{result_emoji} Closed {direction} position on {position['symbol']} "
                f"at {exit_price} ({reason}): PnL ${realized_pnl:.2f} ({pnl_percent:+.2f}%)"
            )

            return position

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get trading statistics."""
        if not self.trade_history:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'avg_pnl': 0.0,
                'max_win': 0.0,
                'max_loss': 0.0,
                'profit_factor': 0.0,
            }

        wins = [t for t in self.trade_history if t['realized_pnl'] > 0]
        losses = [t for t in self.trade_history if t['realized_pnl'] <= 0]

        total_pnl = sum(t['realized_pnl'] for t in self.trade_history)
        win_rate = len(wins) / len(self.trade_history) * 100 if self.trade_history else 0

        gross_profit = sum(t['realized_pnl'] for t in wins) if wins else 0
        gross_loss = abs(sum(t['realized_pnl'] for t in losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        return {
            'total_trades': len(self.trade_history),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_percent': round(total_pnl / self.initial_balance * 100, 2),
            'avg_pnl': round(total_pnl / len(self.trade_history), 2),
            'max_win': round(max((t['realized_pnl'] for t in wins), default=0), 2),
            'max_loss': round(min((t['realized_pnl'] for t in losses), default=0), 2),
            'profit_factor': round(profit_factor, 2),
            'current_balance': round(self.balance, 2),
            'equity': round(self.get_balance()['equity'], 2),
        }


# Connection pool management
class BybitConnectionPool:
    """
    Manages a pool of BybitClient instances for high-throughput operations.
    """

    def __init__(self, pool_size: int = 5, testnet: bool = True):
        """
        Initialize connection pool.

        Args:
            pool_size: Number of client instances (default: 5)
            testnet: Use testnet (default: True)
        """
        self.pool_size = pool_size
        self.testnet = testnet
        self.clients: List[BybitClient] = []
        self.client_index = 0
        self.lock = asyncio.Lock()

    async def initialize(self, api_key: Optional[str] = None, api_secret: Optional[str] = None,
                         demo_trading: bool = False):
        """Initialize all clients in the pool."""
        for i in range(self.pool_size):
            client = BybitClient(
                api_key=api_key,
                api_secret=api_secret,
                testnet=self.testnet,
                demo_trading=demo_trading,
                max_connections=20
            )
            if await client.connect():
                self.clients.append(client)
                logger.info(f"Initialized client {i+1}/{self.pool_size} in pool")
            else:
                logger.error(f"Failed to initialize client {i+1}/{self.pool_size}")

        if not self.clients:
            raise RuntimeError("Failed to initialize any clients in pool")

    async def get_client(self) -> BybitClient:
        """
        Get next available client using round-robin.

        Returns:
            BybitClient instance
        """
        async with self.lock:
            if not self.clients:
                await self.initialize()

            client = self.clients[self.client_index]
            self.client_index = (self.client_index + 1) % len(self.clients)
            return client

    async def close_all(self):
        """Close all clients in the pool."""
        for client in self.clients:
            await client.close()
        self.clients.clear()

    async def health_check_all(self) -> List[Dict]:
        """
        Check health of all clients.

        Returns:
            List of health status dicts
        """
        health_statuses = []
        for i, client in enumerate(self.clients):
            status = await client.check_health()
            status['client_id'] = i
            health_statuses.append(status)
        return health_statuses


# Global instances
_bybit_client: Optional[BybitClient] = None
_bybit_pool: Optional[BybitConnectionPool] = None


async def get_bybit_client(use_pool: bool = False, pool_size: int = 5,
                           api_key: Optional[str] = None, api_secret: Optional[str] = None,
                           testnet: bool = False, demo_trading: bool = True) -> BybitClient:
    """
    Get or create global Bybit client instance.

    Args:
        use_pool: Use connection pool for high throughput (default: False)
        pool_size: Size of connection pool if enabled (default: 5)
        api_key: Bybit API key (from env if None)
        api_secret: Bybit API secret (from env if None)
        testnet: Use testnet (default: False)
        demo_trading: Use demo trading on live endpoint (default: True)

    Returns:
        BybitClient instance
    """
    global _bybit_client, _bybit_pool

    # Get credentials from environment if not provided
    if api_key is None:
        import os
        api_key = os.getenv('BYBIT_API_KEY')
        api_secret = os.getenv('BYBIT_API_SECRET')
        testnet_env = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'
        # Use demo_trading if not testnet
        if not testnet_env:
            demo_trading = True
            testnet = False

    if use_pool:
        if _bybit_pool is None:
            _bybit_pool = BybitConnectionPool(pool_size=pool_size, testnet=testnet)
            await _bybit_pool.initialize(api_key=api_key, api_secret=api_secret, demo_trading=demo_trading)
        return await _bybit_pool.get_client()
    else:
        if _bybit_client is None:
            _bybit_client = BybitClient(
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet,
                demo_trading=demo_trading,
                max_connections=10
            )
            await _bybit_client.connect()
        return _bybit_client
