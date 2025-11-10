"""
Strategy Management API Routes

Endpoints for viewing and managing the 3-phase strategy system
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, tuple_, func, desc
from app.database.database import get_db
from app.database.models import TradeSetup
from app.database.strategy_models import StrategyPerformance, StrategySimulation
from app.services.strategy_selector import StrategySelector
from app.services.strategy_calculator import StrategyCalculator
from app.services.portfolio_simulator import PortfolioSimulator
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from functools import lru_cache
import time
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> Dict:
    """
    Strategy System Health Check
    
    Returns status of the 3-phase strategy system including:
    - Database connectivity
    - Number of active strategies
    - Number of simulations
    - Last update timestamp
    - System status (healthy/degraded/down)
    
    Returns:
        Dict with health metrics and status
    """
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }
        
        # Check 1: Database connectivity
        try:
            # Simple query to test DB connection
            result = await db.execute(select(StrategyPerformance).limit(1))
            result.scalar_one_or_none()
            health_status["checks"]["database"] = {
                "status": "up",
                "message": "Database connection OK"
            }
        except Exception as e:
            health_status["checks"]["database"] = {
                "status": "down",
                "message": f"Database error: {str(e)}"
            }
            health_status["status"] = "down"
            logger.error(f"Health check database error: {e}")
        
        # Check 2: Count active strategies
        try:
            result = await db.execute(
                select(StrategyPerformance).where(
                    StrategyPerformance.is_eligible_for_phase3 == True
                )
            )
            eligible_count = len(result.scalars().all())
            
            result_all = await db.execute(select(StrategyPerformance))
            total_count = len(result_all.scalars().all())
            
            health_status["checks"]["strategies"] = {
                "status": "ok" if total_count > 0 else "warning",
                "total_strategies": total_count,
                "eligible_for_phase3": eligible_count,
                "message": f"{eligible_count}/{total_count} strategies eligible for Phase III"
            }
            
            if total_count == 0:
                health_status["status"] = "warning" if health_status["status"] != "down" else "down"
                
        except Exception as e:
            health_status["checks"]["strategies"] = {
                "status": "error",
                "message": f"Strategy check error: {str(e)}"
            }
            logger.error(f"Health check strategy error: {e}")
        
        # Check 3: Count simulations
        try:
            result = await db.execute(select(StrategySimulation))
            sim_count = len(result.scalars().all())
            
            health_status["checks"]["simulations"] = {
                "status": "ok",
                "total_simulations": sim_count,
                "message": f"{sim_count} strategy simulations recorded"
            }
        except Exception as e:
            health_status["checks"]["simulations"] = {
                "status": "error",
                "message": f"Simulation check error: {str(e)}"
            }
            logger.error(f"Health check simulation error: {e}")
        
        # Check 4: Count baseline trades
        try:
            result = await db.execute(
                select(TradeSetup).where(
                    TradeSetup.risk_strategy == 'baseline',
                    TradeSetup.status == 'completed'
                )
            )
            baseline_count = len(result.scalars().all())
            
            health_status["checks"]["baseline_trades"] = {
                "status": "ok" if baseline_count >= 10 else "warning",
                "completed_trades": baseline_count,
                "message": f"{baseline_count} completed baseline trades"
            }
        except Exception as e:
            health_status["checks"]["baseline_trades"] = {
                "status": "error",
                "message": f"Baseline check error: {str(e)}"
            }
            logger.error(f"Health check baseline error: {e}")
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return {
            "status": "down",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


@router.get("/phase-status/{symbol}/{direction}/{webhook_source}")
async def get_phase_status(
    symbol: str,
    direction: str,
    webhook_source: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get Phase Status for Symbol/Direction/Webhook
    
    Returns the current phase (I/II/III) and strategy status for a specific
    symbol/direction/webhook combination.
    
    **Phases:**
    - **Phase I:** Data collection (0-9 baseline trades)
    - **Phase II:** Strategy optimization/paper trading (10+ baseline trades, testing 4 strategies)
    - **Phase III:** Live trading with best strategy (1+ eligible strategy)
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        direction: Trade direction ("LONG" or "SHORT")
        webhook_source: Source identifier (e.g., "tradingview", "manual")
        
    Returns:
        Dict containing:
        - phase: Current phase number ('I', 'II', or 'III')
        - phase_name: Human-readable phase name
        - baseline_completed: Number of completed baseline trades
        - best_strategy: Active strategy config (Phase III only)
        - all_strategies: Performance data for all 4 strategies
        
    Example Response:
        ```json
        {
            "phase": "III",
            "phase_name": "Live Trading",
            "baseline_completed": 25,
            "best_strategy": {
                "strategy_name": "strategy_B",
                "tp1_pct": 2.5,
                "sl_pct": -1.2,
                "performance": {"win_rate": 65.0, "risk_reward": 2.1}
            },
            "all_strategies": [...]
        }
        ```
    """
    phase_info = await StrategySelector.determine_trade_phase(
        db, symbol, direction, webhook_source
    )

    all_strategies = await StrategySelector.get_all_strategies_performance(
        db, symbol, direction, webhook_source
    )

    return {
        **phase_info,
        'all_strategies': all_strategies
    }


