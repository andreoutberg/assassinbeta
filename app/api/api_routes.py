"""
FastAPI Routes - Andre Assassin Trading Analysis API

THE ENTRY POINT: POST /api/webhook/tradingview
Receives TradingView webhooks, creates trade setups, starts real-time tracking.

Other endpoints: Trade management, statistics, analytics, health checks.
"""

import logging
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, status, Header
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.config.phase_config import PhaseConfig
from app.database.database import check_db_health, get_db, get_pool_stats
from app.api.deps import rate_limit_low, rate_limit_standard
from app.database.models import (
    AssetStatistics,
    PriceAction,
    TradePriceSample,
    TradeSetup,
    TradeMilestones,
)
from app.services.price_tracker import PriceTracker
from app.services.statistics_engine import StatisticsEngine
from app.services.websocket_manager import get_websocket_manager
from app.services.strategy_selector import StrategySelector
from app.services.strategy_processor_async import AsyncStrategyProcessor
from app.services.asset_health_monitor import AssetHealthMonitor
from app.utils.symbol_utils import normalize_symbol, get_display_symbol

logger = logging.getLogger(__name__)

router = APIRouter()

# Global instances (initialized in main.py)
price_tracker: Optional[PriceTracker] = None
statistics_engine: Optional[StatisticsEngine] = None


# Background task wrapper for strategy processing
# Creates its own database session (FastAPI sessions close after response)
async def _process_completed_trade_background(trade_id: int):
    """
    Background task wrapper that creates a new database session.

    This is necessary because FastAPI dependency-injected sessions (get_db)
    close after the HTTP response is sent, but background tasks run AFTER.

    Args:
        trade_id: ID of the completed trade to process
    """
    from app.database.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            # Fetch the trade with eager loading of milestones relationship
            from sqlalchemy.orm import selectinload
            result = await db.execute(
                select(TradeSetup)
                .where(TradeSetup.id == trade_id)
                .options(selectinload(TradeSetup.milestones))
            )
            trade = result.scalar_one_or_none()

            if not trade:
                logger.error(f"❌ Background task: Trade {trade_id} not found")
                return

            # Process the completed trade asynchronously (enqueues grid search to worker)
            await AsyncStrategyProcessor.process_completed_trade_async(db, trade)

            # Update asset health monitoring (Phase 3 circuit breaker)
            # Determine current phase for this asset
            from app.services.strategy_selector import StrategySelector
            phase_info = await StrategySelector.determine_trade_phase(
                db, trade.symbol, trade.direction, trade.webhook_source
            )
            await AssetHealthMonitor.update_asset_health(
                db, trade.symbol, trade.direction, trade.webhook_source, phase_info['phase']
            )

            logger.info(f"✅ Background task completed for trade {trade_id}")

        except Exception as e:
            logger.error(
                f"❌ Background task failed for trade {trade_id}: {e}",
                exc_info=True
            )
            await db.rollback()
        finally:
            await db.close()


async def get_current_pnl_for_trade(trade: TradeSetup, db: AsyncSession) -> float:
    """
    Get current P&L for a trade (completed or active).
    
    For completed trades: returns final_pnl_pct
    For active trades: queries latest TradePriceSample for actual current PnL
    
    Returns:
        Current P&L percentage (can be negative)
    """
    if trade.status == "completed":
        return float(trade.final_pnl_pct or 0)
    
    # For active trades, get latest price sample
    latest_sample_query = select(TradePriceSample).where(
        TradePriceSample.trade_setup_id == trade.id
    ).order_by(TradePriceSample.timestamp.desc()).limit(1)
    
    latest_sample_result = await db.execute(latest_sample_query)
    latest_sample = latest_sample_result.scalar_one_or_none()
    
    if latest_sample:
        return float(latest_sample.pnl_pct)
    else:
        return 0.0


def init_services(tracker: PriceTracker, stats_engine: StatisticsEngine):
    """
    Initialize global service instances

    Called from main.py during startup
    """
    global price_tracker, statistics_engine
    price_tracker = tracker
    statistics_engine = stats_engine


async def run_ai_evaluation_background(
    trade_id: int,
    ccxt_symbol: str,
    direction: str,
    entry_price: float,
    timeframe: str,
    indicators: dict
):
    """
    Run AI evaluation in background and update trade record
    
    This prevents blocking the webhook response (which was causing 30s timeouts)
    """
    logger.info(f"🤖 Starting background AI evaluation for trade {trade_id}")
    
    try:
        from app.services.ai_analyzer import get_analyzer
        from app.database.database import AsyncSessionLocal
        
        analyzer = get_analyzer()
        
        # Run AI evaluation (can take 30+ seconds)
        ai_evaluation = await analyzer.evaluate_setup_quality(
            symbol=ccxt_symbol,
            direction=direction,
            entry_price=entry_price,
            timeframe=timeframe,
            indicators=indicators
        )
        
        logger.info(
            f"🤖 Background AI Evaluation Complete (Trade {trade_id}): "
            f"Quality={ai_evaluation.get('quality_score', 0)}/10, "
            f"Confidence={ai_evaluation.get('confidence', 0):.2f}, "
            f"Action={ai_evaluation.get('recommended_action', 'unknown')}"
        )
        
        # Update trade record with AI evaluation
        async with AsyncSessionLocal() as db:
            trade = await db.get(TradeSetup, trade_id)
            if trade:
                trade.ai_quality_score = Decimal(str(ai_evaluation.get('quality_score', 5.0)))
                trade.ai_confidence = Decimal(str(ai_evaluation.get('confidence', 0.0)))
                trade.ai_setup_type = ai_evaluation.get('setup_type')
                trade.ai_red_flags = ai_evaluation.get('key_divergences')
                trade.ai_green_lights = ai_evaluation.get('key_confluences')
                trade.ai_reasoning = ai_evaluation.get('narrative')
                trade.ai_recommended_action = ai_evaluation.get('recommended_action')
                await db.commit()
                logger.info(f"✅ Updated trade {trade_id} with AI evaluation results")
            else:
                logger.error(f"❌ Trade {trade_id} not found for AI evaluation update")
                
    except Exception as e:
        logger.error(f"❌ Background AI evaluation failed for trade {trade_id}: {e}", exc_info=True)


# ============================================================================
# WEBHOOK ENDPOINT - THE ENTRY POINT FOR ALL TRADES
# ============================================================================


