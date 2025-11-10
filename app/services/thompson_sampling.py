"""
Thompson Sampling Strategy Allocation Service - High Win Rate Optimization

This module implements Thompson Sampling with strong preference for high win-rate strategies.
Optimized to aggressively allocate capital to proven winners while maintaining minimal
exploration for underperformers.

Key Features:
- High-WR focused scoring: (RR^0.25) × (WR^0.75) with bonus multipliers
- Dynamic minimum allocations based on win rate tiers
- Increased exploitation temperature for stronger winner-take-all behavior
- Configurable modes for different market conditions
"""

import math
import random
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ThompsonSamplingConfig:
    """Configuration for Thompson Sampling allocation"""

    # Scoring weights - HIGH WIN RATE OPTIMIZATION
    rr_weight: float = 0.25  # Reduced from 0.4 (less emphasis on RR)
    wr_weight: float = 0.75  # Increased from 0.6 (more emphasis on WR)

    # Win rate bonus multipliers (adjusted to prevent over-allocation)
    wr_bonus_threshold_high: float = 70.0  # WR > 70% gets 1.3x bonus (reduced from 1.5x)
    wr_bonus_multiplier_high: float = 1.3  # Reduced to achieve target 40-45%
    wr_bonus_threshold_medium: float = 65.0  # WR > 65% gets 1.15x bonus (reduced from 1.2x)
    wr_bonus_multiplier_medium: float = 1.15  # Reduced to achieve target

    # Temperature for softmax (adjusted for target allocations)
    temperature: float = 2.2  # Slightly increased from 2.0, but not as high as 3.0

    # Dynamic minimum allocations based on win rate
    min_alloc_wr_high: float = 0.15  # WR > 65%: 15% minimum (increased from 10%)
    min_alloc_wr_medium: float = 0.10  # WR 60-65%: 10% minimum
    min_alloc_wr_low: float = 0.05  # WR 55-60%: 5% minimum
    min_alloc_wr_very_low: float = 0.02  # WR < 55%: 2% minimum (reduced from 10%)

    # Win rate thresholds for minimum allocation tiers
    wr_threshold_high: float = 65.0
    wr_threshold_medium: float = 60.0
    wr_threshold_low: float = 55.0

    # Mode settings
    mode: str = 'high_wr'  # Options: 'high_wr', 'balanced', 'exploration'

    # Duration penalty settings (from original config)
    duration_penalty_threshold_hours: float = 12.0
    duration_penalty_scale_hours: float = 24.0

    # Safety limits
    max_score_cap: float = 100.0  # Cap scores to prevent overflow
    min_trades_for_scoring: int = 5  # Minimum trades before using performance score


