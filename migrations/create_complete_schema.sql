-- ================================================================================
-- High-WR Trading System Complete Database Schema
-- Version: 2.0.0
-- Date: 2025-11-10
-- Description: Complete PostgreSQL schema for high-WR trading system with
--              demo positions, signals, strategies, optimizations, and analytics
-- ================================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "btree_gist";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ================================================================================
-- CLEANUP (for clean migration)
-- ================================================================================
DROP TABLE IF EXISTS trade_simulations CASCADE;
DROP TABLE IF EXISTS optimization_history CASCADE;
DROP TABLE IF EXISTS demo_positions CASCADE;
DROP TABLE IF EXISTS signals CASCADE;
DROP TABLE IF EXISTS strategies CASCADE;
DROP TABLE IF EXISTS signal_quality CASCADE;
DROP TABLE IF EXISTS market_prices CASCADE;
DROP TABLE IF EXISTS system_config CASCADE;

DROP TYPE IF EXISTS position_status CASCADE;
DROP TYPE IF EXISTS position_direction CASCADE;
DROP TYPE IF EXISTS signal_source CASCADE;
DROP TYPE IF EXISTS close_reason CASCADE;
DROP TYPE IF EXISTS strategy_phase CASCADE;
DROP TYPE IF EXISTS optimization_method CASCADE;
DROP TYPE IF EXISTS price_source CASCADE;

-- ================================================================================
-- ENUM TYPES
-- ================================================================================
CREATE TYPE position_status AS ENUM ('open', 'closed', 'cancelled');
CREATE TYPE position_direction AS ENUM ('LONG', 'SHORT');
CREATE TYPE signal_source AS ENUM ('tradingview', 'manual', 'ai');
CREATE TYPE close_reason AS ENUM ('TP', 'SL', 'manual', 'trailing', 'timeout', 'error');
CREATE TYPE strategy_phase AS ENUM ('I', 'II', 'III');
CREATE TYPE optimization_method AS ENUM ('grid_search', 'optuna', 'bayesian', 'genetic');
CREATE TYPE price_source AS ENUM ('bybit', 'binance', 'kraken', 'coinbase');

-- ================================================================================
-- TABLE 1: DEMO_POSITIONS
-- Core table for tracking all trading positions
-- ================================================================================
CREATE TABLE demo_positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    direction position_direction NOT NULL,

    -- Price information
    entry_price DECIMAL(18, 8) NOT NULL,
    current_price DECIMAL(18, 8),
    exit_price DECIMAL(18, 8),
    tp_price DECIMAL(18, 8),
    sl_price DECIMAL(18, 8),
    tp_pct DECIMAL(5, 2),
    sl_pct DECIMAL(5, 2),

    -- Trailing stop configuration
    trailing_config JSONB DEFAULT '{"enabled": false, "activation_pct": 2.0, "trail_pct": 0.5}',

    -- Position sizing
    size_usdt DECIMAL(18, 8) NOT NULL CHECK (size_usdt > 0),
    leverage DECIMAL(5, 2) DEFAULT 1.0 CHECK (leverage >= 1 AND leverage <= 100),

    -- Status and performance
    status position_status NOT NULL DEFAULT 'open',
    pnl_usd DECIMAL(18, 8) DEFAULT 0,
    pnl_pct DECIMAL(10, 4) DEFAULT 0,
    close_reason close_reason,

    -- Timestamps
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT check_tp_sl CHECK (
        (tp_pct IS NULL OR tp_pct > 0) AND
        (sl_pct IS NULL OR sl_pct > 0)
    ),
    CONSTRAINT check_prices CHECK (
        entry_price > 0 AND
        (current_price IS NULL OR current_price > 0) AND
        (exit_price IS NULL OR exit_price > 0)
    ),
    CONSTRAINT check_close_consistency CHECK (
        (status = 'closed' AND closed_at IS NOT NULL AND exit_price IS NOT NULL) OR
        (status != 'closed' AND closed_at IS NULL)
    )
);