@router.post("/webhook/tradingview", dependencies=[Depends(rate_limit_low)], status_code=status.HTTP_201_CREATED)
async def receive_tradingview_webhook(
    webhook: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    x_webhook_signature: Optional[str] = Header(None)
):
    """
    Receive TradingView webhook and create trade setup

    **THE ENTRY POINT** for all trading signals.

    Minimum Required Fields:
        - symbol: "BTCUSDT"
        - direction: "LONG" or "SHORT"
        - entry_price: 43500.50
        - timeframe: "15m"

    Optional Fields:
        - exchange: "binance" (default)
        - setup_type: "breakout", "scalp", etc.
        - confidence: 0.85 (0.0-1.0)
        - webhook_source: "scalping_strategy_v2"
        - indicators: {"rsi": 65.5, "macd": 0.45}
        - ohlcv: {"open": 43400, "high": 43600, "low": 43300, "close": 43500, "volume": 1000}

    Process:
    1. Validate required fields
    2. Log price action to database
    3. Get or generate optimal TP/SL levels (learned or defaults)
    4. Create trade setup
    5. Start real-time price tracking (WebSocket)
    6. Trigger AI analysis in background (Claude Haiku)

    Returns:
        {
            "status": "success",
            "trade_id": 123,
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_price": 43500.50,
            "learned_levels": {
                "tp1": "1.25%",
                "tp2": "2.50%",
                "tp3": "4.00%",
                "sl": "-2.20%",
                "confidence": "high",
                "sample_size": 50
            },
            "tracking": "active"
        }
    """
    # DEBUG: Confirm webhook received
    logger.warning(f"📥 WEBHOOK RECEIVED: {webhook.get('symbol')} {webhook.get('direction')}")

    # Verify webhook signature if secret is configured
    webhook_secret = getattr(settings, 'WEBHOOK_SECRET', None)
    if webhook_secret and x_webhook_signature:
        import json
        # Compute expected signature
        webhook_bytes = json.dumps(webhook, sort_keys=True).encode('utf-8')
        expected_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            webhook_bytes,
            hashlib.sha256
        ).hexdigest()

        # Compare signatures (constant-time comparison)
        if not hmac.compare_digest(x_webhook_signature, expected_signature):
            logger.warning(f"⚠️ Invalid webhook signature for {webhook.get('symbol')}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature"
            )
        logger.debug("✅ Webhook signature verified")
    elif webhook_secret and not x_webhook_signature:
        logger.warning(f"⚠️ Missing webhook signature for {webhook.get('symbol')}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook signature required"
        )

    # Handle HEALTHCHECK webhooks (monitoring/uptime checks)
    if webhook.get('symbol', '').upper() == 'HEALTHCHECK':
        logger.info("✅ HEALTHCHECK webhook received - responding OK")
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "andre-assassin",
            "version": "1.0.0"
        }

    # Validate required fields
    required_fields = ["symbol", "direction", "entry_price", "timeframe"]
    missing = [f for f in required_fields if f not in webhook]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Missing required fields: {missing}"
        )

    # Validate direction (allow lowercase and uppercase)
    direction_upper = webhook["direction"].upper()
    if direction_upper not in ["LONG", "SHORT"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="direction must be 'LONG' or 'SHORT' (case insensitive)"
        )

    symbol = webhook["symbol"]  # Original TradingView symbol (e.g., "HIPPOUSDT.P")
    direction = direction_upper
    entry_price = float(webhook["entry_price"])
    timeframe = webhook["timeframe"]

    # Normalize symbol for exchange compatibility
    try:
        ccxt_symbol, base_asset, is_perpetual = normalize_symbol(symbol)
        logger.info(
            f"📥 Webhook received: {symbol} → {ccxt_symbol} ({base_asset}, perp={is_perpetual}) "
            f"{direction} @ {entry_price} ({timeframe})"
        )
    except ValueError as e:
        logger.error(f"❌ Symbol normalization failed for {symbol}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid symbol format: {symbol}. Error: {str(e)}"
        )

    # 1. Log price action (OHLCV + indicators)
    price_action = PriceAction(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.now(timezone.utc),
        open=Decimal(str(webhook.get("ohlcv", {}).get("open", entry_price))),
        high=Decimal(str(webhook.get("ohlcv", {}).get("high", entry_price))),
        low=Decimal(str(webhook.get("ohlcv", {}).get("low", entry_price))),
        close=Decimal(str(entry_price)),
        volume=(
            Decimal(str(webhook.get("ohlcv", {}).get("volume", 0)))
            if webhook.get("ohlcv", {}).get("volume")
            else None
        ),
        indicators=webhook.get("indicators"),  # JSONB
    )
    db.add(price_action)
    await db.flush()  # Get price_action.id

    # 2. Get asset statistics (needed for R/R updates during signal closes)
    stats = await statistics_engine.get_asset_statistics(symbol, db)

    # 3. SIGNAL-BASED CLOSE LOGIC (NEW!)
    # Check for existing open trades from the same system/symbol
    # Close them before opening the new trade
    webhook_source = webhook.get("webhook_source", "tradingview")

    # Query active trades for this symbol + system
    existing_trades_query = select(TradeSetup).where(
        TradeSetup.symbol == symbol,
        TradeSetup.webhook_source == webhook_source,
        TradeSetup.status == "active"
    )
    result = await db.execute(existing_trades_query)
    existing_trades = result.scalars().all()

    if existing_trades:
        logger.info(f"🔄 Found {len(existing_trades)} active trade(s) for {symbol} ({webhook_source})")

        for existing_trade in existing_trades:
            # Calculate duration before closing
            duration_hours = (datetime.now(timezone.utc) - existing_trade.entry_timestamp).total_seconds() / 3600
            
            # Close the existing trade (signal-based close, not TP/SL)
            existing_trade.status = "completed"
            existing_trade.completed_at = datetime.now(timezone.utc)
            existing_trade.final_outcome = "signal_close"  # New outcome type
            
            # Enhanced logging for signal closures
            logger.warning(
                f"🔄 NEW WEBHOOK CLOSING TRADE | "
                f"Old Trade ID: {existing_trade.id} | "
                f"Symbol: {symbol} | "
                f"Old Direction: {existing_trade.direction} → New Direction: {direction} | "
                f"Duration: {duration_hours:.2f}h | "
                f"Source: {webhook_source} | "
                f"Risk Strategy: {existing_trade.risk_strategy} | "
                f"Reason: New webhook received"
            )

            # Calculate final PnL based on current entry price
            if existing_trade.direction == "LONG":
                pnl_pct = ((entry_price - float(existing_trade.entry_price)) / float(existing_trade.entry_price)) * 100
            else:  # SHORT
                pnl_pct = ((float(existing_trade.entry_price) - entry_price) / float(existing_trade.entry_price)) * 100

            existing_trade.final_pnl_pct = Decimal(str(pnl_pct))

            # Log the close
            close_reason = "opposite_direction" if existing_trade.direction != direction else "same_direction_replace"
            logger.info(
                f"✅ Closed trade {existing_trade.id}: {existing_trade.direction} → {direction} "
                f"(PnL: {pnl_pct:+.2f}%, reason: {close_reason})"
            )

            # Stop price tracking for this trade
            if price_tracker:
                await price_tracker.remove_trade(existing_trade.id, db)
            
            # Add background task to process strategies (Phase II/III optimization)
            # IMPORTANT: Pass trade_id instead of db session (session closes after response)
            if existing_trade.risk_strategy == 'baseline' and existing_trade.status == 'completed':
                trade_id_to_process = existing_trade.id
                background_tasks.add_task(
                    _process_completed_trade_background,
                    trade_id_to_process
                )
                logger.info(f"📊 Strategy processing queued for trade {trade_id_to_process}")

            # Update asset statistics with PnL
            if stats:
                if pnl_pct > 0:
                    stats.cumulative_wins_usd = (stats.cumulative_wins_usd or Decimal("0")) + Decimal(str(abs(pnl_pct)))
                else:
                    stats.cumulative_losses_usd = (stats.cumulative_losses_usd or Decimal("0")) + Decimal(str(abs(pnl_pct)))

                # Recalculate cumulative R/R
                if stats.cumulative_losses_usd and stats.cumulative_losses_usd > 0:
                    stats.cumulative_rr = stats.cumulative_wins_usd / stats.cumulative_losses_usd
                else:
                    stats.cumulative_rr = stats.cumulative_wins_usd

                stats.last_rr_check = datetime.now(timezone.utc)
                logger.info(f"📊 Updated {symbol} R/R: {float(stats.cumulative_rr):.4f}")

    # 4. CIRCUIT BREAKER: Check asset R/R status for live vs paper trading
    cumulative_rr = float(stats.cumulative_rr) if stats and stats.cumulative_rr else 0.0

    if stats and cumulative_rr < 1.0 and stats.completed_setups >= 10:
        # Asset underperforming - switch to paper trading
        trade_mode = "paper"
        deficit_needed = float(stats.cumulative_losses_usd - stats.cumulative_wins_usd)
        logger.warning(
            f"📄 PAPER TRADE MODE: {symbol} R/R={cumulative_rr:.4f} < 1.0 "
            f"(needs ${deficit_needed:.2f} profit to resume live trading)"
        )
        if stats:
            stats.is_live_trading = False
            stats.paper_trade_count = (stats.paper_trade_count or 0) + 1
    else:
        # Asset performing well or new - live trading
        trade_mode = "live"
        if cumulative_rr > 0:
            logger.info(f"💰 LIVE TRADE MODE: {symbol} R/R={cumulative_rr:.4f}")
        else:
            logger.info(f"🆕 NEW ASSET: {symbol} - starting with live trading")
        if stats:
            stats.is_live_trading = True

    # 4. STRATEGY PHASE DETERMINATION (3-Phase System)
    # Phase I: Data collection (baseline)
    # Phase II: Strategy optimization (Thompson Sampling with 20/80 allocation)
    # Phase III: Live trading (90% best strategy, 10% baseline)

    logger.info(f"🔍 Selecting strategy for {symbol} {direction} ({webhook_source})")

    # Use select_strategy_for_signal() which implements Thompson Sampling
    selection_result = await StrategySelector.select_strategy_for_signal(
        db, symbol, direction, webhook_source
    )

    current_phase = selection_result['phase']
    baseline_completed = selection_result['baseline_completed']
    selected_strategy = selection_result.get('selected_strategy')
    is_baseline = selection_result.get('is_baseline', False)

    logger.info(
        f"📊 Phase {current_phase}: {selection_result['phase_name']} | "
        f"Baseline: {baseline_completed}/10 | "
        f"Selected: {'baseline' if is_baseline else selected_strategy['strategy_name'] if selected_strategy else 'None'}"
    )
    
    # CIRCUIT BREAKER: Check if asset is paused/blacklisted (Phase II and III only)
    # Phase I is pure data collection - no blacklisting during baseline data gathering
    if current_phase in ['II', 'III']:
        asset_status = await AssetHealthMonitor.check_asset_status(db, symbol, direction, webhook_source)
        if asset_status == 'paused':
            logger.warning(
                f"⚠️ Asset {symbol} {direction} ({webhook_source}) is PAUSED in Phase {current_phase} - skipping trade creation"
            )
            return {
                "status": "skipped",
                "reason": "asset_paused",
                "symbol": symbol,
                "direction": direction,
                "message": "Asset temporarily paused due to poor performance. Will auto-resume in 7 days or after manual review."
            }
        elif asset_status == 'blacklisted':
            logger.error(
                f"🛑 Asset {symbol} {direction} ({webhook_source}) is BLACKLISTED in Phase {current_phase} - rejecting trade"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Asset {symbol} {direction} is blacklisted due to consistent losses in Phase {current_phase}. Manual review required."
            )
    
    # Determine TP/SL based on selected strategy
    if is_baseline:
        # Baseline trade (100% in Phase I, 20% in Phase II, 10% in Phase III)
        tp1_pct = 999999.0
        tp2_pct = 999999.0
        tp3_pct = 999999.0
        sl_pct = -999999.0
        risk_strategy = 'baseline'
        trailing_enabled = False
        trailing_activation_pct = None
        trailing_distance_pct = None
        confidence = "baseline"
        sample_size = baseline_completed
        # Always paper mode unless live trading is explicitly enabled
        trade_mode = 'paper' if not PhaseConfig.ENABLE_LIVE_TRADING else ('paper' if current_phase in ['I', 'II'] else 'live')

        logger.warning(
            f"📊 BASELINE TRADE (Phase {current_phase}): {symbol} {direction} "
            f"- NO TP/SL (24-hour timeout for data collection)"
        )
    else:
        # Strategy-based trade (Phase II: 80%, Phase III: 90%)
        # selected_strategy is a StrategyPerformanceData TypedDict with nested current_params
        params = selected_strategy['current_params']  # TypedDict access
        tp1_pct = params['tp1']
        tp2_pct = params['tp2']
        tp3_pct = params['tp3']
        sl_pct = params['sl']
        risk_strategy = selected_strategy['strategy_name']
        trailing_enabled = params['trailing']
        trailing_activation_pct = None  # Not in current_params
        trailing_distance_pct = None  # Not in current_params
        sample_size = baseline_completed

        # Validate strategy parameters - must have valid TP and SL
        # If strategy has invalid params (e.g., all zeros like strategy_E), fall back to baseline
        if not tp1_pct or not sl_pct or abs(tp1_pct) < 0.1 or abs(sl_pct) < 0.1:
            logger.warning(
                f"⚠️ Strategy {risk_strategy} has invalid parameters (TP1={tp1_pct}, SL={sl_pct}). "
                f"Falling back to baseline trade."
            )
            # Switch to baseline mode
            tp1_pct = 999999.0
            tp2_pct = 999999.0
            tp3_pct = 999999.0
            sl_pct = -999999.0
            risk_strategy = 'baseline'
            trailing_enabled = False
            trailing_activation_pct = None
            trailing_distance_pct = None
            confidence = "baseline"
            trade_mode = 'paper' if not PhaseConfig.ENABLE_LIVE_TRADING else ('paper' if current_phase in ['I', 'II'] else 'live')
            baseline_mode = True
            logger.warning(
                f"📊 FALLBACK TO BASELINE (Phase {current_phase}): {symbol} {direction} "
                f"- NO TP/SL (24-hour timeout for data collection)"
            )
        elif current_phase == 'II':
            trade_mode = 'paper'
            confidence = "optimizing"
            logger.info(
                f"✅ PHASE II OPTIMIZATION: Using {risk_strategy} | "
                f"TP1={tp1_pct}% SL={sl_pct}% Trailing={trailing_enabled}"
            )
        else:  # Phase III
            # Respect live trading flag
            trade_mode = 'live' if PhaseConfig.ENABLE_LIVE_TRADING else 'paper'
            confidence = "high"
            
            if PhaseConfig.ENABLE_LIVE_TRADING:
                logger.info(
                    f"💰 PHASE III LIVE TRADING: Using {risk_strategy} | "
                    f"TP1={tp1_pct}% SL={sl_pct}% Trailing={trailing_enabled}"
                )
            else:
                logger.info(
                    f"📄 PHASE III PAPER TRADING: Using {risk_strategy} | "
                    f"TP1={tp1_pct}% SL={sl_pct}% Trailing={trailing_enabled} "
                    f"(Live trading disabled)"
                )
    
    # Determine if we're in baseline mode for backward compatibility
    baseline_mode = is_baseline
    
    # 5. MANDATORY STOP LOSS CALCULATION (Skip in baseline mode)
    # Every trade MUST have a learned or default SL (no unlimited risk)
    # EXCEPT baseline mode trades which use 24-hour timeout only
    if not baseline_mode:
        if stats and stats.optimal_sl_pct and stats.completed_setups >= 10:
            sl_pct = float(stats.optimal_sl_pct)
            logger.info(f"✅ Using LEARNED SL: {sl_pct}% (n={stats.completed_setups})")
        else:
            sl_pct = -float(settings.DEFAULT_SL_PCT)  # -3.0% from config
            logger.info(f"⚠️ Using DEFAULT SL: {sl_pct}%")

    # Calculate SL price from entry price
    # Special handling for baseline mode (unreachable SL)
    if baseline_mode:
        # Set SL price to truly unreachable level based on entry price
        if direction == "LONG":
            # For LONG: SL should be far below entry (e.g., entry * 0.0001 or $0.00000001)
            sl_price = entry_price * 0.0001  # 99.99% below entry - truly unreachable
        else:  # SHORT
            # For SHORT: SL should be far above entry (e.g., entry * 100)
            sl_price = entry_price * 100  # 10000% above entry - truly unreachable
        logger.info(f"🛡️ Baseline Mode SL: {sl_price} (unreachable - will timeout)")
    else:
        # Normal SL calculation
        if direction == "LONG":
            sl_price = entry_price * (1 + sl_pct / 100)
        else:  # SHORT
            sl_price = entry_price * (1 - sl_pct / 100)

        # Validate SL price
        if not sl_price or sl_price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid stop loss calculation: sl_price={sl_price}"
            )

        logger.info(f"🛡️ Stop Loss: {sl_price:.8f} ({sl_pct:+.2f}% from entry)")

    # 6. POSITION SIZING (Account Risk Management with Leverage)
    account_risk_usd = settings.ACCOUNT_BALANCE_USD * (settings.MAX_RISK_PER_TRADE_PCT / 100)
    sl_distance_pct = abs(sl_pct)
    leverage = settings.LEVERAGE

    # BASELINE MODE: Fixed position size (0.1% of account), not risk-based
    if baseline_mode:
        # Use fixed percentage of account for baseline data collection
        # 0.1% of $100k = $100 notional position
        notional_position_usd = settings.ACCOUNT_BALANCE_USD * (settings.MAX_RISK_PER_TRADE_PCT / 100)
        margin_required_usd = notional_position_usd / leverage
        logger.info(f"💼 BASELINE MODE Position: ${notional_position_usd:.2f} (fixed 0.1% of account)")
    else:
        # LEARNED MODE: Risk-based position sizing
        # Calculate notional position (total exposure)
        # If we risk $100 on a 3% stop, we need $3,333.33 notional position
        notional_position_usd = account_risk_usd / (sl_distance_pct / 100)

        # Calculate margin required (capital we need to commit with leverage)
        # With 5x leverage, we only need $666.67 margin for $3,333.33 position
        margin_required_usd = notional_position_usd / leverage

    # Backwards compatibility
    position_size_usd = notional_position_usd

    # Calculate Risk/Reward ratio
    tp1_distance_pct = abs(tp1_pct)
    risk_reward_ratio = tp1_distance_pct / sl_distance_pct

    # Validate R/R ratio
    if risk_reward_ratio < settings.MIN_RISK_REWARD_RATIO:
        logger.warning(
            f"⚠️ LOW R/R: {risk_reward_ratio:.2f} < {settings.MIN_RISK_REWARD_RATIO} "
            f"(TP1: {tp1_distance_pct:.2f}% / SL: {sl_distance_pct:.2f}%)"
        )
        # Note: We don't reject, but log for analysis

    logger.info(
        f"💼 Position Sizing: ${notional_position_usd:.2f} notional ({leverage}x leverage) "
        f"| Margin: ${margin_required_usd:.2f} | Risk: ${account_risk_usd:.2f} @ {sl_distance_pct:.2f}% SL | R/R: {risk_reward_ratio:.2f}"
    )

    # 6.5. AI PRE-ENTRY EVALUATION (Moved to Background Task - No Blocking!)
    # Set default values immediately, AI will update trade record asynchronously
    logger.info(f"🤖 AI evaluation will run in background for {symbol} {direction}")
    ai_evaluation = {
        "quality_score": 5.0,  # Neutral default
        "confidence": 0.0,      # Will be updated by background task
        "setup_type": None,
        "key_divergences": None,
        "key_confluences": None,
        "narrative": None,
        "recommended_action": None
    }

    # 6.8. MAX_EXPOSURE_PCT VALIDATION - Enforce total exposure limit (only when live trading)
    # Calculate current total exposure from active trades
    result = await db.execute(
        select(func.sum(TradeSetup.notional_position_usd)).where(TradeSetup.status == 'active')
    )
    total_exposure = result.scalar() or 0

    max_exposure_usd = settings.ACCOUNT_BALANCE_USD * (settings.MAX_EXPOSURE_PCT / 100)

    # Calculate new total exposure (including this trade)
    # Always 1 trade at a time (no more parallel testing)
    trades_to_create = 1
    new_total_exposure = float(total_exposure) + notional_position_usd

    # Only enforce max exposure when live trading is enabled
    if PhaseConfig.ENABLE_LIVE_TRADING and new_total_exposure > max_exposure_usd:
        logger.error(
            f"❌ MAX EXPOSURE EXCEEDED: Current=${total_exposure:.2f}, "
            f"New=${new_total_exposure:.2f}, Max=${max_exposure_usd:.2f} ({settings.MAX_EXPOSURE_PCT}%)"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Max exposure exceeded: ${new_total_exposure:.2f} > ${max_exposure_usd:.2f} ({settings.MAX_EXPOSURE_PCT}% of account)"
        )

    logger.info(
        f"✅ Exposure Check: Current=${total_exposure:.2f}, "
        f"After Trade=${new_total_exposure:.2f}, Max=${max_exposure_usd:.2f} ({settings.MAX_EXPOSURE_PCT}%)"
    )

    # 7. Create trade - Single trade with selected strategy
    # Phase I: baseline strategy
    # Phase II/III: best performing strategy
    
    created_trades = []
    
    # Always create exactly ONE trade with the current best strategy
    logger.info(
        f"📝 Creating single trade: Phase {current_phase} | Strategy: {risk_strategy} | Mode: {trade_mode}"
    )
    
    # Create trade with strategy configuration
    phase_description = f"Phase {current_phase}: {selection_result['phase_name']}"
    strategy = {
        "name": risk_strategy,
        "label": f"Phase {current_phase}: {risk_strategy}",
        "description": phase_description
    }
    
    # No parallel testing - single trade at a time

    # Generate unique trade identifier
    from app.utils.trade_identifier import TradeIdentifierGenerator
    trade_identifier = await TradeIdentifierGenerator.generate_identifier(
        db, symbol, direction, risk_strategy
    )

    # Create the trade
    trade = TradeSetup(
            trade_identifier=trade_identifier,
            symbol=symbol,
            ccxt_symbol=ccxt_symbol,
            exchange=webhook.get("exchange", "binance"),
            timeframe=timeframe,
            direction=direction,
            entry_price=Decimal(str(entry_price)),
            entry_timestamp=datetime.now(timezone.utc),
            setup_type=webhook.get("setup_type", "unknown"),
            confidence_score=Decimal(str(webhook.get("confidence", 0.5))),
            webhook_source=webhook.get("webhook_source", "tradingview"),
            planned_tp1_pct=Decimal(str(tp1_pct)) if tp1_pct is not None else None,
            planned_tp2_pct=Decimal(str(tp2_pct)) if tp2_pct is not None else None,
            planned_tp3_pct=Decimal(str(tp3_pct)) if tp3_pct is not None else None,
            planned_sl_pct=Decimal(str(sl_pct)) if sl_pct is not None else None,
            planned_sl_price=Decimal(str(sl_price)),
            trade_mode=trade_mode,
            position_size_usd=Decimal(str(position_size_usd)),
            notional_position_usd=Decimal(str(notional_position_usd)),
            margin_required_usd=Decimal(str(margin_required_usd)),
            leverage=Decimal(str(leverage)),
            risk_reward_ratio=Decimal(str(risk_reward_ratio)),
            status="active",
            max_drawdown_pct=Decimal("0.0"),
            max_profit_pct=Decimal("0.0"),
            is_parallel_test=False,  # No longer doing parallel testing
            test_group_id=None,  # No test groups
            risk_strategy=risk_strategy,  # baseline, strategy_A, strategy_B, strategy_C, or strategy_D
            # AI Pre-Entry Evaluation (Phase 1: Data Collection - Narrative Analysis)
            ai_quality_score=Decimal(str(ai_evaluation.get('quality_score', 5.0))),
            ai_confidence=Decimal(str(ai_evaluation.get('confidence', 0.0))),
            ai_setup_type=ai_evaluation.get('setup_type'),
            ai_red_flags=ai_evaluation.get('key_divergences'),
            ai_green_lights=ai_evaluation.get('key_confluences'),
            ai_reasoning=ai_evaluation.get('narrative'),
            ai_recommended_action=ai_evaluation.get('recommended_action'),
    )
    
    try:
        db.add(trade)
        await db.commit()
        await db.refresh(trade)

        logger.info(
            "✅ TRADE CREATED %s (ID=%d, Phase=%s, Strategy=%s): %s %s @ %s | TP1=%s%% SL=%s%% | Mode=%s",
            trade.trade_identifier, trade.id, current_phase, risk_strategy, symbol, direction, entry_price, tp1_pct, sl_pct, trade_mode
        )

        created_trades.append(trade)

        # ========== BASELINE DATABASE INTEGRATION (AI Andre Model) ==========
        # After production trade is created, create baseline trade for AI training
        try:
            from app.services.baseline_manager import get_baseline_manager
            baseline_manager = get_baseline_manager()

            await baseline_manager.handle_new_webhook(
                symbol=ccxt_symbol,  # Use CCXT symbol (e.g., 'BTC/USDT')
                direction=direction,
                entry_price=entry_price,
                webhook_source=webhook.get("webhook_source", "tradingview"),
                entry_timestamp=trade.entry_timestamp
            )
            # Note: No await/commit needed - baseline manager handles its own DB session
        except Exception as baseline_error:
            # Log error but don't fail the main webhook - baseline is optional
            logger.error(f"⚠️ Baseline trade creation failed (non-critical): {baseline_error}")
        # ===================================================================

    except Exception as db_error:
            # 🚨 CRITICAL: Database insert failed - log extensively
            logger.error(
                "🚨 WEBHOOK DATABASE INSERT FAILED 🚨\n"
                "Symbol: %s %s\n"
                "Entry: $%s\n"
                "Strategy: %s\n"
                "Webhook Source: %s\n"
                "Error Type: %s\n"
                "Error Message: %s\n"
                "AI Action Length: %d chars\n"
                "---\n"
                "This trade was LOST - webhook needs to be resent!",
                symbol, direction, entry_price, risk_strategy,
                webhook.get("webhook_source", "unknown"),
                type(db_error).__name__, str(db_error),
                len(ai_evaluation.get('recommended_action', '') or '') if ai_evaluation else 0
            )
            await db.rollback()
            raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create trade: {str(db_error)}"
        )
    
    # 4. Execute orders on Bybit (ONLY for non-baseline trades in Phase II/III)
    from app.services.order_executor import OrderExecutor

    for trade in created_trades:
        # NEVER execute baseline trades (they collect data via timeout only)
        if trade.risk_strategy == 'baseline':
            logger.info(
                f"📊 Baseline trade {trade.id} created (NO orders placed - "
                f"will collect data via 24h timeout)"
            )
            continue

        # Execute strategy trades in Phase II (demo testing) and Phase III (demo/live)
        if current_phase in ['II', 'III']:
            try:
                executor = OrderExecutor()
                # Force demo mode in Phase II, respect config in Phase III
                force_demo = (current_phase == 'II') or (not PhaseConfig.ENABLE_LIVE_TRADING)
                success = await executor.execute_trade(trade, db, force_demo=force_demo)
                await executor.close()

                if success:
                    mode = "DEMO" if force_demo else "LIVE"
                    logger.info(
                        f"✅ Phase {current_phase} ({mode}): Bybit orders placed for "
                        f"trade {trade.id} (Strategy: {trade.risk_strategy})"
                    )
                else:
                    logger.warning(
                        f"⚠️ Phase {current_phase}: Bybit order placement skipped/failed "
                        f"for trade {trade.id}"
                    )
            except Exception as e:
                logger.error(
                    f"❌ Phase {current_phase}: Error placing Bybit orders for "
                    f"trade {trade.id}: {e}"
                )
        else:
            # Phase I strategy trades: Paper trading only (shouldn't happen, but handle gracefully)
            logger.info(
                f"📝 Phase {current_phase}: Strategy trade {trade.id} created "
                f"(paper trading only, NO Bybit orders)"
            )

    # 5. Start real-time price tracking (WebSocket) for the trade
    if price_tracker:
        for trade in created_trades:
            await price_tracker.add_trade(trade, db)
            logger.info(f"📡 WebSocket tracking started for trade {trade.id} (Strategy: {trade.risk_strategy})")
    else:
        logger.error("⚠️ Price tracker not initialized - trades will NOT be monitored")

    # 5. Trigger AI analysis in background (Non-blocking - prevents 30s webhook timeout)
    # TEMPORARILY DISABLED - AI evaluation causing 100% CPU usage
    # background_tasks.add_task(
    #     run_ai_evaluation_background,
    #     trade.id,
    #     ccxt_symbol,
    #     direction,
    #     float(entry_price),
    #     timeframe,
    #     webhook.get('indicators', {})
    # )
    logger.info(f"🤖 AI evaluation DISABLED (temporarily) for trade {trade.id}")

    # 6. Return response (single trade created)
    return {
        "status": "success",
        "phase": current_phase,
        "phase_name": selection_result['phase_name'],
        "trade_id": trade.id,
        "strategy": risk_strategy,
        "symbol": symbol,
        "direction": direction,
        "entry_price": float(entry_price),
        "timeframe": timeframe,
        "learned_levels": {
            "tp1": f"{tp1_pct}%",
            "tp2": f"{tp2_pct}%",
            "tp3": f"{tp3_pct}%",
            "sl": f"{sl_pct}%",
            "confidence": confidence,
            "sample_size": sample_size,
        },
        "tracking": "active" if price_tracker else "disabled",
        "timestamp": trade.entry_timestamp.isoformat(),
        "trade_mode": trade_mode,
        "baseline_progress": f"{baseline_completed}/10" if current_phase == 'I' else None,
        "description": phase_description,
        "note": "All 4 strategies simulate in background after trade completes" if current_phase != 'I' else "Collecting baseline data",
    }


