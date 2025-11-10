"""
Strategy Simulation and Performance Models

Tracks Phase II strategy testing and Phase III live trading performance.
"""
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database.models import Base


class StrategySimulation(Base):
    """
    Records simulated outcome for each strategy against a paper trade

    Phase II: All 4 strategies simulate against each trade
    Phase III: Other 3 strategies continue simulating while 1 is live
    """
    __tablename__ = "strategy_simulations"

    id = Column(Integer, primary_key=True)
    trade_setup_id = Column(Integer, ForeignKey('trade_setups.id', ondelete='CASCADE'), nullable=False, index=True)
    strategy_name = Column(String(50), nullable=False, index=True)

    # Strategy parameters used for this simulation
    simulated_tp1_pct = Column(Numeric(10, 4))
    simulated_tp2_pct = Column(Numeric(10, 4))
    simulated_tp3_pct = Column(Numeric(10, 4))
    simulated_sl_pct = Column(Numeric(10, 4))
    trailing_enabled = Column(Boolean, default=False)
    trailing_activation_pct = Column(Numeric(10, 4))
    trailing_distance_pct = Column(Numeric(10, 4))
    breakeven_trigger_pct = Column(Numeric(10, 4), nullable=True)  # Move SL to BE after this % profit

    # Simulated results
    simulated_exit_price = Column(Numeric(20, 8))
    simulated_exit_reason = Column(String(50))  # 'tp1', 'tp2', 'tp3', 'sl', 'time_exit', 'trailing_sl', 'breakeven'
    simulated_pnl_pct = Column(Numeric(10, 4))
    simulated_pnl_usd = Column(Numeric(10, 2))
    simulated_duration_minutes = Column(Integer)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<StrategySimulation {self.strategy_name} trade={self.trade_setup_id} pnl={self.simulated_pnl_pct}%>"


class StrategyPerformance(Base):
    """
    Aggregated performance metrics per strategy per symbol/direction/webhook

    Updated after each trade completes to reflect rolling window performance
    Used for Phase III eligibility checks and best strategy selection
    """
    __tablename__ = "strategy_performance"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    direction = Column(String(10), nullable=False, index=True)
    webhook_source = Column(String(100), nullable=False, index=True)
    strategy_name = Column(String(50), nullable=False, index=True)

    # Performance metrics (rolling window - last 10 trades)
    win_rate = Column(Numeric(5, 2))  # Percentage
    win_count = Column(Integer)
    loss_count = Column(Integer)
    avg_win = Column(Numeric(10, 4))  # Average winning trade %
    avg_loss = Column(Numeric(10, 4))  # Average losing trade % (negative)
    risk_reward = Column(Numeric(10, 4))  # avg_win / abs(avg_loss)
    avg_duration_hours = Column(Numeric(10, 2))
    max_duration_hours = Column(Numeric(10, 2))
    total_simulated_pnl = Column(Numeric(10, 2))  # Sum of last 10 trades
    strategy_score = Column(Numeric(10, 4))  # Composite score for ranking

    # Phase III eligibility flags
    meets_rr_requirement = Column(Boolean, default=False)  # RR >= 1.0
    has_real_sl = Column(Boolean, default=False)  # SL < 999999
    meets_duration_requirement = Column(Boolean, default=False)  # Max duration <= 24h
    is_eligible_for_phase3 = Column(Boolean, default=False, index=True)  # All 3 requirements met

    # Current strategy parameters (adaptive - change as data grows)
    current_tp1_pct = Column(Numeric(10, 4))
    current_tp2_pct = Column(Numeric(10, 4))
    current_tp3_pct = Column(Numeric(10, 4))
    current_sl_pct = Column(Numeric(10, 4))
    current_trailing_enabled = Column(Boolean, default=False)
    current_trailing_activation = Column(Numeric(10, 4))
    current_trailing_distance = Column(Numeric(10, 4))
    current_breakeven_trigger_pct = Column(Numeric(10, 4), nullable=True)  # Move SL to BE after this % profit

    # Walk-forward validation metrics (prevents overfit)
    in_sample_win_rate = Column(Numeric(5, 2))  # Grid search results (may be inflated)
    in_sample_risk_reward = Column(Numeric(10, 4))
    in_sample_cumulative_pnl = Column(Numeric(10, 2))
    out_of_sample_win_rate = Column(Numeric(5, 2))  # Test set results (realistic)
    out_of_sample_risk_reward = Column(Numeric(10, 4))
    out_of_sample_cumulative_pnl = Column(Numeric(10, 2))
    overfit_bias = Column(Numeric(5, 2))  # in_sample - out_sample WR
    validation_confidence = Column(Numeric(3, 2))  # 0.0 to 1.0
    validation_recommendation = Column(String(50))  # APPROVED, CONDITIONAL, REJECTED
    validation_performed_at = Column(DateTime(timezone=True))
    validation_n_splits = Column(Integer)
    validation_status = Column(String(20), default='pending')
    
    # Metadata
    trades_analyzed = Column(Integer, default=0)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<StrategyPerformance {self.strategy_name} {self.symbol} {self.direction} RR={self.risk_reward}>"


class GridSearchResult(Base):
    """
    Historical grid search results for auditing and tracking optimization
    
    Stores grid search results each time strategies are generated/regenerated
    """
    __tablename__ = "grid_search_results"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    direction = Column(String(10), nullable=False)
    webhook_source = Column(String(100), nullable=False)

    # Grid search metadata
    baseline_trades_used = Column(Integer, nullable=False)
    combinations_tested = Column(Integer, nullable=False)
    search_duration_ms = Column(Integer, nullable=True)

    # Top 10 results (stored as JSON)
    top_results = Column(JSON, nullable=False)
    
    # Walk-forward validation results (stored as JSON)
    validation_results = Column(JSON, nullable=True)

    # Winning strategy (top ranked)
    selected_strategy_rank = Column(Integer, default=1)
    selected_tp_pct = Column(Numeric(10, 4), nullable=True)
    selected_sl_pct = Column(Numeric(10, 4), nullable=True)
    selected_trailing_enabled = Column(Boolean, default=False)
    selected_trailing_activation = Column(Numeric(10, 4), nullable=True)
    selected_trailing_distance = Column(Numeric(10, 4), nullable=True)
    selected_risk_reward = Column(Numeric(10, 4), nullable=True)
    selected_win_rate = Column(Numeric(5, 2), nullable=True)
    selected_composite_score = Column(Numeric(10, 4), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<GridSearchResult {self.symbol} {self.direction} RR={self.selected_risk_reward}>"
