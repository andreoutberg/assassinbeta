"""
Dashboard API Routes

High-performance endpoints for real-time trading dashboard.
Implements caching, WebSocket updates, and optimized queries.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
import time

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy import select, func, and_, or_, case, distinct, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.database.database import get_db, AsyncSessionLocal
from app.database.models import (
    TradeSetup, TradeMilestones, AssetStatistics,
    PriceAction, TradePriceSample
)
from app.database.signal_quality_models import SignalQuality
from app.database.strategy_models import StrategySimulation, StrategyPerformance
from app.api.schemas.dashboard import (
    DashboardOverviewResponse, SystemMetrics,
    DashboardPhasesResponse, PhaseMetrics, SignalBreakdown,
    DashboardSignalQualityResponse, SignalQualityMetrics, SignalDistribution,
    DashboardStrategiesResponse, StrategyMetrics, StrategyComparison,
    DashboardRiskResponse, CircuitBreakerStatus, DrawdownMetrics, ActiveRiskMetrics,
    WebSocketMessage, NewTradeNotification, PhaseTransitionNotification,
    TradeUpdateNotification, AlertNotification,
    SystemHealthResponse, ServiceHealth
)
from app.utils.cache import cached, get_cache
from app.config.phase_config import PhaseConfig
from app.services.strategy_selector import StrategySelector
from app.services.asset_health_monitor import AssetHealthMonitor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ============== WebSocket Connection Manager ==============

class DashboardConnectionManager:
    """Manages WebSocket connections for dashboard real-time updates"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_metadata: Dict[WebSocket, Dict] = {}

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_metadata[websocket] = {
            "connected_at": datetime.utcnow(),
            "client_id": id(websocket)
        }
        logger.info(f"Dashboard WebSocket connected: {id(websocket)}")

    def disconnect(self, websocket: WebSocket):
        """Remove disconnected WebSocket"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            del self.connection_metadata[websocket]
            logger.info(f"Dashboard WebSocket disconnected: {id(websocket)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients using parallel sending."""
        if not self.active_connections:
            return

        message_json = WebSocketMessage(
            event_type=message.get("event_type", "update"),
            data=message
        ).model_dump_json()

        # Send to all connections in parallel using asyncio.gather
        # This prevents slow clients from blocking fast ones
        send_tasks = [
            self._send_to_connection(connection, message_json)
            for connection in list(self.active_connections)
        ]

        # Execute all sends in parallel, ignore exceptions (handled in _send_to_connection)
        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)

    async def _send_to_connection(self, connection: WebSocket, message_json: str):
        """Send message to a single connection with timeout and error handling."""
        try:
            # Add timeout to prevent slow clients from blocking
            await asyncio.wait_for(
                connection.send_text(message_json),
                timeout=5.0  # 5 second timeout per client
            )
        except asyncio.TimeoutError:
            logger.warning(f"Timeout sending to WebSocket: {id(connection)}")
            self.disconnect(connection)
        except Exception as e:
            logger.warning(f"Failed to send to WebSocket: {e}")
            self.disconnect(connection)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send message to specific client"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
            self.disconnect(websocket)


# Global WebSocket manager instance
dashboard_manager = DashboardConnectionManager()


# ============== Helper Functions ==============

async def calculate_system_health_score(db: AsyncSession) -> float:
    """Calculate overall system health score (0-100)"""
    # Check various health metrics
    score = 100.0

    # Check for circuit breakers (subtract 20 points per active breaker)
    circuit_breaker_count = await AssetHealthMonitor.get_active_circuit_breakers_count(db)
    score -= circuit_breaker_count * 20

    # Check drawdown (subtract points based on drawdown percentage)
    drawdown_query = await db.execute(
        select(
            func.max(TradeSetup.max_adverse_excursion_pct).label("max_drawdown")
        ).where(
            TradeSetup.status == 'closed',
            TradeSetup.created_at >= datetime.utcnow() - timedelta(days=7)
        )
    )
    max_drawdown = drawdown_query.scalar() or 0
    if max_drawdown:
        score -= min(float(max_drawdown) * 2, 30)  # Max 30 point penalty

    # Check win rate (add/subtract based on performance)
    win_rate_query = await db.execute(
        select(
            func.count(case((TradeSetup.final_pnl_pct > 0, 1))).label("wins"),
            func.count(TradeSetup.id).label("total")
        ).where(
            TradeSetup.status == 'closed',
            TradeSetup.created_at >= datetime.utcnow() - timedelta(days=7)
        )
    )
    result = win_rate_query.first()
    if result and result.total > 0:
        win_rate = (result.wins / result.total) * 100
        if win_rate < 40:
            score -= 20
        elif win_rate > 60:
            score += 10

    return max(0, min(100, score))


