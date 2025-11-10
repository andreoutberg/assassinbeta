"""
Walk-Forward Analysis - Prevents Self-Confirmation Bias

Tests strategies on OUT-OF-SAMPLE data to get realistic performance expectations.

Problem:
  Grid search optimizes on trades 1-10, then "validates" on the SAME 1-10.
  This creates self-confirming bias and inflated win rates.

Solution:
  Train on subset [1-7], test on held-out [8-10].
  Repeat with different splits to get average out-of-sample performance.

Example with 10 baseline trades:
  Split 1: Train[1-7]  → Test[8-10]   (3 test trades)
  Split 2: Train[1-8]  → Test[9-10]   (2 test trades)
  Split 3: Train[1-9]  → Test[10]     (1 test trade)

  Average test performance = TRUE expectation (unbiased)
"""
from typing import List, Dict, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import TradeSetup
from app.services.grid_search_optimizer import GridSearchOptimizer
from app.services.strategy_simulator import StrategySimulator
from app.config.phase_config import PhaseConfig
from decimal import Decimal
import logging
import statistics

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """Validates strategies using walk-forward analysis to prevent overfitting"""

    # Minimum trades needed for walk-forward (need at least 7 train + 3 test)
    MIN_TRADES_FOR_VALIDATION = 10

    # Train/test split ratios to test
    SPLIT_RATIOS = [
        (0.70, 0.30),  # 70% train, 30% test
        (0.80, 0.20),  # 80% train, 20% test
        (0.90, 0.10),  # 90% train, 10% test
    ]

    @classmethod
    async def validate_strategies_walk_forward(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        baseline_trades: List[TradeSetup]
    ) -> Dict:
        """
        Perform walk-forward analysis on baseline trades

        FIXED: MAE/MFE fallback simulation now correctly handles baseline trades
        without stop loss. Baseline trades use MFE as exit point when no TPs are hit.

        Preferentially uses trades with milestones for accuracy, but can fall back
        to MAE/MFE simulation when necessary.
        """
        # Filter trades to prefer those with milestones for better accuracy
        trades_with_milestones = []
        trades_without_milestones = []

        for t in baseline_trades:
            try:
                milestones = list(t.milestones) if hasattr(t, 'milestones') and t.milestones else []
                if len(milestones) > 0:
                    trades_with_milestones.append(t)
                else:
                    trades_without_milestones.append(t)
            except (TypeError, AttributeError):
                # Relationship not loaded or invalid - treat as no milestones
                trades_without_milestones.append(t)

        # Use trades with milestones preferentially, but include MAE/MFE trades if needed
        trades_for_validation = trades_with_milestones

        # If we have less than minimum with milestones, add MAE/MFE trades
        if len(trades_with_milestones) < cls.MIN_TRADES_FOR_VALIDATION:
            trades_needed = cls.MIN_TRADES_FOR_VALIDATION - len(trades_with_milestones)
            trades_for_validation.extend(trades_without_milestones[:trades_needed])

            logger.info(
                f"📊 Walk-forward validation for {symbol} {direction}: "
                f"Using {len(trades_with_milestones)} milestone trades + "
                f"{min(trades_needed, len(trades_without_milestones))} MAE/MFE fallback trades"
            )
        else:
            logger.info(
                f"✅ Walk-forward validation for {symbol} {direction}: "
                f"Using {len(trades_with_milestones)} trades with milestones"
            )

        if len(trades_for_validation) < cls.MIN_TRADES_FOR_VALIDATION:
            logger.warning(
                f"⚠️ Walk-forward validation skipped for {symbol} {direction}: "
                f"Only {len(trades_for_validation)} trades available (need {cls.MIN_TRADES_FOR_VALIDATION})"
            )
            return {
                'status': 'insufficient_trades',
                'message': f'Only {len(trades_for_validation)} trades available',
                'recommendation': 'collect_more_data'
            }

        # Sort trades by timestamp for proper train/test splitting
        sorted_trades = sorted(trades_for_validation, key=lambda t: t.entry_timestamp)

        # Run walk-forward validation with different splits
        split_results = []

        for train_ratio, test_ratio in cls.SPLIT_RATIOS:
            split_result = cls._run_single_split(
                sorted_trades, train_ratio, test_ratio
            )
            split_results.append(split_result)

        # Aggregate results across all splits
        return cls._aggregate_split_results(split_results)

    @classmethod
    def _run_single_split(
        cls,
        sorted_trades: List[TradeSetup],
        train_ratio: float,
        test_ratio: float
    ) -> Dict:
        """
        Run one train/test split

        Process:
          1. Split trades into train/test sets
          2. Run grid search on TRAIN only
          3. Select top 6 strategies
          4. Test on TRAIN (in-sample performance)
          5. Test on TEST (out-of-sample performance)
          6. Compare results
        """
        n_total = len(sorted_trades)
        n_train = int(n_total * train_ratio)
        n_test = n_total - n_train

        train_trades = sorted_trades[:n_train]
        test_trades = sorted_trades[n_train:]

        logger.info(
            f"  📊 Split {int(train_ratio*100)}/{int(test_ratio*100)}: "
            f"Train={n_train} trades, Test={n_test} trades"
        )

        # Step 1: Run grid search on TRAIN set only
        grid_results = GridSearchOptimizer.grid_search(train_trades)

        if not grid_results:
            logger.warning(f"    ⚠️ No valid strategies found in grid search")
            return None

        # Step 2: Select top 6 strategies (same logic as strategy_calculator.py)
        top_strategies = cls._select_top_6_strategies(grid_results)

        # Step 3: Test each strategy on TRAIN (in-sample) and TEST (out-of-sample)
        strategy_results = []

        for strategy in top_strategies:
            # In-sample performance (train set)
            train_performance = cls._evaluate_strategy_on_trades(
                strategy, train_trades
            )

            # Out-of-sample performance (test set)
            test_performance = cls._evaluate_strategy_on_trades(
                strategy, test_trades
            )

            strategy_results.append({
                'strategy_name': strategy['strategy_name'],
                'tp_pct': strategy['tp1_pct'],
                'sl_pct': strategy['sl_pct'],
                'trailing': strategy['trailing_enabled'],
                'in_sample': train_performance,
                'out_of_sample': test_performance,
                'overfit_bias': train_performance['win_rate'] - test_performance['win_rate']
            })

        return {
            'train_size': n_train,
            'test_size': n_test,
            'train_ratio': train_ratio,
            'strategies': strategy_results
        }

    @classmethod
    def _select_top_6_strategies(cls, grid_results: List) -> List[Dict]:
        """
        Select top 6 strategies from grid search results

        Same selection criteria as strategy_calculator.py:
          A: Best composite score (overall)
          B: Best composite score with trailing
          C: Best win rate with RR >= 1.5
          D: 2nd best composite score (diversity)
          E: Best composite with breakeven
          F: Best win rate with RR >= 1.5 and breakeven
        """
        if not grid_results:
            return []

        # Sort by composite score (descending)
        sorted_by_score = sorted(grid_results, key=lambda x: x['composite_score'], reverse=True)

        # Strategy A: Best overall
        strategy_A = sorted_by_score[0] if len(sorted_by_score) > 0 else None

        # Strategy B: Best with trailing
        with_trailing = [s for s in grid_results if s['strategy_params']['trailing_enabled']]
        strategy_B = max(with_trailing, key=lambda x: x['composite_score']) if with_trailing else None

        # Strategy C: Best win rate with RR >= 1.5
        high_wr = sorted(grid_results, key=lambda x: x['win_rate'], reverse=True)
        strategy_C = next((s for s in high_wr if s['risk_reward'] >= 1.5), None)

        # Strategy D: 2nd best overall (diversity)
        strategy_D = sorted_by_score[1] if len(sorted_by_score) > 1 else None

        # Strategy E: Best with breakeven
        with_breakeven = [s for s in grid_results if s['strategy_params']['breakeven_trigger_pct'] is not None]
        strategy_E = max(with_breakeven, key=lambda x: x['composite_score']) if with_breakeven else None

        # Strategy F: Best win rate with RR >= 1.5 and breakeven
        strategy_F = None
        if with_breakeven:
            high_wr_be = sorted(with_breakeven, key=lambda x: x['win_rate'], reverse=True)
            strategy_F = next((s for s in high_wr_be if s['risk_reward'] >= 1.5), None)

        # Collect all valid strategies
        strategies = []
        for name, strat in [('strategy_A', strategy_A), ('strategy_B', strategy_B),
                             ('strategy_C', strategy_C), ('strategy_D', strategy_D),
                             ('strategy_E', strategy_E), ('strategy_F', strategy_F)]:
            if strat:
                params = strat['strategy_params']
                strategies.append({
                    'strategy_name': name,
                    'tp1_pct': float(params['tp1_pct']),
                    'tp2_pct': float(params['tp2_pct']) if params['tp2_pct'] else None,
                    'tp3_pct': float(params['tp3_pct']) if params['tp3_pct'] else None,
                    'sl_pct': float(params['sl_pct']),
                    'trailing_enabled': params['trailing_enabled'],
                    'trailing_activation': float(params['trailing_activation']) if params['trailing_activation'] else None,
                    'trailing_distance': float(params['trailing_distance']) if params['trailing_distance'] else None,
                    'breakeven_trigger_pct': float(params['breakeven_trigger_pct']) if params['breakeven_trigger_pct'] else None
                })

        return strategies

    @classmethod
    def _evaluate_strategy_on_trades(
        cls,
        strategy: Dict,
        trades: List[TradeSetup]
    ) -> Dict:
        """
        Evaluate a strategy on a set of trades

        Returns:
            {
                'win_rate': float,
                'win_count': int,
                'loss_count': int,
                'avg_win': float,
                'avg_loss': float,
                'risk_reward': float,
                'cumulative_pnl': float
            }
        """
        wins = []
        losses = []

        for trade in trades:
            try:
                result = StrategySimulator.simulate_strategy_outcome(trade, strategy)
                pnl = float(result['pnl_pct'])  # Note: key is 'pnl_pct' not 'simulated_pnl_pct'

                if pnl > 0:
                    wins.append(pnl)
                else:
                    losses.append(pnl)
            except Exception as e:
                logger.error(f"Simulation error: {e}")
                continue

        total_trades = len(wins) + len(losses)

        if total_trades == 0:
            return {
                'win_rate': 0.0,
                'win_count': 0,
                'loss_count': 0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'risk_reward': 0.0,
                'cumulative_pnl': 0.0
            }

        win_rate = (len(wins) / total_trades) * 100
        avg_win = statistics.mean(wins) if wins else 0.0
        avg_loss = statistics.mean(losses) if losses else 0.0
        risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 999.0
        cumulative_pnl = sum(wins) + sum(losses)

        return {
            'win_rate': win_rate,
            'win_count': len(wins),
            'loss_count': len(losses),
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'risk_reward': risk_reward,
            'cumulative_pnl': cumulative_pnl
        }

    @classmethod
    def _aggregate_split_results(cls, split_results: List[Dict]) -> Dict:
        """
        Aggregate performance across all train/test splits

        Returns averaged in-sample and out-of-sample metrics with confidence
        """
        # Filter out None results
        valid_splits = [s for s in split_results if s is not None]

        if not valid_splits:
            return {
                'status': 'validation_failed',
                'message': 'No valid splits produced results'
            }

        # Collect performance across all splits for each strategy
        strategy_performance = {}

        for split in valid_splits:
            for strat_result in split['strategies']:
                name = strat_result['strategy_name']

                if name not in strategy_performance:
                    strategy_performance[name] = {
                        'in_sample_wr': [],
                        'out_of_sample_wr': [],
                        'in_sample_rr': [],
                        'out_of_sample_rr': [],
                        'in_sample_pnl': [],
                        'out_of_sample_pnl': [],
                        'overfit_bias': []
                    }

                strategy_performance[name]['in_sample_wr'].append(
                    strat_result['in_sample']['win_rate']
                )
                strategy_performance[name]['out_of_sample_wr'].append(
                    strat_result['out_of_sample']['win_rate']
                )
                strategy_performance[name]['in_sample_rr'].append(
                    strat_result['in_sample']['risk_reward']
                )
                strategy_performance[name]['out_of_sample_rr'].append(
                    strat_result['out_of_sample']['risk_reward']
                )
                strategy_performance[name]['in_sample_pnl'].append(
                    strat_result['in_sample']['cumulative_pnl']
                )
                strategy_performance[name]['out_of_sample_pnl'].append(
                    strat_result['out_of_sample']['cumulative_pnl']
                )
                strategy_performance[name]['overfit_bias'].append(
                    strat_result['overfit_bias']
                )

        # Calculate averages for each strategy
        aggregated_strategies = []

        for name, perf in strategy_performance.items():
            avg_in_sample_wr = statistics.mean(perf['in_sample_wr'])
            avg_out_sample_wr = statistics.mean(perf['out_of_sample_wr'])
            avg_overfit_bias = statistics.mean(perf['overfit_bias'])

            # Confidence: Low bias + consistent performance = high confidence
            wr_std = statistics.stdev(perf['out_of_sample_wr']) if len(perf['out_of_sample_wr']) > 1 else 0
            confidence = cls._calculate_confidence(avg_overfit_bias, wr_std, len(valid_splits))

            aggregated_strategies.append({
                'strategy_name': name,
                'in_sample_win_rate': avg_in_sample_wr,
                'out_of_sample_win_rate': avg_out_sample_wr,
                'in_sample_rr': statistics.mean(perf['in_sample_rr']),
                'out_of_sample_rr': statistics.mean(perf['out_of_sample_rr']),
                'in_sample_pnl': statistics.mean(perf['in_sample_pnl']),
                'out_of_sample_pnl': statistics.mean(perf['out_of_sample_pnl']),
                'overfit_bias': avg_overfit_bias,
                'confidence': confidence,
                'recommendation': cls._make_recommendation(
                    avg_out_sample_wr, avg_overfit_bias, confidence
                )
            })

        # Sort by out-of-sample performance (realistic expectation)
        aggregated_strategies.sort(
            key=lambda x: x['out_of_sample_win_rate'], reverse=True
        )

        # Overall metrics
        all_in_sample_wr = [s['in_sample_win_rate'] for s in aggregated_strategies]
        all_out_sample_wr = [s['out_of_sample_win_rate'] for s in aggregated_strategies]
        all_bias = [s['overfit_bias'] for s in aggregated_strategies]

        return {
            'status': 'success',
            'n_splits': len(valid_splits),
            'strategies': aggregated_strategies,
            'in_sample_avg_win_rate': statistics.mean(all_in_sample_wr),
            'out_of_sample_avg_win_rate': statistics.mean(all_out_sample_wr),
            'overfit_bias': statistics.mean(all_bias),
            'confidence': statistics.mean([s['confidence'] for s in aggregated_strategies]),
            'recommendation': cls._make_overall_recommendation(aggregated_strategies)
        }

    @classmethod
    def _calculate_confidence(
        cls,
        overfit_bias: float,
        performance_std: float,
        n_splits: int
    ) -> float:
        """
        Calculate confidence score (0-1)

        High confidence when:
          - Low overfit bias (< 10%)
          - Consistent performance (low std)
          - Multiple splits tested
        """
        # Bias penalty: More bias = less confidence
        bias_factor = max(0, 1 - abs(overfit_bias) / 30)  # 30% bias = 0 confidence

        # Consistency factor: More variance = less confidence
        consistency_factor = max(0, 1 - performance_std / 50)  # 50% std = 0 confidence

        # Sample size factor: More splits = more confidence
        sample_factor = min(1.0, n_splits / 3.0)  # 3 splits = full confidence

        confidence = (bias_factor * 0.5) + (consistency_factor * 0.3) + (sample_factor * 0.2)

        return round(confidence, 2)

    @classmethod
    def _make_recommendation(
        cls,
        out_sample_wr: float,
        overfit_bias: float,
        confidence: float
    ) -> str:
        """Make recommendation for a single strategy"""
        if confidence < 0.3:
            return "LOW_CONFIDENCE - Collect more data"

        if out_sample_wr >= 60 and overfit_bias < 15:
            return "APPROVED - Ready for Phase III"
        elif out_sample_wr >= 50 and overfit_bias < 25:
            return "CONDITIONAL - Test in Phase II with caution"
        else:
            return "REJECTED - Poor out-of-sample performance"

    @classmethod
    def _make_overall_recommendation(cls, strategies: List[Dict]) -> str:
        """Make overall recommendation for the asset"""
        approved = [s for s in strategies if 'APPROVED' in s['recommendation']]
        conditional = [s for s in strategies if 'CONDITIONAL' in s['recommendation']]

        if len(approved) >= 3:
            return "PROCEED_TO_PHASE_III - Multiple validated strategies"
        elif len(approved) >= 1 or len(conditional) >= 3:
            return "CONTINUE_PHASE_II - Some promising strategies, need more validation"
        else:
            return "CONTINUE_BASELINE - Strategies not validated, collect more data"
