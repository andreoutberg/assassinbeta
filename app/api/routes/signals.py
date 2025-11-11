"""
Trading Signals API Routes
Handles signal generation, quality analysis, and execution
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.database.connection import get_db
from app.api.deps import rate_limit_standard, rate_limit_low
from app.api.schemas.signals import (
    SignalResponse,
    SignalGenerateRequest,
    SignalQualityResponse,
    SignalExecuteRequest
)
from app.database.signal_quality_models import SignalQuality, SignalPerformance
from app.services.signal_generator import SignalGenerator
from app.services.signal_quality_analyzer import SignalQualityAnalyzer
from app.config.settings import settings
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/live", response_model=List[SignalResponse], dependencies=[Depends(rate_limit_standard)])
async def get_live_signals(
    request: Request,
    db: AsyncSession = Depends(get_db),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    min_confidence: float = Query(settings.SIGNAL_MIN_CONFIDENCE, description="Minimum confidence score")
):
    """
    Get currently active trading signals
    """
    try:
        # Get signal generator from app state
        signal_generator: SignalGenerator = request.app.state.signal_generator

        # Get active signals from the last 5 minutes
        cutoff_time = datetime.utcnow() - timedelta(minutes=5)

        query = select(SignalQuality).where(
            and_(
                SignalQuality.timestamp >= cutoff_time,
                SignalQuality.confidence >= min_confidence,
                SignalQuality.is_active == True
            )
        )

        if symbol:
            query = query.where(SignalQuality.symbol == symbol)

        query = query.order_by(desc(SignalQuality.confidence))

        result = await db.execute(query)
        signals = result.scalars().all()

        # Convert to response format
        response_signals = []
        for signal in signals:
            # Get real-time validation
            is_valid = await signal_generator.validate_signal(signal)

            if is_valid:
                response_signals.append(SignalResponse(
                    id=signal.id,
                    symbol=signal.symbol,
                    direction=signal.direction,
                    entry_price=signal.entry_price,
                    take_profit=signal.take_profit,
                    stop_loss=signal.stop_loss,
                    confidence=signal.confidence,
                    timeframe=signal.timeframe,
                    strategy_name=signal.strategy_name,
                    indicators=signal.indicators,
                    timestamp=signal.timestamp,
                    is_active=signal.is_active,
                    risk_reward_ratio=signal.risk_reward_ratio
                ))

        logger.info(f"Retrieved {len(response_signals)} live signals")
        return response_signals

    except Exception as e:
        logger.error(f"Error fetching live signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate", response_model=SignalResponse, dependencies=[Depends(rate_limit_low)])
async def generate_signal(
    request: Request,
    signal_request: SignalGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate new trading signal from market data
    """
    try:
        # Get services from app state
        signal_generator: SignalGenerator = request.app.state.signal_generator

        # Generate signal
        signal = await signal_generator.generate_signal(
            symbol=signal_request.symbol,
            timeframe=signal_request.timeframe,
            strategy_id=signal_request.strategy_id,
            force=signal_request.force
        )

        if not signal:
            raise HTTPException(status_code=404, detail="No valid signal could be generated")

        # Save to database
        signal_quality = SignalQuality(
            id=str(uuid.uuid4()),
            symbol=signal['symbol'],
            direction=signal['direction'],
            entry_price=signal['entry_price'],
            take_profit=signal['take_profit'],
            stop_loss=signal['stop_loss'],
            confidence=signal['confidence'],
            timeframe=signal['timeframe'],
            strategy_name=signal.get('strategy_name', 'manual'),
            indicators=signal.get('indicators', {}),
            risk_reward_ratio=signal.get('risk_reward_ratio', 0),
            timestamp=datetime.utcnow(),
            is_active=True
        )

        db.add(signal_quality)
        await db.commit()
        await db.refresh(signal_quality)

        logger.info(f"Generated new signal: {signal_quality.id} for {signal_quality.symbol}")

        return SignalResponse(
            id=signal_quality.id,
            symbol=signal_quality.symbol,
            direction=signal_quality.direction,
            entry_price=signal_quality.entry_price,
            take_profit=signal_quality.take_profit,
            stop_loss=signal_quality.stop_loss,
            confidence=signal_quality.confidence,
            timeframe=signal_quality.timeframe,
            strategy_name=signal_quality.strategy_name,
            indicators=signal_quality.indicators,
            timestamp=signal_quality.timestamp,
            is_active=signal_quality.is_active,
            risk_reward_ratio=signal_quality.risk_reward_ratio
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating signal: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/quality", response_model=SignalQualityResponse, dependencies=[Depends(rate_limit_standard)])
async def get_signal_quality_metrics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    period: str = Query("week", description="Time period: day, week, month"),
    symbol: Optional[str] = Query(None, description="Filter by symbol")
):
    """
    Get signal quality metrics and performance statistics
    """
    try:
        # Get analyzer from app state
        analyzer: SignalQualityAnalyzer = SignalQualityAnalyzer()

        # Determine date filter
        if period == "day":
            date_filter = datetime.utcnow() - timedelta(days=1)
        elif period == "week":
            date_filter = datetime.utcnow() - timedelta(weeks=1)
        else:  # month
            date_filter = datetime.utcnow() - timedelta(days=30)

        # Query signal performance
        query = select(SignalPerformance).where(
            SignalPerformance.timestamp >= date_filter
        )

        if symbol:
            query = query.where(SignalPerformance.symbol == symbol)

        result = await db.execute(query)
        performances = result.scalars().all()

        # Calculate metrics
        total_signals = len(performances)
        profitable_signals = sum(1 for p in performances if p.pnl > 0)

        if total_signals > 0:
            win_rate = (profitable_signals / total_signals) * 100
            avg_pnl = sum(p.pnl for p in performances) / total_signals
            avg_confidence = sum(p.confidence_score for p in performances) / total_signals

            # Calculate accuracy (signals that hit TP)
            tp_hit = sum(1 for p in performances if p.hit_take_profit)
            accuracy = (tp_hit / total_signals) * 100

            # Risk/reward analysis
            avg_rr = sum(p.risk_reward_actual for p in performances) / total_signals
        else:
            win_rate = 0
            avg_pnl = 0
            avg_confidence = 0
            accuracy = 0
            avg_rr = 0

        # Get quality distribution
        quality_distribution = {
            "excellent": sum(1 for p in performances if p.confidence_score >= 0.9),
            "good": sum(1 for p in performances if 0.7 <= p.confidence_score < 0.9),
            "fair": sum(1 for p in performances if 0.5 <= p.confidence_score < 0.7),
            "poor": sum(1 for p in performances if p.confidence_score < 0.5)
        }

        return SignalQualityResponse(
            total_signals=total_signals,
            win_rate=win_rate,
            accuracy=accuracy,
            avg_confidence=avg_confidence,
            avg_pnl=avg_pnl,
            avg_risk_reward=avg_rr,
            quality_distribution=quality_distribution,
            period=period,
            symbol=symbol
        )

    except Exception as e:
        logger.error(f"Error fetching signal quality metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{signal_id}", response_model=SignalResponse, dependencies=[Depends(rate_limit_standard)])