async def determine_trade_phase(trade: TradeSetup, db: AsyncSession) -> str:
    """Determine which phase a trade is in"""
    phase_info = await StrategySelector.determine_trade_phase(
        db, trade.symbol, trade.direction, trade.webhook_source
    )
    return phase_info['phase']


# ============== API Endpoints ==============

@router.get("/overview", response_model=DashboardOverviewResponse)
@cached(ttl_seconds=10)  # Cache for 10 seconds
async def get_dashboard_overview(db: AsyncSession = Depends(get_db)):
    """
    Get overall system metrics with sub-100ms response time.
    Cached for 10 seconds to reduce database load.
    """
    start_time = time.time()

    try:
        # Use optimized single query with subqueries
        metrics_query = await db.execute(
            select(
                func.count(TradeSetup.id).label("total_trades"),
                func.count(case((TradeSetup.status == 'active', 1))).label("active_trades"),
                func.count(distinct(TradeSetup.symbol)).label("total_symbols"),
                func.avg(case((TradeSetup.status == 'closed',
                              case((TradeSetup.final_pnl_pct > 0, 100), else_=0)))).label("win_rate"),
                func.avg(TradeSetup.risk_reward_ratio).label("avg_rr"),
                func.sum(TradeSetup.final_pnl_usd).label("total_pnl_usd"),
                func.avg(TradeSetup.final_pnl_pct).label("avg_pnl_pct"),
                func.count(case((TradeSetup.created_at >= datetime.utcnow() - timedelta(days=1), 1))).label("volume_24h"),
                func.count(case((TradeSetup.created_at >= datetime.utcnow() - timedelta(days=7), 1))).label("volume_7d"),
                func.count(case((TradeSetup.created_at >= datetime.utcnow() - timedelta(days=30), 1))).label("volume_30d")
            )
        )
        metrics = metrics_query.first()

        # Get circuit breaker count
        circuit_breakers = await AssetHealthMonitor.get_active_circuit_breakers_count(db)

        # Calculate system health
        health_score = await calculate_system_health_score(db)

        # Build response
        system_metrics = SystemMetrics(
            total_trades=metrics.total_trades or 0,
            active_trades=metrics.active_trades or 0,
            total_symbols=metrics.total_symbols or 0,
            overall_win_rate=float(metrics.win_rate or 0),
            overall_rr_ratio=float(metrics.avg_rr or 0),
            total_pnl_usd=float(metrics.total_pnl_usd or 0),
            total_pnl_pct=float(metrics.avg_pnl_pct or 0) * (metrics.total_trades or 1),
            volume_24h=float(metrics.volume_24h or 0),
            volume_7d=float(metrics.volume_7d or 0),
            volume_30d=float(metrics.volume_30d or 0),
            circuit_breakers_active=circuit_breakers,
            system_health_score=health_score,
            last_updated=datetime.utcnow()
        )

        response_time = (time.time() - start_time) * 1000  # Convert to ms

        return DashboardOverviewResponse(
            metrics=system_metrics,
            response_time_ms=response_time
        )

    except Exception as e:
        logger.error(f"Dashboard overview error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/phases", response_model=DashboardPhasesResponse)
