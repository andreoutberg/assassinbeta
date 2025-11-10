"""
Demo Strategy Simulator - Enhanced for Real-time Demo Trading
Simulates strategy outcomes using live Bybit demo prices instead of historical data.

Key Features:
- Real-time price fetching from Bybit demo API
- MAE/MFE simulation based on actual price movements
- Support for all 1,215 TP/SL combinations from phase_config
- Async operations for performance
"""
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database.models import TradeSetup, TradeMilestones
from app.database.strategy_models import StrategySimulation, StrategyPerformance
from app.config.phase_config import PhaseConfig
from app.utils.exceptions import SimulationError, InvalidTradeDataError
from app.models.strategy_types import StrategyConfig, SimulationResult
from datetime import datetime, timedelta
import logging
import asyncio
import aiohttp
import numpy as np
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class DemoStrategySimulator:
    """Enhanced simulator for demo trading with real Bybit prices"""

    # Bybit Demo API endpoints
    BYBIT_DEMO_BASE = "https://api-demo.bybit.com"
    BYBIT_KLINE_ENDPOINT = "/v5/market/kline"
    BYBIT_TICKER_ENDPOINT = "/v5/market/tickers"

    # Simulation parameters
    DEFAULT_LOOKBACK_MINUTES = 60  # How far back to fetch price data
    PRICE_UPDATE_INTERVAL = 1  # Seconds between price updates
    MAX_SIMULATION_DURATION_HOURS = 24  # Maximum time to simulate

    def __init__(self, session: AsyncSession):
        self.db = session
        self.http_session = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.http_session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.http_session:
            await self.http_session.close()

    async def fetch_demo_prices(
        self,
        symbol: str,
        interval: str = "1",
        limit: int = 200
    ) -> List[Dict]:
        """
        Fetch real-time price data from Bybit demo API

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            interval: Kline interval in minutes
            limit: Number of candles to fetch

        Returns:
            List of price candles with OHLCV data
        """
        if not self.http_session:
            self.http_session = aiohttp.ClientSession()

        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }

        try:
            async with self.http_session.get(
                f"{self.BYBIT_DEMO_BASE}{self.BYBIT_KLINE_ENDPOINT}",
                params=params
            ) as response:
                data = await response.json()

                if data.get("retCode") != 0:
                    raise SimulationError(f"Bybit API error: {data.get('retMsg')}")

                return data.get("result", {}).get("list", [])

        except Exception as e:
            logger.error(f"Error fetching demo prices: {str(e)}")
            raise SimulationError(f"Failed to fetch demo prices: {str(e)}")

    async def simulate_mae_mfe_realtime(
        self,
        entry_price: float,
        direction: str,
        symbol: str,
        duration_minutes: int = 60
    ) -> Tuple[float, float, List[Dict]]:
        """
        Simulate MAE/MFE using real-time demo prices

        Args:
            entry_price: Entry price of the trade
            direction: Trade direction ("LONG" or "SHORT")
            symbol: Trading symbol
            duration_minutes: How long to simulate

        Returns:
            Tuple of (MAE%, MFE%, milestone_events)
        """
        # Fetch recent price data
        price_data = await self.fetch_demo_prices(
            symbol=symbol,
            interval="1",
            limit=min(duration_minutes, 200)
        )

        if not price_data:
            raise SimulationError(f"No price data available for {symbol}")

        mae_pct = 0.0
        mfe_pct = 0.0
        milestone_events = []

        for i, candle in enumerate(price_data):
            # Parse candle data [timestamp, open, high, low, close, volume, turnover]
            timestamp = int(candle[0])
            open_price = float(candle[1])
            high_price = float(candle[2])
            low_price = float(candle[3])
            close_price = float(candle[4])

            # Calculate excursions for this candle
            if direction == "LONG":
                # For long: MAE is lowest point, MFE is highest point
                candle_mae = ((low_price - entry_price) / entry_price) * 100
                candle_mfe = ((high_price - entry_price) / entry_price) * 100
            else:  # SHORT
                # For short: MAE is highest point (adverse), MFE is lowest point (favorable)
                candle_mae = ((entry_price - high_price) / entry_price) * 100
                candle_mfe = ((entry_price - low_price) / entry_price) * 100

            # Update running MAE/MFE
            mae_pct = min(mae_pct, candle_mae)
            mfe_pct = max(mfe_pct, candle_mfe)

            # Record milestone events
            milestone_events.append({
                'timestamp': timestamp,
                'minute': i + 1,
                'price_low': low_price,
                'price_high': high_price,
                'price_close': close_price,
                'mae_pct': mae_pct,
                'mfe_pct': mfe_pct
            })

        return mae_pct, mfe_pct, milestone_events

    async def simulate_strategy_on_demo(
        self,
        trade: TradeSetup,
        strategy_config: Dict[str, Any],
        use_realtime_prices: bool = True
    ) -> SimulationResult:
        """
        Simulate strategy outcome using demo prices

        Args:
            trade: Trade setup to simulate
            strategy_config: Strategy parameters (TP/SL/trailing)
            use_realtime_prices: Whether to fetch real-time prices

        Returns:
            Simulation result with exit details
        """
        if not trade.entry_price or not trade.direction:
            raise InvalidTradeDataError(trade.id, "Missing required trade data")

        entry_price = float(trade.entry_price)
        direction = trade.direction

        # Extract strategy parameters
        tp_pct = strategy_config.get('tp_pct', 2.0)
        sl_pct = strategy_config.get('sl_pct', -1.0)
        trailing_config = strategy_config.get('trailing_config')
        breakeven_pct = strategy_config.get('breakeven_pct')

        # Calculate exit levels
        if direction == "LONG":
            tp_price = entry_price * (1 + tp_pct / 100)
            sl_price = entry_price * (1 + sl_pct / 100)
        else:  # SHORT
            tp_price = entry_price * (1 - tp_pct / 100)
            sl_price = entry_price * (1 - sl_pct / 100)

        # Fetch real-time prices or use existing milestones
        if use_realtime_prices:
            mae_pct, mfe_pct, events = await self.simulate_mae_mfe_realtime(
                entry_price=entry_price,
                direction=direction,
                symbol=trade.symbol,
                duration_minutes=60
            )
        else:
            # Use existing milestone data if available
            if hasattr(trade, 'milestones') and trade.milestones:
                milestone = trade.milestones[0] if isinstance(trade.milestones, list) else trade.milestones
                mae_pct = float(milestone.mae_pct) if milestone.mae_pct else 0
                mfe_pct = float(milestone.mfe_pct) if milestone.mfe_pct else 0
                events = []
            else:
                mae_pct = float(trade.mae_pct) if trade.mae_pct else 0
                mfe_pct = float(trade.mfe_pct) if trade.mfe_pct else 0
                events = []

        # Determine exit based on MAE/MFE
        exit_reason = None
        exit_price = None
        exit_pnl_pct = None

        # Check if TP was hit
        if mfe_pct >= tp_pct:
            exit_reason = "tp"
            exit_price = tp_price
            exit_pnl_pct = tp_pct if direction == "LONG" else -tp_pct

        # Check if SL was hit
        elif mae_pct <= sl_pct:
            exit_reason = "sl"
            exit_price = sl_price
            exit_pnl_pct = sl_pct if direction == "LONG" else -sl_pct

        # Handle trailing stop
        elif trailing_config and mfe_pct > trailing_config.get('activation', 1.0):
            trailing_distance = trailing_config.get('distance', 0.5)
            trailing_exit_pct = mfe_pct - trailing_distance

            # Check if price retraced to trailing stop
            if events:
                for event in events:
                    if event['mfe_pct'] >= trailing_config['activation']:
                        current_pct = ((event['price_close'] - entry_price) / entry_price) * 100
                        if direction == "SHORT":
                            current_pct = -current_pct

                        if current_pct <= trailing_exit_pct:
                            exit_reason = "trailing_sl"
                            exit_pnl_pct = trailing_exit_pct
                            break

        # Handle breakeven stop
        elif breakeven_pct and mfe_pct >= breakeven_pct:
            # Check if price returned to breakeven
            if events:
                for event in reversed(events):
                    if event['mfe_pct'] >= breakeven_pct:
                        current_pct = ((event['price_close'] - entry_price) / entry_price) * 100
                        if direction == "SHORT":
                            current_pct = -current_pct

                        if current_pct <= 0:
                            exit_reason = "breakeven"
                            exit_pnl_pct = 0
                            break

        # Default to time exit if no other exit triggered
        if not exit_reason:
            exit_reason = "time_exit"
            # Use last close price
            if events:
                last_close = events[-1]['price_close']
                exit_pnl_pct = ((last_close - entry_price) / entry_price) * 100
                if direction == "SHORT":
                    exit_pnl_pct = -exit_pnl_pct
            else:
                exit_pnl_pct = 0

        # Calculate duration
        duration_minutes = len(events) if events else 60

        return SimulationResult(
            strategy_name=strategy_config.get('strategy_name', 'unnamed'),
            exit_reason=exit_reason,
            exit_price=exit_price or entry_price,
            pnl_pct=exit_pnl_pct or 0,
            pnl_usd=None,  # Will be calculated based on position size
            duration_minutes=duration_minutes,
            mae_pct=mae_pct,
            mfe_pct=mfe_pct,
            risk_reward_ratio=abs(tp_pct / sl_pct) if sl_pct else 0,
            is_winner=exit_pnl_pct > 0 if exit_pnl_pct else False
        )

    async def batch_simulate_strategies(
        self,
        trade: TradeSetup,
        strategy_configs: List[Dict[str, Any]],
        use_realtime_prices: bool = True
    ) -> List[SimulationResult]:
        """
        Simulate multiple strategies in parallel for efficiency

        Args:
            trade: Trade setup to simulate
            strategy_configs: List of strategy configurations
            use_realtime_prices: Whether to fetch real-time prices

        Returns:
            List of simulation results
        """
        # Fetch price data once for all strategies
        if use_realtime_prices:
            mae_pct, mfe_pct, events = await self.simulate_mae_mfe_realtime(
                entry_price=float(trade.entry_price),
                direction=trade.direction,
                symbol=trade.symbol,
                duration_minutes=60
            )

            # Store in trade object for reuse
            trade._demo_mae_pct = mae_pct
            trade._demo_mfe_pct = mfe_pct
            trade._demo_events = events

        # Simulate all strategies
        tasks = []
        for config in strategy_configs:
            task = self.simulate_strategy_on_demo(
                trade=trade,
                strategy_config=config,
                use_realtime_prices=False  # Use cached data
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Strategy simulation failed: {str(result)}")
            else:
                valid_results.append(result)

        return valid_results

    @staticmethod
    def calculate_strategy_score(
        win_rate: float,
        risk_reward: float,
        avg_duration_hours: float
    ) -> float:
        """
        Calculate composite strategy score optimized for high win rate

        Args:
            win_rate: Win rate percentage
            risk_reward: Risk/reward ratio
            avg_duration_hours: Average trade duration

        Returns:
            Composite score (0-100)
        """
        # Base score from win rate (70% weight in high-WR mode)
        wr_score = (win_rate / 100) ** PhaseConfig.SCORE_WIN_RATE_EXPONENT

        # Risk/reward score (30% weight)
        rr_score = min(1.0, (risk_reward / 2.0) ** PhaseConfig.SCORE_RR_EXPONENT)

        # Duration penalty
        duration_penalty = 1.0
        if avg_duration_hours > PhaseConfig.DURATION_PENALTY_THRESHOLD_HOURS:
            excess_hours = avg_duration_hours - PhaseConfig.DURATION_PENALTY_THRESHOLD_HOURS
            penalty_factor = excess_hours / PhaseConfig.DURATION_PENALTY_SCALE_HOURS
            duration_penalty = max(0.5, 1.0 - penalty_factor)

        # Weighted composite score
        base_score = (
            PhaseConfig.SCORE_WEIGHT_WIN_RATE * wr_score +
            PhaseConfig.SCORE_WEIGHT_RISK_REWARD * rr_score
        ) * duration_penalty

        # Apply high win rate bonus if applicable
        if PhaseConfig.OPTIMIZE_FOR_WIN_RATE:
            if win_rate >= PhaseConfig.SCORE_HIGH_WR_THRESHOLD:
                base_score *= PhaseConfig.SCORE_HIGH_WR_BONUS
            elif win_rate >= PhaseConfig.SCORE_MEDIUM_WR_THRESHOLD:
                base_score *= PhaseConfig.SCORE_MEDIUM_WR_BONUS

        return min(100, base_score * 100)

    async def save_simulation_results(
        self,
        trade: TradeSetup,
        results: List[SimulationResult]
    ) -> None:
        """
        Save simulation results to database

        Args:
            trade: Trade that was simulated
            results: List of simulation results
        """
        for result in results:
            simulation = StrategySimulation(
                trade_setup_id=trade.id,
                strategy_name=result.strategy_name,
                simulated_tp1_pct=result.tp_pct,
                simulated_sl_pct=result.sl_pct,
                trailing_enabled=result.trailing_enabled,
                trailing_activation_pct=result.trailing_activation,
                trailing_distance_pct=result.trailing_distance,
                breakeven_trigger_pct=result.breakeven_pct,
                simulated_exit_price=result.exit_price,
                simulated_exit_reason=result.exit_reason,
                simulated_pnl_pct=result.pnl_pct,
                simulated_pnl_usd=result.pnl_usd,
                simulated_duration_minutes=result.duration_minutes
            )

            self.db.add(simulation)

        await self.db.commit()
        logger.info(f"Saved {len(results)} simulation results for trade {trade.id}")