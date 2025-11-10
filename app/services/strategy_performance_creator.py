"""
Strategy Performance Creator - Creates initial strategy_performance records from grid search results

This module solves the chicken-and-egg problem where Phase 2/3 can't start because
strategy_performance records don't exist until 10+ simulations run, but simulations
only run when Phase 2/3 trades complete.

This allows grid search results to immediately create strategy_performance records,
enabling Phase 2/3 to start right away.
"""

import logging
from decimal import Decimal
from typing import Dict, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.strategy_models import StrategyPerformance
from app.config.phase_config import PhaseConfig

logger = logging.getLogger(__name__)

STRATEGY_NAMES = ['strategy_A', 'strategy_B', 'strategy_C', 'strategy_D', 'strategy_E', 'strategy_F']


async def create_initial_strategy_performance_from_grid_search(
    db: AsyncSession,
    symbol: str,
    direction: str,
    webhook_source: str,
    top_results: List[Dict[str, Any]],
    baseline_trades_used: int,
    validation_results: Dict[str, Any] = None
) -> int:
    """
    Create initial strategy_performance records from grid search results

    This is called immediately after grid search completes to enable Phase 2/3
    without waiting for simulations to accumulate.

    Args:
        db: Database session
        symbol: Trading pair symbol
        direction: LONG or SHORT
        webhook_source: Source of webhook signal
        top_results: Top 6 results from grid search (sorted by composite score)
        baseline_trades_used: Number of baseline trades used in grid search
        validation_results: Optional walk-forward validation results containing
                          in-sample/out-of-sample metrics for each strategy

    Returns:
        Number of strategy_performance records created/updated
    """

    if not top_results or len(top_results) == 0:
        logger.warning(
            f"⚠️ No grid search results provided for {symbol} {direction} ({webhook_source})"
        )
        return 0

    created_count = 0
    updated_count = 0

    # Take top 6 results for strategies A-F
    strategies_to_create = top_results[:6]

    logger.info(
        f"📊 Creating {len(strategies_to_create)} initial strategy_performance records "
        f"for {symbol} {direction} ({webhook_source}) from grid search"
    )

    for idx, result_data in enumerate(strategies_to_create):
        strategy_name = STRATEGY_NAMES[idx]

        # Extract TP/SL parameters from nested strategy_params structure
        # Grid search results have format: result_data['strategy_params']['tp1_pct']
        strategy_params = result_data.get('strategy_params', {})
        tp1_pct = Decimal(str(strategy_params.get('tp1_pct', 0)))
        sl_pct = Decimal(str(strategy_params.get('sl_pct', 0)))
        trailing_enabled = strategy_params.get('trailing_enabled', False)
        trailing_activation = (
            Decimal(str(strategy_params.get('trailing_activation', 0)))
            if strategy_params.get('trailing_activation') else None
        )
        trailing_distance = (
            Decimal(str(strategy_params.get('trailing_distance', 0)))
            if strategy_params.get('trailing_distance') else None
        )

        # Extract performance metrics from backtest
        win_rate = Decimal(str(result_data.get('win_rate', 0)))
        risk_reward = Decimal(str(result_data.get('risk_reward', 0)))
        avg_win = Decimal(str(result_data.get('avg_win', 0)))
        avg_loss = Decimal(str(result_data.get('avg_loss', 0)))
        composite_score = Decimal(str(result_data.get('composite_score', 0)))

        # Extract validation metrics if available
        validation_data = None
        if validation_results and validation_results.get('status') == 'success':
            # Find validation data for this strategy
            for val_strategy in validation_results.get('strategies', []):
                if val_strategy.get('strategy_name') == strategy_name:
                    validation_data = val_strategy
                    break
        
        # Estimate win/loss counts
        estimated_wins = int(win_rate * baseline_trades_used / 100)
        estimated_losses = baseline_trades_used - estimated_wins

        # Check Phase 3 eligibility
        meets_rr = risk_reward >= Decimal(str(PhaseConfig.PHASE_III_MIN_RR))
        has_real_sl = sl_pct < Decimal('-0.1')  # Real SL exists (not 999999%)
        meets_duration = True  # Assume meets duration requirement
        has_min_simulations = False  # Initial creation from grid search = 0 simulations
        is_eligible = (
            meets_rr
            and has_real_sl
            and meets_duration
            and win_rate >= Decimal('60')  # Minimum 60% win rate
            and has_min_simulations  # Must have Phase II validation (always False initially)
        )

        # Check if record already exists
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
            # Only update if it's still using grid search data (trades_analyzed matches baseline_trades_used)
            # Don't overwrite real simulation data
            if perf.trades_analyzed and perf.trades_analyzed >= 10:
                logger.debug(
                    f"  ⏭️  {strategy_name}: Already has {perf.trades_analyzed} real simulations, skipping"
                )
                continue

            validation_note = ""
            if validation_data:
                validation_note = f", Val: {validation_data.get('recommendation', 'UNKNOWN')} (Out-WR={validation_data.get('out_of_sample_win_rate', 0):.1f}%)"
            
            logger.info(
                f"  🔄 {strategy_name}: Updating with new grid search results "
                f"(RR={risk_reward:.2f}, WR={win_rate:.1f}%, Eligible={is_eligible}{validation_note})"
            )

            # Update with latest grid search results
            perf.win_rate = win_rate
            perf.win_count = estimated_wins
            perf.loss_count = estimated_losses
            perf.avg_win = avg_win
            perf.avg_loss = avg_loss
            perf.risk_reward = risk_reward
            perf.avg_duration_hours = Decimal('2.0')  # Default estimate
            perf.max_duration_hours = Decimal('24.0')  # Max from baseline timeout
            perf.total_simulated_pnl = Decimal('0')  # Unknown without real trades
            perf.strategy_score = composite_score
            perf.meets_rr_requirement = meets_rr
            perf.has_real_sl = has_real_sl
            perf.meets_duration_requirement = meets_duration
            perf.is_eligible_for_phase3 = is_eligible
            perf.current_tp1_pct = tp1_pct
            perf.current_tp2_pct = tp1_pct * Decimal('2')  # 2x TP1
            perf.current_tp3_pct = tp1_pct * Decimal('3')  # 3x TP1
            perf.current_sl_pct = sl_pct
            perf.current_trailing_enabled = trailing_enabled
            perf.current_trailing_activation = trailing_activation
            perf.current_trailing_distance = trailing_distance
            perf.trades_analyzed = baseline_trades_used
            
            # Store validation metrics if available
            if validation_data:
                from datetime import datetime
                perf.in_sample_win_rate = Decimal(str(validation_data.get('in_sample_win_rate', 0)))
                perf.in_sample_risk_reward = Decimal(str(validation_data.get('in_sample_risk_reward', 0)))
                perf.in_sample_cumulative_pnl = Decimal(str(validation_data.get('in_sample_cumulative_pnl', 0)))
                perf.out_of_sample_win_rate = Decimal(str(validation_data.get('out_of_sample_win_rate', 0)))
                perf.out_of_sample_risk_reward = Decimal(str(validation_data.get('out_of_sample_risk_reward', 0)))
                perf.out_of_sample_cumulative_pnl = Decimal(str(validation_data.get('out_of_sample_cumulative_pnl', 0)))
                perf.overfit_bias = Decimal(str(validation_data.get('overfit_bias', 0)))
                perf.validation_confidence = Decimal(str(validation_data.get('confidence', 0)))
                perf.validation_recommendation = validation_data.get('recommendation', 'UNKNOWN')
                perf.validation_performed_at = datetime.utcnow()
                perf.validation_n_splits = validation_results.get('n_splits', 3)
                perf.validation_status = 'validated'

            updated_count += 1
        else:
            # Create new record
            validation_note = ""
            if validation_data:
                validation_note = f", Val: {validation_data.get('recommendation', 'UNKNOWN')} (Out-WR={validation_data.get('out_of_sample_win_rate', 0):.1f}%)"
            
            logger.info(
                f"  ➕ {strategy_name}: Creating new "
                f"(RR={risk_reward:.2f}, WR={win_rate:.1f}%, Eligible={is_eligible}{validation_note})"
            )

            # Build initial dict
            perf_data = {
                'symbol': symbol,
                'direction': direction,
                'webhook_source': webhook_source,
                'strategy_name': strategy_name,
                'win_rate': win_rate,
                'win_count': estimated_wins,
                'loss_count': estimated_losses,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'risk_reward': risk_reward,
                'avg_duration_hours': Decimal('2.0'),
                'max_duration_hours': Decimal('24.0'),
                'total_simulated_pnl': Decimal('0'),
                'strategy_score': composite_score,
                'meets_rr_requirement': meets_rr,
                'has_real_sl': has_real_sl,
                'meets_duration_requirement': meets_duration,
                'is_eligible_for_phase3': is_eligible,
                'current_tp1_pct': tp1_pct,
                'current_tp2_pct': tp1_pct * Decimal('2'),
                'current_tp3_pct': tp1_pct * Decimal('3'),
                'current_sl_pct': sl_pct,
                'current_trailing_enabled': trailing_enabled,
                'current_trailing_activation': trailing_activation,
                'current_trailing_distance': trailing_distance,
                'trades_analyzed': baseline_trades_used
            }
            
            # Add validation metrics if available
            if validation_data:
                from datetime import datetime
                perf_data.update({
                    'in_sample_win_rate': Decimal(str(validation_data.get('in_sample_win_rate', 0))),
                    'in_sample_risk_reward': Decimal(str(validation_data.get('in_sample_risk_reward', 0))),
                    'in_sample_cumulative_pnl': Decimal(str(validation_data.get('in_sample_cumulative_pnl', 0))),
                    'out_of_sample_win_rate': Decimal(str(validation_data.get('out_of_sample_win_rate', 0))),
                    'out_of_sample_risk_reward': Decimal(str(validation_data.get('out_of_sample_risk_reward', 0))),
                    'out_of_sample_cumulative_pnl': Decimal(str(validation_data.get('out_of_sample_cumulative_pnl', 0))),
                    'overfit_bias': Decimal(str(validation_data.get('overfit_bias', 0))),
                    'validation_confidence': Decimal(str(validation_data.get('confidence', 0))),
                    'validation_recommendation': validation_data.get('recommendation', 'UNKNOWN'),
                    'validation_performed_at': datetime.utcnow(),
                    'validation_n_splits': validation_results.get('n_splits', 3),
                    'validation_status': 'validated'
                })
            
            perf = StrategyPerformance(**perf_data)
            db.add(perf)
            created_count += 1

    # Commit changes
    await db.commit()

    logger.info(
        f"✅ Strategy performance initialization complete for {symbol} {direction}: "
        f"Created={created_count}, Updated={updated_count}"
    )

    return created_count + updated_count
