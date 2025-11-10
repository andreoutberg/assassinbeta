"""
Velocity Analyzer - Time-Based Exit Optimization

Extracts velocity and momentum patterns from milestone data to optimize exit timing.
Fast moves to profit → wider trailing stops (let winners run)
Slow grinds → tighter exits (take profits earlier)
"""
from decimal import Decimal
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database.models import TradeSetup, TradeMilestones
import logging

logger = logging.getLogger(__name__)


class VelocityAnalyzer:
    """Analyzes trade velocity and momentum from milestone timestamps"""

    # Velocity thresholds for categorization
    FAST_THRESHOLD_MINUTES = 60      # < 1 hour to profit = FAST
    MEDIUM_THRESHOLD_MINUTES = 240   # 1-4 hours = MEDIUM
    SLOW_THRESHOLD_MINUTES = 240     # > 4 hours = SLOW

    # Momentum categories
    MOMENTUM_FAST = "FAST"
    MOMENTUM_MEDIUM = "MEDIUM"
    MOMENTUM_SLOW = "SLOW"

    # Trailing stop adjustments based on momentum
    TRAILING_ADJUSTMENT_MAP = {
        MOMENTUM_FAST: 1.5,    # Increase trailing distance by 50% (let winners run)
        MOMENTUM_MEDIUM: 1.0,  # Keep default trailing distance
        MOMENTUM_SLOW: 0.7     # Decrease trailing distance by 30% (take profits earlier)
    }

    @classmethod
    def calculate_velocity_metrics(
        cls,
        trade: TradeSetup,
        milestones: Optional[TradeMilestones]
    ) -> Dict[str, any]:
        """
        Calculate velocity and momentum metrics from milestone data

        Returns:
            Dict containing:
            - time_to_mfe_seconds: Time to reach maximum favorable excursion
            - time_to_mae_seconds: Time to reach maximum adverse excursion
            - velocity_score: Profit % per hour
            - momentum_category: FAST/MEDIUM/SLOW
        """
        if not milestones:
            logger.warning(f"Trade {trade.id} has no milestone data for velocity analysis")
            return {
                "time_to_mfe_seconds": None,
                "time_to_mae_seconds": None,
                "velocity_score": None,
                "momentum_category": None
            }

        # Get entry timestamp
        entry_at = milestones.entry_at
        if not entry_at:
            entry_at = trade.entry_timestamp

        # Calculate time to MFE (Maximum Favorable Excursion)
        time_to_mfe_seconds = cls._calculate_time_to_mfe(milestones, entry_at)

        # Calculate time to MAE (Maximum Adverse Excursion)
        time_to_mae_seconds = cls._calculate_time_to_mae(milestones, entry_at)

        # Calculate velocity score (profit % per hour)
        velocity_score = cls._calculate_velocity_score(milestones, entry_at)

        # Determine momentum category based on time to first profitable milestone
        momentum_category = cls._categorize_momentum(milestones, entry_at)

        return {
            "time_to_mfe_seconds": time_to_mfe_seconds,
            "time_to_mae_seconds": time_to_mae_seconds,
            "velocity_score": velocity_score,
            "momentum_category": momentum_category
        }

    @classmethod
    def _calculate_time_to_mfe(
        cls,
        milestones: TradeMilestones,
        entry_at: datetime
    ) -> Optional[int]:
        """Calculate seconds from entry to maximum favorable excursion"""
        if not milestones.max_profit_at:
            # Find the highest profit milestone reached
            profit_milestones = [
                (milestones.reached_plus_0_5pct_at, 0.5),
                (milestones.reached_plus_1pct_at, 1.0),
                (milestones.reached_plus_1_5pct_at, 1.5),
                (milestones.reached_plus_2pct_at, 2.0),
                (milestones.reached_plus_3pct_at, 3.0),
                (milestones.reached_plus_5pct_at, 5.0),
                (milestones.reached_plus_8pct_at, 8.0),
                (milestones.reached_plus_10pct_at, 10.0),
            ]

            # Get highest milestone reached
            max_timestamp = None
            for timestamp, pct in reversed(profit_milestones):
                if timestamp:
                    max_timestamp = timestamp
                    break

            if max_timestamp:
                return int((max_timestamp - entry_at).total_seconds())
        else:
            return int((milestones.max_profit_at - entry_at).total_seconds())

        return None

    @classmethod
    def _calculate_time_to_mae(
        cls,
        milestones: TradeMilestones,
        entry_at: datetime
    ) -> Optional[int]:
        """Calculate seconds from entry to maximum adverse excursion"""
        if not milestones.max_drawdown_at:
            # Find the worst drawdown milestone reached
            drawdown_milestones = [
                (milestones.reached_minus_0_5pct_at, -0.5),
                (milestones.reached_minus_1pct_at, -1.0),
                (milestones.reached_minus_1_5pct_at, -1.5),
                (milestones.reached_minus_2pct_at, -2.0),
                (milestones.reached_minus_3pct_at, -3.0),
                (milestones.reached_minus_5pct_at, -5.0),
                (milestones.reached_minus_8pct_at, -8.0),
                (milestones.reached_minus_10pct_at, -10.0),
            ]

            # Get worst milestone reached
            min_timestamp = None
            for timestamp, pct in reversed(drawdown_milestones):
                if timestamp:
                    min_timestamp = timestamp
                    break

            if min_timestamp:
                return int((min_timestamp - entry_at).total_seconds())
        else:
            return int((milestones.max_drawdown_at - entry_at).total_seconds())

        return None

    @classmethod
    def _calculate_velocity_score(
        cls,
        milestones: TradeMilestones,
        entry_at: datetime
    ) -> Optional[float]:
        """
        Calculate velocity score: profit % per hour

        Uses the first significant profit milestone (1% or higher) to determine velocity
        """
        # Check profit milestones in order (1%, 1.5%, 2%, etc.)
        profit_checks = [
            (milestones.reached_plus_1pct_at, 1.0),
            (milestones.reached_plus_1_5pct_at, 1.5),
            (milestones.reached_plus_2pct_at, 2.0),
            (milestones.reached_plus_3pct_at, 3.0),
        ]

        for timestamp, pct in profit_checks:
            if timestamp:
                time_hours = (timestamp - entry_at).total_seconds() / 3600
                if time_hours > 0:
                    # Velocity = profit% / hours
                    return round(pct / time_hours, 4)

        # If no significant profit reached, check smaller milestone
        if milestones.reached_plus_0_5pct_at:
            time_hours = (milestones.reached_plus_0_5pct_at - entry_at).total_seconds() / 3600
            if time_hours > 0:
                return round(0.5 / time_hours, 4)

        return None

    @classmethod
    def _categorize_momentum(
        cls,
        milestones: TradeMilestones,
        entry_at: datetime
    ) -> str:
        """
        Categorize trade momentum based on time to reach first profit milestone

        FAST: < 1 hour to 1% profit
        MEDIUM: 1-4 hours to 1% profit
        SLOW: > 4 hours to 1% profit or no profit reached
        """
        # Check time to reach 1% profit (our standard momentum benchmark)
        if milestones.reached_plus_1pct_at:
            time_minutes = (milestones.reached_plus_1pct_at - entry_at).total_seconds() / 60

            if time_minutes < cls.FAST_THRESHOLD_MINUTES:
                return cls.MOMENTUM_FAST
            elif time_minutes <= cls.MEDIUM_THRESHOLD_MINUTES:
                return cls.MOMENTUM_MEDIUM
            else:
                return cls.MOMENTUM_SLOW

        # If 1% not reached, check 0.5% as fallback
        if milestones.reached_plus_0_5pct_at:
            time_minutes = (milestones.reached_plus_0_5pct_at - entry_at).total_seconds() / 60

            # Double the thresholds for 0.5% (half the profit target)
            if time_minutes < cls.FAST_THRESHOLD_MINUTES * 2:
                return cls.MOMENTUM_MEDIUM  # Downgrade from FAST since it's only 0.5%
            else:
                return cls.MOMENTUM_SLOW

        # No profit milestones reached = SLOW
        return cls.MOMENTUM_SLOW

    @classmethod
    def get_adjusted_trailing_distance(
        cls,
        base_trailing_distance: float,
        momentum_category: str
    ) -> float:
        """
        Adjust trailing stop distance based on momentum category

        FAST momentum: Increase by 50% (let winners run)
        MEDIUM momentum: Keep default
        SLOW momentum: Decrease by 30% (take profits earlier)
        """
        if not base_trailing_distance or not momentum_category:
            return base_trailing_distance

        multiplier = cls.TRAILING_ADJUSTMENT_MAP.get(momentum_category, 1.0)
        adjusted_distance = base_trailing_distance * multiplier

        logger.debug(
            f"Adjusted trailing distance: {base_trailing_distance}% -> {adjusted_distance:.2f}% "
            f"(momentum={momentum_category}, multiplier={multiplier})"
        )

        return round(adjusted_distance, 2)

    @classmethod
    async def analyze_and_update_trade(
        cls,
        db: AsyncSession,
        trade_id: int
    ) -> Dict[str, any]:
        """
        Analyze velocity for a specific trade and update database

        Returns velocity metrics that were calculated and stored
        """
        # Get trade with milestones
        result = await db.execute(
            select(TradeSetup)
            .options()
            .where(TradeSetup.id == trade_id)
        )
        trade = result.scalar_one_or_none()

        if not trade:
            logger.error(f"Trade {trade_id} not found")
            return {}

        # Get milestone data
        milestone_result = await db.execute(
            select(TradeMilestones)
            .where(TradeMilestones.trade_setup_id == trade_id)
        )
        milestones = milestone_result.scalar_one_or_none()

        # Calculate velocity metrics
        metrics = cls.calculate_velocity_metrics(trade, milestones)

        # Update trade with velocity data
        await db.execute(
            update(TradeSetup)
            .where(TradeSetup.id == trade_id)
            .values(
                time_to_mfe_seconds=metrics["time_to_mfe_seconds"],
                time_to_mae_seconds=metrics["time_to_mae_seconds"],
                velocity_score=Decimal(str(metrics["velocity_score"])) if metrics["velocity_score"] else None,
                momentum_category=metrics["momentum_category"]
            )
        )

        await db.commit()

        logger.info(
            f"Updated velocity metrics for trade {trade_id}: "
            f"momentum={metrics['momentum_category']}, "
            f"velocity={metrics['velocity_score']} %/hr"
        )

        return metrics

    @classmethod
    async def batch_analyze_trades(
        cls,
        db: AsyncSession,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> int:
        """
        Batch analyze velocity for multiple trades

        Args:
            symbol: Optional filter by symbol
            limit: Maximum number of trades to analyze

        Returns:
            Number of trades analyzed
        """
        # Build query for trades without velocity data
        query = select(TradeSetup).where(
            TradeSetup.velocity_score.is_(None),
            TradeSetup.status == 'completed'
        )

        if symbol:
            query = query.where(TradeSetup.symbol == symbol)

        query = query.limit(limit)

        result = await db.execute(query)
        trades = result.scalars().all()

        analyzed_count = 0
        for trade in trades:
            try:
                await cls.analyze_and_update_trade(db, trade.id)
                analyzed_count += 1
            except Exception as e:
                logger.error(f"Failed to analyze velocity for trade {trade.id}: {e}")
                continue

        logger.info(f"✅ Analyzed velocity for {analyzed_count} trades")
        return analyzed_count