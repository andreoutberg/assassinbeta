from typing import TypedDict, Optional

class StrategyConfig(TypedDict):
    strategy_name: str
    tp1_pct: float
    tp2_pct: Optional[float]
    tp3_pct: Optional[float]
    sl_pct: float
    trailing_enabled: bool
    trailing_activation: Optional[float]
    trailing_distance: Optional[float]
    breakeven_trigger_pct: Optional[float]

class StrategyParams(TypedDict):
    """Internal strategy parameters used during grid search"""
    strategy_name: str
    tp1_pct: float
    tp2_pct: Optional[float]
    tp3_pct: Optional[float]
    sl_pct: float
    trailing_enabled: bool
    trailing_activation: Optional[float]
    trailing_distance: Optional[float]
    breakeven_trigger_pct: Optional[float]

class StrategyCurrentParams(TypedDict):
    """Current parameters for a strategy"""
    tp1: Optional[float]
    tp2: Optional[float]
    tp3: Optional[float]
    sl: Optional[float]
    trailing: bool

class StrategyPerformanceData(TypedDict):
    """Complete performance data for a strategy"""
    strategy_name: str
    risk_reward: float
    win_rate: float
    win_count: int
    loss_count: int
    avg_win: float
    avg_loss: float
    avg_duration_hours: float
    max_duration_hours: float
    total_pnl: float
    strategy_score: float
    is_eligible_phase3: bool
    meets_rr: bool
    has_real_sl: bool
    meets_duration: bool
    trades_analyzed: int
    current_params: StrategyCurrentParams

class SimulationResult(TypedDict):
    exit_price: float
    exit_reason: str
    pnl_pct: float
    pnl_usd: float
    duration_minutes: int

class GridSearchResult(TypedDict):
    """Result from grid search optimization containing strategy parameters and metrics"""
    strategy_params: StrategyParams
    risk_reward: float
    win_rate: float
    composite_score: float
    avg_win: float
    avg_loss: float
    avg_duration_hours: float
    trades_tested: int
    win_count: int
    loss_count: int

class TradePhaseInfo(TypedDict, total=False):
    """Information about the current trading phase for a symbol/direction"""
    phase: str
    phase_name: str
    baseline_completed: int
    baseline_needed: int
    best_strategy: Optional[StrategyConfig]
    description: str