-- Indexes for demo_positions
CREATE INDEX idx_positions_symbol_direction ON demo_positions (symbol, direction);
CREATE INDEX idx_positions_status ON demo_positions (status);
CREATE INDEX idx_positions_opened_at ON demo_positions (opened_at DESC);
CREATE INDEX idx_positions_active ON demo_positions (symbol, status) WHERE status = 'open';
CREATE INDEX idx_positions_pnl ON demo_positions (pnl_pct DESC) WHERE status = 'closed';
CREATE INDEX idx_positions_trailing ON demo_positions USING gin (trailing_config);

-- ================================================================================
-- TABLE 2: SIGNALS
-- Trading signals from various sources
-- ================================================================================
CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    direction position_direction NOT NULL,
    signal_source signal_source NOT NULL,

    -- Signal details
    entry_price DECIMAL(18, 8) NOT NULL CHECK (entry_price > 0),
    confidence_score DECIMAL(5, 2) CHECK (confidence_score >= 0 AND confidence_score <= 100),

    -- Indicator values at signal time
    indicators JSONB DEFAULT '{}',
    -- Example: {"rsi": 72.5, "volume": 1234567, "macd": 0.001, "ema_cross": true}

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,

    -- Ensure signals expire
    CONSTRAINT check_expiry CHECK (expires_at IS NULL OR expires_at > created_at)
);

-- Indexes for signals
CREATE INDEX idx_signals_symbol_direction ON signals (symbol, direction, created_at DESC);
CREATE INDEX idx_signals_created_at ON signals (created_at DESC);
CREATE INDEX idx_signals_source ON signals (signal_source);
CREATE INDEX idx_signals_active ON signals (created_at DESC)
    WHERE expires_at IS NULL OR expires_at > NOW();
CREATE INDEX idx_signals_confidence ON signals (confidence_score DESC)
    WHERE confidence_score IS NOT NULL;
CREATE INDEX idx_signals_indicators ON signals USING gin (indicators);

-- ================================================================================
-- TABLE 3: STRATEGIES
-- Trading strategies with optimization parameters and Thompson sampling
-- ================================================================================
CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    direction position_direction NOT NULL,
    webhook_source VARCHAR(100) NOT NULL,

    -- Risk parameters
    tp_pct DECIMAL(5, 2) NOT NULL CHECK (tp_pct > 0 AND tp_pct <= 100),
    sl_pct DECIMAL(5, 2) NOT NULL CHECK (sl_pct > 0 AND sl_pct <= 100),
    trailing_config JSONB DEFAULT '{"enabled": false}',
    breakeven_pct DECIMAL(5, 2) DEFAULT 1.0 CHECK (breakeven_pct >= 0),

    -- Performance metrics
    win_rate DECIMAL(5, 2) DEFAULT 0 CHECK (win_rate >= 0 AND win_rate <= 100),
    rr_ratio DECIMAL(5, 2) DEFAULT 1.5 CHECK (rr_ratio > 0),
    expected_value DECIMAL(10, 4) DEFAULT 0,

    -- Simulation data
    simulations_count INTEGER DEFAULT 0,
    phase strategy_phase NOT NULL DEFAULT 'I',
    quality_score DECIMAL(5, 2) DEFAULT 50 CHECK (quality_score >= 0 AND quality_score <= 100),
    is_active BOOLEAN DEFAULT true,

    -- Thompson sampling parameters (Beta distribution)
    thompson_alpha DECIMAL(10, 4) DEFAULT 1.0 CHECK (thompson_alpha > 0),
    thompson_beta DECIMAL(10, 4) DEFAULT 1.0 CHECK (thompson_beta > 0),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,

    -- Unique constraint per symbol/direction/source
    CONSTRAINT unique_strategy_combo UNIQUE (symbol, direction, webhook_source),

    -- Ensure RR ratio matches TP/SL
    CONSTRAINT check_rr_ratio CHECK (
        ABS(rr_ratio - (tp_pct / sl_pct)) < 0.1 OR rr_ratio = (tp_pct / sl_pct)
    )
);

