"""
Trade Identifier Generator

Generates unique trade identifiers in format: #AIALONG_A_001

Components:
- Asset abbreviation (AIA for AIAUSDT.P)
- Direction (LONG/SHORT)
- Strategy (A/B/C/D/BASE for baseline)
- Sequential counter (001, 002, 003...)
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.models import TradeSetup
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class TradeIdentifierGenerator:
    """Generates unique trade identifiers"""

    # Symbol abbreviation mapping
    SYMBOL_MAP = {
        'AIAUSDT.P': 'AIA',
        'FLUXUSDT.P': 'FLUX',
        'HIPPOUSDT.P': 'HIPPO',
        'SAGAUSDT.P': 'SAGA',
        'PENDLEUSDT.P': 'PENDLE',
        'LINKUSDT.P': 'LINK',
        'AVAXUSDT.P': 'AVAX',
        'BTCUSDT.P': 'BTC',
        'ETHUSDT.P': 'ETH',
        'SOLUSDT.P': 'SOL',
    }

    # Strategy abbreviation mapping
    STRATEGY_MAP = {
        'baseline': 'BASE',
        'strategy_A': 'A',
        'strategy_B': 'B',
        'strategy_C': 'C',
        'strategy_D': 'D',
    }

    @classmethod
    def _get_symbol_abbr(cls, symbol: str) -> str:
        """Get symbol abbreviation (e.g., AIAUSDT.P → AIA)"""
        if symbol in cls.SYMBOL_MAP:
            return cls.SYMBOL_MAP[symbol]

        # Auto-generate for unknown symbols
        if symbol.endswith('USDT.P'):
            base = symbol.replace('USDT.P', '')
            if len(base) <= 5:
                return base
            # For longer symbols, take first 4 chars
            return base[:4].upper()

        # Fallback
        return symbol[:5].upper()

    @classmethod
    def _get_strategy_abbr(cls, risk_strategy: str) -> str:
        """Get strategy abbreviation"""
        return cls.STRATEGY_MAP.get(risk_strategy, risk_strategy[:4].upper())

    @classmethod
    async def get_next_sequence(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        risk_strategy: str
    ) -> int:
        """
        Get next sequential number for this symbol+direction+strategy combination

        Example:
            get_next_sequence('AIAUSDT.P', 'LONG', 'strategy_A')
            Returns: 1 (if no previous trades), 2 (if 1 trade exists), etc.
        """
        result = await db.execute(
            select(func.count())
            .select_from(TradeSetup)
            .where(
                TradeSetup.symbol == symbol,
                TradeSetup.direction == direction,
                TradeSetup.risk_strategy == risk_strategy
            )
        )
        count = result.scalar()
        return (count or 0) + 1

    @classmethod
    async def generate_identifier(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        risk_strategy: str
    ) -> str:
        """
        Generate unique trade identifier

        Format: #AIALONG_A_001

        Args:
            db: Database session
            symbol: Trading symbol (e.g., 'AIAUSDT.P')
            direction: 'LONG' or 'SHORT'
            risk_strategy: 'baseline', 'strategy_A', 'strategy_B', 'strategy_C', 'strategy_D'

        Returns:
            Unique identifier string (e.g., '#AIALONG_A_001')

        Examples:
            >>> await generate_identifier(db, 'AIAUSDT.P', 'LONG', 'strategy_A')
            '#AIALONG_A_001'

            >>> await generate_identifier(db, 'FLUXUSDT.P', 'SHORT', 'baseline')
            '#FLUXSHORT_BASE_001'
        """
        # Get components
        symbol_abbr = cls._get_symbol_abbr(symbol)
        direction_upper = direction.upper()
        strategy_abbr = cls._get_strategy_abbr(risk_strategy)
        sequence = await cls.get_next_sequence(db, symbol, direction, risk_strategy)

        # Format: #AIALONG_A_001
        identifier = f"#{symbol_abbr}{direction_upper}_{strategy_abbr}_{sequence:03d}"

        logger.debug(
            f"Generated identifier: {identifier} "
            f"(symbol={symbol}, direction={direction}, strategy={risk_strategy}, seq={sequence})"
        )

        return identifier

    @classmethod
    async def update_existing_trades(cls, db: AsyncSession, limit: Optional[int] = None):
        """
        Backfill trade identifiers for existing trades

        Args:
            db: Database session
            limit: Max trades to update (None = all)
        """
        # Get trades without identifiers
        query = select(TradeSetup).where(
            TradeSetup.trade_identifier == None
        ).order_by(TradeSetup.created_at)

        if limit:
            query = query.limit(limit)

        result = await db.execute(query)
        trades = result.scalars().all()

        logger.info(f"Backfilling identifiers for {len(trades)} trades")

        updated_count = 0
        for trade in trades:
            # Skip if already has identifier
            if trade.trade_identifier:
                continue

            # Generate identifier
            identifier = await cls.generate_identifier(
                db,
                trade.symbol,
                trade.direction,
                trade.risk_strategy or 'baseline'
            )

            # Update trade
            trade.trade_identifier = identifier
            updated_count += 1

            if updated_count % 100 == 0:
                logger.info(f"Progress: {updated_count}/{len(trades)} trades updated")
                await db.flush()

        await db.commit()
        logger.info(f"✅ Backfilled {updated_count} trade identifiers")

        return updated_count
