"""
Signal Generator for Real-time Trading Signals

Generates LONG/SHORT signals from real Bybit market data, integrates with
signal quality analyzer, and persists signals to PostgreSQL.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from decimal import Decimal
import numpy as np
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import AsyncSessionLocal
from app.database.models import TradeSetup, AssetStatistics
from app.services.market_data_service import MarketDataService, get_market_data_service
from app.services.signal_quality_analyzer import SignalQualityAnalyzer
from app.config import settings

logger = logging.getLogger(__name__)


class SignalGenerator:
    """
    Generate trading signals from real-time market data with quality analysis.

    Features:
    - Breakout detection using Bollinger Bands
    - Momentum analysis with volume confirmation
    - Integration with signal quality analyzer for baseline validation
    - PostgreSQL persistence with proper async handling
    - 55%+ baseline win rate targeting
    """

    def __init__(self, market_data_service: MarketDataService):
        """
        Initialize signal generator.

        Args:
            market_data_service: MarketDataService instance for real-time data
        """
        self.market_data = market_data_service
        self.active_signals: Dict[str, Dict] = {}
        self.signal_history: List[Dict] = []
        self.total_signals_generated = 0
        self.signals_above_baseline = 0

        # Signal generation thresholds
        self.MIN_CONFIDENCE = 0.60  # Minimum confidence for signal generation
        self.MIN_VOLUME_SPIKE = 2.0  # Minimum volume multiplier
        self.MIN_MOMENTUM = 0.5  # Minimum price change %
        self.MAX_SPREAD = 0.15  # Maximum bid-ask spread %

        # Baseline targeting
        self.TARGET_WIN_RATE = 55.0  # Minimum baseline win rate target
        self.quality_check_enabled = True

    async def start_signal_generation(self, symbols: List[str]):
        """
        Start generating signals for specified symbols.

        Args:
            symbols: List of trading pairs to monitor
        """
        logger.info(f"🚀 Starting signal generation for {len(symbols)} symbols")

        # Register callback with market data service
        self.market_data.add_signal_callback(self._process_market_signal)

        # Start background tasks
        tasks = [
            asyncio.create_task(self._monitor_signal_quality()),
            asyncio.create_task(self._cleanup_old_signals()),
            asyncio.create_task(self._calculate_statistics())
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Signal generation tasks cancelled")
        except Exception as e:
            logger.error(f"Signal generation error: {e}")

    async def _process_market_signal(self, symbol: str, market_signal: Dict):
        """
        Process market signal and generate trading signal if conditions met.

        Args:
            symbol: Trading pair
            market_signal: Signal from market data service
        """
        try:
            # Enhanced signal validation
            if not self._validate_market_conditions(market_signal):
                return

            # Check if we already have an active signal for this symbol
            if symbol in self.active_signals:
                last_signal_time = self.active_signals[symbol].get('timestamp')
                if last_signal_time and (datetime.now() - last_signal_time).seconds < 300:  # 5 min cooldown
                    return

            # Generate enhanced trading signal
            trading_signal = await self._generate_trading_signal(symbol, market_signal)

            if trading_signal:
                # Quality check with signal analyzer
                if self.quality_check_enabled:
                    quality_check = await self._check_signal_quality(trading_signal)
                    if not quality_check['passes_baseline']:
                        logger.info(f"📉 Signal rejected for {symbol}: Below baseline (WR: {quality_check['win_rate']:.1f}%)")
                        return

                # Persist to database
                await self._save_signal_to_db(trading_signal)

                # Update tracking
                self.active_signals[symbol] = trading_signal
                self.signal_history.append(trading_signal)
                self.total_signals_generated += 1

                if trading_signal.get('baseline_win_rate', 0) >= self.TARGET_WIN_RATE:
                    self.signals_above_baseline += 1

                logger.info(
                    f"✅ Signal generated: {symbol} {trading_signal['direction']} "
                    f"@ {trading_signal['entry_price']:.8f} "
                    f"(Confidence: {trading_signal['confidence']:.2f})"
                )

        except Exception as e:
            logger.error(f"Error processing market signal for {symbol}: {e}")

    def _validate_market_conditions(self, market_signal: Dict) -> bool:
        """
        Validate market conditions for signal generation.

        Args:
            market_signal: Market signal dict

        Returns:
            True if conditions are favorable
        """
        # Check confidence
        if market_signal.get('confidence', 0) < self.MIN_CONFIDENCE:
            return False

        # Check spread
        if market_signal.get('spread', float('inf')) > self.MAX_SPREAD:
            return False

        # Check if there are enough positive signals
        signals = market_signal.get('signals', [])
        if len(signals) < 2:  # Need at least 2 confirming signals
            return False

        return True

    async def _generate_trading_signal(self, symbol: str, market_signal: Dict) -> Optional[Dict]:
        """
        Generate enhanced trading signal with entry/exit levels.

        Args:
            symbol: Trading pair
            market_signal: Market signal from data service

        Returns:
            Trading signal dict or None
        """
        try:
            direction = market_signal['direction']
            entry_price = market_signal['entry_price']
            volatility = market_signal.get('volatility', 0)

            # Calculate dynamic TP/SL based on volatility
            if volatility > 0:
                # ATR-based levels
                tp1_distance = volatility * 1.5
                tp2_distance = volatility * 2.5
                tp3_distance = volatility * 4.0
                sl_distance = volatility * 1.2
            else:
                # Default levels
                tp1_distance = entry_price * 0.015  # 1.5%
                tp2_distance = entry_price * 0.025  # 2.5%
                tp3_distance = entry_price * 0.040  # 4.0%
                sl_distance = entry_price * 0.012   # 1.2%

            # Calculate actual prices
            if direction == 'LONG':
                tp1_price = entry_price + tp1_distance
                tp2_price = entry_price + tp2_distance
                tp3_price = entry_price + tp3_distance
                sl_price = entry_price - sl_distance
            else:  # SHORT
                tp1_price = entry_price - tp1_distance
                tp2_price = entry_price - tp2_distance
                tp3_price = entry_price - tp3_distance
                sl_price = entry_price + sl_distance

            # Calculate percentages
            tp1_pct = abs(tp1_price - entry_price) / entry_price * 100
            tp2_pct = abs(tp2_price - entry_price) / entry_price * 100
            tp3_pct = abs(tp3_price - entry_price) / entry_price * 100
            sl_pct = -abs(sl_price - entry_price) / entry_price * 100

            # Risk/Reward ratio
            risk_reward = tp1_pct / abs(sl_pct)

            # Build comprehensive signal
            signal = {
                'symbol': symbol,
                'direction': direction,
                'entry_price': entry_price,
                'entry_timestamp': datetime.now(),
                'confidence': market_signal['confidence'],
                'setup_type': self._determine_setup_type(market_signal['signals']),
                'signals': market_signal['signals'],

                # TP/SL levels
                'tp1_price': tp1_price,
                'tp1_pct': tp1_pct,
                'tp2_price': tp2_price,
                'tp2_pct': tp2_pct,
                'tp3_price': tp3_price,
                'tp3_pct': tp3_pct,
                'sl_price': sl_price,
                'sl_pct': sl_pct,

                # Risk management
                'risk_reward_ratio': risk_reward,
                'position_size_usd': 1000,  # Default position size
                'leverage': 5.0,  # Default leverage

                # Market context
                'volatility': volatility,
                'volume_24h': market_signal.get('volume_24h', 0),
                'spread': market_signal.get('spread', 0),
                'order_book_imbalance': market_signal.get('order_book', {}).get('imbalance', 0),

                # Metadata
                'timestamp': datetime.now(),
                'webhook_source': 'signal_generator',
                'trade_mode': 'paper',  # Always paper for generated signals
            }

            return signal

        except Exception as e:
            logger.error(f"Error generating trading signal for {symbol}: {e}")
            return None

    def _determine_setup_type(self, signals: List[str]) -> str:
        """
        Determine setup type from signal components.

        Args:
            signals: List of signal components

        Returns:
            Setup type string
        """
        if 'BB_BREAKOUT_UP' in signals or 'BB_BREAKOUT_DOWN' in signals:
            return 'breakout'
        elif 'MOMENTUM_UP' in signals or 'MOMENTUM_DOWN' in signals:
            return 'momentum'
        elif 'VOLUME_SPIKE' in signals:
            return 'volume_spike'
        elif 'STRONG_BID_PRESSURE' in signals or 'STRONG_ASK_PRESSURE' in signals:
            return 'order_flow'
        else:
            return 'mixed'

    async def _check_signal_quality(self, signal: Dict) -> Dict:
        """
        Check signal quality against baseline requirements.

        Args:
            signal: Trading signal dict

        Returns:
            Quality check result dict
        """
        try:
            async with AsyncSessionLocal() as db:
                # Analyze signal quality
                quality_analysis = await SignalQualityAnalyzer.analyze_signal(
                    db=db,
                    symbol=signal['symbol'],
                    direction=signal['direction'],
                    webhook_source=signal['webhook_source'],
                    enable_high_wr_mode=True
                )

                # Check baseline requirement
                win_rate = quality_analysis.get('raw_win_rate', 0)
                passes_baseline = win_rate >= self.TARGET_WIN_RATE

                return {
                    'passes_baseline': passes_baseline,
                    'win_rate': win_rate,
                    'confidence_interval': quality_analysis.get('confidence_interval'),
                    'expected_value': quality_analysis.get('expected_value'),
                    'quality_score': quality_analysis.get('quality_score'),
                    'sample_size': quality_analysis.get('sample_size'),
                    'has_edge': quality_analysis.get('has_edge')
                }

        except Exception as e:
            logger.error(f"Error checking signal quality: {e}")
            # Default to allowing signal if quality check fails
            return {'passes_baseline': True, 'win_rate': 0}

    async def _save_signal_to_db(self, signal: Dict):
        """
        Save trading signal to PostgreSQL database.

        Args:
            signal: Trading signal dict
        """
        try:
            async with AsyncSessionLocal() as db:
                # Create trade setup record
                trade_setup = TradeSetup(
                    symbol=signal['symbol'],
                    ccxt_symbol=signal['symbol'],
                    direction=signal['direction'],
                    entry_price=Decimal(str(signal['entry_price'])),
                    entry_timestamp=signal['entry_timestamp'],
                    setup_type=signal['setup_type'],
                    confidence_score=Decimal(str(signal['confidence'])),
                    webhook_source=signal['webhook_source'],
                    trade_mode=signal['trade_mode'],

                    # Position sizing
                    notional_position_usd=Decimal(str(signal['position_size_usd'] * signal['leverage'])),
                    margin_required_usd=Decimal(str(signal['position_size_usd'])),
                    leverage=Decimal(str(signal['leverage'])),
                    risk_reward_ratio=Decimal(str(signal['risk_reward_ratio'])),

                    # Planned levels
                    planned_tp1_price=Decimal(str(signal['tp1_price'])),
                    planned_tp1_pct=Decimal(str(signal['tp1_pct'])),
                    planned_tp2_price=Decimal(str(signal['tp2_price'])),
                    planned_tp2_pct=Decimal(str(signal['tp2_pct'])),
                    planned_tp3_price=Decimal(str(signal['tp3_price'])),
                    planned_tp3_pct=Decimal(str(signal['tp3_pct'])),
                    planned_sl_price=Decimal(str(signal['sl_price'])),
                    planned_sl_pct=Decimal(str(signal['sl_pct'])),

                    # Status
                    status='active'
                )

                db.add(trade_setup)
                await db.commit()

                logger.info(f"💾 Signal saved to database: {signal['symbol']} {signal['direction']}")

                # Update asset statistics
                await self._update_asset_statistics(db, signal['symbol'])

        except Exception as e:
            logger.error(f"Error saving signal to database: {e}")

    async def _update_asset_statistics(self, db: AsyncSession, symbol: str):
        """
        Update asset statistics after new signal.

        Args:
            db: Database session
            symbol: Trading pair
        """
        try:
            # Get or create asset statistics
            stmt = select(AssetStatistics).where(AssetStatistics.symbol == symbol)
            result = await db.execute(stmt)
            asset_stats = result.scalar_one_or_none()

            if not asset_stats:
                asset_stats = AssetStatistics(symbol=symbol)
                db.add(asset_stats)

            # Update counters
            asset_stats.total_setups = (asset_stats.total_setups or 0) + 1
            asset_stats.active_setups = (asset_stats.active_setups or 0) + 1
            asset_stats.last_updated = datetime.now()

            await db.commit()

        except Exception as e:
            logger.error(f"Error updating asset statistics for {symbol}: {e}")

    async def _monitor_signal_quality(self):
        """Monitor and log signal quality metrics."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes

                if self.total_signals_generated > 0:
                    baseline_rate = (self.signals_above_baseline / self.total_signals_generated) * 100

                    logger.info(
                        f"📊 Signal Quality: {self.signals_above_baseline}/{self.total_signals_generated} "
                        f"signals above {self.TARGET_WIN_RATE}% baseline ({baseline_rate:.1f}%)"
                    )

                    # Log active signals
                    if self.active_signals:
                        logger.info(f"Active signals: {list(self.active_signals.keys())}")

            except Exception as e:
                logger.error(f"Error monitoring signal quality: {e}")

    async def _cleanup_old_signals(self):
        """Remove old signals from active tracking."""
        while True:
            try:
                await asyncio.sleep(600)  # Cleanup every 10 minutes

                now = datetime.now()
                expired_symbols = []

                for symbol, signal in self.active_signals.items():
                    signal_time = signal.get('timestamp')
                    if signal_time and (now - signal_time).seconds > 3600:  # 1 hour expiry
                        expired_symbols.append(symbol)

                for symbol in expired_symbols:
                    del self.active_signals[symbol]

                if expired_symbols:
                    logger.info(f"🧹 Cleaned up {len(expired_symbols)} expired signals")

            except Exception as e:
                logger.error(f"Error cleaning up old signals: {e}")

    async def _calculate_statistics(self):
        """Calculate and log signal generation statistics."""
        while True:
            try:
                await asyncio.sleep(3600)  # Calculate every hour

                if self.signal_history:
                    # Calculate statistics
                    total_signals = len(self.signal_history)
                    long_signals = sum(1 for s in self.signal_history if s['direction'] == 'LONG')
                    short_signals = total_signals - long_signals

                    avg_confidence = np.mean([s['confidence'] for s in self.signal_history])
                    avg_risk_reward = np.mean([s['risk_reward_ratio'] for s in self.signal_history])

                    # Setup type distribution
                    setup_types = {}
                    for signal in self.signal_history:
                        setup = signal.get('setup_type', 'unknown')
                        setup_types[setup] = setup_types.get(setup, 0) + 1

                    logger.info(
                        f"📈 Signal Statistics (Last Hour):\n"
                        f"  Total Signals: {total_signals}\n"
                        f"  Long/Short: {long_signals}/{short_signals}\n"
                        f"  Avg Confidence: {avg_confidence:.2f}\n"
                        f"  Avg Risk/Reward: {avg_risk_reward:.2f}\n"
                        f"  Setup Types: {setup_types}"
                    )

                    # Clear old history (keep last 100 signals)
                    if len(self.signal_history) > 100:
                        self.signal_history = self.signal_history[-100:]

            except Exception as e:
                logger.error(f"Error calculating statistics: {e}")

    def get_statistics(self) -> Dict:
        """Get signal generator statistics."""
        baseline_rate = 0
        if self.total_signals_generated > 0:
            baseline_rate = (self.signals_above_baseline / self.total_signals_generated) * 100

        return {
            'total_signals': self.total_signals_generated,
            'signals_above_baseline': self.signals_above_baseline,
            'baseline_achievement_rate': round(baseline_rate, 1),
            'active_signals': len(self.active_signals),
            'history_size': len(self.signal_history),
            'target_win_rate': self.TARGET_WIN_RATE
        }


class SignalAggregator:
    """
    Aggregate signals from multiple sources and rank by quality.
    """

    def __init__(self):
        """Initialize signal aggregator."""
        self.signals: List[Dict] = []
        self.signal_sources: Dict[str, int] = {}

    async def aggregate_signals(self, max_signals: int = 20) -> List[Dict]:
        """
        Get top signals ranked by quality.

        Args:
            max_signals: Maximum number of signals to return

        Returns:
            List of top signals
        """
        # Sort by confidence and risk/reward
        sorted_signals = sorted(
            self.signals,
            key=lambda x: x.get('confidence', 0) * x.get('risk_reward_ratio', 1),
            reverse=True
        )

        return sorted_signals[:max_signals]

    def add_signal(self, signal: Dict):
        """
        Add signal to aggregator.

        Args:
            signal: Signal dict
        """
        self.signals.append(signal)

        # Track source
        source = signal.get('webhook_source', 'unknown')
        self.signal_sources[source] = self.signal_sources.get(source, 0) + 1

        # Keep only recent signals (last 100)
        if len(self.signals) > 100:
            self.signals = self.signals[-100:]