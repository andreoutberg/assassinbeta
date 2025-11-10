"""
Post-Trade Analyzer

Handles post-trade operations:
1. AI analysis of trade outcomes
2. Asset statistics updates
3. R/R circuit breaker checks
4. Strategy simulation
5. Price sample cleanup
"""
from datetime import datetime
from decimal import Decimal
import logging

from app.database.models import TradeSetup, TradePriceSample
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PostTradeAnalyzer:
    """
    Performs comprehensive post-trade analysis and cleanup

    Operations:
    - AI analysis (pattern recognition, market regime, lessons learned)
    - Strategy simulation (backtest all 3 strategies on actual price data)
    - Statistics update (win/loss tracking, R/R calculation)
    - Circuit breaker check (live trading eligibility)
    - Price sample cleanup (delete to keep DB small)
    """

    async def analyze_trade(self, trade: TradeSetup, outcome: str, final_pnl: float, db: AsyncSession):
        """
        Run AI analysis on completed trade

        Analyzes WHY the trade won/lost to build knowledge base
        """
        try:
            from app.services.ai_analyzer import get_analyzer
            analyzer = get_analyzer()

            ai_insights = await analyzer.analyze_trade_outcome(
                trade=trade,
                final_outcome=outcome,
                final_pnl=final_pnl
            )

            # Store AI insights in database
            trade.ai_post_analysis = ai_insights.get('analysis')
            trade.ai_pattern = ai_insights.get('pattern')
            trade.ai_market_regime = ai_insights.get('market_regime')
            trade.ai_lessons = ai_insights.get('lessons')
            trade.ai_assessment_accuracy = ai_insights.get('ai_assessment_accuracy')

            await db.commit()

            logger.info(
                f"🤖 AI Post-Analysis: Pattern={ai_insights.get('pattern')}, "
                f"Regime={ai_insights.get('market_regime')}, "
                f"Accuracy={ai_insights.get('ai_assessment_accuracy')}"
            )
        except Exception as e:
            logger.error(f"❌ AI post-trade analysis failed (non-blocking): {e}")

    async def simulate_strategies(self, trade: TradeSetup, db: AsyncSession):
        """
        Simulate all 3 strategies on actual price data

        Enables fair comparison between strategies using same market conditions
        """
        from app.services.strategy_simulator import StrategySimulator
        try:
            await StrategySimulator.simulate_all_strategies_for_trade(trade, db)
        except Exception as e:
            logger.error(f"❌ Strategy simulation failed for trade {trade.id}: {e}")

    async def update_statistics(self, trade: TradeSetup, final_pnl: float, db: AsyncSession):
        """
        Update asset statistics and check circuit breaker

        Operations:
        1. Update cumulative wins/losses
        2. Calculate cumulative R/R
        3. Check circuit breaker threshold
        4. Determine live trading eligibility
        5. Recalculate all asset statistics
        """
        from app.services.statistics_engine import StatisticsEngine
        stats_engine = StatisticsEngine()
        stats = await stats_engine.get_asset_statistics(trade.symbol, db)

        if stats:
            # Update cumulative wins/losses
            if final_pnl > 0:
                stats.cumulative_wins_usd = (stats.cumulative_wins_usd or Decimal("0")) + Decimal(str(abs(final_pnl)))
                logger.info(f"💰 {trade.symbol}: Win +{final_pnl:.2f}% (Total wins: ${stats.cumulative_wins_usd})")
            else:
                stats.cumulative_losses_usd = (stats.cumulative_losses_usd or Decimal("0")) + Decimal(str(abs(final_pnl)))
                logger.info(f"📉 {trade.symbol}: Loss {final_pnl:.2f}% (Total losses: ${stats.cumulative_losses_usd})")

            # Recalculate cumulative R/R
            if stats.cumulative_losses_usd and stats.cumulative_losses_usd > 0:
                stats.cumulative_rr = stats.cumulative_wins_usd / stats.cumulative_losses_usd
            else:
                stats.cumulative_rr = stats.cumulative_wins_usd

            stats.last_rr_check = datetime.utcnow()

            # Check circuit breaker threshold and live trading eligibility
            rr = float(stats.cumulative_rr)
            completed = stats.completed_setups

            # Phase 1-2: Must complete 20 setups before live trading (10 baseline + 10 optimization)
            if completed < 20:
                stats.is_live_trading = False
                logger.info(
                    f"📊 {trade.symbol}: Setup {completed}/20 complete → PAPER MODE (baseline/optimization phase)"
                )
            # Phase 3: Check circuit breaker (R/R must be >= 1.0 for live trading)
            elif rr < 1.0:
                stats.is_live_trading = False
                deficit = float(stats.cumulative_losses_usd - stats.cumulative_wins_usd)
                logger.warning(
                    f"🚨 CIRCUIT BREAKER TRIGGERED: {trade.symbol} R/R={rr:.4f} < 1.0 "
                    f"(Deficit: ${deficit:.2f}) → PAPER MODE"
                )
            else:
                stats.is_live_trading = True
                logger.info(f"✅ {trade.symbol} R/R: {rr:.4f}, {completed} setups → LIVE MODE")

            await db.commit()

        # Update asset statistics (trigger recalculation)
        await stats_engine.update_asset_statistics(trade.symbol, db)

    async def cleanup_price_samples(self, trade: TradeSetup, db: AsyncSession):
        """
        Delete price samples after trade completes

        Keeps database size small by removing temporary tick data
        Should be called AFTER strategy simulation (which needs the samples)
        """
        from sqlalchemy import delete
        await db.execute(
            delete(TradePriceSample).where(TradePriceSample.trade_setup_id == trade.id)
        )
        logger.info(f"🗑️ Cleaned up price samples for trade {trade.id}")
        await db.commit()

    async def process_completed_trade(
        self,
        trade: TradeSetup,
        outcome: str,
        final_pnl: float,
        db: AsyncSession
    ):
        """
        Complete post-trade processing pipeline

        Call this when a trade closes to run all analysis steps
        """
        # 1. AI analysis
        await self.analyze_trade(trade, outcome, final_pnl, db)

        # 2. Simulate all 3 strategies (BEFORE deleting price samples!)
        await self.simulate_strategies(trade, db)

        # 3. Cleanup price samples (NOW safe since simulation is done)
        await self.cleanup_price_samples(trade, db)

        # 4. Update statistics and circuit breaker
        await self.update_statistics(trade, final_pnl, db)