async def get_signal_details(
    signal_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific signal
    """
    try:
        result = await db.execute(
            select(SignalQuality).where(SignalQuality.id == signal_id)
        )
        signal = result.scalar_one_or_none()

        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")

        return SignalResponse(
            id=signal.id,
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=signal.entry_price,
            take_profit=signal.take_profit,
            stop_loss=signal.stop_loss,
            confidence=signal.confidence,
            timeframe=signal.timeframe,
            strategy_name=signal.strategy_name,
            indicators=signal.indicators,
            timestamp=signal.timestamp,
            is_active=signal.is_active,
            risk_reward_ratio=signal.risk_reward_ratio
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching signal details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{signal_id}/execute", response_model=dict, dependencies=[Depends(rate_limit_low)])
async def execute_signal(
    request: Request,
    signal_id: str,
    execute_request: SignalExecuteRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Execute a signal by creating a demo position
    """
    try:
        # Get signal
        result = await db.execute(
            select(SignalQuality).where(
                and_(
                    SignalQuality.id == signal_id,
                    SignalQuality.is_active == True
                )
            )
        )
        signal = result.scalar_one_or_none()

        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found or inactive")

        # Import demo trading module
        from app.api.routes.demo_trading import open_demo_position
        from app.api.schemas.demo_trading import DemoPositionCreate

        # Create position from signal
        position_data = DemoPositionCreate(
            symbol=signal.symbol,
            side="long" if signal.direction == "BUY" else "short",
            quantity=execute_request.quantity,
            entry_price=signal.entry_price,
            leverage=execute_request.leverage,
            take_profit=signal.take_profit,
            stop_loss=signal.stop_loss,
            signal_id=signal.id
        )

        # Execute position
        position = await open_demo_position(request, position_data, db)

        # Mark signal as executed
        signal.is_active = False
        await db.commit()

        logger.info(f"Executed signal {signal_id} as position {position.id}")

        return {
            "message": "Signal executed successfully",
            "signal_id": signal_id,
            "position_id": position.id,
            "entry_price": position.entry_price
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing signal: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=List[SignalResponse])
async def get_signal_history(
    db: AsyncSession = Depends(get_db),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    days: int = Query(7, description="Number of days to look back"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """
    Get historical signals
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        query = select(SignalQuality).where(
            SignalQuality.timestamp >= cutoff_date
        )

        if symbol:
            query = query.where(SignalQuality.symbol == symbol)

        query = query.order_by(desc(SignalQuality.timestamp)).limit(limit).offset(offset)

        result = await db.execute(query)
        signals = result.scalars().all()

        response_signals = []
        for signal in signals:
            response_signals.append(SignalResponse(
                id=signal.id,
                symbol=signal.symbol,
                direction=signal.direction,
                entry_price=signal.entry_price,
                take_profit=signal.take_profit,
                stop_loss=signal.stop_loss,
                confidence=signal.confidence,
                timeframe=signal.timeframe,
                strategy_name=signal.strategy_name,
                indicators=signal.indicators,
                timestamp=signal.timestamp,
                is_active=signal.is_active,
                risk_reward_ratio=signal.risk_reward_ratio
            ))

        logger.info(f"Retrieved {len(response_signals)} historical signals")
        return response_signals

    except Exception as e:
        logger.error(f"Error fetching signal history: {e}")
        raise HTTPException(status_code=500, detail=str(e))