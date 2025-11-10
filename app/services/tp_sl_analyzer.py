"""
TP/SL Hit Rate Analyzer

Analyzes historical trades to determine what percentage would have hit
various TP and SL levels. Used for optimizing strategy parameters.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import TradeSetup, TradeMilestones
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class TPSLAnalyzer:
    """Analyzes TP/SL hit rates from historical trade data"""

    # Standard levels to test (in %)
    TP_LEVELS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0]
    SL_LEVELS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0, 20.0]

    @classmethod
    async def analyze_hit_rates(
        cls,
        db: AsyncSession,
        symbol: str = None,
        direction: str = None,
        webhook_source: str = None,
        min_trades: int = 5
    ) -> Dict:
        """
        Analyze TP/SL hit rates for completed trades

        Args:
            db: Database session
            symbol: Optional symbol filter
            direction: Optional direction filter
            webhook_source: Optional webhook source filter
            min_trades: Minimum trades required for analysis

        Returns:
            Dict containing hit rate analysis for TP and SL levels
        """
        # Build query for completed baseline trades with milestones
        query = select(TradeSetup).join(
            TradeMilestones,
            TradeSetup.id == TradeMilestones.trade_setup_id
        ).where(
            TradeSetup.status == 'completed',
            TradeSetup.risk_strategy == 'baseline'
        )

        # Apply filters
        if symbol:
            query = query.where(TradeSetup.symbol == symbol)
        if direction:
            query = query.where(TradeSetup.direction == direction)
        if webhook_source:
            query = query.where(TradeSetup.webhook_source == webhook_source)

        result = await db.execute(query)
        trades = result.scalars().all()

        if len(trades) < min_trades:
            return {
                'error': f'Insufficient data: {len(trades)} trades (need {min_trades}+)',
                'trades_analyzed': len(trades)
            }

        # Load milestones for each trade
        for trade in trades:
            await db.refresh(trade, ['milestones'])

        logger.info(f"Analyzing TP/SL hit rates for {len(trades)} trades")

        # Analyze TP hit rates
        tp_analysis = cls._analyze_tp_levels(trades)

        # Analyze SL hit rates
        sl_analysis = cls._analyze_sl_levels(trades)

        # Calculate optimal levels (highest hit rate with good RR)
        optimal = cls._find_optimal_levels(tp_analysis, sl_analysis)

        return {
            'trades_analyzed': len(trades),
            'symbol': symbol,
            'direction': direction,
            'webhook_source': webhook_source,
            'tp_hit_rates': tp_analysis,
            'sl_hit_rates': sl_analysis,
            'optimal_levels': optimal,
            'chart_data': cls._format_for_chart(tp_analysis, sl_analysis)
        }

    @classmethod
    def _analyze_tp_levels(cls, trades: List[TradeSetup]) -> List[Dict]:
        """Analyze what % of trades would have hit each TP level"""
        tp_results = []

        for tp_pct in cls.TP_LEVELS:
            hits = 0
            total = 0
            hit_trades = []

            for trade in trades:
                if not trade.milestones:
                    continue

                total += 1
                max_profit = float(trade.milestones.max_profit_pct or 0)

                # Check if max profit reached this TP level
                if max_profit >= tp_pct:
                    hits += 1
                    hit_trades.append({
                        'trade_id': trade.id,
                        'symbol': trade.symbol,
                        'max_profit': max_profit,
                        'final_pnl': float(trade.final_pnl_pct or 0)
                    })

            hit_rate = (hits / total * 100) if total > 0 else 0

            tp_results.append({
                'level': tp_pct,
                'hits': hits,
                'total': total,
                'hit_rate': round(hit_rate, 1),
                'sample_hits': hit_trades[:3]  # Show first 3 examples
            })

        return tp_results

    @classmethod
    def _analyze_sl_levels(cls, trades: List[TradeSetup]) -> List[Dict]:
        """Analyze what % of trades would have hit each SL level"""
        sl_results = []

        for sl_pct in cls.SL_LEVELS:
            hits = 0
            total = 0
            hit_trades = []

            for trade in trades:
                if not trade.milestones:
                    continue

                total += 1
                max_drawdown = float(trade.milestones.max_drawdown_pct or 0)

                # Check if max drawdown reached this SL level (negative comparison)
                if max_drawdown <= -sl_pct:
                    hits += 1
                    hit_trades.append({
                        'trade_id': trade.id,
                        'symbol': trade.symbol,
                        'max_drawdown': max_drawdown,
                        'final_pnl': float(trade.final_pnl_pct or 0)
                    })

            hit_rate = (hits / total * 100) if total > 0 else 0

            sl_results.append({
                'level': sl_pct,
                'hits': hits,
                'total': total,
                'hit_rate': round(hit_rate, 1),
                'sample_hits': hit_trades[:3]  # Show first 3 examples
            })

        return sl_results

    @classmethod
    def _find_optimal_levels(cls, tp_analysis: List[Dict], sl_analysis: List[Dict]) -> Dict:
        """Find optimal TP/SL levels based on hit rates"""
        # Find TP with >70% hit rate
        high_prob_tp = [tp for tp in tp_analysis if tp['hit_rate'] >= 70]
        optimal_tp = high_prob_tp[-1] if high_prob_tp else tp_analysis[0]

        # Find SL with <30% hit rate (want to avoid SL)
        low_prob_sl = [sl for sl in sl_analysis if sl['hit_rate'] <= 30]
        optimal_sl = low_prob_sl[-1] if low_prob_sl else sl_analysis[0]

        # Calculate theoretical RR
        rr = optimal_tp['level'] / optimal_sl['level'] if optimal_sl['level'] > 0 else 0

        return {
            'recommended_tp': optimal_tp['level'],
            'tp_hit_rate': optimal_tp['hit_rate'],
            'recommended_sl': optimal_sl['level'],
            'sl_hit_rate': optimal_sl['hit_rate'],
            'theoretical_rr': round(rr, 2),
            'rationale': (
                f"TP {optimal_tp['level']}% hits {optimal_tp['hit_rate']}% of the time, "
                f"SL {optimal_sl['level']}% hits {optimal_sl['hit_rate']}% of the time"
            )
        }

    @classmethod
    def _format_for_chart(cls, tp_analysis: List[Dict], sl_analysis: List[Dict]) -> Dict:
        """Format data for frontend charting"""
        return {
            'tp_levels': [tp['level'] for tp in tp_analysis],
            'tp_hit_rates': [tp['hit_rate'] for tp in tp_analysis],
            'sl_levels': [sl['level'] for sl in sl_analysis],
            'sl_hit_rates': [sl['hit_rate'] for sl in sl_analysis]
        }
