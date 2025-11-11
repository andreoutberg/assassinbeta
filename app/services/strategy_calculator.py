"""
Strategy Calculator - Generates strategies via grid search (NO hardcoded formulas)

Creates 6 different strategies with varying optimization criteria:
- Strategy A: Balanced (best composite score - overall winner)
- Strategy B: Aggressive (highest risk/reward - bigger wins)
- Strategy C: High Frequency (highest win rate with RR >= 1.0 - consistent wins)
- Strategy D: Adaptive (2nd best composite score - diversity)
- Strategy E: Breakeven Test on Balanced (similar to A but with breakeven feature)
- Strategy F: Breakeven Test on High WR (similar to C but with breakeven feature)
"""
from decimal import Decimal
from typing import List
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import TradeSetup, TradeMilestones
from app.database.strategy_models import GridSearchResult
from app.services.grid_search_optimizer import GridSearchOptimizer
from app.services.optuna_optimizer import run_optuna_grid_search
from app.config.settings import settings
from app.config.phase_config import PhaseConfig
from app.utils.exceptions import InsufficientDataError, StrategyGenerationError
from app.utils.retry import db_retry
from app.models.strategy_types import StrategyConfig
import logging

logger = logging.getLogger(__name__)


class StrategyCalculator:
    """Generates strategies via grid search optimization"""

    @classmethod
    @db_retry
    async def generate_all_strategies(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> List[StrategyConfig]:
        """
        Generate 4 strategies from baseline data using grid search

        OLD APPROACH (WRONG):
        - Hardcoded multipliers (TP1 = 50% of median, SL = 110% of median)
        - Guaranteed RR < 1.0 by design

        NEW APPROACH (CORRECT):
        - Grid search all 126 combinations
        - Select top 4 based on different criteria
        - Let data decide optimal parameters
        """
        logger.info(f"Starting grid search strategy generation for {symbol} {direction} {webhook_source}")

        # Get last N baseline trades (use recent data for relevance)
        # Eagerly load milestones to avoid lazy loading issues in async context
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(TradeSetup)
            .where(
                TradeSetup.symbol == symbol,
                TradeSetup.direction == direction,
                TradeSetup.webhook_source == webhook_source,
                TradeSetup.risk_strategy == 'baseline',
                TradeSetup.status == 'completed'
            )
            .options(selectinload(TradeSetup.milestones))
            .order_by(TradeSetup.completed_at.desc())
            .limit(PhaseConfig.BASELINE_TRADES_LIMIT)
        )
        baseline_trades = result.scalars().all()

        if len(baseline_trades) < PhaseConfig.MIN_BASELINE_TRADES:
            raise InsufficientDataError(
                symbol=symbol,
                direction=direction,
                required=PhaseConfig.MIN_BASELINE_TRADES,
                actual=len(baseline_trades)
            )

        logger.info(f"Found {len(baseline_trades)} baseline trades for optimization")

        # Run Optuna multi-objective optimization (replaces traditional grid search)
        start = time.time()

        # Prepare Optuna storage URL (use synchronous psycopg2 driver)
        storage_url = None
        if hasattr(settings, 'DATABASE_URL') and settings.DATABASE_URL:
            # Convert asyncpg to psycopg2 for Optuna compatibility
            storage_url = str(settings.DATABASE_URL).replace('postgresql+asyncpg://', 'postgresql+psycopg2://')
            logger.info(f"🔬 Using Optuna with persistent storage")

        logger.info(f"🔬 Running Optuna multi-objective optimization (NSGA-II)...")
        try:
            top_results = await run_optuna_grid_search(
                db=db,
                symbol=symbol,
                direction=direction,
                webhook_source=webhook_source,
                baseline_trades=baseline_trades,
                use_multi_objective=True,
                storage_url=storage_url
            )
        except Exception as optuna_error:
            logger.error(f"⚠️  Optuna optimization failed: {optuna_error}")
            logger.info(f"📊 Falling back to traditional grid search...")
            top_results = GridSearchOptimizer.grid_search(baseline_trades)

        duration_ms = int((time.time() - start) * 1000)

        if not top_results:
            raise StrategyGenerationError(f"Optimization produced no valid results for {symbol} {direction}")

        logger.info(f"✅ Optimization completed in {duration_ms}ms. Top score: {top_results[0]['composite_score']:.4f}")

        # ═══════════════════════════════════════════════════════════════════════════════
        # WALK-FORWARD VALIDATION (Prevent Overfit)
        # ═══════════════════════════════════════════════════════════════════════════════
        # Run out-of-sample validation to detect overfit strategies
        # This tests strategies on held-out data they haven't seen during optimization
        logger.info(f"🔬 Running walk-forward validation to detect overfit...")
        from app.services.walk_forward_validator import WalkForwardValidator
        
        # Expunge trades from session for sync processing
        for trade in baseline_trades:
            db.expunge(trade)
        
        validation_result = await WalkForwardValidator.validate_strategies_walk_forward(
            db=db,
            symbol=symbol,
            direction=direction,
            webhook_source=webhook_source,
            baseline_trades=baseline_trades
        )
        
        if validation_result['status'] == 'insufficient_milestones':
            # Not enough trades with milestones - skip validation entirely
            logger.warning(
                f"⚠️ Walk-forward validation skipped: {validation_result.get('message', 'Unknown error')}. "
                f"Proceeding without validation (MAE/MFE fallback unreliable for baseline trades)."
            )
            validated_strategies = None  # Will use all strategies
        elif validation_result['status'] != 'success':
            logger.warning(
                f"⚠️ Walk-forward validation failed: {validation_result.get('message', 'Unknown error')}. "
                f"Proceeding with all strategies (no filtering)."
            )
            validated_strategies = None  # Will use all strategies
        else:
            # Filter for APPROVED or CONDITIONAL strategies only
            validated_strategies = {
                s['strategy_name']: s 
                for s in validation_result['strategies']
                if 'APPROVED' in s['recommendation'] or 'CONDITIONAL' in s['recommendation']
            }
            
            logger.info(
                f"✅ Walk-forward validation complete: "
                f"In-sample WR={validation_result['in_sample_avg_win_rate']:.1f}%, "
                f"Out-sample WR={validation_result['out_of_sample_avg_win_rate']:.1f}%, "
                f"Bias={validation_result['overfit_bias']:+.1f}%, "
                f"Validated: {len(validated_strategies)}/6 strategies"
            )
            
            if len(validated_strategies) == 0:
                logger.error(
                    f"🚨 NO STRATEGIES VALIDATED! All strategies failed out-of-sample testing. "
                    f"Recommendation: {validation_result['recommendation']}"
                )
                raise StrategyGenerationError(
                    symbol=symbol,
                    direction=direction,
                    reason=f"No strategies passed walk-forward validation. Out-of-sample WR: {validation_result['out_of_sample_avg_win_rate']:.1f}%. Continue collecting baseline data."
                )
        # ═══════════════════════════════════════════════════════════════════════════════

        # Select 4-6 strategies with DIVERSE TP/SL philosophies
        # This ensures we test fundamentally different approaches, not just variations
        # NOTE: Only select strategies that passed validation (if validation ran)
        strategies = []
        
        # Group strategies by TP range to enforce diversity
        # Small TP: 0.5-3% (Conservative/Scalping)
        # Medium TP: 3-8% (Balanced)
        # Large TP: 8-15% (Aggressive)
        # Moon TP: 15%+ (Home Run Hunting)
        small_tp = [r for r in top_results if 0.5 <= r['strategy_params']['tp1_pct'] < 3.0]
        medium_tp = [r for r in top_results if 3.0 <= r['strategy_params']['tp1_pct'] < 8.0]
        large_tp = [r for r in top_results if 8.0 <= r['strategy_params']['tp1_pct'] < 15.0]
        moon_tp = [r for r in top_results if r['strategy_params']['tp1_pct'] >= 15.0]
        
        # Still keep overall best as reference
        sorted_by_score = sorted(top_results, key=lambda x: x['composite_score'], reverse=True)
        
        # Strategy A (Conservative/Scalping): Best small TP strategy
        # Philosophy: High win rate, quick exits, tight risk
        if validated_strategies is None or 'strategy_A' in validated_strategies:
            if small_tp:
                best_small = max(small_tp, key=lambda x: x['composite_score'])
                strategy_a = cls._format_strategy('strategy_A', best_small)
                strategies.append(strategy_a)
                
                validation_note = ""
                if validated_strategies and 'strategy_A' in validated_strategies:
                    val = validated_strategies['strategy_A']
                    validation_note = f" | ✅ Validated (Out-sample WR: {val['out_of_sample_win_rate']:.1f}%)"
                
                logger.info(
                    f"Strategy A (Conservative): TP={best_small['strategy_params']['tp1_pct']:.2f}%, "
                    f"SL={best_small['strategy_params']['sl_pct']:.2f}%, "
                    f"WR={best_small['win_rate']}%, RR={best_small['risk_reward']:.2f}"
                    f"{validation_note}"
                )
            else:
                logger.warning("❌ No small TP candidates for Strategy A")
        else:
            logger.warning(f"❌ Strategy A REJECTED by walk-forward validation (overfit)")

        # Strategy B (Balanced): Best medium TP strategy
        # Philosophy: Balance between win rate and R/R, often with trailing
        if validated_strategies is None or 'strategy_B' in validated_strategies:
            if medium_tp:
                best_medium = max(medium_tp, key=lambda x: x['composite_score'])
                strategy_b = cls._format_strategy('strategy_B', best_medium)
                strategies.append(strategy_b)
                
                validation_note = ""
                if validated_strategies and 'strategy_B' in validated_strategies:
                    val = validated_strategies['strategy_B']
                    validation_note = f" | ✅ Validated (Out-sample WR: {val['out_of_sample_win_rate']:.1f}%)"
                
                logger.info(
                    f"Strategy B (Balanced): TP={best_medium['strategy_params']['tp1_pct']:.2f}%, "
                    f"SL={best_medium['strategy_params']['sl_pct']:.2f}%, "
                    f"WR={best_medium['win_rate']}%, RR={best_medium['risk_reward']:.2f}"
                    f"{validation_note}"
                )
            else:
                logger.warning("❌ No medium TP candidates for Strategy B")
        else:
            logger.warning(f"❌ Strategy B REJECTED by walk-forward validation (overfit)")

        # Strategy C (Aggressive): Best large TP strategy
        # Philosophy: Wide stops, high targets, capture big moves, lower win rate
        if validated_strategies is None or 'strategy_C' in validated_strategies:
            if large_tp:
                best_large = max(large_tp, key=lambda x: x['composite_score'])
                strategy_c = cls._format_strategy('strategy_C', best_large)
                strategies.append(strategy_c)
                
                validation_note = ""
                if validated_strategies and 'strategy_C' in validated_strategies:
                    val = validated_strategies['strategy_C']
                    validation_note = f" | ✅ Validated (Out-sample WR: {val['out_of_sample_win_rate']:.1f}%)"
                
                logger.info(
                    f"Strategy C (Aggressive): TP={best_large['strategy_params']['tp1_pct']:.2f}%, "
                    f"SL={best_large['strategy_params']['sl_pct']:.2f}%, "
                    f"WR={best_large['win_rate']}%, RR={best_large['risk_reward']:.2f}"
                    f"{validation_note}"
                )
            else:
                logger.warning("❌ No large TP candidates for Strategy C")
        else:
            logger.warning(f"❌ Strategy C REJECTED by walk-forward validation (overfit)")

        # Strategy D (Moon Shot): Best very large TP strategy OR highest RR overall
        # Philosophy: Huge targets, catch the outliers, very low win rate but massive when it hits
        if validated_strategies is None or 'strategy_D' in validated_strategies:
            if moon_tp:
                best_moon = max(moon_tp, key=lambda x: x['composite_score'])
                strategy_d = cls._format_strategy('strategy_D', best_moon)
                strategies.append(strategy_d)
                
                validation_note = ""
                if validated_strategies and 'strategy_D' in validated_strategies:
                    val = validated_strategies['strategy_D']
                    validation_note = f" | ✅ Validated (Out-sample WR: {val['out_of_sample_win_rate']:.1f}%)"
                
                logger.info(
                    f"Strategy D (Moon Shot): TP={best_moon['strategy_params']['tp1_pct']:.2f}%, "
                    f"SL={best_moon['strategy_params']['sl_pct']:.2f}%, "
                    f"WR={best_moon['win_rate']}%, RR={best_moon['risk_reward']:.2f}"
                    f"{validation_note}"
                )
            else:
                # Fallback: Highest R/R from any category
                sorted_by_rr = sorted(top_results, key=lambda x: x['risk_reward'], reverse=True)
                best_rr = sorted_by_rr[0]
                strategy_d = cls._format_strategy('strategy_D', best_rr)
                strategies.append(strategy_d)
                logger.info(
                    f"Strategy D (Highest RR): TP={best_rr['strategy_params']['tp1_pct']:.2f}%, "
                    f"RR={best_rr['risk_reward']:.2f}"
                )
        else:
            logger.warning(f"❌ Strategy D REJECTED by walk-forward validation (overfit)")

        # Strategy E (Best Trailing): Best strategy WITH trailing stops (any TP range)
        # Philosophy: Let winners run, adaptive risk management
        if validated_strategies is None or 'strategy_E' in validated_strategies:
            trailing_candidates = [r for r in top_results if r['strategy_params'].get('trailing_enabled', False)]
            if trailing_candidates:
                best_trailing = max(trailing_candidates, key=lambda x: x['composite_score'])
                strategy_e = cls._format_strategy('strategy_E', best_trailing)
                strategies.append(strategy_e)
                
                validation_note = ""
                if validated_strategies and 'strategy_E' in validated_strategies:
                    val = validated_strategies['strategy_E']
                    validation_note = f" | ✅ Validated (Out-sample WR: {val['out_of_sample_win_rate']:.1f}%)"
                
                logger.info(
                    f"Strategy E (Best Trailing): TP={best_trailing['strategy_params']['tp1_pct']:.2f}%, "
                    f"Trail@{best_trailing['strategy_params']['trailing_activation']:.2f}%, "
                    f"WR={best_trailing['win_rate']}%, RR={best_trailing['risk_reward']:.2f}"
                    f"{validation_note}"
                )
            else:
                logger.warning("❌ No trailing stop candidates for Strategy E")
        else:
            logger.warning(f"❌ Strategy E REJECTED by walk-forward validation (overfit)")
        
        # Strategy F (Best Overall): Highest composite score regardless of category
        # Philosophy: Pure optimization winner - the grid search's top pick
        if validated_strategies is None or 'strategy_F' in validated_strategies:
            best_overall = sorted_by_score[0]
            strategy_f = cls._format_strategy('strategy_F', best_overall)
            strategies.append(strategy_f)
            
            validation_note = ""
            if validated_strategies and 'strategy_F' in validated_strategies:
                val = validated_strategies['strategy_F']
                validation_note = f" | ✅ Validated (Out-sample WR: {val['out_of_sample_win_rate']:.1f}%)"
            
            logger.info(
                f"Strategy F (Best Overall): TP={best_overall['strategy_params']['tp1_pct']:.2f}%, "
                f"SL={best_overall['strategy_params']['sl_pct']:.2f}%, "
                f"Score={best_overall['composite_score']:.4f}, "
                f"WR={best_overall['win_rate']}%, RR={best_overall['risk_reward']:.2f}"
                f"{validation_note}"
            )
        else:
            logger.warning(f"❌ Strategy F REJECTED by walk-forward validation (overfit)")

        # Store grid search results for audit trail (including validation)
        grid_search_record = GridSearchResult(
            symbol=symbol,
            direction=direction,
            webhook_source=webhook_source,
            baseline_trades_used=len(baseline_trades),
            combinations_tested=PhaseConfig.get_total_combinations(),
            search_duration_ms=duration_ms,
            top_results=top_results[:10],  # Store top 10 for reference
            validation_results=validation_result if validation_result and validation_result.get('status') == 'success' else None,
            selected_strategy_rank=1,
            selected_tp_pct=Decimal(str(sorted_by_score[0]['strategy_params']['tp1_pct'])),
            selected_sl_pct=Decimal(str(sorted_by_score[0]['strategy_params']['sl_pct'])),
            selected_trailing_enabled=sorted_by_score[0]['strategy_params']['trailing_enabled'],
            selected_trailing_activation=Decimal(str(sorted_by_score[0]['strategy_params']['trailing_activation'])) if sorted_by_score[0]['strategy_params']['trailing_activation'] else None,
            selected_trailing_distance=Decimal(str(sorted_by_score[0]['strategy_params']['trailing_distance'])) if sorted_by_score[0]['strategy_params']['trailing_distance'] else None,
            selected_risk_reward=Decimal(str(sorted_by_score[0]['risk_reward'])),
            selected_win_rate=Decimal(str(sorted_by_score[0]['win_rate'])),
            selected_composite_score=Decimal(str(sorted_by_score[0]['composite_score']))
        )
        db.add(grid_search_record)
        await db.commit()

        logger.info(f"✅ Generated {len(strategies)} strategies for {symbol} {direction} via grid search (A-D always, E-F if breakeven found)")

        return strategies

    @staticmethod
    def _format_strategy(name: str, grid_result: dict) -> StrategyConfig:
        """Format grid search result as strategy config"""
        params = grid_result['strategy_params']
        return StrategyConfig(
            strategy_name=name,
            tp1_pct=params['tp1_pct'],
            tp2_pct=params['tp2_pct'],
            tp3_pct=params['tp3_pct'],
            sl_pct=params['sl_pct'],
            trailing_enabled=params['trailing_enabled'],
            trailing_activation=params['trailing_activation'],
            trailing_distance=params['trailing_distance'],
            breakeven_trigger_pct=params.get('breakeven_trigger_pct')
        )