-- Indexes for strategies
CREATE INDEX idx_strategies_phase_active ON strategies (phase, is_active);
CREATE INDEX idx_strategies_symbol_direction ON strategies (symbol, direction);
CREATE INDEX idx_strategies_quality ON strategies (quality_score DESC) WHERE is_active = true;
CREATE INDEX idx_strategies_win_rate ON strategies (win_rate DESC) WHERE is_active = true;
CREATE INDEX idx_strategies_thompson ON strategies (thompson_alpha, thompson_beta) WHERE is_active = true;
CREATE INDEX idx_strategies_webhook ON strategies (webhook_source);

-- ================================================================================
-- TABLE 4: SIGNAL_QUALITY
-- Signal quality metrics for edge validation (keeping existing structure)
-- ================================================================================
CREATE TABLE signal_quality (
    id SERIAL PRIMARY KEY,

    -- Signal identification
    symbol VARCHAR(50) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    webhook_source VARCHAR(100) NOT NULL,

    -- Performance metrics
    raw_win_rate DECIMAL(5, 2),
    ci_lower DECIMAL(5, 2),
    ci_upper DECIMAL(5, 2),
    expected_value DECIMAL(10, 4),

    -- Statistical validation
    sample_size INTEGER,
    is_significant BOOLEAN DEFAULT false,
    p_value DECIMAL(10, 8),

    -- Quality assessment
    has_edge BOOLEAN DEFAULT false,
    quality_score DECIMAL(5, 2),
    recommendation VARCHAR(50),

    -- High-WR potential metrics
    high_wr_potential BOOLEAN DEFAULT false,
    phase2_predicted_wr DECIMAL(5, 2) DEFAULT 0,
    phase2_confidence DECIMAL(5, 2) DEFAULT 0,

    -- Consistency tracking
    consistency_score DECIMAL(5, 2) DEFAULT 0,
    rolling_variance DECIMAL(10, 4) DEFAULT 0,
    max_streak INTEGER DEFAULT 0,
    current_streak INTEGER DEFAULT 0,

    -- Early detection
    early_detection_status VARCHAR(30),

    -- Metadata
    last_analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_signal_quality UNIQUE (symbol, direction, webhook_source),
    CONSTRAINT check_win_rates CHECK (
        (raw_win_rate IS NULL OR (raw_win_rate >= 0 AND raw_win_rate <= 100)) AND
        (phase2_predicted_wr >= 0 AND phase2_predicted_wr <= 100)
    )
);

-- Indexes for signal_quality
CREATE INDEX idx_signal_quality_combo ON signal_quality (symbol, direction, webhook_source);
CREATE INDEX idx_signal_quality_has_edge ON signal_quality (has_edge);
CREATE INDEX idx_signal_quality_score ON signal_quality (quality_score DESC);
CREATE INDEX idx_signal_quality_high_wr ON signal_quality (high_wr_potential);
CREATE INDEX idx_signal_quality_consistency ON signal_quality (consistency_score DESC);

-- ================================================================================
-- TABLE 5: MARKET_PRICES
-- Real-time market price data
-- ================================================================================
CREATE TABLE market_prices (
    symbol VARCHAR(20) NOT NULL,
    price DECIMAL(18, 8) NOT NULL CHECK (price > 0),
    volume DECIMAL(20, 8) DEFAULT 0 CHECK (volume >= 0),
    volatility DECIMAL(10, 4) DEFAULT 0 CHECK (volatility >= 0),

    -- Bid/Ask spread
    bid DECIMAL(18, 8) CHECK (bid > 0),
    ask DECIMAL(18, 8) CHECK (ask > 0),
    spread DECIMAL(10, 4) GENERATED ALWAYS AS
        (CASE WHEN bid IS NOT NULL AND ask IS NOT NULL
              THEN ((ask - bid) / bid) * 100
              ELSE NULL
         END) STORED,

    -- Source and timestamp
    source price_source NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Composite primary key for time-series data
    PRIMARY KEY (symbol, timestamp, source),

    -- Ensure bid < ask
    CONSTRAINT check_bid_ask CHECK (
        (bid IS NULL AND ask IS NULL) OR
        (bid IS NOT NULL AND ask IS NOT NULL AND bid < ask)
    )
);

