"""
Exit Strategy Handlers

Modular exit strategy implementations for different trading approaches:
- StaticSLHandler: Basic TP/SL system
- EarlyMomentumHandler: Quality signal filtering
- AdaptiveTrailingHandler: Dynamic trailing stop with momentum states
"""
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Optional
import logging

from app.database.models import TradeSetup
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ExitStrategyHandler(ABC):
    """Base class for exit strategy handlers"""

    @abstractmethod
    async def check_exit(
        self,
        trade: TradeSetup,
        price: float,
        pnl_pct: float,
        now: datetime,
        minutes_since_entry: float,
        db: AsyncSession
    ) -> bool:
        """
        Check if exit conditions are met

        Returns:
            True if trade should be closed, False otherwise
        """
        pass


class StaticSLHandler(ExitStrategyHandler):
    """
    Strategy A: Static Stop Loss (Control Group)

    Basic exit logic:
    - Fixed TP levels (TP1, TP2, TP3)
    - Fixed SL level
    - No dynamic adjustments
    """

    async def check_exit(
        self,
        trade: TradeSetup,
        price: float,
        pnl_pct: float,
        now: datetime,
        minutes_since_entry: float,
        db: AsyncSession
    ) -> bool:
        """Check static stop loss"""
        sl_hit = False

        # Primary check: Actual price against planned_sl_price (most accurate with leverage)
        if trade.planned_sl_price:
            if trade.direction == 'LONG' and price <= float(trade.planned_sl_price):
                sl_hit = True
            elif trade.direction == 'SHORT' and price >= float(trade.planned_sl_price):
                sl_hit = True

        # Fallback check: Percentage-based (for trades without planned_sl_price)
        elif trade.planned_sl_pct and pnl_pct <= float(trade.planned_sl_pct):
            sl_hit = True

        if sl_hit:
            trade.sl_hit = True
            trade.sl_hit_at = now
            trade.sl_hit_price = Decimal(str(price))
            trade.sl_time_minutes = int(minutes_since_entry)
            trade.sl_type_hit = 'static'

            sl_price_str = f" (SL: {float(trade.planned_sl_price):.2f})" if trade.planned_sl_price else ""
            logger.warning(
                f"🛑 STOP LOSS HIT: {trade.symbol} @ {price}{sl_price_str} "
                f"({pnl_pct:.2f}%) after {trade.sl_time_minutes}min"
            )

            return True

        return False


