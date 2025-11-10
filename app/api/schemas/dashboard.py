"""
Dashboard API Response Schemas

Pydantic models for structured API responses with validation.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal


# ============== Overview Response Models ==============

class SystemMetrics(BaseModel):
    """Overall system performance metrics"""
    model_config = ConfigDict(from_attributes=True)

    total_trades: int = Field(description="Total number of trades processed")
    active_trades: int = Field(description="Currently active trades")
    total_symbols: int = Field(description="Number of unique symbols traded")

    # Performance metrics
    overall_win_rate: float = Field(description="System-wide win rate percentage")
    overall_rr_ratio: float = Field(description="Average risk-reward ratio")
    total_pnl_usd: float = Field(description="Total profit/loss in USD")
    total_pnl_pct: float = Field(description="Total profit/loss percentage")

    # Volume metrics
    volume_24h: float = Field(description="Trading volume in last 24 hours")
    volume_7d: float = Field(description="Trading volume in last 7 days")
    volume_30d: float = Field(description="Trading volume in last 30 days")

    # Health metrics
    circuit_breakers_active: int = Field(description="Number of active circuit breakers")
    system_health_score: float = Field(description="Overall system health (0-100)")
    last_updated: datetime = Field(description="Last update timestamp")


class DashboardOverviewResponse(BaseModel):
    """Main dashboard overview response"""
    metrics: SystemMetrics
    response_time_ms: float = Field(description="API response time in milliseconds")


# ============== Phase Response Models ==============

class PhaseMetrics(BaseModel):
    """Metrics for a specific phase"""
    model_config = ConfigDict(from_attributes=True)

    phase_name: str = Field(description="Phase name (I, II, or III)")
    trade_count: int = Field(description="Number of trades in this phase")
    active_count: int = Field(description="Number of active trades")

    # Performance
    win_rate: float = Field(description="Win rate percentage")
    avg_pnl_pct: float = Field(description="Average PnL percentage")
    total_pnl_usd: float = Field(description="Total PnL in USD")
    risk_reward_ratio: float = Field(description="Average risk-reward ratio")

    # Timing
    avg_duration_hours: float = Field(description="Average trade duration in hours")
    fastest_tp_minutes: Optional[float] = Field(description="Fastest TP hit time")

    # Asset distribution
    unique_symbols: int = Field(description="Number of unique symbols")
    top_symbol: Optional[str] = Field(description="Most traded symbol")
    top_strategy: Optional[str] = Field(description="Most used strategy")


class SignalBreakdown(BaseModel):
    """Breakdown of signals by phase"""
    model_config = ConfigDict(from_attributes=True)

    webhook_source: str = Field(description="Signal source identifier")
    phase_i_count: int = Field(description="Phase I signal count")
    phase_ii_count: int = Field(description="Phase II signal count")
    phase_iii_count: int = Field(description="Phase III signal count")
    total_count: int = Field(description="Total signal count")
    avg_quality_score: float = Field(description="Average signal quality score")


class DashboardPhasesResponse(BaseModel):
    """Phase breakdown response"""
    phases: List[PhaseMetrics]
    signal_breakdown: List[SignalBreakdown]
    phase_transitions: Dict[str, int] = Field(
        description="Count of transitions between phases",
        example={"i_to_ii": 45, "ii_to_iii": 12}
    )
    response_time_ms: float


# ============== Signal Quality Response Models ==============

class SignalQualityMetrics(BaseModel):
    """Signal quality assessment metrics"""
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    direction: str
    webhook_source: str
    quality_score: float = Field(ge=0, le=100, description="Quality score (0-100)")

    # Performance
    raw_win_rate: float = Field(description="Raw win rate without TP/SL")
    confidence_interval_lower: float = Field(description="95% CI lower bound")
    confidence_interval_upper: float = Field(description="95% CI upper bound")
    expected_value: float = Field(description="Expected value per trade")

    # Statistical validation
    sample_size: int = Field(description="Number of trades analyzed")
    is_significant: bool = Field(description="Statistical significance")
    p_value: float = Field(description="Statistical p-value")
    has_edge: bool = Field(description="Has profitable edge")

    # Recommendation
    recommendation: str = Field(description="Action recommendation")
    last_analyzed: datetime


class SignalDistribution(BaseModel):
    """Signal quality distribution"""
    excellent: int = Field(description="Signals with score > 80")
    good: int = Field(description="Signals with score 60-80")
    fair: int = Field(description="Signals with score 40-60")
    poor: int = Field(description="Signals with score < 40")

    total_signals: int
    avg_quality_score: float
    signals_with_edge: int
    signals_needing_data: int


class DashboardSignalQualityResponse(BaseModel):
    """Signal quality dashboard response"""
    distribution: SignalDistribution
    top_signals: List[SignalQualityMetrics] = Field(description="Top 10 signals by quality")
    recommendations_breakdown: Dict[str, int] = Field(
        description="Count by recommendation type",
        example={"optimize": 15, "collect_more_data": 8, "skip": 3}
    )
    response_time_ms: float


# ============== Strategy Response Models ==============

class StrategyMetrics(BaseModel):
    """Individual strategy performance metrics"""
    model_config = ConfigDict(from_attributes=True)

    strategy_name: str
    symbol: str
    direction: str
    webhook_source: str

    # Performance
    win_rate: float
    win_count: int
    loss_count: int
    avg_win_pct: float
    avg_loss_pct: float
    risk_reward_ratio: float
    total_pnl_usd: float
    strategy_score: float = Field(description="Composite performance score")

    # Trade characteristics
    avg_duration_hours: float
    max_duration_hours: float

    # Parameters
    current_tp1_pct: float
    current_tp2_pct: float
    current_tp3_pct: float
    current_sl_pct: float
    trailing_enabled: bool
    breakeven_trigger_pct: Optional[float]

    # Phase III eligibility
    is_eligible_phase3: bool
    meets_rr_requirement: bool
    meets_duration_requirement: bool
    has_real_sl: bool


class StrategyComparison(BaseModel):
    """Strategy comparison metrics"""
    symbol: str
    direction: str
    webhook_source: str
    strategies: List[Dict[str, Any]] = Field(description="Strategy performance comparison")
    best_strategy: str
    best_strategy_score: float


class DashboardStrategiesResponse(BaseModel):
    """Strategy dashboard response"""
    top_strategies: List[StrategyMetrics] = Field(description="Top strategies by score")
    comparisons: List[StrategyComparison] = Field(description="Strategy comparisons by symbol")

    # Aggregated metrics
    total_strategies: int
    phase3_eligible_count: int
    avg_strategy_score: float
    best_performing_params: Dict[str, Any] = Field(
        description="Most successful parameters across all strategies"
    )
    response_time_ms: float


# ============== Risk Management Response Models ==============

class CircuitBreakerStatus(BaseModel):
    """Circuit breaker status for an asset"""
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    direction: str
    webhook_source: str
    phase: str

    is_active: bool = Field(description="Circuit breaker active")
    trigger_reason: Optional[str] = Field(description="Why it triggered")
    consecutive_losses: int
    drawdown_pct: float
    recovery_time_remaining: Optional[int] = Field(description="Minutes until recovery")

    # Thresholds
    loss_threshold: int = Field(description="Max consecutive losses allowed")
    drawdown_threshold: float = Field(description="Max drawdown percentage allowed")


class DrawdownMetrics(BaseModel):
    """System drawdown tracking"""
    current_drawdown_pct: float
    max_drawdown_pct: float
    max_drawdown_date: datetime
    recovery_days: Optional[int] = Field(description="Days since max drawdown")

    # Per-phase drawdowns
    phase_i_drawdown: float
    phase_ii_drawdown: float
    phase_iii_drawdown: float


class ActiveRiskMetrics(BaseModel):
    """Currently active risk exposure"""
    total_exposure_usd: float = Field(description="Total USD at risk")
    margin_used_usd: float = Field(description="Total margin deployed")
    leverage_weighted_avg: float = Field(description="Weighted average leverage")

    positions_at_risk: int = Field(description="Positions near stop loss")
    positions_in_profit: int = Field(description="Positions in profit")

    # Risk concentration
    max_symbol_exposure_pct: float = Field(description="Largest single symbol exposure")
    max_symbol: str = Field(description="Symbol with largest exposure")


class DashboardRiskResponse(BaseModel):
    """Risk management dashboard response"""
    circuit_breakers: List[CircuitBreakerStatus]
    drawdown_metrics: DrawdownMetrics
    active_risk: ActiveRiskMetrics

    # Risk alerts
    active_alerts: List[Dict[str, Any]] = Field(description="Current risk alerts")
    risk_score: float = Field(description="Overall risk score (0-100, lower is better)")
    response_time_ms: float


# ============== WebSocket Message Models ==============

class WebSocketMessage(BaseModel):
    """Base WebSocket message"""
    event_type: str = Field(description="Type of event")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any]


class NewTradeNotification(BaseModel):
    """New trade opened notification"""
    trade_id: int
    trade_identifier: str
    symbol: str
    direction: str
    entry_price: float
    phase: str
    strategy: Optional[str]
    confidence_score: float


class PhaseTransitionNotification(BaseModel):
    """Phase transition notification"""
    symbol: str
    direction: str
    webhook_source: str
    from_phase: str
    to_phase: str
    reason: str
    new_strategy: Optional[str]


class TradeUpdateNotification(BaseModel):
    """Trade update notification (TP hit, SL hit, etc.)"""
    trade_id: int
    trade_identifier: str
    update_type: str = Field(description="tp_hit, sl_hit, trailing_activated, etc.")
    current_pnl_pct: float
    current_pnl_usd: float
    details: Dict[str, Any]


class AlertNotification(BaseModel):
    """System alert notification"""
    alert_type: str = Field(description="circuit_breaker, drawdown, system_health, etc.")
    severity: str = Field(description="info, warning, critical")
    title: str
    message: str
    affected_assets: Optional[List[str]]
    action_required: bool


# ============== Health Check Models ==============

class ServiceHealth(BaseModel):
    """Individual service health status"""
    name: str
    status: str = Field(description="healthy, degraded, unhealthy")
    latency_ms: Optional[float]
    last_check: datetime
    error_message: Optional[str]


class SystemHealthResponse(BaseModel):
    """System health check response"""
    overall_status: str = Field(description="healthy, degraded, unhealthy")
    services: List[ServiceHealth]
    database_connections: int
    active_websockets: int
    cache_hit_rate: float
    uptime_seconds: int
    response_time_ms: float