#!/usr/bin/env python3
"""
Production-Ready New Listing Detector for Crypto Exchanges

Detects new cryptocurrency listings in real-time across:
- Binance Futures (USDT perpetuals)
- Bybit Futures (USDT perpetuals)
- Upbit Spot (KRW pairs - CRITICAL for price impact)
- MEXC Futures (USDT perpetuals)

Uses hybrid approach: WebSocket primary + REST backup
"""

import ccxt
import ccxt.pro as ccxtpro
import asyncio
import redis
import json
import logging
import websockets
import aiohttp
from typing import Dict, Set, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ExchangeType(Enum):
    """Exchange types for different handling"""
    FUTURES = "futures"
    SPOT = "spot"


@dataclass
class NewListingEvent:
    """Data structure for new listing events"""
    exchange: str
    symbol: str
    price: float
    volume: float
    timestamp: datetime
    source: str  # 'websocket' or 'rest'
    metadata: Dict


class NewListingDetector:
    """
    Enterprise-grade new listing detector with CCXT integration

    Features:
    - Real-time WebSocket detection (1-5 second latency)
    - REST API backup polling (5 minute intervals)
    - Redis persistence for known symbols
    - Automatic retry and reconnection
    - Webhook notifications to trading system
    """

    def __init__(self,
                 redis_host: str = 'localhost',
                 redis_port: int = 6379,
                 webhook_url: str = "http://localhost:8000/api/webhook/tradingview"):

        # Configuration
        self.webhook_url = webhook_url
        self.rest_poll_interval = 300  # 5 minutes

        # Exchange configurations
        self.exchange_configs = {
            'binance': {
                'type': ExchangeType.FUTURES,
                'ccxt_options': {
                    'enableRateLimit': True,
                    'options': {'defaultType': 'future'}
                }
            },
            'bybit': {
                'type': ExchangeType.FUTURES,
                'ccxt_options': {
                    'enableRateLimit': True,
                    'options': {'defaultType': 'linear'}
                }
            },
            'upbit': {
                'type': ExchangeType.SPOT,
                'ccxt_options': {
                    'enableRateLimit': True
                },
                'ws_url': 'wss://api.upbit.com/websocket/v1'
            },
            'mexc': {
                'type': ExchangeType.FUTURES,
                'ccxt_options': {
                    'enableRateLimit': True,
                    'options': {'defaultType': 'swap'}
                }
            }
        }

        # Initialize REST exchanges
        self.rest_exchanges = {}
        for name, config in self.exchange_configs.items():
            try:
                exchange_class = getattr(ccxt, name)
                self.rest_exchanges[name] = exchange_class(config['ccxt_options'])
                logger.info(f"✅ Initialized REST client for {name}")
            except Exception as e:
                logger.error(f"Failed to initialize REST for {name}: {e}")

        # Initialize WebSocket exchanges (where supported by CCXT Pro)
        self.ws_exchanges = {}
        for name in ['binance', 'bybit']:
            try:
                exchange_class = getattr(ccxtpro, name)
                config = self.exchange_configs[name]
                self.ws_exchanges[name] = exchange_class(config['ccxt_options'])
                logger.info(f"✅ Initialized WebSocket client for {name}")
            except Exception as e:
                logger.error(f"Failed to initialize WebSocket for {name}: {e}")

        # Redis for persistence
        try:
            self.redis = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True,
                socket_connect_timeout=5
            )
            self.redis.ping()
            logger.info("✅ Connected to Redis")
        except Exception as e:
            logger.warning(f"Redis not available: {e}. Using in-memory storage.")
            self.redis = None

        # Symbol tracking
        self.known_symbols: Dict[str, Set[str]] = {}
        self.detection_cache: Dict[str, datetime] = {}

        # Control flags
        self.is_running = False
        self.tasks: List[asyncio.Task] = []

        # Callbacks for extensibility
        self.event_callbacks: List[Callable] = []

        # Statistics
        self.stats = {
            'total_detections': 0,
            'detections_by_exchange': {},
            'websocket_reconnects': 0,
            'rest_polls': 0,
            'webhook_sent': 0,
            'webhook_failed': 0
        }

    async def initialize(self):
        """Initialize detector and load known symbols"""
        logger.info("🚀 Initializing New Listing Detector")

        # Load known symbols from Redis or fetch current markets
        for exchange in self.rest_exchanges:
            await self._load_known_symbols(exchange)

        logger.info(f"📊 Initialization complete. Tracking {sum(len(s) for s in self.known_symbols.values())} total symbols")

    async def _load_known_symbols(self, exchange_name: str):
        """Load known symbols from Redis or fetch from exchange"""
        # Try Redis first
        if self.redis:
            try:
                stored = self.redis.smembers(f"known:{exchange_name}")
                if stored:
                    self.known_symbols[exchange_name] = stored
                    logger.info(f"  Loaded {len(stored)} known symbols for {exchange_name} from Redis")
                    return
            except Exception as e:
                logger.warning(f"Redis error loading {exchange_name}: {e}")

        # Fetch current markets from exchange
        try:
            exchange = self.rest_exchanges[exchange_name]
            markets = exchange.fetch_markets()

            # Filter based on exchange type
            if self.exchange_configs[exchange_name]['type'] == ExchangeType.SPOT:
                # For Upbit, get KRW pairs
                if exchange_name == 'upbit':
                    symbols = {
                        m['symbol'] for m in markets
                        if m['quote'] == 'KRW' and m['active']
                    }
                else:
                    symbols = {
                        m['symbol'] for m in markets
                        if m['active'] and m['type'] == 'spot'
                    }
            else:
                # For futures exchanges
                symbols = {
                    m['symbol'] for m in markets
                    if m['active'] and m['type'] in ['swap', 'future', 'perpetual']
                }

            self.known_symbols[exchange_name] = symbols

            # Store in Redis
            if self.redis and symbols:
                self.redis.sadd(f"known:{exchange_name}", *symbols)

            logger.info(f"  Initialized {len(symbols)} symbols for {exchange_name}")

        except Exception as e:
            logger.error(f"Failed to fetch markets for {exchange_name}: {e}")
            self.known_symbols[exchange_name] = set()

    async def watch_binance_websocket(self):
        """Watch Binance futures via CCXT Pro WebSocket"""
        exchange = self.ws_exchanges.get('binance')
        if not exchange:
            return

        retry_count = 0

        while self.is_running:
            try:
                await exchange.load_markets()
                logger.info("📡 Connected to Binance WebSocket")
                retry_count = 0

                while self.is_running:
                    # Watch all tickers
                    tickers = await exchange.watch_tickers()

                    # Check for new symbols
                    await self._process_tickers('binance', tickers, 'websocket')

            except Exception as e:
                retry_count += 1
                self.stats['websocket_reconnects'] += 1
                wait_time = min(2 ** retry_count, 60)
                logger.error(f"Binance WebSocket error: {e}. Reconnecting in {wait_time}s...")
                await asyncio.sleep(wait_time)

    async def watch_bybit_websocket(self):
        """Watch Bybit futures via CCXT Pro WebSocket"""
        exchange = self.ws_exchanges.get('bybit')
        if not exchange:
            return

        retry_count = 0

        while self.is_running:
            try:
                await exchange.load_markets()
                logger.info("📡 Connected to Bybit WebSocket")
                retry_count = 0

                while self.is_running:
                    # Watch all tickers
                    tickers = await exchange.watch_tickers()

                    # Check for new symbols
                    await self._process_tickers('bybit', tickers, 'websocket')

            except Exception as e:
                retry_count += 1
                self.stats['websocket_reconnects'] += 1
                wait_time = min(2 ** retry_count, 60)
                logger.error(f"Bybit WebSocket error: {e}. Reconnecting in {wait_time}s...")
                await asyncio.sleep(wait_time)

    async def watch_upbit_websocket(self):
        """
        Watch Upbit KRW pairs via direct WebSocket

        CRITICAL: Upbit listings create massive pumps (50-200%)
        Fast detection is essential for profitability
        """
        url = self.exchange_configs['upbit']['ws_url']
        retry_count = 0

        while self.is_running:
            try:
                async with websockets.connect(url) as ws:
                    logger.info("📡 Connected to Upbit WebSocket (KRW pairs)")
                    retry_count = 0

                    # Get current KRW markets
                    exchange = self.rest_exchanges.get('upbit')
                    if exchange:
                        markets = exchange.fetch_markets()
                        krw_codes = [
                            m['id'] for m in markets
                            if m['quote'] == 'KRW' and m['active']
                        ]
                    else:
                        krw_codes = []

                    # Subscribe to all KRW tickers
                    subscribe = [
                        {"ticket": "listing_detector"},
                        {
                            "type": "ticker",
                            "codes": krw_codes,
                            "isOnlyRealtime": True
                        }
                    ]

                    await ws.send(json.dumps(subscribe))

                    # Heartbeat task
                    async def send_ping():
                        while self.is_running:
                            await asyncio.sleep(30)
                            await ws.ping()

                    ping_task = asyncio.create_task(send_ping())

                    try:
                        async for message in ws:
                            if not self.is_running:
                                break

                            data = json.loads(message)
                            code = data.get('code', '')

                            if code.startswith('KRW-'):
                                # Convert to CCXT format
                                base = code.replace('KRW-', '')
                                symbol = f"{base}/KRW"

                                # Check if new
                                known = self.known_symbols.get('upbit', set())
                                if symbol not in known:
                                    volume = float(data.get('acc_trade_volume_24h', 0))

                                    if volume > 0:  # Has actual trading
                                        price = float(data.get('trade_price', 0))
                                        change = float(data.get('signed_change_rate', 0)) * 100

                                        event = NewListingEvent(
                                            exchange='upbit',
                                            symbol=symbol,
                                            price=price,
                                            volume=volume,
                                            timestamp=datetime.now(),
                                            source='websocket',
                                            metadata={
                                                'change_percentage': change,
                                                'code': code,
                                                'alert': 'EXTREME_VOLATILITY_EXPECTED'
                                            }
                                        )

                                        await self._handle_new_listing(event)

                    finally:
                        ping_task.cancel()

            except Exception as e:
                retry_count += 1
                wait_time = min(2 ** retry_count, 60)
                logger.error(f"Upbit WebSocket error: {e}. Reconnecting in {wait_time}s...")
                await asyncio.sleep(wait_time)

    async def periodic_rest_check(self):
        """Periodic REST API check as backup for all exchanges"""

        while self.is_running:
            # Wait for interval
            await asyncio.sleep(self.rest_poll_interval)

            logger.debug(f"Running periodic REST check...")
            self.stats['rest_polls'] += 1

            for exchange_name, exchange in self.rest_exchanges.items():
                try:
                    markets = exchange.fetch_markets()

                    # Filter based on exchange type
                    config = self.exchange_configs[exchange_name]
                    if config['type'] == ExchangeType.SPOT:
                        if exchange_name == 'upbit':
                            current_symbols = {
                                m['symbol'] for m in markets
                                if m['quote'] == 'KRW' and m['active']
                            }
                        else:
                            current_symbols = {
                                m['symbol'] for m in markets
                                if m['active'] and m['type'] == 'spot'
                            }
                    else:
                        current_symbols = {
                            m['symbol'] for m in markets
                            if m['active'] and m['type'] in ['swap', 'future', 'perpetual']
                        }

                    # Check for new symbols
                    known = self.known_symbols.get(exchange_name, set())
                    new_symbols = current_symbols - known

                    if new_symbols:
                        logger.info(f"REST check found {len(new_symbols)} new symbols on {exchange_name}")

                        for symbol in new_symbols:
                            # Get market details
                            market = next((m for m in markets if m['symbol'] == symbol), None)

                            if market:
                                event = NewListingEvent(
                                    exchange=exchange_name,
                                    symbol=symbol,
                                    price=0,  # Will be fetched if needed
                                    volume=0,
                                    timestamp=datetime.now(),
                                    source='rest',
                                    metadata={'market_info': market}
                                )

                                await self._handle_new_listing(event)

                except Exception as e:
                    logger.error(f"REST check error for {exchange_name}: {e}")

    async def check_mexc_new_flag(self):
        """
        Special check for MEXC's 'isNew' flag
        MEXC explicitly marks new listings
        """

        while self.is_running:
            await asyncio.sleep(60)  # Check every minute

            try:
                exchange = self.rest_exchanges.get('mexc')
                if not exchange:
                    continue

                # MEXC-specific API call
                response = exchange.publicGetApi2FuturesContractDetail()

                for contract in response.get('data', []):
                    if contract.get('isNew', False):
                        symbol = contract['symbol']

                        # Convert to CCXT format
                        if 'USDT' in symbol:
                            formatted_symbol = symbol.replace('_', '/')
                        else:
                            formatted_symbol = symbol

                        known = self.known_symbols.get('mexc', set())
                        if formatted_symbol not in known:
                            event = NewListingEvent(
                                exchange='mexc',
                                symbol=formatted_symbol,
                                price=float(contract.get('lastPrice', 0)),
                                volume=float(contract.get('volumeReal', 0)),
                                timestamp=datetime.now(),
                                source='rest',
                                metadata={
                                    'is_new_flag': True,
                                    'opening_time': contract.get('openingTime'),
                                    'list_time': contract.get('listTime')
                                }
                            )

                            await self._handle_new_listing(event)

            except Exception as e:
                logger.error(f"MEXC new flag check error: {e}")

    async def _process_tickers(self, exchange_name: str, tickers: Dict, source: str):
        """Process ticker data for new symbols"""
        current_symbols = set(tickers.keys())
        known = self.known_symbols.get(exchange_name, set())
        new_symbols = current_symbols - known

        if new_symbols:
            for symbol in new_symbols:
                ticker = tickers[symbol]

                # Verify actual trading (volume > 0)
                volume = ticker.get('baseVolume', 0)
                if volume and volume > 0:
                    event = NewListingEvent(
                        exchange=exchange_name,
                        symbol=symbol,
                        price=ticker.get('last', 0),
                        volume=volume,
                        timestamp=datetime.now(),
                        source=source,
                        metadata={
                            'bid': ticker.get('bid'),
                            'ask': ticker.get('ask'),
                            'percentage': ticker.get('percentage')
                        }
                    )

                    await self._handle_new_listing(event)

    async def _handle_new_listing(self, event: NewListingEvent):
        """Process new listing event"""

        # Deduplication check
        cache_key = f"{event.exchange}:{event.symbol}"
        last_detection = self.detection_cache.get(cache_key)

        if last_detection and (datetime.now() - last_detection) < timedelta(minutes=1):
            return  # Already detected recently

        # Update tracking
        if event.exchange not in self.known_symbols:
            self.known_symbols[event.exchange] = set()

        self.known_symbols[event.exchange].add(event.symbol)
        self.detection_cache[cache_key] = datetime.now()

        # Update statistics
        self.stats['total_detections'] += 1
        if event.exchange not in self.stats['detections_by_exchange']:
            self.stats['detections_by_exchange'][event.exchange] = 0
        self.stats['detections_by_exchange'][event.exchange] += 1

        # Store in Redis
        if self.redis:
            try:
                self.redis.sadd(f"known:{event.exchange}", event.symbol)
                # Store detection event
                self.redis.hset(
                    f"detection:{cache_key}",
                    mapping={
                        'timestamp': event.timestamp.isoformat(),
                        'source': event.source,
                        'price': str(event.price),
                        'volume': str(event.volume)
                    }
                )
                self.redis.expire(f"detection:{cache_key}", 86400)  # 24 hour expiry
            except Exception as e:
                logger.error(f"Redis storage error: {e}")

        # Log detection
        logger.warning("=" * 60)
        logger.warning(f"🚨 NEW LISTING DETECTED via {event.source.upper()}")
        logger.warning(f"   Exchange: {event.exchange}")
        logger.warning(f"   Symbol: {event.symbol}")
        logger.warning(f"   Price: ${event.price:.6f}" if event.price else "   Price: N/A")
        logger.warning(f"   Volume: {event.volume:.2f}" if event.volume else "   Volume: N/A")

        if event.exchange == 'upbit':
            logger.warning("   ⚠️ UPBIT LISTING - EXPECT EXTREME VOLATILITY (50-200% possible)")

        if event.metadata.get('is_new_flag'):
            logger.warning("   📍 Explicitly marked as NEW by exchange")

        logger.warning("=" * 60)

        # Execute callbacks
        for callback in self.event_callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Callback error: {e}")

        # Send webhook
        await self._send_webhook(event)

    async def _send_webhook(self, event: NewListingEvent):
        """Send webhook notification to trading system"""

        # Format symbol (remove slash for compatibility)
        formatted_symbol = event.symbol.replace('/', '')

        # Prepare payloads based on exchange
        payloads = []

        if event.exchange == 'upbit':
            # Upbit typically pumps hard on new listings
            payloads.append({
                "symbol": formatted_symbol,
                "direction": "LONG",
                "source": f"new_listing_{event.exchange}",
                "timeframe": "1m",  # Quick trades for volatile listings
                "metadata": {
                    "reason": "upbit_new_listing",
                    "expected_volatility": "extreme",
                    "detection_source": event.source,
                    "current_price": event.price,
                    "volume_24h": event.volume
                }
            })
        else:
            # Other exchanges: send both LONG and SHORT
            for direction in ["LONG", "SHORT"]:
                payloads.append({
                    "symbol": formatted_symbol,
                    "direction": direction,
                    "source": f"new_listing_{event.exchange}",
                    "timeframe": "5m",
                    "metadata": {
                        "reason": "new_listing_detected",
                        "exchange": event.exchange,
                        "detection_source": event.source,
                        "detection_price": event.price,
                        "detection_volume": event.volume
                    }
                })

        # Send webhooks
        async with aiohttp.ClientSession() as session:
            for payload in payloads:
                try:
                    async with session.post(
                        self.webhook_url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            logger.info(f"✅ Sent {payload['direction']} signal for {formatted_symbol}")
                            self.stats['webhook_sent'] += 1
                        else:
                            logger.error(f"Webhook failed with status {response.status}")
                            self.stats['webhook_failed'] += 1
                except Exception as e:
                    logger.error(f"Webhook error: {e}")
                    self.stats['webhook_failed'] += 1

    def add_callback(self, callback: Callable):
        """Add a callback for new listing events"""
        self.event_callbacks.append(callback)

    async def start(self):
        """Start the detector"""
        self.is_running = True

        # Initialize
        await self.initialize()

        logger.info("=" * 60)
        logger.info("🚀 NEW LISTING DETECTOR STARTED")
        logger.info("Exchanges: Binance, Bybit, Upbit, MEXC")
        logger.info("Method: Hybrid (WebSocket + REST)")
        logger.info(f"Webhook: {self.webhook_url}")
        logger.info("=" * 60)

        # Create tasks
        self.tasks = [
            # WebSocket watchers
            asyncio.create_task(self.watch_binance_websocket()),
            asyncio.create_task(self.watch_bybit_websocket()),
            asyncio.create_task(self.watch_upbit_websocket()),

            # REST checkers
            asyncio.create_task(self.periodic_rest_check()),
            asyncio.create_task(self.check_mexc_new_flag()),
        ]

        try:
            await asyncio.gather(*self.tasks)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal...")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        finally:
            await self.stop()

    async def stop(self):
        """Stop the detector gracefully"""
        logger.info("Shutting down detector...")
        self.is_running = False

        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.tasks, return_exceptions=True)

        # Close WebSocket exchanges
        for exchange in self.ws_exchanges.values():
            try:
                await exchange.close()
            except:
                pass

        # Print statistics
        logger.info("=" * 60)
        logger.info("📊 Final Statistics:")
        logger.info(f"   Total Detections: {self.stats['total_detections']}")
        for exchange, count in self.stats['detections_by_exchange'].items():
            logger.info(f"     - {exchange}: {count}")
        logger.info(f"   WebSocket Reconnects: {self.stats['websocket_reconnects']}")
        logger.info(f"   REST Polls: {self.stats['rest_polls']}")
        logger.info(f"   Webhooks Sent: {self.stats['webhook_sent']}")
        logger.info(f"   Webhooks Failed: {self.stats['webhook_failed']}")
        logger.info("=" * 60)

    def get_stats(self) -> Dict:
        """Get current statistics"""
        return {
            **self.stats,
            'known_symbols_count': {
                exchange: len(symbols)
                for exchange, symbols in self.known_symbols.items()
            },
            'is_running': self.is_running
        }


async def main():
    """Main entry point"""

    # Create detector
    detector = NewListingDetector(
        redis_host='localhost',
        webhook_url="http://localhost:8000/api/webhook/tradingview"
    )

    # Add custom callback (optional)
    async def custom_handler(event: NewListingEvent):
        # Your custom logic here
        print(f"Custom handler: {event.symbol} on {event.exchange}")

    detector.add_callback(custom_handler)

    # Start detector
    try:
        await detector.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run the detector
    asyncio.run(main())