"""
Demo Trading API Routes
Handles paper trading operations for testing strategies
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_

from app.database.connection import get_db, get_redis
from app.api.deps import get_current_user
from app.api.schemas.demo_trading import (
    DemoPositionCreate,
    DemoPositionResponse,
    DemoPositionUpdate,
    DemoBalanceResponse,
    DemoPositionStats,
    DemoPositionClose
)
from app.database.models import DemoPosition, DemoAccount
from app.services.market_data_service import MarketDataService
from app.config.settings import settings
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/positions", response_model=List[DemoPositionResponse])
async def get_demo_positions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status (open, closed, cancelled)"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """
    Get all demo trading positions
    """
    try:
        # Build query
        query = select(DemoPosition)

        # Apply filters
        conditions = []
        if status:
            conditions.append(DemoPosition.status == status)
        if symbol:
            conditions.append(DemoPosition.symbol == symbol)

        if conditions:
            query = query.where(and_(*conditions))

        # Apply pagination
        query = query.order_by(DemoPosition.created_at.desc()).limit(limit).offset(offset)

        # Execute query
        result = await db.execute(query)
        positions = result.scalars().all()

        # Get current prices for open positions
        market_service: MarketDataService = request.app.state.market_data_service
        for position in positions:
            if position.status == "open":
                current_price = await market_service.get_current_price(position.symbol)
                position.current_price = current_price
                position.unrealized_pnl = position.calculate_pnl(current_price)

        return positions

    except Exception as e:
        logger.error(f"Error fetching demo positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/open", response_model=DemoPositionResponse)
async def open_demo_position(
    request: Request,
    position_data: DemoPositionCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Open a new demo position
    """
    try:
        # Get or create demo account
        demo_account = await db.execute(
            select(DemoAccount).where(DemoAccount.id == 1)
        )
        account = demo_account.scalar_one_or_none()

        if not account:
            # Create default demo account
            account = DemoAccount(
                id=1,
                balance=settings.DEMO_STARTING_BALANCE,
                equity=settings.DEMO_STARTING_BALANCE,
                margin_used=0,
                free_margin=settings.DEMO_STARTING_BALANCE
            )
            db.add(account)
            await db.commit()

        # Check if account has sufficient margin
        required_margin = (position_data.quantity * position_data.entry_price) / position_data.leverage
        if required_margin > account.free_margin:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient margin. Required: {required_margin}, Available: {account.free_margin}"
            )

        # Get current market price
        market_service: MarketDataService = request.app.state.market_data_service
        current_price = await market_service.get_current_price(position_data.symbol)

        # Validate entry price (should be close to market price)
        price_diff_pct = abs(current_price - position_data.entry_price) / current_price * 100
        if price_diff_pct > 1:  # More than 1% difference
            logger.warning(f"Entry price {position_data.entry_price} differs from market price {current_price} by {price_diff_pct:.2f}%")

        # Create position
        position = DemoPosition(
            id=str(uuid.uuid4()),
            symbol=position_data.symbol,
            side=position_data.side,
            quantity=position_data.quantity,
            entry_price=position_data.entry_price or current_price,
            current_price=current_price,
            leverage=position_data.leverage,
            take_profit=position_data.take_profit,
            stop_loss=position_data.stop_loss,
            status="open",
            strategy_id=position_data.strategy_id,
            signal_id=position_data.signal_id,
            created_at=datetime.utcnow(),
            unrealized_pnl=0,
            realized_pnl=0,
            commission=position_data.quantity * current_price * settings.DEMO_TAKER_FEE
        )

        # Update account margin
        account.margin_used += required_margin
        account.free_margin -= required_margin

        # Save to database
        db.add(position)
        await db.commit()
        await db.refresh(position)

        logger.info(f"Opened demo position: {position.id} for {position.symbol}")

        return position

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error opening demo position: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/{position_id}/close", response_model=DemoPositionResponse)
async def close_demo_position(
    request: Request,
    position_id: str,
    close_data: DemoPositionClose,
    db: AsyncSession = Depends(get_db)
):
    """
    Close an open demo position
    """
    try:
        # Get position
        result = await db.execute(
            select(DemoPosition).where(
                and_(
                    DemoPosition.id == position_id,
                    DemoPosition.status == "open"
                )
            )
        )
        position = result.scalar_one_or_none()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found or already closed")

        # Get current market price
        market_service: MarketDataService = request.app.state.market_data_service
        exit_price = close_data.exit_price or await market_service.get_current_price(position.symbol)

        # Calculate P&L
        if position.side == "long":
            pnl = (exit_price - position.entry_price) * position.quantity
        else:  # short
            pnl = (position.entry_price - exit_price) * position.quantity

        # Calculate commission
        commission = position.quantity * exit_price * settings.DEMO_TAKER_FEE
        realized_pnl = pnl - position.commission - commission

        # Update position
        position.exit_price = exit_price
        position.realized_pnl = realized_pnl
        position.status = "closed"
        position.closed_at = datetime.utcnow()
        position.close_reason = close_data.reason or "manual"

        # Update demo account
        account = await db.execute(select(DemoAccount).where(DemoAccount.id == 1))
        account = account.scalar_one()

        # Return margin and apply P&L
        required_margin = (position.quantity * position.entry_price) / position.leverage
        account.margin_used -= required_margin
        account.free_margin += required_margin
        account.balance += realized_pnl
        account.equity = account.balance + account.margin_used

        await db.commit()
        await db.refresh(position)

        logger.info(f"Closed demo position: {position.id} with P&L: {realized_pnl:.2f}")

        return position

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error closing demo position: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions/{position_id}", response_model=DemoPositionResponse)
async def get_demo_position(
    request: Request,
    position_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific demo position
    """
    try:
        result = await db.execute(
            select(DemoPosition).where(DemoPosition.id == position_id)
        )
        position = result.scalar_one_or_none()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        # Update current price if position is open
        if position.status == "open":
            market_service: MarketDataService = request.app.state.market_data_service
            position.current_price = await market_service.get_current_price(position.symbol)
            position.unrealized_pnl = position.calculate_pnl(position.current_price)

        return position

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching demo position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions/stats", response_model=DemoPositionStats)
async def get_demo_stats(
    db: AsyncSession = Depends(get_db),
    period: Optional[str] = Query("all", description="Time period: today, week, month, all")
):
    """
    Get P&L summary and statistics for demo positions
    """
    try:
        # Determine date filter
        date_filter = None
        if period == "today":
            date_filter = datetime.utcnow() - timedelta(days=1)
        elif period == "week":
            date_filter = datetime.utcnow() - timedelta(weeks=1)
        elif period == "month":
            date_filter = datetime.utcnow() - timedelta(days=30)

        # Build query
        query = select(DemoPosition).where(DemoPosition.status == "closed")
        if date_filter:
            query = query.where(DemoPosition.closed_at >= date_filter)

        result = await db.execute(query)
        positions = result.scalars().all()

        # Calculate statistics
        total_trades = len(positions)
        winning_trades = sum(1 for p in positions if p.realized_pnl > 0)
        losing_trades = sum(1 for p in positions if p.realized_pnl < 0)

        total_pnl = sum(p.realized_pnl for p in positions)
        total_profit = sum(p.realized_pnl for p in positions if p.realized_pnl > 0)
        total_loss = sum(abs(p.realized_pnl) for p in positions if p.realized_pnl < 0)

        avg_win = total_profit / winning_trades if winning_trades > 0 else 0
        avg_loss = total_loss / losing_trades if losing_trades > 0 else 0

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf') if total_profit > 0 else 0

        # Get current account balance
        account = await db.execute(select(DemoAccount).where(DemoAccount.id == 1))
        account = account.scalar_one_or_none()

        return DemoPositionStats(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_profit=total_profit,
            total_loss=total_loss,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            current_balance=account.balance if account else settings.DEMO_STARTING_BALANCE,
            period=period
        )

    except Exception as e:
        logger.error(f"Error calculating demo stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/positions/{position_id}", response_model=DemoPositionResponse)
async def update_demo_position(
    position_id: str,
    update_data: DemoPositionUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update take profit or stop loss for an open position
    """
    try:
        result = await db.execute(
            select(DemoPosition).where(
                and_(
                    DemoPosition.id == position_id,
                    DemoPosition.status == "open"
                )
            )
        )
        position = result.scalar_one_or_none()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found or already closed")

        # Update fields if provided
        if update_data.take_profit is not None:
            position.take_profit = update_data.take_profit
        if update_data.stop_loss is not None:
            position.stop_loss = update_data.stop_loss

        position.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(position)

        logger.info(f"Updated demo position: {position.id}")

        return position

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating demo position: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/positions/{position_id}")
async def cancel_demo_position(
    position_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel a pending demo position
    """
    try:
        result = await db.execute(
            select(DemoPosition).where(
                and_(
                    DemoPosition.id == position_id,
                    DemoPosition.status == "open"
                )
            )
        )
        position = result.scalar_one_or_none()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        # Mark as cancelled
        position.status = "cancelled"
        position.closed_at = datetime.utcnow()
        position.close_reason = "cancelled"

        # Return margin to account
        account = await db.execute(select(DemoAccount).where(DemoAccount.id == 1))
        account = account.scalar_one()

        required_margin = (position.quantity * position.entry_price) / position.leverage
        account.margin_used -= required_margin
        account.free_margin += required_margin

        await db.commit()

        logger.info(f"Cancelled demo position: {position.id}")

        return {"message": "Position cancelled successfully", "position_id": position_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling demo position: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balance", response_model=DemoBalanceResponse)
async def get_demo_balance(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Get current demo account balance and equity
    """
    try:
        # Get or create demo account
        result = await db.execute(select(DemoAccount).where(DemoAccount.id == 1))
        account = result.scalar_one_or_none()

        if not account:
            # Create default demo account
            account = DemoAccount(
                id=1,
                balance=settings.DEMO_STARTING_BALANCE,
                equity=settings.DEMO_STARTING_BALANCE,
                margin_used=0,
                free_margin=settings.DEMO_STARTING_BALANCE
            )
            db.add(account)
            await db.commit()
            await db.refresh(account)

        # Calculate unrealized P&L from open positions
        open_positions = await db.execute(
            select(DemoPosition).where(DemoPosition.status == "open")
        )
        positions = open_positions.scalars().all()

        market_service: MarketDataService = request.app.state.market_data_service
        unrealized_pnl = 0

        for position in positions:
            current_price = await market_service.get_current_price(position.symbol)
            if position.side == "long":
                pnl = (current_price - position.entry_price) * position.quantity
            else:
                pnl = (position.entry_price - current_price) * position.quantity
            unrealized_pnl += pnl

        # Update equity
        account.equity = account.balance + unrealized_pnl
        account.margin_level = (account.equity / account.margin_used * 100) if account.margin_used > 0 else 0

        return DemoBalanceResponse(
            balance=account.balance,
            equity=account.equity,
            margin_used=account.margin_used,
            free_margin=account.free_margin,
            unrealized_pnl=unrealized_pnl,
            margin_level=account.margin_level,
            open_positions=len(positions),
            total_commission=sum(p.commission for p in positions)
        )

    except Exception as e:
        logger.error(f"Error fetching demo balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))