-- Indexes for market_prices
CREATE INDEX idx_prices_symbol_timestamp ON market_prices (symbol, timestamp DESC);
CREATE INDEX idx_prices_timestamp ON market_prices (timestamp DESC);
CREATE INDEX idx_prices_volatility ON market_prices (volatility DESC) WHERE volatility > 0;
CREATE INDEX idx_prices_source ON market_prices (source);

-- ================================================================================
-- TABLE 6: OPTIMIZATION_HISTORY
-- Track strategy optimization runs
-- ================================================================================
CREATE TABLE optimization_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    direction position_direction NOT NULL,
    optimization_method optimization_method NOT NULL,

    -- Optimization results
    trials_count INTEGER NOT NULL CHECK (trials_count > 0),
    best_score DECIMAL(10, 4) NOT NULL,
    best_params JSONB NOT NULL,
    -- Example: {"tp_pct": 2.5, "sl_pct": 1.0, "trailing": {"activation_pct": 2.0}}

    -- Performance metrics
    optimization_time_seconds INTEGER CHECK (optimization_time_seconds > 0),

    -- Timestamp
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for optimization_history
CREATE INDEX idx_optimization_symbol_direction ON optimization_history (symbol, direction, created_at DESC);
CREATE INDEX idx_optimization_method ON optimization_history (optimization_method);
CREATE INDEX idx_optimization_score ON optimization_history (best_score DESC);
CREATE INDEX idx_optimization_params ON optimization_history USING gin (best_params);

-- ================================================================================
-- TABLE 7: TRADE_SIMULATIONS
-- Detailed simulation results linking to demo positions
-- ================================================================================
CREATE TABLE trade_simulations (
    id SERIAL PRIMARY KEY,
    demo_position_id INTEGER REFERENCES demo_positions(id) ON DELETE CASCADE,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE CASCADE,
    baseline_trade_id INTEGER, -- Reference to baseline trade if applicable

    -- Excursion metrics
    mae DECIMAL(10, 4), -- Max Adverse Excursion (%)
    mfe DECIMAL(10, 4), -- Max Favorable Excursion (%)

    -- Duration
    duration_hours DECIMAL(10, 2),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT check_excursions CHECK (
        (mae IS NULL OR mae <= 0) AND  -- MAE should be negative or zero
        (mfe IS NULL OR mfe >= 0)       -- MFE should be positive or zero
    )
);

-- Indexes for trade_simulations
CREATE INDEX idx_simulations_position ON trade_simulations (demo_position_id);
CREATE INDEX idx_simulations_strategy ON trade_simulations (strategy_id);
CREATE INDEX idx_simulations_baseline ON trade_simulations (baseline_trade_id);
CREATE INDEX idx_simulations_mae ON trade_simulations (mae) WHERE mae IS NOT NULL;
CREATE INDEX idx_simulations_mfe ON trade_simulations (mfe DESC) WHERE mfe IS NOT NULL;

