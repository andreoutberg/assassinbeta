"""
Database Models for Andre Assassin

Statistical trade tracking system with per-asset learning.
TP levels are LEARNED from historical data, not hardcoded.
"""
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from decimal import Decimal
from typing import Optional

Base = declarative_base()


class PriceAction(Base):
    """
    Raw price action data from TradingView webhooks

    Stores OHLCV candles and technical indicators.
    This is the ingestion layer.
    """
    __tablename__ = "price_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    exchange = Column(String(50), nullable=True)
    timeframe = Column(String(10), nullable=False)  # e.g., "15m", "1h", "4h"

    # OHLCV data
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(Numeric(20, 8), nullable=False)
    high = Column(Numeric(20, 8), nullable=False)
    low = Column(Numeric(20, 8), nullable=False)
    close = Column(Numeric(20, 8), nullable=False)
    volume = Column(Numeric(20, 8), nullable=True)

    # Technical indicators (flexible JSONB storage)
    indicators = Column(JSON, nullable=True)
    # Example: {"rsi": 65.5, "macd": 0.45, "bb_upper": 43500, "ema_50": 42000}

    # AI analysis results (stored after background analysis)
    ai_analysis = Column(JSON, nullable=True)
    # Example: {"trend": "uptrend", "confidence": 0.85, "setup_type": "breakout"}

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    webhook_received_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<PriceAction {self.symbol} {self.timeframe} @ {self.timestamp}>"