@router.get("/performance/{symbol}/{direction}/{webhook_source}")
async def get_strategy_performance(
    symbol: str,
    direction: str,
    webhook_source: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get Strategy Performance Metrics
    
    Returns detailed performance metrics for all 4 strategies (A, B, C, D)
    for a specific symbol/direction/webhook combination.
    
    **Strategies:**
    - **Strategy A (Conservative):** Quick exits, tight SL, high win rate
    - **Strategy B (Balanced):** Moderate targets with trailing stop
    - **Strategy C (Aggressive):** Wide SL, high targets, lower win rate
    - **Strategy D (Adaptive):** Dynamic based on volatility
    
    Args:
        symbol: Trading symbol
        direction: Trade direction
        webhook_source: Source identifier
        
    Returns:
        Dict containing array of strategy performance data including:
        - win_rate: Percentage of winning trades
        - risk_reward: Average win / average loss ratio
        - avg_duration_hours: Average trade duration
        - strategy_score: Composite performance score
        - is_eligible_phase3: Whether strategy meets Phase III requirements
        
    Status Codes:
        - 200: Success
        - 404: No strategy data (still in Phase I)
    """
    strategies = await StrategySelector.get_all_strategies_performance(
        db, symbol, direction, webhook_source
    )

    if not strategies:
        return {
            "message": "No strategy data yet - still in Phase I (baseline collection)",
            "strategies": []
        }

    return {"strategies": strategies}


@router.get("/simulations/{trade_id}")
async def get_trade_simulations(
    trade_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get Strategy Simulations for a Trade
    
    Returns simulated outcomes for all 4 strategies on a specific completed trade.
    Shows what would have happened if each strategy was applied to this trade.
    
    Args:
        trade_id: Database ID of the completed trade
        
    Returns:
        Dict containing:
        - trade_id: ID of the trade
        - simulations: Array of 4 simulation results (one per strategy)
          - strategy_name: Strategy identifier (A/B/C/D)
          - exit_reason: How strategy would exit (tp1/tp2/tp3/sl/trailing_sl)
          - pnl_pct: Simulated P&L percentage
          - pnl_usd: Simulated P&L in USD
          - duration_minutes: Estimated trade duration
          - tp1/tp2/tp3/sl: Strategy parameters used
          
    Example Response:
        ```json
        {
            "trade_id": 123,
            "simulations": [
                {
                    "strategy_name": "strategy_A",
                    "exit_reason": "tp1",
                    "pnl_pct": 1.5,
                    "pnl_usd": 150.0,
                    "duration_minutes": 45
                },
                ...
            ]
        }
        ```
    """
    result = await db.execute(
        select(StrategySimulation).where(
            StrategySimulation.trade_setup_id == trade_id
        )
    )
    sims = result.scalars().all()

    return {
        "trade_id": trade_id,
        "simulations": [
            {
                "strategy_name": s.strategy_name,
                "exit_reason": s.simulated_exit_reason,
                "pnl_pct": float(s.simulated_pnl_pct),
                "pnl_usd": float(s.simulated_pnl_usd),
                "duration_minutes": s.simulated_duration_minutes,
                "tp1": float(s.simulated_tp1_pct) if s.simulated_tp1_pct else None,
                "tp2": float(s.simulated_tp2_pct) if s.simulated_tp2_pct else None,
                "tp3": float(s.simulated_tp3_pct) if s.simulated_tp3_pct else None,
                "sl": float(s.simulated_sl_pct) if s.simulated_sl_pct else None,
                "trailing": s.trailing_enabled
            }
            for s in sims
        ]
    }


@router.get("/all-phases")
async def get_all_phases_summary(db: AsyncSession = Depends(get_db)):
    """
    Get All Phases Summary
    
    Returns a summary of all symbol/direction/webhook combinations and their
    current phase status. Useful for dashboard overview and monitoring.
    
    Returns:
        Dict containing:
        - summaries: Array of phase summaries
          - symbol: Trading symbol
          - direction: Trade direction
          - webhook_source: Source identifier
          - phase: Current phase ('I', 'II', or 'III')
          - phase_name: Human-readable phase name
          - baseline_completed: Number of completed baseline trades
          - best_strategy: Active strategy (Phase III only)
          - description: Phase description
          
    Example Response:
        ```json
        {
            "summaries": [
                {
                    "symbol": "BTCUSDT",
                    "direction": "LONG",
                    "webhook_source": "tradingview",
                    "phase": "III",
                    "phase_name": "Live Trading",
                    "baseline_completed": 30,
                    "best_strategy": {...}
                },
                {
                    "symbol": "ETHUSDT",
                    "direction": "SHORT",
                    "webhook_source": "manual",
                    "phase": "I",
                    "phase_name": "Data Collection",
                    "baseline_completed": 5
                }
            ]
        }
        ```
    """
    # Get all unique combinations (Query 1)
    result = await db.execute(
        select(
            TradeSetup.symbol,
            TradeSetup.direction,
            TradeSetup.webhook_source
        ).where(
            TradeSetup.risk_strategy == 'baseline',
            TradeSetup.status == 'completed'
        ).distinct()
    )
    combinations = result.all()

    if not combinations:
        return {"summaries": []}

    # Batch load baseline counts for all combinations (Query 2)
    baseline_counts_result = await db.execute(
        select(
            TradeSetup.symbol,
            TradeSetup.direction,
            TradeSetup.webhook_source,
            func.count(TradeSetup.id).label('count')
        ).where(
            TradeSetup.risk_strategy == 'baseline',
            TradeSetup.status == 'completed',
            tuple_(
                TradeSetup.symbol,
                TradeSetup.direction,
                TradeSetup.webhook_source
            ).in_(combinations)
        ).group_by(
            TradeSetup.symbol,
            TradeSetup.direction,
            TradeSetup.webhook_source
        )
    )

    # Create lookup dict for baseline counts
    baseline_counts = {}
    for row in baseline_counts_result:
        key = (row.symbol, row.direction, row.webhook_source)
        baseline_counts[key] = row.count

    # Batch load all strategy performances for all combinations (Query 3)
    all_performances_result = await db.execute(
        select(StrategyPerformance).where(
            tuple_(
                StrategyPerformance.symbol,
                StrategyPerformance.direction,
                StrategyPerformance.webhook_source
            ).in_(combinations),
            StrategyPerformance.is_eligible_for_phase3 == True
        ).order_by(StrategyPerformance.strategy_score.desc())
    )

    # Group performances by combination
    perf_by_combo = {}
    for perf in all_performances_result.scalars():
        key = (perf.symbol, perf.direction, perf.webhook_source)
        if key not in perf_by_combo:
            perf_by_combo[key] = []
        perf_by_combo[key].append(perf)

    # Process all combinations without additional DB queries
    summaries = []
    for symbol, direction, webhook_source in combinations:
        key = (symbol, direction, webhook_source)
        baseline_count = baseline_counts.get(key, 0)
        performances = perf_by_combo.get(key, [])

        # Determine phase based on baseline count and performances
        if baseline_count < 10:
            # Phase I: Data collection
            phase_info = {
                'phase': 'I',
                'phase_name': 'Data Collection',
                'baseline_completed': baseline_count,
                'baseline_needed': 10,
                'best_strategy': None,
                'description': 'Collecting baseline data with 999999 TP/SL'
            }
        elif performances:
            # Phase III: Live trading with best strategy
            # Apply same tie-breaking logic as StrategySelector.get_best_strategy
            top_score = float(performances[0].strategy_score)
            tied_strategies = [
                p for p in performances
                if abs(float(p.strategy_score) - top_score) < 0.001
            ]

            if len(tied_strategies) > 1:
                # Sort by: win_rate DESC, duration ASC, name ASC
                tied_strategies.sort(
                    key=lambda p: (
                        -float(p.win_rate),
                        float(p.avg_duration_hours),
                        p.strategy_name
                    )
                )

            best = tied_strategies[0] if len(tied_strategies) > 1 else performances[0]

            best_strategy = {
                'strategy_name': best.strategy_name,
                'tp1_pct': float(best.current_tp1_pct) if best.current_tp1_pct else None,
                'tp2_pct': float(best.current_tp2_pct) if best.current_tp2_pct else None,
                'tp3_pct': float(best.current_tp3_pct) if best.current_tp3_pct else None,
                'sl_pct': float(best.current_sl_pct) if best.current_sl_pct else None,
                'trailing_enabled': best.current_trailing_enabled,
                'trailing_activation': float(best.current_trailing_activation) if best.current_trailing_activation else None,
                'trailing_distance': float(best.current_trailing_distance) if best.current_trailing_distance else None,
                'performance': {
                    'win_rate': float(best.win_rate),
                    'risk_reward': float(best.risk_reward),
                    'strategy_score': float(best.strategy_score),
                    'trades_analyzed': best.trades_analyzed
                }
            }

            phase_info = {
                'phase': 'III',
                'phase_name': 'Live Trading',
                'baseline_completed': baseline_count,
                'best_strategy': best_strategy,
                'description': f"Using {best_strategy['strategy_name']} (RR={best_strategy['performance']['risk_reward']:.2f})"
            }
        else:
            # Phase II: Strategy optimization (paper trading)
            phase_info = {
                'phase': 'II',
                'phase_name': 'Strategy Optimization',
                'baseline_completed': baseline_count,
                'best_strategy': None,
                'description': 'Paper trading, testing all 4 strategies'
            }

        summaries.append({
            'symbol': symbol,
            'direction': direction,
            'webhook_source': webhook_source,
            **phase_info
        })

    return {"summaries": summaries}


@router.post("/regenerate/{symbol}/{direction}/{webhook_source}")
async def regenerate_strategies(
    symbol: str,
    direction: str,
    webhook_source: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Regenerate Strategies
    
    Manually triggers strategy regeneration for a symbol/direction/webhook combination.
    Recalculates all 4 strategies based on latest baseline data.
    
    **Use Cases:**
    - After accumulating more baseline trades
    - When baseline data was corrected/updated
    - Manual testing and debugging
    - Forcing strategy refresh outside automatic regeneration cycle
    
    **Note:** Strategies automatically regenerate every 20 completed baseline trades.
    
    Args:
        symbol: Trading symbol
        direction: Trade direction
        webhook_source: Source identifier
        
    Returns:
        Dict containing:
        - message: Success message
        - strategies: Array of 4 newly generated strategies
        
    Raises:
        400: Insufficient baseline data (need 10+ completed trades)
        500: Strategy generation error
        
    Example Response:
        ```json
        {
            "message": "Successfully generated 4 strategies",
            "strategies": [
                {
                    "strategy_name": "strategy_A",
                    "tp1_pct": 1.5,
                    "sl_pct": -0.8,
                    "description": "Conservative: Quick exits, tight SL"
                },
                ...
            ]
        }
        ```
    """
    from app.services.strategy_simulator import StrategySimulator
    from sqlalchemy.orm import selectinload
    
    try:
        # Generate new strategies
        strategies = await StrategyCalculator.generate_all_strategies(
            db, symbol, direction, webhook_source
        )

        if not strategies:
            raise HTTPException(
                status_code=400,
                detail="Insufficient baseline data (need 10 completed trades)"
            )

        logger.info(f"✅ Generated {len(strategies)} strategies for {symbol} {direction} {webhook_source}")

        # Backtest new strategies against all past completed trades
        result = await db.execute(
            select(TradeSetup)
            .where(
                TradeSetup.symbol == symbol,
                TradeSetup.direction == direction,
                TradeSetup.webhook_source == webhook_source,
                TradeSetup.status == 'completed'
            )
            .options(selectinload(TradeSetup.milestones))
            .order_by(TradeSetup.completed_at)
        )
        past_trades = result.scalars().all()

        logger.info(f"🔄 Backtesting {len(strategies)} strategies against {len(past_trades)} past trades")

        backtested_count = 0
        for trade in past_trades:
            try:
                # Simulate all strategies for this trade
                simulations = await StrategySimulator.simulate_all_strategies_for_trade(
                    db, trade, strategies
                )
                
                if simulations:
                    # Save simulations to DB first
                    for sim in simulations:
                        db.add(sim)
                    await db.flush()  # Flush so performance update can find them
                    
                    # Update performance metrics for each strategy
                    for sim in simulations:
                        await StrategySimulator.update_strategy_performance(
                            db, symbol, direction, webhook_source, sim.strategy_name
                        )
                    
                    backtested_count += 1
                    
            except Exception as e:
                logger.error(f"Error backtesting trade {trade.id}: {e}")
                continue

        await db.commit()
        logger.info(f"✅ Backtesting complete: {backtested_count} trades processed")

        return {
            "message": f"Successfully generated {len(strategies)} strategies",
            "strategies": strategies,
            "backtested_trades": backtested_count
        }

    except Exception as e:
        logger.error(f"Error regenerating strategies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tp-sl-analysis")
async def get_tp_sl_hit_rates(
    symbol: Optional[str] = None,
    direction: Optional[str] = None,
    webhook_source: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    TP/SL Hit Rate Analysis

    Analyzes historical trades to show what percentage would have hit
    various TP and SL levels. Helps optimize strategy parameters.

    **Query Parameters:**
    - symbol (optional): Filter by specific symbol (e.g., "BTCUSDT.P")
    - direction (optional): Filter by direction ("LONG" or "SHORT")
    - webhook_source (optional): Filter by webhook source (e.g., "ADX1m")

    **Returns:**
    - TP hit rates for levels: 0.5%, 0.75%, 1%, 1.25%, 1.5%, 2%, 2.5%, 3%, 4%, 5%, 7.5%, 10%, 15%
    - SL hit rates for levels: 0.5%, 0.75%, 1%, 1.25%, 1.5%, 2%, 2.5%, 3%, 4%, 5%, 7.5%, 10%, 15%, 20%
    - Optimal TP/SL recommendations based on hit rates
    - Chart-ready data for visualization

    **Example:**
    ```
    GET /api/strategies/tp-sl-analysis?symbol=AIAUSDT.P&direction=LONG
    ```

    **Use Cases:**
    - Understand which TP levels are realistic for a symbol
    - See which SL levels provide good protection
    - Validate grid search results
    - Optimize strategy parameters based on actual market behavior
    """
    from app.services.tp_sl_analyzer import TPSLAnalyzer

    try:
        analysis = await TPSLAnalyzer.analyze_hit_rates(
            db,
            symbol=symbol,
            direction=direction,
            webhook_source=webhook_source
        )

        return analysis

    except Exception as e:
        logger.error(f"Error analyzing TP/SL hit rates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio-simulation")
async def get_portfolio_simulation(
    symbol: Optional[str] = None,
    direction: Optional[str] = None,
    webhook_source: Optional[str] = None,
    starting_capital: float = 100000.0,
    risk_pct: float = 0.1,
    db: AsyncSession = Depends(get_db)
):
    """
    Portfolio Performance Simulation
    
    Simulates how each strategy would perform with a real portfolio over time.
    Shows account balance growth/loss assuming position sizing based on risk %.
    
    **Key Assumptions:**
    - Starting capital: $100,000 (configurable)
    - Risk per trade: 0.1% of current balance (configurable)
    - Leverage already factored into strategy PnL%
    - Compounds wins/losses into next trade
    
    **Query Parameters:**
    - symbol (optional): Filter by specific symbol
    - direction (optional): Filter by direction (LONG/SHORT)
    - webhook_source (optional): Filter by webhook source
    - starting_capital (optional): Starting balance in USD (default: 100000)
    - risk_pct (optional): % of balance to risk per trade (default: 0.1)
    
    **Returns:**
    For each strategy:
    - Final balance & total return %
    - Max balance & max drawdown %
    - Win rate, wins/losses, total trades
    - Win/loss streaks
    - Balance curve (chronological balance snapshots)
    
    **Example:**
    ```
    GET /api/strategies/portfolio-simulation?symbol=AIAUSDT.P&direction=LONG
    GET /api/strategies/portfolio-simulation?starting_capital=50000&risk_pct=0.2
    ```
    
    **Use Cases:**
    - See real portfolio growth potential
    - Compare strategies by actual $ performance
    - Understand drawdown risk
    - Visualize balance curves over time
    - Focus on % returns (scalable to any account size)
    """
    try:
        simulation = await PortfolioSimulator.simulate_portfolio_performance(
            db,
            symbol=symbol,
            direction=direction,
            webhook_source=webhook_source,
            starting_capital=starting_capital,
            risk_pct=risk_pct
        )
        
        return simulation
        
    except Exception as e:
        logger.error(f"Error simulating portfolio performance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Simple time-based cache
_cache = {}
_cache_timestamps = {}
CACHE_TTL = 300  # 5 minutes


async def get_cached_or_compute(cache_key: str, compute_func, ttl: int = CACHE_TTL):
    """Simple time-based cache for async functions"""
    now = time.time()
    if cache_key in _cache and cache_key in _cache_timestamps:
        if now - _cache_timestamps[cache_key] < ttl:
            return _cache[cache_key]

    # Compute and cache
    result = await compute_func()
    _cache[cache_key] = result
    _cache_timestamps[cache_key] = now
    return result


@router.get("/dashboard-overview")
async def get_dashboard_overview(db: AsyncSession = Depends(get_db)) -> Dict:
    """
    Dashboard Overview - Top Performers (Cached 5 minutes)

    Returns:
    - Best strategy overall
    - Best asset
    - Best webhook source
    - Breakeven A/B test results
    """

    async def compute_overview():
        # Get all strategy performance data
        result = await db.execute(
            select(StrategyPerformance)
            .where(StrategyPerformance.trades_analyzed >= 2)  # Min 2 trades for early data
            .order_by(desc(StrategyPerformance.total_simulated_pnl))
        )
        all_strategies = result.scalars().all()

        if not all_strategies:
            return {
                "best_strategy": None,
                "best_asset": None,
                "best_source": None,
                "breakeven_test": None
            }

        # Best strategy
        best_strat = max(all_strategies, key=lambda x: float(x.total_simulated_pnl or 0))

        # Best asset (group by symbol)
        asset_totals = {}
        for strat in all_strategies:
            key = f"{strat.symbol}_{strat.direction}"
            if key not in asset_totals:
                asset_totals[key] = {
                    "symbol": strat.symbol,
                    "direction": strat.direction,
                    "total_pnl": 0,
                    "trades": 0
                }
            asset_totals[key]["total_pnl"] += float(strat.total_simulated_pnl or 0)
            asset_totals[key]["trades"] += strat.trades_analyzed

        best_asset = max(asset_totals.values(), key=lambda x: x["total_pnl"]) if asset_totals else None

        # Best source (group by webhook_source)
        source_totals = {}
        for strat in all_strategies:
            if strat.webhook_source not in source_totals:
                source_totals[strat.webhook_source] = {
                    "source": strat.webhook_source,
                    "total_pnl": 0,
                    "trades": 0
                }
            source_totals[strat.webhook_source]["total_pnl"] += float(strat.total_simulated_pnl or 0)
            source_totals[strat.webhook_source]["trades"] += strat.trades_analyzed

        best_source = max(source_totals.values(), key=lambda x: x["total_pnl"]) if source_totals else None

        # Breakeven A/B test: Compare A vs E, C vs F
        breakeven_test = {}
        for combo_key in set((s.symbol, s.direction, s.webhook_source) for s in all_strategies):
            symbol, direction, webhook = combo_key
            combo_strats = [s for s in all_strategies
                            if s.symbol == symbol and s.direction == direction and s.webhook_source == webhook]

            strat_a = next((s for s in combo_strats if s.strategy_name == 'strategy_A'), None)
            strat_e = next((s for s in combo_strats if s.strategy_name == 'strategy_E'), None)
            strat_c = next((s for s in combo_strats if s.strategy_name == 'strategy_C'), None)
            strat_f = next((s for s in combo_strats if s.strategy_name == 'strategy_F'), None)

            if strat_a and strat_e:
                key = f"{symbol}_{direction}"
                breakeven_test[f"{key}_A_vs_E"] = {
                    "asset": f"{symbol} {direction}",
                    "strategy_a_pnl": float(strat_a.total_simulated_pnl or 0) / strat_a.trades_analyzed if strat_a.trades_analyzed > 0 else 0,
                    "strategy_e_pnl": float(strat_e.total_simulated_pnl or 0) / strat_e.trades_analyzed if strat_e.trades_analyzed > 0 else 0,
                    "winner": "E" if (strat_e.total_simulated_pnl or 0) > (strat_a.total_simulated_pnl or 0) else "A"
                }

            if strat_c and strat_f:
                key = f"{symbol}_{direction}"
                breakeven_test[f"{key}_C_vs_F"] = {
                    "asset": f"{symbol} {direction}",
                    "strategy_c_pnl": float(strat_c.total_simulated_pnl or 0) / strat_c.trades_analyzed if strat_c.trades_analyzed > 0 else 0,
                    "strategy_f_pnl": float(strat_f.total_simulated_pnl or 0) / strat_f.trades_analyzed if strat_f.trades_analyzed > 0 else 0,
                    "winner": "F" if (strat_f.total_simulated_pnl or 0) > (strat_c.total_simulated_pnl or 0) else "C"
                }

        return {
            "best_strategy": {
                "name": best_strat.strategy_name,
                "symbol": best_strat.symbol,
                "direction": best_strat.direction,
                "avg_pnl": float(best_strat.total_simulated_pnl or 0) / best_strat.trades_analyzed if best_strat.trades_analyzed > 0 else 0,
                "win_rate": float(best_strat.win_rate or 0),
                "trades": best_strat.trades_analyzed
            },
            "best_asset": best_asset,
            "best_source": best_source,
            "breakeven_test": breakeven_test
        }

    cache_key = "dashboard_overview"
    return await get_cached_or_compute(cache_key, compute_overview)


@router.get("/recent-trades-overview")
async def get_recent_trades_overview(
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
) -> Dict:
    """
    Recent Trades Overview - Lazy Load (Cached 2 minutes)

    Returns list of recent completed trades with basic info.
    Full strategy comparison loaded separately when card expanded.
    """

    async def compute_recent():
        result = await db.execute(
            select(TradeSetup)
            .where(TradeSetup.status == 'completed')
            .order_by(desc(TradeSetup.completed_at))
            .limit(limit)
        )
        trades = result.scalars().all()

        return [
            {
                "id": t.id,
                "trade_identifier": t.trade_identifier,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": float(t.entry_price or 0),
                "final_pnl_pct": float(t.final_pnl_pct or 0),
                "max_profit_pct": float(t.max_profit_pct or 0),
                "max_drawdown_pct": float(t.max_drawdown_pct or 0),
                "completed_at": t.completed_at.isoformat() if t.completed_at else None
            }
            for t in trades
        ]

    cache_key = f"recent_trades_{limit}"
    return {"trades": await get_cached_or_compute(cache_key, compute_recent, ttl=120)}
