"""
Real-time Market Data Service using CCXT Pro (WebSocket)

Provides high-frequency price streaming, volatility calculation, and order book depth analysis
for 100+ cryptocurrencies. Optimized for signal generation with 5-second update intervals.
"""

import ccxt.pro as ccxtpro
import asyncio
import logging
from typing import Dict, List, Optional, Any, Set, Callable
from datetime import datetime, timedelta
from collections import defaultdict, deque
import numpy as np
from decimal import Decimal
import json

logger = logging.getLogger(__name__)


class MarketDataService:
    """
    Real-time market data streaming service using CCXT Pro WebSocket connections.

    Features:
    - Multi-symbol price tracking (100+ coins simultaneously)
    - 5-second update intervals
    - Real-time volatility calculation (ATR, Bollinger Bands)
    - Order book depth analysis
    - Price change detection for signal generation
    """

    def __init__(self, testnet: bool = True):
        """
        Initialize market data service.

        Args:
            testnet: Use testnet for demo trading (default: True)
        """
        self.exchange = ccxtpro.bybit({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'linear',  # USDT perpetual
                'testnet': testnet,
            }
        })

        # Price tracking
        self.current_prices: Dict[str, float] = {}
        self.price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))  # Last 100 prices per symbol
        self.last_update: Dict[str, datetime] = {}

        # Volatility tracking
        self.atr_values: Dict[str, float] = {}
        self.bollinger_bands: Dict[str, Dict[str, float]] = {}

        # Order book tracking
        self.order_books: Dict[str, Dict] = {}
        self.bid_ask_spread: Dict[str, float] = {}

        # Volume tracking
        self.volume_24h: Dict[str, float] = {}
        self.volume_spikes: Dict[str, bool] = {}

        # Streaming management
        self.active_symbols: Set[str] = set()
        self.is_streaming = False
        self.stream_tasks: List[asyncio.Task] = []

        # Callbacks for price changes
        self.price_callbacks: List[Callable] = []
        self.signal_callbacks: List[Callable] = []

        # Performance metrics
        self.updates_per_second = 0
        self.total_updates = 0
        self.start_time = None

    async def connect(self) -> bool:
        """
        Initialize exchange connection.

        Returns:
            True if connection successful
        """
        try:
            await self.exchange.load_markets()
            logger.info(f"✅ Connected to Bybit WebSocket ({'testnet' if self.exchange.options.get('testnet') else 'mainnet'})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to Bybit WebSocket: {e}")
            return False

    async def start_streaming(self, symbols: List[str], update_interval: int = 5):
        """
        Start streaming real-time data for multiple symbols.

        Args:
            symbols: List of trading pairs (e.g., ['BTC/USDT', 'ETH/USDT'])
            update_interval: Update interval in seconds (default: 5)
        """
        if self.is_streaming:
            logger.warning("Streaming already active")
            return

        self.active_symbols = set(symbols)
        self.is_streaming = True
        self.start_time = datetime.now()

        logger.info(f"📡 Starting real-time streaming for {len(symbols)} symbols")

        # Create streaming tasks
        tasks = []

        # Ticker streaming (prices and volume)
        tasks.append(asyncio.create_task(self._stream_tickers(symbols)))

        # Order book streaming (depth analysis)
        tasks.append(asyncio.create_task(self._stream_order_books(symbols)))

        # OHLCV streaming (for volatility calculation)
        tasks.append(asyncio.create_task(self._stream_ohlcv(symbols)))

        # Update processor (calculates metrics every interval)
        tasks.append(asyncio.create_task(self._process_updates(update_interval)))

        self.stream_tasks = tasks

        # Run all tasks concurrently
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Streaming tasks cancelled")
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            self.is_streaming = False

    async def _stream_tickers(self, symbols: List[str]):
        """Stream ticker data (price and volume) via WebSocket."""
        logger.info(f"Starting ticker stream for {len(symbols)} symbols")

        while self.is_streaming:
            try:
                # Watch multiple tickers simultaneously
                for symbol in symbols:
                    if not self.is_streaming:
                        break

                    try:
                        ticker = await self.exchange.watch_ticker(symbol)

                        # Update price data
                        current_price = ticker['last']
                        self.current_prices[symbol] = current_price
                        self.price_history[symbol].append(current_price)
                        self.last_update[symbol] = datetime.now()

                        # Update volume data
                        self.volume_24h[symbol] = ticker['baseVolume']

                        # Check for volume spikes
                        if symbol in self.volume_24h and len(self.price_history[symbol]) > 10:
                            avg_volume = np.mean(list(self.volume_24h.values()))
                            self.volume_spikes[symbol] = ticker['baseVolume'] > avg_volume * 2

                        self.total_updates += 1

                        # Trigger callbacks
                        for callback in self.price_callbacks:
                            asyncio.create_task(callback(symbol, current_price))

                    except Exception as e:
                        logger.error(f"Error watching ticker for {symbol}: {e}")
                        await asyncio.sleep(0.1)

                await asyncio.sleep(0.01)  # Small delay to prevent overwhelming

            except Exception as e:
                logger.error(f"Ticker stream error: {e}")
                await asyncio.sleep(1)

    async def _stream_order_books(self, symbols: List[str]):
        """Stream order book data for depth analysis."""
        logger.info(f"Starting order book stream for {len(symbols)} symbols")

        while self.is_streaming:
            try:
                for symbol in symbols:
                    if not self.is_streaming:
                        break

                    try:
                        orderbook = await self.exchange.watch_order_book(symbol, limit=20)

                        # Calculate metrics
                        bids = orderbook['bids']
                        asks = orderbook['asks']

                        if bids and asks:
                            best_bid = bids[0][0]
                            best_ask = asks[0][0]

                            # Calculate spread
                            spread = (best_ask - best_bid) / best_bid * 100
                            self.bid_ask_spread[symbol] = spread

                            # Calculate order book imbalance
                            bid_volume = sum(bid[1] for bid in bids[:10])
                            ask_volume = sum(ask[1] for ask in asks[:10])
                            imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume) if (bid_volume + ask_volume) > 0 else 0

                            self.order_books[symbol] = {
                                'best_bid': best_bid,
                                'best_ask': best_ask,
                                'spread': spread,
                                'bid_volume': bid_volume,
                                'ask_volume': ask_volume,
                                'imbalance': imbalance,
                                'timestamp': datetime.now()
                            }

                    except Exception as e:
                        logger.error(f"Error watching order book for {symbol}: {e}")
                        await asyncio.sleep(0.1)

                await asyncio.sleep(0.1)  # Rate limiting

            except Exception as e:
                logger.error(f"Order book stream error: {e}")
                await asyncio.sleep(1)

    async def _stream_ohlcv(self, symbols: List[str]):
        """Stream OHLCV data for volatility calculation."""
        logger.info(f"Starting OHLCV stream for {len(symbols)} symbols")

        while self.is_streaming:
            try:
                for symbol in symbols:
                    if not self.is_streaming:
                        break

                    try:
                        # Fetch recent OHLCV for volatility calculation
                        ohlcv = await self.exchange.watch_ohlcv(symbol, '1m', limit=20)

                        if len(ohlcv) >= 14:  # Need at least 14 periods for ATR
                            # Calculate ATR (Average True Range)
                            atr = self._calculate_atr(ohlcv)
                            self.atr_values[symbol] = atr

                            # Calculate Bollinger Bands
                            bb = self._calculate_bollinger_bands(ohlcv)
                            self.bollinger_bands[symbol] = bb

                    except Exception as e:
                        logger.error(f"Error watching OHLCV for {symbol}: {e}")
                        await asyncio.sleep(0.1)

                await asyncio.sleep(5)  # Update volatility every 5 seconds

            except Exception as e:
                logger.error(f"OHLCV stream error: {e}")
                await asyncio.sleep(1)

    def _calculate_atr(self, ohlcv: List, period: int = 14) -> float:
        """
        Calculate Average True Range (ATR) for volatility measurement.

        Args:
            ohlcv: OHLCV candle data
            period: ATR period (default: 14)

        Returns:
            ATR value
        """
        if len(ohlcv) < period + 1:
            return 0.0

        true_ranges = []
        for i in range(1, len(ohlcv)):
            high = ohlcv[i][2]
            low = ohlcv[i][3]
            prev_close = ohlcv[i-1][4]

            true_range = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(true_range)

        # Calculate ATR
        atr = np.mean(true_ranges[-period:])
        return float(atr)

    def _calculate_bollinger_bands(self, ohlcv: List, period: int = 20, std_dev: float = 2.0) -> Dict[str, float]:
        """
        Calculate Bollinger Bands for volatility and breakout detection.

        Args:
            ohlcv: OHLCV candle data
            period: MA period (default: 20)
            std_dev: Standard deviation multiplier (default: 2.0)

        Returns:
            Dict with upper, middle, lower bands and width
        """
        if len(ohlcv) < period:
            return {'upper': 0, 'middle': 0, 'lower': 0, 'width': 0}

        closes = [candle[4] for candle in ohlcv[-period:]]
        middle = np.mean(closes)
        std = np.std(closes)

        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        width = (upper - lower) / middle * 100  # Width as percentage

        return {
            'upper': float(upper),
            'middle': float(middle),
            'lower': float(lower),
            'width': float(width),
            'std': float(std)
        }

    async def _process_updates(self, interval: int):
        """
        Process updates and detect signals every interval.

        Args:
            interval: Update interval in seconds
        """
        while self.is_streaming:
            await asyncio.sleep(interval)

            # Calculate performance metrics
            if self.start_time:
                elapsed = (datetime.now() - self.start_time).total_seconds()
                self.updates_per_second = self.total_updates / elapsed if elapsed > 0 else 0

            # Detect signals for each symbol
            for symbol in self.active_symbols:
                if symbol in self.current_prices:
                    signal = self._detect_signal(symbol)
                    if signal:
                        logger.info(f"🎯 Signal detected for {symbol}: {signal}")
                        for callback in self.signal_callbacks:
                            asyncio.create_task(callback(symbol, signal))

    def _detect_signal(self, symbol: str) -> Optional[Dict]:
        """
        Detect trading signals based on market data.

        Args:
            symbol: Trading pair

        Returns:
            Signal dict if conditions met, None otherwise
        """
        if symbol not in self.current_prices:
            return None

        signals = []
        confidence = 0.5  # Base confidence

        # 1. Breakout Detection (Bollinger Bands)
        if symbol in self.bollinger_bands:
            bb = self.bollinger_bands[symbol]
            price = self.current_prices[symbol]

            if bb['upper'] > 0:
                if price > bb['upper']:
                    signals.append('BB_BREAKOUT_UP')
                    confidence += 0.1
                elif price < bb['lower']:
                    signals.append('BB_BREAKOUT_DOWN')
                    confidence += 0.1

        # 2. Volume Spike Detection
        if symbol in self.volume_spikes and self.volume_spikes[symbol]:
            signals.append('VOLUME_SPIKE')
            confidence += 0.15

        # 3. Order Book Imbalance
        if symbol in self.order_books:
            imbalance = self.order_books[symbol]['imbalance']
            if abs(imbalance) > 0.3:  # Significant imbalance
                if imbalance > 0:
                    signals.append('STRONG_BID_PRESSURE')
                    confidence += 0.1
                else:
                    signals.append('STRONG_ASK_PRESSURE')
                    confidence += 0.1

        # 4. Momentum Detection (price change)
        if symbol in self.price_history and len(self.price_history[symbol]) >= 10:
            prices = list(self.price_history[symbol])
            price_change = (prices[-1] - prices[-10]) / prices[-10] * 100

            if abs(price_change) > 0.5:  # 0.5% move in last 10 updates
                if price_change > 0:
                    signals.append('MOMENTUM_UP')
                else:
                    signals.append('MOMENTUM_DOWN')
                confidence += 0.1

        # 5. Low Spread (good liquidity)
        if symbol in self.bid_ask_spread and self.bid_ask_spread[symbol] < 0.1:
            signals.append('TIGHT_SPREAD')
            confidence += 0.05

        # Generate signal if confidence is high enough
        if confidence >= 0.6 and signals:
            direction = 'LONG' if any('UP' in s or 'BID' in s for s in signals) else 'SHORT'

            return {
                'symbol': symbol,
                'direction': direction,
                'entry_price': self.current_prices[symbol],
                'confidence': min(confidence, 1.0),
                'signals': signals,
                'timestamp': datetime.now(),
                'volatility': self.atr_values.get(symbol, 0),
                'volume_24h': self.volume_24h.get(symbol, 0),
                'spread': self.bid_ask_spread.get(symbol, 0),
                'order_book': self.order_books.get(symbol, {})
            }

        return None

    def add_price_callback(self, callback: Callable):
        """
        Add callback for price updates.

        Args:
            callback: Async function(symbol, price) called on price updates
        """
        self.price_callbacks.append(callback)

    def add_signal_callback(self, callback: Callable):
        """
        Add callback for signal detection.

        Args:
            callback: Async function(symbol, signal) called when signal detected
        """
        self.signal_callbacks.append(callback)

    async def stop_streaming(self):
        """Stop all streaming tasks."""
        self.is_streaming = False

        # Cancel all tasks
        for task in self.stream_tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.stream_tasks, return_exceptions=True)

        # Close exchange connection
        await self.exchange.close()

        logger.info("📴 Stopped market data streaming")

    def get_market_summary(self, symbol: str) -> Optional[Dict]:
        """
        Get comprehensive market summary for a symbol.

        Args:
            symbol: Trading pair

        Returns:
            Market summary dict
        """
        if symbol not in self.current_prices:
            return None

        return {
            'symbol': symbol,
            'price': self.current_prices.get(symbol),
            'last_update': self.last_update.get(symbol),
            'atr': self.atr_values.get(symbol, 0),
            'bollinger_bands': self.bollinger_bands.get(symbol, {}),
            'volume_24h': self.volume_24h.get(symbol, 0),
            'has_volume_spike': self.volume_spikes.get(symbol, False),
            'spread': self.bid_ask_spread.get(symbol, 0),
            'order_book': self.order_books.get(symbol, {}),
            'price_history_length': len(self.price_history.get(symbol, []))
        }

    def get_top_movers(self, n: int = 10) -> List[Dict]:
        """
        Get top price movers.

        Args:
            n: Number of top movers to return

        Returns:
            List of top mover dicts
        """
        movers = []

        for symbol in self.active_symbols:
            if symbol in self.price_history and len(self.price_history[symbol]) >= 10:
                prices = list(self.price_history[symbol])
                price_change = (prices[-1] - prices[0]) / prices[0] * 100

                movers.append({
                    'symbol': symbol,
                    'price': prices[-1],
                    'change_pct': price_change,
                    'volume': self.volume_24h.get(symbol, 0)
                })

        # Sort by absolute price change
        movers.sort(key=lambda x: abs(x['change_pct']), reverse=True)

        return movers[:n]

    def get_statistics(self) -> Dict:
        """Get streaming statistics."""
        return {
            'active_symbols': len(self.active_symbols),
            'total_updates': self.total_updates,
            'updates_per_second': round(self.updates_per_second, 2),
            'symbols_with_prices': len(self.current_prices),
            'symbols_with_order_books': len(self.order_books),
            'symbols_with_volatility': len(self.atr_values),
            'is_streaming': self.is_streaming,
            'uptime': str(datetime.now() - self.start_time) if self.start_time else '0:00:00'
        }


# Global instance management
_market_data_service: Optional[MarketDataService] = None


async def get_market_data_service(testnet: bool = True) -> MarketDataService:
    """
    Get or create global market data service instance.

    Args:
        testnet: Use testnet (default: True)

    Returns:
        MarketDataService instance
    """
    global _market_data_service

    if _market_data_service is None:
        _market_data_service = MarketDataService(testnet=testnet)
        await _market_data_service.connect()

    return _market_data_service