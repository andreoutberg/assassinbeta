"""
Strategy Simulator - Simulates strategy outcomes against actual trade price movement

Takes a completed trade's MAE/MFE data and simulates what would have happened
with each strategy's TP/SL/trailing configuration.
"""
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import TradeSetup, TradeMilestones
from app.database.strategy_models import StrategySimulation, StrategyPerformance
from app.config.phase_config import PhaseConfig
from app.utils.exceptions import SimulationError, InvalidTradeDataError
from app.models.strategy_types import StrategyConfig, SimulationResult
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class StrategySimulator:
    """Simulates strategy performance against actual trades"""

    @staticmethod
    def simulate_strategy_outcome(
        trade: TradeSetup,
        strategy_config: StrategyConfig
    ) -> SimulationResult:
        """
        Simulate how a strategy would have exited the trade using chronological replay
        
        Args:
            trade: Completed TradeSetup with milestones data
            strategy_config: Strategy parameters (TP/SL/trailing)
            
        Returns:
            Dict with simulated exit price, reason, PnL, duration
            
        Raises:
            InvalidTradeDataError: If trade data is invalid/incomplete
            SimulationError: If simulation calculation fails
            
        CHRONOLOGICAL REPLAY APPROACH:
        ===============================
        1. Get all milestone events sorted by timestamp
        2. Replay events in order, checking if each matches a TP/SL/trailing condition
        3. First matching event determines exit
        4. Accurate timestamps mean accurate duration calculation
        5. Handles trailing stops with high-water mark tracking
        """
        # Validate trade data
        if not trade.entry_price:
            raise InvalidTradeDataError(trade.id, "Missing entry_price")
        if not trade.direction:
            raise InvalidTradeDataError(trade.id, "Missing direction")
        
        # Get milestone record (if available)
        # For backward compatibility, fall back to MAE/MFE if milestones missing
        milestones = None
        if hasattr(trade, 'milestones') and trade.milestones:
            milestones = trade.milestones[0] if isinstance(trade.milestones, list) else trade.milestones
        
        entry_price = float(trade.entry_price)
        direction = trade.direction
        
        logger.debug(
            f"Simulating {strategy_config.get('strategy_name')} for trade {trade.id} "
            f"(using {'milestones' if milestones else 'MAE/MFE fallback'})"
        )

        # Extract strategy parameters
        tp1_pct = strategy_config.get('tp1_pct')
        tp2_pct = strategy_config.get('tp2_pct')
        tp3_pct = strategy_config.get('tp3_pct')
        sl_pct = strategy_config.get('sl_pct')
        trailing_enabled = strategy_config.get('trailing_enabled', False)
        trailing_activation = strategy_config.get('trailing_activation')
        trailing_distance = strategy_config.get('trailing_distance')
        breakeven_trigger_pct = strategy_config.get('breakeven_trigger_pct')

        # --- CHRONOLOGICAL REPLAY ---
        if milestones:
            result = StrategySimulator._simulate_with_chronology(
                trade, milestones, strategy_config,
                tp1_pct, tp2_pct, tp3_pct, sl_pct,
                trailing_enabled, trailing_activation, trailing_distance,
                breakeven_trigger_pct
            )
        else:
            # Fallback to old MAE/MFE estimation
            logger.warning(f"Trade {trade.id} missing milestones - using MAE/MFE fallback")
            result = StrategySimulator._simulate_with_mae_mfe(
                trade, strategy_config,
                tp1_pct, tp2_pct, tp3_pct, sl_pct,
                trailing_enabled, trailing_activation, trailing_distance,
                breakeven_trigger_pct
            )
        
        logger.debug(
            f"Simulation result for trade {trade.id}: "
            f"exit={result['exit_reason']}, pnl={result['pnl_pct']:.2f}%"
        )
        return result

    @staticmethod
    def _simulate_with_chronology(
        trade: TradeSetup,
        milestones: TradeMilestones,
        strategy_config: StrategyConfig,
        tp1_pct, tp2_pct, tp3_pct, sl_pct,
        trailing_enabled, trailing_activation, trailing_distance,
        breakeven_trigger_pct
    ) -> SimulationResult:
        """
        Simulate using chronological milestone replay - ACCURATE METHOD
        
        Replays all milestone events in timestamp order to determine which
        TP/SL condition was hit first.
        """
        entry_price = float(trade.entry_price)
        direction = trade.direction
        
        # Get all milestone events in chronological order
        events = milestones.get_chronological_events()
        
        if not events:
            logger.warning(f"Trade {trade.id} has milestone record but no events - using fallback")
            return StrategySimulator._simulate_with_mae_mfe(
                trade, strategy_config, tp1_pct, tp2_pct, tp3_pct, sl_pct,
                trailing_enabled, trailing_activation, trailing_distance,
                breakeven_trigger_pct
            )
        
        # State tracking for trailing stop and breakeven
        trailing_activated = False
        highest_profit_reached = 0
        trailing_stop_level = None
        breakeven_activated = False
        effective_sl = sl_pct  # Will change to 0% if breakeven triggers

        # Partial exit tracking for breakeven strategies with TP2
        tp1_hit = False
        tp1_timestamp = None
        tp1_exit_pct = 0.5  # Exit 50% at TP1 for breakeven strategies

        # Replay events chronologically
        for timestamp, event_type, pnl_pct in events:
            
            # Update trailing stop state
            if event_type == 'profit' and pnl_pct > highest_profit_reached:
                highest_profit_reached = pnl_pct

                # Check if breakeven should activate
                if breakeven_trigger_pct and pnl_pct >= breakeven_trigger_pct:
                    if not breakeven_activated:
                        logger.debug(f"Breakeven activated at {pnl_pct}% for trade {trade.id} (trigger={breakeven_trigger_pct}%)")
                        breakeven_activated = True
                        effective_sl = 0.0  # Move SL to breakeven

                # Check if trailing should activate
                if trailing_enabled and trailing_activation and pnl_pct >= trailing_activation:
                    if not trailing_activated:
                        logger.debug(f"Trailing stop activated at {pnl_pct}% for trade {trade.id}")
                        trailing_activated = True

                    # Update trailing stop level
                    trailing_stop_level = highest_profit_reached - abs(trailing_distance or 0)
            
            # Check exit conditions in priority order

            # 1. Check if SL hit (use effective_sl which may be 0% if breakeven triggered)
            if effective_sl is not None and pnl_pct <= effective_sl:
                duration_minutes = int((timestamp - milestones.entry_at).total_seconds() / 60)

                # Check if TP1 was hit first (partial exit scenario)
                if tp1_hit:
                    # Weighted average: 50% exited at TP1, 50% at SL/breakeven
                    weighted_pnl = (tp1_exit_pct * tp1_pct) + ((1 - tp1_exit_pct) * effective_sl)
                    exit_reason = 'tp1+breakeven' if breakeven_activated and effective_sl == 0.0 else 'tp1+sl'
                    logger.debug(f"Partial exits: {tp1_exit_pct*100}% @ TP1({tp1_pct}%) + {(1-tp1_exit_pct)*100}% @ SL/BE({effective_sl}%) = {weighted_pnl}%")
                    return StrategySimulator._build_result(
                        entry_price, direction, trade, weighted_pnl, exit_reason, duration_minutes
                    )
                else:
                    # Normal SL/breakeven exit
                    exit_reason = 'breakeven' if breakeven_activated and effective_sl == 0.0 else 'sl'
                    return StrategySimulator._build_result(
                        entry_price, direction, trade, effective_sl, exit_reason, duration_minutes
                    )
            
            # 2. Check if trailing stop hit (only after activation)
            if trailing_activated and trailing_stop_level:
                if pnl_pct <= trailing_stop_level:
                    duration_minutes = int((timestamp - milestones.entry_at).total_seconds() / 60)
                    return StrategySimulator._build_result(
                        entry_price, direction, trade, trailing_stop_level, 'trailing_sl', duration_minutes
                    )
            
            # 3. Check TP levels (highest to lowest priority)
            if tp3_pct and pnl_pct >= tp3_pct:
                duration_minutes = int((timestamp - milestones.entry_at).total_seconds() / 60)
                return StrategySimulator._build_result(
                    entry_price, direction, trade, tp3_pct, 'tp3', duration_minutes
                )
            
            if tp2_pct and pnl_pct >= tp2_pct:
                duration_minutes = int((timestamp - milestones.entry_at).total_seconds() / 60)
                # Check if TP1 was hit (partial exit scenario)
                if tp1_hit:
                    # Weighted average: 50% exited at TP1, 50% at TP2
                    weighted_pnl = (tp1_exit_pct * tp1_pct) + ((1 - tp1_exit_pct) * tp2_pct)
                    logger.debug(f"Partial exits: {tp1_exit_pct*100}% @ TP1({tp1_pct}%) + {(1-tp1_exit_pct)*100}% @ TP2({tp2_pct}%) = {weighted_pnl}%")
                    return StrategySimulator._build_result(
                        entry_price, direction, trade, weighted_pnl, 'tp1+tp2', duration_minutes
                    )
                else:
                    # Normal TP2 exit
                    return StrategySimulator._build_result(
                        entry_price, direction, trade, tp2_pct, 'tp2', duration_minutes
                    )
            
            if tp1_pct and pnl_pct >= tp1_pct and not tp1_hit:
                # Check if this is a breakeven strategy with TP2 (partial exit)
                if breakeven_trigger_pct and tp2_pct:
                    # Partial exit at TP1 - mark it and continue to TP2
                    tp1_hit = True
                    tp1_timestamp = timestamp
                    logger.debug(f"TP1 hit at {tp1_pct}% for trade {trade.id} - partial exit, continuing to TP2")
                    # Don't exit - continue loop to check TP2
                elif not trailing_activated:
                    # Normal strategy - full exit at TP1
                    duration_minutes = int((timestamp - milestones.entry_at).total_seconds() / 60)
                    return StrategySimulator._build_result(
                        entry_price, direction, trade, tp1_pct, 'tp1', duration_minutes
                    )
        
        # No TP/SL hit - check time exit or early close
        if trade.completed_at:
            duration_hours = (trade.completed_at - trade.entry_timestamp).total_seconds() / 3600
            duration_minutes = int(duration_hours * 60)
            
            if duration_hours >= 24:
                # 24h time exit
                final_pnl = float(trade.final_pnl_pct or milestones.max_profit_pct or 0)

                # Check if TP1 was hit (partial exit scenario)
                if tp1_hit:
                    weighted_pnl = (tp1_exit_pct * tp1_pct) + ((1 - tp1_exit_pct) * final_pnl)
                    logger.debug(f"Partial exits: {tp1_exit_pct*100}% @ TP1({tp1_pct}%) + {(1-tp1_exit_pct)*100}% @ time_exit({final_pnl}%) = {weighted_pnl}%")
                    return StrategySimulator._build_result(
                        entry_price, direction, trade, weighted_pnl, 'tp1+time_exit', duration_minutes
                    )
                else:
                    return StrategySimulator._build_result(
                        entry_price, direction, trade, final_pnl, 'time_exit', duration_minutes
                    )
            else:
                # Early manual close
                final_pnl = float(trade.final_pnl_pct or 0)

                # Check if TP1 was hit (partial exit scenario)
                if tp1_hit:
                    weighted_pnl = (tp1_exit_pct * tp1_pct) + ((1 - tp1_exit_pct) * final_pnl)
                    logger.debug(f"Partial exits: {tp1_exit_pct*100}% @ TP1({tp1_pct}%) + {(1-tp1_exit_pct)*100}% @ early_close({final_pnl}%) = {weighted_pnl}%")
                    return StrategySimulator._build_result(
                        entry_price, direction, trade, weighted_pnl, 'tp1+early_close', duration_minutes
                    )
                else:
                    return StrategySimulator._build_result(
                        entry_price, direction, trade, final_pnl, 'early_close', duration_minutes
                    )
        
        # Fallback - should not reach here
        logger.error(f"Simulation reached end without exit for trade {trade.id}")
        raise SimulationError(f"Unable to determine exit for trade {trade.id}")

    @staticmethod
    def _simulate_with_mae_mfe(
        trade: TradeSetup,
        strategy_config: StrategyConfig,
        tp1_pct, tp2_pct, tp3_pct, sl_pct,
        trailing_enabled, trailing_activation, trailing_distance,
        breakeven_trigger_pct
    ) -> SimulationResult:
        """
        Fallback simulation using MAE/MFE - LEGACY METHOD (less accurate)
        
        Assumes drawdown happens before profit (SL checked first).
        Used for backward compatibility or when milestones missing.
        """
        entry_price = float(trade.entry_price)
        direction = trade.direction
        max_profit_pct = float(trade.max_profit_pct or 0)
        max_drawdown_pct = float(trade.max_drawdown_pct or 0)

        # Determine if this is a breakeven strategy with partial exits
        tp1_exit_pct = 0.5  # Exit 50% at TP1
        tp1_hit = breakeven_trigger_pct and tp2_pct and max_profit_pct >= tp1_pct

        # Determine effective SL based on breakeven trigger
        breakeven_activated = breakeven_trigger_pct and max_profit_pct >= breakeven_trigger_pct
        effective_sl = 0.0 if breakeven_activated else sl_pct

        # Check SL first (assume drawdown happened before profit)
        # CRITICAL FIX: Skip SL check for baseline trades (SL <= -999999%)
        # Baseline trades have no real stop loss and should use MFE as exit
        is_baseline_trade = sl_pct is not None and sl_pct <= -999999

        if not is_baseline_trade and effective_sl is not None and abs(max_drawdown_pct) >= abs(effective_sl):
            simulated_duration = int((trade.completed_at - trade.entry_timestamp).total_seconds() / 60 * 0.3) if trade.completed_at else 0

            # Check if TP1 was hit first (partial exit scenario)
            if tp1_hit:
                weighted_pnl = (tp1_exit_pct * tp1_pct) + ((1 - tp1_exit_pct) * effective_sl)
                exit_reason = 'tp1+breakeven' if breakeven_activated and effective_sl == 0.0 else 'tp1+sl'
                return StrategySimulator._build_result(
                    entry_price, direction, trade, weighted_pnl, exit_reason, simulated_duration
                )
            else:
                exit_reason = 'breakeven' if breakeven_activated and effective_sl == 0.0 else 'sl'
                return StrategySimulator._build_result(
                    entry_price, direction, trade, effective_sl, exit_reason, simulated_duration
                )

        # Check TPs
        if tp3_pct and max_profit_pct >= tp3_pct:
            simulated_duration = int((trade.completed_at - trade.entry_timestamp).total_seconds() / 60 * 0.9) if trade.completed_at else 0
            return StrategySimulator._build_result(
                entry_price, direction, trade, tp3_pct, 'tp3', simulated_duration
            )

        if tp2_pct and max_profit_pct >= tp2_pct:
            simulated_duration = int((trade.completed_at - trade.entry_timestamp).total_seconds() / 60 * 0.7) if trade.completed_at else 0

            # Check if TP1 was hit (partial exit scenario)
            if tp1_hit:
                weighted_pnl = (tp1_exit_pct * tp1_pct) + ((1 - tp1_exit_pct) * tp2_pct)
                return StrategySimulator._build_result(
                    entry_price, direction, trade, weighted_pnl, 'tp1+tp2', simulated_duration
                )
            else:
                return StrategySimulator._build_result(
                    entry_price, direction, trade, tp2_pct, 'tp2', simulated_duration
                )
        
        if tp1_pct and max_profit_pct >= tp1_pct:
            # Check if trailing would have been activated
            if trailing_enabled and trailing_activation and max_profit_pct >= trailing_activation:
                trailing_exit = max(tp1_pct, max_profit_pct - abs(trailing_distance or 0))
                simulated_duration = int((trade.completed_at - trade.entry_timestamp).total_seconds() / 60 * 0.8) if trade.completed_at else 0
                return StrategySimulator._build_result(
                    entry_price, direction, trade, trailing_exit, 'trailing_sl', simulated_duration
                )
            else:
                simulated_duration = int((trade.completed_at - trade.entry_timestamp).total_seconds() / 60 * 0.5) if trade.completed_at else 0
                return StrategySimulator._build_result(
                    entry_price, direction, trade, tp1_pct, 'tp1', simulated_duration
                )
        
        # Check time exit or early close
        if trade.completed_at:
            duration_hours = (trade.completed_at - trade.entry_timestamp).total_seconds() / 3600
            duration_minutes = int(duration_hours * 60)

            # For baseline trades without TPs hit, use MFE as exit
            if is_baseline_trade and not tp1_hit:
                # Baseline trades exit at their max favorable excursion (MFE)
                final_pnl = max_profit_pct
                return StrategySimulator._build_result(
                    entry_price, direction, trade, final_pnl, 'baseline_mfe', duration_minutes
                )

            if duration_hours >= 24:
                final_pnl = float(trade.final_pnl_pct or max_profit_pct)
                return StrategySimulator._build_result(
                    entry_price, direction, trade, final_pnl, 'time_exit', duration_minutes
                )
            else:
                final_pnl = float(trade.final_pnl_pct or 0)
                return StrategySimulator._build_result(
                    entry_price, direction, trade, final_pnl, 'early_close', duration_minutes
                )
        
        # Fallback
        logger.error(f"MAE/MFE simulation reached end without exit for trade {trade.id}")
        raise SimulationError(f"Unable to determine exit for trade {trade.id}")

    @staticmethod
    def _build_result(entry_price: float, direction: str, trade: TradeSetup,
                      exit_pnl: float, exit_reason: str, duration_minutes: int) -> SimulationResult:
        """Helper to build standardized simulation result"""
        # Calculate exit price
        if direction == "LONG":
            exit_price = entry_price * (1 + exit_pnl / 100)
        else:  # SHORT
            exit_price = entry_price * (1 - exit_pnl / 100)

        # Calculate P&L in USD
        notional = float(trade.notional_position_usd or 0)
        exit_pnl_usd = (exit_pnl / 100) * notional

        return SimulationResult(
            exit_price=round(exit_price, 8),
            exit_reason=exit_reason,
            pnl_pct=round(exit_pnl, 4),
            pnl_usd=round(exit_pnl_usd, 2),
            duration_minutes=duration_minutes
        )

    @classmethod
    async def simulate_all_strategies_for_trade(
        cls,
        db: AsyncSession,
        trade: TradeSetup,
        strategies: List[StrategyConfig]
    ) -> List[StrategySimulation]:
        """
        Simulate all 4 strategies against a completed trade

        Args:
            trade: Completed TradeSetup
            strategies: List of 4 strategy configs

        Returns:
            List of StrategySimulation records (not yet saved to DB)
        """
        simulations = []
        failed_simulations = []

        for strategy_config in strategies:
            try:
                # Run simulation
                result = cls.simulate_strategy_outcome(trade, strategy_config)

                # Create simulation record
                sim = StrategySimulation(
                trade_setup_id=trade.id,
                strategy_name=strategy_config['strategy_name'],
                simulated_tp1_pct=strategy_config.get('tp1_pct'),
                simulated_tp2_pct=strategy_config.get('tp2_pct'),
                simulated_tp3_pct=strategy_config.get('tp3_pct'),
                simulated_sl_pct=strategy_config.get('sl_pct'),
                trailing_enabled=strategy_config.get('trailing_enabled', False),
                trailing_activation_pct=strategy_config.get('trailing_activation'),
                trailing_distance_pct=strategy_config.get('trailing_distance'),
                simulated_exit_price=Decimal(str(result['exit_price'])),
                simulated_exit_reason=result['exit_reason'],
                simulated_pnl_pct=Decimal(str(result['pnl_pct'])),
                simulated_pnl_usd=Decimal(str(result['pnl_usd'])),
                    simulated_duration_minutes=result['duration_minutes']
                )
                simulations.append(sim)
                
            except (InvalidTradeDataError, SimulationError) as e:
                logger.error(f"Failed to simulate {strategy_config['strategy_name']} for trade {trade.id}: {e}")
                failed_simulations.append(strategy_config['strategy_name'])
            except Exception as e:
                logger.error(
                    f"Unexpected error simulating {strategy_config['strategy_name']} for trade {trade.id}: {e}",
                    exc_info=True
                )
                failed_simulations.append(strategy_config['strategy_name'])

        if failed_simulations:
            logger.warning(
                f"Some simulations failed for trade {trade.id}: {failed_simulations}. "
                f"Generated {len(simulations)}/{len(strategies)} simulations."
            )
        else:
            logger.info(f"✅ Generated {len(simulations)} simulations for trade {trade.id}")

        return simulations

    @classmethod
    async def update_strategy_performance(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        strategy_name: str
    ):
        """
        Update performance metrics for a strategy based on last 10 simulations

        Calculates win rate, RR, avg duration, and Phase III eligibility
        
        TODO: OPTIMIZE FOR INCREMENTAL UPDATES
        =======================================
        Current implementation recalculates ALL metrics from scratch every time
        by fetching last 10 simulations and recomputing everything.
        
        PERFORMANCE ISSUES:
        - Query fetches 10+ records every time
        - Recalculates mean/median/percentiles from scratch
        - Updates entire StrategyPerformance record
        - With 100+ trades, this becomes expensive
        
        OPTIMIZATION APPROACH:
        1. Track running statistics (count, sum, sum_of_squares) for incremental updates
        2. Use window functions for rolling calculations
        3. Only update changed fields (not entire record)
        4. Cache frequently accessed performance data
        
        INCREMENTAL UPDATE FORMULA:
        - New mean = (old_mean * old_count + new_value) / (old_count + 1)
        - New variance = ((old_var * old_count) + (new_value - new_mean)^2) / (old_count + 1)
        - Win rate = running_wins / running_total
        
        This requires adding fields to StrategyPerformance:
        - running_win_sum
        - running_loss_sum  
        - running_win_count
        - running_loss_count
        - running_pnl_sum
        - last_10_simulations (array or separate table)
        
        For now, current approach is acceptable for Phase II/III with moderate trade volume.
        Optimize when system scales to 1000+ simulations per strategy.
        """
        # Get last 10 simulations for this strategy
        result = await db.execute(
            select(StrategySimulation)
            .join(TradeSetup, StrategySimulation.trade_setup_id == TradeSetup.id)
            .where(
                TradeSetup.symbol == symbol,
                TradeSetup.direction == direction,
                TradeSetup.webhook_source == webhook_source,
                StrategySimulation.strategy_name == strategy_name
            )
            .order_by(StrategySimulation.created_at.desc())
            .limit(10)
        )
        recent_sims = result.scalars().all()

        if not recent_sims:
            logger.warning(f"No simulations found for {strategy_name} on {symbol} {direction}")
            return

        # Calculate metrics
        wins = [s for s in recent_sims if float(s.simulated_pnl_pct) > 0]
        losses = [s for s in recent_sims if float(s.simulated_pnl_pct) <= 0]

        win_rate = (len(wins) / len(recent_sims)) * 100 if recent_sims else 0
        avg_win = sum(float(s.simulated_pnl_pct) for s in wins) / len(wins) if wins else 0
        avg_loss = sum(float(s.simulated_pnl_pct) for s in losses) / len(losses) if losses else 0
        # Calculate risk/reward ratio with proper zero handling
        if avg_loss == 0:
            # Strategy has no losses - perfect strategy!
            # Use 999.0 instead of infinity (can't store inf in Decimal fields)
            risk_reward = 999.0 if avg_win > 0 else 0.0
        else:
            risk_reward = abs(avg_win / avg_loss)

        durations = [float(s.simulated_duration_minutes) / 60 for s in recent_sims]
        avg_duration = sum(durations) / len(durations) if durations else 0
        max_duration = max(durations) if durations else 0

        total_pnl = sum(float(s.simulated_pnl_usd) for s in recent_sims)

        # Get current strategy parameters from most recent simulation
        latest = recent_sims[0]

        # Phase III eligibility checks
        meets_rr = risk_reward >= PhaseConfig.PHASE_III_MIN_RR
        has_real_sl = latest.simulated_sl_pct and float(latest.simulated_sl_pct) > -999999
        meets_duration = max_duration <= PhaseConfig.PHASE_III_MAX_DURATION_HOURS
        has_min_simulations = len(recent_sims) >= PhaseConfig.PHASE_III_MIN_SIMULATIONS

        is_eligible = meets_rr and has_real_sl and meets_duration and has_min_simulations

        # Calculate composite score for ranking
        # MODIFIED: Win rate gets more weight than R/R (user preference)
        # Formula: (RR^0.4) × (WR^0.6) × (1 - duration_penalty)
        # This prioritizes high win rate strategies (60% emphasis) even if slightly less profitable
        duration_penalty = max(0, (max_duration - PhaseConfig.DURATION_PENALTY_THRESHOLD_HOURS) / PhaseConfig.DURATION_PENALTY_SCALE_HOURS)

        # Apply power weighting: 40% R/R, 60% win rate (matches grid search)
        normalized_wr = (win_rate / 100) if win_rate > 0 else 0
        rr_factor = (risk_reward ** 0.4) if risk_reward > 0 else 0
        wr_factor = (normalized_wr ** 0.6) if normalized_wr > 0 else 0

        strategy_score = rr_factor * wr_factor * (1 - duration_penalty)

        # Upsert performance record
        existing = await db.execute(
            select(StrategyPerformance).where(
                StrategyPerformance.symbol == symbol,
                StrategyPerformance.direction == direction,
                StrategyPerformance.webhook_source == webhook_source,
                StrategyPerformance.strategy_name == strategy_name
            )
        )
        perf = existing.scalar_one_or_none()

        if perf:
            # Update existing
            perf.win_rate = Decimal(str(round(win_rate, 2)))
            perf.win_count = len(wins)
            perf.loss_count = len(losses)
            perf.avg_win = Decimal(str(round(avg_win, 4)))
            perf.avg_loss = Decimal(str(round(avg_loss, 4)))
            perf.risk_reward = Decimal(str(round(risk_reward, 4)))
            perf.avg_duration_hours = Decimal(str(round(avg_duration, 2)))
            perf.max_duration_hours = Decimal(str(round(max_duration, 2)))
            perf.total_simulated_pnl = Decimal(str(round(total_pnl, 2)))
            perf.strategy_score = Decimal(str(round(strategy_score, 4)))
            perf.meets_rr_requirement = meets_rr
            perf.has_real_sl = has_real_sl
            perf.meets_duration_requirement = meets_duration
            perf.is_eligible_for_phase3 = is_eligible
            perf.current_tp1_pct = latest.simulated_tp1_pct
            perf.current_tp2_pct = latest.simulated_tp2_pct
            perf.current_tp3_pct = latest.simulated_tp3_pct
            perf.current_sl_pct = latest.simulated_sl_pct
            perf.current_trailing_enabled = latest.trailing_enabled
            perf.current_trailing_activation = latest.trailing_activation_pct
            perf.current_trailing_distance = latest.trailing_distance_pct
            perf.trades_analyzed = len(recent_sims)
        else:
            # Create new
            perf = StrategyPerformance(
                symbol=symbol,
                direction=direction,
                webhook_source=webhook_source,
                strategy_name=strategy_name,
                win_rate=Decimal(str(round(win_rate, 2))),
                win_count=len(wins),
                loss_count=len(losses),
                avg_win=Decimal(str(round(avg_win, 4))),
                avg_loss=Decimal(str(round(avg_loss, 4))),
                risk_reward=Decimal(str(round(risk_reward, 4))),
                avg_duration_hours=Decimal(str(round(avg_duration, 2))),
                max_duration_hours=Decimal(str(round(max_duration, 2))),
                total_simulated_pnl=Decimal(str(round(total_pnl, 2))),
                strategy_score=Decimal(str(round(strategy_score, 4))),
                meets_rr_requirement=meets_rr,
                has_real_sl=has_real_sl,
                meets_duration_requirement=meets_duration,
                is_eligible_for_phase3=is_eligible,
                current_tp1_pct=latest.simulated_tp1_pct,
                current_tp2_pct=latest.simulated_tp2_pct,
                current_tp3_pct=latest.simulated_tp3_pct,
                current_sl_pct=latest.simulated_sl_pct,
                current_trailing_enabled=latest.trailing_enabled,
                current_trailing_activation=latest.trailing_activation_pct,
                current_trailing_distance=latest.trailing_distance_pct,
                trades_analyzed=len(recent_sims)
            )
            db.add(perf)

        await db.commit()
        logger.info(f"Updated {strategy_name} performance for {symbol} {direction}: RR={risk_reward:.2f}, Eligible={is_eligible}")