-- ================================================================================
-- TABLE 8: SYSTEM_CONFIG
-- Key-value store for system configuration
-- ================================================================================
CREATE TABLE system_config (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for system_config
CREATE INDEX idx_config_updated ON system_config (updated_at DESC);

-- ================================================================================
-- FUNCTIONS
-- ================================================================================

-- Function 1: Get active positions for a symbol
CREATE OR REPLACE FUNCTION get_active_positions(p_symbol VARCHAR)
RETURNS TABLE (
    id INTEGER,
    direction position_direction,
    entry_price DECIMAL,
    current_price DECIMAL,
    pnl_pct DECIMAL,
    opened_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        dp.id,
        dp.direction,
        dp.entry_price,
        dp.current_price,
        dp.pnl_pct,
        dp.opened_at
    FROM demo_positions dp
    WHERE dp.symbol = p_symbol
      AND dp.status = 'open'
    ORDER BY dp.opened_at DESC;
END;
$$ LANGUAGE plpgsql;

-- Function 2: Calculate unrealized P&L for all open positions
CREATE OR REPLACE FUNCTION calculate_unrealized_pnl()
RETURNS TABLE (
    total_unrealized_pnl DECIMAL,
    positions_count INTEGER,
    avg_pnl_pct DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COALESCE(SUM(pnl_usd), 0) as total_unrealized_pnl,
        COUNT(*)::INTEGER as positions_count,
        COALESCE(AVG(pnl_pct), 0) as avg_pnl_pct
    FROM demo_positions
    WHERE status = 'open';
END;
$$ LANGUAGE plpgsql;

-- Function 3: Get strategy performance over N days
CREATE OR REPLACE FUNCTION get_strategy_performance(
    p_strategy_id INTEGER,
    p_days INTEGER DEFAULT 30
)
RETURNS TABLE (
    total_trades INTEGER,
    win_rate DECIMAL,
    total_pnl DECIMAL,
    avg_pnl_pct DECIMAL,
    sharpe_ratio DECIMAL
) AS $$
DECLARE
    v_returns DECIMAL[];
    v_avg_return DECIMAL;
    v_std_dev DECIMAL;
BEGIN
    -- Calculate performance metrics
    WITH trades AS (
        SELECT
            dp.pnl_pct,
            dp.pnl_usd,
            CASE WHEN dp.pnl_usd > 0 THEN 1 ELSE 0 END as is_win
        FROM demo_positions dp
        JOIN trade_simulations ts ON ts.demo_position_id = dp.id
        WHERE ts.strategy_id = p_strategy_id
          AND dp.status = 'closed'
          AND dp.closed_at >= NOW() - INTERVAL '1 day' * p_days
    )
    SELECT
        COUNT(*)::INTEGER,
        CASE WHEN COUNT(*) > 0
             THEN (SUM(is_win)::DECIMAL / COUNT(*)::DECIMAL) * 100
             ELSE 0 END,
        COALESCE(SUM(pnl_usd), 0),
        COALESCE(AVG(pnl_pct), 0),
        0::DECIMAL -- Placeholder for Sharpe ratio
    INTO total_trades, win_rate, total_pnl, avg_pnl_pct, sharpe_ratio
    FROM trades;

    -- Calculate Sharpe ratio if we have trades
    IF total_trades > 0 THEN
        SELECT array_agg(pnl_pct) INTO v_returns
        FROM (
            SELECT dp.pnl_pct
            FROM demo_positions dp
            JOIN trade_simulations ts ON ts.demo_position_id = dp.id
            WHERE ts.strategy_id = p_strategy_id
              AND dp.status = 'closed'
              AND dp.closed_at >= NOW() - INTERVAL '1 day' * p_days
        ) t;

        IF array_length(v_returns, 1) > 1 THEN
            v_avg_return := avg_pnl_pct;
            SELECT stddev(unnest) INTO v_std_dev FROM unnest(v_returns);

            IF v_std_dev > 0 THEN
                sharpe_ratio := v_avg_return / v_std_dev;
            END IF;
        END IF;
    END IF;

    RETURN QUERY SELECT total_trades, win_rate, total_pnl, avg_pnl_pct, sharpe_ratio;
END;
$$ LANGUAGE plpgsql;

-- ================================================================================
-- VIEWS
-- ================================================================================

-- View 1: Position Summary (aggregated P&L)
CREATE OR REPLACE VIEW v_position_summary AS
SELECT
    symbol,
    COUNT(*) FILTER (WHERE status = 'open') as open_positions,
    COUNT(*) FILTER (WHERE status = 'closed') as closed_positions,
    SUM(pnl_usd) FILTER (WHERE status = 'closed') as realized_pnl,
    SUM(pnl_usd) FILTER (WHERE status = 'open') as unrealized_pnl,
    AVG(pnl_pct) FILTER (WHERE status = 'closed') as avg_closed_pnl_pct,
    COUNT(*) FILTER (WHERE status = 'closed' AND pnl_usd > 0) as wins,
    COUNT(*) FILTER (WHERE status = 'closed' AND pnl_usd <= 0) as losses,
    CASE
        WHEN COUNT(*) FILTER (WHERE status = 'closed') > 0
        THEN (COUNT(*) FILTER (WHERE status = 'closed' AND pnl_usd > 0)::DECIMAL /
              COUNT(*) FILTER (WHERE status = 'closed')::DECIMAL) * 100
        ELSE 0
    END as win_rate
FROM demo_positions
GROUP BY symbol
ORDER BY symbol;

-- View 2: Strategy Leaderboard (top performing strategies)
CREATE OR REPLACE VIEW v_strategy_leaderboard AS
WITH strategy_stats AS (
    SELECT
        s.id,
        s.symbol,
        s.direction,
        s.webhook_source,
        s.phase,
        s.win_rate,
        s.expected_value,
        s.quality_score,
        s.simulations_count,
        COUNT(DISTINCT ts.id) as actual_trades,
        AVG(ts.mfe) as avg_mfe,
        AVG(ts.mae) as avg_mae,
        s.thompson_alpha,
        s.thompson_beta,
        s.last_used_at
    FROM strategies s
    LEFT JOIN trade_simulations ts ON ts.strategy_id = s.id
    WHERE s.is_active = true
    GROUP BY s.id
)
SELECT
    id,
    symbol,
    direction,
    webhook_source,
    phase,
    win_rate,
    expected_value,
    quality_score,
    simulations_count,
    actual_trades,
    avg_mfe,
    avg_mae,
    -- Thompson sampling score (using mean of Beta distribution)
    (thompson_alpha / (thompson_alpha + thompson_beta)) * 100 as thompson_score,
    last_used_at,
    RANK() OVER (ORDER BY quality_score DESC, win_rate DESC) as overall_rank,
    RANK() OVER (PARTITION BY phase ORDER BY win_rate DESC) as phase_rank
FROM strategy_stats
WHERE simulations_count > 0 OR actual_trades > 0
ORDER BY quality_score DESC, win_rate DESC
LIMIT 100;

-- ================================================================================
-- TRIGGERS
-- ================================================================================

-- Trigger to update 'updated_at' column
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON demo_positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_system_config_updated_at
    BEFORE UPDATE ON system_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Trigger to auto-calculate PnL on price updates
CREATE OR REPLACE FUNCTION calculate_position_pnl()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.current_price IS NOT NULL AND NEW.entry_price IS NOT NULL THEN
        IF NEW.direction = 'LONG' THEN
            NEW.pnl_usd := (NEW.current_price - NEW.entry_price) * NEW.size_usdt / NEW.entry_price;
            NEW.pnl_pct := ((NEW.current_price - NEW.entry_price) / NEW.entry_price) * 100;
        ELSE -- SHORT
            NEW.pnl_usd := (NEW.entry_price - NEW.current_price) * NEW.size_usdt / NEW.entry_price;
            NEW.pnl_pct := ((NEW.entry_price - NEW.current_price) / NEW.entry_price) * 100;
        END IF;

        -- Apply leverage to PnL
        NEW.pnl_usd := NEW.pnl_usd * NEW.leverage;
        NEW.pnl_pct := NEW.pnl_pct * NEW.leverage;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER calculate_demo_position_pnl
    BEFORE INSERT OR UPDATE OF current_price ON demo_positions
    FOR EACH ROW EXECUTE FUNCTION calculate_position_pnl();

-- ================================================================================
-- INITIAL DATA
-- ================================================================================

-- Insert default system configuration
INSERT INTO system_config (key, value, description) VALUES
    ('trading.max_open_positions', '{"value": 10}', 'Maximum number of open positions allowed'),
    ('trading.default_leverage', '{"value": 1}', 'Default leverage for new positions'),
    ('trading.default_size_usdt', '{"value": 100}', 'Default position size in USDT'),
    ('risk.max_daily_loss', '{"value": 500}', 'Maximum daily loss in USDT'),
    ('risk.max_position_size', '{"value": 1000}', 'Maximum single position size in USDT'),
    ('optimization.min_trades_phase1', '{"value": 100}', 'Minimum trades for Phase I'),
    ('optimization.min_trades_phase2', '{"value": 500}', 'Minimum trades for Phase II'),
    ('optimization.min_trades_phase3', '{"value": 1000}', 'Minimum trades for Phase III'),
    ('optimization.target_win_rate', '{"value": 65}', 'Target win rate percentage'),
    ('signals.default_expiry_minutes', '{"value": 15}', 'Default signal expiry in minutes'),
    ('dashboard.refresh_interval_ms', '{"value": 5000}', 'Dashboard refresh interval'),
    ('dashboard.chart_candles', '{"value": 100}', 'Number of candles to display'),
    ('notifications.enabled', '{"value": true}', 'Enable notifications'),
    ('notifications.webhook_url', '{"value": ""}', 'Webhook URL for notifications'),
    ('api.rate_limit', '{"requests_per_minute": 60}', 'API rate limiting configuration');

-- Insert example strategies (high-performing baseline strategies)
INSERT INTO strategies (
    symbol, direction, webhook_source, tp_pct, sl_pct,
    win_rate, rr_ratio, expected_value, phase, quality_score, is_active
) VALUES
    ('BTCUSDT', 'LONG', 'momentum_breakout', 2.5, 1.0, 68.5, 2.5, 0.46, 'II', 75.0, true),
    ('BTCUSDT', 'SHORT', 'resistance_reversal', 2.0, 1.0, 65.0, 2.0, 0.30, 'I', 65.0, true),
    ('ETHUSDT', 'LONG', 'volume_surge', 3.0, 1.5, 66.7, 2.0, 0.33, 'I', 68.0, true),
    ('ETHUSDT', 'SHORT', 'macd_divergence', 2.0, 0.8, 70.0, 2.5, 0.50, 'II', 78.0, true),
    ('SOLUSDT', 'LONG', 'rsi_oversold', 2.5, 1.2, 64.0, 2.08, 0.25, 'I', 62.0, true);

-- ================================================================================
-- PERMISSIONS (uncomment and adjust for your database user)
-- ================================================================================
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO your_app_user;

-- ================================================================================
-- DOCUMENTATION
-- ================================================================================
COMMENT ON TABLE demo_positions IS 'Core table tracking all trading positions with P&L calculation';
COMMENT ON TABLE signals IS 'Trading signals from various sources (TradingView, AI, Manual)';
COMMENT ON TABLE strategies IS 'Trading strategies with optimization parameters and Thompson sampling';
COMMENT ON TABLE signal_quality IS 'Signal quality metrics for edge validation before optimization';
COMMENT ON TABLE market_prices IS 'Real-time market price data with bid/ask spreads';
COMMENT ON TABLE optimization_history IS 'Historical record of strategy optimization runs';
COMMENT ON TABLE trade_simulations IS 'Detailed simulation results with MAE/MFE metrics';
COMMENT ON TABLE system_config IS 'Key-value store for system configuration and settings';

COMMENT ON FUNCTION get_active_positions IS 'Returns all active positions for a given symbol';
COMMENT ON FUNCTION calculate_unrealized_pnl IS 'Calculates total unrealized P&L across all open positions';
COMMENT ON FUNCTION get_strategy_performance IS 'Returns performance metrics for a strategy over N days';

-- ================================================================================
-- SCHEMA DIAGRAM (ASCII)
-- ================================================================================
/*
                            HIGH-WR TRADING SYSTEM DATABASE SCHEMA
    ========================================================================================

    ┌─────────────────┐         ┌──────────────┐         ┌─────────────────┐
    │  DEMO_POSITIONS │◄────────┤    SIGNALS   │         │   STRATEGIES    │
    ├─────────────────┤         ├──────────────┤         ├─────────────────┤
    │ id (PK)         │         │ id (PK)      │         │ id (PK)         │
    │ symbol          │         │ symbol       │         │ symbol          │
    │ direction       │         │ direction    │         │ direction       │
    │ entry_price     │         │ signal_source│         │ webhook_source  │
    │ current_price   │         │ entry_price  │         │ tp_pct          │
    │ exit_price      │         │ confidence   │         │ sl_pct          │
    │ tp_price        │         │ indicators   │         │ win_rate        │
    │ sl_price        │         │ created_at   │         │ rr_ratio        │
    │ pnl_usd         │         │ expires_at   │         │ phase           │
    │ pnl_pct         │         └──────────────┘         │ thompson_alpha  │
    │ status          │                                  │ thompson_beta   │
    │ close_reason    │                                  │ quality_score   │
    └─────────────────┘                                  └─────────────────┘
            ▲                                                      ▲
            │                                                      │
            │                                                      │
    ┌───────┴─────────┐                                  ┌────────┴────────┐
    │TRADE_SIMULATIONS│                                  │ SIGNAL_QUALITY  │
    ├─────────────────┤                                  ├─────────────────┤
    │ id (PK)         │                                  │ id (PK)         │
    │ demo_position_id├──────────────┐                  │ symbol          │
    │ strategy_id (FK)│              │                  │ direction       │
    │ mae             │              │                  │ webhook_source  │
    │ mfe             │              │                  │ raw_win_rate    │
    │ duration_hours  │              │                  │ has_edge        │
    └─────────────────┘              │                  │ high_wr_potential│
                                     │                  └─────────────────┘
                                     │
    ┌─────────────────┐              │                  ┌─────────────────┐
    │  MARKET_PRICES  │              │                  │OPTIMIZATION_HIST│
    ├─────────────────┤              │                  ├─────────────────┤
    │ symbol (PK)     │              │                  │ id (PK)         │
    │ timestamp (PK)  │              │                  │ symbol          │
    │ source (PK)     │              │                  │ direction       │
    │ price           │              │                  │ method          │
    │ volume          │              │                  │ best_score      │
    │ bid/ask         │              │                  │ best_params     │
    │ spread          │              │                  │ trials_count    │
    └─────────────────┘              │                  └─────────────────┘
                                     │
    ┌─────────────────┐              │
    │  SYSTEM_CONFIG  │              │
    ├─────────────────┤              │
    │ key (PK)        │              │
    │ value (JSONB)   │              │
    │ description     │              │
    │ updated_at      │              │
    └─────────────────┘              │
                                     │
    VIEWS:                           │
    ┌──────────────────┐             │
    │ v_position_summary│◄────────────┘
    └──────────────────┘
    ┌──────────────────────┐
    │ v_strategy_leaderboard│
    └──────────────────────┘

    KEY RELATIONSHIPS:
    - trade_simulations → demo_positions (Many-to-One)
    - trade_simulations → strategies (Many-to-One)
    - signal_quality ←→ strategies (One-to-One via symbol/direction/source)
    - market_prices: Time-series data (no direct FK relationships)
    - system_config: Standalone configuration table

    INDEXES SUMMARY:
    - Symbol/Direction combinations for fast lookups
    - Status-based filtering for active positions
    - Timestamp ordering for time-series queries
    - JSON GIN indexes for flexible querying
    - Quality/Score based sorting for rankings

    ========================================================================================
*/

-- ================================================================================
-- PERFORMANCE OPTIMIZATION
-- ================================================================================
-- Run ANALYZE after initial data load to update statistics
ANALYZE demo_positions;
ANALYZE signals;
ANALYZE strategies;
ANALYZE signal_quality;
ANALYZE market_prices;
ANALYZE optimization_history;
ANALYZE trade_simulations;
ANALYZE system_config;

-- ================================================================================
-- END OF SCHEMA
-- ================================================================================