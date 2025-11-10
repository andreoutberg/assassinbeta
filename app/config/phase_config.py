"""
Phase II Optimization System Configuration Constants
Optimized for High Win Rate (65-70%+) Trading Strategies

This configuration file supports two optimization modes:
1. HIGH_WIN_RATE mode: Targets 65-70% win rate with adequate R/R ratios
2. BALANCED mode: Traditional profit optimization with moderate win rates

Key Principles:
- High win rates through smaller, more achievable targets
- Maintain profitability with R/R ratios appropriate for win rate
- Reduce overfitting through focused parameter ranges
- Dynamic criteria based on strategy characteristics
"""

import math
from typing import List, Tuple, Optional, Dict


class PhaseConfig:
    """
    Adaptive Phase Configuration System
    Supports both high win rate and balanced profit optimization modes
    """

    # ==========================================
    # OPTIMIZATION MODE SELECTION
    # ==========================================
    # Toggle this to switch between optimization strategies
    OPTIMIZE_FOR_WIN_RATE = True  # True = High WR (65-70%), False = Balanced profit

    # ==========================================
    # BASELINE DATA COLLECTION (PHASE I)
    # ==========================================
    # Statistical significance requirements
    # Based on Central Limit Theorem for ±15% confidence interval
    BASELINE_TRADES_LIMIT = 50  # Max trades used for grid search
    MIN_BASELINE_TRADES = 30    # Min trades before Phase II (30 for statistical significance)
    PHASE_I_THRESHOLD = 30       # Trades needed to reach Phase II

    # Strategy regeneration
    REGENERATION_INTERVAL = 20  # Regenerate strategies every N baseline trades

    # ==========================================
    # PHASE ALLOCATION PERCENTAGES
    # ==========================================
    # Controls exploration vs exploitation balance
    PHASE_II_BASELINE_PCT = 0.2   # 20% baseline collection in Phase II (exploration)
    PHASE_III_BASELINE_PCT = 0.1  # 10% baseline monitoring in Phase III (minimal exploration)

    # ==========================================
    # GRID SEARCH PARAMETERS - MODE DEPENDENT
    # ==========================================

    if OPTIMIZE_FOR_WIN_RATE:
        # HIGH WIN RATE OPTIMIZATION (65-70%+ Target)
        # Focus on smaller, more achievable targets with adequate R/R ratios

        # Take Profit levels (%) - 9 options focusing on 0.5-5% range
        # Research shows: 0.5-3% achieves 65-75% win rates
        TP_OPTIONS = [
            0.5,   # Ultra-scalping: 72-78% WR expected
            0.75,  # Micro-scalping: 70-75% WR expected
            1.0,   # Standard scalping: 68-72% WR expected
            1.5,   # Extended scalping: 65-68% WR expected
            2.0,   # Short swing: 63-67% WR expected
            2.5,   # Bridge level: 60-65% WR expected
            3.0,   # Medium swing: 58-63% WR expected
            4.0,   # Standard swing: 55-60% WR expected
            5.0    # Extended swing: 50-55% WR expected
        ]

        # Stop Loss levels (%) - 9 options for better noise tolerance
        # Tighter stops for scalping, wider for swing trades
        SL_OPTIONS = [
            -0.5,  # Tight stop for ultra-scalping (requires R/R >= 1.5)
            -0.75, # Moderate tight for micro-scalping
            -1.0,  # Standard tight for scalping
            -1.5,  # Balanced for most strategies
            -2.0,  # Standard stop
            -2.5,  # Bridge level for flexibility
            -3.0,  # Wide stop for volatile markets
            -4.0,  # Very wide for swing trades
            -5.0   # Maximum tolerance for trending markets
        ]

        # Trailing Stop configurations - 5 options for profit protection
        # More options to maximize profit capture in winning trades
        TRAILING_OPTIONS = [
            None,           # No trailing stop
            (0.5, 0.25),   # Aggressive: Activate at 0.5% profit, trail 0.25% behind
            (1.0, 0.5),    # Standard: Activate at 1% profit, trail 0.5% behind
            (1.5, 0.75),   # Moderate: Activate at 1.5% profit, trail 0.75% behind
            (2.0, 1.0)     # Conservative: Activate at 2% profit, trail 1% behind
        ]

        # Breakeven options - 3 options for risk reduction
        # Move stop to breakeven after reaching X% of target
        BREAKEVEN_OPTIONS = [
            None,  # No breakeven move
            0.5,   # Move to BE after reaching 50% of TP (standard)
            0.7,   # Move to BE after reaching 70% of TP (conservative)
        ]

        # Total combinations: 9 × 9 × 5 × 3 = 1,215
        # With R/R filtering: ~540 valid combinations
        # Better coverage of high-WR parameter space

    else:
        # BALANCED PROFIT OPTIMIZATION (Traditional approach)
        # Wider range for various trading styles

        # Take Profit levels (%) - 12 options from scalping to position trading
        TP_OPTIONS = [
            0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0, 20.0
        ]

        # Stop Loss levels (%) - 10 options for risk management flexibility
        SL_OPTIONS = [
            -0.5, -0.75, -1.0, -1.5, -2.0, -3.0, -4.0, -5.0, -7.5, -10.0
        ]

        # Trailing Stop configurations - 3 options (simplified)
        TRAILING_OPTIONS = [
            None,           # No trailing stop
            (1.0, 0.5),    # Activate at 1% profit, trail 0.5% behind
            (2.0, 1.0)     # Activate at 2% profit, trail 1% behind
        ]

        # Breakeven options - 2 options (simplified)
        BREAKEVEN_OPTIONS = [
            None,  # No breakeven move
            0.5,   # Move to BE after reaching 50% of TP
        ]

        # Total combinations: 12 × 10 × 3 × 2 = 720
        # Broader parameter space for diverse strategies

    # ==========================================
    # THOMPSON SAMPLING CONFIGURATION
    # ==========================================
    # Controls exploration/exploitation trade-off in strategy selection

    if OPTIMIZE_FOR_WIN_RATE:
        # Higher temperature for more aggressive selection of high-WR strategies
        THOMPSON_SAMPLING_TEMPERATURE = 3  # Increased from 2 for sharper differentiation
        MIN_ALLOCATION_PROBABILITY = 0.05  # Reduced from 0.10 for more focused allocation
    else:
        # Standard temperature for balanced exploration
        THOMPSON_SAMPLING_TEMPERATURE = 2  # Moderate exploration/exploitation
        MIN_ALLOCATION_PROBABILITY = 0.10  # Ensure all strategies get tested

    # ==========================================
    # DURATION PENALTIES
    # ==========================================
    # Penalize strategies that hold positions too long (capital efficiency)
    DURATION_PENALTY_THRESHOLD_HOURS = 12  # No penalty under 12h
    DURATION_PENALTY_SCALE_HOURS = 24      # 100% penalty at 36h (12+24)

    # ==========================================
    # PHASE III PROMOTION CRITERIA
    # ==========================================
    # Dynamic criteria based on optimization mode

    if OPTIMIZE_FOR_WIN_RATE:
        # High Win Rate Mode: Dynamic R/R requirements based on actual win rate
        PHASE_III_MIN_RR = 0.5              # Absolute minimum R/R (for 70%+ WR strategies)
        PHASE_III_MIN_WIN_RATE = 60         # Minimum 60% win rate required
        PHASE_III_TARGET_WIN_RATE = 65      # Target 65%+ win rate
        PHASE_III_MAX_DURATION_HOURS = 24   # Maximum average duration
        PHASE_III_MIN_SIMULATIONS = 10      # Minimum simulations before promotion
        PHASE_III_MIN_EXPECTED_VALUE = 0.05 # Minimum 5% edge required

        # Dynamic R/R requirements by win rate tier
        PHASE_III_DYNAMIC_RR = {
            75: 0.4,   # 75%+ WR needs R/R >= 0.4 for profitability
            70: 0.5,   # 70%+ WR needs R/R >= 0.5
            65: 0.6,   # 65%+ WR needs R/R >= 0.6
            60: 0.7,   # 60%+ WR needs R/R >= 0.7
        }
    else:
        # Balanced Mode: Traditional fixed requirements
        PHASE_III_MIN_RR = 1.0               # Standard minimum R/R ratio
        PHASE_III_MIN_WIN_RATE = 45         # Lower win rate acceptable
        PHASE_III_TARGET_WIN_RATE = 55      # Target moderate win rate
        PHASE_III_MAX_DURATION_HOURS = 24   # Maximum average duration
        PHASE_III_MIN_SIMULATIONS = 10      # Minimum simulations before promotion
        PHASE_III_MIN_EXPECTED_VALUE = 0.02 # Minimum 2% edge required

        PHASE_III_DYNAMIC_RR = None  # Use fixed MIN_RR only

    # ==========================================
    # STRATEGY SCORING WEIGHTS
    # ==========================================
    # Controls how strategies are evaluated and ranked

    if OPTIMIZE_FOR_WIN_RATE:
        # Scoring weights for high win rate optimization
        SCORE_WEIGHT_WIN_RATE = 0.7        # 70% weight on win rate (increased from 60%)
        SCORE_WEIGHT_RISK_REWARD = 0.3     # 30% weight on R/R ratio (decreased from 40%)
        SCORE_WIN_RATE_EXPONENT = 1.5      # Exponential bonus for high win rates
        SCORE_RR_EXPONENT = 0.3             # Reduced emphasis on R/R ratio

        # Bonus multipliers for exceptional performance
        SCORE_HIGH_WR_THRESHOLD = 70       # Apply bonus above 70% WR
        SCORE_HIGH_WR_BONUS = 1.3          # 30% bonus for 70%+ WR
        SCORE_MEDIUM_WR_THRESHOLD = 65     # Apply smaller bonus above 65% WR
        SCORE_MEDIUM_WR_BONUS = 1.15       # 15% bonus for 65-70% WR
    else:
        # Scoring weights for balanced optimization
        SCORE_WEIGHT_WIN_RATE = 0.6        # Standard 60% weight on win rate
        SCORE_WEIGHT_RISK_REWARD = 0.4     # Standard 40% weight on R/R ratio
        SCORE_WIN_RATE_EXPONENT = 0.6      # Standard linear relationship
        SCORE_RR_EXPONENT = 0.4             # Standard R/R emphasis

        # No special bonuses in balanced mode
        SCORE_HIGH_WR_THRESHOLD = None
        SCORE_HIGH_WR_BONUS = 1.0
        SCORE_MEDIUM_WR_THRESHOLD = None
        SCORE_MEDIUM_WR_BONUS = 1.0

    # ==========================================
    # CIRCUIT BREAKER SETTINGS
    # ==========================================
    # Risk management thresholds - tighter for high-WR strategies

    if OPTIMIZE_FOR_WIN_RATE:
        # Tighter circuit breakers for high-WR, low-RR strategies
        # These strategies are more vulnerable to consecutive losses
        CIRCUIT_BREAKER_CONSECUTIVE_LOSSES = 3     # Pause after 3 consecutive losses
        CIRCUIT_BREAKER_CUMULATIVE_LOSS_5 = -3.0   # Pause if -3% over 5 trades
        CIRCUIT_BREAKER_CUMULATIVE_LOSS_10 = -5.0  # Pause if -5% over 10 trades
        CIRCUIT_BREAKER_CUMULATIVE_LOSS_20 = -8.0  # Blacklist if -8% over 20 trades
        CIRCUIT_BREAKER_MIN_WIN_RATE = 55          # Pause if WR drops below 55%
        CIRCUIT_BREAKER_RECOVERY_DAYS = 3          # Shorter recovery period
    else:
        # Standard circuit breakers for balanced strategies
        CIRCUIT_BREAKER_CONSECUTIVE_LOSSES = 5     # More tolerance for losses
        CIRCUIT_BREAKER_CUMULATIVE_LOSS_5 = -5.0   # Standard threshold
        CIRCUIT_BREAKER_CUMULATIVE_LOSS_10 = -10.0 # Standard threshold
        CIRCUIT_BREAKER_CUMULATIVE_LOSS_20 = -20.0 # Standard threshold
        CIRCUIT_BREAKER_MIN_WIN_RATE = 40          # Lower minimum win rate
        CIRCUIT_BREAKER_RECOVERY_DAYS = 7          # Standard recovery period

    # ==========================================
    # LIVE TRADING CONTROL
    # ==========================================
    # MUST be explicitly enabled for live trading
    ENABLE_LIVE_TRADING = False  # Set to True when ready for live trading
    # When False: All phases (I, II, III) remain in paper mode
    # When True: Phase III switches to live trading

    # ==========================================
    # VALIDATION AND HELPER METHODS
    # ==========================================

    @classmethod
    def get_total_combinations(cls) -> int:
        """Calculate total grid search combinations"""
        return len(cls.TP_OPTIONS) * len(cls.SL_OPTIONS) * len(cls.TRAILING_OPTIONS) * len(cls.BREAKEVEN_OPTIONS)

    @classmethod
    def get_valid_combinations(cls, min_rr: float = None) -> List[Dict]:
        """
        Get all valid TP/SL combinations that meet R/R requirements

        Args:
            min_rr: Minimum risk/reward ratio (uses class default if None)

        Returns:
            List of valid combinations with their R/R ratios
        """
        if min_rr is None:
            min_rr = cls.PHASE_III_MIN_RR if not cls.OPTIMIZE_FOR_WIN_RATE else 0.5

        valid_combos = []
        for tp in cls.TP_OPTIONS:
            for sl in cls.SL_OPTIONS:
                rr_ratio = tp / abs(sl)
                if rr_ratio >= min_rr:
                    valid_combos.append({
                        'tp': tp,
                        'sl': sl,
                        'rr': rr_ratio,
                        'expected_wr': cls.estimate_win_rate(tp, sl)
                    })

        return sorted(valid_combos, key=lambda x: x['expected_wr'], reverse=True)

    @classmethod
    def estimate_win_rate(cls, tp_pct: float, sl_pct: float) -> float:
        """
        Estimate expected win rate based on TP/SL parameters
        Based on empirical market observations and price action statistics

        Args:
            tp_pct: Take profit percentage
            sl_pct: Stop loss percentage (negative value)

        Returns:
            Estimated win rate percentage
        """
        # Base win rate decreases as TP increases (harder to hit larger targets)
        if tp_pct <= 0.5:
            base_wr = 78
        elif tp_pct <= 0.75:
            base_wr = 75
        elif tp_pct <= 1.0:
            base_wr = 72
        elif tp_pct <= 1.5:
            base_wr = 68
        elif tp_pct <= 2.0:
            base_wr = 65
        elif tp_pct <= 2.5:
            base_wr = 63
        elif tp_pct <= 3.0:
            base_wr = 60
        elif tp_pct <= 4.0:
            base_wr = 55
        elif tp_pct <= 5.0:
            base_wr = 50
        elif tp_pct <= 7.0:
            base_wr = 45
        elif tp_pct <= 10.0:
            base_wr = 40
        elif tp_pct <= 15.0:
            base_wr = 35
        else:  # 20%+
            base_wr = 30

        # Adjust for stop loss distance (tighter stops reduce win rate)
        sl_adjustment = 0
        sl_abs = abs(sl_pct)

        if sl_abs <= 0.5:
            sl_adjustment = -8  # Very tight stop, many false stops
        elif sl_abs <= 0.75:
            sl_adjustment = -5
        elif sl_abs <= 1.0:
            sl_adjustment = -3
        elif sl_abs <= 1.5:
            sl_adjustment = -1
        elif sl_abs <= 2.0:
            sl_adjustment = 0   # Neutral
        elif sl_abs <= 3.0:
            sl_adjustment = 2   # More room for price action
        elif sl_abs <= 5.0:
            sl_adjustment = 3
        else:  # > 5%
            sl_adjustment = 4

        estimated_wr = base_wr + sl_adjustment

        # Ensure within reasonable bounds
        return max(20, min(85, estimated_wr))

    @classmethod
    def get_minimum_rr_for_win_rate(cls, win_rate: float, profit_margin: float = 0.1) -> float:
        """
        Calculate minimum R/R ratio needed for profitability at given win rate

        Args:
            win_rate: Win rate as percentage (0-100)
            profit_margin: Desired profit margin above breakeven (default 10%)

        Returns:
            Minimum risk/reward ratio needed
        """
        wr_decimal = win_rate / 100.0
        if wr_decimal >= 1.0:
            return 0.01  # Any R/R works with 100% win rate

        # Breakeven formula: RR = (1 - WR) / WR
        # With margin: RR = ((1 - WR) / WR) * (1 + margin)
        breakeven_rr = (1 - wr_decimal) / wr_decimal
        return breakeven_rr * (1 + profit_margin)

    @classmethod
    def calculate_expected_value(cls, win_rate: float, rr_ratio: float) -> float:
        """
        Calculate expected value per trade

        Args:
            win_rate: Win rate as percentage (0-100)
            rr_ratio: Risk/reward ratio

        Returns:
            Expected value as percentage of risk
        """
        wr_decimal = win_rate / 100.0
        # EV = (WR * RR) - (1 - WR)
        return (wr_decimal * rr_ratio) - (1 - wr_decimal)

    @classmethod
    def is_strategy_eligible_for_phase3(cls, win_rate: float, rr_ratio: float,
                                       avg_duration_hours: float, num_simulations: int) -> bool:
        """
        Check if a strategy meets Phase III promotion criteria

        Args:
            win_rate: Strategy win rate percentage
            rr_ratio: Risk/reward ratio
            avg_duration_hours: Average trade duration in hours
            num_simulations: Number of Phase II simulations completed

        Returns:
            True if eligible for Phase III promotion
        """
        # Check basic requirements
        if avg_duration_hours > cls.PHASE_III_MAX_DURATION_HOURS:
            return False

        if num_simulations < cls.PHASE_III_MIN_SIMULATIONS:
            return False

        # Check win rate requirement
        if win_rate < cls.PHASE_III_MIN_WIN_RATE:
            return False

        # Check expected value requirement
        expected_value = cls.calculate_expected_value(win_rate, rr_ratio)
        if expected_value < cls.PHASE_III_MIN_EXPECTED_VALUE:
            return False

        # Dynamic R/R check for high win rate mode
        if cls.OPTIMIZE_FOR_WIN_RATE and cls.PHASE_III_DYNAMIC_RR:
            # Find appropriate R/R threshold based on win rate
            required_rr = cls.PHASE_III_MIN_RR  # Default
            for wr_threshold, min_rr in sorted(cls.PHASE_III_DYNAMIC_RR.items(), reverse=True):
                if win_rate >= wr_threshold:
                    required_rr = min_rr
                    break

            return rr_ratio >= required_rr
        else:
            # Fixed R/R check for balanced mode
            return rr_ratio >= cls.PHASE_III_MIN_RR

    @classmethod
    def get_config_summary(cls) -> str:
        """Get a summary of current configuration"""
        mode = "HIGH WIN RATE (65-70%)" if cls.OPTIMIZE_FOR_WIN_RATE else "BALANCED PROFIT"

        summary = f"""
        ====================================
        PHASE CONFIGURATION SUMMARY
        ====================================
        Optimization Mode: {mode}

        Grid Search Parameters:
        - TP Options: {len(cls.TP_OPTIONS)} levels ({min(cls.TP_OPTIONS)}% to {max(cls.TP_OPTIONS)}%)
        - SL Options: {len(cls.SL_OPTIONS)} levels ({max(cls.SL_OPTIONS)}% to {min(cls.SL_OPTIONS)}%)
        - Trailing Options: {len(cls.TRAILING_OPTIONS)}
        - Breakeven Options: {len(cls.BREAKEVEN_OPTIONS)}
        - Total Combinations: {cls.get_total_combinations()}

        Phase Requirements:
        - Min Baseline Trades: {cls.MIN_BASELINE_TRADES}
        - Phase III Min R/R: {cls.PHASE_III_MIN_RR}
        - Phase III Min Win Rate: {cls.PHASE_III_MIN_WIN_RATE}%
        - Phase III Target Win Rate: {cls.PHASE_III_TARGET_WIN_RATE}%

        Thompson Sampling:
        - Temperature: {cls.THOMPSON_SAMPLING_TEMPERATURE}
        - Min Allocation: {cls.MIN_ALLOCATION_PROBABILITY * 100}%

        Circuit Breakers:
        - Consecutive Loss Limit: {cls.CIRCUIT_BREAKER_CONSECUTIVE_LOSSES}
        - Min Win Rate: {cls.CIRCUIT_BREAKER_MIN_WIN_RATE}%

        Live Trading: {'ENABLED' if cls.ENABLE_LIVE_TRADING else 'DISABLED (Paper Mode)'}
        ====================================
        """
        return summary

    @classmethod
    def validate_configuration(cls) -> bool:
        """
        Validate that configuration is internally consistent

        Returns:
            True if configuration is valid
        """
        errors = []

        # Check TP/SL arrays are not empty
        if not cls.TP_OPTIONS:
            errors.append("TP_OPTIONS is empty")
        if not cls.SL_OPTIONS:
            errors.append("SL_OPTIONS is empty")

        # Check all TP values are positive
        if any(tp <= 0 for tp in cls.TP_OPTIONS):
            errors.append("TP_OPTIONS contains non-positive values")

        # Check all SL values are negative
        if any(sl >= 0 for sl in cls.SL_OPTIONS):
            errors.append("SL_OPTIONS contains non-negative values")

        # Check that we have valid combinations
        valid_combos = cls.get_valid_combinations()
        if not valid_combos:
            errors.append(f"No valid TP/SL combinations meet minimum R/R of {cls.PHASE_III_MIN_RR}")

        # Check scoring weights sum appropriately
        total_weight = cls.SCORE_WEIGHT_WIN_RATE + cls.SCORE_WEIGHT_RISK_REWARD
        if not (0.99 <= total_weight <= 1.01):  # Allow for floating point errors
            errors.append(f"Scoring weights don't sum to 1.0: {total_weight}")

        # Check Thompson Sampling parameters
        if cls.THOMPSON_SAMPLING_TEMPERATURE <= 0:
            errors.append("THOMPSON_SAMPLING_TEMPERATURE must be positive")

        if not (0 < cls.MIN_ALLOCATION_PROBABILITY < 1):
            errors.append("MIN_ALLOCATION_PROBABILITY must be between 0 and 1")

        # Print errors if any
        if errors:
            print("Configuration Validation Errors:")
            for error in errors:
                print(f"  - {error}")
            return False

        return True


# ==========================================
# CONFIGURATION VALIDATION ON IMPORT
# ==========================================
# Automatically validate configuration when module is imported
if __name__ == "__main__" or True:  # Always validate on import
    if PhaseConfig.validate_configuration():
        print(f"✓ Phase configuration validated successfully")
        print(f"  Mode: {'HIGH WIN RATE' if PhaseConfig.OPTIMIZE_FOR_WIN_RATE else 'BALANCED'}")
        print(f"  Total combinations: {PhaseConfig.get_total_combinations()}")
        valid_combos = PhaseConfig.get_valid_combinations()
        print(f"  Valid combinations: {len(valid_combos)}")

        # Show top high-WR combinations if in that mode
        if PhaseConfig.OPTIMIZE_FOR_WIN_RATE:
            print(f"\n  Top 5 High Win Rate Combinations:")
            for i, combo in enumerate(valid_combos[:5], 1):
                print(f"    {i}. TP: {combo['tp']:.2f}%, SL: {combo['sl']:.2f}%, "
                      f"R/R: {combo['rr']:.2f}, Est WR: {combo['expected_wr']}%")
    else:
        print("✗ Phase configuration validation FAILED")