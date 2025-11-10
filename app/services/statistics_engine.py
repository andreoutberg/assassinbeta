"""
Statistical Learning Engine - THE BRAIN

Learns optimal TP/SL levels, trailing stop parameters, and sentiment correlation
from historical trade data. **NOTHING IS HARDCODED** - all parameters are calculated
from actual historical performance.

Algorithm:
1. Collect all completed trades for an asset
2. Test different % levels (0.5%, 0.75%, 1.0%, 1.25%, ..., 10%)
3. Calculate what % of trades hit each level
4. Find the level that achieves target hit rate:
   - TP1: 80-90% hit rate (high probability)
   - TP2: 50-60% hit rate (medium probability)
   - TP3: 30-40% hit rate (stretch target)
5. Test SL strategies (p90/p95/p99 * 1.0x-1.3x buffer) and pick best:
   - Minimize false stops (stopping out winners)
   - Maximize risk/reward ratio
   - Score = R:R - (false_stop_rate * 10)
6. Compare trailing vs static stop performance
7. Analyze sentiment correlation with win rates
"""
import numpy as np
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime
import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import TradeSetup, AssetStatistics, TradePriceSample

logger = logging.getLogger(__name__)


class StatisticsEngine:
    """
    Learn optimal trading parameters from historical data

    This is the core intelligence - everything is data-driven.
    """

    # Target hit rates for each TP level
    TP1_TARGET_HIT_RATE = 0.85  # 85% - high probability
    TP2_TARGET_HIT_RATE = 0.55  # 55% - medium probability
    TP3_TARGET_HIT_RATE = 0.35  # 35% - stretch target

    # Minimum trades required for confident learning
    MIN_TRADES_FOR_LEARNING = 10
    MIN_TRADES_FOR_HIGH_CONFIDENCE = 30

    def __init__(self):
        pass

    async def update_asset_statistics(self, symbol: str, db: AsyncSession):
        """
        Recalculate all statistics for an asset after a new trade completes

        This is called after EVERY trade completion to keep learning fresh.
        """
        logger.info(f"📊 Recalculating statistics for {symbol}...")

        # Load all completed trades
        trades = await self._load_completed_trades(symbol, db)

        if len(trades) < 3:
            logger.warning(f"⚠️ Only {len(trades)} trades for {symbol} - insufficient data")
            return

        # Get or create statistics record
        stats = await self._get_or_create_stats(symbol, db)

        # Update sample size - COUNT SIGNALS NOT TRADES
        # Count UNIQUE test_group_id across all directions
        # This ensures 3 parallel trades = 1 signal, 1 new trade = 1 signal
        all_signals = set()
        long_signals = set()
        short_signals = set()
        
        for trade in trades:
            # Use test_group_id if available, else use trade ID (old trades)
            signal_id = trade.test_group_id if trade.test_group_id else f"trade_{trade.id}"
            all_signals.add(signal_id)
            
            if trade.direction == "LONG":
                long_signals.add(signal_id)
            else:  # SHORT
                short_signals.add(signal_id)
        
        stats.total_setups = len(all_signals)
        stats.completed_setups = len(all_signals)
        stats.completed_longs = len(long_signals)
        stats.completed_shorts = len(short_signals)
        
        logger.info(f"📊 {symbol}: {stats.completed_longs} LONG signals, {stats.completed_shorts} SHORT signals")

        # Calculate TP hit rates
        await self._calculate_tp_hit_rates(trades, stats)

        # Calculate time to target (median minutes)
        await self._calculate_time_to_target(trades, stats)

        # Calculate drawdown/profit percentiles
        await self._calculate_drawdown_percentiles(trades, stats)
        await self._calculate_profit_percentiles(trades, stats)

        # **THE KEY FUNCTION** - Learn optimal TP levels from hit rate analysis
        await self._learn_optimal_tp_levels(trades, stats)

        # Learn optimal SL from drawdown percentiles
        await self._learn_optimal_sl(trades, stats)

        # Calculate risk/reward ratio
        await self._calculate_risk_reward(stats)

        # Compare trailing vs static stops
        await self._analyze_trailing_stops(trades, stats)

        # Analyze sentiment correlation
        await self._analyze_sentiment_correlation(trades, stats)

        # Build percentile hit data curve
        await self._build_percentile_hit_curve(trades, stats)

        # Update metadata
        stats.last_calculation_at = datetime.utcnow()
        stats.calculation_count = (stats.calculation_count or 0) + 1

        await db.commit()

        logger.info(f"✅ Statistics updated for {symbol}: TP1={stats.optimal_tp1_pct}% TP2={stats.optimal_tp2_pct}% TP3={stats.optimal_tp3_pct}% SL={stats.optimal_sl_pct}%")

    async def _load_completed_trades(self, symbol: str, db: AsyncSession) -> List[TradeSetup]:
        """Load all completed trades for analysis"""
        result = await db.execute(
            select(TradeSetup)
            .where(TradeSetup.symbol == symbol)
            .where(TradeSetup.status == 'completed')
            .order_by(TradeSetup.completed_at.desc())
        )
        return result.scalars().all()

    async def _get_or_create_stats(self, symbol: str, db: AsyncSession) -> AssetStatistics:
        """Get existing stats or create new record"""
        result = await db.execute(
            select(AssetStatistics).where(AssetStatistics.symbol == symbol)
        )
        stats = result.scalar_one_or_none()

        if not stats:
            stats = AssetStatistics(symbol=symbol)
            db.add(stats)
            await db.commit()
            await db.refresh(stats)

        return stats

    async def _calculate_tp_hit_rates(self, trades: List[TradeSetup], stats: AssetStatistics):
        """Calculate what % of trades hit each TP level"""
        tp1_hits = sum(1 for t in trades if t.tp1_hit)
        tp2_hits = sum(1 for t in trades if t.tp2_hit)
        tp3_hits = sum(1 for t in trades if t.tp3_hit)

        stats.tp1_hit_rate = Decimal(str(tp1_hits / len(trades))) if trades else None
        stats.tp2_hit_rate = Decimal(str(tp2_hits / len(trades))) if trades else None
        stats.tp3_hit_rate = Decimal(str(tp3_hits / len(trades))) if trades else None

        # Win rate = hit any TP before SL
        winners = sum(1 for t in trades if t.tp1_hit or t.tp2_hit or t.tp3_hit)
        stats.win_rate = Decimal(str(winners / len(trades))) if trades else None

    async def _calculate_time_to_target(self, trades: List[TradeSetup], stats: AssetStatistics):
        """Calculate median time to reach each TP"""
        tp1_times = [t.tp1_time_minutes for t in trades if t.tp1_hit and t.tp1_time_minutes]
        tp2_times = [t.tp2_time_minutes for t in trades if t.tp2_hit and t.tp2_time_minutes]
        tp3_times = [t.tp3_time_minutes for t in trades if t.tp3_hit and t.tp3_time_minutes]

        stats.tp1_median_minutes = int(np.median(tp1_times)) if tp1_times else None
        stats.tp2_median_minutes = int(np.median(tp2_times)) if tp2_times else None
        stats.tp3_median_minutes = int(np.median(tp3_times)) if tp3_times else None

    async def _calculate_drawdown_percentiles(self, trades: List[TradeSetup], stats: AssetStatistics):
        """Calculate drawdown percentiles (risk analysis)"""
        drawdowns = [float(t.max_drawdown_pct) for t in trades if t.max_drawdown_pct is not None]

        if not drawdowns:
            return

        stats.avg_max_drawdown_pct = Decimal(str(np.mean(drawdowns)))
        stats.p50_max_drawdown_pct = Decimal(str(np.percentile(drawdowns, 50)))
        stats.p75_max_drawdown_pct = Decimal(str(np.percentile(drawdowns, 75)))
        stats.p90_max_drawdown_pct = Decimal(str(np.percentile(drawdowns, 90)))
        stats.p95_max_drawdown_pct = Decimal(str(np.percentile(drawdowns, 95)))  # Worst case

    async def _calculate_profit_percentiles(self, trades: List[TradeSetup], stats: AssetStatistics):
        """Calculate profit excursion percentiles"""
        profits = [float(t.max_profit_pct) for t in trades if t.max_profit_pct is not None]

        if not profits:
            return

        stats.avg_max_profit_pct = Decimal(str(np.mean(profits)))
        stats.p50_max_profit_pct = Decimal(str(np.percentile(profits, 50)))
        stats.p75_max_profit_pct = Decimal(str(np.percentile(profits, 75)))
        stats.p90_max_profit_pct = Decimal(str(np.percentile(profits, 90)))

    async def _learn_optimal_tp_levels(self, trades: List[TradeSetup], stats: AssetStatistics):
        """
        **THE KEY ALGORITHM** - Learn optimal TP levels from historical data

        Process:
        1. Test different % levels (0.25%, 0.5%, 0.75%, 1.0%, ..., 10%)
        2. For each level, calculate: "What % of trades reached this profit?"
        3. Find the % level that hits our target rate (85% for TP1, 55% for TP2, etc.)

        Example:
        - 98% of BTCUSDT trades hit 0.5%
        - 92% hit 1.0%
        - 85% hit 1.25% ← USE THIS FOR TP1 (target = 85%)
        - 78% hit 1.5%
        - 55% hit 2.5% ← USE THIS FOR TP2 (target = 55%)
        - 35% hit 4.0% ← USE THIS FOR TP3 (target = 35%)
        """
        # Test levels from 0.25% to 10% in 0.25% increments
        test_levels = np.arange(0.25, 10.0, 0.25)

        hit_rates = {}
        for level in test_levels:
            # Count how many trades reached this profit level
            hits = sum(1 for t in trades if t.max_profit_pct and float(t.max_profit_pct) >= level)
            hit_rate = hits / len(trades)
            hit_rates[level] = hit_rate

        # Find optimal TP1 (target: 85% hit rate)
        tp1_level, tp1_confidence = self._find_closest_level(
            hit_rates, self.TP1_TARGET_HIT_RATE
        )
        if tp1_level:
            stats.optimal_tp1_pct = Decimal(str(tp1_level))
            stats.optimal_tp1_confidence = Decimal(str(tp1_confidence))

        # Find optimal TP2 (target: 55% hit rate)
        tp2_level, tp2_confidence = self._find_closest_level(
            hit_rates, self.TP2_TARGET_HIT_RATE
        )
        if tp2_level:
            stats.optimal_tp2_pct = Decimal(str(tp2_level))
            stats.optimal_tp2_confidence = Decimal(str(tp2_confidence))

        # Find optimal TP3 (target: 35% hit rate)
        tp3_level, tp3_confidence = self._find_closest_level(
            hit_rates, self.TP3_TARGET_HIT_RATE
        )
        if tp3_level:
            stats.optimal_tp3_pct = Decimal(str(tp3_level))
            stats.optimal_tp3_confidence = Decimal(str(tp3_confidence))

        logger.info(f"📈 Learned TP levels: TP1={tp1_level}% (conf={tp1_confidence:.2f}), TP2={tp2_level}%, TP3={tp3_level}%")

    def _find_closest_level(self, hit_rates: Dict[float, float], target_rate: float) -> Tuple[Optional[float], float]:
        """
        Find the % level that gets closest to our target hit rate

        Returns: (level, confidence_score)
        """
        if not hit_rates:
            return None, 0.0

        # Find level with hit rate closest to target
        closest_level = None
        closest_diff = float('inf')

        for level, rate in hit_rates.items():
            diff = abs(rate - target_rate)
            if diff < closest_diff:
                closest_diff = diff
                closest_level = level

        # Confidence = how close we got to target (1.0 = perfect match)
        confidence = 1.0 - min(closest_diff / target_rate, 1.0)

        return closest_level, confidence

    async def _learn_optimal_sl(self, trades: List[TradeSetup], stats: AssetStatistics):
        """
        **DATA-DRIVEN SL OPTIMIZATION** (Nothing Hardcoded!)

        Test different SL strategies and pick the best one based on:
        1. Minimize false stops (trades that would have recovered)
        2. Maximize risk/reward ratio (TP1 / SL)
        3. Protect capital on true losers

        Algorithm:
        - Test percentiles: p90, p95, p99 of drawdown
        - Test buffer multipliers: 1.0x, 1.1x, 1.2x, 1.3x, 1.5x
        - For each combination, simulate: "If we used this SL, what would have happened?"
        - Score each strategy: score = R:R ratio - (false_stop_rate * 10)
        - Pick highest scoring strategy

        Example:
        - p90 * 1.1 = -1.8%: 15% false stops, R:R=2.1 → score = 2.1 - 1.5 = 0.6
        - p95 * 1.2 = -2.3%: 5% false stops, R:R=1.6 → score = 1.6 - 0.5 = 1.1 ← BEST
        - p99 * 1.3 = -3.0%: 2% false stops, R:R=1.2 → score = 1.2 - 0.2 = 1.0
        """
        drawdowns = [float(t.max_drawdown_pct) for t in trades if t.max_drawdown_pct is not None]

        if not drawdowns or len(trades) < self.MIN_TRADES_FOR_LEARNING:
            # Not enough data - use conservative default
            stats.optimal_sl_pct = Decimal('-2.5')
            stats.optimal_sl_confidence = Decimal('0.3')
            logger.warning(f"⚠️ Insufficient data for SL learning ({len(trades)} trades), using conservative -2.5%")
            return

        # Calculate percentiles
        p90_dd = np.percentile(drawdowns, 90)
        p95_dd = np.percentile(drawdowns, 95)
        p99_dd = np.percentile(drawdowns, 99)

        # Test different strategies
        test_strategies = [
            ('p90', 1.0, p90_dd * 1.0),
            ('p90', 1.1, p90_dd * 1.1),
            ('p90', 1.2, p90_dd * 1.2),
            ('p95', 1.0, p95_dd * 1.0),
            ('p95', 1.1, p95_dd * 1.1),
            ('p95', 1.2, p95_dd * 1.2),
            ('p95', 1.3, p95_dd * 1.3),
            ('p99', 1.0, p99_dd * 1.0),
            ('p99', 1.1, p99_dd * 1.1),
            ('p99', 1.2, p99_dd * 1.2),
        ]

        best_strategy = None
        best_score = -float('inf')

        for percentile_name, buffer, sl_level in test_strategies:
            # Simulate: What would happen with this SL?
            false_stops = 0  # Trades that hit SL but would have recovered to hit a TP
            true_stops = 0   # Trades that hit SL and would NOT have recovered

            for trade in trades:
                max_dd = float(trade.max_drawdown_pct) if trade.max_drawdown_pct else 0

                # Would this SL have been hit?
                if max_dd <= sl_level:
                    # SL would have been hit
                    # Check if trade eventually won (hit a TP)
                    if trade.tp1_hit or trade.tp2_hit or trade.tp3_hit:
                        false_stops += 1  # Bad: Stopped out a winner
                    else:
                        true_stops += 1   # Good: Stopped out a loser

            # Calculate false stop rate
            total_stops = false_stops + true_stops
            false_stop_rate = false_stops / len(trades) if len(trades) > 0 else 0

            # Calculate risk/reward ratio (use TP1 as baseline)
            rr_ratio = abs(float(stats.optimal_tp1_pct) / sl_level) if stats.optimal_tp1_pct and sl_level != 0 else 0

            # Calculate expected value (EV) = profitability metric
            # Winners hit TP1 on average, losers hit SL
            win_rate = stats.tp1_hit_rate if stats.tp1_hit_rate else 0.5  # Default 50% if unknown
            loss_rate = 1 - float(win_rate)
            avg_win = abs(float(stats.optimal_tp1_pct)) if stats.optimal_tp1_pct else 1.0
            avg_loss = abs(sl_level)

            # EV = (win_rate * avg_win) - (loss_rate * avg_loss)
            # Positive EV = profitable setup
            expected_value = (float(win_rate) * avg_win) - (loss_rate * avg_loss)

            # Score this strategy
            # PRIMARY: Expected value (profitability)
            # SECONDARY: Minimize false stops
            # R:R must be >= 1.2:1 minimum (disqualify bad setups)
            if rr_ratio < 1.2:
                score = -999  # Disqualify: R:R too low
            else:
                score = (expected_value * 100) - (false_stop_rate * 10)

            logger.debug(
                f"  Test SL: {percentile_name} * {buffer} = {sl_level:.2f}% | "
                f"EV: {expected_value:+.3f}% | R:R: {rr_ratio:.2f} | "
                f"False stops: {false_stop_rate:.1%} | Score: {score:.2f}"
            )

            if score > best_score:
                best_score = score
                best_strategy = (percentile_name, buffer, sl_level, false_stop_rate, rr_ratio, expected_value)

        if best_strategy:
            percentile_name, buffer, optimal_sl, false_stop_rate, rr_ratio, expected_value = best_strategy

            stats.optimal_sl_pct = Decimal(str(optimal_sl))

            # Store profitability metrics (THE MOST IMPORTANT!)
            stats.expected_value_pct = Decimal(str(expected_value))
            stats.is_profitable_setup = expected_value > 0

            # Confidence based on sample size, false stop rate, AND profitability
            is_profitable = expected_value > 0
            if len(trades) >= self.MIN_TRADES_FOR_HIGH_CONFIDENCE and false_stop_rate < 0.10 and is_profitable:
                stats.optimal_sl_confidence = Decimal('0.9')
            elif len(trades) >= self.MIN_TRADES_FOR_LEARNING and false_stop_rate < 0.15 and is_profitable:
                stats.optimal_sl_confidence = Decimal('0.7')
            elif is_profitable:
                stats.optimal_sl_confidence = Decimal('0.5')
            else:
                stats.optimal_sl_confidence = Decimal('0.3')  # Low confidence if not profitable

            logger.info(
                f"🛑 LEARNED SL: {optimal_sl:.2f}% ({percentile_name} * {buffer}) | "
                f"EV: {expected_value:+.3f}% {'✅ PROFITABLE' if expected_value > 0 else '❌ UNPROFITABLE'} | "
                f"R:R: {rr_ratio:.2f} | False stops: {false_stop_rate:.1%} | "
                f"Score: {best_score:.2f}"
            )
        else:
            # Fallback
            stats.optimal_sl_pct = Decimal('-2.5')
            stats.optimal_sl_confidence = Decimal('0.3')
            logger.warning("⚠️ No optimal SL found, using conservative -2.5%")

    async def _calculate_risk_reward(self, stats: AssetStatistics):
        """Calculate risk/reward ratio (TP1 / SL)"""
        if stats.optimal_tp1_pct and stats.optimal_sl_pct:
            rr_ratio = abs(float(stats.optimal_tp1_pct) / float(stats.optimal_sl_pct))
            stats.avg_risk_reward_ratio = Decimal(str(rr_ratio))

    async def _analyze_trailing_stops(self, trades: List[TradeSetup], stats: AssetStatistics):
        """
        Compare trailing stop vs static stop performance

        A/B test: Which approach has better win rate?
        """
        trailing_trades = [t for t in trades if t.use_trailing_stop]
        static_trades = [t for t in trades if not t.use_trailing_stop]

        if trailing_trades:
            trailing_winners = sum(1 for t in trailing_trades if t.final_outcome in ['tp1', 'tp2', 'tp3'])
            stats.trailing_stop_win_rate = Decimal(str(trailing_winners / len(trailing_trades)))

        if static_trades:
            static_winners = sum(1 for t in static_trades if t.final_outcome in ['tp1', 'tp2', 'tp3'])
            stats.static_stop_win_rate = Decimal(str(static_winners / len(static_trades)))

        # Recommend trailing stops if they perform better
        if stats.trailing_stop_win_rate and stats.static_stop_win_rate:
            if float(stats.trailing_stop_win_rate) > float(stats.static_stop_win_rate) * 1.05:  # 5% better
                stats.trailing_stop_recommended = True
                logger.info(f"✅ Trailing stops recommended ({stats.trailing_stop_win_rate:.1%} vs {stats.static_stop_win_rate:.1%})")
            else:
                stats.trailing_stop_recommended = False

        # Learn optimal trailing parameters
        if trailing_trades:
            # Find median trailing distance for winning trades
            winning_trailing = [t for t in trailing_trades if t.final_outcome in ['tp1', 'tp2', 'tp3']]
            if winning_trailing:
                distances = [float(t.trailing_stop_distance_pct) for t in winning_trailing if t.trailing_stop_distance_pct]
                activations = [float(t.trailing_stop_activation_pct) for t in winning_trailing if t.trailing_stop_activation_pct]

                if distances:
                    stats.optimal_trailing_distance_pct = Decimal(str(np.median(distances)))
                if activations:
                    stats.optimal_trailing_activation_pct = Decimal(str(np.median(activations)))

    async def _analyze_sentiment_correlation(self, trades: List[TradeSetup], stats: AssetStatistics):
        """
        Analyze if news sentiment correlates with trade outcomes

        Question: Do trades with positive sentiment at entry have higher win rates?
        """
        trades_with_sentiment = [t for t in trades if t.news_sentiment_score is not None]

        if len(trades_with_sentiment) < 10:
            return  # Need enough data

        winners = [t for t in trades_with_sentiment if t.final_outcome in ['tp1', 'tp2', 'tp3']]
        losers = [t for t in trades_with_sentiment if t.final_outcome in ['sl', 'timeout']]

        if winners:
            avg_winner_sentiment = np.mean([float(t.news_sentiment_score) for t in winners])
            stats.avg_sentiment_winners = Decimal(str(avg_winner_sentiment))

        if losers:
            avg_loser_sentiment = np.mean([float(t.news_sentiment_score) for t in losers])
            stats.avg_sentiment_losers = Decimal(str(avg_loser_sentiment))

        # Statistical significance test (simple threshold for now)
        if stats.avg_sentiment_winners and stats.avg_sentiment_losers:
            sentiment_diff = abs(float(stats.avg_sentiment_winners) - float(stats.avg_sentiment_losers))
            if sentiment_diff > 0.15:  # 15% difference
                stats.sentiment_matters = True
                logger.info(f"📰 Sentiment correlation found! Winners: {stats.avg_sentiment_winners:.2f}, Losers: {stats.avg_sentiment_losers:.2f}")

    async def _build_percentile_hit_curve(self, trades: List[TradeSetup], stats: AssetStatistics):
        """
        Build complete percentile hit curve for visualization

        Example output:
        {
          "0.25": 0.99,  // 99% of trades hit 0.25%
          "0.50": 0.96,  // 96% hit 0.5%
          "1.00": 0.92,  // 92% hit 1.0%
          "1.25": 0.85,  // 85% hit 1.25%
          ...
        }
        """
        test_levels = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0]

        curve = {}
        for level in test_levels:
            hits = sum(1 for t in trades if t.max_profit_pct and float(t.max_profit_pct) >= level)
            hit_rate = hits / len(trades)
            curve[str(level)] = round(hit_rate, 4)

        stats.percentile_hit_data = curve

    async def calculate_bootstrap_confidence_intervals(
        self,
        trades: List[TradeSetup],
        stats: AssetStatistics,
        n_bootstrap: int = 1000,
        confidence_level: float = 0.95
    ):
        """
        Calculate bootstrap confidence intervals for learned levels

        **CRITICAL**: Tells us how RELIABLE the learned levels are

        Algorithm:
        1. Resample trades with replacement (bootstrap)
        2. Calculate TP1 level for each bootstrap sample
        3. Get 95% confidence interval from distribution

        Example:
        - TP1 learned: 1.25%
        - 95% CI: [1.15%, 1.35%]
        - Interpretation: We're 95% confident true TP1 is between 1.15-1.35%

        Stores in database:
        - optimal_tp1_confidence_lower
        - optimal_tp1_confidence_upper
        """
        if len(trades) < 30:
            logger.warning(f"⚠️ Only {len(trades)} trades - bootstrap CI not reliable")
            return

        logger.info(f"🔬 Calculating bootstrap CIs ({n_bootstrap} samples)...")

        # TP1 confidence interval
        tp1_bootstrap_samples = []
        for _ in range(n_bootstrap):
            # Resample with replacement
            resample = np.random.choice(trades, size=len(trades), replace=True)

            # Calculate TP1 for this sample
            test_levels = np.arange(0.25, 10.0, 0.25)
            hit_rates = {}
            for level in test_levels:
                hits = sum(1 for t in resample if t.max_profit_pct and float(t.max_profit_pct) >= level)
                hit_rate = hits / len(resample)
                hit_rates[level] = hit_rate

            # Find TP1 (closest to 85% target)
            tp1_level, _ = self._find_closest_level(hit_rates, self.TP1_TARGET_HIT_RATE)
            tp1_bootstrap_samples.append(tp1_level)

        # Calculate 95% CI
        alpha = 1 - confidence_level
        ci_lower = np.percentile(tp1_bootstrap_samples, alpha / 2 * 100)
        ci_upper = np.percentile(tp1_bootstrap_samples, (1 - alpha / 2) * 100)

        # Store in database
        stats.optimal_tp1_confidence_lower = Decimal(str(ci_lower))
        stats.optimal_tp1_confidence_upper = Decimal(str(ci_upper))

        logger.info(
            f"📊 TP1 Bootstrap CI: {ci_lower:.2f}% - {ci_upper:.2f}% "
            f"(learned: {stats.optimal_tp1_pct}%)"
        )

        # Calculate confidence width (narrow = high confidence)
        ci_width = ci_upper - ci_lower
        if ci_width < 0.5:
            stats.optimal_tp1_confidence = Decimal('0.95')  # High confidence
        elif ci_width < 1.0:
            stats.optimal_tp1_confidence = Decimal('0.75')  # Medium confidence
        else:
            stats.optimal_tp1_confidence = Decimal('0.50')  # Low confidence

    async def validate_learned_levels(
        self,
        symbol: str,
        stats: AssetStatistics,
        db: AsyncSession
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate learned levels before using them in live trades

        **CRITICAL SAFETY FEATURE**

        Checks:
        1. Sufficient sample size (>= 30 trades)
        2. Data is fresh (last trade < 30 days ago)
        3. Win rate is reasonable (>= 40%)
        4. Expected Value is positive
        5. R:R ratio >= 1.2:1
        6. Bootstrap CI is not too wide (confidence >= 0.5)

        Returns:
            (is_valid, reason_if_invalid)

        Usage:
            Call this BEFORE using learned levels for new trades
        """
        # Check 1: Sample size
        if stats.completed_setups < self.MIN_TRADES_FOR_HIGH_CONFIDENCE:
            return False, f"Insufficient sample size: {stats.completed_setups} trades (need >= 30)"

        # Check 2: Data freshness
        result = await db.execute(
            select(TradeSetup.completed_at)
            .where(TradeSetup.symbol == symbol)
            .where(TradeSetup.status == 'completed')
            .order_by(TradeSetup.completed_at.desc())
            .limit(1)
        )
        last_trade_date = result.scalar_one_or_none()

        if last_trade_date:
            days_since_last = (datetime.utcnow() - last_trade_date).days
            if days_since_last > 30:
                return False, f"Data is stale: Last trade was {days_since_last} days ago"

        # Check 3: Win rate
        if stats.tp1_hit_rate and float(stats.tp1_hit_rate) < 0.40:
            return False, f"Win rate too low: {stats.tp1_hit_rate:.2%} (need >= 40%)"

        # Check 4: Expected Value
        if stats.expected_value_pct and float(stats.expected_value_pct) < 0:
            return False, f"Negative Expected Value: {stats.expected_value_pct:.2%}"

        # Check 5: Risk/Reward ratio
        if stats.avg_risk_reward_ratio and float(stats.avg_risk_reward_ratio) < 1.2:
            return False, f"R:R too low: {stats.avg_risk_reward_ratio:.2f}:1 (need >= 1.2:1)"

        # Check 6: Confidence (if bootstrap CI calculated)
        if stats.optimal_tp1_confidence and float(stats.optimal_tp1_confidence) < 0.5:
            return False, f"Low confidence: {stats.optimal_tp1_confidence:.2%} (CI too wide)"

        # All checks passed
        return True, None

    async def get_asset_statistics(self, symbol: str, db: AsyncSession) -> Optional[AssetStatistics]:
        """
        Get statistics for an asset (with validation)

        Returns statistics only if they pass validation.
        Returns None if invalid or don't exist.

        Call this when getting learned levels for a new trade.
        """
        result = await db.execute(
            select(AssetStatistics).where(AssetStatistics.symbol == symbol)
        )
        stats = result.scalar_one_or_none()

        if not stats:
            return None

        # Validate before returning
        is_valid, reason = await self.validate_learned_levels(symbol, stats, db)

        if not is_valid:
            logger.warning(f"⚠️ {symbol} learned levels invalid: {reason}")
            return None

        return stats


# Convenience function for external use
async def update_asset_statistics(symbol: str, db: AsyncSession):
    """Update statistics for an asset (called after trade completion)"""
    engine = StatisticsEngine()
    await engine.update_asset_statistics(symbol, db)