@cached(ttl_seconds=30)  # Cache for 30 seconds
async def get_phase_breakdown(db: AsyncSession = Depends(get_db)):
    """Get detailed breakdown of trades by phase"""
    start_time = time.time()

    try:
        phase_metrics = []

        # Analyze each phase
        for phase_num, phase_name in [(1, "Phase I"), (2, "Phase II"), (3, "Phase III")]:
            # Get trades for this phase
            # Note: We need to determine phase dynamically based on trade count
            phase_trades_query = await db.execute(
                select(TradeSetup).options(selectinload(TradeSetup.milestones))
            )
            phase_trades = phase_trades_query.scalars().all()

            # Filter trades by phase
            trades_in_phase = []
            for trade in phase_trades:
                trade_phase = await determine_trade_phase(trade, db)
                if trade_phase == f"phase_{phase_num}":
                    trades_in_phase.append(trade)

            if not trades_in_phase:
                phase_metrics.append(PhaseMetrics(
                    phase_name=phase_name,
                    trade_count=0,
                    active_count=0,
                    win_rate=0,
                    avg_pnl_pct=0,
                    total_pnl_usd=0,
                    risk_reward_ratio=0,
                    avg_duration_hours=0,
                    fastest_tp_minutes=None,
                    unique_symbols=0,
                    top_symbol=None,
                    top_strategy=None
                ))
                continue

            # Calculate metrics
            active_count = len([t for t in trades_in_phase if t.status == 'active'])
            closed_trades = [t for t in trades_in_phase if t.status == 'closed']

            wins = [t for t in closed_trades if t.final_pnl_pct and t.final_pnl_pct > 0]
            win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0

            avg_pnl_pct = sum(float(t.final_pnl_pct or 0) for t in closed_trades) / len(closed_trades) if closed_trades else 0
            total_pnl_usd = sum(float(t.final_pnl_usd or 0) for t in trades_in_phase)

            rr_values = [float(t.risk_reward_ratio) for t in trades_in_phase if t.risk_reward_ratio]
            avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0

            durations = [t.trade_duration_hours for t in closed_trades if t.trade_duration_hours]
            avg_duration = sum(durations) / len(durations) if durations else 0

            # Find fastest TP hit
            tp_times = []
            for t in trades_in_phase:
                if t.tp1_time_minutes:
                    tp_times.append(t.tp1_time_minutes)
                if t.tp2_time_minutes:
                    tp_times.append(t.tp2_time_minutes)
                if t.tp3_time_minutes:
                    tp_times.append(t.tp3_time_minutes)
            fastest_tp = min(tp_times) if tp_times else None

            # Symbol analysis
            symbol_counts = {}
            for t in trades_in_phase:
                symbol_counts[t.symbol] = symbol_counts.get(t.symbol, 0) + 1
            top_symbol = max(symbol_counts.items(), key=lambda x: x[1])[0] if symbol_counts else None

            # Strategy analysis (for Phase II/III)
            strategy_counts = {}
            if phase_num >= 2:
                for t in trades_in_phase:
                    if t.risk_strategy:
                        strategy_counts[t.risk_strategy] = strategy_counts.get(t.risk_strategy, 0) + 1
            top_strategy = max(strategy_counts.items(), key=lambda x: x[1])[0] if strategy_counts else None

            phase_metrics.append(PhaseMetrics(
                phase_name=phase_name,
                trade_count=len(trades_in_phase),
                active_count=active_count,
                win_rate=win_rate,
                avg_pnl_pct=avg_pnl_pct,
                total_pnl_usd=total_pnl_usd,
                risk_reward_ratio=avg_rr,
                avg_duration_hours=avg_duration,
                fastest_tp_minutes=fastest_tp,
                unique_symbols=len(set(t.symbol for t in trades_in_phase)),
                top_symbol=top_symbol,
                top_strategy=top_strategy
            ))

        # Get signal breakdown
        signal_query = await db.execute(
            select(
                TradeSetup.webhook_source,
                func.count(TradeSetup.id).label("count")
            ).group_by(TradeSetup.webhook_source)
        )
        signal_results = signal_query.all()

        signal_breakdown = []
        for source, count in signal_results:
            if not source:
                continue

            # Get quality score for this signal
            quality_query = await db.execute(
                select(SignalQuality.quality_score).where(
                    SignalQuality.webhook_source == source
                ).limit(1)
            )
            quality_score = quality_query.scalar() or 0

            signal_breakdown.append(SignalBreakdown(
                webhook_source=source,
                phase_i_count=0,  # Will be calculated properly with phase detection
                phase_ii_count=0,
                phase_iii_count=0,
                total_count=count,
                avg_quality_score=float(quality_score)
            ))

        # Calculate phase transitions
        phase_transitions = {
            "i_to_ii": 0,
            "ii_to_iii": 0
        }
        # This would require tracking phase changes over time
        # Simplified for now

        response_time = (time.time() - start_time) * 1000

        return DashboardPhasesResponse(
            phases=phase_metrics,
            signal_breakdown=signal_breakdown,
            phase_transitions=phase_transitions,
            response_time_ms=response_time
        )

    except Exception as e:
        logger.error(f"Phase breakdown error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signal-quality", response_model=DashboardSignalQualityResponse)
