"""
Asset Health Monitor - Circuit Breaker for Phase 3

Prevents continued trading of consistently losing assets by monitoring
cumulative P&L and win rate over recent trades.

Phase 2: Allow all assets (need data for grid search)
Phase 3: Enforce profitability requirements (live trading with real risk)
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.database.models import TradeSetup
from datetime import datetime, timedelta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class AssetHealthMonitor:
    """Monitors asset profitability and implements circuit breakers"""

    # Circuit breaker thresholds
    CUMULATIVE_LOSS_THRESHOLD_20 = -20.0  # Pause if lost >20% over 20 trades
    CUMULATIVE_LOSS_THRESHOLD_10 = -30.0  # Blacklist if lost >30% over 10 trades
    WIN_RATE_THRESHOLD = 40.0  # Pause if win rate < 40% over 20 trades
    MIN_TRADES_FOR_CHECK = 10  # Need at least 10 trades to evaluate
    PAUSE_AUTO_RESUME_DAYS = 7  # Auto-resume paused assets after 7 days
    MAX_PAUSE_COUNT = 3  # Blacklist after 3 pauses

    @classmethod
    async def check_asset_status(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> str:
        """
        Check if asset is allowed to trade

        Returns: 'active', 'paused', or 'blacklisted'
        """
        # Check asset_status table
        result = await db.execute(
            text("""
                SELECT status, paused_at, pause_count
                FROM asset_status
                WHERE symbol = :symbol
                    AND direction = :direction
                    AND webhook_source = :webhook_source
            """),
            {"symbol": symbol, "direction": direction, "webhook_source": webhook_source}
        )
        row = result.fetchone()

        if not row:
            # Asset not tracked yet - allow trading
            return 'active'

        status, paused_at, pause_count = row

        # Check if paused asset can be auto-resumed
        if status == 'paused' and paused_at:
            days_paused = (datetime.now() - paused_at).days
            if days_paused >= cls.PAUSE_AUTO_RESUME_DAYS:
                logger.info(
                    f"Auto-resuming {symbol} {direction} ({webhook_source}) "
                    f"after {days_paused} days pause"
                )
                await cls._resume_asset(db, symbol, direction, webhook_source)
                return 'active'

        return status

    @classmethod
    async def update_asset_health(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        phase: str
    ):
        """
        Update asset health metrics after trade completion
        Only enforces circuit breaker in Phase 3
        """
        # Only enforce circuit breaker in Phase 3 (live trading)
        if phase != 'III':
            logger.debug(f"Skipping circuit breaker for {symbol} {direction} (Phase {phase})")
            return

        # Get last 20 trades
        result = await db.execute(
            select(TradeSetup).where(
                TradeSetup.symbol == symbol,
                TradeSetup.direction == direction,
                TradeSetup.webhook_source == webhook_source,
                TradeSetup.status == 'completed'
            ).order_by(TradeSetup.created_at.desc()).limit(20)
        )
        recent_trades = result.scalars().all()

        if len(recent_trades) < cls.MIN_TRADES_FOR_CHECK:
            logger.debug(
                f"Not enough trades for {symbol} {direction} "
                f"({len(recent_trades)}/{cls.MIN_TRADES_FOR_CHECK})"
            )
            return

        # Calculate metrics
        cumulative_pnl = sum(float(t.final_pnl_pct or 0) for t in recent_trades)
        wins = sum(1 for t in recent_trades if (t.final_pnl_pct or 0) > 0)
        win_rate = (wins / len(recent_trades)) * 100

        logger.info(
            f"Asset Health Check: {symbol} {direction} ({webhook_source}) | "
            f"Phase {phase} | Last {len(recent_trades)} trades | "
            f"Cumulative P&L: {cumulative_pnl:.2f}% | Win Rate: {win_rate:.1f}%"
        )

        # Check circuit breaker conditions
        should_pause = False
        pause_reason = None

        # Severe loss over 10 trades → immediate blacklist
        if len(recent_trades) >= 10:
            pnl_10 = sum(float(t.final_pnl_pct or 0) for t in recent_trades[:10])
            if pnl_10 < cls.CUMULATIVE_LOSS_THRESHOLD_10:
                await cls._blacklist_asset(
                    db, symbol, direction, webhook_source,
                    reason=f"SEVERE LOSS: {pnl_10:.2f}% over last 10 trades"
                )
                return

        # Check 20-trade thresholds
        if len(recent_trades) >= 20:
            if cumulative_pnl < cls.CUMULATIVE_LOSS_THRESHOLD_20:
                should_pause = True
                pause_reason = f"Cumulative loss: {cumulative_pnl:.2f}% over {len(recent_trades)} trades (threshold: {cls.CUMULATIVE_LOSS_THRESHOLD_20}%)"
            elif win_rate < cls.WIN_RATE_THRESHOLD:
                should_pause = True
                pause_reason = f"Low win rate: {win_rate:.1f}% over {len(recent_trades)} trades (threshold: {cls.WIN_RATE_THRESHOLD}%)"

        if should_pause:
            await cls._pause_asset(db, symbol, direction, webhook_source, pause_reason)
        else:
            # Update metrics even if not pausing
            await cls._update_asset_metrics(
                db, symbol, direction, webhook_source,
                cumulative_pnl, win_rate, len(recent_trades)
            )

    @classmethod
    async def _pause_asset(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        reason: str
    ):
        """Pause an asset (can be auto-resumed after 7 days)"""
        # Get current pause count
        result = await db.execute(
            text("""
                SELECT pause_count FROM asset_status
                WHERE symbol = :symbol
                    AND direction = :direction
                    AND webhook_source = :webhook_source
            """),
            {"symbol": symbol, "direction": direction, "webhook_source": webhook_source}
        )
        row = result.fetchone()
        current_pause_count = row[0] if row else 0
        new_pause_count = current_pause_count + 1

        # Check if should blacklist instead
        if new_pause_count >= cls.MAX_PAUSE_COUNT:
            await cls._blacklist_asset(
                db, symbol, direction, webhook_source,
                reason=f"Exceeded max pause count ({cls.MAX_PAUSE_COUNT}): {reason}"
            )
            return

        logger.warning(
            f"⚠️ PAUSING ASSET: {symbol} {direction} ({webhook_source}) | "
            f"Pause #{new_pause_count}/{cls.MAX_PAUSE_COUNT} | Reason: {reason}"
        )

        await db.execute(
            text("""
                INSERT INTO asset_status (
                    symbol, direction, webhook_source, status, pause_reason,
                    paused_at, pause_count, updated_at
                )
                VALUES (:symbol, :direction, :webhook_source, 'paused', :reason,
                        NOW(), :pause_count, NOW())
                ON CONFLICT (symbol, direction, webhook_source)
                DO UPDATE SET
                    status = 'paused',
                    pause_reason = :reason,
                    paused_at = NOW(),
                    pause_count = :pause_count,
                    updated_at = NOW()
            """),
            {
                "symbol": symbol,
                "direction": direction,
                "webhook_source": webhook_source,
                "reason": reason,
                "pause_count": new_pause_count
            }
        )
        await db.commit()

    @classmethod
    async def _blacklist_asset(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        reason: str
    ):
        """Blacklist an asset (requires manual review to resume)"""
        logger.error(
            f"🛑 BLACKLISTING ASSET: {symbol} {direction} ({webhook_source}) | "
            f"Reason: {reason}"
        )

        await db.execute(
            text("""
                INSERT INTO asset_status (
                    symbol, direction, webhook_source, status, pause_reason,
                    paused_at, updated_at
                )
                VALUES (:symbol, :direction, :webhook_source, 'blacklisted', :reason,
                        NOW(), NOW())
                ON CONFLICT (symbol, direction, webhook_source)
                DO UPDATE SET
                    status = 'blacklisted',
                    pause_reason = :reason,
                    paused_at = NOW(),
                    updated_at = NOW()
            """),
            {
                "symbol": symbol,
                "direction": direction,
                "webhook_source": webhook_source,
                "reason": reason
            }
        )
        await db.commit()

    @classmethod
    async def _resume_asset(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ):
        """Resume a paused asset (auto or manual)"""
        logger.info(f"▶️ RESUMING ASSET: {symbol} {direction} ({webhook_source})")

        await db.execute(
            text("""
                UPDATE asset_status
                SET status = 'active',
                    pause_reason = NULL,
                    updated_at = NOW()
                WHERE symbol = :symbol
                    AND direction = :direction
                    AND webhook_source = :webhook_source
            """),
            {"symbol": symbol, "direction": direction, "webhook_source": webhook_source}
        )
        await db.commit()

    @classmethod
    async def _update_asset_metrics(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        cumulative_pnl: float,
        win_rate: float,
        total_trades: int
    ):
        """Update asset metrics without changing status"""
        await db.execute(
            text("""
                INSERT INTO asset_status (
                    symbol, direction, webhook_source, status,
                    cumulative_pnl_last_20, win_rate_last_20, total_trades,
                    last_checked_at, updated_at
                )
                VALUES (:symbol, :direction, :webhook_source, 'active',
                        :pnl, :wr, :trades, NOW(), NOW())
                ON CONFLICT (symbol, direction, webhook_source)
                DO UPDATE SET
                    cumulative_pnl_last_20 = :pnl,
                    win_rate_last_20 = :wr,
                    total_trades = :trades,
                    last_checked_at = NOW(),
                    updated_at = NOW()
            """),
            {
                "symbol": symbol,
                "direction": direction,
                "webhook_source": webhook_source,
                "pnl": cumulative_pnl,
                "wr": win_rate,
                "trades": total_trades
            }
        )
        await db.commit()

    @classmethod
    async def get_asset_health_summary(cls, db: AsyncSession) -> list:
        """Get summary of all asset health statuses"""
        result = await db.execute(
            text("""
                SELECT
                    symbol,
                    direction,
                    webhook_source,
                    status,
                    ROUND(cumulative_pnl_last_20::numeric, 2) as pnl,
                    ROUND(win_rate_last_20::numeric, 1) as win_rate,
                    total_trades,
                    pause_count,
                    pause_reason,
                    paused_at
                FROM asset_status
                ORDER BY
                    CASE status
                        WHEN 'blacklisted' THEN 1
                        WHEN 'paused' THEN 2
                        WHEN 'active' THEN 3
                    END,
                    cumulative_pnl_last_20 ASC
            """)
        )
        return [dict(row) for row in result.fetchall()]