class EarlyMomentumHandler(ExitStrategyHandler):
    """
    Strategy C: Early Momentum Filter (Quality Signal Detection)

    Theory: "Good trades work right away, bad trades struggle"

    Algorithm:
    1. Check if favorable movement happens within time threshold
    2. If YES → Move SL to breakeven (lock in quality signal)
    3. If NO → Close at BE or small loss (filter low-quality signal)

    Example (15m timeframe):
    - Time threshold: 5 minutes
    - Profit threshold: 0.5%
    - If profit reaches 0.5% within 5 min → SL to BE
    - If 5 min passes without 0.5% → Close trade (low quality)
    """

    async def check_exit(
        self,
        trade: TradeSetup,
        price: float,
        pnl_pct: float,
        now: datetime,
        minutes_since_entry: float,
        db: AsyncSession
    ) -> bool:
        """Check early momentum exit conditions"""
        # Check if early momentum already detected (SL already moved to BE)
        if trade.early_momentum_detected:
            # Check BE stop loss
            if pnl_pct <= 0:
                trade.sl_hit = True
                trade.sl_hit_at = now
                trade.sl_hit_price = Decimal(str(price))
                trade.sl_time_minutes = int(minutes_since_entry)
                trade.sl_type_hit = 'breakeven'

                logger.info(
                    f"🔒 BE STOP HIT (Early Momentum): {trade.symbol} @ {price} "
                    f"({pnl_pct:.2f}%) after {trade.sl_time_minutes}min"
                )

                return True
            return False

        # Get thresholds
        time_threshold = float(trade.early_profit_time_threshold) if trade.early_profit_time_threshold else 5.0
        profit_threshold = float(trade.early_profit_pct_threshold) if trade.early_profit_pct_threshold else 0.5

        # Check if profit threshold reached within time window
        if minutes_since_entry <= time_threshold:
            if pnl_pct >= profit_threshold:
                # EARLY MOMENTUM DETECTED! Move SL to breakeven
                trade.early_momentum_detected = True
                trade.early_momentum_time = Decimal(str(minutes_since_entry))
                trade.early_momentum_pnl = Decimal(str(pnl_pct))
                trade.sl_moved_to_be = True
                trade.sl_move_timestamp = now

                logger.info(
                    f"⚡ EARLY MOMENTUM DETECTED: {trade.symbol} reached {pnl_pct:.2f}% "
                    f"in {minutes_since_entry:.1f}min (threshold: {profit_threshold}% in {time_threshold}min) "
                    f"→ SL moved to BE"
                )

        # Check if time window expired without reaching threshold
        elif minutes_since_entry > time_threshold and not trade.early_momentum_detected:
            # LOW QUALITY SIGNAL - close trade
            trade.low_quality_signal = True
            trade.sl_hit = True
            trade.sl_hit_at = now
            trade.sl_hit_price = Decimal(str(price))
            trade.sl_time_minutes = int(minutes_since_entry)
            trade.sl_type_hit = 'quality_filter'

            logger.warning(
                f"❌ LOW QUALITY SIGNAL: {trade.symbol} failed to reach {profit_threshold}% "
                f"within {time_threshold}min (only {pnl_pct:.2f}%) → Closing trade"
            )

            return True

        return False


