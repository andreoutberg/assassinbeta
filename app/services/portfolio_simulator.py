"""
Portfolio Simulator - Shows account growth/loss over time

Simulates portfolio performance assuming:
- Starting capital: $100,000 (configurable)
- Risk per trade: 0.1% of current balance (configurable)
- Leverage already factored into PnL%
"""
from typing import List, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import TradeSetup
from app.database.strategy_models import StrategySimulation
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class PortfolioSimulator:
    """Simulate portfolio performance for each strategy"""
    
    DEFAULT_STARTING_CAPITAL = 100000.0  # $100k
    DEFAULT_RISK_PER_TRADE_PCT = 0.1     # 0.1% of balance per trade
    
    @classmethod
    async def simulate_portfolio_performance(
        cls,
        db: AsyncSession,
        symbol: str = None,
        direction: str = None,
        webhook_source: str = None,
        starting_capital: float = DEFAULT_STARTING_CAPITAL,
        risk_pct: float = DEFAULT_RISK_PER_TRADE_PCT
    ) -> Dict:
        """
        Simulate portfolio performance for all strategies
        
        Args:
            db: Database session
            symbol: Optional filter by symbol
            direction: Optional filter by direction  
            webhook_source: Optional filter by webhook
            starting_capital: Starting balance in USD
            risk_pct: % of balance to risk per trade
            
        Returns:
            Dict with portfolio metrics for each strategy
        """
        # Build query to get completed trade IDs with simulations in chronological order
        # Use subquery to avoid DISTINCT on JSON columns
        subquery = (
            select(TradeSetup.id.distinct())
            .join(StrategySimulation, TradeSetup.id == StrategySimulation.trade_setup_id)
            .where(TradeSetup.status == 'completed')
        )
        
        if symbol:
            subquery = subquery.where(TradeSetup.symbol == symbol)
        if direction:
            subquery = subquery.where(TradeSetup.direction == direction)
        if webhook_source:
            subquery = subquery.where(TradeSetup.webhook_source == webhook_source)
            
        # Get the trade IDs
        id_result = await db.execute(subquery)
        trade_ids_set = set(row[0] for row in id_result.all())
        
        if not trade_ids_set:
            return {
                "strategies": {},
                "filters": {
                    "symbol": symbol,
                    "direction": direction,
                    "webhook_source": webhook_source,
                    "starting_capital": starting_capital,
                    "risk_pct": risk_pct
                }
            }
        
        # Now get the full trades
        query = (
            select(TradeSetup)
            .where(TradeSetup.id.in_(trade_ids_set))
            .order_by(TradeSetup.completed_at)
        )
        
        result = await db.execute(query)
        trades = result.scalars().all()
        
        if not trades:
            return {
                "strategies": {},
                "filters": {
                    "symbol": symbol,
                    "direction": direction,
                    "webhook_source": webhook_source,
                    "starting_capital": starting_capital,
                    "risk_pct": risk_pct
                }
            }
        
        # Get all simulations for these trades
        trade_ids = [t.id for t in trades]
        sim_result = await db.execute(
            select(StrategySimulation)
            .where(StrategySimulation.trade_setup_id.in_(trade_ids))
            .order_by(StrategySimulation.trade_setup_id)
        )
        all_sims = sim_result.scalars().all()
        
        # Group simulations by strategy
        sims_by_strategy = {}
        for sim in all_sims:
            if sim.strategy_name not in sims_by_strategy:
                sims_by_strategy[sim.strategy_name] = []
            sims_by_strategy[sim.strategy_name].append(sim)
        
        # Simulate portfolio for each strategy
        portfolio_results = {}
        
        for strategy_name, sims in sims_by_strategy.items():
            # Sort by trade completion time
            sims_with_time = []
            for sim in sims:
                # Find the trade
                trade = next((t for t in trades if t.id == sim.trade_setup_id), None)
                if trade:
                    sims_with_time.append((trade.completed_at, sim))
            
            sims_with_time.sort(key=lambda x: x[0])
            
            # Simulate portfolio
            balance = starting_capital
            balance_curve = [{"trade": 0, "balance": balance, "balance_pct": 100.0}]
            max_balance = balance
            min_balance = balance
            
            current_streak = 0
            max_win_streak = 0
            max_loss_streak = 0
            
            wins = 0
            losses = 0
            total_pnl_usd = 0
            
            for i, (completed_at, sim) in enumerate(sims_with_time, 1):
                pnl_pct = float(sim.simulated_pnl_pct or 0)
                
                # Calculate position size based on current balance and risk%
                # Risk per trade = balance * (risk_pct / 100)
                # With leverage, the actual P&L is: risk_amount * (pnl_pct / 100)
                risk_amount = balance * (risk_pct / 100.0)
                pnl_usd = risk_amount * (pnl_pct / 100.0)
                
                # Update balance
                balance += pnl_usd
                total_pnl_usd += pnl_usd
                
                # Track min/max
                max_balance = max(max_balance, balance)
                min_balance = min(min_balance, balance)
                
                # Track streaks
                if pnl_pct > 0:
                    wins += 1
                    if current_streak >= 0:
                        current_streak += 1
                    else:
                        current_streak = 1
                    max_win_streak = max(max_win_streak, current_streak)
                else:
                    losses += 1
                    if current_streak <= 0:
                        current_streak -= 1
                    else:
                        current_streak = -1
                    max_loss_streak = max(max_loss_streak, abs(current_streak))
                
                # Record balance snapshot
                balance_pct = (balance / starting_capital) * 100.0
                balance_curve.append({
                    "trade": i,
                    "balance": round(balance, 2),
                    "balance_pct": round(balance_pct, 2),
                    "pnl_usd": round(pnl_usd, 2),
                    "pnl_pct": round(pnl_pct, 2)
                })
            
            # Calculate final metrics
            total_return_pct = ((balance - starting_capital) / starting_capital) * 100.0
            max_drawdown_pct = ((max_balance - min_balance) / max_balance) * 100.0 if max_balance > 0 else 0
            win_rate = (wins / len(sims_with_time)) * 100.0 if sims_with_time else 0
            
            portfolio_results[strategy_name] = {
                "starting_capital": starting_capital,
                "final_balance": round(balance, 2),
                "total_return_usd": round(total_pnl_usd, 2),
                "total_return_pct": round(total_return_pct, 2),
                "max_balance": round(max_balance, 2),
                "min_balance": round(min_balance, 2),
                "max_drawdown_pct": round(max_drawdown_pct, 2),
                "win_rate": round(win_rate, 2),
                "wins": wins,
                "losses": losses,
                "total_trades": len(sims_with_time),
                "max_win_streak": max_win_streak,
                "max_loss_streak": max_loss_streak,
                "balance_curve": balance_curve
            }
        
        # Find best strategy by total return %
        best_strategy = max(
            portfolio_results.items(),
            key=lambda x: x[1]['total_return_pct']
        ) if portfolio_results else None
        
        return {
            "strategies": portfolio_results,
            "best_strategy": best_strategy[0] if best_strategy else None,
            "filters": {
                "symbol": symbol,
                "direction": direction,
                "webhook_source": webhook_source,
                "starting_capital": starting_capital,
                "risk_pct": risk_pct
            },
            "summary": {
                "total_unique_trades": len(trades),
                "strategies_compared": len(portfolio_results)
            }
        }
