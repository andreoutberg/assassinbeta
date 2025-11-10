"""
Async Strategy Processor - Non-blocking strategy generation with Signal Quality Validation

Modified version of strategy_processor.py that uses worker queue
for CPU-intensive grid search operations.

CHANGES FROM ORIGINAL:
- Grid search offloaded to worker process (non-blocking)
- Main process remains responsive during optimization
- Job status tracked in Redis Queue
- SIGNAL QUALITY VALIDATION: Only optimizes signals with validated edge

NEW IMPROVEMENT:
- Validates signal quality BEFORE grid search
- Skips optimization if signal has no edge (WR<55% or not significant)
- Only optimizes signals with proven predictive power

USAGE:
    Instead of:
        await StrategyProcessor.process_completed_trade(db, trade)

    Use:
        await AsyncStrategyProcessor.process_completed_trade_async(db, trade)

This will enqueue the grid search to a worker and return immediately.
The worker will handle strategy generation and database updates.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import TradeSetup
from app.services.worker_client import WorkerClient
from app.services.signal_quality_analyzer import SignalQualityAnalyzer
from app.config.phase_config import PhaseConfig
from app.utils.exceptions import (
    InsufficientDataError,
    NoEligibleStrategyError
)
import logging

logger = logging.getLogger(__name__)


class AsyncStrategyProcessor:
    """Non-blocking strategy processor using worker queue"""

    @classmethod
    async def process_completed_trade_async(
        cls,
        db: AsyncSession,
        trade: TradeSetup
    ):
        """
        Process a completed trade asynchronously using worker queue

        Instead of blocking for 10-15 seconds during grid search,
        this enqueues the task to a worker process and returns immediately.

        Args:
            db: Database session
            trade: Completed trade to process

        Returns:
            Job object if grid search enqueued, None if not needed
        """
        logger.info(
            f"🔄 [ASYNC_PROCESSOR] Processing completed trade {trade.id}: "
            f"{trade.symbol} {trade.direction} via {trade.webhook_source}"
        )

        # Only process baseline trades
        if trade.risk_strategy != 'baseline':
            logger.info(
                f"[ASYNC_PROCESSOR] Trade {trade.id} is '{trade.risk_strategy}', "
                f"skipping processing (only baseline trades trigger processing)"
            )
            return None

        symbol = trade.symbol
        direction = trade.direction
        webhook_source = trade.webhook_source

        logger.info(
            f"📊 [ASYNC_PROCESSOR] Baseline trade completed for {symbol} {direction} "
            f"- checking if grid search needed"
        )

        try:
            # Check if we should regenerate strategies
            from app.database.strategy_models import StrategyPerformance
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            # Count completed baseline trades
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

            # Decide if we need to run grid search
            needs_grid_search = False
            reason = ""

            if not strategies_exist and baseline_count >= PhaseConfig.MIN_BASELINE_TRADES:
                needs_grid_search = True
                reason = "first-time generation"
            elif should_regenerate:
                needs_grid_search = True
                reason = f"regeneration (every {PhaseConfig.REGENERATION_INTERVAL} trades)"

            # CRITICAL IMPROVEMENT: Validate signal quality BEFORE grid search
            if needs_grid_search:
                logger.info(f"🔍 [ASYNC_PROCESSOR] Validating signal quality before optimization...")

                # Analyze signal quality
                signal_quality = await SignalQualityAnalyzer.analyze_signal(
                    db, symbol, direction, webhook_source
                )

                # Check if signal has edge
                if not signal_quality['has_edge']:
                    logger.warning(
                        f"⚠️ [ASYNC_PROCESSOR] Signal lacks edge - SKIPPING optimization: "
                        f"{symbol} {direction} {webhook_source} - "
                        f"WR: {signal_quality['raw_win_rate']}%, "
                        f"Recommendation: {signal_quality['recommendation']}, "
                        f"Sample: {signal_quality['sample_size']} trades"
                    )
                    return None  # Don't waste time optimizing bad signals

                # Check recommendation
                if signal_quality['recommendation'] == 'collect_more_data':
                    logger.info(
                        f"📊 [ASYNC_PROCESSOR] Need more baseline data: "
                        f"{signal_quality['sample_size']}/{PhaseConfig.MIN_BASELINE_TRADES} trades - "
                        f"Waiting for sufficient sample size"
                    )
                    return None

                logger.info(
                    f"✅ [ASYNC_PROCESSOR] Signal validated with edge: "
                    f"WR: {signal_quality['raw_win_rate']}% "
                    f"(CI: {signal_quality['confidence_interval']}, "
                    f"Quality: {signal_quality['quality_score']}/100) - "
                    f"Proceeding with optimization"
                )

            if needs_grid_search:
                logger.info(
                    f"🎯 [ASYNC_PROCESSOR] Grid search needed for {symbol} {direction}: {reason} "
                    f"(baseline_count={baseline_count})"
                )

                # Enqueue grid search to worker process (non-blocking)
                job = await WorkerClient.enqueue_grid_search(
                    trade_id=trade.id,
                    symbol=symbol,
                    direction=direction,
                    webhook_source=webhook_source
                )

                logger.info(
                    f"✅ [ASYNC_PROCESSOR] Grid search enqueued for trade {trade.id}: job_id={job.id}"
                )

                return job

            else:
                if strategies_exist:
                    next_regen = ((baseline_count // PhaseConfig.REGENERATION_INTERVAL) + 1) * PhaseConfig.REGENERATION_INTERVAL
                    logger.info(
                        f"✓ [ASYNC_PROCESSOR] Using existing strategies for {symbol} {direction} - "
                        f"baseline_count={baseline_count}, next regeneration at {next_regen} trades "
                        f"({next_regen - baseline_count} trades away)"
                    )
                else:
                    logger.info(
                        f"ℹ️ [ASYNC_PROCESSOR] Insufficient baseline data for {symbol} {direction} - "
                        f"need {PhaseConfig.MIN_BASELINE_TRADES}+ trades (have {baseline_count})"
                    )

                return None

        except Exception as e:
            logger.error(
                f"❌ [ASYNC_PROCESSOR] Error checking grid search need for trade {trade.id}: {e}",
                exc_info=True
            )
            raise

    @classmethod
    async def check_job_status(cls, job_id: str) -> dict:
        """
        Check status of an enqueued grid search job

        Args:
            job_id: RQ job ID from enqueue_grid_search

        Returns:
            Dict with job status

        Example:
            status = await AsyncStrategyProcessor.check_job_status(job_id)
            if status['status'] == 'finished':
                print(f"Strategies generated: {status['result']['strategies_generated']}")
        """
        return await WorkerClient.get_job_status(job_id)

    @classmethod
    async def get_queue_info(cls) -> dict:
        """
        Get information about the worker queue

        Returns:
            Dict with queue statistics
        """
        return await WorkerClient.get_queue_info()
