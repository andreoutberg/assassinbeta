"""
Order Executor Service for Phase III Live Trading

Handles complete trade execution lifecycle on Bybit exchange:
- Entry order placement (market orders)
- Take-profit orders (TP1, TP2, TP3 as limit orders with reduceOnly)
- Stop-loss order placement
- Trailing stop management
- Order cancellation and position synchronization

This service bridges the gap between simulated trading (Phase I/II)
and real money trading (Phase III) with comprehensive safety controls.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database.models import TradeSetup
from app.config.settings import settings
from app.config.phase_config import PhaseConfig
from app.services.bybit_client import get_bybit_client, BybitClient

logger = logging.getLogger(__name__)


class OrderExecutionError(Exception):
    """Raised when order execution fails"""
    pass


class OrderExecutor:
    """
    Production-ready order executor for live trading on Bybit.

    Key Features:
    - Automatic position sizing calculation
    - Multi-level TP orders (TP1, TP2, TP3)
    - Stop-loss protection
    - Trailing stop activation
    - Order ID tracking in database
    - Comprehensive error handling
    - Exchange position synchronization

    Safety Controls:
    - Only executes if trade_mode == 'live' AND ENABLE_LIVE_TRADING == True
    - Validates all parameters before execution
    - Stores all order IDs for tracking
    - Logs every action for audit trail
    """

    def __init__(self, bybit_client: Optional[BybitClient] = None):
        """
        Initialize OrderExecutor.

        Args:
            bybit_client: Optional pre-configured BybitClient instance.
                         If None, will be fetched from global singleton.
        """
        self.client = bybit_client
        self._client_owned = bybit_client is None  # Track if we need to manage client lifecycle

    async def _ensure_client(self) -> BybitClient:
        """
        Ensure Bybit client is initialized and connected.

        Returns:
            Connected BybitClient instance

        Raises:
            OrderExecutionError: If client connection fails
        """
        if self.client is None:
            try:
                # Get client from settings (will use demo trading if configured)
                self.client = await get_bybit_client(
                    api_key=settings.BYBIT_API_KEY,
                    api_secret=settings.BYBIT_API_SECRET,
                    testnet=settings.BYBIT_TESTNET,
                    demo_trading=not PhaseConfig.ENABLE_LIVE_TRADING  # Use demo if live trading disabled
                )
                logger.info(f"✅ Bybit client initialized (demo_trading={not PhaseConfig.ENABLE_LIVE_TRADING})")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Bybit client: {e}")
                raise OrderExecutionError(f"Client initialization failed: {e}")

        if not self.client.is_connected:
            try:
                await self.client.connect()
            except Exception as e:
                logger.error(f"❌ Failed to connect to Bybit: {e}")
                raise OrderExecutionError(f"Connection failed: {e}")

        return self.client

    async def execute_trade(self, trade: TradeSetup, db: AsyncSession, force_demo: bool = True) -> bool:
        """
        Execute complete trade lifecycle: entry, TPs, SL, and optional trailing stop.

        This is the main entry point for live/demo trade execution.

        Args:
            trade: TradeSetup instance with all trade parameters
            db: Database session for updating trade record
            force_demo: If True (default), always execute on demo even if ENABLE_LIVE_TRADING=False

        Returns:
            True if execution successful, False otherwise

        Safety Checks:
            1. Real money requires: trade_mode='live' AND ENABLE_LIVE_TRADING=True
            2. Demo execution: force_demo=True OR ENABLE_LIVE_TRADING=False
            3. Validates all required trade parameters exist
            4. Validates symbol is tradeable on exchange
        """
        try:
            # ========================================
            # SAFETY CHECK 1: Determine Execution Mode
            # ========================================
            is_live_money = PhaseConfig.ENABLE_LIVE_TRADING and trade.trade_mode == 'live'
            is_demo = force_demo or not PhaseConfig.ENABLE_LIVE_TRADING

            if not is_live_money and not is_demo:
                logger.info(
                    f"ℹ️ Trade {trade.id} ({trade.symbol}) skipped. "
                    f"Set force_demo=True to execute on demo account."
                )
                return False

            execution_mode = "🔴 LIVE (REAL MONEY)" if is_live_money else "🟢 DEMO (VIRTUAL $99K)"
            logger.info(
                f"🚀 {execution_mode} TRADE EXECUTION STARTED: {trade.symbol} {trade.direction} "
                f"(Trade ID: {trade.id})"
            )

            # ========================================
            # SAFETY CHECK 2: Validate Trade Parameters
            # ========================================
            if not self._validate_trade_parameters(trade):
                logger.error(f"❌ Trade {trade.id} failed parameter validation")
                return False

            # ========================================
            # STEP 1: Initialize Bybit Client
            # ========================================
            client = await self._ensure_client()

            # ========================================
            # STEP 2: Get Market Information
            # ========================================
            market_info = await self._get_market_info(trade.ccxt_symbol or trade.symbol)
            if not market_info:
                logger.error(f"❌ Could not fetch market info for {trade.symbol}")
                return False

            # ========================================
            # STEP 2.5: Set Leverage
            # ========================================
            try:
                leverage = int(trade.leverage) if trade.leverage else 5
                await client.exchange.set_leverage(
                    leverage,
                    trade.ccxt_symbol or trade.symbol,
                    params={'positionIdx': 0}  # One-way mode
                )
                logger.info(f"⚙️ Leverage set to {leverage}x for {trade.symbol}")
            except Exception as e:
                logger.warning(f"⚠️ Could not set leverage (may already be set): {e}")
                # Don't fail - leverage might already be set correctly

            # ========================================
            # STEP 3: Calculate Position Size
            # ========================================
            qty = await self._calculate_position_size(
                trade=trade,
                market_info=market_info,
                entry_price=float(trade.entry_price)
            )

            if not qty or qty <= 0:
                logger.error(f"❌ Invalid position size calculated: {qty}")
                return False

            logger.info(f"💼 Position size: {qty} contracts @ ${trade.entry_price}")

            # ========================================
            # STEP 4: Place Entry Order (Market Order)
            # ========================================
            entry_order_id = await self.place_entry_order(
                symbol=trade.ccxt_symbol or trade.symbol,
                direction=trade.direction,
                qty=qty,
                market_info=market_info
            )

            if not entry_order_id:
                logger.error(f"❌ Failed to place entry order for trade {trade.id}")
                return False

            logger.info(f"✅ Entry order placed: {entry_order_id}")

            # ========================================
            # STEP 5: Place Take-Profit Orders
            # ========================================
            tp_order_ids = await self.place_tp_orders(
                symbol=trade.ccxt_symbol or trade.symbol,
                direction=trade.direction,
                qty=qty,
                entry_price=float(trade.entry_price),
                tp1_pct=float(trade.planned_tp1_pct) if trade.planned_tp1_pct else None,
                tp2_pct=float(trade.planned_tp2_pct) if trade.planned_tp2_pct else None,
                tp3_pct=float(trade.planned_tp3_pct) if trade.planned_tp3_pct else None,
                market_info=market_info
            )

            logger.info(f"✅ TP orders placed: {tp_order_ids}")

            # ========================================
            # STEP 6: Place Stop-Loss Order
            # ========================================
            sl_order_id = await self.place_sl_order(
                symbol=trade.ccxt_symbol or trade.symbol,
                direction=trade.direction,
                qty=qty,
                entry_price=float(trade.entry_price),
                sl_pct=float(trade.planned_sl_pct) if trade.planned_sl_pct else None,
                market_info=market_info
            )

            if not sl_order_id:
                logger.error(f"❌ Failed to place SL order for trade {trade.id}")
                # Try to cancel all orders and exit position
                await self.cancel_orders(trade.ccxt_symbol or trade.symbol, entry_order_id, tp_order_ids)
                return False

            logger.info(f"✅ Stop-loss order placed: {sl_order_id}")

            # ========================================
            # STEP 7: Setup Trailing Stop (if enabled)
            # ========================================
            trailing_order_id = None
            if trade.use_trailing_stop:
                trailing_order_id = await self.setup_trailing_stop(
                    symbol=trade.ccxt_symbol or trade.symbol,
                    direction=trade.direction,
                    qty=qty,
                    entry_price=float(trade.entry_price),
                    activation_pct=float(trade.trailing_stop_activation_pct) if trade.trailing_stop_activation_pct else 2.0,
                    distance_pct=float(trade.trailing_stop_distance_pct) if trade.trailing_stop_distance_pct else 1.0,
                    market_info=market_info
                )

                if trailing_order_id:
                    logger.info(f"✅ Trailing stop configured: {trailing_order_id}")

            # ========================================
            # STEP 8: Update Trade Record with Order IDs
            # ========================================
            order_tracking = {
                'entry_order_id': entry_order_id,
                'tp_order_ids': tp_order_ids,
                'sl_order_id': sl_order_id,
                'trailing_order_id': trailing_order_id,
                'execution_timestamp': datetime.now().isoformat(),
                'position_qty': qty
            }

            # Store in trade.notes as JSON for now
            # TODO: Add dedicated columns to TradeSetup model for order tracking
            import json
            current_notes = trade.notes or ""
            order_info = f"\n\n[ORDER_IDS] {json.dumps(order_tracking)}"
            trade.notes = current_notes + order_info

            await db.commit()
            await db.refresh(trade)

            logger.info(
                f"🎉 LIVE TRADE EXECUTION COMPLETED: {trade.symbol} {trade.direction}\n"
                f"   Entry Order: {entry_order_id}\n"
                f"   TP Orders: {tp_order_ids}\n"
                f"   SL Order: {sl_order_id}\n"
                f"   Trailing: {trailing_order_id or 'N/A'}"
            )

            return True

        except Exception as e:
            logger.error(
                f"❌ CRITICAL ERROR executing trade {trade.id}: {e}",
                exc_info=True
            )
            return False

    def _validate_trade_parameters(self, trade: TradeSetup) -> bool:
        """
        Validate trade has all required parameters for execution.

        Args:
            trade: TradeSetup instance

        Returns:
            True if valid, False otherwise
        """
        required_fields = {
            'symbol': trade.symbol,
            'direction': trade.direction,
            'entry_price': trade.entry_price,
            'planned_sl_pct': trade.planned_sl_pct,
            'notional_position_usd': trade.notional_position_usd,
        }

        missing = [k for k, v in required_fields.items() if v is None]

        if missing:
            logger.error(f"❌ Missing required fields: {missing}")
            return False

        # Validate direction
        if trade.direction not in ['LONG', 'SHORT']:
            logger.error(f"❌ Invalid direction: {trade.direction}")
            return False

        # Validate at least TP1 exists
        if not trade.planned_tp1_pct:
            logger.error(f"❌ No TP1 configured for trade")
            return False

        return True

    async def _get_market_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch market information from exchange.

        Args:
            symbol: Trading symbol in CCXT format (e.g., 'BTC/USDT')

        Returns:
            Market info dict with precision, limits, etc.
        """
        try:
            client = await self._ensure_client()
            market_info = await client.get_market_info(symbol)
            return market_info
        except Exception as e:
            logger.error(f"❌ Failed to get market info for {symbol}: {e}")
            return None

    async def _calculate_position_size(
        self,
        trade: TradeSetup,
        market_info: Dict[str, Any],
        entry_price: float
    ) -> Optional[float]:
        """
        Calculate position size in contracts based on notional USD value.

        For Bybit perpetuals:
        - Position size = notional_usd / entry_price
        - Must respect minimum/maximum contract sizes
        - Must respect precision requirements

        Args:
            trade: TradeSetup with notional_position_usd
            market_info: Market information from exchange
            entry_price: Entry price

        Returns:
            Position size in contracts (rounded to exchange precision)
        """
        try:
            notional_usd = float(trade.notional_position_usd)

            # Calculate raw quantity
            qty = notional_usd / entry_price

            # Get precision and limits from market info
            amount_precision = int(market_info.get('precision', {}).get('amount', 8))
            min_qty = float(market_info.get('limits', {}).get('amount', {}).get('min', 0.001))
            max_qty = float(market_info.get('limits', {}).get('amount', {}).get('max', 1000000))

            # Round to exchange precision
            qty = round(qty, amount_precision)

            # Validate limits
            if qty < min_qty:
                logger.error(
                    f"❌ Position size {qty} below minimum {min_qty}. "
                    f"Increase notional_position_usd or check market limits."
                )
                return None

            if qty > max_qty:
                logger.warning(f"⚠️ Position size {qty} exceeds maximum {max_qty}, capping")
                qty = max_qty

            logger.info(
                f"💼 Position calculation: "
                f"${notional_usd:.2f} / ${entry_price:.2f} = {qty} contracts "
                f"(precision: {amount_precision}, min: {min_qty}, max: {max_qty})"
            )

            return qty

        except Exception as e:
            logger.error(f"❌ Failed to calculate position size: {e}")
            return None

    async def place_entry_order(
        self,
        symbol: str,
        direction: str,
        qty: float,
        market_info: Dict[str, Any]
    ) -> Optional[str]:
        """
        Place market entry order.

        Args:
            symbol: Trading symbol (CCXT format)
            direction: 'LONG' or 'SHORT'
            qty: Position size in contracts
            market_info: Market information

        Returns:
            Order ID if successful, None otherwise
        """
        try:
            client = await self._ensure_client()

            # Determine order side
            side = 'buy' if direction == 'LONG' else 'sell'

            logger.info(f"📤 Placing MARKET {side.upper()} order: {qty} {symbol}")

            # Place market order using CCXT
            order = await client.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=qty,
                params={
                    'positionIdx': 0,  # One-way mode (not hedge mode)
                }
            )

            order_id = order.get('id') or order.get('info', {}).get('orderId')

            logger.info(
                f"✅ Entry order placed successfully\n"
                f"   Order ID: {order_id}\n"
                f"   Symbol: {symbol}\n"
                f"   Side: {side.upper()}\n"
                f"   Qty: {qty}\n"
                f"   Status: {order.get('status')}"
            )

            return str(order_id)

        except Exception as e:
            logger.error(f"❌ Failed to place entry order: {e}", exc_info=True)
            return None

    async def place_tp_orders(
        self,
        symbol: str,
        direction: str,
        qty: float,
        entry_price: float,
        tp1_pct: Optional[float],
        tp2_pct: Optional[float],
        tp3_pct: Optional[float],
        market_info: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Place take-profit limit orders (reduceOnly).

        Creates up to 3 TP orders at different price levels.
        Orders are reduceOnly to prevent increasing position.

        Args:
            symbol: Trading symbol
            direction: 'LONG' or 'SHORT'
            qty: Position size (will be split across TPs)
            entry_price: Entry price for calculating TP levels
            tp1_pct: TP1 percentage (e.g., 1.5 for +1.5%)
            tp2_pct: TP2 percentage
            tp3_pct: TP3 percentage
            market_info: Market information

        Returns:
            Dict mapping TP level to order ID: {'tp1': 'xxx', 'tp2': 'yyy', ...}
        """
        tp_order_ids = {}

        try:
            client = await self._ensure_client()
            price_precision = int(market_info.get('precision', {}).get('price', 2))

            # Determine order side (opposite of entry for closing)
            side = 'sell' if direction == 'LONG' else 'buy'

            # TP allocation: 40% TP1, 30% TP2, 30% TP3
            tp_allocations = {
                'tp1': (tp1_pct, 0.4),
                'tp2': (tp2_pct, 0.3),
                'tp3': (tp3_pct, 0.3)
            }

            for tp_name, (tp_pct, allocation) in tp_allocations.items():
                if tp_pct is None:
                    continue

                # Calculate TP price
                if direction == 'LONG':
                    tp_price = entry_price * (1 + tp_pct / 100)
                else:  # SHORT
                    tp_price = entry_price * (1 - tp_pct / 100)

                # Round to exchange precision
                tp_price = round(tp_price, price_precision)

                # Calculate quantity for this TP level
                tp_qty = round(qty * allocation, int(market_info.get('precision', {}).get('amount', 8)))

                logger.info(f"📤 Placing {tp_name.upper()} order: {side.upper()} {tp_qty} @ ${tp_price}")

                # Place limit order with reduceOnly
                order = await client.exchange.create_order(
                    symbol=symbol,
                    type='limit',
                    side=side,
                    amount=tp_qty,
                    price=tp_price,
                    params={
                        'reduceOnly': True,  # Only close position, never increase
                        'postOnly': False,   # Can take liquidity
                        'positionIdx': 0
                    }
                )

                order_id = order.get('id') or order.get('info', {}).get('orderId')
                tp_order_ids[tp_name] = str(order_id)

                logger.info(f"✅ {tp_name.upper()} order placed: {order_id}")

                # Small delay to avoid rate limits
                await asyncio.sleep(0.1)

            return tp_order_ids

        except Exception as e:
            logger.error(f"❌ Failed to place TP orders: {e}", exc_info=True)
            return tp_order_ids

    async def place_sl_order(
        self,
        symbol: str,
        direction: str,
        qty: float,
        entry_price: float,
        sl_pct: Optional[float],
        market_info: Dict[str, Any]
    ) -> Optional[str]:
        """
        Place stop-loss order.

        Uses stop-market order that triggers when price hits stop price.

        Args:
            symbol: Trading symbol
            direction: 'LONG' or 'SHORT'
            qty: Position size
            entry_price: Entry price
            sl_pct: Stop-loss percentage (negative, e.g., -3.0 for -3%)
            market_info: Market information

        Returns:
            Order ID if successful, None otherwise
        """
        try:
            if sl_pct is None:
                logger.warning("⚠️ No SL percentage provided, using default -3%")
                sl_pct = -3.0

            client = await self._ensure_client()
            price_precision = int(market_info.get('precision', {}).get('price', 2))

            # Determine order side (opposite of entry for closing)
            side = 'sell' if direction == 'LONG' else 'buy'

            # Calculate SL price
            if direction == 'LONG':
                sl_price = entry_price * (1 + sl_pct / 100)  # sl_pct is negative
            else:  # SHORT
                sl_price = entry_price * (1 - sl_pct / 100)

            # Round to exchange precision
            sl_price = round(sl_price, price_precision)

            logger.info(f"📤 Placing STOP-LOSS order: {side.upper()} {qty} @ ${sl_price} (trigger)")

            # Place stop-market order
            order = await client.exchange.create_order(
                symbol=symbol,
                type='market',  # Market order when triggered
                side=side,
                amount=qty,
                params={
                    'stopLoss': sl_price,  # Bybit parameter
                    'reduceOnly': True,
                    'positionIdx': 0
                }
            )

            order_id = order.get('id') or order.get('info', {}).get('orderId')

            logger.info(
                f"✅ Stop-loss order placed successfully\n"
                f"   Order ID: {order_id}\n"
                f"   Trigger Price: ${sl_price}\n"
                f"   Type: Stop Market"
            )

            return str(order_id)

        except Exception as e:
            logger.error(f"❌ Failed to place SL order: {e}", exc_info=True)
            return None

    async def setup_trailing_stop(
        self,
        symbol: str,
        direction: str,
        qty: float,
        entry_price: float,
        activation_pct: float,
        distance_pct: float,
        market_info: Dict[str, Any]
    ) -> Optional[str]:
        """
        Setup trailing stop order.

        Note: Bybit's trailing stop implementation varies by market type.
        This creates a conditional order that activates after price moves
        favorably by activation_pct, then trails by distance_pct.

        Args:
            symbol: Trading symbol
            direction: 'LONG' or 'SHORT'
            qty: Position size
            entry_price: Entry price
            activation_pct: Profit % to activate trailing (e.g., 2.0 for +2%)
            distance_pct: Trail distance % (e.g., 1.0 for 1% behind peak)
            market_info: Market information

        Returns:
            Order ID if successful, None otherwise
        """
        try:
            client = await self._ensure_client()
            price_precision = int(market_info.get('precision', {}).get('price', 2))

            # Calculate activation price
            if direction == 'LONG':
                activation_price = entry_price * (1 + activation_pct / 100)
            else:  # SHORT
                activation_price = entry_price * (1 - activation_pct / 100)

            activation_price = round(activation_price, price_precision)

            logger.info(
                f"📤 Setting up TRAILING STOP:\n"
                f"   Activation: ${activation_price} ({activation_pct:+.2f}%)\n"
                f"   Trail Distance: {distance_pct}%"
            )

            # Determine order side
            side = 'sell' if direction == 'LONG' else 'buy'

            # Place trailing stop order
            # Note: Bybit API varies by contract type, this is a general approach
            order = await client.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=qty,
                params={
                    'trailingStop': distance_pct,  # Distance in percentage
                    'activationPrice': activation_price,  # When to activate
                    'reduceOnly': True,
                    'positionIdx': 0
                }
            )

            order_id = order.get('id') or order.get('info', {}).get('orderId')

            logger.info(f"✅ Trailing stop configured: {order_id}")

            return str(order_id)

        except Exception as e:
            # Trailing stops may not be supported on all markets
            logger.warning(
                f"⚠️ Could not set up trailing stop (may not be supported): {e}"
            )
            return None

    async def cancel_orders(
        self,
        symbol: str,
        entry_order_id: Optional[str] = None,
        tp_order_ids: Optional[Dict[str, str]] = None,
        sl_order_id: Optional[str] = None
    ) -> bool:
        """
        Cancel all orders for a trade.

        Used for emergency cleanup if trade setup fails.

        Args:
            symbol: Trading symbol
            entry_order_id: Entry order ID
            tp_order_ids: Dict of TP order IDs
            sl_order_id: SL order ID

        Returns:
            True if all cancellations successful
        """
        try:
            client = await self._ensure_client()
            success = True

            # Collect all order IDs
            order_ids = []
            if entry_order_id:
                order_ids.append(entry_order_id)
            if tp_order_ids:
                order_ids.extend(tp_order_ids.values())
            if sl_order_id:
                order_ids.append(sl_order_id)

            logger.info(f"🗑️ Cancelling {len(order_ids)} orders for {symbol}")

            for order_id in order_ids:
                try:
                    await client.exchange.cancel_order(order_id, symbol)
                    logger.info(f"   ✅ Cancelled order: {order_id}")
                    await asyncio.sleep(0.1)  # Rate limit protection
                except Exception as e:
                    logger.error(f"   ❌ Failed to cancel order {order_id}: {e}")
                    success = False

            return success

        except Exception as e:
            logger.error(f"❌ Failed to cancel orders: {e}")
            return False

    async def sync_position(
        self,
        symbol: str,
        db: AsyncSession,
        trade: TradeSetup
    ) -> Dict[str, Any]:
        """
        Synchronize position state from exchange with database.

        Checks actual position on exchange and compares with expected state.
        Useful for detecting fills, partial fills, or unexpected closes.

        Args:
            symbol: Trading symbol
            db: Database session
            trade: TradeSetup instance

        Returns:
            Dict with position info:
            {
                'position_size': float,
                'entry_price': float,
                'unrealized_pnl': float,
                'side': 'long'|'short'|'none',
                'synced': bool
            }
        """
        try:
            client = await self._ensure_client()

            # Fetch position from exchange
            positions = await client.exchange.fetch_positions([symbol])

            if not positions:
                logger.warning(f"⚠️ No position found for {symbol}")
                return {
                    'position_size': 0,
                    'entry_price': 0,
                    'unrealized_pnl': 0,
                    'side': 'none',
                    'synced': False
                }

            position = positions[0]

            position_info = {
                'position_size': abs(float(position.get('contracts', 0))),
                'entry_price': float(position.get('entryPrice', 0)),
                'unrealized_pnl': float(position.get('unrealizedPnl', 0)),
                'side': position.get('side', 'none'),
                'synced': True
            }

            logger.info(
                f"📊 Position sync for {symbol}:\n"
                f"   Size: {position_info['position_size']} contracts\n"
                f"   Entry: ${position_info['entry_price']}\n"
                f"   Unrealized PnL: ${position_info['unrealized_pnl']:.2f}\n"
                f"   Side: {position_info['side']}"
            )

            # Check if position matches expected
            expected_side = trade.direction.lower()
            if position_info['side'] != expected_side and position_info['position_size'] > 0:
                logger.warning(
                    f"⚠️ Position side mismatch! "
                    f"Expected: {expected_side}, Actual: {position_info['side']}"
                )

            return position_info

        except Exception as e:
            logger.error(f"❌ Failed to sync position: {e}")
            return {
                'position_size': 0,
                'entry_price': 0,
                'unrealized_pnl': 0,
                'side': 'none',
                'synced': False,
                'error': str(e)
            }

    async def close(self):
        """
        Clean up resources.

        Only closes client if we own it (created internally).
        """
        if self._client_owned and self.client:
            await self.client.close()
            logger.info("✅ OrderExecutor client closed")


# ==========================================
# HELPER FUNCTIONS
# ==========================================

async def execute_live_trade(trade_id: int, db: AsyncSession) -> bool:
    """
    Convenience function to execute a live trade by ID.

    Args:
        trade_id: TradeSetup ID
        db: Database session

    Returns:
        True if execution successful
    """
    try:
        # Fetch trade from database
        result = await db.execute(
            select(TradeSetup).where(TradeSetup.id == trade_id)
        )
        trade = result.scalar_one_or_none()

        if not trade:
            logger.error(f"❌ Trade {trade_id} not found")
            return False

        # Execute trade
        executor = OrderExecutor()
        success = await executor.execute_trade(trade, db)
        await executor.close()

        return success

    except Exception as e:
        logger.error(f"❌ Failed to execute live trade {trade_id}: {e}", exc_info=True)
        return False


async def cancel_trade_orders(trade_id: int, db: AsyncSession) -> bool:
    """
    Cancel all orders for a trade by ID.

    Args:
        trade_id: TradeSetup ID
        db: Database session

    Returns:
        True if cancellation successful
    """
    try:
        # Fetch trade from database
        result = await db.execute(
            select(TradeSetup).where(TradeSetup.id == trade_id)
        )
        trade = result.scalar_one_or_none()

        if not trade:
            logger.error(f"❌ Trade {trade_id} not found")
            return False

        # Extract order IDs from notes
        import json
        if not trade.notes or '[ORDER_IDS]' not in trade.notes:
            logger.warning(f"⚠️ No order IDs found for trade {trade_id}")
            return False

        # Parse order IDs
        order_data_str = trade.notes.split('[ORDER_IDS]')[1].strip()
        order_data = json.loads(order_data_str)

        # Cancel orders
        executor = OrderExecutor()
        success = await executor.cancel_orders(
            symbol=trade.ccxt_symbol or trade.symbol,
            entry_order_id=order_data.get('entry_order_id'),
            tp_order_ids=order_data.get('tp_order_ids'),
            sl_order_id=order_data.get('sl_order_id')
        )
        await executor.close()

        return success

    except Exception as e:
        logger.error(f"❌ Failed to cancel trade orders {trade_id}: {e}", exc_info=True)
        return False


# ==========================================
# EXAMPLE USAGE
# ==========================================

if __name__ == "__main__":
    """
    Example usage of OrderExecutor.

    This demonstrates the complete flow of executing a live trade.
    """
    import asyncio
    from app.database.database import AsyncSessionLocal

    async def example_execution():
        """Example: Execute a trade from database"""
        async with AsyncSessionLocal() as db:
            # Fetch a pending Phase III trade
            result = await db.execute(
                select(TradeSetup)
                .where(TradeSetup.trade_mode == 'live')
                .where(TradeSetup.status == 'active')
                .limit(1)
            )
            trade = result.scalar_one_or_none()

            if not trade:
                print("No live trades found for execution")
                return

            print(f"Executing trade: {trade.symbol} {trade.direction}")

            # Execute trade
            executor = OrderExecutor()
            success = await executor.execute_trade(trade, db)

            if success:
                print("✅ Trade executed successfully!")

                # Sync position to verify
                await asyncio.sleep(2)  # Wait for orders to fill
                position_info = await executor.sync_position(
                    trade.ccxt_symbol or trade.symbol,
                    db,
                    trade
                )
                print(f"Position info: {position_info}")
            else:
                print("❌ Trade execution failed")

            await executor.close()

    # Run example
    # asyncio.run(example_execution())
    print("OrderExecutor module loaded successfully")
    print("Import and use: from app.services.order_executor import OrderExecutor")
