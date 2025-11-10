"""
Grid Search Optimizer - Tests all parameter combinations
Optimized for High Win Rate (>65%) with Risk/Reward > 1.0

Key optimizations:
1. Pre-filters invalid TP/SL combinations (RR <= 1.0)
2. Prioritizes high win rate strategies (65-70% target)
3. Enforces strict minimum thresholds for Phase III
4. Uses MFE/MAE data to estimate hit probabilities
"""
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import TradeSetup, TradeMilestones
from app.services.strategy_simulator import StrategySimulator
from app.config.phase_config import PhaseConfig
from app.models.strategy_types import GridSearchResult
import logging

logger = logging.getLogger(__name__)


class GridSearchOptimizer:
    """Grid-based strategy optimization for high win rate"""

    # High-WR optimization thresholds
    MIN_WIN_RATE_PCT = 60.0          # Reject if WR < 60%
    TARGET_WIN_RATE_PCT = 65.0       # Target 65-70% WR
    HIGH_WIN_RATE_PCT = 70.0         # Premium WR threshold
    MIN_RISK_REWARD = 1.0             # Strict RR > 1.0 requirement
    MIN_EXPECTED_VALUE = 0.0          # Must have positive EV
    MAX_DURATION_HOURS = 24.0         # Reject if avg duration > 24h
    OPTIMAL_DURATION_HOURS = 6.0      # Prefer trades < 6h

    @classmethod
    def grid_search(
        cls,
        baseline_trades: List[TradeSetup]
    ) -> List[GridSearchResult]:
        """
        Test all parameter combinations against baseline trades
        Optimized for High Win Rate (>65%) with RR > 1.0

        Returns top strategies ranked by high-WR composite score
        """
        import time
        start_time = time.time()

        results = []
        total_combinations = PhaseConfig.get_total_combinations()

        # Track filtering statistics
        total_theoretical = len(PhaseConfig.TP_OPTIONS) * len(PhaseConfig.SL_OPTIONS) * len(PhaseConfig.TRAILING_OPTIONS) * len(PhaseConfig.BREAKEVEN_OPTIONS)
        combinations_filtered_rr = 0
        combinations_filtered_invalid = 0
        combination_count = 0

        logger.info(
            f"🔍 Starting HIGH-WR grid search: "
            f"{total_theoretical} theoretical combinations × {len(baseline_trades)} trades"
        )
        logger.info(f"📊 Target: WR≥{cls.TARGET_WIN_RATE_PCT}%, RR>{cls.MIN_RISK_REWARD}")

        # Test all combinations with pre-filtering
        for tp_pct in PhaseConfig.TP_OPTIONS:
            for sl_pct in PhaseConfig.SL_OPTIONS:
                # === PRE-FILTER 1: Risk/Reward Ratio ===
                # CRITICAL: Enforce RR > 1.0 (not >= 1.5 as before)
                theoretical_rr = tp_pct / abs(sl_pct)
                if theoretical_rr <= cls.MIN_RISK_REWARD:
                    combinations_filtered_rr += 1
                    continue  # Skip low RR combinations

                # === PRE-FILTER 2: Invalid Combinations ===
                # Skip if abs(SL) >= TP (would result in RR <= 1.0)
                if abs(sl_pct) >= tp_pct:
                    combinations_filtered_invalid += 1
                    continue  # Skip invalid combinations

                # === HIGH-WR OPTIMIZATION: Estimate hit probability ===
                # Favor TP/SL combinations likely to achieve high win rate
                # Smaller TPs are more likely to hit (higher WR)
                # Larger SLs give more room (reduce premature exits)
                estimated_wr_factor = cls._estimate_win_rate_factor(tp_pct, sl_pct)

                # Skip combinations unlikely to achieve target WR
                if estimated_wr_factor < 0.5:  # Less than 50% chance of high WR
                    continue

                for trailing in PhaseConfig.TRAILING_OPTIONS:
                    for breakeven_multiplier in PhaseConfig.BREAKEVEN_OPTIONS:
                        combination_count += 1

                        # Build strategy config
                        if trailing is None:
                            trailing_enabled = False
                            trailing_activation = None
                            trailing_distance = None
                        else:
                            trailing_enabled = True
                            trailing_activation = trailing[0]  # Activation %
                            trailing_distance = trailing[1]    # Callback %

                        # Breakeven structure
                        if breakeven_multiplier is None:
                            # No breakeven: Single TP
                            tp1_pct_val = tp_pct
                            tp2_pct_val = None
                            breakeven_trigger_pct = None
                        else:
                            # With breakeven: TP1=trigger, TP2=final target
                            tp1_pct_val = tp_pct * breakeven_multiplier
                            tp2_pct_val = tp_pct
                            breakeven_trigger_pct = tp1_pct_val

                        strategy = {
                            'strategy_name': f'high_wr_{combination_count}',
                            'tp1_pct': tp1_pct_val,
                            'tp2_pct': tp2_pct_val,
                            'tp3_pct': None,
                            'sl_pct': sl_pct,
                            'trailing_enabled': trailing_enabled,
                            'trailing_activation': trailing_activation,
                            'trailing_distance': trailing_distance,
                            'breakeven_trigger_pct': breakeven_trigger_pct
                        }

                        # Simulate against all baseline trades
                        simulation_results = []
                        for trade in baseline_trades:
                            try:
                                result = StrategySimulator.simulate_strategy_outcome(
                                    trade, strategy
                                )
                                simulation_results.append(result)
                            except Exception as e:
                                logger.error(f"Simulation failed for trade {trade.id}: {e}")
                                continue

                        # Calculate performance metrics with HIGH-WR scoring
                        if simulation_results:
                            metrics = cls._calculate_high_wr_metrics(
                                simulation_results, strategy, baseline_trades
                            )

                            # === MINIMUM THRESHOLDS ===
                            # Only include strategies meeting ALL criteria
                            if cls._meets_minimum_thresholds(metrics):
                                results.append(metrics)
                            else:
                                logger.debug(
                                    f"Strategy {strategy['strategy_name']} rejected: "
                                    f"WR={metrics['win_rate']:.1f}%, "
                                    f"RR={metrics['risk_reward']:.2f}, "
                                    f"Duration={metrics['avg_duration_hours']:.1f}h"
                                )

        # Sort by HIGH-WR composite score
        results.sort(key=lambda x: x['composite_score'], reverse=True)

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Detailed filtering report
        total_filtered = combinations_filtered_rr + combinations_filtered_invalid
        actual_tested = combination_count

        logger.info(
            f"🎯 HIGH-WR Grid Search Complete in {elapsed_ms}ms\n"
            f"  📊 Filtering Summary:\n"
            f"     • Total theoretical: {total_theoretical} combinations\n"
            f"     • Filtered (RR≤1.0): {combinations_filtered_rr} combinations\n"
            f"     • Filtered (invalid): {combinations_filtered_invalid} combinations\n"
            f"     • Actually tested: {actual_tested} combinations\n"
            f"     • Valid strategies: {len(results)} strategies\n"
        )

        if results:
            # Report top strategies
            top = results[0]
            logger.info(
                f"  🏆 Top Strategy:\n"
                f"     • Win Rate: {top['win_rate']:.1f}% "
                f"{'🌟' if top['win_rate'] >= cls.HIGH_WIN_RATE_PCT else '✓' if top['win_rate'] >= cls.TARGET_WIN_RATE_PCT else ''}\n"
                f"     • Risk/Reward: {top['risk_reward']:.2f}\n"
                f"     • Score: {top['composite_score']:.4f}\n"
                f"     • Duration: {top['avg_duration_hours']:.1f}h"
            )

            # Count high-WR strategies
            high_wr_count = sum(1 for r in results if r['win_rate'] >= cls.TARGET_WIN_RATE_PCT)
            very_high_wr_count = sum(1 for r in results if r['win_rate'] >= cls.HIGH_WIN_RATE_PCT)
            logger.info(
                f"  📈 High-WR Strategies Found:\n"
                f"     • WR≥65%: {high_wr_count} strategies\n"
                f"     • WR≥70%: {very_high_wr_count} strategies"
            )
        else:
            logger.warning(
                f"⚠️ No valid HIGH-WR strategies found! "
                f"Consider adjusting parameters or collecting more baseline data."
            )

        return results[:50]  # Return top 50 for diverse strategy selection

    @classmethod
    def _estimate_win_rate_factor(cls, tp_pct: float, sl_pct: float) -> float:
        """
        Estimate likelihood of achieving high win rate based on TP/SL levels
        Uses heuristics based on typical market behavior

        Returns: 0.0-1.0 factor (1.0 = very likely to achieve high WR)
        """
        # First check if RR is valid
        rr = tp_pct / abs(sl_pct)
        if rr <= cls.MIN_RISK_REWARD:
            return 0.0  # Invalid RR, no chance of being selected

        # Smaller TPs are more likely to hit
        tp_factor = max(0, 1.0 - (tp_pct / 20.0))  # 20% TP = 0 factor

        # Larger SLs (in absolute terms) give more room
        sl_factor = min(1.0, abs(sl_pct) / 10.0)  # 10% SL = 1.0 factor

        # RR penalty - very high RR means tiny SL or huge TP (both reduce WR)
        rr_penalty = max(0, 1.0 - ((rr - 1.0) / 4.0))  # RR=5 gets 0 factor

        # Combine factors
        combined = (tp_factor * 0.5 + sl_factor * 0.3 + rr_penalty * 0.2)

        # Boost for sweet spots (e.g., TP=2-5%, SL=2-4%)
        # BUT only if RR is valid (>1.0)
        if 2.0 <= tp_pct <= 5.0 and 2.0 <= abs(sl_pct) <= 4.0 and rr > cls.MIN_RISK_REWARD:
            combined *= 1.2  # 20% boost for sweet spot

        return min(1.0, combined)

    @classmethod
    def _calculate_high_wr_metrics(
        cls,
        sim_results: List[dict],
        strategy: dict,
        baseline_trades: List[TradeSetup]
    ) -> GridSearchResult:
        """
        Calculate performance metrics optimized for HIGH WIN RATE

        Scoring prioritizes:
        1. Win rate (65% weight)
        2. Risk/reward (20% weight)
        3. Duration (15% weight)

        Includes bonuses for WR>65% and WR>70%
        """
        wins = [r for r in sim_results if r['pnl_pct'] > 0]
        losses = [r for r in sim_results if r['pnl_pct'] <= 0]

        win_rate = (len(wins) / len(sim_results)) * 100 if sim_results else 0
        avg_win = sum(r['pnl_pct'] for r in wins) / len(wins) if wins else 0
        avg_loss = sum(r['pnl_pct'] for r in losses) / len(losses) if losses else 0

        # Calculate PLANNED risk/reward ratio
        tp_pct = strategy['tp1_pct']
        sl_pct = abs(strategy['sl_pct'])

        if sl_pct > 0:
            planned_risk_reward = tp_pct / sl_pct
        else:
            planned_risk_reward = 0.0

        risk_reward = planned_risk_reward

        # Calculate expected value
        expected_value = (win_rate/100 * avg_win) + ((100-win_rate)/100 * avg_loss)

        # === HIGH-WR COMPOSITE SCORE ===
        # Increase win rate weight to 65% (from 60%)
        # Add bonuses for high win rates
        # Penalize low RR even if RR>1
        avg_duration_hours = sum(r['duration_minutes'] for r in sim_results) / len(sim_results) / 60

        # Duration score (prefer <6h, penalize >12h)
        if avg_duration_hours <= cls.OPTIMAL_DURATION_HOURS:
            duration_score = 1.0  # Perfect duration
        elif avg_duration_hours <= 12.0:
            duration_score = 1.0 - (avg_duration_hours - cls.OPTIMAL_DURATION_HOURS) / 12.0
        else:
            duration_score = max(0, 1.0 - (avg_duration_hours - 12.0) / 12.0)

        # Win rate score with bonuses
        normalized_wr = win_rate / 100
        wr_score = normalized_wr

        # Add bonuses for high win rates
        if win_rate >= cls.HIGH_WIN_RATE_PCT:  # ≥70%
            wr_score *= 1.3  # 30% bonus for very high WR
        elif win_rate >= cls.TARGET_WIN_RATE_PCT:  # ≥65%
            wr_score *= 1.15  # 15% bonus for target WR

        # Risk/Reward score with penalty for low RR
        # Even if RR>1, we prefer higher RR for safety
        if risk_reward >= 2.0:
            rr_score = 1.0  # Excellent RR
        elif risk_reward >= 1.5:
            rr_score = 0.8 + (risk_reward - 1.5) * 0.4  # Scale 0.8-1.0
        elif risk_reward > 1.0:
            rr_score = 0.5 + (risk_reward - 1.0) * 0.6  # Scale 0.5-0.8
        else:
            rr_score = 0.0  # Should be filtered already

        # === MFE/MAE-based adjustment ===
        # Use baseline trade MFE/MAE data to adjust scoring
        mfe_mae_factor = cls._calculate_mfe_mae_factor(baseline_trades, tp_pct, sl_pct)

        # Final HIGH-WR composite score
        # Weights: WR=65%, RR=20%, Duration=15%
        composite_score = (
            (wr_score ** 0.65) *      # Win rate: 65% weight
            (rr_score ** 0.20) *       # Risk/Reward: 20% weight
            (duration_score ** 0.15) * # Duration: 15% weight
            mfe_mae_factor             # MFE/MAE adjustment
        )

        # Apply expected value boost/penalty
        if expected_value > 0:
            ev_multiplier = 1.0 + min(0.2, expected_value / 10.0)  # Up to 20% boost
        else:
            ev_multiplier = 0.8  # 20% penalty for negative EV

        composite_score *= ev_multiplier

        return GridSearchResult(
            strategy_params=strategy,
            risk_reward=round(risk_reward, 4),
            win_rate=round(win_rate, 2),
            composite_score=round(composite_score, 4),
            avg_win=round(avg_win, 4),
            avg_loss=round(avg_loss, 4),
            avg_duration_hours=round(avg_duration_hours, 2),
            trades_tested=len(sim_results),
            win_count=len(wins),
            loss_count=len(losses)
        )

    @classmethod
    def _calculate_mfe_mae_factor(
        cls,
        baseline_trades: List[TradeSetup],
        tp_pct: float,
        sl_pct: float
    ) -> float:
        """
        Calculate adjustment factor based on MFE/MAE data
        Estimates how often this TP/SL would hit based on historical excursions

        Returns: 0.8-1.2 factor
        """
        if not baseline_trades:
            return 1.0

        # Count trades where MFE would hit TP
        tp_hit_count = 0
        sl_hit_count = 0

        for trade in baseline_trades:
            if not trade:
                continue

            # Get MFE from milestones if available
            max_profit_pct = 0
            max_drawdown_pct = 0

            if hasattr(trade, 'milestones') and trade.milestones:
                for milestone in trade.milestones:
                    if milestone.price_pct:
                        if milestone.price_pct > max_profit_pct:
                            max_profit_pct = milestone.price_pct
                        if milestone.price_pct < max_drawdown_pct:
                            max_drawdown_pct = milestone.price_pct
            elif hasattr(trade, 'max_favorable_excursion') and trade.max_favorable_excursion:
                # Fallback to MFE field
                entry_price = trade.entry_price
                if entry_price and entry_price > 0:
                    max_profit_pct = ((trade.max_favorable_excursion - entry_price) / entry_price) * 100

            # Check if TP would hit
            if max_profit_pct >= tp_pct:
                tp_hit_count += 1

            # Check if SL would hit (before TP)
            if abs(max_drawdown_pct) >= abs(sl_pct):
                sl_hit_count += 1

        total_trades = len(baseline_trades)
        tp_hit_rate = tp_hit_count / total_trades if total_trades > 0 else 0
        sl_hit_rate = sl_hit_count / total_trades if total_trades > 0 else 0

        # Calculate factor
        # High TP hit rate = good
        # Low SL hit rate = good
        factor = 1.0

        if tp_hit_rate > 0.7:  # >70% would hit TP
            factor *= 1.1
        elif tp_hit_rate < 0.3:  # <30% would hit TP
            factor *= 0.9

        if sl_hit_rate < 0.3:  # <30% would hit SL
            factor *= 1.1
        elif sl_hit_rate > 0.5:  # >50% would hit SL
            factor *= 0.9

        return min(1.2, max(0.8, factor))

    @classmethod
    def _meets_minimum_thresholds(cls, metrics: GridSearchResult) -> bool:
        """
        Check if strategy meets minimum thresholds for HIGH-WR optimization

        Requirements:
        - Win Rate >= 60%
        - Risk/Reward > 1.0
        - Expected Value > 0
        - Average Duration <= 24h
        """
        # Check win rate
        if metrics['win_rate'] < cls.MIN_WIN_RATE_PCT:
            return False

        # Check risk/reward
        if metrics['risk_reward'] <= cls.MIN_RISK_REWARD:
            return False

        # Check expected value
        win_rate_decimal = metrics['win_rate'] / 100
        expected_value = (win_rate_decimal * metrics['avg_win']) + ((1 - win_rate_decimal) * metrics['avg_loss'])
        if expected_value <= cls.MIN_EXPECTED_VALUE:
            return False

        # Check duration
        if metrics['avg_duration_hours'] > cls.MAX_DURATION_HOURS:
            return False

        return True

    @classmethod
    def calculate_strategy_score_high_wr(
        cls,
        win_rate: float,
        rr_ratio: float,
        expected_value: float,
        duration_hours: float
    ) -> float:
        """
        Public scoring function for HIGH-WR optimization
        Can be used by other components

        Args:
            win_rate: Win rate percentage (0-100)
            rr_ratio: Risk/reward ratio
            expected_value: Expected value per trade
            duration_hours: Average trade duration

        Returns:
            Composite score (0-1+ range)
        """
        # Win rate score with bonuses
        normalized_wr = win_rate / 100
        wr_score = normalized_wr

        if win_rate >= cls.HIGH_WIN_RATE_PCT:
            wr_score *= 1.3
        elif win_rate >= cls.TARGET_WIN_RATE_PCT:
            wr_score *= 1.15

        # RR score
        if rr_ratio >= 2.0:
            rr_score = 1.0
        elif rr_ratio >= 1.5:
            rr_score = 0.8 + (rr_ratio - 1.5) * 0.4
        elif rr_ratio > 1.0:
            rr_score = 0.5 + (rr_ratio - 1.0) * 0.6
        else:
            rr_score = 0.0

        # Duration score
        if duration_hours <= cls.OPTIMAL_DURATION_HOURS:
            duration_score = 1.0
        elif duration_hours <= 12.0:
            duration_score = 1.0 - (duration_hours - cls.OPTIMAL_DURATION_HOURS) / 12.0
        else:
            duration_score = max(0, 1.0 - (duration_hours - 12.0) / 12.0)

        # Composite score
        composite = (
            (wr_score ** 0.65) *
            (rr_score ** 0.20) *
            (duration_score ** 0.15)
        )

        # EV adjustment
        if expected_value > 0:
            ev_multiplier = 1.0 + min(0.2, expected_value / 10.0)
        else:
            ev_multiplier = 0.8

        return composite * ev_multiplier