@cached(ttl_seconds=60)  # Cache for 1 minute
async def get_signal_quality(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(10, description="Number of top signals to return")
):
    """Get signal quality metrics and recommendations"""
    start_time = time.time()

    try:
        # Get all signal quality records
        quality_query = await db.execute(
            select(SignalQuality).order_by(SignalQuality.quality_score.desc())
        )
        all_signals = quality_query.scalars().all()

        # Calculate distribution
        distribution = SignalDistribution(
            excellent=len([s for s in all_signals if s.quality_score > 80]),
            good=len([s for s in all_signals if 60 <= s.quality_score <= 80]),
            fair=len([s for s in all_signals if 40 <= s.quality_score < 60]),
            poor=len([s for s in all_signals if s.quality_score < 40]),
            total_signals=len(all_signals),
            avg_quality_score=sum(float(s.quality_score) for s in all_signals) / len(all_signals) if all_signals else 0,
            signals_with_edge=len([s for s in all_signals if s.has_edge]),
            signals_needing_data=len([s for s in all_signals if s.recommendation == 'collect_more_data'])
        )

        # Get top signals
        top_signals = []
        for signal in all_signals[:limit]:
            top_signals.append(SignalQualityMetrics(
                symbol=signal.symbol,
                direction=signal.direction,
                webhook_source=signal.webhook_source,
                quality_score=float(signal.quality_score),
                raw_win_rate=float(signal.raw_win_rate),
                confidence_interval_lower=float(signal.ci_lower),
                confidence_interval_upper=float(signal.ci_upper),
                expected_value=float(signal.expected_value),
                sample_size=signal.sample_size,
                is_significant=signal.is_significant,
                p_value=float(signal.p_value),
                has_edge=signal.has_edge,
                recommendation=signal.recommendation,
                last_analyzed=signal.last_analyzed_at
            ))

        # Recommendations breakdown
        recommendations = {}
        for signal in all_signals:
            recommendations[signal.recommendation] = recommendations.get(signal.recommendation, 0) + 1

        response_time = (time.time() - start_time) * 1000

        return DashboardSignalQualityResponse(
            distribution=distribution,
            top_signals=top_signals,
            recommendations_breakdown=recommendations,
            response_time_ms=response_time
        )

    except Exception as e:
        logger.error(f"Signal quality error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies", response_model=DashboardStrategiesResponse)
