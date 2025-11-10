"""
Baseline Trade Manager

Manages baseline trades for AI model training.
Tracks signal performance without TP/SL exits - trades close only on signal replacement/reversal.

Architecture:
- One active baseline trade per (symbol, direction, webhook_source)
- Price updates from existing WebSocket manager
- Milestone tracking (max profit/drawdown)
- Independent per webhook source (Edge2Trend5m doesn't affect ADX1m)
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict
import logging

from sqlalchemy import create_engine, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.database.baseline_models import BaselineTrade, BaselineMilestone
from app.config import settings

logger = logging.getLogger(__name__)


class BaselineManager:
    """
    Manages baseline trades for pure signal performance tracking
    """

    def __init__(self):
        # Create async engine for baseline database
        baseline_db_url = f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/ai_andre_baseline"

        self.engine = create_async_engine(
            baseline_db_url,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False
        )

        self.AsyncSessionLocal = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        # Milestone thresholds to track
        self.profit_milestones = [1, 2, 3, 4, 5, 7, 10, 15, 20]  # +1%, +2%, etc.
        self.loss_milestones = [-1, -2, -3, -5, -7, -10, -15, -20]  # -1%, -2%, etc.

        logger.info("✅ BaselineManager initialized")

    async def handle_new_webhook(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        webhook_source: str,
        entry_timestamp: Optional[datetime] = None
    ) -> Optional[BaselineTrade]:
        """
        Handle new webhook signal - close old baseline trade if exists, create new one

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            direction: 'LONG' or 'SHORT'
            entry_price: Entry price
            webhook_source: Source of signal (e.g., 'Edge2Trend5m')
            entry_timestamp: Entry time (defaults to now)

        Returns:
            New baseline trade object
        """
        if entry_timestamp is None:
            entry_timestamp = datetime.now(timezone.utc)

        async with self.AsyncSessionLocal() as db:
            try:
                # Check for existing active trade from same webhook source on same symbol
                existing_trade = await self._get_active_trade(db, symbol, webhook_source)

                if existing_trade:
                    # Determine exit reason
                    if existing_trade.direction == direction:
                        exit_reason = 'replacement'  # Same direction = replacement
                    else:
                        exit_reason = 'reversal'  # Opposite direction = reversal

                    # Close existing trade
                    await self._close_trade(
                        db,
                        existing_trade,
                        exit_price=entry_price,
                        exit_timestamp=entry_timestamp,
                        exit_reason=exit_reason
                    )

                    logger.info(
                        f"📊 Closed baseline trade #{existing_trade.id}: {existing_trade.symbol} "
                        f"{existing_trade.direction} ({exit_reason}) "
                        f"P&L: {existing_trade.final_pnl_pct:.2f}%"
                    )

                # Create new baseline trade
                new_trade = await self._create_trade(
                    db,
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    webhook_source=webhook_source,
                    entry_timestamp=entry_timestamp
                )

                await db.commit()

                logger.info(
                    f"📊 Created baseline trade #{new_trade.id}: {symbol} {direction} "
                    f"@ {entry_price} from {webhook_source}"
                )

                return new_trade

            except Exception as e:
                await db.rollback()
                logger.error(f"❌ Error handling webhook for baseline: {e}", exc_info=True)
                return None

    async def update_price(
        self,
        symbol: str,
        price: float,
        timestamp: Optional[datetime] = None
    ) -> int:
        """
        Update current price for all active baseline trades on this symbol

        Args:
            symbol: Trading pair
            price: Current price
            timestamp: Update time (defaults to now)

        Returns:
            Number of trades updated
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        async with self.AsyncSessionLocal() as db:
            try:
                # Get all active trades for this symbol
                result = await db.execute(
                    select(BaselineTrade).where(
                        BaselineTrade.symbol == symbol,
                        BaselineTrade.status == 'active'
                    )
                )
                trades = result.scalars().all()

                if not trades:
                    return 0

                updated_count = 0
                for trade in trades:
                    await self._update_trade_price(db, trade, price, timestamp)
                    updated_count += 1

                await db.commit()
                return updated_count

            except Exception as e:
                await db.rollback()
                logger.error(f"❌ Error updating baseline price for {symbol}: {e}")
                return 0

    async def _get_active_trade(
        self,
        db: AsyncSession,
        symbol: str,
        webhook_source: str
    ) -> Optional[BaselineTrade]:
        """Get active baseline trade for symbol + webhook_source"""
        result = await db.execute(
            select(BaselineTrade).where(
                BaselineTrade.symbol == symbol,
                BaselineTrade.webhook_source == webhook_source,
                BaselineTrade.status == 'active'
            ).options(selectinload(BaselineTrade.milestones))
        )
        return result.scalar_one_or_none()

    async def _create_trade(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        entry_price: float,
        webhook_source: str,
        entry_timestamp: datetime
    ) -> BaselineTrade:
        """Create new baseline trade"""
        trade = BaselineTrade(
            symbol=symbol,
            direction=direction,
            entry_price=Decimal(str(entry_price)),
            webhook_source=webhook_source,
            entry_timestamp=entry_timestamp,
            current_price=Decimal(str(entry_price)),
            last_price_update=entry_timestamp,
            max_profit_pct=Decimal('0'),
            max_drawdown_pct=Decimal('0'),
            status='active'
        )

        db.add(trade)
        await db.flush()  # Get trade ID

        return trade

    async def _update_trade_price(
        self,
        db: AsyncSession,
        trade: BaselineTrade,
        price: float,
        timestamp: datetime
    ):
        """Update trade with new price and track milestones"""
        # Calculate P&L
        price_decimal = Decimal(str(price))
        entry_price = trade.entry_price

        if trade.direction == 'LONG':
            pnl_pct = ((price_decimal - entry_price) / entry_price) * 100
        else:  # SHORT
            pnl_pct = ((entry_price - price_decimal) / entry_price) * 100

        # Update max profit/drawdown
        if pnl_pct > trade.max_profit_pct:
            trade.max_profit_pct = pnl_pct

        if pnl_pct < trade.max_drawdown_pct:
            trade.max_drawdown_pct = pnl_pct

        # Update current price
        trade.current_price = price_decimal
        trade.last_price_update = timestamp

        # Record milestones
        await self._record_milestones(db, trade, pnl_pct, price_decimal, timestamp)

    async def _record_milestones(
        self,
        db: AsyncSession,
        trade: BaselineTrade,
        current_pnl_pct: Decimal,
        current_price: Decimal,
        timestamp: datetime
    ):
        """Record price milestones"""
        current_pnl_float = float(current_pnl_pct)

        # Check profit milestones
        for milestone in self.profit_milestones:
            if current_pnl_float >= milestone:
                # Check if milestone already recorded
                result = await db.execute(
                    select(BaselineMilestone).where(
                        BaselineMilestone.baseline_trade_id == trade.id,
                        BaselineMilestone.milestone_type == f'+{milestone}pct'
                    )
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    time_to_hit = int((timestamp - trade.entry_timestamp).total_seconds() / 60)

                    milestone_obj = BaselineMilestone(
                        baseline_trade_id=trade.id,
                        milestone_type=f'+{milestone}pct',
                        milestone_value=Decimal(str(milestone)),
                        hit_at=timestamp,
                        hit_price=current_price,
                        time_to_hit_minutes=time_to_hit
                    )
                    db.add(milestone_obj)

        # Check loss milestones
        for milestone in self.loss_milestones:
            if current_pnl_float <= milestone:
                # Check if milestone already recorded
                result = await db.execute(
                    select(BaselineMilestone).where(
                        BaselineMilestone.baseline_trade_id == trade.id,
                        BaselineMilestone.milestone_type == f'{milestone}pct'
                    )
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    time_to_hit = int((timestamp - trade.entry_timestamp).total_seconds() / 60)

                    milestone_obj = BaselineMilestone(
                        baseline_trade_id=trade.id,
                        milestone_type=f'{milestone}pct',
                        milestone_value=Decimal(str(milestone)),
                        hit_at=timestamp,
                        hit_price=current_price,
                        time_to_hit_minutes=time_to_hit
                    )
                    db.add(milestone_obj)

    async def _close_trade(
        self,
        db: AsyncSession,
        trade: BaselineTrade,
        exit_price: float,
        exit_timestamp: datetime,
        exit_reason: str
    ):
        """Close baseline trade and calculate final stats"""
        # Calculate final P&L
        exit_price_decimal = Decimal(str(exit_price))

        if trade.direction == 'LONG':
            final_pnl_pct = ((exit_price_decimal - trade.entry_price) / trade.entry_price) * 100
        else:  # SHORT
            final_pnl_pct = ((trade.entry_price - exit_price_decimal) / trade.entry_price) * 100

        # Calculate duration
        duration_minutes = int((exit_timestamp - trade.entry_timestamp).total_seconds() / 60)

        # Update trade
        trade.exit_price = exit_price_decimal
        trade.exit_timestamp = exit_timestamp
        trade.exit_reason = exit_reason
        trade.final_pnl_pct = final_pnl_pct
        trade.duration_minutes = duration_minutes
        trade.status = 'completed'

    async def get_active_count(self) -> int:
        """Get number of active baseline trades"""
        async with self.AsyncSessionLocal() as db:
            result = await db.execute(
                select(BaselineTrade).where(BaselineTrade.status == 'active')
            )
            return len(result.scalars().all())

    async def get_stats(self, webhook_source: Optional[str] = None) -> Dict:
        """Get baseline statistics"""
        async with self.AsyncSessionLocal() as db:
            query = select(BaselineTrade).where(BaselineTrade.status == 'completed')

            if webhook_source:
                query = query.where(BaselineTrade.webhook_source == webhook_source)

            result = await db.execute(query)
            trades = result.scalars().all()

            if not trades:
                return {
                    'total_trades': 0,
                    'avg_pnl_pct': 0,
                    'avg_duration_minutes': 0,
                    'win_rate': 0
                }

            total_pnl = sum(float(t.final_pnl_pct) for t in trades)
            avg_pnl = total_pnl / len(trades)
            avg_duration = sum(t.duration_minutes for t in trades) / len(trades)
            winners = sum(1 for t in trades if t.final_pnl_pct > 0)
            win_rate = (winners / len(trades)) * 100

            return {
                'total_trades': len(trades),
                'avg_pnl_pct': round(avg_pnl, 2),
                'avg_duration_minutes': round(avg_duration, 1),
                'win_rate': round(win_rate, 1),
                'total_pnl_pct': round(total_pnl, 2)
            }

    async def close(self):
        """Close database connections"""
        await self.engine.dispose()


# Global instance
_baseline_manager: Optional[BaselineManager] = None


def get_baseline_manager() -> BaselineManager:
    """Get or create global baseline manager instance"""
    global _baseline_manager
    if _baseline_manager is None:
        _baseline_manager = BaselineManager()
    return _baseline_manager
