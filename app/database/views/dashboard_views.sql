-- Dashboard Optimized Database Views
-- These views pre-aggregate common dashboard queries for sub-100ms response times
-- Run this script to create views in PostgreSQL

-- ============================================
-- 1. System Overview View
-- ============================================
CREATE OR REPLACE VIEW dashboard_system_overview AS
SELECT
    COUNT(DISTINCT ts.id) as total_trades,
    COUNT(DISTINCT CASE WHEN ts.status = 'active' THEN ts.id END) as active_trades,
    COUNT(DISTINCT ts.symbol) as total_symbols,

    -- Performance metrics
    COALESCE(AVG(CASE WHEN ts.status = 'closed' AND ts.final_pnl_pct > 0 THEN 100.0 ELSE 0 END), 0) as win_rate,
    COALESCE(AVG(ts.risk_reward_ratio), 0) as avg_risk_reward,
    COALESCE(SUM(ts.final_pnl_usd), 0) as total_pnl_usd,
    COALESCE(AVG(ts.final_pnl_pct), 0) as avg_pnl_pct,

    -- Volume metrics
    COUNT(DISTINCT CASE WHEN ts.created_at >= NOW() - INTERVAL '1 day' THEN ts.id END) as volume_24h,
    COUNT(DISTINCT CASE WHEN ts.created_at >= NOW() - INTERVAL '7 days' THEN ts.id END) as volume_7d,
    COUNT(DISTINCT CASE WHEN ts.created_at >= NOW() - INTERVAL '30 days' THEN ts.id END) as volume_30d,

    -- Additional metrics
    COUNT(DISTINCT CASE WHEN ts.tp1_hit = true THEN ts.id END) as tp1_hits,
    COUNT(DISTINCT CASE WHEN ts.tp2_hit = true THEN ts.id END) as tp2_hits,
    COUNT(DISTINCT CASE WHEN ts.tp3_hit = true THEN ts.id END) as tp3_hits,
    COUNT(DISTINCT CASE WHEN ts.sl_hit = true THEN ts.id END) as sl_hits,

    NOW() as last_updated
FROM trade_setups ts;

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_dashboard_overview_status ON trade_setups(status);
CREATE INDEX IF NOT EXISTS idx_dashboard_overview_created ON trade_setups(created_at DESC);