# ============================================================================
# TRADE MANAGEMENT ENDPOINTS
# ============================================================================


@router.get("/trades/active", dependencies=[Depends(rate_limit_standard)])
async def get_active_trades(
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 50,  # Pagination for performance
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all active trades

    Query Parameters:
        - symbol: Filter by symbol (e.g., "BTCUSDT")
        - strategy: Filter by webhook_source (e.g., "scalping_strategy_v2")
        - limit: Max trades to return (default: 50)
        - offset: Number of trades to skip (default: 0)

    Returns:
        List of active trades with current P&L, MAE, MFE
    """
    # Get total count first
    from sqlalchemy import func
    count_query = select(func.count()).select_from(TradeSetup).where(TradeSetup.status == "active")
    
    if symbol:
        count_query = count_query.where(TradeSetup.symbol == symbol)
    if strategy:
        count_query = count_query.where(TradeSetup.webhook_source == strategy)
    
    count_result = await db.execute(count_query)
    total_count = count_result.scalar()
    
    # Build main query with pagination
    query = select(TradeSetup).where(TradeSetup.status == "active")

    if symbol:
        query = query.where(TradeSetup.symbol == symbol)
    if strategy:
        query = query.where(TradeSetup.webhook_source == strategy)

    query = query.order_by(TradeSetup.entry_timestamp.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    trades = result.scalars().all()

    # Get all latest price samples in ONE query using DISTINCT ON (fixes N+1 query)
    # Extract trade IDs
    trade_ids = [t.id for t in trades]

    if trade_ids:
        # Use DISTINCT ON for PostgreSQL - gets latest price sample per trade efficiently
        latest_samples_query = (
            select(TradePriceSample)
            .where(TradePriceSample.trade_setup_id.in_(trade_ids))
            .distinct(TradePriceSample.trade_setup_id)
            .order_by(
                TradePriceSample.trade_setup_id,
                TradePriceSample.timestamp.desc()
            )
        )

        latest_samples_result = await db.execute(latest_samples_query)
        latest_samples = latest_samples_result.scalars().all()

        # Create a lookup dict for O(1) access
        latest_sample_map = {sample.trade_setup_id: sample for sample in latest_samples}
    else:
        latest_sample_map = {}

    # Build response with current prices and PnL
    trades_response = []
    for t in trades:
        # Use the pre-fetched latest sample from the map (no additional query!)
        latest_sample = latest_sample_map.get(t.id)

        if latest_sample:
            # Use actual current price and PnL from latest sample
            current_price = float(latest_sample.price)
            current_pnl_pct = float(latest_sample.pnl_pct)
        else:
            # Fallback to entry price if no samples yet
            current_price = float(t.entry_price)
            current_pnl_pct = 0.0

        entry_price = float(t.entry_price)

        # Calculate dollar P&L from percentage and notional position (with leverage)
        notional_usd = float(t.notional_position_usd) if t.notional_position_usd else 0
        current_pnl_usd = (current_pnl_pct / 100) * notional_usd if notional_usd > 0 else None

        trades_response.append({
            "id": t.id,
            "symbol": t.symbol,
            "direction": t.direction,
            "entry_price": entry_price,
            "current_price": round(current_price, 8),
            "current_pnl": current_pnl_usd,  # Dollar P&L
            "current_pnl_pct": current_pnl_pct,
            "entry_time": t.entry_timestamp.isoformat(),
            "max_profit_pct": float(t.max_profit_pct) if t.max_profit_pct else 0,
            "max_drawdown_pct": float(t.max_drawdown_pct) if t.max_drawdown_pct else 0,
            "tp1_hit": t.tp1_hit,
            "tp2_hit": t.tp2_hit,
            "tp3_hit": t.tp3_hit,
            "planned_levels": {
                "tp1": float(t.planned_tp1_pct) if t.planned_tp1_pct else None,
                "tp2": float(t.planned_tp2_pct) if t.planned_tp2_pct else None,
                "tp3": float(t.planned_tp3_pct) if t.planned_tp3_pct else None,
                "sl": float(t.planned_sl_pct) if t.planned_sl_pct else None,
            },
            "strategy": t.webhook_source,
            # Leverage and position fields
            "trade_mode": t.trade_mode,
            "notional_position_usd": notional_usd,
            "margin_required_usd": float(t.margin_required_usd) if t.margin_required_usd else 0,
            "leverage": float(t.leverage) if t.leverage else 1.0,
        })

    return {
        "count": len(trades),  # Number of trades in this page
        "total_count": total_count,  # Total matching trades
        "limit": limit,
        "offset": offset,
        "trades": trades_response,
    }


@router.get("/trades/recent-signals", dependencies=[Depends(rate_limit_standard)])
async def get_recent_signals(limit: int = 10, offset: int = 0, db: AsyncSession = Depends(get_db)):
    """
    Get recent webhook signals (last N trade setups created)

    Returns recent trade setups with entry details, useful for dashboard.
    Supports pagination via limit/offset.
    """
    # Get total count
    from sqlalchemy import func
    count_result = await db.execute(select(func.count()).select_from(TradeSetup))
    total_count = count_result.scalar()
    
    # Get paginated results
    result = await db.execute(
        select(TradeSetup)
        .order_by(TradeSetup.entry_timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    trades = result.scalars().all()

    return {
        "count": len(trades),
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "signals": [
            {
                "id": t.id,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": float(t.entry_price),
                "entry_time": t.entry_timestamp.isoformat(),
                "timeframe": t.timeframe,
                "setup_type": t.setup_type,
                "confidence_score": float(t.confidence_score) if t.confidence_score else None,
                "webhook_source": t.webhook_source,
                "trade_mode": t.trade_mode,
                "status": t.status,
                "risk_strategy": t.risk_strategy,
                "ai_quality_score": float(t.ai_quality_score) if t.ai_quality_score else None,
                "final_outcome": t.final_outcome,
                "final_pnl_pct": float(t.final_pnl_pct) if t.final_pnl_pct else None,
            }
            for t in trades
        ]
    }


@router.get("/trades/live-activity", dependencies=[Depends(rate_limit_standard)])
async def get_live_trading_activity(
    status: Optional[str] = "active",
    period: Optional[str] = "all",
    limit: int = 20,  # Default to 20 trades per page
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    Get trading activity with optional filters

    Args:
        status: Filter by status - "active", "completed", or "all" (default: "active")
        period: Time period - "today", "week", "month", or "all" (default: "all")
        limit: Max number of trades to return (default: 100)
        offset: Number of trades to skip (default: 0)

    Returns active/completed trades with current/final P&L for dashboard display.
    Paginated to improve performance.
    """
    from sqlalchemy.orm import joinedload

    # Build query with status filter - EAGER LOAD milestones to avoid N+1 query
    query = select(TradeSetup).options(joinedload(TradeSetup.milestones))
    
    if status == "active":
        query = query.where(TradeSetup.status == "active")
    elif status == "completed":
        query = query.where(TradeSetup.status == "completed")
    # else: status == "all", no filter
    
    # Add time period filter
    if period == "today":
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.where(TradeSetup.entry_timestamp >= today_start)
    elif period == "week":
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        query = query.where(TradeSetup.entry_timestamp >= week_ago)
    elif period == "month":
        month_ago = datetime.now(timezone.utc) - timedelta(days=30)
        query = query.where(TradeSetup.entry_timestamp >= month_ago)
    # else: period == "all", no filter

    # Get total counts for summary cards (before pagination)
    # Use func.count with CASE for conditional counting
    from sqlalchemy import func, case
    count_query = select(
        func.count().label('total_count'),
        func.count(case((TradeSetup.risk_strategy == 'baseline', 1))).label('baseline_count'),
        func.count(case((TradeSetup.risk_strategy != 'baseline', 1))).label('strategy_count'),
        func.count(case((TradeSetup.trade_mode == 'paper', 1))).label('paper_count'),
        func.count(case((TradeSetup.trade_mode == 'live', 1))).label('live_count'),
        func.sum(TradeSetup.notional_position_usd).label('total_exposure'),
        func.sum(case((TradeSetup.risk_strategy == 'baseline', TradeSetup.notional_position_usd))).label('baseline_exposure'),
        func.sum(case((TradeSetup.risk_strategy != 'baseline', TradeSetup.notional_position_usd))).label('strategy_exposure')
    )
    
    # Apply same filters to count query
    if status == "active":
        count_query = count_query.where(TradeSetup.status == "active")
    elif status == "completed":
        count_query = count_query.where(TradeSetup.status == "completed")
    
    if period == "today":
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        count_query = count_query.where(TradeSetup.entry_timestamp >= today_start)
    elif period == "week":
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        count_query = count_query.where(TradeSetup.entry_timestamp >= week_ago)
    elif period == "month":
        month_ago = datetime.now(timezone.utc) - timedelta(days=30)
        count_query = count_query.where(TradeSetup.entry_timestamp >= month_ago)
    
    # Execute count query
    count_result = await db.execute(count_query)
    counts = count_result.one()

    query = query.order_by(TradeSetup.entry_timestamp.desc())

    # Add pagination
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    trades = result.scalars().unique().all()  # unique() needed with joinedload

    # Milestones are already loaded via joinedload - no separate query needed!
    # Access via trade.milestones relationship
    milestones_by_trade = {t.id: t.milestones for t in trades}

    # Calculate aggregate stats (use appropriate P&L field based on status)
    def get_trade_pnl_pct(t):
        if t.status == 'completed':
            return float(t.final_pnl_pct or 0)
        else:  # active
            return float(t.max_profit_pct or 0)

    # Helper to format milestone data
    def format_milestones(trade, milestones):
        if not milestones:
            return None

        result = {
            "reached": [],
            "pending": [],
            "max_profit_pct": float(milestones.max_profit_pct) if milestones.max_profit_pct else 0,
            "max_drawdown_pct": float(milestones.max_drawdown_pct) if milestones.max_drawdown_pct else 0,
        }

        # Check profit milestones
        profit_thresholds = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 10.0]
        for threshold in profit_thresholds:
            field_name = f"reached_plus_{str(threshold).replace('.', '_').rstrip('0').rstrip('_')}pct_at"
            timestamp = getattr(milestones, field_name, None)

            milestone_data = {
                "pct": threshold,
                "label": f"+{threshold}%",
                "is_tp": False,
            }

            # Check if this matches a TP level
            if trade.planned_tp1_pct and abs(float(trade.planned_tp1_pct) - threshold) < 0.01:
                milestone_data["is_tp"] = True
                milestone_data["tp_level"] = "TP1"
            elif trade.planned_tp2_pct and abs(float(trade.planned_tp2_pct) - threshold) < 0.01:
                milestone_data["is_tp"] = True
                milestone_data["tp_level"] = "TP2"
            elif trade.planned_tp3_pct and abs(float(trade.planned_tp3_pct) - threshold) < 0.01:
                milestone_data["is_tp"] = True
                milestone_data["tp_level"] = "TP3"

            if timestamp:
                milestone_data["timestamp"] = timestamp.isoformat()
                milestone_data["minutes_ago"] = int((datetime.now(timezone.utc) - timestamp).total_seconds() / 60)
                result["reached"].append(milestone_data)
            else:
                # Calculate distance to threshold
                current_pnl = get_trade_pnl_pct(trade)
                if current_pnl < threshold:
                    milestone_data["distance"] = threshold - current_pnl
                    result["pending"].append(milestone_data)

        # Check SL milestones
        drawdown_thresholds = [-0.5, -1.0, -1.5, -2.0, -3.0, -5.0]
        sl_crossed = False
        for threshold in drawdown_thresholds:
            field_name = f"reached_minus_{str(abs(threshold)).replace('.', '_').rstrip('0').rstrip('_')}pct_at"
            timestamp = getattr(milestones, field_name, None)
            if timestamp:
                sl_crossed = True
                break

        result["sl_status"] = {
            "crossed": sl_crossed,
            "current_drawdown": float(milestones.max_drawdown_pct) if milestones.max_drawdown_pct else 0,
            "sl_level": float(trade.planned_sl_pct) if trade.planned_sl_pct else None,
        }

        return result

    # EXCLUDE BASELINE TRADES from P&L calculation (they're data collection only)
    strategy_trades = [t for t in trades if t.risk_strategy != 'baseline']

    # Calculate P&L only for strategy trades (post-baseline optimization)
    # Note: P&L is calculated from paginated trades only (for performance)
    total_pnl = sum(get_trade_pnl_pct(t) * float(t.notional_position_usd or 0) / 100 for t in strategy_trades)

    # Use counts from count query for summary cards (shows TOTAL, not paginated)
    return {
        "count": len(trades),  # Number of trades in THIS page
        "total_count": counts.total_count,  # TOTAL trades matching filters
        "summary": {
            "total_exposure_usd": round(float(counts.total_exposure or 0), 2),
            "total_pnl_usd": round(total_pnl, 2),  # Only from paginated trades (estimate)
            "live_trades": counts.live_count,
            "paper_trades": counts.paper_count,
            "baseline_trades": counts.baseline_count,
            "strategy_trades": counts.strategy_count,
            "baseline_exposure_usd": round(float(counts.baseline_exposure or 0), 2),
            "strategy_exposure_usd": round(float(counts.strategy_exposure or 0), 2),
        },
"trades": [
            {
                "id": t.id,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": float(t.entry_price),
                "webhook_source": t.webhook_source,
                "status": t.status,
                "current_pnl_pct": get_trade_pnl_pct(t),
                "current_pnl_usd": round(get_trade_pnl_pct(t) * float(t.notional_position_usd or 0) / 100, 2),
                "notional_position_usd": float(t.notional_position_usd or 0),
                "trade_mode": t.trade_mode,
                "risk_strategy": t.risk_strategy,
                "entry_time": t.entry_timestamp.isoformat(),
                "exit_time": t.completed_at.isoformat() if t.completed_at else None,
                "duration_minutes": int((datetime.now(timezone.utc) - t.entry_timestamp).total_seconds() / 60) if t.status == "active" else int((t.completed_at - t.entry_timestamp).total_seconds() / 60) if t.completed_at else 0,
                "tp1_hit": t.tp1_hit,
                "tp2_hit": t.tp2_hit,
                "tp3_hit": t.tp3_hit,
                "planned_tp1_pct": float(t.planned_tp1_pct) if t.planned_tp1_pct else None,
                "planned_tp2_pct": float(t.planned_tp2_pct) if t.planned_tp2_pct else None,
                "planned_tp3_pct": float(t.planned_tp3_pct) if t.planned_tp3_pct else None,
                "planned_sl_pct": float(t.planned_sl_pct) if t.planned_sl_pct else None,
                "milestones": format_milestones(t, milestones_by_trade.get(t.id)),
            }
            for t in trades
        ]
    }