class ThompsonSampler:
    """Thompson Sampling implementation optimized for high win rate strategies"""

    def __init__(self, config: Optional[ThompsonSamplingConfig] = None):
        """
        Initialize Thompson Sampler with configuration

        Args:
            config: Configuration object, defaults to high-WR optimized settings
        """
        self.config = config or ThompsonSamplingConfig()

    def calculate_strategy_score(
        self,
        win_rate: float,
        risk_reward: float,
        avg_duration_hours: float,
        trades_analyzed: int
    ) -> float:
        """
        Calculate composite score for a strategy with high-WR optimization

        Formula: (RR^0.25) × (WR^0.75) × duration_penalty × wr_bonus

        Args:
            win_rate: Win percentage (0-100)
            risk_reward: Risk/reward ratio
            avg_duration_hours: Average trade duration
            trades_analyzed: Number of trades used for statistics

        Returns:
            Composite score (higher is better)
        """
        # Skip if insufficient data
        if trades_analyzed < self.config.min_trades_for_scoring:
            return 0.0

        # Normalize win rate to 0-1 range
        wr_normalized = win_rate / 100.0

        # Calculate base score with new weights
        # HIGH-WR OPTIMIZATION: Reduced RR weight, increased WR weight
        base_score = (
            math.pow(max(risk_reward, 0.1), self.config.rr_weight) *
            math.pow(wr_normalized, self.config.wr_weight)
        )

        # Apply duration penalty (same as original)
        if avg_duration_hours > self.config.duration_penalty_threshold_hours:
            excess_hours = avg_duration_hours - self.config.duration_penalty_threshold_hours
            penalty_factor = 1.0 - min(excess_hours / self.config.duration_penalty_scale_hours, 1.0)
            base_score *= penalty_factor

        # Apply WIN RATE BONUS MULTIPLIERS
        if win_rate > self.config.wr_bonus_threshold_high:
            base_score *= self.config.wr_bonus_multiplier_high
        elif win_rate > self.config.wr_bonus_threshold_medium:
            base_score *= self.config.wr_bonus_multiplier_medium

        return base_score

    def get_minimum_allocation(self, win_rate: float) -> float:
        """
        Get dynamic minimum allocation based on win rate tier

        Args:
            win_rate: Win percentage (0-100)

        Returns:
            Minimum allocation probability
        """
        if win_rate > self.config.wr_threshold_high:
            return self.config.min_alloc_wr_high  # 15% for WR > 65%
        elif win_rate > self.config.wr_threshold_medium:
            return self.config.min_alloc_wr_medium  # 10% for WR 60-65%
        elif win_rate > self.config.wr_threshold_low:
            return self.config.min_alloc_wr_low  # 5% for WR 55-60%
        else:
            return self.config.min_alloc_wr_very_low  # 2% for WR < 55%

    def allocate_probabilities(self, strategies: List[Dict]) -> List[Tuple[str, float]]:
        """
        Calculate allocation probabilities for all strategies

        Args:
            strategies: List of strategy dictionaries with performance metrics

        Returns:
            List of (strategy_name, probability) tuples
        """
        if not strategies:
            return []

        # Calculate scores for each strategy
        scores = []
        for strategy in strategies:
            score = self.calculate_strategy_score(
                win_rate=strategy.get('win_rate', 0),
                risk_reward=strategy.get('risk_reward', 0),
                avg_duration_hours=strategy.get('avg_duration_hours', 0),
                trades_analyzed=strategy.get('trades_analyzed', 0)
            )
            scores.append(score)

        # Handle case where all scores are zero
        total_score = sum(scores)
        if total_score == 0:
            # Equal allocation if no data
            probabilities = [1.0 / len(strategies)] * len(strategies)
            logger.info("No performance data available, using equal allocation")
        else:
            # Softmax with INCREASED TEMPERATURE for stronger exploitation
            capped_scores = [min(s, self.config.max_score_cap) for s in scores]
            exp_scores = [math.exp(s * self.config.temperature) for s in capped_scores]
            sum_exp = sum(exp_scores)
            probabilities = [e / sum_exp for e in exp_scores]

        # Apply DYNAMIC MINIMUM ALLOCATIONS based on win rate
        adjusted_probabilities = []
        for i, strategy in enumerate(strategies):
            win_rate = strategy.get('win_rate', 0)
            min_alloc = self.get_minimum_allocation(win_rate)
            adjusted_prob = max(probabilities[i], min_alloc)
            adjusted_probabilities.append(adjusted_prob)

            if probabilities[i] < min_alloc:
                logger.debug(
                    f"Strategy {strategy.get('strategy_name')}: "
                    f"Adjusted from {probabilities[i]:.3f} to {min_alloc:.3f} "
                    f"(min for WR={win_rate:.1f}%)"
                )

        # Renormalize to sum to 1.0
        total_prob = sum(adjusted_probabilities)
        normalized_probabilities = [p / total_prob for p in adjusted_probabilities]

        # Create result with strategy names
        result = [
            (strategy.get('strategy_name', f'strategy_{i}'), prob)
            for i, (strategy, prob) in enumerate(zip(strategies, normalized_probabilities))
        ]

        # Log allocation summary (commented out to avoid excessive logging in production)
        # Uncomment for debugging
        # self._log_allocation_summary(result, strategies)

        return result

    def select_strategy(self, strategies: List[Dict]) -> str:
        """
        Select a strategy using Thompson Sampling with high-WR optimization

        Args:
            strategies: List of strategy dictionaries with performance metrics

        Returns:
            Name of selected strategy
        """
        if not strategies:
            raise ValueError("No strategies provided for selection")

        # Get allocation probabilities
        allocations = self.allocate_probabilities(strategies)

        # Sample based on probabilities
        rand = random.random()
        cumulative = 0.0

        for strategy_name, probability in allocations:
            cumulative += probability
            if rand < cumulative:
                # Log selection at debug level to reduce noise
                logger.debug(
                    f"Selected {strategy_name} "
                    f"(allocation: {probability:.1%})"
                )
                return strategy_name

        # Fallback (should not reach here)
        return allocations[0][0]

    def _log_allocation_summary(self, allocations: List[Tuple[str, float]], strategies: List[Dict]):
        """Log allocation summary for monitoring"""
        logger.info("=" * 60)
        logger.info("THOMPSON SAMPLING ALLOCATION (HIGH-WR MODE)")
        logger.info("-" * 60)

        for (name, prob), strategy in zip(allocations, strategies):
            wr = strategy.get('win_rate', 0)
            rr = strategy.get('risk_reward', 0)
            score = strategy.get('strategy_score', 0)

            # Determine if bonus was applied
            bonus = ""
            if wr > self.config.wr_bonus_threshold_high:
                bonus = " [1.5x BONUS]"
            elif wr > self.config.wr_bonus_threshold_medium:
                bonus = " [1.2x BONUS]"

            logger.info(
                f"{name:15s}: {prob:6.1%} allocation | "
                f"WR: {wr:5.1f}% | RR: {rr:4.2f} | Score: {score:6.3f}{bonus}"
            )

        logger.info("=" * 60)

        # Verify expected allocation ranges (only log once per batch)
        if len(allocations) > 0:
            sorted_strategies = sorted(
                zip(allocations, strategies),
                key=lambda x: x[1].get('win_rate', 0),
                reverse=True
            )

            if sorted_strategies:
                top_strategy = sorted_strategies[0]
                top_wr = top_strategy[1].get('win_rate', 0)
                top_alloc = top_strategy[0][1] * 100

                # Only log significant deviations from expectations
                if top_wr >= 75 and (top_alloc < 35 or top_alloc > 50):
                    logger.debug(
                        f"Allocation check: Top strategy (WR={top_wr:.1f}%) has {top_alloc:.1f}% allocation "
                        f"(target: 40-45%)"
                    )

    def get_expected_allocations(self, win_rates: List[float]) -> Dict[str, str]:
        """
        Get expected allocation ranges for given win rates

        Args:
            win_rates: List of win rate percentages

        Returns:
            Dictionary of expected allocation ranges
        """
        expectations = {}

        for wr in sorted(win_rates, reverse=True):
            if wr >= 75:
                expectations[f"WR {wr:.0f}%"] = "40-45% allocation"
            elif wr >= 70:
                expectations[f"WR {wr:.0f}%"] = "25-30% allocation"
            elif wr >= 65:
                expectations[f"WR {wr:.0f}%"] = "15-20% allocation"
            elif wr >= 60:
                expectations[f"WR {wr:.0f}%"] = "10-15% allocation"
            else:
                expectations[f"WR {wr:.0f}%"] = "2-5% allocation"

        return expectations


# Module-level convenience function for backward compatibility
def thompson_sampling_select(strategies: List[Dict], config: Optional[ThompsonSamplingConfig] = None) -> str:
    """
    Select a strategy using Thompson Sampling

    Args:
        strategies: List of strategy performance dictionaries
        config: Optional configuration (uses high-WR defaults if not provided)

    Returns:
        Name of selected strategy
    """
    sampler = ThompsonSampler(config)
    return sampler.select_strategy(strategies)


# Export for use in StrategySelector
__all__ = [
    'ThompsonSampler',
    'ThompsonSamplingConfig',
    'thompson_sampling_select'
]