@cached(ttl_seconds=30)  # Cache for 30 seconds
async def get_strategy_performance(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, description="Number of top strategies to return")
):
    """Get strategy performance metrics and comparisons"""
    start_time = time.time()

    try:
        # Get strategy performance records
        perf_query = await db.execute(
            select(StrategyPerformance)
            .order_by(StrategyPerformance.strategy_score.desc())
            .limit(limit)
        )
        top_performances = perf_query.scalars().all()

        # Convert to response models
        top_strategies = []
        for perf in top_performances:
            top_strategies.append(StrategyMetrics(
                strategy_name=perf.strategy_name,
                symbol=perf.symbol,
                direction=perf.direction,
                webhook_source=perf.webhook_source,
                win_rate=float(perf.win_rate or 0),
                win_count=perf.win_count or 0,
                loss_count=perf.loss_count or 0,
                avg_win_pct=float(perf.avg_win or 0),
                avg_loss_pct=float(perf.avg_loss or 0),
                risk_reward_ratio=float(perf.risk_reward or 0),
                total_pnl_usd=float(perf.total_simulated_pnl or 0),
                strategy_score=float(perf.strategy_score or 0),
                avg_duration_hours=float(perf.avg_duration_hours or 0),
                max_duration_hours=float(perf.max_duration_hours or 0),
                current_tp1_pct=float(perf.current_tp1_pct or 0),
                current_tp2_pct=float(perf.current_tp2_pct or 0),
                current_tp3_pct=float(perf.current_tp3_pct or 0),
                current_sl_pct=float(perf.current_sl_pct or 0),
                trailing_enabled=perf.current_trailing_enabled or False,
                breakeven_trigger_pct=float(perf.current_breakeven_trigger_pct) if perf.current_breakeven_trigger_pct else None,
                is_eligible_phase3=perf.is_eligible_for_phase3 or False,
                meets_rr_requirement=perf.meets_rr_requirement or False,
                meets_duration_requirement=perf.meets_duration_requirement or False,
                has_real_sl=perf.has_real_sl or False
            ))

        # Get strategy comparisons
        comparison_query = await db.execute(
            select(
                StrategyPerformance.symbol,
                StrategyPerformance.direction,
                StrategyPerformance.webhook_source
            ).distinct()
        )
        comparison_groups = comparison_query.all()

        comparisons = []
        for symbol, direction, webhook_source in comparison_groups[:10]:  # Limit comparisons
            # Get all strategies for this combination
            strat_query = await db.execute(
                select(StrategyPerformance).where(
                    and_(
                        StrategyPerformance.symbol == symbol,
                        StrategyPerformance.direction == direction,
                        StrategyPerformance.webhook_source == webhook_source
                    )
                ).order_by(StrategyPerformance.strategy_score.desc())
            )
            strategies = strat_query.scalars().all()

            if strategies:
                comparison_data = []
                for strat in strategies:
                    comparison_data.append({
                        "name": strat.strategy_name,
                        "score": float(strat.strategy_score or 0),
                        "win_rate": float(strat.win_rate or 0),
                        "risk_reward": float(strat.risk_reward or 0)
                    })

                comparisons.append(StrategyComparison(
                    symbol=symbol,
                    direction=direction,
                    webhook_source=webhook_source,
                    strategies=comparison_data,
                    best_strategy=strategies[0].strategy_name,
                    best_strategy_score=float(strategies[0].strategy_score or 0)
                ))

        # Calculate aggregated metrics
        all_strategies_query = await db.execute(
            select(
                func.count(StrategyPerformance.id).label("total"),
                func.count(case((StrategyPerformance.is_eligible_for_phase3 == True, 1))).label("eligible"),
                func.avg(StrategyPerformance.strategy_score).label("avg_score")
            )
        )
        agg_metrics = all_strategies_query.first()

        # Find best performing parameters across all strategies
        best_params_query = await db.execute(
            select(
                func.avg(StrategyPerformance.current_tp1_pct).label("avg_tp1"),
                func.avg(StrategyPerformance.current_sl_pct).label("avg_sl"),
                func.mode().within_group(StrategyPerformance.current_trailing_enabled).label("common_trailing")
            ).where(
                StrategyPerformance.strategy_score > 70  # Only from good strategies
            )
        )
        best_params = best_params_query.first()

        best_performing_params = {}
        if best_params:
            best_performing_params = {
                "avg_tp1_pct": float(best_params.avg_tp1 or 0),
                "avg_sl_pct": float(best_params.avg_sl or 0),
                "most_common_trailing": bool(best_params.common_trailing) if best_params.common_trailing is not None else False
            }

        response_time = (time.time() - start_time) * 1000

        return DashboardStrategiesResponse(
            top_strategies=top_strategies,
            comparisons=comparisons,
            total_strategies=agg_metrics.total or 0,
            phase3_eligible_count=agg_metrics.eligible or 0,
            avg_strategy_score=float(agg_metrics.avg_score or 0),
            best_performing_params=best_performing_params,
            response_time_ms=response_time
        )

    except Exception as e:
        logger.error(f"Strategy performance error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk", response_model=DashboardRiskResponse)