class TradeSetup(Base):
    """
    Individual trade setups tracked after AI identifies opportunity

    This tracks the ENTIRE JOURNEY of a trade from entry to completion.
    Records what actually happens (TP hits, drawdowns, timing).
    """
    __tablename__ = "trade_setups"
    __table_args__ = (
        # Composite indexes for common query patterns (performance optimization)
        Index('idx_symbol_status_source', 'symbol', 'status', 'webhook_source'),
        Index('idx_status_timestamp', 'status', 'entry_timestamp'),
        Index('idx_symbol_direction_source', 'symbol', 'direction', 'webhook_source'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_identifier = Column(String(50), unique=True, nullable=True, index=True)  # e.g., "#AIALONG_A_001"
    symbol = Column(String(20), nullable=False, index=True)  # Original TradingView symbol (e.g., "HIPPOUSDT.P")
    ccxt_symbol = Column(String(20), nullable=True)  # CCXT format for exchanges (e.g., "HIPPO/USDT")
    exchange = Column(String(50), nullable=True)
    timeframe = Column(String(10), nullable=False)
    direction = Column(String(10), nullable=False)  # LONG or SHORT

    # Entry details
    entry_price = Column(Numeric(20, 8), nullable=False)
    entry_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    setup_type = Column(String(20), nullable=True)  # breakout, reversal, continuation
    confidence_score = Column(Numeric(5, 4), nullable=True)  # 0.0 to 1.0
    webhook_source = Column(String(50), nullable=True)  # Strategy identifier (e.g., "scalping_v2")

    # Risk Management (V2 Architecture - Signal-Based Trading)
    trade_mode = Column(String(10), default='live', nullable=True)  # 'live' or 'paper'
    position_size_usd = Column(Numeric(20, 2), nullable=True)  # DEPRECATED: Use notional_position_usd
    notional_position_usd = Column(Numeric(20, 2), nullable=True)  # Full position with leverage (e.g., $16,665)
    margin_required_usd = Column(Numeric(20, 2), nullable=True)  # Actual capital required (e.g., $3,333)
    leverage = Column(Numeric(10, 2), nullable=True)  # Leverage multiplier (e.g., 5.0)
    risk_reward_ratio = Column(Numeric(10, 4), nullable=True)  # TP1 / SL distance ratio

    # News sentiment at entry (for correlation analysis)
    news_sentiment_score = Column(Numeric(5, 4), nullable=True)  # -1.0 (bearish) to +1.0 (bullish)
    news_count_1h = Column(Integer, nullable=True)  # Number of news articles in past 1h
    major_news = Column(Boolean, default=False)  # Was there major news at entry?

    # Market cap tracking (for correlation analysis)
    market_cap_usd = Column(Numeric(20, 2), nullable=True)  # Market cap in USD at entry
    market_cap_rank = Column(Integer, nullable=True)  # CoinGecko/CMC rank (1=BTC, 2=ETH, etc.)

    # PLANNED LEVELS (from AI or manual input)
    # These are the INITIAL suggestions, may not be optimal yet
    planned_tp1_price = Column(Numeric(20, 8), nullable=True)
    planned_tp1_pct = Column(Numeric(10, 4), nullable=True)
    planned_tp2_price = Column(Numeric(20, 8), nullable=True)
    planned_tp2_pct = Column(Numeric(10, 4), nullable=True)
    planned_tp3_price = Column(Numeric(20, 8), nullable=True)
    planned_tp3_pct = Column(Numeric(10, 4), nullable=True)
    planned_sl_price = Column(Numeric(20, 8), nullable=True)
    planned_sl_pct = Column(Numeric(10, 4), nullable=True)

    # Trailing stop configuration (for A/B testing)
    use_trailing_stop = Column(Boolean, default=False)
    trailing_stop_distance_pct = Column(Numeric(10, 4), nullable=True)  # e.g., 1.0% below high
    trailing_stop_activation_pct = Column(Numeric(10, 4), nullable=True)  # Activate after +2% profit
    trailing_stop_triggered = Column(Boolean, default=False)
    trailing_stop_high_water = Column(Numeric(20, 8), nullable=True)  # Highest price reached

    # PARALLEL STRATEGY TESTING FRAMEWORK (3-Strategy Deep Analysis)
    # Risk strategy identifier
    risk_strategy = Column(String(20), default='static')  # 'static', 'adaptive_trailing', 'early_momentum'
    is_parallel_test = Column(Boolean, default=False)  # Is this part of parallel testing?
    test_group_id = Column(String(100), nullable=True)  # Groups trades from same signal (e.g., "BTC_20251105_123456")

    # Strategy B: Adaptive Momentum Lock (Enhanced Trailing)
    trailing_stop_pct = Column(Numeric(5, 2), nullable=True)  # Current trailing stop % (adaptive)
    trailing_stop_updates = Column(Integer, default=0)  # Number of times trail was updated
    volatility_multiplier = Column(Numeric(5, 2), nullable=True)  # ATR-based multiplier (1.0-3.0)
    momentum_state = Column(String(20), nullable=True)  # 'pre_tp1', 'tp1_tp2', 'post_tp2'

    # Strategy C: Early Momentum Filter (Quality Signal Detection)
    early_momentum_detected = Column(Boolean, nullable=True)  # Did trade show early favorable movement?
    early_momentum_time = Column(Numeric(10, 2), nullable=True)  # Minutes to reach early profit threshold
    early_momentum_pnl = Column(Numeric(10, 4), nullable=True)  # PnL % when early momentum detected
    low_quality_signal = Column(Boolean, default=False)  # Did trade fail early momentum test?
    early_profit_time_threshold = Column(Numeric(5, 2), nullable=True)  # Time threshold (minutes) for early profit
    early_profit_pct_threshold = Column(Numeric(5, 2), nullable=True)  # PnL threshold (%) for early profit

    # Shared tracking fields (all strategies)
    max_favorable_excursion = Column(Numeric(20, 8), nullable=True)  # Best price reached (absolute)
    sl_moved_to_be = Column(Boolean, default=False)  # Was SL moved to breakeven?
    sl_move_timestamp = Column(DateTime(timezone=True), nullable=True)  # When was SL moved to BE?

    # WHAT ACTUALLY HAPPENED (ground truth data)
    # TP1 tracking
    tp1_hit = Column(Boolean, default=False)
    tp1_hit_at = Column(DateTime(timezone=True), nullable=True)
    tp1_hit_price = Column(Numeric(20, 8), nullable=True)
    tp1_time_minutes = Column(Integer, nullable=True)  # Time from entry to TP1
    tp1_mae_pct = Column(Numeric(10, 4), nullable=True)  # Max Adverse Excursion before hitting TP1

    # TP2 tracking
    tp2_hit = Column(Boolean, default=False)
    tp2_hit_at = Column(DateTime(timezone=True), nullable=True)
    tp2_hit_price = Column(Numeric(20, 8), nullable=True)
    tp2_time_minutes = Column(Integer, nullable=True)
    tp2_mae_pct = Column(Numeric(10, 4), nullable=True)

    # TP3 tracking
    tp3_hit = Column(Boolean, default=False)
    tp3_hit_at = Column(DateTime(timezone=True), nullable=True)
    tp3_hit_price = Column(Numeric(20, 8), nullable=True)
    tp3_time_minutes = Column(Integer, nullable=True)
    tp3_mae_pct = Column(Numeric(10, 4), nullable=True)

    # Stop Loss tracking
    sl_hit = Column(Boolean, default=False)
    sl_hit_at = Column(DateTime(timezone=True), nullable=True)
    sl_hit_price = Column(Numeric(20, 8), nullable=True)
    sl_time_minutes = Column(Integer, nullable=True)
    sl_type_hit = Column(String(20), nullable=True)  # 'static' or 'trailing'

    # Overall metrics
    max_drawdown_pct = Column(Numeric(10, 4), nullable=True)  # Worst loss during trade
    max_profit_pct = Column(Numeric(10, 4), nullable=True)    # Best profit during trade
    final_outcome = Column(String(20), nullable=True)  # tp1, tp2, tp3, sl, timeout
    final_pnl_pct = Column(Numeric(10, 4), nullable=True)

    # Trade status
    status = Column(String(20), default='active', index=True)  # active, completed, cancelled
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # AI Analysis (Phase 1: Data Collection - Non-blocking)
    # Pre-Entry AI Evaluation
    ai_quality_score = Column(Numeric(3, 1), nullable=True)  # 0.0 to 10.0 quality rating
    ai_confidence = Column(Numeric(3, 2), nullable=True)  # 0.00 to 1.00 confidence
    ai_setup_type = Column(String(50), nullable=True)  # "breakout", "reversal", "continuation", etc.
    ai_red_flags = Column(JSON, nullable=True)  # List of red flags identified
    ai_green_lights = Column(JSON, nullable=True)  # List of positive factors
    ai_reasoning = Column(Text, nullable=True)  # AI's explanation of score
    ai_recommended_action = Column(String(30), nullable=True)  # "take", "skip", "wait_for_confirmation"

    # Post-Trade AI Analysis
    ai_post_analysis = Column(Text, nullable=True)  # Detailed analysis of why trade won/lost
    ai_pattern = Column(String(50), nullable=True)  # Pattern identified: "strong_breakout", "fakeout", etc.
    ai_market_regime = Column(String(30), nullable=True)  # "trending", "ranging", "volatile", "low_volume"
    ai_lessons = Column(JSON, nullable=True)  # List of lessons learned
    ai_assessment_accuracy = Column(String(30), nullable=True)  # "correct", "incorrect", "partially_correct"

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    notes = Column(Text, nullable=True)
    
    # Relationships
    milestones = relationship("TradeMilestones", back_populates="trade_setup", uselist=False)

    def __repr__(self):
        return f"<TradeSetup {self.symbol} {self.direction} @ {self.entry_price} [{self.status}]>"


class TradePriceSample(Base):
    """
    Price samples taken every 5 minutes during active trade

    Used to calculate exact MAE, MFE, and track price journey.
    Allows us to answer: "What percentage of BTCUSDT trades reached 1.5%?"
    """
    __tablename__ = "trade_price_samples"
    __table_args__ = (
        # Composite index for efficient latest price sample queries (fixes N+1 query pattern)
        Index('idx_trade_timestamp', 'trade_setup_id', 'timestamp'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_setup_id = Column(Integer, nullable=False, index=True)

    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    price = Column(Numeric(20, 8), nullable=False)
    pnl_pct = Column(Numeric(10, 4), nullable=False)  # % from entry

    # High-water marks at this sample
    max_profit_so_far = Column(Numeric(10, 4), nullable=True)
    max_drawdown_so_far = Column(Numeric(10, 4), nullable=True)

    def __repr__(self):
        return f"<PriceSample trade={self.trade_setup_id} pnl={self.pnl_pct}%>"


class TradeMilestones(Base):
    """
    Event-based milestone tracking for accurate strategy simulation
    
    Records timestamps when price crosses specific thresholds during trade lifetime.
    This enables chronological replay to determine which TP/SL hit first.
    
    Storage efficiency: Only 16 nullable timestamp columns vs thousands of price samples.
    """
    __tablename__ = "trade_milestones"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_setup_id = Column(Integer, ForeignKey('trade_setups.id', ondelete='CASCADE'), nullable=False, index=True, unique=True)
    
    # Entry tracking
    entry_price = Column(Numeric(20, 8), nullable=False)
    entry_at = Column(DateTime(timezone=True), nullable=False)

    # Profit milestone timestamps (when threshold was first crossed)
    reached_plus_0_5pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_plus_1pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_plus_1_5pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_plus_2pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_plus_3pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_plus_5pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_plus_8pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_plus_10pct_at = Column(DateTime(timezone=True), nullable=True)

    # Drawdown milestone timestamps (when threshold was first crossed)
    reached_minus_0_5pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_minus_1pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_minus_1_5pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_minus_2pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_minus_3pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_minus_5pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_minus_8pct_at = Column(DateTime(timezone=True), nullable=True)
    reached_minus_10pct_at = Column(DateTime(timezone=True), nullable=True)

    # High-water marks (for trailing stop simulation)
    max_profit_pct = Column(Numeric(10, 4), nullable=True)
    max_profit_at = Column(DateTime(timezone=True), nullable=True)
    max_drawdown_pct = Column(Numeric(10, 4), nullable=True)
    max_drawdown_at = Column(DateTime(timezone=True), nullable=True)

    # Exit tracking
    exit_price = Column(Numeric(20, 8), nullable=True)
    exit_at = Column(DateTime(timezone=True), nullable=True)
    final_pnl_pct = Column(Numeric(10, 4), nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    trade_setup = relationship("TradeSetup", back_populates="milestones")
    
    def __repr__(self):
        return f"&lt;TradeMilestones trade={self.trade_setup_id} milestones_reached={self._count_milestones()}>"
    
    def _count_milestones(self):
        """Count how many milestones have been reached"""
        count = 0
        for field in [
            'reached_plus_0_5pct_at', 'reached_plus_1pct_at', 'reached_plus_1_5pct_at',
            'reached_plus_2pct_at', 'reached_plus_3pct_at', 'reached_plus_5pct_at',
            'reached_plus_8pct_at', 'reached_plus_10pct_at',
            'reached_minus_0_5pct_at', 'reached_minus_1pct_at', 'reached_minus_1_5pct_at',
            'reached_minus_2pct_at', 'reached_minus_3pct_at', 'reached_minus_5pct_at',
            'reached_minus_8pct_at', 'reached_minus_10pct_at'
        ]:
            if getattr(self, field, None):
                count += 1
        return count
    
    def get_chronological_events(self):
        """
        Return all milestone events in chronological order
        
        Returns list of tuples: (timestamp, event_type, pnl_pct)
        Used for simulation replay
        """
        events = []
        
        # Profit milestones
        milestones_map = [
            ('reached_plus_0_5pct_at', 'profit', 0.5),
            ('reached_plus_1pct_at', 'profit', 1.0),
            ('reached_plus_1_5pct_at', 'profit', 1.5),
            ('reached_plus_2pct_at', 'profit', 2.0),
            ('reached_plus_3pct_at', 'profit', 3.0),
            ('reached_plus_5pct_at', 'profit', 5.0),
            ('reached_plus_8pct_at', 'profit', 8.0),
            ('reached_plus_10pct_at', 'profit', 10.0),
            ('reached_minus_0_5pct_at', 'drawdown', -0.5),
            ('reached_minus_1pct_at', 'drawdown', -1.0),
            ('reached_minus_1_5pct_at', 'drawdown', -1.5),
            ('reached_minus_2pct_at', 'drawdown', -2.0),
            ('reached_minus_3pct_at', 'drawdown', -3.0),
            ('reached_minus_5pct_at', 'drawdown', -5.0),
            ('reached_minus_8pct_at', 'drawdown', -8.0),
            ('reached_minus_10pct_at', 'drawdown', -10.0),
        ]
        
        for field_name, event_type, pnl_pct in milestones_map:
            timestamp = getattr(self, field_name, None)
            if timestamp:
                events.append((timestamp, event_type, pnl_pct))
        
        # Sort by timestamp - CHRONOLOGICAL ORDER!
        events.sort(key=lambda x: x[0])
        
        return events


class AssetStatistics(Base):
    """
    Per-asset statistical model - THE BRAIN

    This is where we LEARN optimal TP/SL levels based on historical data.
    Updated after each completed trade.

    Example: "For BTCUSDT, 92% of trades hit 1.25% (use as TP1),
              68% hit 2.5% (use as TP2), 41% hit 4.0% (use as TP3)"
    """
    __tablename__ = "asset_statistics"

    symbol = Column(String(20), primary_key=True)
    exchange = Column(String(50), nullable=True)

    # Sample size
    total_setups = Column(Integer, default=0)
    completed_setups = Column(Integer, default=0)
    active_setups = Column(Integer, default=0)
    
    # Direction-specific counters (for baseline data collection)
    completed_longs = Column(Integer, default=0)  # Number of completed LONG trades
    completed_shorts = Column(Integer, default=0)  # Number of completed SHORT trades

    # TP HIT RATES (the key learning metric)
    tp1_hit_rate = Column(Numeric(5, 4), nullable=True)  # 0.0 to 1.0 (e.g., 0.92 = 92%)
    tp2_hit_rate = Column(Numeric(5, 4), nullable=True)
    tp3_hit_rate = Column(Numeric(5, 4), nullable=True)

    # TIME TO TARGET (median minutes)
    tp1_median_minutes = Column(Integer, nullable=True)
    tp2_median_minutes = Column(Integer, nullable=True)
    tp3_median_minutes = Column(Integer, nullable=True)

    # DRAWDOWN STATISTICS (risk management)
    avg_max_drawdown_pct = Column(Numeric(10, 4), nullable=True)
    p50_max_drawdown_pct = Column(Numeric(10, 4), nullable=True)  # Median
    p75_max_drawdown_pct = Column(Numeric(10, 4), nullable=True)  # 75th percentile
    p90_max_drawdown_pct = Column(Numeric(10, 4), nullable=True)  # 90th percentile
    p95_max_drawdown_pct = Column(Numeric(10, 4), nullable=True)  # 95th percentile (worst case)

    # PROFIT EXCURSION STATISTICS
    avg_max_profit_pct = Column(Numeric(10, 4), nullable=True)
    p50_max_profit_pct = Column(Numeric(10, 4), nullable=True)
    p75_max_profit_pct = Column(Numeric(10, 4), nullable=True)
    p90_max_profit_pct = Column(Numeric(10, 4), nullable=True)

    # LEARNED OPTIMAL LEVELS (calculated from hit rates)
    # These are NOT hardcoded - they are DERIVED from historical data
    # Target: TP1 should hit 80-90% of the time
    optimal_tp1_pct = Column(Numeric(10, 4), nullable=True)
    optimal_tp1_confidence = Column(Numeric(5, 4), nullable=True)

    # Target: TP2 should hit 50-60% of the time
    optimal_tp2_pct = Column(Numeric(10, 4), nullable=True)
    optimal_tp2_confidence = Column(Numeric(5, 4), nullable=True)

    # Target: TP3 should hit 30-40% of the time
    optimal_tp3_pct = Column(Numeric(10, 4), nullable=True)
    optimal_tp3_confidence = Column(Numeric(5, 4), nullable=True)

    # Optimal SL (learned from testing p90/p95/p99 with different buffers)
    optimal_sl_pct = Column(Numeric(10, 4), nullable=True)
    optimal_sl_confidence = Column(Numeric(5, 4), nullable=True)

    # PROFITABILITY METRICS (The Most Important!)
    expected_value_pct = Column(Numeric(10, 4), nullable=True)  # EV = (win_rate * avg_win) - (loss_rate * avg_loss)
    is_profitable_setup = Column(Boolean, default=False)  # Is EV > 0? (worth trading!)
    avg_risk_reward_ratio = Column(Numeric(10, 4), nullable=True)  # TP1 / SL ratio
    win_rate = Column(Numeric(5, 4), nullable=True)  # % of trades hitting any TP

    # TRAILING STOP ANALYSIS (A/B testing static vs trailing)
    trailing_stop_win_rate = Column(Numeric(5, 4), nullable=True)  # Win rate with trailing stops
    static_stop_win_rate = Column(Numeric(5, 4), nullable=True)  # Win rate with static stops
    optimal_trailing_distance_pct = Column(Numeric(10, 4), nullable=True)  # Learned optimal distance
    optimal_trailing_activation_pct = Column(Numeric(10, 4), nullable=True)  # When to activate trailing
    trailing_stop_recommended = Column(Boolean, default=False)  # Should we use trailing for this asset?

    # NEWS SENTIMENT CORRELATION
    avg_sentiment_winners = Column(Numeric(5, 4), nullable=True)  # Avg sentiment of winning trades
    avg_sentiment_losers = Column(Numeric(5, 4), nullable=True)  # Avg sentiment of losing trades
    sentiment_matters = Column(Boolean, default=False)  # Is sentiment statistically significant?

    # MARKET CAP CORRELATION
    # Question: Do small caps (< $100M) perform different than large caps (> $1B)?
    avg_market_cap_winners = Column(Numeric(20, 2), nullable=True)  # Avg market cap of winning trades
    avg_market_cap_losers = Column(Numeric(20, 2), nullable=True)  # Avg market cap of losing trades
    market_cap_correlation_score = Column(Numeric(5, 4), nullable=True)  # -1 to +1

    # PERCENTILE HIT ANALYSIS (JSON for flexibility)
    # Example: {"0.5": 0.98, "0.75": 0.95, "1.0": 0.92, "1.25": 0.88, ...}
    # Means: 98% hit 0.5%, 95% hit 0.75%, 92% hit 1.0%, etc.
    percentile_hit_data = Column(JSON, nullable=True)

    # CIRCUIT BREAKER (V2 Architecture - Signal-Based Trading)
    # Cumulative R/R tracking for live vs paper trading decisions
    cumulative_wins_usd = Column(Numeric(20, 2), default=Decimal("0"))  # Total $ wins (sum of all winning trades)
    cumulative_losses_usd = Column(Numeric(20, 2), default=Decimal("0"))  # Total $ losses (sum of all losing trades)
    cumulative_rr = Column(Numeric(10, 4), default=Decimal("0"))  # wins / losses ratio (>= 1.0 = profitable)
    is_live_trading = Column(Boolean, default=True)  # True = live trades, False = paper trades only
    paper_trade_count = Column(Integer, default=0)  # Number of paper trades since going below R/R 1.0
    last_rr_check = Column(DateTime(timezone=True), nullable=True)  # Last time R/R was updated

    # Metadata
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_calculation_at = Column(DateTime(timezone=True), nullable=True)
    calculation_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<AssetStats {self.symbol} (n={self.completed_setups})>"


class AIAnalysisLog(Base):
    """
    Log of all AI analysis calls for monitoring and cost tracking
    """
    __tablename__ = "ai_analysis_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    price_action_id = Column(Integer, nullable=True, index=True)
    trade_setup_id = Column(Integer, nullable=True, index=True)

    symbol = Column(String(20), nullable=False)
    model = Column(String(50), nullable=False)  # e.g., "claude-haiku-4-20250514"

    # Request details
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    # Response details
    analysis_result = Column(JSON, nullable=True)
    confidence_score = Column(Numeric(5, 4), nullable=True)

    # Performance
    latency_ms = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self):
        return f"<AILog {self.model} {self.symbol} @ {self.created_at}>"


class StrategySimulationResult(Base):
    """
    Simulated performance of different exit strategies on the same trade
    
    Instead of tracking 3 parallel trades, we track 1 trade and simulate
    how each strategy (Static, Adaptive Trailing, Early Momentum) would have
    performed given the actual price journey.
    
    This gives us:
    - Perfect A/B/C comparison (identical market conditions)
    - 3x less database load (1 trade instead of 3)
    - Ability to backtest new strategies on historical data
    """
    __tablename__ = "strategy_simulation_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_setup_id = Column(Integer, nullable=False, index=True)
    test_group_id = Column(String(100), nullable=True, index=True)
    
    # Strategy identification
    strategy_name = Column(String(20), nullable=False)  # 'static', 'adaptive_trailing', 'early_momentum'
    
    # Simulated outcome
    simulated_exit_price = Column(Numeric(20, 8), nullable=True)
    simulated_pnl_pct = Column(Numeric(10, 4), nullable=True)
    simulated_outcome = Column(String(20), nullable=True)  # 'tp1', 'tp2', 'tp3', 'sl', 'be', 'timeout'
    simulated_exit_timestamp = Column(DateTime(timezone=True), nullable=True)
    
    # TP hits (what levels were reached before exit?)
    tp1_hit = Column(Boolean, default=False)
    tp2_hit = Column(Boolean, default=False)
    tp3_hit = Column(Boolean, default=False)
    sl_hit = Column(Boolean, default=False)
    
    # Strategy-specific metrics
    # For Adaptive Trailing
    trailing_updates = Column(Integer, default=0)
    max_trail_distance_pct = Column(Numeric(10, 4), nullable=True)
    final_trail_distance_pct = Column(Numeric(10, 4), nullable=True)
    volatility_multiplier = Column(Numeric(5, 2), nullable=True)
    momentum_state = Column(String(20), nullable=True)  # 'pre_tp1', 'tp1_to_tp2', 'post_tp2'
    
    # For Early Momentum
    early_momentum_detected = Column(Boolean, default=False)
    early_momentum_time_minutes = Column(Numeric(10, 2), nullable=True)
    early_momentum_pnl = Column(Numeric(10, 4), nullable=True)
    moved_to_be = Column(Boolean, default=False)
    
    # Performance metrics (same as actual trade)
    max_favorable_excursion = Column(Numeric(10, 4), nullable=True)
    max_adverse_excursion = Column(Numeric(10, 4), nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<SimResult {self.strategy_name} trade={self.trade_setup_id} pnl={self.simulated_pnl_pct}%>"
