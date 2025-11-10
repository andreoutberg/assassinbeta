"""
Demo Grid Search Optimizer - Optimized for High Win Rate Trading
Tests all 1,215 parameter combinations from phase_config using demo trades.

Key Features:
- Tests all combinations from PhaseConfig (9 TP × 9 SL × 5 trailing × 3 breakeven)
- Pre-filters invalid combinations (RR < 0.5 for high-WR mode)
- Uses real Bybit demo price data for MAE/MFE simulation
- Stores results in PostgreSQL strategies table
- Completes in <5 minutes for 720 valid combinations
"""
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from app.database.models import TradeSetup, TradeMilestones
from app.database.strategy_models import GridSearchResult, StrategyPerformance
from app.services.demo_strategy_simulator import DemoStrategySimulator
from app.config.phase_config import PhaseConfig
from app.models.strategy_types import GridSearchResult as GridSearchResultType
from datetime import datetime, timedelta
import logging
import asyncio
import time
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


class DemoGridSearchOptimizer:
    """Grid search optimizer for demo trading with high win rate focus"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.simulator = DemoStrategySimulator(db)

    async def run_grid_search(
        self,
        symbol: str,
        direction: str,
        webhook_source: str,
        baseline_trades: List[TradeSetup],
        max_trades: int = 50,
        use_realtime_prices: bool = True
    ) -> Dict[str, Any]:
        """
        Run grid search on demo trades testing all 1,215 combinations

        Args:
            symbol: Trading symbol
            direction: Trade direction
            webhook_source: Signal source
            baseline_trades: List of Phase I baseline trades
            max_trades: Maximum trades to use (default 50)
            use_realtime_prices: Whether to fetch real-time demo prices

        Returns:
            Dict with top strategies and performance metrics
        """
        start_time = time.time()
        trades_to_use = baseline_trades[:max_trades]

        logger.info(f"Starting HIGH-WR grid search for {symbol} {direction}")
        logger.info(f"Using {len(trades_to_use)} baseline trades")
        logger.info(f"Testing {PhaseConfig.get_total_combinations()} theoretical combinations")

        # Generate all valid combinations
        valid_combinations = self._generate_valid_combinations()
        logger.info(f"Pre-filtered to {len(valid_combinations)} valid combinations")

        # Initialize results tracker
        results = defaultdict(lambda: {
            'wins': 0,
            'losses': 0,
            'total_pnl': 0,
            'durations': [],
            'exit_reasons': defaultdict(int),
            'config': {}
        })

        # Process trades in batches for efficiency
        batch_size = 10
        total_simulations = 0

        for i in range(0, len(trades_to_use), batch_size):
            batch_trades = trades_to_use[i:i + batch_size]

            # Simulate all combinations for this batch
            for trade in batch_trades:
                simulation_configs = []

                for combo in valid_combinations:
                    config = {
                        'strategy_name': self._generate_strategy_name(combo),
                        'tp_pct': combo['tp'],
                        'sl_pct': combo['sl'],
                        'trailing_config': combo.get('trailing'),
                        'breakeven_pct': combo.get('breakeven'),
                        **combo
                    }
                    simulation_configs.append(config)

                # Run simulations in parallel
                async with self.simulator:
                    simulation_results = await self.simulator.batch_simulate_strategies(
                        trade=trade,
                        strategy_configs=simulation_configs,
                        use_realtime_prices=use_realtime_prices
                    )

                # Process results
                for result, config in zip(simulation_results, simulation_configs):
                    strategy_key = config['strategy_name']
                    results[strategy_key]['config'] = config

                    if result.is_winner:
                        results[strategy_key]['wins'] += 1
                    else:
                        results[strategy_key]['losses'] += 1

                    results[strategy_key]['total_pnl'] += result.pnl_pct
                    results[strategy_key]['durations'].append(result.duration_minutes)
                    results[strategy_key]['exit_reasons'][result.exit_reason] += 1

                    total_simulations += 1

            # Log progress
            if (i + batch_size) % 10 == 0:
                elapsed = time.time() - start_time
                logger.info(
                    f"Progress: {i + batch_size}/{len(trades_to_use)} trades, "
                    f"{total_simulations} simulations, {elapsed:.1f}s elapsed"
                )

        # Calculate metrics for each strategy
        strategy_scores = []
        for strategy_name, data in results.items():
            total_trades = data['wins'] + data['losses']
            if total_trades == 0:
                continue

            win_rate = (data['wins'] / total_trades) * 100
            avg_duration = np.mean(data['durations']) if data['durations'] else 0
            avg_duration_hours = avg_duration / 60

            # Calculate risk/reward
            avg_win = data['total_pnl'] / data['wins'] if data['wins'] > 0 else 0
            avg_loss = abs(data['total_pnl'] / data['losses']) if data['losses'] > 0 else 1
            risk_reward = avg_win / avg_loss if avg_loss > 0 else 0

            # Calculate expected value
            expected_value = PhaseConfig.calculate_expected_value(win_rate, risk_reward)

            # Check Phase III eligibility
            is_eligible = PhaseConfig.is_strategy_eligible_for_phase3(
                win_rate=win_rate,
                rr_ratio=risk_reward,
                avg_duration_hours=avg_duration_hours,
                num_simulations=total_trades
            )

            # Calculate composite score
            score = self.simulator.calculate_strategy_score(
                win_rate=win_rate,
                risk_reward=risk_reward,
                avg_duration_hours=avg_duration_hours
            )

            strategy_scores.append({
                'strategy_name': strategy_name,
                'config': data['config'],
                'win_rate': win_rate,
                'risk_reward': risk_reward,
                'expected_value': expected_value,
                'avg_duration_hours': avg_duration_hours,
                'total_pnl': data['total_pnl'],
                'trades_analyzed': total_trades,
                'composite_score': score,
                'is_eligible_phase3': is_eligible,
                'exit_reasons': dict(data['exit_reasons'])
            })

        # Sort by composite score
        strategy_scores.sort(key=lambda x: x['composite_score'], reverse=True)

        # Get top strategies
        top_strategies = strategy_scores[:10]

        # Calculate search duration
        search_duration = time.time() - start_time

        # Save results to database
        await self._save_grid_search_results(
            symbol=symbol,
            direction=direction,
            webhook_source=webhook_source,
            baseline_trades_used=len(trades_to_use),
            combinations_tested=len(valid_combinations),
            search_duration_ms=int(search_duration * 1000),
            top_results=top_strategies
        )

        logger.info(f"Grid search completed in {search_duration:.1f}s")
        logger.info(f"Top strategy: WR={top_strategies[0]['win_rate']:.1f}%, RR={top_strategies[0]['risk_reward']:.2f}")

        return {
            'search_duration': search_duration,
            'combinations_tested': len(valid_combinations),
            'total_simulations': total_simulations,
            'top_strategies': top_strategies,
            'phase3_eligible': [s for s in top_strategies if s['is_eligible_phase3']],
            'high_wr_strategies': [s for s in top_strategies if s['win_rate'] >= 65],
            'stats': {
                'avg_win_rate': np.mean([s['win_rate'] for s in strategy_scores]),
                'max_win_rate': max([s['win_rate'] for s in strategy_scores]),
                'avg_risk_reward': np.mean([s['risk_reward'] for s in strategy_scores]),
                'phase3_eligible_count': len([s for s in strategy_scores if s['is_eligible_phase3']])
            }
        }

    def _generate_valid_combinations(self) -> List[Dict[str, Any]]:
        """
        Generate all valid TP/SL/trailing/breakeven combinations

        Returns:
            List of valid combinations meeting R/R requirements
        """
        valid_combos = []
        min_rr = 0.5 if PhaseConfig.OPTIMIZE_FOR_WIN_RATE else 1.0

        for tp in PhaseConfig.TP_OPTIONS:
            for sl in PhaseConfig.SL_OPTIONS:
                # Calculate risk/reward ratio
                rr_ratio = tp / abs(sl)

                # Skip if doesn't meet minimum R/R
                if rr_ratio < min_rr:
                    continue

                # Skip invalid combinations
                if abs(sl) >= tp:
                    continue

                # Estimate win rate for this combination
                estimated_wr = PhaseConfig.estimate_win_rate(tp, sl)

                # For high-WR mode, skip unlikely combinations
                if PhaseConfig.OPTIMIZE_FOR_WIN_RATE:
                    if estimated_wr < 50:  # Skip if unlikely to achieve >50% WR
                        continue

                # Add all trailing and breakeven variations
                for trailing in PhaseConfig.TRAILING_OPTIONS:
                    for breakeven in PhaseConfig.BREAKEVEN_OPTIONS:
                        combo = {
                            'tp': tp,
                            'sl': sl,
                            'rr': rr_ratio,
                            'estimated_wr': estimated_wr,
                            'trailing': None if trailing is None else {
                                'activation': trailing[0],
                                'distance': trailing[1]
                            },
                            'breakeven': breakeven
                        }
                        valid_combos.append(combo)

        # Sort by estimated win rate (highest first)
        valid_combos.sort(key=lambda x: x['estimated_wr'], reverse=True)

        return valid_combos

    def _generate_strategy_name(self, combo: Dict[str, Any]) -> str:
        """Generate unique strategy name from parameters"""
        tp = combo['tp']
        sl = abs(combo['sl'])

        # Include trailing info if present
        trailing_str = ""
        if combo.get('trailing'):
            trailing_str = f"_T{combo['trailing']['activation']}-{combo['trailing']['distance']}"

        # Include breakeven info if present
        breakeven_str = ""
        if combo.get('breakeven'):
            breakeven_str = f"_BE{combo['breakeven']}"

        return f"TP{tp}_SL{sl}{trailing_str}{breakeven_str}"

    async def _save_grid_search_results(
        self,
        symbol: str,
        direction: str,
        webhook_source: str,
        baseline_trades_used: int,
        combinations_tested: int,
        search_duration_ms: int,
        top_results: List[Dict[str, Any]]
    ) -> None:
        """Save grid search results to database"""
        # Select winning strategy (top ranked)
        winner = top_results[0] if top_results else None

        grid_result = GridSearchResult(
            symbol=symbol,
            direction=direction,
            webhook_source=webhook_source,
            baseline_trades_used=baseline_trades_used,
            combinations_tested=combinations_tested,
            search_duration_ms=search_duration_ms,
            top_results=top_results,
            selected_strategy_rank=1,
            selected_tp_pct=winner['config']['tp_pct'] if winner else None,
            selected_sl_pct=winner['config']['sl_pct'] if winner else None,
            selected_trailing_enabled=bool(winner['config'].get('trailing_config')) if winner else False,
            selected_trailing_activation=winner['config']['trailing_config']['activation'] if winner and winner['config'].get('trailing_config') else None,
            selected_trailing_distance=winner['config']['trailing_config']['distance'] if winner and winner['config'].get('trailing_config') else None,
            selected_risk_reward=winner['risk_reward'] if winner else None,
            selected_win_rate=winner['win_rate'] if winner else None,
            selected_composite_score=winner['composite_score'] if winner else None
        )

        self.db.add(grid_result)

        # Also update strategy performance records
        for strategy in top_results[:4]:  # Top 4 strategies for Phase II
            perf = await self.db.execute(
                select(StrategyPerformance).where(
                    and_(
                        StrategyPerformance.symbol == symbol,
                        StrategyPerformance.direction == direction,
                        StrategyPerformance.webhook_source == webhook_source,
                        StrategyPerformance.strategy_name == strategy['strategy_name']
                    )
                )
            )
            perf_record = perf.scalar_one_or_none()

            if not perf_record:
                perf_record = StrategyPerformance(
                    symbol=symbol,
                    direction=direction,
                    webhook_source=webhook_source,
                    strategy_name=strategy['strategy_name']
                )
                self.db.add(perf_record)

            # Update performance metrics
            perf_record.win_rate = strategy['win_rate']
            perf_record.risk_reward = strategy['risk_reward']
            perf_record.avg_duration_hours = strategy['avg_duration_hours']
            perf_record.strategy_score = strategy['composite_score']
            perf_record.is_eligible_for_phase3 = strategy['is_eligible_phase3']
            perf_record.trades_analyzed = strategy['trades_analyzed']

            # Update strategy parameters
            config = strategy['config']
            perf_record.current_tp1_pct = config['tp_pct']
            perf_record.current_sl_pct = config['sl_pct']
            if config.get('trailing_config'):
                perf_record.current_trailing_enabled = True
                perf_record.current_trailing_activation = config['trailing_config']['activation']
                perf_record.current_trailing_distance = config['trailing_config']['distance']
            else:
                perf_record.current_trailing_enabled = False
            perf_record.current_breakeven_trigger_pct = config.get('breakeven_pct')

        await self.db.commit()
        logger.info(f"Saved grid search results with {len(top_results)} strategies")

    async def get_top_strategies(
        self,
        symbol: str,
        direction: str,
        webhook_source: str,
        limit: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Get top performing strategies from latest grid search

        Args:
            symbol: Trading symbol
            direction: Trade direction
            webhook_source: Signal source
            limit: Number of strategies to return

        Returns:
            List of top strategies with configs
        """
        # Get latest grid search result
        result = await self.db.execute(
            select(GridSearchResult)
            .where(
                and_(
                    GridSearchResult.symbol == symbol,
                    GridSearchResult.direction == direction,
                    GridSearchResult.webhook_source == webhook_source
                )
            )
            .order_by(desc(GridSearchResult.created_at))
            .limit(1)
        )
        grid_result = result.scalar_one_or_none()

        if not grid_result or not grid_result.top_results:
            return []

        return grid_result.top_results[:limit]

    async def validate_strategy_performance(
        self,
        strategy_name: str,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> Dict[str, Any]:
        """
        Validate strategy performance meets Phase III requirements

        Args:
            strategy_name: Name of strategy to validate
            symbol: Trading symbol
            direction: Trade direction
            webhook_source: Signal source

        Returns:
            Dict with validation results
        """
        # Get strategy performance record
        result = await self.db.execute(
            select(StrategyPerformance).where(
                and_(
                    StrategyPerformance.symbol == symbol,
                    StrategyPerformance.direction == direction,
                    StrategyPerformance.webhook_source == webhook_source,
                    StrategyPerformance.strategy_name == strategy_name
                )
            )
        )
        perf = result.scalar_one_or_none()

        if not perf:
            return {
                'valid': False,
                'reason': 'Strategy not found'
            }

        # Check Phase III requirements
        is_eligible = PhaseConfig.is_strategy_eligible_for_phase3(
            win_rate=float(perf.win_rate) if perf.win_rate else 0,
            rr_ratio=float(perf.risk_reward) if perf.risk_reward else 0,
            avg_duration_hours=float(perf.avg_duration_hours) if perf.avg_duration_hours else 0,
            num_simulations=perf.trades_analyzed or 0
        )

        return {
            'valid': is_eligible,
            'win_rate': float(perf.win_rate) if perf.win_rate else 0,
            'risk_reward': float(perf.risk_reward) if perf.risk_reward else 0,
            'avg_duration_hours': float(perf.avg_duration_hours) if perf.avg_duration_hours else 0,
            'trades_analyzed': perf.trades_analyzed or 0,
            'strategy_score': float(perf.strategy_score) if perf.strategy_score else 0,
            'meets_requirements': {
                'win_rate': float(perf.win_rate) >= PhaseConfig.PHASE_III_MIN_WIN_RATE if perf.win_rate else False,
                'risk_reward': float(perf.risk_reward) >= PhaseConfig.PHASE_III_MIN_RR if perf.risk_reward else False,
                'duration': float(perf.avg_duration_hours) <= PhaseConfig.PHASE_III_MAX_DURATION_HOURS if perf.avg_duration_hours else False,
                'simulations': (perf.trades_analyzed or 0) >= PhaseConfig.PHASE_III_MIN_SIMULATIONS
            }
        }