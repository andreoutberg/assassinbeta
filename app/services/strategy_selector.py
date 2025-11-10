"""
Strategy Selector - Picks the best performing strategy for each trade

Evaluates all strategies and selects winner based on recent performance.
Used in Phase II/III to determine which strategy to apply to incoming signals.
"""
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.strategy_models import StrategyPerformance
from app.config.phase_config import PhaseConfig
from app.utils.exceptions import NoEligibleStrategyError
from app.models.strategy_types import StrategyConfig, StrategyPerformanceData, TradePhaseInfo
import logging

logger = logging.getLogger(__name__)


class StrategySelector:
    """Selects best strategy based on performance metrics"""

    @classmethod
    async def get_best_strategy(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> Optional[StrategyConfig]:
        """
        Select best performing eligible strategy

        Returns:
            Strategy config dict with parameters, or None if no eligible strategies
        """
        try:
            logger.debug(f"Selecting best strategy for {symbol} {direction} {webhook_source}")
            
            # Get all strategy performances for this symbol/direction/webhook
            result = await db.execute(
            select(StrategyPerformance).where(
                StrategyPerformance.symbol == symbol,
                StrategyPerformance.direction == direction,
                StrategyPerformance.webhook_source == webhook_source,
                    StrategyPerformance.is_eligible_for_phase3 == True  # Only Phase III eligible
                ).order_by(StrategyPerformance.strategy_score.desc())
            )
            performances = result.scalars().all()

            if not performances:
                logger.info(f"No eligible strategies for {symbol} {direction} - staying in Phase II")
                return None

            # TIE-BREAKING LOGIC
            # If multiple strategies have equal scores, break ties by:
            # 1. Highest win_rate
            # 2. Lowest avg_duration_hours (faster is better)
            # 3. Alphabetical by strategy_name (deterministic fallback)
            
            # Get top score
            top_score = float(performances[0].strategy_score)
            
            # Find all strategies with top score (within 0.001 tolerance for floating point comparison)
            tied_strategies = [
                p for p in performances 
                if abs(float(p.strategy_score) - top_score) < 0.001
            ]
            
            if len(tied_strategies) > 1:
                logger.info(
                    f"Found {len(tied_strategies)} strategies tied at score={top_score:.4f}. "
                    f"Applying tie-breaking rules..."
                )
                
                # Sort by: win_rate DESC, duration ASC, name ASC
                tied_strategies.sort(
                    key=lambda p: (
                        -float(p.win_rate),  # Higher win rate is better (negative for DESC)
                        float(p.avg_duration_hours),  # Lower duration is better
                        p.strategy_name  # Alphabetical tiebreaker
                    )
                )
                
                best = tied_strategies[0]
                logger.info(
                    f"Tie broken: Selected {best.strategy_name} "
                    f"(win_rate={float(best.win_rate):.1f}%, "
                    f"duration={float(best.avg_duration_hours):.2f}h)"
                )
            else:
                # No tie, just use top strategy
                best = performances[0]

            logger.info(
                f"✅ Selected {best.strategy_name} for {symbol} {direction}: "
                f"Score={float(best.strategy_score):.3f}, RR={float(best.risk_reward):.2f}, "
                f"WinRate={float(best.win_rate):.1f}%"
            )

            return StrategyConfig(
                strategy_name=best.strategy_name,
                tp1_pct=float(best.current_tp1_pct) if best.current_tp1_pct else None,
                tp2_pct=float(best.current_tp2_pct) if best.current_tp2_pct else None,
                tp3_pct=float(best.current_tp3_pct) if best.current_tp3_pct else None,
                sl_pct=float(best.current_sl_pct) if best.current_sl_pct else None,
                trailing_enabled=best.current_trailing_enabled,
                trailing_activation=float(best.current_trailing_activation) if best.current_trailing_activation else None,
                trailing_distance=float(best.current_trailing_distance) if best.current_trailing_distance else None
            )
            
        except Exception as e:
            logger.error(
                f"Error selecting best strategy for {symbol} {direction} {webhook_source}: {e}",
                exc_info=True
            )
            raise

    @classmethod
    async def get_all_strategies_performance(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> List[StrategyPerformanceData]:
        """
        Get performance metrics for all 4 strategies

        Used for dashboard display and comparison
        """
        result = await db.execute(
            select(StrategyPerformance).where(
                StrategyPerformance.symbol == symbol,
                StrategyPerformance.direction == direction,
                StrategyPerformance.webhook_source == webhook_source
            ).order_by(StrategyPerformance.strategy_score.desc())
        )
        performances = result.scalars().all()

        from app.models.strategy_types import StrategyCurrentParams

        return [
            StrategyPerformanceData(
                strategy_name=p.strategy_name,
                win_rate=float(p.win_rate) if p.win_rate else 0,
                win_count=p.win_count,
                loss_count=p.loss_count,
                risk_reward=float(p.risk_reward) if p.risk_reward else 0,
                avg_win=float(p.avg_win) if p.avg_win else 0,
                avg_loss=float(p.avg_loss) if p.avg_loss else 0,
                avg_duration_hours=float(p.avg_duration_hours) if p.avg_duration_hours else 0,
                max_duration_hours=float(p.max_duration_hours) if p.max_duration_hours else 0,
                total_pnl=float(p.total_simulated_pnl) if p.total_simulated_pnl else 0,
                strategy_score=float(p.strategy_score) if p.strategy_score else 0,
                is_eligible_phase3=p.is_eligible_for_phase3,
                meets_rr=p.meets_rr_requirement,
                has_real_sl=p.has_real_sl,
                meets_duration=p.meets_duration_requirement,
                trades_analyzed=p.trades_analyzed,
                current_params=StrategyCurrentParams(
                    tp1=float(p.current_tp1_pct) if p.current_tp1_pct is not None else None,
                    tp2=float(p.current_tp2_pct) if p.current_tp2_pct is not None else None,
                    tp3=float(p.current_tp3_pct) if p.current_tp3_pct is not None else None,
                    sl=float(p.current_sl_pct) if p.current_sl_pct is not None else None,
                    trailing=p.current_trailing_enabled
                )
            )
            for p in performances
        ]

    @classmethod
    async def determine_trade_phase(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> TradePhaseInfo:
        """
        Determine which phase this symbol/direction is in

        Returns:
            {
                'phase': 'I', 'II', or 'III',
                'baseline_completed': count,
                'best_strategy': strategy_config or None
            }
        """
        from app.database.models import TradeSetup

        # Count completed baseline trades
        result = await db.execute(
            select(TradeSetup).where(
                TradeSetup.symbol == symbol,
                TradeSetup.direction == direction,
                TradeSetup.webhook_source == webhook_source,
                TradeSetup.risk_strategy == 'baseline',
                TradeSetup.status == 'completed'
            )
        )
        baseline_count = len(result.scalars().all())

        if baseline_count < PhaseConfig.PHASE_I_THRESHOLD:
            # Phase I: Data collection
            return TradePhaseInfo(
                phase='I',
                phase_name='Data Collection',
                baseline_completed=baseline_count,
                baseline_needed=PhaseConfig.PHASE_I_THRESHOLD,
                best_strategy=None,
                description='Collecting baseline data with 999999 TP/SL'
            )

        # Phase II or III: Check for eligible strategies
        best_strategy = await cls.get_best_strategy(db, symbol, direction, webhook_source)

        if best_strategy:
            # Phase III: Live trading with best strategy
            return TradePhaseInfo(
                phase='III',
                phase_name='Live Trading',
                baseline_completed=baseline_count,
                best_strategy=best_strategy,
                description=f"Using {best_strategy['strategy_name']}"
            )
        else:
            # Phase II: Strategy optimization (paper trading)
            return TradePhaseInfo(
                phase='II',
                phase_name='Strategy Optimization',
                baseline_completed=baseline_count,
                best_strategy=None,
                description='Paper trading, testing all 4 strategies'
            )

    @classmethod
    async def select_strategy_for_signal(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> Dict:
        """
        Select strategy using dual-track + Thompson Sampling

        PHASE I (Baseline Collection):
        - 100% baseline until 10 trades

        PHASE II (Optimization):
        - 20% baseline (continuous learning)
        - 80% optimized (Thompson Sampling allocation)

        PHASE III (Live Trading):
        - 10% baseline (monitoring)
        - 90% best strategy live

        Returns:
            Dict with keys: phase, phase_name, baseline_completed, is_baseline, selected_strategy
        """
        from app.database.models import TradeSetup

        # Get baseline count
        result = await db.execute(
            select(TradeSetup).where(
                TradeSetup.symbol == symbol,
                TradeSetup.direction == direction,
                TradeSetup.webhook_source == webhook_source,
                TradeSetup.risk_strategy == 'baseline',
                TradeSetup.status == 'completed'
            )
        )
        baseline_count = len(result.scalars().all())

        # PHASE I: Baseline collection
        if baseline_count < PhaseConfig.PHASE_I_THRESHOLD:
            logger.info(f"Phase I: Baseline collection ({baseline_count}/{PhaseConfig.PHASE_I_THRESHOLD})")
            return {
                'phase': 'I',
                'phase_name': 'Baseline Collection',
                'baseline_completed': baseline_count,
                'is_baseline': True,
                'selected_strategy': None
            }

        # Get all strategies and their performance
        strategies = await cls.get_all_strategies_performance(db, symbol, direction, webhook_source)

        if not strategies:
            # No strategies yet, continue baseline
            logger.info(f"No strategies generated, continuing baseline")
            return {
                'phase': 'I',
                'phase_name': 'Baseline Collection (No Strategies)',
                'baseline_completed': baseline_count,
                'is_baseline': True,
                'selected_strategy': None
            }

        # Check if any strategy is Phase III eligible
        eligible = [s for s in strategies if s.get('is_eligible_for_phase3', False)]

        if eligible:
            # PHASE III: Best strategy with baseline monitoring
            import random
            if random.random() < PhaseConfig.PHASE_III_BASELINE_PCT:
                logger.info(f"Phase III: Baseline monitoring ({PhaseConfig.PHASE_III_BASELINE_PCT*100:.0f}%)")
                return {
                    'phase': 'III',
                    'phase_name': 'Live Trading (Baseline Monitor)',
                    'baseline_completed': baseline_count,
                    'is_baseline': True,
                    'selected_strategy': None
                }
            else:
                # Select best strategy
                best = max(eligible, key=lambda x: x.get('strategy_score', 0))
                logger.info(f"Phase III: Live trading {best['strategy_name']} ({(1-PhaseConfig.PHASE_III_BASELINE_PCT)*100:.0f}%)")
                return {
                    'phase': 'III',
                    'phase_name': 'Live Trading',
                    'baseline_completed': baseline_count,
                    'is_baseline': False,
                    'selected_strategy': best
                }
        else:
            # PHASE II: Baseline + Thompson Sampling
            import random
            if random.random() < PhaseConfig.PHASE_II_BASELINE_PCT:
                logger.info(f"Phase II: Baseline collection ({PhaseConfig.PHASE_II_BASELINE_PCT*100:.0f}%)")
                return {
                    'phase': 'II',
                    'phase_name': 'Strategy Optimization (Baseline)',
                    'baseline_completed': baseline_count,
                    'is_baseline': True,
                    'selected_strategy': None
                }
            else:
                # Thompson Sampling allocation
                strategy_name = cls._thompson_sampling(strategies)
                selected_strategy = next((s for s in strategies if s['strategy_name'] == strategy_name), None)
                logger.info(f"Phase II: Testing {strategy_name} ({(1-PhaseConfig.PHASE_II_BASELINE_PCT)*100:.0f}% optimized)")
                return {
                    'phase': 'II',
                    'phase_name': 'Strategy Optimization (Thompson Sampling)',
                    'baseline_completed': baseline_count,
                    'is_baseline': False,
                    'selected_strategy': selected_strategy
                }

    @staticmethod
    def _thompson_sampling(strategies: List[Dict]) -> str:
        """
        Allocate testing budget using Thompson Sampling

        HIGH-WR OPTIMIZED: Winners get significantly more tests, losers get minimal tests
        Uses new thompson_sampling module with:
        - (RR^0.25) × (WR^0.75) scoring
        - Win rate bonuses (1.5x for >70%, 1.2x for >65%)
        - Dynamic minimum allocations based on win rate
        - Temperature=3 for stronger exploitation
        """
        from app.services.thompson_sampling import thompson_sampling_select

        # Use the new high-WR optimized Thompson Sampling
        return thompson_sampling_select(strategies)

    @classmethod
    async def get_strategy_params(
        cls,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        strategy_name: str
    ) -> StrategyConfig:
        """Get strategy parameters from StrategyPerformance"""
        result = await db.execute(
            select(StrategyPerformance).where(
                StrategyPerformance.symbol == symbol,
                StrategyPerformance.direction == direction,
                StrategyPerformance.webhook_source == webhook_source,
                StrategyPerformance.strategy_name == strategy_name
            )
        )
        perf = result.scalar_one_or_none()
        
        if not perf:
            raise NoEligibleStrategyError(f"Strategy {strategy_name} not found")

        return StrategyConfig(
            strategy_name=strategy_name,
            tp1_pct=float(perf.current_tp1_pct) if perf.current_tp1_pct else None,
            tp2_pct=float(perf.current_tp2_pct) if perf.current_tp2_pct else None,
            tp3_pct=float(perf.current_tp3_pct) if perf.current_tp3_pct else None,
            sl_pct=float(perf.current_sl_pct) if perf.current_sl_pct else None,
            trailing_enabled=perf.current_trailing_enabled,
            trailing_activation=float(perf.current_trailing_activation) if perf.current_trailing_activation else None,
            trailing_distance=float(perf.current_trailing_distance) if perf.current_trailing_distance else None
        )