class AdaptiveTrailingHandler(ExitStrategyHandler):
    """
    Strategy B: Adaptive Momentum Lock (Enhanced Trailing)

    Theory: Adapt trail distance based on:
    1. Momentum state (pre_tp1 / tp1_tp2 / post_tp2)
    2. Asset volatility (ATR-based multiplier)

    Algorithm:
    - Pre-TP1: Wide trail (2.0% * 1.5 * volatility_multiplier)
    - Between TP1-TP2: Normal trail (2.0% * 1.0 * volatility_multiplier)
    - Post-TP2: Tight trail (2.0% * 0.7 * volatility_multiplier)

    Volatility multiplier: 1.0-3.0 based on recent ATR
    """

    async def check_exit(
        self,
        trade: TradeSetup,
        price: float,
        pnl_pct: float,
        now: datetime,
        minutes_since_entry: float,
        db: AsyncSession
    ) -> bool:
        """Check adaptive trailing stop exit conditions"""
        # CRITICAL: Check static SL first (initial stop loss)
        # Adaptive trailing should NOT override the initial static SL
        sl_hit = False
        if trade.planned_sl_price:
            if trade.direction == 'LONG' and price <= float(trade.planned_sl_price):
                sl_hit = True
            elif trade.direction == 'SHORT' and price >= float(trade.planned_sl_price):
                sl_hit = True
        elif trade.planned_sl_pct and pnl_pct <= float(trade.planned_sl_pct):
            sl_hit = True

        if sl_hit:
            trade.sl_hit = True
            trade.sl_hit_at = now
            trade.sl_hit_price = Decimal(str(price))
            trade.sl_time_minutes = int(minutes_since_entry)
            trade.sl_type_hit = 'static_initial'

            sl_price_str = f" (SL: {float(trade.planned_sl_price):.2f})" if trade.planned_sl_price else ""
            logger.warning(
                f"🛑 INITIAL STOP LOSS HIT (Adaptive): {trade.symbol} @ {price}{sl_price_str} "
                f"({pnl_pct:.2f}%) after {trade.sl_time_minutes}min"
            )

            return True

        # Continue with adaptive trailing logic...
        # Update momentum state based on TP hits
        if trade.tp2_hit and trade.momentum_state != 'post_tp2':
            trade.momentum_state = 'post_tp2'
            trade.trailing_stop_updates = (trade.trailing_stop_updates or 0) + 1
            logger.info(f"📈 Momentum State: POST_TP2 (tightening trail) - {trade.symbol}")
        elif trade.tp1_hit and trade.momentum_state == 'pre_tp1':
            trade.momentum_state = 'tp1_tp2'
            trade.trailing_stop_updates = (trade.trailing_stop_updates or 0) + 1
            logger.info(f"📈 Momentum State: TP1_TP2 (normal trail) - {trade.symbol}")

        # Get volatility multiplier (default 1.0, would be updated with ATR in production)
        # TODO: Calculate from recent ATR data
        volatility_multiplier = float(trade.volatility_multiplier) if trade.volatility_multiplier else 1.0

        # Base trailing distance
        base_trail = 2.0  # 2%

        # Adjust based on momentum state
        if trade.momentum_state == 'pre_tp1':
            trail_distance = base_trail * 1.5 * volatility_multiplier  # Wide
        elif trade.momentum_state == 'post_tp2':
            trail_distance = base_trail * 0.7 * volatility_multiplier  # Tight
        else:  # tp1_tp2
            trail_distance = base_trail * 1.0 * volatility_multiplier  # Normal

        # Update adaptive trailing stop percentage
        new_trail_pct = Decimal(str(trail_distance))
        if trade.trailing_stop_pct != new_trail_pct:
            trade.trailing_stop_pct = new_trail_pct
            trade.trailing_stop_distance_pct = new_trail_pct
            logger.debug(
                f"🎯 Adaptive Trail Updated: {trade.symbol} → {trail_distance:.2f}% "
                f"(state: {trade.momentum_state}, vol: {volatility_multiplier:.2f}x)"
            )

        # Apply standard trailing stop logic with adaptive distance
        # Update high-water mark
        if trade.trailing_stop_high_water is None:
            trade.trailing_stop_high_water = trade.entry_price

        current_high = max(float(trade.trailing_stop_high_water), price)
        if current_high > float(trade.trailing_stop_high_water):
            trade.trailing_stop_high_water = Decimal(str(current_high))
            trade.trailing_stop_updates = (trade.trailing_stop_updates or 0) + 1

        # Check if trailing stop should activate
        if not trade.trailing_stop_triggered:
            if trade.trailing_stop_activation_pct:
                if pnl_pct >= float(trade.trailing_stop_activation_pct):
                    trade.trailing_stop_triggered = True
                    logger.info(
                        f"🎣 Adaptive Trailing ACTIVATED: {trade.symbol} @ {price} "
                        f"(+{pnl_pct:.2f}%, trail: {trail_distance:.2f}%)"
                    )
            else:
                trade.trailing_stop_triggered = True

        # If trailing stop is active, check if hit
        if trade.trailing_stop_triggered:
            # Calculate dynamic SL level
            if trade.direction == 'LONG':
                dynamic_sl_price = current_high * (1 - trail_distance / 100)
            else:  # SHORT
                dynamic_sl_price = current_high * (1 + trail_distance / 100)

            # Check if price hit dynamic SL
            hit_trailing = False
            if trade.direction == 'LONG' and price <= dynamic_sl_price:
                hit_trailing = True
            elif trade.direction == 'SHORT' and price >= dynamic_sl_price:
                hit_trailing = True

            if hit_trailing:
                trade.sl_hit = True
                trade.sl_hit_at = now
                trade.sl_hit_price = Decimal(str(price))
                trade.sl_time_minutes = int(minutes_since_entry)
                trade.sl_type_hit = 'adaptive_trailing'

                logger.warning(
                    f"🎣🛑 ADAPTIVE TRAILING STOP HIT: {trade.symbol} @ {price} "
                    f"(High: {current_high}, Dynamic SL: {dynamic_sl_price:.2f}, "
                    f"Trail: {trail_distance:.2f}%, State: {trade.momentum_state}, "
                    f"Updates: {trade.trailing_stop_updates}, Final PnL: {pnl_pct:.2f}%)"
                )

                return True

        return False
