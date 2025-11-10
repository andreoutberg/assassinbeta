"""
Milestone Recorder

Tracks P&L milestone timestamps for performance analysis:
- Profit milestones: +0.5%, +1.0%, +1.5%, +2.0%, +3.0%, +5.0%, +8.0%, +10.0%
- Drawdown milestones: -0.5%, -1.0%, -1.5%, -2.0%, -3.0%, -5.0%, -8.0%, -10.0%

Used for Phase II optimization and trade quality assessment.
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict
import logging

from app.database.models import TradeSetup, TradeMilestones
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MilestoneRecorder:
    """
    Records P&L milestones for active trades

    Lazy creation: Creates milestone records on first price update
    Caching: Maintains in-memory cache to reduce DB queries
    """

    # Milestone thresholds for Phase II optimization
    PROFIT_MILESTONES = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 10.0]
    DRAWDOWN_MILESTONES = [-0.5, -1.0, -1.5, -2.0, -3.0, -5.0, -8.0, -10.0]

    def __init__(self):
        # Milestone tracking cache (trade_id -> TradeMilestones)
        self.cache: Dict[int, TradeMilestones] = {}

    async def ensure_record(self, trade: TradeSetup, db: AsyncSession) -> TradeMilestones:
        """
        Ensure milestone record exists for trade (lazy creation)

        Creates record on first price update if it doesn't exist yet.
        This handles both new trades and existing trades after deployment.
        """
        # Check cache first
        if trade.id in self.cache:
            return self.cache[trade.id]

        # Query database
        from sqlalchemy import select
        result = await db.execute(
            select(TradeMilestones).where(TradeMilestones.trade_setup_id == trade.id)
        )
        milestone_record = result.scalar_one_or_none()

        if not milestone_record:
            # Create new milestone record
            milestone_record = TradeMilestones(
                trade_setup_id=trade.id,
                entry_price=trade.entry_price,
                entry_at=trade.entry_timestamp
            )
            db.add(milestone_record)
            await db.commit()  # CRITICAL FIX: Commit to persist milestone record
            logger.info(f"🏁 Created milestone tracking for trade {trade.id}")

        # Cache it
        self.cache[trade.id] = milestone_record
        return milestone_record

    async def update_milestones(
        self,
        trade: TradeSetup,
        pnl_pct: float,
        timestamp: datetime,
        db: AsyncSession
    ):
        """
        Check if new milestones crossed and record timestamps

        Performance optimized:
        - Only checks thresholds not yet reached
        - Uses cached milestone record
        - Batched with other DB operations
        """
        # Ensure milestone record exists
        milestones = await self.ensure_record(trade, db)

        # Track if any milestones were newly reached
        new_milestones_reached = []

        # Check profit milestones
        for threshold in self.PROFIT_MILESTONES:
            if pnl_pct >= threshold:
                # Build field name: reached_plus_1pct_at (handle decimal formatting)
                threshold_str = str(threshold).replace('.', '_').rstrip('0').rstrip('_')
                field_name = f"reached_plus_{threshold_str}pct_at"

                # Only update if not already set
                if not getattr(milestones, field_name):
                    setattr(milestones, field_name, timestamp)
                    new_milestones_reached.append(f"+{threshold}%")

        # Check drawdown milestones
        for threshold in self.DRAWDOWN_MILESTONES:
            if pnl_pct <= threshold:
                # Build field name: reached_minus_1pct_at (handle decimal formatting)
                threshold_str = str(abs(threshold)).replace('.', '_').rstrip('0').rstrip('_')
                field_name = f"reached_minus_{threshold_str}pct_at"

                # Only update if not already set
                if not getattr(milestones, field_name):
                    setattr(milestones, field_name, timestamp)
                    new_milestones_reached.append(f"{threshold}%")

        # Update high-water marks
        if milestones.max_profit_pct is None or pnl_pct > float(milestones.max_profit_pct):
            milestones.max_profit_pct = Decimal(str(pnl_pct))
            milestones.max_profit_at = timestamp

        if milestones.max_drawdown_pct is None or pnl_pct < float(milestones.max_drawdown_pct):
            milestones.max_drawdown_pct = Decimal(str(pnl_pct))
            milestones.max_drawdown_at = timestamp

        # Log new milestones (debug level to reduce CPU usage)
        if new_milestones_reached:
            logger.debug(
                f"🎯 Trade {trade.id} reached milestones: {', '.join(new_milestones_reached)}"
            )

    def clear_cache(self, trade_id: int):
        """Remove trade from cache (call when trade closes)"""
        self.cache.pop(trade_id, None)

    def clear_all(self):
        """Clear entire cache (call on shutdown)"""
        self.cache.clear()