@router.get("/trades/{trade_id}", dependencies=[Depends(rate_limit_standard)])
async def get_trade(trade_id: int = Path(..., ge=1), db: AsyncSession = Depends(get_db)):
    """
    Get detailed information about a specific trade

    Includes: Entry details, TP/SL levels, current status, timestamps, news sentiment
    """
    result = await db.execute(select(TradeSetup).where(TradeSetup.id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    return {
        "id": trade.id,
        "symbol": trade.symbol,
        "exchange": trade.exchange,
        "direction": trade.direction,
        "entry_price": float(trade.entry_price),
        "entry_timestamp": trade.entry_timestamp.isoformat(),
        "status": trade.status,
        "setup_type": trade.setup_type,
        "confidence_score": float(trade.confidence_score) if trade.confidence_score else None,
        "webhook_source": trade.webhook_source,
        "planned_levels": {
            "tp1_pct": float(trade.planned_tp1_pct) if trade.planned_tp1_pct else None,
            "tp2_pct": float(trade.planned_tp2_pct) if trade.planned_tp2_pct else None,
            "tp3_pct": float(trade.planned_tp3_pct) if trade.planned_tp3_pct else None,
            "sl_pct": float(trade.planned_sl_pct) if trade.planned_sl_pct else None,
        },
        "current_performance": {
            "max_profit_pct": float(trade.max_profit_pct) if trade.max_profit_pct else 0,
            "max_drawdown_pct": float(trade.max_drawdown_pct) if trade.max_drawdown_pct else 0,
            "tp1_hit": trade.tp1_hit,
            "tp2_hit": trade.tp2_hit,
            "tp3_hit": trade.tp3_hit,
            "sl_hit": trade.sl_hit,
        },
        "tp_hit_details": {
            "tp1_time_minutes": trade.tp1_time_minutes,
            "tp2_time_minutes": trade.tp2_time_minutes,
            "tp3_time_minutes": trade.tp3_time_minutes,
        },
        "final_outcome": {
            "outcome": trade.final_outcome,
            "final_pnl_pct": float(trade.final_pnl_pct) if trade.final_pnl_pct else None,
            "completed_at": trade.completed_at.isoformat() if trade.completed_at else None,
        },
        "news_sentiment": {
            "score": float(trade.news_sentiment_score) if trade.news_sentiment_score else None,
            "count_1h": trade.news_count_1h,
            "major_news": trade.major_news,
        },
        "market_cap": {
            "usd": float(trade.market_cap_usd) if trade.market_cap_usd else None,
            "rank": trade.market_cap_rank,
        },
    }


@router.get("/trades/{trade_id}/details", dependencies=[Depends(rate_limit_standard)])
async def get_trade_details(trade_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get comprehensive trade details for modal popup

    Returns:
        - Full trade information with AI analysis
        - Previous trades for the same symbol (last 5-10)
        - Overall symbol performance statistics
    """
    # Get the main trade
    result = await db.execute(select(TradeSetup).where(TradeSetup.id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    # Get latest price sample for current PnL
    latest_sample_query = select(TradePriceSample).where(
        TradePriceSample.trade_setup_id == trade.id
    ).order_by(TradePriceSample.timestamp.desc()).limit(1)
    
    latest_sample_result = await db.execute(latest_sample_query)
    latest_sample = latest_sample_result.scalar_one_or_none()
    
    if latest_sample:
        current_pnl_pct = float(latest_sample.pnl_pct)
    else:
        current_pnl_pct = 0.0
    
    # Build trade data
    trade_data = {
        "id": trade.id,
        "symbol": trade.symbol,
        "exchange": trade.exchange,
        "direction": trade.direction,
        "entry_price": float(trade.entry_price),
        "entry_timestamp": trade.entry_timestamp.isoformat(),
        "completed_at": trade.completed_at.isoformat() if trade.completed_at else None,
        "status": trade.status,
        "trade_mode": trade.trade_mode,
        "current_pnl_pct": current_pnl_pct,
        "final_pnl_pct": float(trade.final_pnl_pct) if trade.final_pnl_pct else None,
        "final_outcome": trade.final_outcome,
        "planned_tp1_pct": float(trade.planned_tp1_pct) if trade.planned_tp1_pct else None,
        "planned_tp2_pct": float(trade.planned_tp2_pct) if trade.planned_tp2_pct else None,
        "planned_tp3_pct": float(trade.planned_tp3_pct) if trade.planned_tp3_pct else None,
        "planned_sl_pct": float(trade.planned_sl_pct) if trade.planned_sl_pct else None,
        "tp1_hit": trade.tp1_hit,
        "tp2_hit": trade.tp2_hit,
        "tp3_hit": trade.tp3_hit,
        "sl_hit": trade.sl_hit,
    }

    # Get AI analysis
    ai_analysis = None
    if trade.ai_reasoning or trade.ai_red_flags or trade.ai_green_lights or trade.ai_recommended_action:
        ai_analysis = {
            "reasoning": trade.ai_reasoning,
            "red_flags": trade.ai_red_flags if isinstance(trade.ai_red_flags, list) else [],
            "green_lights": trade.ai_green_lights if isinstance(trade.ai_green_lights, list) else [],
            "recommended_action": trade.ai_recommended_action,
            "quality_score": float(trade.ai_quality_score) if trade.ai_quality_score else None,
            "confidence": float(trade.ai_confidence) if trade.ai_confidence else None,
        }

    # Get previous trades for this symbol (last 10 completed trades)
    previous_trades_result = await db.execute(
        select(TradeSetup)
        .where(
            TradeSetup.symbol == trade.symbol,
            TradeSetup.id != trade_id,
            TradeSetup.status == "completed"
        )
        .order_by(TradeSetup.completed_at.desc())
        .limit(10)
    )
    previous_trades = previous_trades_result.scalars().all()

    previous_trades_data = [
        {
            "id": t.id,
            "direction": t.direction,
            "entry_price": float(t.entry_price),
            "entry_timestamp": t.entry_timestamp.isoformat(),
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "final_outcome": t.final_outcome,
            "final_pnl_pct": float(t.final_pnl_pct) if t.final_pnl_pct else 0,
        }
        for t in previous_trades
    ]

    # Calculate symbol statistics
    symbol_trades_result = await db.execute(
        select(TradeSetup)
        .where(
            TradeSetup.symbol == trade.symbol,
            TradeSetup.status == "completed",
            TradeSetup.final_pnl_pct.isnot(None)
        )
    )
    symbol_trades = symbol_trades_result.scalars().all()

    symbol_stats = None
    if symbol_trades:
        total_trades = len(symbol_trades)
        winning_trades = sum(1 for t in symbol_trades if float(t.final_pnl_pct or 0) > 0)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        avg_pnl = sum(float(t.final_pnl_pct or 0) for t in symbol_trades) / total_trades if total_trades > 0 else 0

        symbol_stats = {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "avg_pnl": avg_pnl,
        }

    return {
        "trade": trade_data,
        "ai_analysis": ai_analysis,
        "previous_trades": previous_trades_data,
        "symbol_stats": symbol_stats,
    }


@router.get("/history-trades", dependencies=[Depends(rate_limit_standard)])
async def get_trade_history(
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """
    Get historical trades (completed)

    Query Parameters:
        - symbol: Filter by symbol
        - strategy: Filter by webhook_source
        - limit: Max results (default 100)
        - offset: Pagination offset

    Returns:
        List of completed trades with final outcomes
    """
    # Get total count
    from sqlalchemy import func
    count_query = select(func.count()).select_from(TradeSetup).where(TradeSetup.status == "completed")
    
    if symbol:
        count_query = count_query.where(TradeSetup.symbol == symbol)
    if strategy:
        count_query = count_query.where(TradeSetup.webhook_source == strategy)
    
    count_result = await db.execute(count_query)
    total_count = count_result.scalar()
    
    # Main query
    query = select(TradeSetup).where(TradeSetup.status == "completed")

    if symbol:
        query = query.where(TradeSetup.symbol == symbol)
    if strategy:
        query = query.where(TradeSetup.webhook_source == strategy)

    query = query.order_by(TradeSetup.completed_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    trades = result.scalars().all()

    return {
        "count": len(trades),
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "trades": [
            {
                "id": t.id,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": float(t.entry_price),
                "entry_time": t.entry_timestamp.isoformat(),
                "completed_time": t.completed_at.isoformat() if t.completed_at else None,
                "final_outcome": t.final_outcome,
                "final_pnl_pct": float(t.final_pnl_pct) if t.final_pnl_pct else None,
                "tp1_hit": t.tp1_hit,
                "tp2_hit": t.tp2_hit,
                "tp3_hit": t.tp3_hit,
                "sl_hit": t.sl_hit,
                "strategy": t.webhook_source,
            }
            for t in trades
        ],
    }


@router.post("/trades/{trade_id}/close", dependencies=[Depends(rate_limit_low)])
async def close_trade_manually(
    trade_id: int,
    outcome: str,
    final_pnl_pct: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually close a trade (for testing or emergency)

    Body:
        - outcome: "tp1", "tp2", "tp3", "sl", "manual", "timeout"
        - final_pnl_pct: Final P&L percentage (optional, calculated if not provided)

    Use Cases:
        - Testing trade closure logic
        - Emergency stop during market crash
        - Manual exit before TP/SL hit
    """
    result = await db.execute(select(TradeSetup).where(TradeSetup.id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    if trade.status != "active":
        raise HTTPException(status_code=400, detail=f"Trade {trade_id} is already {trade.status}")

    # Calculate final P&L if not provided
    if final_pnl_pct is None:
        final_pnl_pct = float(trade.max_profit_pct) if trade.max_profit_pct else 0

    # Close trade
    if price_tracker:
        await price_tracker._close_trade(trade, outcome=outcome, final_pnl=final_pnl_pct, db=db)
    else:
        # Fallback if price tracker not running
        trade.status = "completed"
        trade.completed_at = datetime.now(timezone.utc)
        trade.final_outcome = outcome
        trade.final_pnl_pct = Decimal(str(final_pnl_pct))
        await db.commit()

    logger.info(f"✅ Trade {trade_id} closed manually: {outcome} ({final_pnl_pct:.2f}%)")

    return {
        "status": "closed",
        "trade_id": trade_id,
        "outcome": outcome,
        "final_pnl_pct": final_pnl_pct,
    }


# ============================================================================
# STATISTICS ENDPOINTS
# ============================================================================


@router.get("/statistics/{symbol}", dependencies=[Depends(rate_limit_standard)])
async def get_symbol_statistics(symbol: str, db: AsyncSession = Depends(get_db)):
    """
    Get learned statistics for a symbol

    Returns:
        - Learned optimal TP/SL levels
        - Hit rates (TP1/TP2/TP3)
        - Profitability metrics (EV, R:R ratio)
        - Sample size and confidence
        - Recommendations (trailing stop, sentiment matters)
    """
    result = await db.execute(select(AssetStatistics).where(AssetStatistics.symbol == symbol))
    stats = result.scalar_one_or_none()

    if not stats:
        return {
            "error": "No statistics available for this symbol",
            "symbol": symbol,
            "sample_size": 0,
            "recommendation": "Collect at least 30 trades before using learned levels",
        }

    return {
        "symbol": stats.symbol,
        "sample_size": stats.completed_setups,
        "confidence": (
            "high"
            if stats.completed_setups >= 50
            else "medium" if stats.completed_setups >= 30 else "low"
        ),
        "learned_levels": {
            "tp1_pct": float(stats.optimal_tp1_pct) if stats.optimal_tp1_pct else None,
            "tp2_pct": float(stats.optimal_tp2_pct) if stats.optimal_tp2_pct else None,
            "tp3_pct": float(stats.optimal_tp3_pct) if stats.optimal_tp3_pct else None,
            "sl_pct": float(stats.optimal_sl_pct) if stats.optimal_sl_pct else None,
        },
        "hit_rates": {
            "tp1": f"{stats.tp1_hit_rate * 100:.1f}%" if stats.tp1_hit_rate else None,
            "tp2": f"{stats.tp2_hit_rate * 100:.1f}%" if stats.tp2_hit_rate else None,
            "tp3": f"{stats.tp3_hit_rate * 100:.1f}%" if stats.tp3_hit_rate else None,
        },
        "profitability": {
            "expected_value_pct": (
                float(stats.expected_value_pct) if stats.expected_value_pct else None
            ),
            "is_profitable": stats.is_profitable_setup,
            "avg_risk_reward_ratio": (
                float(stats.avg_risk_reward_ratio) if stats.avg_risk_reward_ratio else None
            ),
        },
        "recommendations": {
            "use_trailing_stop": stats.trailing_stop_recommended,
            "sentiment_matters": stats.sentiment_matters,
        },
        "last_updated": stats.last_updated.isoformat() if stats.last_updated else None,
    }


# ============================================================================
# STRATEGY PERFORMANCE ENDPOINTS
# ============================================================================


@router.get("/strategies")
async def list_strategies(db: AsyncSession = Depends(get_db)):
    """
    List all strategies that have sent trades

    Returns:
        List of strategy names with basic stats
    """
    from sqlalchemy import case

    result = await db.execute(
        select(
            TradeSetup.webhook_source,
            func.count().label("total_trades"),
            func.sum(case((TradeSetup.status == "active", 1), else_=0)).label("active_trades"),
        )
        .where(TradeSetup.webhook_source.isnot(None))
        .group_by(TradeSetup.webhook_source)
    )

    strategies = []
    for row in result:
        strategies.append(
            {
                "name": row.webhook_source,
                "total_trades": row.total_trades,
                "active_trades": row.active_trades,
            }
        )

    return {"count": len(strategies), "strategies": strategies}


@router.get("/strategies/performance-by-source")
async def get_strategy_performance_by_source(db: AsyncSession = Depends(get_db)):
    """
    Get strategy performance grouped by webhook source

    Shows performance of A/B/C/D strategies (post-baseline) grouped by webhook source.
    EXCLUDES baseline trades (data collection only).

    Returns:
        - Per-source strategy performance (A, B, C, D)
        - Only includes trades with risk_strategy != 'baseline'
        - P&L, win rate, trade count per strategy per source
    """
    # Get all NON-BASELINE trades
    result = await db.execute(
        select(TradeSetup)
        .where(TradeSetup.risk_strategy != 'baseline')
        .where(TradeSetup.status.in_(['active', 'completed']))
    )
    strategy_trades = result.scalars().all()

    # Group by source and risk_strategy
    from collections import defaultdict
    by_source = defaultdict(lambda: defaultdict(lambda: {
        "trades": [],
        "total_pnl": 0,
        "wins": 0,
        "losses": 0,
        "exposure": 0
    }))

    for trade in strategy_trades:
        source = trade.webhook_source or "unknown"
        strategy = trade.risk_strategy

        # Calculate P&L
        if trade.status == 'completed':
            pnl_pct = float(trade.final_pnl_pct or 0)
        else:
            pnl_pct = float(trade.max_profit_pct or 0)

        pnl_usd = pnl_pct * float(trade.notional_position_usd or 0) / 100

        by_source[source][strategy]["trades"].append(trade)
        by_source[source][strategy]["total_pnl"] += pnl_usd
        by_source[source][strategy]["exposure"] += float(trade.notional_position_usd or 0)

        if pnl_pct > 0:
            by_source[source][strategy]["wins"] += 1
        elif pnl_pct < 0:
            by_source[source][strategy]["losses"] += 1

    # Format response
    sources = []
    for source, strategies in by_source.items():
        strategy_stats = []
        for strategy_name, data in strategies.items():
            total_trades = len(data["trades"])
            win_rate = (data["wins"] / total_trades * 100) if total_trades > 0 else 0

            strategy_stats.append({
                "risk_strategy": strategy_name,
                "total_trades": total_trades,
                "wins": data["wins"],
                "losses": data["losses"],
                "win_rate_pct": round(win_rate, 2),
                "total_pnl_usd": round(data["total_pnl"], 2),
                "total_exposure_usd": round(data["exposure"], 2),
                "avg_pnl_per_trade": round(data["total_pnl"] / total_trades, 2) if total_trades > 0 else 0
            })

        sources.append({
            "webhook_source": source,
            "strategies": sorted(strategy_stats, key=lambda x: x["total_pnl_usd"], reverse=True),
            "total_trades": sum(len(d["trades"]) for d in strategies.values()),
            "total_pnl_usd": round(sum(d["total_pnl"] for d in strategies.values()), 2)
        })

    return {
        "by_source": sorted(sources, key=lambda x: x["total_pnl_usd"], reverse=True),
        "summary": {
            "total_strategy_trades": len(strategy_trades),
            "total_sources": len(by_source),
            "note": "Excludes baseline trades (data collection only)"
        }
    }


@router.get("/strategies/parallel-comparison")
async def get_parallel_strategy_comparison(db: AsyncSession = Depends(get_db)):
    """
    Get parallel strategy testing results grouped by webhook source, then by symbol
    
    Returns hierarchical structure:
    - Webhook Source (e.g., ADX5m)
      - Symbol (e.g., BTCUSDT)
        - Strategy A, B, C comparison
    
    Perfect for collapsible dashboard UI.
    """
    from sqlalchemy import select
    
    # Get all parallel test trades
    result = await db.execute(
        select(TradeSetup)
        .where(TradeSetup.is_parallel_test == True)
        .order_by(TradeSetup.entry_timestamp.desc())
    )
    all_trades = result.scalars().all()
    
    # Build hierarchy: webhook_source -> symbol -> test_group -> strategies
    sources = {}
    
    for trade in all_trades:
        source = trade.webhook_source or "unknown"
        symbol = trade.symbol
        group_id = trade.test_group_id
        strategy = trade.risk_strategy
        
        # Initialize source
        if source not in sources:
            sources[source] = {
                "webhook_source": source,
                "symbols": {},
                "total_signals": 0,
                "strategy_wins": {"static": 0, "adaptive_trailing": 0, "early_momentum": 0, "ai_filtered": 0},
                "overview": ""
            }
        
        # Initialize symbol
        if symbol not in sources[source]["symbols"]:
            sources[source]["symbols"][symbol] = {
                "symbol": symbol,
                "test_groups": {},
                "live_price": None,
                "total_groups": 0,
                "strategy_performance": {"static": [], "adaptive_trailing": [], "early_momentum": [], "ai_filtered": []}
            }
        
        # Initialize test group
        if group_id not in sources[source]["symbols"][symbol]["test_groups"]:
            sources[source]["symbols"][symbol]["test_groups"][group_id] = {
                "test_group_id": group_id,
                "entry_price": float(trade.entry_price),
                "entry_time": trade.entry_timestamp.isoformat(),
                "direction": trade.direction,
                "status": "active",
                "strategies": {}
            }
        
        # Add strategy data - get ACTUAL current P&L
        pnl = await get_current_pnl_for_trade(trade, db)
        
        sources[source]["symbols"][symbol]["test_groups"][group_id]["strategies"][strategy] = {
            "trade_id": trade.id,
            "status": trade.status,
            "pnl_pct": pnl,
            "max_profit_pct": float(trade.max_profit_pct or 0),
            "max_drawdown_pct": float(trade.max_drawdown_pct or 0),
            "tp1_hit": trade.tp1_hit,
            "tp2_hit": trade.tp2_hit,
            "tp3_hit": trade.tp3_hit,
            "sl_hit": trade.sl_hit,
            "sl_type_hit": trade.sl_type_hit,
            "final_outcome": trade.final_outcome,
            "minutes_active": int((trade.completed_at or trade.entry_timestamp).timestamp() - trade.entry_timestamp.timestamp()) / 60,
            # Strategy-specific
            "early_momentum_detected": trade.early_momentum_detected if strategy == "early_momentum" else None,
            "early_momentum_time": float(trade.early_momentum_time) if trade.early_momentum_time else None,
            "trailing_updates": trade.trailing_stop_updates if strategy == "adaptive_trailing" else None,
            "momentum_state": trade.momentum_state if strategy == "adaptive_trailing" else None,
        }
        
        # Track PnL for this strategy
        sources[source]["symbols"][symbol]["strategy_performance"][strategy].append(pnl)
        
        # Update group status
        group = sources[source]["symbols"][symbol]["test_groups"][group_id]
        if len(group["strategies"]) == 3:
            if all(s["status"] == "completed" for s in group["strategies"].values()):
                group["status"] = "completed"
                
                # Determine winner
                best_strat = max(group["strategies"].items(), key=lambda x: x[1]["pnl_pct"])
                group["winning_strategy"] = best_strat[0]
                group["best_pnl"] = best_strat[1]["pnl_pct"]
                
                # Count for source-level stats
                sources[source]["strategy_wins"][best_strat[0]] += 1
    
    # Calculate summaries
    for source_name, source_data in sources.items():
        source_data["total_signals"] = sum(len(sym["test_groups"]) for sym in source_data["symbols"].values())
        
        # Source overview
        wins = source_data["strategy_wins"]
        total = sum(wins.values())
        if total > 0:
            winner = max(wins.items(), key=lambda x: x[1])
            source_data["overview"] = f"{total} signals, Strategy {winner[0][0].upper()} winning {winner[1]}/{total}"
        else:
            source_data["overview"] = "No completed signals yet"
        
        # Symbol summaries
        for symbol_name, symbol_data in source_data["symbols"].items():
            symbol_data["total_groups"] = len(symbol_data["test_groups"])
            
            # Calculate avg PnL per strategy
            for strat in ["static", "adaptive_trailing", "early_momentum"]:
                pnls = symbol_data["strategy_performance"][strat]
                symbol_data["strategy_performance"][strat] = {
                    "avg_pnl": sum(pnls) / len(pnls) if pnls else 0,
                    "count": len(pnls),
                    "total_pnl": sum(pnls)
                }
            
            # Get current live price from most recent trade
            latest_group = max(symbol_data["test_groups"].values(), key=lambda g: g["entry_time"])
            latest_trade_id = latest_group["strategies"].get("static", {}).get("trade_id")
            if latest_trade_id:
                # Get live price from active trade
                live_result = await db.execute(
                    select(TradeSetup).where(TradeSetup.id == latest_trade_id)
                )
                live_trade = live_result.scalar_one_or_none()
                if live_trade and live_trade.max_favorable_excursion:
                    symbol_data["live_price"] = float(live_trade.max_favorable_excursion)
                else:
                    symbol_data["live_price"] = latest_group["entry_price"]
            
            # Convert test_groups dict to list
            symbol_data["test_groups"] = list(symbol_data["test_groups"].values())
        
        # Convert symbols dict to list
        source_data["symbols"] = list(source_data["symbols"].values())
    
    return {
        "sources": list(sources.values())
    }


@router.get("/strategies/parallel-comparison-legacy")
async def get_parallel_strategy_comparison_legacy(db: AsyncSession = Depends(get_db)):
    """Legacy endpoint - deprecated"""
    return {"error": "This endpoint has been replaced by /api/strategies/parallel-comparison"}


# ============================================================================
# AI INSIGHTS ENDPOINTS
# ============================================================================


@router.get("/ai/evaluation-summary")
async def get_ai_evaluation_summary(db: AsyncSession = Depends(get_db)):
    """
    Get AI evaluation summary statistics

    Returns:
        - Total AI evaluations
        - Average quality score
        - Average confidence
        - Red flags count
        - Setup type breakdown
        - Quality score distribution
    """
    # Get all trades with AI evaluations
    result = await db.execute(
        select(TradeSetup)
        .where(TradeSetup.ai_quality_score.isnot(None))
    )
    trades = result.scalars().all()

    if not trades:
        return {
            "total_evaluations": 0,
            "avg_quality_score": 0,
            "avg_confidence": 0,
            "red_flags_count": 0,
            "setup_types": {},
            "quality_distribution": {},
            "note": "No AI evaluations yet - trades are being collected"
        }

    # Calculate statistics
    total_evaluations = len(trades)
    avg_quality_score = sum(float(t.ai_quality_score or 0) for t in trades) / total_evaluations
    avg_confidence = sum(float(t.ai_confidence or 0) for t in trades) / total_evaluations

    # Count red flags (stored as JSON list)
    red_flags_count = 0
    for t in trades:
        if t.ai_red_flags and isinstance(t.ai_red_flags, list):
            red_flags_count += len(t.ai_red_flags)

    # Setup type breakdown
    setup_types = {}
    for t in trades:
        if t.ai_setup_type:
            setup_types[t.ai_setup_type] = setup_types.get(t.ai_setup_type, 0) + 1

    # Quality score distribution (0-10 scale, group by 2-point buckets)
    quality_distribution = {
        "0-2": 0,
        "2-4": 0,
        "4-6": 0,
        "6-8": 0,
        "8-10": 0
    }
    for t in trades:
        score = float(t.ai_quality_score or 0)
        if score < 2:
            quality_distribution["0-2"] += 1
        elif score < 4:
            quality_distribution["2-4"] += 1
        elif score < 6:
            quality_distribution["4-6"] += 1
        elif score < 8:
            quality_distribution["6-8"] += 1
        else:
            quality_distribution["8-10"] += 1

    # Red flags vs green lights analysis
    all_red_flags = []
    all_green_lights = []
    for t in trades:
        if t.ai_red_flags and isinstance(t.ai_red_flags, list):
            all_red_flags.extend(t.ai_red_flags)
        if t.ai_green_lights and isinstance(t.ai_green_lights, list):
            all_green_lights.extend(t.ai_green_lights)

    # Count frequency of each flag/light
    from collections import Counter
    red_flag_freq = Counter(all_red_flags)
    green_light_freq = Counter(all_green_lights)

    return {
        "total_evaluations": total_evaluations,
        "avg_quality_score": round(avg_quality_score, 2),
        "avg_confidence": round(avg_confidence, 2),
        "red_flags_count": red_flags_count,
        "setup_types": setup_types,
        "quality_distribution": quality_distribution,
        "top_red_flags": dict(red_flag_freq.most_common(5)),
        "top_green_lights": dict(green_light_freq.most_common(5)),
        "phase": "Phase 1: Data Collection (non-blocking)"
    }


# ============================================================================
# LEARNING STATISTICS ENDPOINTS
# ============================================================================


@router.get("/learning/baseline-progress")
async def get_baseline_progress(db: AsyncSession = Depends(get_db)):
    """
    Get baseline data collection progress

    Shows how many trades have been collected per symbol per direction.
    First 10 trades per direction per symbol = baseline mode (no TP/SL).

    Returns:
        - Per-symbol progress (LONG and SHORT)
        - Symbols ready for learned levels (10+ trades)
        - Symbols still in baseline mode
    """
    result = await db.execute(
        select(AssetStatistics)
        .order_by(AssetStatistics.completed_setups.desc())
    )
    all_stats = result.scalars().all()

    symbols_progress = []
    baseline_active = []
    ready_for_learning = []

    for stats in all_stats:
        long_count = stats.completed_longs or 0
        short_count = stats.completed_shorts or 0
        total_count = stats.completed_setups or 0

        # Baseline mode = less than 10 trades for either direction
        long_baseline = long_count < 10
        short_baseline = short_count < 10

        symbol_data = {
            "symbol": stats.symbol,
            "longs": {
                "completed": long_count,
                "target": 10,
                "progress_pct": min(100, (long_count / 10) * 100),
                "status": "baseline" if long_baseline else "learning"
            },
            "shorts": {
                "completed": short_count,
                "target": 10,
                "progress_pct": min(100, (short_count / 10) * 100),
                "status": "baseline" if short_baseline else "learning"
            },
            "total_completed": total_count,
            "overall_status": "baseline" if (long_baseline or short_baseline) else "learning"
        }

        symbols_progress.append(symbol_data)

        if long_baseline or short_baseline:
            baseline_active.append({
                "symbol": stats.symbol,
                "longs_needed": max(0, 10 - long_count),
                "shorts_needed": max(0, 10 - short_count)
            })
        else:
            ready_for_learning.append(stats.symbol)

    return {
        "symbols": symbols_progress,
        "summary": {
            "total_symbols": len(all_stats),
            "baseline_active": len(baseline_active),
            "ready_for_learning": len(ready_for_learning),
        },
        "baseline_active": baseline_active,
        "ready_for_learning": ready_for_learning,
        "note": "First 10 trades per direction = baseline mode (24h timeout only, no TP/SL)"
    }


@router.get("/learning/baseline-by-source")
async def get_baseline_by_source(db: AsyncSession = Depends(get_db)):
    """
    Get baseline data collection progress grouped by webhook source

    Shows how many baseline trades are active per webhook source (ADX1m, ADX5m, etc.)
    and progress toward 10-trade threshold per symbol/direction.
    """
    # Get all active baseline trades grouped by source
    result = await db.execute(
        select(TradeSetup)
        .where(TradeSetup.status == 'active')
        .where(TradeSetup.risk_strategy == 'baseline')
    )
    baseline_trades = result.scalars().all()

    # Group by webhook source
    from collections import defaultdict
    by_source = defaultdict(lambda: {"trades": [], "symbols": set(), "total_exposure": 0})

    for trade in baseline_trades:
        source = trade.webhook_source or "unknown"
        by_source[source]["trades"].append(trade)
        by_source[source]["symbols"].add(trade.symbol)
        by_source[source]["total_exposure"] += float(trade.notional_position_usd or 0)

    # Format response
    sources = []
    for source, data in by_source.items():
        sources.append({
            "webhook_source": source,
            "active_trades": len(data["trades"]),
            "unique_symbols": len(data["symbols"]),
            "total_exposure_usd": round(data["total_exposure"], 2),
            "symbols": sorted(list(data["symbols"]))
        })

    return {
        "by_source": sorted(sources, key=lambda x: x["active_trades"], reverse=True),
        "summary": {
            "total_baseline_trades": len(baseline_trades),
            "total_sources": len(by_source),
            "total_baseline_exposure": round(sum(d["total_exposure"] for d in by_source.values()), 2)
        },
        "note": "Baseline trades = data collection only, no TP/SL (first 10 per symbol/direction)"
    }


@router.get("/learning/learned-levels")
async def get_learned_levels(db: AsyncSession = Depends(get_db)):
    """
    Get learned TP/SL levels per symbol

    Shows optimal levels derived from historical data.
    Only shows symbols with 10+ completed trades.

    Returns:
        - Per-symbol learned levels (TP1, TP2, TP3, SL)
        - Sample size and confidence
        - Hit rates
        - Risk/reward ratios
    """
    result = await db.execute(
        select(AssetStatistics)
        .where(AssetStatistics.completed_setups >= 10)
        .order_by(AssetStatistics.completed_setups.desc())
    )
    stats = result.scalars().all()

    learned_data = []
    for s in stats:
        # Confidence level based on sample size
        if s.completed_setups >= 50:
            confidence = "high"
        elif s.completed_setups >= 30:
            confidence = "medium"
        else:
            confidence = "low"

        learned_data.append({
            "symbol": s.symbol,
            "sample_size": s.completed_setups,
            "confidence": confidence,
            "learned_levels": {
                "tp1_pct": float(s.optimal_tp1_pct) if s.optimal_tp1_pct else None,
                "tp2_pct": float(s.optimal_tp2_pct) if s.optimal_tp2_pct else None,
                "tp3_pct": float(s.optimal_tp3_pct) if s.optimal_tp3_pct else None,
                "sl_pct": float(s.optimal_sl_pct) if s.optimal_sl_pct else None,
            },
            "hit_rates": {
                "tp1": float(s.tp1_hit_rate) if s.tp1_hit_rate else None,
                "tp2": float(s.tp2_hit_rate) if s.tp2_hit_rate else None,
                "tp3": float(s.tp3_hit_rate) if s.tp3_hit_rate else None,
            },
            "risk_reward": {
                "avg_rr": float(s.avg_risk_reward_ratio) if s.avg_risk_reward_ratio else None,
                "cumulative_rr": float(s.cumulative_rr) if s.cumulative_rr else None,
                "is_profitable": s.is_profitable_setup,
            },
            "time_to_target": {
                "tp1_minutes": s.tp1_median_minutes,
                "tp2_minutes": s.tp2_median_minutes,
                "tp3_minutes": s.tp3_median_minutes,
            }
        })

    return {
        "symbols": learned_data,
        "total_symbols": len(learned_data),
        "note": "Levels are learned from historical data, updated after each trade"
    }


@router.get("/learning/circuit-breakers")
async def get_circuit_breaker_status(db: AsyncSession = Depends(get_db)):
    """
    Get circuit breaker status (live vs paper trading)

    Circuit breaker activates when cumulative R/R < 1.0 after 10+ trades.
    Asset switches to paper trading until R/R recovers above 1.0.

    Returns:
        - Per-asset trading mode (live or paper)
        - Cumulative risk/reward ratio
        - Profit/loss needed to resume live trading
        - Paper trade count
        - Historical R/R tracking
    """
    result = await db.execute(
        select(AssetStatistics)
        .where(AssetStatistics.completed_setups >= 10)
        .order_by(AssetStatistics.cumulative_rr.desc())
    )
    all_stats = result.scalars().all()

    circuit_breaker_data = []
    live_count = 0
    paper_count = 0

    for stats in all_stats:
        cumulative_rr = float(stats.cumulative_rr) if stats.cumulative_rr else 0
        is_live = stats.is_live_trading if stats.is_live_trading is not None else True

        if is_live:
            live_count += 1
        else:
            paper_count += 1

        # Calculate how much profit needed to resume live trading
        if not is_live and stats.cumulative_losses_usd and stats.cumulative_wins_usd:
            profit_needed = float(stats.cumulative_losses_usd - stats.cumulative_wins_usd)
        else:
            profit_needed = 0

        circuit_breaker_data.append({
            "symbol": stats.symbol,
            "trading_mode": "live" if is_live else "paper",
            "cumulative_rr": round(cumulative_rr, 4),
            "cumulative_wins": float(stats.cumulative_wins_usd) if stats.cumulative_wins_usd else 0,
            "cumulative_losses": float(stats.cumulative_losses_usd) if stats.cumulative_losses_usd else 0,
            "profit_needed_to_resume": round(profit_needed, 2) if profit_needed > 0 else 0,
            "paper_trade_count": stats.paper_trade_count or 0,
            "completed_setups": stats.completed_setups,
            "last_rr_check": stats.last_rr_check.isoformat() if stats.last_rr_check else None,
            "status": (
                "healthy" if is_live and cumulative_rr >= 1.5 else
                "ok" if is_live and cumulative_rr >= 1.0 else
                "warning" if is_live and cumulative_rr < 1.0 else
                "paper_mode"
            )
        })

    return {
        "assets": circuit_breaker_data,
        "summary": {
            "total_assets": len(all_stats),
            "live_trading": live_count,
            "paper_trading": paper_count,
        },
        "circuit_breaker_rules": {
            "activation": "R/R < 1.0 after 10+ trades",
            "deactivation": "R/R >= 1.0 (break-even or profitable)",
            "note": "Protects capital by pausing underperforming assets"
        }
    }


@router.get("/strategies/leaderboard")
async def get_strategy_leaderboard(
    sort_by: str = "profitability",  # profitability, win_rate, total_pnl
    db: AsyncSession = Depends(get_db),
):
    """
    Strategy leaderboard - ranked by performance

    Query Parameters:
        - sort_by: profitability (default), win_rate, total_pnl

    Returns:
        Ranked list of strategies with performance metrics
    """
    result = await db.execute(
        select(
            TradeSetup.webhook_source,
            func.count().label("total"),
            func.sum(func.case((TradeSetup.status == "completed", 1), else_=0)).label("completed"),
            func.avg(TradeSetup.final_pnl_pct).label("avg_pnl"),
            func.sum(TradeSetup.final_pnl_pct).label("total_pnl"),
            func.sum(
                func.case(((TradeSetup.final_outcome.in_(["tp1", "tp2", "tp3"]), 1)), else_=0)
            ).label("wins"),
        )
        .where(TradeSetup.webhook_source.isnot(None))
        .where(TradeSetup.status == "completed")
        .group_by(TradeSetup.webhook_source)
    )

    strategies = []
    for row in result:
        win_rate = float(row.wins) / float(row.completed) if row.completed > 0 else 0

        # Calculate profitability score (combines win rate + avg P&L)
        avg_pnl = float(row.avg_pnl) if row.avg_pnl else 0
        profitability_score = (win_rate * 100) + (avg_pnl * 10)

        strategies.append(
            {
                "strategy": row.webhook_source,
                "total_trades": row.total,
                "completed_trades": row.completed,
                "win_rate": round(win_rate * 100, 1),
                "avg_pnl_pct": round(avg_pnl, 2),
                "total_pnl_pct": round(float(row.total_pnl) if row.total_pnl else 0, 2),
                "profitability_score": round(profitability_score, 2),
                "rank": None,  # Will be filled after sorting
            }
        )

    # Sort strategies
    if sort_by == "win_rate":
        strategies.sort(key=lambda x: x["win_rate"], reverse=True)
    elif sort_by == "total_pnl":
        strategies.sort(key=lambda x: x["total_pnl_pct"], reverse=True)
    else:  # profitability (default)
        strategies.sort(key=lambda x: x["profitability_score"], reverse=True)

    # Assign ranks
    for i, s in enumerate(strategies, 1):
        s["rank"] = i

    return {
        "leaderboard": strategies,
        "best_strategy": strategies[0] if strategies else None,
        "worst_strategy": strategies[-1] if strategies else None,
        "sorted_by": sort_by,
    }


@router.get("/strategies/{strategy_name}/statistics")
async def get_strategy_statistics(strategy_name: str, db: AsyncSession = Depends(get_db)):
    """
    Get detailed statistics for a specific strategy

    Returns:
        - Performance metrics
        - Best/worst symbols
        - Recent trades
        - Time-of-day analysis (TODO)
    """
    # Get all completed trades for this strategy
    result = await db.execute(
        select(TradeSetup)
        .where(TradeSetup.webhook_source == strategy_name)
        .where(TradeSetup.status == "completed")
    )
    trades = result.scalars().all()

    if not trades:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{strategy_name}' not found or has no completed trades",
        )

    # Calculate overall metrics
    total_trades = len(trades)
    winning_trades = sum(1 for t in trades if t.final_outcome in ["tp1", "tp2", "tp3"])
    win_rate = winning_trades / total_trades
    avg_pnl = sum(float(t.final_pnl_pct or 0) for t in trades) / total_trades
    total_pnl = sum(float(t.final_pnl_pct or 0) for t in trades)

    # Break down by symbol
    by_symbol = {}
    for trade in trades:
        if trade.symbol not in by_symbol:
            by_symbol[trade.symbol] = {"trades": 0, "wins": 0, "total_pnl": 0}
        by_symbol[trade.symbol]["trades"] += 1
        if trade.final_outcome in ["tp1", "tp2", "tp3"]:
            by_symbol[trade.symbol]["wins"] += 1
        by_symbol[trade.symbol]["total_pnl"] += float(trade.final_pnl_pct or 0)

    # Calculate per-symbol metrics
    symbol_stats = []
    for symbol, data in by_symbol.items():
        win_rate_symbol = data["wins"] / data["trades"]
        avg_pnl_symbol = data["total_pnl"] / data["trades"]

        symbol_stats.append(
            {
                "symbol": symbol,
                "trades": data["trades"],
                "win_rate": round(win_rate_symbol * 100, 1),
                "avg_pnl_pct": round(avg_pnl_symbol, 2),
                "total_pnl_pct": round(data["total_pnl"], 2),
            }
        )

    # Sort by profitability
    symbol_stats.sort(key=lambda x: x["avg_pnl_pct"], reverse=True)

    # Recent trades
    recent_trades = sorted(trades, key=lambda t: t.completed_at, reverse=True)[:10]

    return {
        "strategy_name": strategy_name,
        "overall": {
            "total_trades": total_trades,
            "win_rate": round(win_rate * 100, 1),
            "avg_pnl_pct": round(avg_pnl, 2),
            "total_pnl_pct": round(total_pnl, 2),
        },
        "by_symbol": symbol_stats,
        "best_symbol": symbol_stats[0] if symbol_stats else None,
        "worst_symbol": symbol_stats[-1] if symbol_stats else None,
        "recent_trades": [
            {
                "id": t.id,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": float(t.entry_price),
                "final_outcome": t.final_outcome,
                "final_pnl_pct": float(t.final_pnl_pct) if t.final_pnl_pct else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in recent_trades
        ],
    }


# ============================================================================
# ANALYTICS ENDPOINTS - PHASE 3
# ============================================================================


@router.get("/analytics/hit-rate-curves/{symbol}")
async def get_hit_rate_curves(
    symbol: str, min_trades: int = 30, db: AsyncSession = Depends(get_db)
):
    """
    Get hit rate curves for symbol

    Shows how win rate changes as TP target increases.
    Identifies optimal TP levels (target 85%, 70%, 50% hit rates).

    Returns:
        - TP/SL hit rate curves
        - Optimal TP1/TP2/TP3 levels
        - Expected value analysis
        - Actionable recommendations
    """
    from app.analytics.hit_rate_analyzer import get_hit_rate_analyzer

    analyzer = get_hit_rate_analyzer()
    curves = await analyzer.generate_hit_rate_curves(symbol, db, min_trades)

    return curves


@router.get("/analytics/hit-rate-curves/{symbol}/chart-data")
async def get_hit_rate_chart_data(
    symbol: str, min_trades: int = 30, db: AsyncSession = Depends(get_db)
):
    """
    Get hit rate curves formatted for charting libraries

    Returns data ready to plot with Chart.js, Plotly, etc.
    """
    from app.analytics.hit_rate_analyzer import get_hit_rate_analyzer

    analyzer = get_hit_rate_analyzer()
    curves = await analyzer.generate_hit_rate_curves(symbol, db, min_trades)
    chart_data = analyzer.get_chart_data(curves)

    return chart_data


@router.get("/analytics/learned-vs-manual/{symbol}")
async def compare_learned_vs_manual(
    symbol: str, min_trades: int = 30, lookback_days: int = 90, db: AsyncSession = Depends(get_db)
):
    """
    Compare learned TP/SL levels vs manual defaults

    Proves system value by showing improvement metrics.

    Returns:
        - Learned levels vs manual levels
        - Performance comparison (win rate, EV, Sharpe ratio)
        - Improvement percentages
        - Verdict
    """
    from app.analytics.learned_vs_manual import get_learned_vs_manual_analyzer

    analyzer = get_learned_vs_manual_analyzer()
    comparison = await analyzer.compare_learned_vs_manual(symbol, db, min_trades, lookback_days)

    return comparison


@router.get("/analytics/learned-vs-manual/{symbol}/report")
async def get_learned_vs_manual_report(
    symbol: str, min_trades: int = 30, lookback_days: int = 90, db: AsyncSession = Depends(get_db)
):
    """
    Get human-readable learned vs manual comparison report

    Returns formatted text report suitable for display
    """
    from app.analytics.learned_vs_manual import get_learned_vs_manual_analyzer

    analyzer = get_learned_vs_manual_analyzer()
    comparison = await analyzer.compare_learned_vs_manual(symbol, db, min_trades, lookback_days)
    report = analyzer.generate_report(comparison)

    return {"report": report}


@router.get("/analytics/time-of-day/{symbol}")
async def analyze_time_patterns(
    symbol: str,
    min_total_trades: int = 50,
    lookback_days: int = 90,
    timezone: str = "UTC",
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze win rates by hour of day

    Identifies optimal trading windows.
    UNIQUE feature: "Trade BTC only 9-11am EST"

    Returns:
        - Hourly statistics (trades, wins, win rate, avg profit)
        - Best hours for trading
        - Worst hours to avoid
        - Recommendations
    """
    from app.analytics.time_of_day import get_time_of_day_analyzer

    analyzer = get_time_of_day_analyzer()
    analysis = await analyzer.analyze_time_patterns(
        symbol, db, min_total_trades, lookback_days, timezone
    )

    return analysis


@router.post("/analytics/confluence/check")
async def check_multiframe_confluence(
    symbol: str,
    entry_price: float,
    direction: str,
    lookback_candles: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """
    Check multi-timeframe confluence for potential trade

    Detects alignment across 15m, 1h, 4h, 1d timeframes.
    Improves win rate by 5%+ when timeframes agree.

    Body:
        {
            "symbol": "BTCUSDT",
            "entry_price": 43500.0,
            "direction": "long"
        }

    Returns:
        - Timeframe alignment (15m, 1h, 4h, 1d)
        - Confluence score (0-1)
        - Verdict (high/medium/low)
        - Recommendation
    """
    from app.analytics.multiframe_confluence import get_multiframe_confluence_detector

    detector = get_multiframe_confluence_detector()
    confluence = await detector.analyze_confluence(
        symbol=symbol,
        entry_price=Decimal(str(entry_price)),
        direction=direction.lower(),
        db=db,
        lookback_candles=lookback_candles,
    )

    return confluence


@router.post("/analytics/setup-quality/score")
async def score_setup_quality(
    symbol: str,
    entry_price: float,
    direction: str,
    tp1: float,
    tp2: float,
    tp3: float,
    sl: float,
    db: AsyncSession = Depends(get_db),
):
    """
    Score trade setup quality (0-100)

    Combines multiple quality factors:
    - Historical win rate (30%)
    - Multi-timeframe confluence (25%)
    - Risk/reward ratio (20%)
    - Volatility appropriateness (15%)
    - Time of day (10%)

    Body:
        {
            "symbol": "BTCUSDT",
            "entry_price": 43500.0,
            "direction": "long",
            "tp1": 1.5,
            "tp2": 3.0,
            "tp3": 5.5,
            "sl": -2.0
        }

    Returns:
        - Quality score (0-100)
        - Quality grade (high/medium/low/very_low)
        - Factor scores breakdown
        - Recommendation
        - Warnings
    """
    from app.analytics.setup_quality import get_setup_quality_filter

    filter_service = get_setup_quality_filter()
    quality = await filter_service.score_setup(
        symbol=symbol,
        entry_price=Decimal(str(entry_price)),
        direction=direction.lower(),
        tp_levels={"tp1": Decimal(str(tp1)), "tp2": Decimal(str(tp2)), "tp3": Decimal(str(tp3))},
        sl_level=Decimal(str(sl)),
        db=db,
    )

    return quality


@router.get("/analytics/backtest/confluence/{symbol}")
async def backtest_confluence_filter(
    symbol: str, min_trades: int = 50, lookback_days: int = 90, db: AsyncSession = Depends(get_db)
):
    """
    Backtest confluence filter effectiveness

    Shows win rate improvement when filtering for high confluence.

    Returns:
        - All trades performance
        - High confluence only performance
        - Improvement metrics
    """
    from app.analytics.multiframe_confluence import get_multiframe_confluence_detector

    detector = get_multiframe_confluence_detector()
    backtest = await detector.backtest_confluence_filter(symbol, db, min_trades, lookback_days)

    return backtest


@router.get("/analytics/backtest/quality-filter/{symbol}")
async def backtest_quality_filter(
    symbol: str, min_trades: int = 50, lookback_days: int = 90, db: AsyncSession = Depends(get_db)
):
    """
    Backtest quality filter effectiveness

    Shows win rate improvement when filtering for high-quality setups.

    Returns:
        - All setups performance
        - High quality only performance
        - Improvement metrics (win rate increase, false signals filtered)
    """
    from app.analytics.setup_quality import get_setup_quality_filter

    filter_service = get_setup_quality_filter()
    backtest = await filter_service.backtest_quality_filter(symbol, db, min_trades, lookback_days)

    return backtest


@router.get("/account/balance")
async def get_account_balance(db: AsyncSession = Depends(get_db)):
    """Get account balance with realized and unrealized P&L"""
    starting_balance = Decimal('100000.00')

    # Get all completed trades (EXCLUDE BASELINE - data collection only)
    completed_trades = await db.execute(
        select(TradeSetup)
        .where(
            TradeSetup.status == 'completed',
            TradeSetup.risk_strategy != 'baseline'
        )
    )
    completed_trades = completed_trades.scalars().all()

    # Calculate realized P&L from completed trades
    # P&L USD = (final_pnl_pct / 100) * notional_position_usd
    realized_pnl = sum(
        (float(trade.final_pnl_pct or 0) / 100) * float(trade.notional_position_usd or 0)
        for trade in completed_trades
        if trade.final_pnl_pct is not None and trade.notional_position_usd is not None
    )

    # Get all active trades (EXCLUDE BASELINE - data collection only)
    active_trades = await db.execute(
        select(TradeSetup)
        .where(
            TradeSetup.status == 'active',
            TradeSetup.risk_strategy != 'baseline'
        )
    )
    active_trades = active_trades.scalars().all()

    # Calculate unrealized P&L from active trades using ACTUAL current price, not max_profit
    unrealized_pnl = 0.0
    for trade in active_trades:
        if trade.notional_position_usd is None:
            continue
        
        # Get latest price sample for ACTUAL current PnL
        latest_sample_query = select(TradePriceSample).where(
            TradePriceSample.trade_setup_id == trade.id
        ).order_by(TradePriceSample.timestamp.desc()).limit(1)
        
        latest_sample_result = await db.execute(latest_sample_query)
        latest_sample = latest_sample_result.scalar_one_or_none()
        
        if latest_sample:
            current_pnl_pct = float(latest_sample.pnl_pct)
        else:
            current_pnl_pct = 0.0
        
        unrealized_pnl += (current_pnl_pct / 100) * float(trade.notional_position_usd)

    # Account balance includes both realized and unrealized P&L
    account_balance = float(starting_balance) + realized_pnl + unrealized_pnl
    net_pnl = realized_pnl + unrealized_pnl
    net_pnl_pct = (net_pnl / float(starting_balance)) * 100

    return {
        "starting_balance": float(starting_balance),
        "realized_pnl": round(realized_pnl, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "account_balance": round(account_balance, 2),
        "net_pnl": round(net_pnl, 2),
        "net_pnl_pct": round(net_pnl_pct, 4),
        "active_trades_count": len(active_trades),
        "completed_trades_count": len(completed_trades)
    }


# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================


@router.get("/health", dependencies=[Depends(rate_limit_standard)])
async def health_check():
    """
    System health check

    Returns:
        - API status
        - Database connectivity
        - Connection pool status
        - Price tracker status
        - Statistics engine status
    """
    db_healthy = await check_db_health()
    pool_stats = get_pool_stats()

    return {
        "status": "healthy" if db_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "api": "online",
            "database": "connected" if db_healthy else "disconnected",
            "price_tracker": "active" if price_tracker and price_tracker.running else "inactive",
            "statistics_engine": "active" if statistics_engine else "inactive",
        },
        "database_pool": pool_stats,
    }


@router.get("/websocket/stats")
async def get_websocket_stats():
    """
    Get WebSocket connection statistics (multiplexing metrics)

    Returns:
        - Total symbols being tracked
        - Total subscribers (trades)
        - Active WebSocket connections
        - Symbols in polling mode (fallback)
        - Exchange distribution
        - Multiplexing efficiency metrics

    Use Cases:
        - Monitor WebSocket multiplexing efficiency
        - Debug connection issues
        - Verify scalability (500 trades = ~50 connections)
        - Performance monitoring dashboards
    """
    if not price_tracker:
        return {"error": "Price tracker not initialized", "stats": None}

    ws_manager = get_websocket_manager()
    stats = ws_manager.get_connection_stats()

    # Calculate multiplexing efficiency
    total_subscribers = stats.get("total_subscribers", 0)
    active_websockets = stats.get("active_websockets", 0)

    if active_websockets > 0:
        multiplexing_ratio = total_subscribers / active_websockets
        efficiency_pct = 100 * (1 - (active_websockets / max(total_subscribers, 1)))
    else:
        multiplexing_ratio = 0
        efficiency_pct = 0

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "websocket_stats": stats,
        "multiplexing_metrics": {
            "total_trades": total_subscribers,
            "websocket_connections": active_websockets,
            "multiplexing_ratio": round(multiplexing_ratio, 2),
            "efficiency_pct": round(efficiency_pct, 1),
            "status": (
                "optimal"
                if efficiency_pct > 80
                else "good" if efficiency_pct > 50 else "suboptimal"
            ),
        },
        "performance_notes": {
            "expected_at_500_trades": "~50 connections (90% efficiency)",
            "current_performance": f"{active_websockets} connections for {total_subscribers} trades",
        },
    }


@router.post("/tracking/start", dependencies=[Depends(rate_limit_low)])
async def start_price_tracking(db: AsyncSession = Depends(get_db)):
    """
    Manually start price tracking for all active trades

    This endpoint loads all active trades from the database and subscribes
    to WebSocket feeds for real-time price monitoring.

    Use this if price tracking was stopped or if trades were created
    while the tracker was offline.
    """
    if not price_tracker:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Price tracker not initialized"
        )

    # Load all active trades
    result = await db.execute(
        select(TradeSetup).where(TradeSetup.status == 'active')
    )
    trades = result.scalars().all()

    if not trades:
        return {
            "status": "no_trades",
            "message": "No active trades to track",
            "trades_added": 0
        }

    # Add each trade to the tracker
    added_count = 0
    for trade in trades:
        try:
            await price_tracker.add_trade(trade, db)
            added_count += 1
            logger.info(f"📡 Added trade {trade.id} ({trade.symbol}) to price tracker")
        except Exception as e:
            logger.error(f"❌ Failed to add trade {trade.id} to tracker: {e}")

    return {
        "status": "success",
        "message": f"Started tracking {added_count} trades",
        "trades_added": added_count,
        "total_active_trades": len(trades),
        "websocket_stats": get_websocket_manager().get_connection_stats()
    }


@router.get("/learning/risk-reward-history")
async def get_risk_reward_history(
    limit: int = 30,
    symbol: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get risk/reward ratio history over time

    Shows how R/R evolves for each completed trade.
    Useful for tracking learning progress and circuit breaker status.
    """
    query = select(TradeSetup).where(
        TradeSetup.status == "completed",
        TradeSetup.final_pnl_pct.isnot(None)
    )

    if symbol:
        query = query.where(TradeSetup.symbol == symbol)

    query = query.order_by(TradeSetup.completed_at.desc()).limit(limit)

    result = await db.execute(query)
    trades = result.scalars().all()

    # Calculate cumulative R/R for each point
    history = []
    cumulative_wins = 0
    cumulative_losses = 0

    for t in reversed(trades):  # Process oldest to newest
        pnl = float(t.final_pnl_pct or 0)

        if pnl > 0:
            cumulative_wins += abs(pnl)
        else:
            cumulative_losses += abs(pnl)

        cumulative_rr = cumulative_wins / cumulative_losses if cumulative_losses > 0 else cumulative_wins

        history.append({
            "trade_id": t.id,
            "symbol": t.symbol,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "final_pnl_pct": pnl,
            "cumulative_wins": round(cumulative_wins, 2),
            "cumulative_losses": round(cumulative_losses, 2),
            "cumulative_rr": round(cumulative_rr, 4),
            "trade_mode": t.trade_mode,
            "final_outcome": t.final_outcome,
        })

    return {
        "count": len(history),
        "data": list(reversed(history)),  # Return newest first
        "current_rr": history[-1]["cumulative_rr"] if history else 0,
        "status": "healthy" if (history and history[-1]["cumulative_rr"] >= 1.0) else "warning"
    }


@router.get("/analytics/by-strategy")
async def get_analytics_by_strategy(
    strategy: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get per-strategy analytics breakdown

    Query Parameters:
        - strategy: Filter by specific strategy (webhook_source), or omit for all strategies

    Returns:
        - Per-strategy statistics (win rate, total trades, avg P&L, realized P&L, best/worst trades)
        - Time series data for P&L charts
        - Comparison table when strategy is None (ALL view)

    Note: P&L is calculated as percentage of total account, factoring in position size
    """
    from app.config import Settings
    settings = Settings()
    account_balance = settings.ACCOUNT_BALANCE_USD

    # Build query based on filter - include both completed AND active trades
    # EXCLUDE BASELINE TRADES (data collection only - not for analytics)
    if strategy and strategy.lower() != 'all':
        query = select(TradeSetup).where(
            TradeSetup.webhook_source == strategy,
            TradeSetup.status.in_(["completed", "active"]),
            TradeSetup.risk_strategy != 'baseline'
        )
    else:
        query = select(TradeSetup).where(
            TradeSetup.status.in_(["completed", "active"]),
            TradeSetup.risk_strategy != 'baseline'
        )

    # Order by entry time to get chronological order
    result = await db.execute(query.order_by(TradeSetup.entry_timestamp.desc()))
    trades = result.scalars().all()

    if not trades:
        return {
            "strategy": strategy or "all",
            "total_trades": 0,
            "win_rate": 0,
            "avg_pnl_per_trade": 0,
            "total_realized_pnl": 0,
            "best_trade": None,
            "worst_trade": None,
            "strategies_comparison": [],
            "time_series": []
        }

    # If specific strategy, return detailed stats
    if strategy and strategy.lower() != 'all':
        # Separate completed and active trades
        completed_trades = [t for t in trades if t.status == "completed"]
        active_trades = [t for t in trades if t.status == "active"]
        
        # Win rate only counts completed trades
        winning_trades = [t for t in completed_trades if t.final_outcome in ["tp1", "tp2", "tp3"]]
        win_rate = len(winning_trades) / len(completed_trades) * 100 if completed_trades else 0

        # P&L includes both realized (completed) and unrealized (active)
        # For completed: use final_pnl_pct, for active: use max_profit_pct (floating P&L)
        # IMPORTANT: Convert position P&L to account P&L by factoring in position size
        pnl_values = []  # Position P&L (for display/comparison)
        account_pnl_values = []  # Account P&L (for cumulative calculation)

        for t in trades:
            # Get ACTUAL current position P&L (not max_profit for active)
            position_pnl = await get_current_pnl_for_trade(t, db)
            
            pnl_values.append(position_pnl)

            # Convert to account P&L: position_pnl × (notional_position / account_balance)
            notional_position = float(t.notional_position_usd or 0)
            if notional_position > 0 and account_balance > 0:
                position_size_fraction = notional_position / account_balance
                account_pnl = position_pnl * position_size_fraction
            else:
                account_pnl = 0

            account_pnl_values.append(account_pnl)

        avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0

        # Calculate cumulative P&L using compound returns on ACCOUNT P&L
        cumulative_factor = 1.0
        for account_pnl in account_pnl_values:
            cumulative_factor *= (1 + account_pnl / 100)
        total_pnl = (cumulative_factor - 1) * 100

        # Best/worst trade calculation using ACTUAL current P&L
        # Pre-fetch all current P&Ls for active trades to avoid N+1 queries
        trade_pnls = {}
        for t in trades:
            trade_pnls[t.id] = await get_current_pnl_for_trade(t, db)
        
        best_trade = max(trades, key=lambda t: trade_pnls[t.id]) if trades else None
        worst_trade = min(trades, key=lambda t: trade_pnls[t.id]) if trades else None

        # Time series for chart (last 50 trades, including active)
        time_series = []
        cumulative_factor = 1.0  # Start at 1.0 for compound returns
        peak_pnl = 0  # Track highest cumulative P&L (peak)

        for t in reversed(trades[-50:]):
            # Get ACTUAL current position P&L
            position_pnl = await get_current_pnl_for_trade(t, db)

            # Convert to account P&L by factoring in position size
            notional_position = float(t.notional_position_usd or 0)
            if notional_position > 0 and account_balance > 0:
                position_size_fraction = notional_position / account_balance
                account_pnl = position_pnl * position_size_fraction
            else:
                account_pnl = 0

            # Calculate compound return on ACCOUNT P&L: (1 + r1) × (1 + r2) × ... - 1
            cumulative_factor *= (1 + account_pnl / 100)
            cumulative_pnl = (cumulative_factor - 1) * 100  # Convert back to percentage

            # Update peak and calculate drawdown
            if cumulative_pnl > peak_pnl:
                peak_pnl = cumulative_pnl
            drawdown = cumulative_pnl - peak_pnl  # Negative when in drawdown

            time_series.append({
                "timestamp": t.completed_at.isoformat() if t.completed_at else t.entry_timestamp.isoformat(),
                "pnl_pct": round(position_pnl, 2),  # Show position P&L for individual trade
                "account_pnl_pct": round(account_pnl, 4),  # Account impact
                "cumulative_pnl": round(cumulative_pnl, 2),  # Cumulative account P&L
                "drawdown": round(drawdown, 2),  # Drawdown from peak
                "symbol": t.symbol,
                "status": t.status  # Include status so frontend can distinguish
            })

        return {
            "strategy": strategy,
            "total_trades": len(trades),
            "completed_trades": len(completed_trades),
            "active_trades": len(active_trades),
            "win_rate": round(win_rate, 2),
            "avg_pnl_per_trade": round(avg_pnl, 2),
            "total_realized_pnl": round(total_pnl, 2),  # Now includes unrealized from active trades
            "best_trade": {
                "id": best_trade.id,
                "symbol": best_trade.symbol,
                "pnl_pct": float(best_trade.final_pnl_pct or 0),
                "direction": best_trade.direction,
                "completed_at": best_trade.completed_at.isoformat() if best_trade.completed_at else None
            },
            "worst_trade": {
                "id": worst_trade.id,
                "symbol": worst_trade.symbol,
                "pnl_pct": float(worst_trade.final_pnl_pct or 0),
                "direction": worst_trade.direction,
                "completed_at": worst_trade.completed_at.isoformat() if worst_trade.completed_at else None
            },
            "time_series": time_series
        }

    # ALL strategies - return comparison table
    strategies_data = {}

    for trade in trades:
        strat = trade.webhook_source or "unknown"
        if strat not in strategies_data:
            strategies_data[strat] = {
                "trades": [],
                "completed_trades": [],
                "active_trades": [],
                "wins": 0
            }

        strategies_data[strat]["trades"].append(trade)
        
        if trade.status == "completed":
            strategies_data[strat]["completed_trades"].append(trade)
            if trade.final_outcome in ["tp1", "tp2", "tp3"]:
                strategies_data[strat]["wins"] += 1
        else:
            strategies_data[strat]["active_trades"].append(trade)

    # Calculate stats for each strategy (including floating P&L)
    comparison = []
    for strat_name, data in strategies_data.items():
        trades_list = data["trades"]
        completed = data["completed_trades"]
        active = data["active_trades"]
        
        # P&L includes both realized (completed) and unrealized (active)
        # Factor in position size to get account-level P&L
        pnl_values = []  # Position P&L
        account_pnl_values = []  # Account P&L

        for t in trades_list:
            # Get ACTUAL current position P&L
            position_pnl = await get_current_pnl_for_trade(t, db)
            
            pnl_values.append(position_pnl)

            # Convert to account P&L
            notional_position = float(t.notional_position_usd or 0)
            if notional_position > 0 and account_balance > 0:
                position_size_fraction = notional_position / account_balance
                account_pnl = position_pnl * position_size_fraction
            else:
                account_pnl = 0

            account_pnl_values.append(account_pnl)

        # Calculate cumulative P&L using compound returns on ACCOUNT P&L
        cumulative_factor = 1.0
        for account_pnl in account_pnl_values:
            cumulative_factor *= (1 + account_pnl / 100)
        total_pnl = (cumulative_factor - 1) * 100

        comparison.append({
            "strategy": strat_name,
            "total_trades": len(trades_list),
            "completed_trades": len(completed),
            "active_trades": len(active),
            "win_rate": round(data["wins"] / len(completed) * 100, 2) if completed else 0,
            "avg_pnl_per_trade": round(sum(pnl_values) / len(pnl_values), 2) if pnl_values else 0,
            "total_realized_pnl": round(total_pnl, 2),  # Compound returns, includes unrealized
            "best_trade": float(max(pnl_values)) if pnl_values else 0,
            "worst_trade": float(min(pnl_values)) if pnl_values else 0
        })

    # Sort by total realized P&L
    comparison.sort(key=lambda x: x["total_realized_pnl"], reverse=True)

    # Time series for all strategies combined (last 100 trades, including active)
    time_series = []
    cumulative_factor = 1.0  # Start at 1.0 for compound returns
    peak_pnl = 0  # Track highest cumulative P&L (peak)

    for t in reversed(trades[-100:]):
        # Get position P&L
        position_pnl = float(t.final_pnl_pct or 0) if t.status == "completed" else float(t.max_profit_pct or 0)

        # Convert to account P&L by factoring in position size
        notional_position = float(t.notional_position_usd or 0)
        if notional_position > 0 and account_balance > 0:
            position_size_fraction = notional_position / account_balance
            account_pnl = position_pnl * position_size_fraction
        else:
            account_pnl = 0

        # Calculate compound return on ACCOUNT P&L: (1 + r1) × (1 + r2) × ... - 1
        cumulative_factor *= (1 + account_pnl / 100)
        cumulative_pnl = (cumulative_factor - 1) * 100  # Convert back to percentage

        # Update peak and calculate drawdown
        if cumulative_pnl > peak_pnl:
            peak_pnl = cumulative_pnl
        drawdown = cumulative_pnl - peak_pnl  # Negative when in drawdown

        time_series.append({
            "timestamp": t.completed_at.isoformat() if t.completed_at else t.entry_timestamp.isoformat(),
            "pnl_pct": round(position_pnl, 2),  # Show position P&L for individual trade
            "account_pnl_pct": round(account_pnl, 4),  # Account impact
            "cumulative_pnl": round(cumulative_pnl, 2),  # Cumulative account P&L
            "drawdown": round(drawdown, 2),  # Drawdown from peak
            "strategy": t.webhook_source or "unknown",
            "symbol": t.symbol,
            "status": t.status  # Include status
        })

    return {
        "strategy": "all",
        "total_trades": len(trades),
        "strategies_comparison": comparison,
        "time_series": time_series
    }


@router.get("/")
async def root():
    """
    API root - Show available endpoints
    """
    return {
        "name": "Andre Assassin Trading Analysis API",
        "version": "1.0.0",
        "description": "AI-powered trading analysis with data-driven TP/SL optimization",
        "endpoints": {
            "webhook": "POST /api/webhook/tradingview - THE ENTRY POINT",
            "active_trades": "GET /api/trades/active",
            "recent_signals": "GET /api/trades/recent-signals",
            "live_activity": "GET /api/trades/live-activity",
            "trade_history": "GET /api/trades/history",
            "trade_details": "GET /api/trades/{trade_id}",
            "statistics": "GET /api/statistics/{symbol}",
            "analytics_by_strategy": "GET /api/analytics/by-strategy - Strategy performance analytics",
            "websocket_stats": "GET /api/websocket/stats - Multiplexing metrics",
            "tracking_start": "POST /api/tracking/start - Start price tracking",
            "health": "GET /api/health",
        },
        "docs": "/docs",
        "redoc": "/redoc",
    }
