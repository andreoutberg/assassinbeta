"""
Enhanced Signal Quality Analyzer for High-WR Potential Detection

CRITICAL COMPONENT: Validates if trading signals have edge BEFORE optimization.
Includes advanced high-WR potential prediction and early detection capabilities.

Key Enhancements:
- Stricter thresholds for high-WR mode (>62% baseline required)
- Phase II win rate prediction using empirical multipliers
- Early detection after 10 trades with fast-track for exceptional signals
- Consistency tracking with rolling variance and streak analysis

Author: Claude (System Improvement Initiative)
Version: 2.0 - High-WR Enhanced
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import math
import statistics

from app.database.models import TradeSetup
from app.database.signal_quality_models import SignalQuality
from app.config import settings

logger = logging.getLogger(__name__)


class SignalQualityAnalyzer:
    """
    Enhanced analyzer for baseline trades with high-WR potential detection.

    Key Metrics:
    - Raw win rate (without TP/SL constraints)
    - Confidence intervals (Wilson score method)
    - Statistical significance (binomial test)
    - Expected value
    - Quality score (0-100 composite)
    - High-WR potential prediction
    - Consistency tracking
    """

    # Standard thresholds
    MIN_SAMPLE_SIZE = 10  # Minimum trades to analyze
    STRONG_EDGE_THRESHOLD = 60.0  # >60% WR = strong edge
    MODERATE_EDGE_THRESHOLD = 55.0  # 55-60% = moderate edge
    SIGNIFICANCE_LEVEL = 0.05  # p < 0.05 for statistical significance

    # High-WR mode thresholds (stricter)
    HIGH_WR_MIN_BASELINE = 62.0  # Minimum baseline WR for high-WR potential
    HIGH_WR_MAX_CI_WIDTH = 15.0  # Maximum confidence interval width
    HIGH_WR_MIN_EV = 0.5  # Minimum expected value (0.5%)

    # Phase II prediction multipliers (empirical)
    PHASE2_MULTIPLIER_MIN = 1.05  # Conservative multiplier
    PHASE2_MULTIPLIER_MAX = 1.15  # Optimistic multiplier
    PHASE2_MULTIPLIER_TYPICAL = 1.10  # Most common multiplier

    # Early detection thresholds
    EARLY_DETECTION_MIN_TRADES = 10
    EXCEPTIONAL_WIN_THRESHOLD = 0.8  # 80% win rate
    POOR_SIGNAL_THRESHOLD = 0.4  # 40% win rate

    @classmethod
    async def analyze_signal(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        enable_high_wr_mode: bool = True
    ) -> Dict:
        """
        Analyze signal quality with enhanced high-WR potential detection.

        Args:
            enable_high_wr_mode: Enable stricter thresholds and Phase II prediction

        Returns:
            dict with enhanced metrics including:
                - has_edge: bool
                - raw_win_rate: float
                - confidence_interval: tuple (lower, upper)
                - expected_value: float
                - quality_score: float (0-100)
                - recommendation: str
                - sample_size: int
                - is_significant: bool
                - p_value: float
                - high_wr_potential: bool (NEW)
                - phase2_predicted_wr: float (NEW)
                - phase2_confidence: float (NEW)
                - consistency_score: float (NEW)
                - early_detection_status: str (NEW)
        """
        logger.info(f"Analyzing signal quality: {symbol} {direction} {webhook_source}")

        # Get baseline trades
        baseline_trades = await cls._get_baseline_trades(
            db, symbol, direction, webhook_source
        )

        # Handle insufficient data
        if len(baseline_trades) < cls.MIN_SAMPLE_SIZE:
            # Check for early detection of exceptional signals
            early_status = cls._check_early_detection(baseline_trades) if baseline_trades else 'insufficient_data'

            return {
                'has_edge': False,
                'raw_win_rate': cls._calculate_win_rate(baseline_trades)[0] if baseline_trades else 0.0,
                'confidence_interval': (0.0, 0.0),
                'expected_value': 0.0,
                'quality_score': 0.0,
                'recommendation': 'collect_more_data',
                'sample_size': len(baseline_trades),
                'is_significant': False,
                'p_value': 1.0,
                'message': f'Need {cls.MIN_SAMPLE_SIZE - len(baseline_trades)} more baseline trades',
                'high_wr_potential': False,
                'phase2_predicted_wr': 0.0,
                'phase2_confidence': 0.0,
                'consistency_score': 0.0,
                'early_detection_status': early_status,
                'rolling_variance': 0.0,
                'max_streak': 0,
                'current_streak': 0
            }

        # Calculate core metrics
        win_rate, wins, losses = cls._calculate_win_rate(baseline_trades)
        ci_lower, ci_upper = cls._wilson_score_interval(wins, len(baseline_trades))
        expected_value = cls._calculate_expected_value(baseline_trades)
        is_significant, p_value = cls._binomial_test(wins, len(baseline_trades))

        # Calculate consistency metrics
        consistency_metrics = cls._calculate_consistency_metrics(baseline_trades)

        # Calculate quality score
        quality_score = cls._calculate_quality_score(
            win_rate, ci_lower, ci_upper, expected_value,
            len(baseline_trades), consistency_metrics['consistency_score']
        )

        # Determine edge based on mode
        if enable_high_wr_mode:
            has_edge = cls._evaluate_high_wr_edge(
                win_rate, is_significant, expected_value, ci_upper - ci_lower
            )
        else:
            has_edge = (
                win_rate >= cls.MODERATE_EDGE_THRESHOLD and
                is_significant and
                expected_value > 0
            )

        # Phase II prediction for high-WR potential
        high_wr_potential, phase2_predicted_wr, phase2_confidence = (
            cls._predict_phase2_performance(
                win_rate, ci_lower, ci_upper, expected_value,
                consistency_metrics['consistency_score']
            ) if enable_high_wr_mode else (False, 0.0, 0.0)
        )

        # Early detection status
        early_detection_status = cls._check_early_detection(baseline_trades)

        # Generate recommendation
        recommendation = cls._generate_recommendation(
            win_rate, has_edge, len(baseline_trades), ci_upper - ci_lower,
            high_wr_potential, early_detection_status
        )

        result = {
            'has_edge': has_edge,
            'raw_win_rate': round(win_rate, 2),
            'confidence_interval': (round(ci_lower, 2), round(ci_upper, 2)),
            'expected_value': round(expected_value, 4),
            'quality_score': round(quality_score, 2),
            'recommendation': recommendation,
            'sample_size': len(baseline_trades),
            'is_significant': is_significant,
            'p_value': round(p_value, 6),
            'wins': wins,
            'losses': losses,
            # Enhanced metrics
            'high_wr_potential': high_wr_potential,
            'phase2_predicted_wr': round(phase2_predicted_wr, 2),
            'phase2_confidence': round(phase2_confidence, 2),
            'consistency_score': round(consistency_metrics['consistency_score'], 2),
            'early_detection_status': early_detection_status,
            'rolling_variance': round(consistency_metrics['rolling_variance'], 4),
            'max_streak': consistency_metrics['max_streak'],
            'current_streak': consistency_metrics['current_streak']
        }

        # Store in database
        await cls._store_quality_metrics(
            db, symbol, direction, webhook_source, result
        )

        logger.info(
            f"Signal quality: {symbol} {direction} {webhook_source} - "
            f"WR: {win_rate:.1f}%, Edge: {has_edge}, Score: {quality_score:.1f}, "
            f"High-WR Potential: {high_wr_potential}"
        )

        return result

    @classmethod
    def _evaluate_high_wr_edge(
        cls,
        win_rate: float,
        is_significant: bool,
        expected_value: float,
        ci_width: float
    ) -> bool:
        """
        Evaluate edge using stricter high-WR thresholds.

        Requirements:
        - Baseline WR > 62%
        - CI width < 15%
        - EV > 0.5%
        - Statistical significance
        """
        return (
            win_rate > cls.HIGH_WR_MIN_BASELINE and
            ci_width < cls.HIGH_WR_MAX_CI_WIDTH and
            expected_value > cls.HIGH_WR_MIN_EV and
            is_significant
        )

    @classmethod
    def _predict_phase2_performance(
        cls,
        baseline_wr: float,
        ci_lower: float,
        ci_upper: float,
        expected_value: float,
        consistency_score: float
    ) -> Tuple[bool, float, float]:
        """
        Predict Phase II win rate from baseline performance.

        Uses empirical multipliers and consistency to estimate:
        - Phase II win rate (baseline × 1.05-1.15)
        - Confidence in prediction
        - High-WR potential flag

        Returns:
            (high_wr_potential, predicted_wr, confidence)
        """
        # Check if baseline meets minimum requirements
        if baseline_wr < cls.HIGH_WR_MIN_BASELINE:
            return (False, 0.0, 0.0)

        ci_width = ci_upper - ci_lower
        if ci_width > cls.HIGH_WR_MAX_CI_WIDTH or expected_value < cls.HIGH_WR_MIN_EV:
            return (False, 0.0, 0.0)

        # Calculate multiplier based on consistency
        if consistency_score >= 80:
            multiplier = cls.PHASE2_MULTIPLIER_MAX
            confidence_base = 85
        elif consistency_score >= 60:
            multiplier = cls.PHASE2_MULTIPLIER_TYPICAL
            confidence_base = 70
        else:
            multiplier = cls.PHASE2_MULTIPLIER_MIN
            confidence_base = 55

        # Predict Phase II win rate
        predicted_wr = min(95, baseline_wr * multiplier)  # Cap at 95%

        # Calculate confidence in prediction
        # Factors: CI width, consistency, baseline WR
        ci_penalty = min(20, ci_width * 0.8)  # Wider CI reduces confidence
        wr_bonus = max(0, (baseline_wr - 62) * 0.5)  # Higher baseline increases confidence

        confidence = min(95, confidence_base - ci_penalty + wr_bonus)

        # Determine high-WR potential (predicted >70% with good confidence)
        high_wr_potential = predicted_wr >= 70 and confidence >= 60

        return (high_wr_potential, predicted_wr, confidence)

    @classmethod
    def _calculate_consistency_metrics(cls, trades: List[TradeSetup]) -> Dict:
        """
        Calculate consistency metrics for performance stability.

        Metrics:
        - Rolling variance in win rate
        - Win/loss streaks
        - Performance stability score
        """
        if len(trades) < 3:
            return {
                'consistency_score': 0.0,
                'rolling_variance': 0.0,
                'max_streak': 0,
                'current_streak': 0
            }

        # Sort trades by timestamp
        sorted_trades = sorted(trades, key=lambda t: t.entry_timestamp)

        # Calculate rolling win rates (window size = min(10, len/3))
        window_size = min(10, max(3, len(sorted_trades) // 3))
        rolling_win_rates = []

        for i in range(len(sorted_trades) - window_size + 1):
            window = sorted_trades[i:i + window_size]
            wins = sum(1 for t in window if float(t.final_pnl_pct) > 0)
            wr = (wins / window_size) * 100
            rolling_win_rates.append(wr)

        # Calculate variance in rolling win rates
        rolling_variance = statistics.variance(rolling_win_rates) if len(rolling_win_rates) > 1 else 0

        # Calculate streaks
        max_win_streak = 0
        max_loss_streak = 0
        current_streak = 0
        last_result = None

        for trade in sorted_trades:
            is_win = float(trade.final_pnl_pct) > 0

            if last_result is None:
                current_streak = 1 if is_win else -1
            elif (is_win and last_result > 0) or (not is_win and last_result < 0):
                current_streak = current_streak + 1 if is_win else current_streak - 1
            else:
                current_streak = 1 if is_win else -1

            if current_streak > 0:
                max_win_streak = max(max_win_streak, current_streak)
            else:
                max_loss_streak = max(max_loss_streak, abs(current_streak))

            last_result = 1 if is_win else -1

        # Calculate consistency score (0-100)
        # Lower variance and balanced streaks = higher consistency
        variance_penalty = min(40, rolling_variance * 2)  # Max 40 point penalty

        # Reward balanced streaks (neither too long wins nor losses)
        streak_balance = 100 - (abs(max_win_streak - max_loss_streak) * 5)
        streak_score = max(0, min(30, streak_balance / 3))

        # Base score from win rate stability
        base_score = 70 if rolling_variance < 100 else 50 if rolling_variance < 200 else 30

        consistency_score = max(0, min(100, base_score - variance_penalty + streak_score))

        return {
            'consistency_score': consistency_score,
            'rolling_variance': rolling_variance,
            'max_streak': max_win_streak,
            'current_streak': current_streak
        }

    @classmethod
    def _check_early_detection(cls, trades: List[TradeSetup]) -> str:
        """
        Perform early detection analysis for signals with <10 trades.

        Returns status:
        - 'exceptional': 7/7 or 8/10 wins (fast-track)
        - 'promising': >60% win rate
        - 'poor': <40% win rate (skip early)
        - 'monitoring': Need more data
        - 'insufficient_data': <3 trades
        """
        if len(trades) < 3:
            return 'insufficient_data'

        wins = sum(1 for t in trades if float(t.final_pnl_pct) > 0)
        win_rate = wins / len(trades)

        # Exceptional signals (fast-track)
        if (len(trades) == 7 and wins == 7) or \
           (len(trades) >= 8 and win_rate >= cls.EXCEPTIONAL_WIN_THRESHOLD):
            return 'exceptional'

        # Poor signals (early skip)
        if len(trades) >= 10 and win_rate < cls.POOR_SIGNAL_THRESHOLD:
            return 'poor'

        # Promising signals
        if win_rate > 0.6:
            return 'promising'

        return 'monitoring'

    @classmethod
    def _calculate_quality_score(
        cls,
        win_rate: float,
        ci_lower: float,
        ci_upper: float,
        expected_value: float,
        sample_size: int,
        consistency_score: float
    ) -> float:
        """
        Calculate enhanced composite quality score (0-100).

        Components:
        - 35%: Win rate above 50%
        - 25%: Confidence (narrow CI)
        - 15%: Sample size
        - 15%: Consistency
        - 10%: Expected value
        """
        # Win rate component (35 points max)
        wr_score = min(35, max(0, (win_rate - 50) * 1.75))

        # Confidence component (25 points max)
        ci_width = ci_upper - ci_lower
        confidence_score = max(0, 25 - (ci_width * 0.625))

        # Sample size component (15 points max)
        sample_score = min(15, (sample_size / 6.67))

        # Consistency component (15 points max)
        consistency_points = (consistency_score / 100) * 15

        # Expected value component (10 points max)
        ev_score = min(10, max(0, expected_value * 10))

        total_score = wr_score + confidence_score + sample_score + consistency_points + ev_score

        return total_score

    @classmethod
    def _generate_recommendation(
        cls,
        win_rate: float,
        has_edge: bool,
        sample_size: int,
        ci_width: float,
        high_wr_potential: bool,
        early_detection_status: str
    ) -> str:
        """Generate enhanced recommendation based on analysis."""

        # Early detection overrides
        if early_detection_status == 'exceptional':
            return 'fast_track_optimize'
        elif early_detection_status == 'poor' and sample_size >= 10:
            return 'skip_poor_performance'

        # Insufficient data
        if sample_size < 10:
            if early_detection_status == 'promising':
                return 'collect_more_data_promising'
            return 'collect_more_data'

        # High-WR potential signals
        if high_wr_potential:
            return 'optimize_high_wr'

        # Need more data if CI too wide
        if ci_width > 30 and sample_size < 30:
            return 'collect_more_data'

        # Clear edge - proceed with optimization
        if has_edge and win_rate >= 55:
            return 'optimize'

        # Marginal - monitor
        if 52 <= win_rate < 55:
            return 'monitor'

        # No edge - skip
        return 'skip'

    @classmethod
    async def analyze_all_signals(cls, db: AsyncSession, enable_high_wr_mode: bool = True) -> List[Dict]:
        """Analyze all unique signal combinations with enhanced metrics."""

        # Get all unique signal combinations
        query = select(
            TradeSetup.symbol,
            TradeSetup.direction,
            TradeSetup.webhook_source
        ).where(
            and_(
                TradeSetup.risk_strategy == 'baseline',
                TradeSetup.status == 'completed',
                TradeSetup.final_pnl_pct.isnot(None)
            )
        ).distinct()

        result = await db.execute(query)
        signal_combos = result.fetchall()

        logger.info(f"Analyzing {len(signal_combos)} unique signal combinations")

        results = []
        for symbol, direction, webhook_source in signal_combos:
            analysis = await cls.analyze_signal(
                db, symbol, direction, webhook_source, enable_high_wr_mode
            )
            results.append({
                'symbol': symbol,
                'direction': direction,
                'webhook_source': webhook_source,
                **analysis
            })

        # Sort by high-WR potential and quality score
        results.sort(key=lambda x: (x['high_wr_potential'], x['quality_score']), reverse=True)

        return results

    @staticmethod
    async def _get_baseline_trades(
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> List[TradeSetup]:
        """Get completed baseline trades for analysis."""

        query = select(TradeSetup).where(
            and_(
                TradeSetup.symbol == symbol,
                TradeSetup.direction == direction,
                TradeSetup.webhook_source == webhook_source,
                TradeSetup.risk_strategy == 'baseline',
                TradeSetup.status == 'completed',
                TradeSetup.final_pnl_pct.isnot(None)
            )
        ).order_by(TradeSetup.entry_timestamp.desc())

        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    def _calculate_win_rate(trades: List[TradeSetup]) -> Tuple[float, int, int]:
        """Calculate raw win rate from baseline trades."""
        if not trades:
            return (0.0, 0, 0)
        wins = sum(1 for t in trades if float(t.final_pnl_pct) > 0)
        losses = len(trades) - wins
        win_rate = (wins / len(trades)) * 100
        return win_rate, wins, losses

    @staticmethod
    def _wilson_score_interval(
        successes: int,
        total: int,
        confidence: float = 0.95
    ) -> Tuple[float, float]:
        """
        Calculate Wilson score confidence interval for win rate.

        More accurate than normal approximation for small samples.
        Returns confidence interval as percentages.
        """
        if total == 0:
            return (0.0, 0.0)

        # Z-score for confidence level (1.96 for 95%)
        z = 1.96 if confidence == 0.95 else 2.576  # 99%

        p = successes / total
        denominator = 1 + (z**2 / total)
        centre = (p + (z**2 / (2*total))) / denominator
        margin = (z * math.sqrt((p*(1-p)/total) + (z**2/(4*total**2)))) / denominator

        lower = max(0, centre - margin) * 100
        upper = min(1, centre + margin) * 100

        return (lower, upper)

    @staticmethod
    def _binomial_test(successes: int, total: int, p0: float = 0.5) -> Tuple[bool, float]:
        """
        Perform binomial test to determine if win rate is significantly different from 50%.

        Returns:
            (is_significant, p_value)
        """
        if total == 0:
            return (False, 1.0)

        # Use normal approximation to binomial
        p = successes / total

        # Standard error
        se = math.sqrt(p0 * (1 - p0) / total)

        # Z-score
        z = (p - p0) / se if se > 0 else 0

        # Two-tailed p-value (approximate)
        from math import erf
        p_value = 2 * (1 - 0.5 * (1 + erf(abs(z) / math.sqrt(2))))

        is_significant = p_value < 0.05

        return (is_significant, p_value)

    @staticmethod
    def _calculate_expected_value(trades: List[TradeSetup]) -> float:
        """
        Calculate expected value per trade.

        EV = (win_rate × avg_win) - (loss_rate × avg_loss)
        """
        if not trades:
            return 0.0

        wins = [float(t.final_pnl_pct) for t in trades if float(t.final_pnl_pct) > 0]
        losses = [abs(float(t.final_pnl_pct)) for t in trades if float(t.final_pnl_pct) < 0]

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        win_rate = len(wins) / len(trades)
        loss_rate = 1 - win_rate

        ev = (win_rate * avg_win) - (loss_rate * avg_loss)

        return ev

    @staticmethod
    async def _store_quality_metrics(
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        metrics: Dict
    ):
        """Store enhanced signal quality metrics in database."""

        try:
            # Check if record exists
            query = select(SignalQuality).where(
                and_(
                    SignalQuality.symbol == symbol,
                    SignalQuality.direction == direction,
                    SignalQuality.webhook_source == webhook_source
                )
            )
            result = await db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing record with all metrics
                existing.raw_win_rate = Decimal(str(metrics['raw_win_rate']))
                existing.ci_lower = Decimal(str(metrics['confidence_interval'][0]))
                existing.ci_upper = Decimal(str(metrics['confidence_interval'][1]))
                existing.expected_value = Decimal(str(metrics['expected_value']))
                existing.sample_size = metrics['sample_size']
                existing.is_significant = metrics['is_significant']
                existing.p_value = Decimal(str(metrics['p_value']))
                existing.has_edge = metrics['has_edge']
                existing.quality_score = Decimal(str(metrics['quality_score']))
                existing.recommendation = metrics['recommendation']
                # Enhanced metrics
                existing.high_wr_potential = metrics['high_wr_potential']
                existing.phase2_predicted_wr = Decimal(str(metrics['phase2_predicted_wr']))
                existing.phase2_confidence = Decimal(str(metrics['phase2_confidence']))
                existing.consistency_score = Decimal(str(metrics['consistency_score']))
                existing.early_detection_status = metrics['early_detection_status']
                existing.rolling_variance = Decimal(str(metrics['rolling_variance']))
                existing.max_streak = metrics['max_streak']
                existing.current_streak = metrics['current_streak']
                existing.last_analyzed_at = datetime.utcnow()
            else:
                # Create new record with all metrics
                quality = SignalQuality(
                    symbol=symbol,
                    direction=direction,
                    webhook_source=webhook_source,
                    raw_win_rate=Decimal(str(metrics['raw_win_rate'])),
                    ci_lower=Decimal(str(metrics['confidence_interval'][0])),
                    ci_upper=Decimal(str(metrics['confidence_interval'][1])),
                    expected_value=Decimal(str(metrics['expected_value'])),
                    sample_size=metrics['sample_size'],
                    is_significant=metrics['is_significant'],
                    p_value=Decimal(str(metrics['p_value'])),
                    has_edge=metrics['has_edge'],
                    quality_score=Decimal(str(metrics['quality_score'])),
                    recommendation=metrics['recommendation'],
                    # Enhanced metrics
                    high_wr_potential=metrics['high_wr_potential'],
                    phase2_predicted_wr=Decimal(str(metrics['phase2_predicted_wr'])),
                    phase2_confidence=Decimal(str(metrics['phase2_confidence'])),
                    consistency_score=Decimal(str(metrics['consistency_score'])),
                    early_detection_status=metrics['early_detection_status'],
                    rolling_variance=Decimal(str(metrics['rolling_variance'])),
                    max_streak=metrics['max_streak'],
                    current_streak=metrics['current_streak'],
                    last_analyzed_at=datetime.utcnow()
                )
                db.add(quality)

            await db.commit()

        except Exception as e:
            logger.error(f"Error storing signal quality metrics: {e}")
            await db.rollback()