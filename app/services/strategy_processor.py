"""
Strategy Processor - Background task that runs after trade completes

Handles:
1. Generating strategies when Phase I completes
2. Simulating all strategies against completed trades
3. Updating performance metrics
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import TradeSetup
from app.services.strategy_calculator import StrategyCalculator
from app.services.strategy_simulator import StrategySimulator
from app.database.strategy_models import StrategySimulation
from app.config.phase_config import PhaseConfig
from app.utils.exceptions import (
    InsufficientDataError,
    StrategyGenerationError,
    NoEligibleStrategyError
)
import logging

logger = logging.getLogger(__name__)


class StrategyProcessor:
    """Processes completed trades for strategy simulation"""

    @classmethod
    async def process_completed_trade(
        cls,
        db: AsyncSession,
        trade: TradeSetup
    ):
        """
        Process a completed trade:
        - Generate strategies if needed (Phase I → II transition)
        - Simulate all 4 strategies against this trade
        - Update performance metrics

        Called after trade closes (24h timeout or opposite signal)
        """
        logger.info(f"🔄 [STRATEGY_PROCESSOR] Processing completed trade {trade.id}: {trade.symbol} {trade.direction} via {trade.webhook_source}")
        logger.debug(f"[STRATEGY_PROCESSOR] Trade details: entry={trade.entry_price}, exit={getattr(trade, 'exit_price', 'N/A')}, pnl={getattr(trade, 'final_pnl_pct', 'N/A')}%")

        # Eagerly load milestones relationship (needed for chronological simulation)
        await db.refresh(trade, ['milestones'])

        if trade.milestones:
            logger.debug(f"[STRATEGY_PROCESSOR] Trade {trade.id} has milestone data: max_profit={trade.milestones.max_profit_pct}%, max_drawdown={trade.milestones.max_drawdown_pct}%")
        else:
            logger.warning(f"⚠️ [STRATEGY_PROCESSOR] Trade {trade.id} has NO milestone data - simulations may be inaccurate")

        if trade.risk_strategy != 'baseline':
            logger.info(f"[STRATEGY_PROCESSOR] Trade {trade.id} is '{trade.risk_strategy}', skipping strategy processing (only baseline trades trigger processing)")
            return

        symbol = trade.symbol
        direction = trade.direction
        webhook_source = trade.webhook_source

        logger.info(f"📊 [STRATEGY_PROCESSOR] Baseline trade completed for {symbol} {direction} - checking strategy status")

        try:
            # STRATEGY REGENERATION: Check if we should regenerate strategies
            # Regenerate every N completed baseline trades (not just at Phase I threshold)
            # This keeps strategies fresh as more data accumulates
            from app.database.strategy_models import StrategyPerformance
            from sqlalchemy import select

            from sqlalchemy.orm import selectinload
            baseline_trades = await db.execute(
                select(TradeSetup)
                .where(
                    TradeSetup.symbol == symbol,
                    TradeSetup.direction == direction,
                    TradeSetup.webhook_source == webhook_source,
                    TradeSetup.risk_strategy == 'baseline',
                    TradeSetup.status == 'completed'
                )
                .options(selectinload(TradeSetup.milestones))
            )
            baseline_count = len(baseline_trades.scalars().all())

            # Check if strategies exist
            existing_check = await db.execute(
                select(StrategyPerformance).where(
                    StrategyPerformance.symbol == symbol,
                    StrategyPerformance.direction == direction,
                    StrategyPerformance.webhook_source == webhook_source
                ).limit(1)
            )

            strategies_exist = existing_check.scalar_one_or_none() is not None
            should_regenerate = baseline_count > 0 and baseline_count % PhaseConfig.REGENERATION_INTERVAL == 0

            logger.debug(f"[STRATEGY_PROCESSOR] Baseline count: {baseline_count}, strategies exist: {strategies_exist}, should regenerate: {should_regenerate}")

            if strategies_exist and not should_regenerate:
                next_regen = ((baseline_count // PhaseConfig.REGENERATION_INTERVAL) + 1) * PhaseConfig.REGENERATION_INTERVAL
                logger.info(
                    f"✓ [STRATEGY_PROCESSOR] Using existing strategies for {symbol} {direction} - "
                    f"baseline_count={baseline_count}, next regeneration at {next_regen} trades ({next_regen - baseline_count} trades away)"
                )
                # Strategies exist, but we still need to simulate this trade
                # Fetch existing strategies
                from app.services.strategy_selector import StrategySelector
                existing_strategies = await StrategySelector.get_all_strategies_performance(
                    db, symbol, direction, webhook_source
                )
                # Convert to strategy config format (match format from generate_all_strategies)
                # Need to fetch StrategyPerformance records to get trailing params
                perf_result = await db.execute(
                    select(StrategyPerformance).where(
                        StrategyPerformance.symbol == symbol,
                        StrategyPerformance.direction == direction,
                        StrategyPerformance.webhook_source == webhook_source
                    )
                )
                perf_records = {p.strategy_name: p for p in perf_result.scalars().all()}
                
                strategies = []
                for s in existing_strategies:
                    perf = perf_records.get(s['strategy_name'])
                    strategies.append({
                        'strategy_name': s['strategy_name'],
                        'tp1_pct': s['current_params']['tp1'],
                        'tp2_pct': s['current_params']['tp2'],
                        'tp3_pct': s['current_params']['tp3'],
                        'sl_pct': s['current_params']['sl'],
                        'trailing_enabled': s['current_params']['trailing'],
                        'trailing_activation': float(perf.current_trailing_activation) if perf and perf.current_trailing_activation else None,
                        'trailing_distance': float(perf.current_trailing_distance) if perf and perf.current_trailing_distance else None
                    })

                logger.debug(f"[STRATEGY_PROCESSOR] Loaded {len(strategies)} existing strategies for simulation")

            elif should_regenerate:
                # REGENERATE strategies with updated data
                logger.info(
                    f"🔄 [STRATEGY_PROCESSOR] REGENERATION TRIGGERED for {symbol} {direction} - "
                    f"baseline_count={baseline_count} (regenerates every {PhaseConfig.REGENERATION_INTERVAL} trades)"
                )
                try:
                    strategies = await StrategyCalculator.generate_all_strategies(
                        db, symbol, direction, webhook_source
                    )
                    logger.info(
                        f"✅ [STRATEGY_PROCESSOR] Regenerated {len(strategies)} strategies using {baseline_count} baseline trades"
                    )
                    for strat in strategies:
                        logger.debug(
                            f"[STRATEGY_PROCESSOR] {strat['strategy_name']}: "
                            f"TP={strat['tp1_pct']}%, SL={strat['sl_pct']}%, "
                            f"trailing={strat['trailing_enabled']}"
                        )
                except InsufficientDataError as e:
                    logger.warning(f"⚠️ [STRATEGY_PROCESSOR] Insufficient baseline data for regeneration: {e}")
                    return
                except StrategyGenerationError as e:
                    logger.error(f"❌ [STRATEGY_PROCESSOR] Strategy regeneration failed: {e}", exc_info=True)
                    return
            else:
                # Generate strategies from baseline data (first time)
                logger.info(f"🎯 [STRATEGY_PROCESSOR] FIRST-TIME strategy generation for {symbol} {direction} (baseline_count={baseline_count})")
                try:
                    strategies = await StrategyCalculator.generate_all_strategies(
                        db, symbol, direction, webhook_source
                    )
                    logger.info(f"✅ [STRATEGY_PROCESSOR] Generated {len(strategies)} strategies for first time")
                    for strat in strategies:
                        logger.debug(
                            f"[STRATEGY_PROCESSOR] {strat['strategy_name']}: "
                            f"TP={strat['tp1_pct']}%, SL={strat['sl_pct']}%, "
                            f"trailing={strat['trailing_enabled']}"
                        )
                except InsufficientDataError as e:
                    logger.info(f"ℹ️ [STRATEGY_PROCESSOR] Insufficient baseline data (need {PhaseConfig.PHASE_I_THRESHOLD}+ trades): {e}")
                    return
                except StrategyGenerationError as e:
                    logger.error(f"❌ [STRATEGY_PROCESSOR] Strategy generation failed: {e}", exc_info=True)
                    return

            if not strategies:
                logger.warning(f"⚠️ [STRATEGY_PROCESSOR] No strategies available for {symbol} {direction}")
                return

            logger.info(f"📊 [STRATEGY_PROCESSOR] Simulating {len(strategies)} strategies against trade {trade.id}")

            # Simulate all strategies against this completed trade
            simulations = await StrategySimulator.simulate_all_strategies_for_trade(
                db, trade, strategies
            )

            # Log simulation results
            logger.debug(f"[STRATEGY_PROCESSOR] Simulation results for trade {trade.id}:")
            for sim in simulations:
                logger.debug(
                    f"  {sim.strategy_name}: "
                    f"PnL={sim.simulated_pnl_pct}%, "
                    f"exit_reason={sim.simulated_exit_reason}, "
                    f"duration={sim.simulated_duration_minutes}min"
                )

            # Add simulations to session
            for sim in simulations:
                db.add(sim)

            logger.info(f"💾 [STRATEGY_PROCESSOR] Created {len(simulations)} strategy simulations for trade {trade.id}")

            # FLUSH to make simulations visible to subsequent queries (but don't commit yet)
            await db.flush()

            # Update performance metrics for each strategy (still in same transaction)
            logger.debug(f"[STRATEGY_PROCESSOR] Updating performance metrics for {len(strategies)} strategies")
            for strategy in strategies:
                await StrategySimulator.update_strategy_performance(
                    db, symbol, direction, webhook_source, strategy['strategy_name']
                )

            # CRITICAL: Commit everything together in single transaction
            # If this fails, ALL changes roll back (no orphaned simulations)
            await db.commit()

            logger.info(
                f"✅ [STRATEGY_PROCESSOR] Processing complete for trade {trade.id}: "
                f"{len(simulations)} simulations saved, {len(strategies)} performance metrics updated"
            )

        except Exception as e:
            logger.error(
                f"❌ Error processing strategies for trade {trade.id}: {e}. "
                f"Rolling back all changes to maintain data consistency.",
                exc_info=True
            )
            await db.rollback()
            # Re-raise to allow caller to handle if needed
            raise