@cached(ttl_seconds=5)  # Cache for only 5 seconds (risk is critical)
async def get_risk_metrics(db: AsyncSession = Depends(get_db)):
    """Get current risk metrics and circuit breaker status"""
    start_time = time.time()

    try:
        # Get circuit breaker status
        circuit_breakers = []

        # Query for assets with potential circuit breaker triggers
        cb_query = await db.execute(
            select(
                TradeSetup.symbol,
                TradeSetup.direction,
                TradeSetup.webhook_source,
                func.count(case((TradeSetup.final_pnl_pct < 0, 1))).label("consecutive_losses"),
                func.min(TradeSetup.final_pnl_pct).label("max_drawdown")
            ).where(
                TradeSetup.status == 'closed',
                TradeSetup.created_at >= datetime.utcnow() - timedelta(days=7)
            ).group_by(
                TradeSetup.symbol,
                TradeSetup.direction,
                TradeSetup.webhook_source
            )
        )

        for row in cb_query.all():
            # Determine phase for this asset
            phase_info = await StrategySelector.determine_trade_phase(
                db, row.symbol, row.direction, row.webhook_source
            )

            # Check if circuit breaker should be active
            is_active = row.consecutive_losses >= 5 or abs(float(row.max_drawdown or 0)) > 10

            circuit_breakers.append(CircuitBreakerStatus(
                symbol=row.symbol,
                direction=row.direction,
                webhook_source=row.webhook_source,
                phase=phase_info['phase'],
                is_active=is_active,
                trigger_reason="Consecutive losses" if row.consecutive_losses >= 5 else "Excessive drawdown" if is_active else None,
                consecutive_losses=row.consecutive_losses,
                drawdown_pct=abs(float(row.max_drawdown or 0)),
                recovery_time_remaining=30 if is_active else None,  # 30 minutes recovery
                loss_threshold=5,
                drawdown_threshold=10.0
            ))

        # Calculate drawdown metrics
        dd_query = await db.execute(
            select(
                func.min(TradeSetup.final_pnl_pct).label("max_dd"),
                func.min(TradeSetup.created_at).label("max_dd_date")
            ).where(
                TradeSetup.status == 'closed',
                TradeSetup.final_pnl_pct < 0
            )
        )
        dd_result = dd_query.first()

        # Current drawdown (recent performance)
        current_dd_query = await db.execute(
            select(func.avg(TradeSetup.final_pnl_pct)).where(
                TradeSetup.status == 'closed',
                TradeSetup.created_at >= datetime.utcnow() - timedelta(days=1)
            )
        )
        current_dd = current_dd_query.scalar() or 0

        drawdown_metrics = DrawdownMetrics(
            current_drawdown_pct=abs(float(current_dd)) if current_dd < 0 else 0,
            max_drawdown_pct=abs(float(dd_result.max_dd or 0)),
            max_drawdown_date=dd_result.max_dd_date or datetime.utcnow(),
            recovery_days=(datetime.utcnow() - dd_result.max_dd_date).days if dd_result.max_dd_date else None,
            phase_i_drawdown=0,  # Would need phase-specific tracking
            phase_ii_drawdown=0,
            phase_iii_drawdown=0
        )

        # Calculate active risk metrics
        active_query = await db.execute(
            select(
                func.sum(TradeSetup.notional_position_usd).label("total_exposure"),
                func.sum(TradeSetup.margin_required_usd).label("total_margin"),
                func.avg(TradeSetup.leverage).label("avg_leverage"),
                func.count(case((TradeSetup.current_price <= TradeSetup.planned_sl_price * 1.05, 1))).label("at_risk"),
                func.count(case((TradeSetup.current_price > TradeSetup.entry_price, 1))).label("in_profit")
            ).where(TradeSetup.status == 'active')
        )
        active_result = active_query.first()

        # Get max exposure per symbol
        exposure_query = await db.execute(
            select(
                TradeSetup.symbol,
                func.sum(TradeSetup.notional_position_usd).label("symbol_exposure")
            ).where(
                TradeSetup.status == 'active'
            ).group_by(TradeSetup.symbol).order_by(text("symbol_exposure DESC")).limit(1)
        )
        max_exposure = exposure_query.first()

        total_exposure = float(active_result.total_exposure or 0)
        max_symbol_exposure_pct = (float(max_exposure.symbol_exposure) / total_exposure * 100) if max_exposure and total_exposure > 0 else 0

        active_risk = ActiveRiskMetrics(
            total_exposure_usd=total_exposure,
            margin_used_usd=float(active_result.total_margin or 0),
            leverage_weighted_avg=float(active_result.avg_leverage or 0),
            positions_at_risk=active_result.at_risk or 0,
            positions_in_profit=active_result.in_profit or 0,
            max_symbol_exposure_pct=max_symbol_exposure_pct,
            max_symbol=max_exposure.symbol if max_exposure else ""
        )

        # Generate alerts
        active_alerts = []

        # Check for high drawdown
        if drawdown_metrics.current_drawdown_pct > 5:
            active_alerts.append({
                "type": "drawdown",
                "severity": "warning" if drawdown_metrics.current_drawdown_pct < 10 else "critical",
                "message": f"Current drawdown: {drawdown_metrics.current_drawdown_pct:.1f}%"
            })

        # Check for concentration risk
        if active_risk.max_symbol_exposure_pct > 30:
            active_alerts.append({
                "type": "concentration",
                "severity": "warning",
                "message": f"High exposure to {active_risk.max_symbol}: {active_risk.max_symbol_exposure_pct:.1f}%"
            })

        # Check for circuit breakers
        active_cb_count = len([cb for cb in circuit_breakers if cb.is_active])
        if active_cb_count > 0:
            active_alerts.append({
                "type": "circuit_breaker",
                "severity": "critical" if active_cb_count > 2 else "warning",
                "message": f"{active_cb_count} circuit breakers active"
            })

        # Calculate overall risk score (0-100, lower is better)
        risk_score = 0
        risk_score += drawdown_metrics.current_drawdown_pct * 2  # Weight drawdown heavily
        risk_score += active_cb_count * 10  # 10 points per circuit breaker
        risk_score += max(0, active_risk.max_symbol_exposure_pct - 20)  # Penalty for concentration > 20%
        risk_score = min(100, risk_score)

        response_time = (time.time() - start_time) * 1000

        return DashboardRiskResponse(
            circuit_breakers=circuit_breakers,
            drawdown_metrics=drawdown_metrics,
            active_risk=active_risk,
            active_alerts=active_alerts,
            risk_score=risk_score,
            response_time_ms=response_time
        )

    except Exception as e:
        logger.error(f"Risk metrics error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=SystemHealthResponse)
async def get_system_health(db: AsyncSession = Depends(get_db)):
    """Get detailed system health status"""
    start_time = time.time()

    services = []
    overall_status = "healthy"

    # Check database
    try:
        db_start = time.time()
        await db.execute(text("SELECT 1"))
        db_latency = (time.time() - db_start) * 1000
        services.append(ServiceHealth(
            name="database",
            status="healthy" if db_latency < 100 else "degraded",
            latency_ms=db_latency,
            last_check=datetime.utcnow(),
            error_message=None
        ))
    except Exception as e:
        services.append(ServiceHealth(
            name="database",
            status="unhealthy",
            latency_ms=None,
            last_check=datetime.utcnow(),
            error_message=str(e)
        ))
        overall_status = "unhealthy"

    # Check cache
    cache = get_cache()
    cache_stats = cache.stats()
    cache_status = "healthy" if cache_stats["hit_rate_pct"] > 50 else "degraded"
    services.append(ServiceHealth(
        name="cache",
        status=cache_status,
        latency_ms=1.0,  # Cache is always fast
        last_check=datetime.utcnow(),
        error_message=None
    ))

    # Check WebSocket connections
    ws_count = len(dashboard_manager.active_connections)
    services.append(ServiceHealth(
        name="websocket",
        status="healthy",
        latency_ms=None,
        last_check=datetime.utcnow(),
        error_message=None
    ))

    # Get database connection count
    from app.database.database import engine
    pool_status = engine.pool.status()
    db_connections = pool_status.split("Pool size: ")[1].split(" ")[0] if "Pool size:" in pool_status else 0

    # Calculate uptime (would need to track app start time)
    uptime_seconds = 0  # Placeholder

    # Determine overall status
    unhealthy_count = len([s for s in services if s.status == "unhealthy"])
    degraded_count = len([s for s in services if s.status == "degraded"])

    if unhealthy_count > 0:
        overall_status = "unhealthy"
    elif degraded_count > 0:
        overall_status = "degraded"

    response_time = (time.time() - start_time) * 1000

    return SystemHealthResponse(
        overall_status=overall_status,
        services=services,
        database_connections=int(db_connections),
        active_websockets=ws_count,
        cache_hit_rate=cache_stats["hit_rate_pct"],
        uptime_seconds=uptime_seconds,
        response_time_ms=response_time
    )


# ============== WebSocket Endpoint ==============

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.

    Sends:
    - New trade notifications
    - Phase transitions
    - Trade updates (TP/SL hits)
    - System alerts
    """
    await dashboard_manager.connect(websocket)

    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "event_type": "connected",
            "message": "Dashboard WebSocket connected",
            "timestamp": datetime.utcnow().isoformat()
        })

        # Keep connection alive and handle incoming messages
        while True:
            # Wait for any message from client (ping/pong or commands)
            data = await websocket.receive_text()

            # Handle ping
            if data == "ping":
                await websocket.send_text("pong")

            # Could handle other commands here
            # For example: subscribe to specific symbols, request specific data, etc.

    except WebSocketDisconnect:
        dashboard_manager.disconnect(websocket)
        logger.info("Dashboard client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        dashboard_manager.disconnect(websocket)


# ============== Broadcasting Functions (called from other services) ==============

async def broadcast_new_trade(trade: TradeSetup, phase: str, strategy: Optional[str] = None):
    """Broadcast new trade notification to all dashboard clients"""
    notification = NewTradeNotification(
        trade_id=trade.id,
        trade_identifier=trade.trade_identifier,
        symbol=trade.symbol,
        direction=trade.direction,
        entry_price=float(trade.entry_price),
        phase=phase,
        strategy=strategy,
        confidence_score=float(trade.confidence_score or 0)
    )

    await dashboard_manager.broadcast({
        "event_type": "new_trade",
        "data": notification.model_dump()
    })


async def broadcast_phase_transition(
    symbol: str,
    direction: str,
    webhook_source: str,
    from_phase: str,
    to_phase: str,
    reason: str,
    new_strategy: Optional[str] = None
):
    """Broadcast phase transition notification"""
    notification = PhaseTransitionNotification(
        symbol=symbol,
        direction=direction,
        webhook_source=webhook_source,
        from_phase=from_phase,
        to_phase=to_phase,
        reason=reason,
        new_strategy=new_strategy
    )

    await dashboard_manager.broadcast({
        "event_type": "phase_transition",
        "data": notification.model_dump()
    })


async def broadcast_trade_update(
    trade: TradeSetup,
    update_type: str,
    details: Dict[str, Any]
):
    """Broadcast trade update (TP hit, SL hit, etc.)"""
    notification = TradeUpdateNotification(
        trade_id=trade.id,
        trade_identifier=trade.trade_identifier,
        update_type=update_type,
        current_pnl_pct=float(trade.current_pnl_pct or 0),
        current_pnl_usd=float(trade.current_pnl_usd or 0),
        details=details
    )

    await dashboard_manager.broadcast({
        "event_type": "trade_update",
        "data": notification.model_dump()
    })


async def broadcast_alert(
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    affected_assets: Optional[List[str]] = None
):
    """Broadcast system alert"""
    notification = AlertNotification(
        alert_type=alert_type,
        severity=severity,
        title=title,
        message=message,
        affected_assets=affected_assets,
        action_required=severity == "critical"
    )

    await dashboard_manager.broadcast({
        "event_type": "alert",
        "data": notification.model_dump()
    })


# Export broadcasting functions for use by other services
__all__ = [
    'router',
    'broadcast_new_trade',
    'broadcast_phase_transition',
    'broadcast_trade_update',
    'broadcast_alert'
]