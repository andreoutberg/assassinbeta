"""
Enhanced Phase Manager for High-WR Optimization

Manages phase transitions with adaptive baseline collection, fast-tracking for
high-performing signals, and early skip logic for poor quality signals.

Key Features:
- High-WR mode support with specialized Phase III criteria
- Fast-track exceptional signals (>70% WR) to Phase II
- Skip poor signals (<40% WR) early
- Adaptive baseline collection based on signal strength
- Dynamic promotion criteria based on OPTIMIZE_FOR_WIN_RATE setting
"""

import logging
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from scipy import stats
import numpy as np

from app.database.models import TradeSetup
from app.database.baseline_models import BaselineTrade
from app.database.strategy_models import StrategyPerformance, StrategySimulation
from app.database.signal_quality_models import SignalQuality
from app.config.phase_config import PhaseConfig
from app.models.strategy_types import TradePhaseInfo, StrategyConfig

logger = logging.getLogger(__name__)


class PhaseManager:
    """
    Enhanced phase manager with high-WR optimization support

    Phases:
    - Phase I: Baseline collection (adaptive 20-40 trades)
    - Phase II: Strategy optimization (paper trading)
    - Phase III: Live trading with best strategy
    """

    # Signal quality thresholds
    EXCEPTIONAL_SIGNAL_WR = 70.0    # Fast-track to Phase II
    EXCEPTIONAL_SIGNAL_CI = 20.0    # Max confidence interval for fast-track
    POOR_SIGNAL_WR = 40.0           # Skip threshold
    POOR_SIGNAL_MIN_TRADES = 10    # Min trades before skip decision

    # Adaptive baseline thresholds
    STRONG_SIGNAL_TRADES = 20      # Strong signals need fewer baseline
    NORMAL_SIGNAL_TRADES = 30      # Standard baseline collection
    MARGINAL_SIGNAL_TRADES = 40    # Marginal signals need more data

    def __init__(self):
        """Initialize the phase manager"""
        self.config = PhaseConfig
        logger.info(
            f"✅ PhaseManager initialized - Mode: "
            f"{'HIGH-WR' if self.config.OPTIMIZE_FOR_WIN_RATE else 'BALANCED'}"
        )

    async def determine_phase(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> TradePhaseInfo:
        """
        Determine current phase with adaptive logic

        Returns:
            TradePhaseInfo with phase details and recommendations
        """
        # Get baseline statistics
        baseline_stats = await self._get_baseline_stats(db, symbol, direction, webhook_source)
        baseline_count = baseline_stats['completed_count']

        # Get signal quality
        signal_quality = await self._get_signal_quality(db, symbol, direction, webhook_source)

        # Phase I: Check for early decisions
        if baseline_count < self.config.MIN_BASELINE_TRADES:
            phase_decision = await self._evaluate_phase_i(
                db, symbol, direction, webhook_source,
                baseline_stats, signal_quality
            )
            if phase_decision:
                return phase_decision

        # Check if we have enough baseline for Phase II
        required_baseline = await self._get_adaptive_baseline_requirement(
            baseline_stats, signal_quality
        )

        if baseline_count < required_baseline:
            # Still in Phase I
            return TradePhaseInfo(
                phase='I',
                phase_name='Data Collection',
                baseline_completed=baseline_count,
                baseline_needed=required_baseline,
                best_strategy=None,
                description=f'Collecting baseline data ({baseline_count}/{required_baseline})'
            )

        # Phase II or III: Check for eligible strategies
        best_strategy = await self._get_best_eligible_strategy(
            db, symbol, direction, webhook_source
        )

        if best_strategy:
            # Phase III: Live trading
            return TradePhaseInfo(
                phase='III',
                phase_name='Live Trading',
                baseline_completed=baseline_count,
                best_strategy=best_strategy,
                description=f"Using {best_strategy['strategy_name']} - "
                          f"WR: {best_strategy.get('win_rate', 0):.1f}%, "
                          f"RR: {best_strategy.get('risk_reward', 0):.2f}"
            )
        else:
            # Phase II: Strategy optimization
            strategies = await self._get_all_strategies(db, symbol, direction, webhook_source)
            strategy_count = len(strategies) if strategies else 0

            return TradePhaseInfo(
                phase='II',
                phase_name='Strategy Optimization',
                baseline_completed=baseline_count,
                best_strategy=None,
                description=f'Testing {strategy_count} strategies via paper trading'
            )

    async def _evaluate_phase_i(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        baseline_stats: Dict,
        signal_quality: Optional[SignalQuality]
    ) -> Optional[TradePhaseInfo]:
        """
        Evaluate Phase I for early decisions (fast-track or skip)
        """
        baseline_count = baseline_stats['completed_count']
        win_rate = baseline_stats.get('win_rate', 0)

        # 1. Check for poor signal (skip optimization)
        if baseline_count >= self.POOR_SIGNAL_MIN_TRADES:
            if win_rate < self.POOR_SIGNAL_WR:
                # Mark as poor quality and skip
                logger.warning(
                    f"⚠️ Poor signal detected for {symbol} {direction}: "
                    f"WR={win_rate:.1f}% after {baseline_count} trades. Skipping optimization."
                )

                # Update signal quality
                if signal_quality:
                    signal_quality.early_detection_status = 'poor'
                    signal_quality.recommendation = 'SKIP_OPTIMIZATION'

                return TradePhaseInfo(
                    phase='I',
                    phase_name='Poor Signal - Skipped',
                    baseline_completed=baseline_count,
                    baseline_needed=0,
                    best_strategy=None,
                    description=f'Signal quality too low (WR={win_rate:.1f}%). Optimization skipped.'
                )

            # Check for statistically significant evidence of <50% WR
            if signal_quality and signal_quality.is_significant:
                if signal_quality.ci_upper and signal_quality.ci_upper < 50.0:
                    logger.warning(
                        f"⚠️ Statistically poor signal for {symbol} {direction}: "
                        f"CI upper bound={signal_quality.ci_upper:.1f}%"
                    )

                    signal_quality.early_detection_status = 'poor'
                    signal_quality.recommendation = 'SKIP_OPTIMIZATION'

                    return TradePhaseInfo(
                        phase='I',
                        phase_name='Poor Signal - Skipped',
                        baseline_completed=baseline_count,
                        baseline_needed=0,
                        best_strategy=None,
                        description=f'Statistically poor signal (CI: {signal_quality.ci_lower:.1f}-{signal_quality.ci_upper:.1f}%)'
                    )

        # 2. Check for exceptional signal (fast-track)
        if baseline_count >= 20:  # Minimum for fast-track
            ci_width = baseline_stats.get('ci_width', 100)

            if win_rate > self.EXCEPTIONAL_SIGNAL_WR and ci_width < self.EXCEPTIONAL_SIGNAL_CI:
                logger.info(
                    f"🚀 Exceptional signal detected for {symbol} {direction}: "
                    f"WR={win_rate:.1f}% CI={ci_width:.1f}%. Fast-tracking to Phase II."
                )

                # Update signal quality
                if signal_quality:
                    signal_quality.early_detection_status = 'exceptional'
                    signal_quality.high_wr_potential = True
                    signal_quality.phase2_predicted_wr = Decimal(str(min(win_rate + 5, 85)))
                    signal_quality.phase2_confidence = Decimal(str(85.0))

                # Trigger Phase II immediately
                return None  # Will proceed to Phase II check

        return None  # Continue normal Phase I

    async def _get_adaptive_baseline_requirement(
        self,
        baseline_stats: Dict,
        signal_quality: Optional[SignalQuality]
    ) -> int:
        """
        Determine adaptive baseline requirement based on signal strength
        """
        win_rate = baseline_stats.get('win_rate', 50)
        completed_count = baseline_stats['completed_count']

        # If we have signal quality assessment
        if signal_quality and signal_quality.quality_score:
            quality_score = float(signal_quality.quality_score)

            if quality_score >= 80:  # Strong signal
                return self.STRONG_SIGNAL_TRADES
            elif quality_score >= 60:  # Normal signal
                return self.NORMAL_SIGNAL_TRADES
            else:  # Marginal signal
                return self.MARGINAL_SIGNAL_TRADES

        # Fallback to win rate based assessment
        if completed_count >= 10:
            if win_rate >= 65:  # Strong signal
                return self.STRONG_SIGNAL_TRADES
            elif win_rate >= 50:  # Normal signal
                return self.NORMAL_SIGNAL_TRADES
            else:  # Marginal signal
                return self.MARGINAL_SIGNAL_TRADES

        # Default to normal requirement
        return self.NORMAL_SIGNAL_TRADES

    async def check_phase_iii_eligibility(
        self,
        db: AsyncSession,
        strategy_performance: StrategyPerformance
    ) -> Tuple[bool, Dict[str, any]]:
        """
        Check if strategy meets Phase III promotion criteria

        Enhanced for high-WR mode with additional validation
        """
        criteria = {
            'eligible': False,
            'win_rate': float(strategy_performance.win_rate) if strategy_performance.win_rate else 0,
            'risk_reward': float(strategy_performance.risk_reward) if strategy_performance.risk_reward else 0,
            'expected_value': 0,
            'duration': float(strategy_performance.avg_duration_hours) if strategy_performance.avg_duration_hours else 0,
            'has_valid_sl': False,
            'meets_wr': False,
            'meets_rr': False,
            'meets_ev': False,
            'meets_duration': False,
            'sl_tp_constraint': False,
            'actual_rr_verified': False
        }

        # Basic checks
        if not strategy_performance.trades_analyzed or strategy_performance.trades_analyzed < 10:
            criteria['reason'] = 'Insufficient trades analyzed'
            return False, criteria

        # Check for valid SL (not 999999)
        if strategy_performance.current_sl_pct and abs(float(strategy_performance.current_sl_pct)) < 100:
            criteria['has_valid_sl'] = True
        else:
            criteria['reason'] = 'Invalid or missing stop loss'
            return False, criteria

        # Duration check
        if strategy_performance.max_duration_hours and float(strategy_performance.max_duration_hours) <= 24:
            criteria['meets_duration'] = True
        else:
            criteria['reason'] = f"Duration too long: {float(strategy_performance.max_duration_hours):.1f}h > 24h"
            return False, criteria

        # Calculate expected value
        win_rate = criteria['win_rate']
        risk_reward = criteria['risk_reward']
        criteria['expected_value'] = self.config.calculate_expected_value(win_rate, risk_reward)

        # HIGH-WR MODE CHECKS
        if self.config.OPTIMIZE_FOR_WIN_RATE:
            # Win rate requirement
            if win_rate >= self.config.PHASE_III_TARGET_WIN_RATE:  # 65%
                criteria['meets_wr'] = True
            else:
                criteria['reason'] = f"Win rate {win_rate:.1f}% < {self.config.PHASE_III_TARGET_WIN_RATE}%"
                return False, criteria

            # Expected value requirement
            if criteria['expected_value'] >= self.config.PHASE_III_MIN_EXPECTED_VALUE:  # 0.05
                criteria['meets_ev'] = True
            else:
                criteria['reason'] = f"Expected value {criteria['expected_value']:.4f} < {self.config.PHASE_III_MIN_EXPECTED_VALUE}"
                return False, criteria

            # Risk/Reward requirement (keep at 1.0 minimum)
            min_rr = 1.0  # As specified in requirements
            if risk_reward >= min_rr:
                criteria['meets_rr'] = True
            else:
                criteria['reason'] = f"Risk/Reward {risk_reward:.2f} < {min_rr}"
                return False, criteria

            # SL < TP constraint check
            tp_pct = float(strategy_performance.current_tp1_pct) if strategy_performance.current_tp1_pct else 0
            sl_pct = abs(float(strategy_performance.current_sl_pct)) if strategy_performance.current_sl_pct else 0

            if sl_pct < tp_pct:
                criteria['sl_tp_constraint'] = True
            else:
                criteria['reason'] = f"SL ({sl_pct:.2f}%) must be < TP ({tp_pct:.2f}%)"
                return False, criteria

            # Verify RR from actual trades (not just planned parameters)
            criteria['actual_rr_verified'] = await self._verify_actual_rr(
                db, strategy_performance, min_rr
            )

            if not criteria['actual_rr_verified']:
                criteria['reason'] = f"Actual RR from trades doesn't meet {min_rr} requirement"
                return False, criteria

        else:
            # BALANCED MODE CHECKS (original logic)
            # Win rate requirement (lower threshold)
            if win_rate >= self.config.PHASE_III_MIN_WIN_RATE:  # 45%
                criteria['meets_wr'] = True

            # Risk/Reward requirement
            if risk_reward >= self.config.PHASE_III_MIN_RR:  # 1.0
                criteria['meets_rr'] = True
            else:
                criteria['reason'] = f"Risk/Reward {risk_reward:.2f} < {self.config.PHASE_III_MIN_RR}"
                return False, criteria

            # Expected value requirement
            if criteria['expected_value'] >= self.config.PHASE_III_MIN_EXPECTED_VALUE:  # 0.02
                criteria['meets_ev'] = True
            else:
                criteria['reason'] = f"Expected value {criteria['expected_value']:.4f} < {self.config.PHASE_III_MIN_EXPECTED_VALUE}"
                return False, criteria

        # All criteria met
        criteria['eligible'] = True
        criteria['reason'] = 'All Phase III criteria met'

        return True, criteria

    async def _verify_actual_rr(
        self,
        db: AsyncSession,
        strategy_performance: StrategyPerformance,
        min_rr: float
    ) -> bool:
        """
        Verify RR ratio from actual simulated trades, not just parameters
        """
        # Get recent simulations for this strategy
        result = await db.execute(
            select(StrategySimulation).join(
                TradeSetup,
                StrategySimulation.trade_setup_id == TradeSetup.id
            ).where(
                and_(
                    TradeSetup.symbol == strategy_performance.symbol,
                    TradeSetup.direction == strategy_performance.direction,
                    TradeSetup.webhook_source == strategy_performance.webhook_source,
                    StrategySimulation.strategy_name == strategy_performance.strategy_name,
                    StrategySimulation.simulated_pnl_pct.isnot(None)
                )
            ).order_by(
                StrategySimulation.created_at.desc()
            ).limit(20)
        )
        simulations = result.scalars().all()

        if not simulations or len(simulations) < 10:
            return False  # Not enough data

        # Calculate actual RR from trades
        wins = [float(s.simulated_pnl_pct) for s in simulations if float(s.simulated_pnl_pct) > 0]
        losses = [abs(float(s.simulated_pnl_pct)) for s in simulations if float(s.simulated_pnl_pct) < 0]

        if not wins or not losses:
            return False  # Need both wins and losses

        avg_win = np.mean(wins)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return True  # No losses means infinite RR

        actual_rr = avg_win / avg_loss

        return actual_rr >= min_rr

    async def _get_baseline_stats(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> Dict:
        """
        Get comprehensive baseline statistics
        """
        # Get completed baseline trades
        result = await db.execute(
            select(BaselineTrade).where(
                and_(
                    BaselineTrade.symbol == symbol,
                    BaselineTrade.direction == direction,
                    BaselineTrade.webhook_source == webhook_source,
                    BaselineTrade.status == 'completed'
                )
            ).order_by(BaselineTrade.exit_timestamp.desc())
        )
        trades = result.scalars().all()

        if not trades:
            return {
                'completed_count': 0,
                'win_rate': 0,
                'avg_pnl': 0,
                'ci_lower': 0,
                'ci_upper': 0,
                'ci_width': 100,
                'recent_trend': 'neutral'
            }

        # Calculate statistics
        pnls = [float(t.final_pnl_pct) for t in trades]
        wins = sum(1 for pnl in pnls if pnl > 0)
        win_rate = (wins / len(trades)) * 100 if trades else 0

        # Calculate confidence interval
        if len(trades) >= 10:
            ci_lower, ci_upper = self._calculate_confidence_interval(wins, len(trades))
        else:
            ci_lower, ci_upper = 0, 100

        # Recent trend (last 10 trades)
        recent_trades = trades[:10]
        recent_wins = sum(1 for t in recent_trades if float(t.final_pnl_pct) > 0)
        recent_wr = (recent_wins / len(recent_trades)) * 100 if recent_trades else 0

        if recent_wr > win_rate + 10:
            recent_trend = 'improving'
        elif recent_wr < win_rate - 10:
            recent_trend = 'declining'
        else:
            recent_trend = 'stable'

        return {
            'completed_count': len(trades),
            'win_rate': win_rate,
            'avg_pnl': np.mean(pnls) if pnls else 0,
            'ci_lower': ci_lower,
            'ci_upper': ci_upper,
            'ci_width': ci_upper - ci_lower,
            'recent_trend': recent_trend,
            'recent_win_rate': recent_wr
        }

    async def _get_signal_quality(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> Optional[SignalQuality]:
        """
        Get signal quality assessment
        """
        result = await db.execute(
            select(SignalQuality).where(
                and_(
                    SignalQuality.symbol == symbol,
                    SignalQuality.direction == direction,
                    SignalQuality.webhook_source == webhook_source
                )
            )
        )
        return result.scalar_one_or_none()

    async def _get_best_eligible_strategy(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> Optional[StrategyConfig]:
        """
        Get the best strategy that meets Phase III criteria
        """
        # Get all strategies ordered by score
        result = await db.execute(
            select(StrategyPerformance).where(
                and_(
                    StrategyPerformance.symbol == symbol,
                    StrategyPerformance.direction == direction,
                    StrategyPerformance.webhook_source == webhook_source,
                    StrategyPerformance.trades_analyzed >= 10
                )
            ).order_by(StrategyPerformance.strategy_score.desc())
        )
        performances = result.scalars().all()

        # Check each strategy for Phase III eligibility
        for perf in performances:
            eligible, criteria = await self.check_phase_iii_eligibility(db, perf)

            if eligible:
                logger.info(
                    f"✅ Phase III eligible strategy found: {perf.strategy_name} "
                    f"WR={criteria['win_rate']:.1f}% RR={criteria['risk_reward']:.2f} "
                    f"EV={criteria['expected_value']:.4f}"
                )

                return StrategyConfig(
                    strategy_name=perf.strategy_name,
                    tp1_pct=float(perf.current_tp1_pct) if perf.current_tp1_pct else None,
                    tp2_pct=float(perf.current_tp2_pct) if perf.current_tp2_pct else None,
                    tp3_pct=float(perf.current_tp3_pct) if perf.current_tp3_pct else None,
                    sl_pct=float(perf.current_sl_pct) if perf.current_sl_pct else None,
                    trailing_enabled=perf.current_trailing_enabled,
                    trailing_activation=float(perf.current_trailing_activation) if perf.current_trailing_activation else None,
                    trailing_distance=float(perf.current_trailing_distance) if perf.current_trailing_distance else None,
                    # Include metrics for transparency
                    win_rate=criteria['win_rate'],
                    risk_reward=criteria['risk_reward'],
                    expected_value=criteria['expected_value']
                )

        return None

    async def _get_all_strategies(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> List[StrategyPerformance]:
        """
        Get all strategies for a symbol/direction/webhook
        """
        result = await db.execute(
            select(StrategyPerformance).where(
                and_(
                    StrategyPerformance.symbol == symbol,
                    StrategyPerformance.direction == direction,
                    StrategyPerformance.webhook_source == webhook_source
                )
            ).order_by(StrategyPerformance.strategy_score.desc())
        )
        return result.scalars().all()

    def _calculate_confidence_interval(
        self,
        successes: int,
        trials: int,
        confidence: float = 0.95
    ) -> Tuple[float, float]:
        """
        Calculate Wilson score confidence interval for binomial proportion
        """
        if trials == 0:
            return 0, 0

        p_hat = successes / trials
        z = stats.norm.ppf((1 + confidence) / 2)

        denominator = 1 + z**2 / trials
        center = (p_hat + z**2 / (2 * trials)) / denominator
        spread = z * np.sqrt((p_hat * (1 - p_hat) / trials + z**2 / (4 * trials**2))) / denominator

        ci_lower = max(0, (center - spread) * 100)
        ci_upper = min(100, (center + spread) * 100)

        return ci_lower, ci_upper

    async def update_strategy_eligibility(
        self,
        db: AsyncSession,
        strategy_performance: StrategyPerformance
    ) -> bool:
        """
        Update strategy's Phase III eligibility status
        """
        eligible, criteria = await self.check_phase_iii_eligibility(db, strategy_performance)

        # Update the strategy performance record
        strategy_performance.is_eligible_for_phase3 = eligible
        strategy_performance.meets_rr_requirement = criteria.get('meets_rr', False)
        strategy_performance.has_real_sl = criteria.get('has_valid_sl', False)
        strategy_performance.meets_duration_requirement = criteria.get('meets_duration', False)

        # Log the update
        logger.info(
            f"📊 Updated {strategy_performance.strategy_name} eligibility: "
            f"{'✅ ELIGIBLE' if eligible else '❌ NOT ELIGIBLE'} - {criteria.get('reason', '')}"
        )

        return eligible

    async def get_phase_summary(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> Dict:
        """
        Get comprehensive phase summary for monitoring
        """
        # Get current phase
        phase_info = await self.determine_phase(db, symbol, direction, webhook_source)

        # Get baseline stats
        baseline_stats = await self._get_baseline_stats(db, symbol, direction, webhook_source)

        # Get signal quality
        signal_quality = await self._get_signal_quality(db, symbol, direction, webhook_source)

        # Get all strategies
        strategies = await self._get_all_strategies(db, symbol, direction, webhook_source)

        # Count Phase III eligible strategies
        eligible_count = sum(1 for s in strategies if s.is_eligible_for_phase3)

        summary = {
            'symbol': symbol,
            'direction': direction,
            'webhook_source': webhook_source,
            'current_phase': phase_info['phase'],
            'phase_name': phase_info['phase_name'],
            'phase_description': phase_info.get('description', ''),
            'baseline': {
                'completed': baseline_stats['completed_count'],
                'win_rate': baseline_stats['win_rate'],
                'avg_pnl': baseline_stats['avg_pnl'],
                'confidence_interval': f"{baseline_stats['ci_lower']:.1f}-{baseline_stats['ci_upper']:.1f}%",
                'recent_trend': baseline_stats['recent_trend']
            },
            'signal_quality': {
                'has_edge': signal_quality.has_edge if signal_quality else False,
                'quality_score': float(signal_quality.quality_score) if signal_quality and signal_quality.quality_score else 0,
                'high_wr_potential': signal_quality.high_wr_potential if signal_quality else False,
                'early_detection': signal_quality.early_detection_status if signal_quality else 'monitoring',
                'recommendation': signal_quality.recommendation if signal_quality else 'CONTINUE'
            },
            'strategies': {
                'total': len(strategies),
                'phase_iii_eligible': eligible_count,
                'best_score': float(strategies[0].strategy_score) if strategies else 0,
                'best_win_rate': float(strategies[0].win_rate) if strategies else 0,
                'best_rr': float(strategies[0].risk_reward) if strategies else 0
            },
            'optimization_mode': 'HIGH_WIN_RATE' if self.config.OPTIMIZE_FOR_WIN_RATE else 'BALANCED'
        }

        # Add best strategy details if in Phase III
        if phase_info['phase'] == 'III' and phase_info.get('best_strategy'):
            summary['active_strategy'] = {
                'name': phase_info['best_strategy']['strategy_name'],
                'win_rate': phase_info['best_strategy'].get('win_rate', 0),
                'risk_reward': phase_info['best_strategy'].get('risk_reward', 0),
                'expected_value': phase_info['best_strategy'].get('expected_value', 0)
            }

        return summary


# Global instance
_phase_manager: Optional[PhaseManager] = None


def get_phase_manager() -> PhaseManager:
    """Get or create global phase manager instance"""
    global _phase_manager
    if _phase_manager is None:
        _phase_manager = PhaseManager()
    return _phase_manager