-- ============================================
-- 2. Phase Metrics View
-- ============================================
CREATE OR REPLACE VIEW dashboard_phase_metrics AS
WITH trade_phases AS (
    -- Determine phase for each trade based on count
    SELECT
        ts.*,
        COUNT(*) OVER (
            PARTITION BY ts.symbol, ts.direction, ts.webhook_source
            ORDER BY ts.created_at
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as trade_number,
        CASE
            WHEN COUNT(*) OVER (
                PARTITION BY ts.symbol, ts.direction, ts.webhook_source
                ORDER BY ts.created_at
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) <= 30 THEN 'Phase I'
            WHEN COUNT(*) OVER (
                PARTITION BY ts.symbol, ts.direction, ts.webhook_source
                ORDER BY ts.created_at
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) <= 100 THEN 'Phase II'
            ELSE 'Phase III'
        END as phase
    FROM trade_setups ts
)
SELECT
    phase,
    COUNT(*) as trade_count,
    COUNT(CASE WHEN status = 'active' THEN 1 END) as active_count,

    -- Performance metrics
    AVG(CASE WHEN status = 'closed' AND final_pnl_pct > 0 THEN 100.0 ELSE 0 END) as win_rate,
    AVG(final_pnl_pct) as avg_pnl_pct,
    SUM(final_pnl_usd) as total_pnl_usd,
    AVG(risk_reward_ratio) as avg_risk_reward,

    -- Timing metrics
    AVG(trade_duration_hours) as avg_duration_hours,
    MIN(LEAST(tp1_time_minutes, tp2_time_minutes, tp3_time_minutes)) as fastest_tp_minutes,

    -- Symbol distribution
    COUNT(DISTINCT symbol) as unique_symbols,
    MODE() WITHIN GROUP (ORDER BY symbol) as top_symbol,
    MODE() WITHIN GROUP (ORDER BY risk_strategy) as top_strategy

FROM trade_phases
GROUP BY phase;


-- ============================================
-- 3. Signal Quality Aggregated View
-- ============================================
CREATE OR REPLACE VIEW dashboard_signal_quality_agg AS
SELECT
    -- Distribution
    COUNT(CASE WHEN quality_score > 80 THEN 1 END) as excellent_count,
    COUNT(CASE WHEN quality_score BETWEEN 60 AND 80 THEN 1 END) as good_count,
    COUNT(CASE WHEN quality_score BETWEEN 40 AND 60 THEN 1 END) as fair_count,
    COUNT(CASE WHEN quality_score < 40 THEN 1 END) as poor_count,

    -- Overall metrics
    COUNT(*) as total_signals,
    AVG(quality_score) as avg_quality_score,
    COUNT(CASE WHEN has_edge = true THEN 1 END) as signals_with_edge,
    COUNT(CASE WHEN recommendation = 'collect_more_data' THEN 1 END) as signals_needing_data,

    -- Top performers
    MAX(quality_score) as max_quality_score,
    MIN(quality_score) as min_quality_score,
    STDDEV(quality_score) as quality_score_stddev

FROM signal_quality;


-- ============================================
-- 4. Strategy Performance Ranking View
-- ============================================
CREATE OR REPLACE VIEW dashboard_strategy_ranking AS
WITH strategy_ranks AS (
    SELECT
        sp.*,
        RANK() OVER (
            PARTITION BY symbol, direction, webhook_source
            ORDER BY strategy_score DESC
        ) as rank_within_group,
        RANK() OVER (ORDER BY strategy_score DESC) as global_rank
    FROM strategy_performance sp
)
SELECT
    sr.*,
    CASE
        WHEN rank_within_group = 1 THEN true
        ELSE false
    END as is_best_for_asset
FROM strategy_ranks sr;

-- Create composite index for strategy queries
CREATE INDEX IF NOT EXISTS idx_strategy_ranking
ON strategy_performance(symbol, direction, webhook_source, strategy_score DESC);


-- ============================================
-- 5. Active Risk Exposure View
-- ============================================
CREATE OR REPLACE VIEW dashboard_active_risk AS
SELECT
    -- Overall exposure
    SUM(notional_position_usd) as total_exposure_usd,
    SUM(margin_required_usd) as total_margin_usd,
    AVG(leverage) as avg_leverage,

    -- Risk distribution
    COUNT(CASE
        WHEN current_price <= planned_sl_price * 1.05
        THEN 1
    END) as positions_near_sl,
    COUNT(CASE
        WHEN current_price > entry_price
        THEN 1
    END) as positions_in_profit,

    -- Per symbol exposure
    MAX(symbol_exposure.exposure_pct) as max_symbol_exposure_pct,
    MAX(symbol_exposure.symbol) as max_exposure_symbol

FROM trade_setups ts
LEFT JOIN LATERAL (
    SELECT
        symbol,
        SUM(notional_position_usd) / NULLIF(
            (SELECT SUM(notional_position_usd) FROM trade_setups WHERE status = 'active'),
            0
        ) * 100 as exposure_pct
    FROM trade_setups
    WHERE status = 'active'
    GROUP BY symbol
    ORDER BY exposure_pct DESC
    LIMIT 1
) symbol_exposure ON true
WHERE ts.status = 'active'
GROUP BY symbol_exposure.exposure_pct, symbol_exposure.symbol;


-- ============================================
-- 6. Circuit Breaker Status View
-- ============================================
CREATE OR REPLACE VIEW dashboard_circuit_breakers AS
WITH recent_trades AS (
    SELECT
        symbol,
        direction,
        webhook_source,
        final_pnl_pct,
        status,
        created_at,
        -- Count consecutive losses
        SUM(CASE WHEN final_pnl_pct < 0 THEN 1 ELSE 0 END) OVER (
            PARTITION BY symbol, direction, webhook_source
            ORDER BY created_at DESC
            ROWS BETWEEN CURRENT ROW AND 4 FOLLOWING
        ) as consecutive_losses,
        -- Calculate rolling drawdown
        MIN(final_pnl_pct) OVER (
            PARTITION BY symbol, direction, webhook_source
            ORDER BY created_at DESC
            ROWS BETWEEN CURRENT ROW AND 9 FOLLOWING
        ) as rolling_drawdown
    FROM trade_setups
    WHERE status = 'closed'
    AND created_at >= NOW() - INTERVAL '7 days'
)
SELECT DISTINCT
    symbol,
    direction,
    webhook_source,
    MAX(consecutive_losses) as max_consecutive_losses,
    ABS(MIN(rolling_drawdown)) as max_drawdown_pct,
    CASE
        WHEN MAX(consecutive_losses) >= 5 THEN true
        WHEN ABS(MIN(rolling_drawdown)) > 10 THEN true
        ELSE false
    END as is_circuit_breaker_active,
    CASE
        WHEN MAX(consecutive_losses) >= 5 THEN 'Consecutive losses'
        WHEN ABS(MIN(rolling_drawdown)) > 10 THEN 'Excessive drawdown'
        ELSE NULL
    END as trigger_reason
FROM recent_trades
GROUP BY symbol, direction, webhook_source;


-- ============================================
-- 7. Drawdown Tracking View
-- ============================================
CREATE OR REPLACE VIEW dashboard_drawdown_metrics AS
WITH drawdown_calc AS (
    SELECT
        ts.created_at::date as trade_date,
        SUM(ts.final_pnl_usd) OVER (ORDER BY ts.created_at) as cumulative_pnl,
        MAX(SUM(ts.final_pnl_usd) OVER (ORDER BY ts.created_at)) OVER (
            ORDER BY ts.created_at
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as running_peak,
        ts.status
    FROM trade_setups ts
    WHERE ts.status = 'closed'
)
SELECT
    MIN(CASE
        WHEN cumulative_pnl < running_peak
        THEN (cumulative_pnl - running_peak) / NULLIF(running_peak, 0) * 100
        ELSE 0
    END) as max_drawdown_pct,

    MIN(CASE
        WHEN trade_date >= CURRENT_DATE - INTERVAL '1 day'
        AND cumulative_pnl < running_peak
        THEN (cumulative_pnl - running_peak) / NULLIF(running_peak, 0) * 100
        ELSE 0
    END) as current_drawdown_pct,

    MAX(trade_date) FILTER (
        WHERE cumulative_pnl < running_peak * 0.9
    ) as max_drawdown_date,

    CASE
        WHEN MAX(cumulative_pnl) >= MAX(running_peak) * 0.95
        THEN CURRENT_DATE - MAX(trade_date) FILTER (WHERE cumulative_pnl < running_peak * 0.95)
        ELSE NULL
    END as recovery_days

FROM drawdown_calc;


-- ============================================
-- 8. Real-time Trade Updates View
-- ============================================
CREATE OR REPLACE VIEW dashboard_recent_updates AS
SELECT
    ts.id,
    ts.trade_identifier,
    ts.symbol,
    ts.direction,
    ts.status,
    ts.entry_price,
    ts.current_price,
    ts.current_pnl_pct,
    ts.current_pnl_usd,

    -- Latest milestone
    GREATEST(
        ts.tp1_hit_at,
        ts.tp2_hit_at,
        ts.tp3_hit_at,
        ts.sl_hit_at,
        ts.time_exit_at
    ) as last_update_time,

    CASE
        WHEN ts.sl_hit THEN 'sl_hit'
        WHEN ts.tp3_hit THEN 'tp3_hit'
        WHEN ts.tp2_hit THEN 'tp2_hit'
        WHEN ts.tp1_hit THEN 'tp1_hit'
        WHEN ts.time_exit THEN 'time_exit'
        WHEN ts.status = 'active' THEN 'active'
        ELSE 'pending'
    END as last_event

FROM trade_setups ts
WHERE ts.created_at >= NOW() - INTERVAL '24 hours'
ORDER BY GREATEST(
    ts.created_at,
    ts.tp1_hit_at,
    ts.tp2_hit_at,
    ts.tp3_hit_at,
    ts.sl_hit_at,
    ts.time_exit_at
) DESC
LIMIT 100;


-- ============================================
-- 9. Top Performers View (for leaderboard)
-- ============================================
CREATE OR REPLACE VIEW dashboard_top_performers AS
SELECT
    symbol,
    direction,
    webhook_source,
    COUNT(*) as trade_count,
    AVG(CASE WHEN final_pnl_pct > 0 THEN 100.0 ELSE 0 END) as win_rate,
    SUM(final_pnl_usd) as total_pnl,
    AVG(final_pnl_pct) as avg_pnl_pct,
    AVG(risk_reward_ratio) as avg_risk_reward,
    AVG(trade_duration_hours) as avg_duration,

    -- Scoring formula (customize as needed)
    (
        AVG(CASE WHEN final_pnl_pct > 0 THEN 100.0 ELSE 0 END) * 0.3 +  -- 30% weight on win rate
        LEAST(AVG(risk_reward_ratio) * 20, 40) * 0.3 +                  -- 30% weight on RR (capped)
        LEAST(SUM(final_pnl_usd) / 100, 40) * 0.2 +                     -- 20% weight on total PnL
        CASE
            WHEN AVG(trade_duration_hours) <= 4 THEN 20                 -- 20% for fast trades
            WHEN AVG(trade_duration_hours) <= 12 THEN 15
            WHEN AVG(trade_duration_hours) <= 24 THEN 10
            ELSE 0
        END * 0.2
    ) as performance_score

FROM trade_setups
WHERE status = 'closed'
GROUP BY symbol, direction, webhook_source
HAVING COUNT(*) >= 5  -- Minimum 5 trades for ranking
ORDER BY performance_score DESC
LIMIT 50;


-- ============================================
-- 10. Materialized View for Heavy Aggregations
-- ============================================
-- This materialized view is refreshed periodically for expensive calculations

CREATE MATERIALIZED VIEW IF NOT EXISTS dashboard_stats_cache AS
WITH base_stats AS (
    SELECT
        DATE_TRUNC('hour', ts.created_at) as time_bucket,
        ts.symbol,
        ts.direction,
        ts.webhook_source,
        COUNT(*) as trades,
        AVG(CASE WHEN ts.final_pnl_pct > 0 THEN 1.0 ELSE 0 END) as win_rate,
        AVG(ts.final_pnl_pct) as avg_pnl,
        SUM(ts.final_pnl_usd) as total_pnl,
        AVG(ts.trade_duration_hours) as avg_duration
    FROM trade_setups ts
    WHERE ts.status = 'closed'
    GROUP BY 1, 2, 3, 4
)
SELECT * FROM base_stats;

-- Create indexes on materialized view
CREATE INDEX IF NOT EXISTS idx_dashboard_cache_time
ON dashboard_stats_cache(time_bucket DESC);

CREATE INDEX IF NOT EXISTS idx_dashboard_cache_symbol
ON dashboard_stats_cache(symbol, direction, webhook_source);

-- Refresh policy (run this periodically, e.g., every 5 minutes)
-- REFRESH MATERIALIZED VIEW CONCURRENTLY dashboard_stats_cache;


-- ============================================
-- Helper Functions for Complex Calculations
-- ============================================

-- Function to calculate Sharpe ratio for a trading signal
CREATE OR REPLACE FUNCTION calculate_sharpe_ratio(
    p_symbol VARCHAR,
    p_direction VARCHAR,
    p_webhook_source VARCHAR,
    p_days INTEGER DEFAULT 30
) RETURNS NUMERIC AS $$
DECLARE
    avg_return NUMERIC;
    stddev_return NUMERIC;
    sharpe NUMERIC;
BEGIN
    SELECT
        AVG(final_pnl_pct),
        STDDEV(final_pnl_pct)
    INTO avg_return, stddev_return
    FROM trade_setups
    WHERE symbol = p_symbol
    AND direction = p_direction
    AND webhook_source = p_webhook_source
    AND status = 'closed'
    AND created_at >= CURRENT_DATE - INTERVAL '1 day' * p_days;

    IF stddev_return > 0 THEN
        sharpe := (avg_return / stddev_return) * SQRT(252); -- Annualized
    ELSE
        sharpe := 0;
    END IF;

    RETURN sharpe;
END;
$$ LANGUAGE plpgsql;


-- Function to calculate maximum consecutive wins/losses
CREATE OR REPLACE FUNCTION calculate_streaks(
    p_symbol VARCHAR,
    p_direction VARCHAR,
    p_webhook_source VARCHAR
) RETURNS TABLE(max_win_streak INTEGER, max_loss_streak INTEGER) AS $$
DECLARE
    current_streak INTEGER := 0;
    max_wins INTEGER := 0;
    max_losses INTEGER := 0;
    trade_record RECORD;
BEGIN
    FOR trade_record IN
        SELECT final_pnl_pct
        FROM trade_setups
        WHERE symbol = p_symbol
        AND direction = p_direction
        AND webhook_source = p_webhook_source
        AND status = 'closed'
        ORDER BY created_at
    LOOP
        IF trade_record.final_pnl_pct > 0 THEN
            IF current_streak >= 0 THEN
                current_streak := current_streak + 1;
                max_wins := GREATEST(max_wins, current_streak);
            ELSE
                current_streak := 1;
            END IF;
        ELSIF trade_record.final_pnl_pct < 0 THEN
            IF current_streak <= 0 THEN
                current_streak := current_streak - 1;
                max_losses := GREATEST(max_losses, ABS(current_streak));
            ELSE
                current_streak := -1;
            END IF;
        END IF;
    END LOOP;

    RETURN QUERY SELECT max_wins, max_losses;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- Permissions (adjust based on your user setup)
-- ============================================
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO dashboard_user;
-- GRANT SELECT ON ALL VIEWS IN SCHEMA public TO dashboard_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO dashboard_user;