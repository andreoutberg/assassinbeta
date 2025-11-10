"""
Enhanced Circuit Breaker System for High-WR Strategies

Provides adaptive circuit breakers that adjust thresholds based on strategy
characteristics (win rate and risk-reward ratio). Especially designed for
high win-rate strategies with RR>1 that are vulnerable to losing streaks.
"""
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.database.models import TradeSetup
import logging

logger = logging.getLogger(__name__)


class StrategyProfile:
    """Define strategy profiles based on win rate and risk-reward characteristics"""

    HIGH_WR = "HIGH_WR"  # Win Rate > 65%, RR > 1
    MODERATE_WR = "MODERATE_WR"  # Win Rate 50-65%, RR 1-2
    LOW_WR = "LOW_WR"  # Win Rate < 50%, RR > 2
    STANDARD = "STANDARD"  # Default profile

    @classmethod
    def determine_profile(cls, win_rate: float, risk_reward: float) -> str:
        """Determine strategy profile based on metrics"""
        if win_rate >= 65 and risk_reward >= 1.0:
            return cls.HIGH_WR
        elif 50 <= win_rate < 65 and 1.0 <= risk_reward <= 2.0:
            return cls.MODERATE_WR
        elif win_rate < 50 and risk_reward > 2.0:
            return cls.LOW_WR
        else:
            return cls.STANDARD


class CircuitBreakerConfig:
    """Configuration for circuit breaker thresholds"""

    # Standard mode thresholds
    STANDARD_CONFIG = {
        "consecutive_loss_limit": 5,
        "losses_in_10_trades": 7,
        "max_drawdown_pct": -5.0,
        "min_win_rate_20": 40.0,
        "pause_duration_days": 7,
        "max_pause_count": 3,
        "recovery_wins_required": 2,
        "recovery_win_rate_10": 50.0,
        "recovery_pnl_threshold": 1.0,
        "position_size_multiplier": 1.0,
        "rapid_loss_hourly": -3.0,
        "rapid_loss_daily": -5.0
    }

    # High-WR mode thresholds (tighter controls)
    HIGH_WR_CONFIG = {
        "consecutive_loss_limit": 3,  # Pause after 3 consecutive losses
        "losses_in_10_trades": 5,  # Blacklist after 5 losses in 10 trades
        "max_drawdown_pct": -3.0,  # Tighter drawdown limit
        "min_win_rate_20": 55.0,  # Pause if WR drops below 55% over 20 trades
        "pause_duration_days": 3,  # Shorter pause duration
        "max_pause_count": 2,  # Less tolerance for repeated failures
        "recovery_wins_required": 3,  # Need 3 consecutive wins to resume
        "recovery_win_rate_10": 60.0,  # OR 60% WR over next 10 trades
        "recovery_pnl_threshold": 2.0,  # Need +2% to exit recovery
        "position_size_multiplier": 0.75,  # Reduce base position size
        "rapid_loss_hourly": -1.5,  # Pause if -1.5% in an hour
        "rapid_loss_daily": -3.0  # Pause if -3% in a day
    }

    # Moderate-WR mode thresholds
    MODERATE_WR_CONFIG = {
        "consecutive_loss_limit": 4,
        "losses_in_10_trades": 6,
        "max_drawdown_pct": -4.0,
        "min_win_rate_20": 45.0,
        "pause_duration_days": 5,
        "max_pause_count": 3,
        "recovery_wins_required": 2,
        "recovery_win_rate_10": 55.0,
        "recovery_pnl_threshold": 1.5,
        "position_size_multiplier": 0.9,
        "rapid_loss_hourly": -2.0,
        "rapid_loss_daily": -4.0
    }

    @classmethod
    def get_config(cls, profile: str) -> Dict[str, Any]:
        """Get configuration based on strategy profile"""
        configs = {
            StrategyProfile.HIGH_WR: cls.HIGH_WR_CONFIG,
            StrategyProfile.MODERATE_WR: cls.MODERATE_WR_CONFIG,
            StrategyProfile.STANDARD: cls.STANDARD_CONFIG,
            StrategyProfile.LOW_WR: cls.STANDARD_CONFIG  # Use standard for low WR
        }
        return configs.get(profile, cls.STANDARD_CONFIG)


class EnhancedCircuitBreaker:
    """Enhanced circuit breaker with adaptive thresholds for different strategy profiles"""

    def __init__(self):
        self.alerts = []
        self.strategy_profiles = {}  # Cache strategy profiles
        self.recovery_tracking = {}  # Track recovery progress

    @staticmethod
    def calculate_breakeven_wr(risk_reward: float) -> float:
        """
        Calculate minimum win rate needed to break even
        Formula: Breakeven WR = 1 / (1 + RR)
        """
        if risk_reward <= 0:
            return 100.0  # Impossible to break even with negative RR
        return 100.0 / (1 + risk_reward)

    @staticmethod
    def calculate_kelly_fraction(win_rate: float, risk_reward: float) -> float:
        """
        Calculate Kelly Criterion for position sizing
        Conservative implementation using 25% Kelly
        """
        p = win_rate / 100.0
        q = 1 - p
        b = risk_reward

        if b <= 0:
            return 0.0

        kelly = (p * b - q) / b

        # Conservative Kelly (25% of full Kelly, max 25% position)
        return max(0, min(kelly * 0.25, 0.25))

    async def check_circuit_breakers(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        phase: str
    ) -> Tuple[str, Optional[str], Dict[str, Any]]:
        """
        Check if circuit breakers should trigger

        Returns: (status, reason, metrics)
        Status: 'active', 'paused', 'recovery', 'blacklisted'
        """
        # Only enforce in Phase III (live trading)
        if phase != 'III':
            return 'active', None, {}

        # Get recent trades and calculate metrics
        metrics = await self._calculate_metrics(db, symbol, direction, webhook_source)

        if metrics['total_trades'] < 10:
            return 'active', None, metrics

        # Determine strategy profile
        profile = StrategyProfile.determine_profile(
            metrics.get('win_rate', 50),
            metrics.get('risk_reward', 1.0)
        )

        # Store profile for later use
        strategy_key = f"{symbol}_{direction}_{webhook_source}"
        self.strategy_profiles[strategy_key] = profile

        # Get configuration based on profile
        config = CircuitBreakerConfig.get_config(profile)

        # Check various circuit breaker conditions
        status, reason = await self._evaluate_conditions(metrics, config, profile)

        # Check recovery status if applicable
        if status == 'active' and strategy_key in self.recovery_tracking:
            recovery_status = await self._check_recovery_progress(
                db, symbol, direction, webhook_source, config
            )
            if recovery_status:
                status = 'recovery'
                reason = recovery_status

        # Generate alerts if necessary
        if status in ['paused', 'blacklisted']:
            await self._generate_alert(
                symbol, direction, webhook_source, status, reason, metrics
            )

        return status, reason, metrics

    async def _calculate_metrics(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str
    ) -> Dict[str, Any]:
        """Calculate comprehensive metrics for circuit breaker evaluation"""

        # Get last 20 trades
        result = await db.execute(
            select(TradeSetup).where(
                TradeSetup.symbol == symbol,
                TradeSetup.direction == direction,
                TradeSetup.webhook_source == webhook_source,
                TradeSetup.status == 'completed'
            ).order_by(TradeSetup.created_at.desc()).limit(20)
        )
        recent_trades = result.scalars().all()

        if not recent_trades:
            return {'total_trades': 0}

        metrics = {
            'total_trades': len(recent_trades),
            'symbol': symbol,
            'direction': direction,
            'webhook_source': webhook_source
        }

        # Calculate win rate
        wins = sum(1 for t in recent_trades if (t.final_pnl_pct or 0) > 0)
        metrics['win_rate'] = (wins / len(recent_trades)) * 100 if recent_trades else 0

        # Calculate cumulative P&L for different windows
        metrics['cumulative_pnl_5'] = sum(
            float(t.final_pnl_pct or 0) for t in recent_trades[:5]
        ) if len(recent_trades) >= 5 else 0

        metrics['cumulative_pnl_10'] = sum(
            float(t.final_pnl_pct or 0) for t in recent_trades[:10]
        ) if len(recent_trades) >= 10 else 0

        metrics['cumulative_pnl_20'] = sum(
            float(t.final_pnl_pct or 0) for t in recent_trades
        )

        # Count losses in last 10 trades
        if len(recent_trades) >= 10:
            metrics['losses_in_10'] = sum(
                1 for t in recent_trades[:10] if (t.final_pnl_pct or 0) <= 0
            )

        # Calculate consecutive losses
        consecutive_losses = 0
        for trade in recent_trades:
            if (trade.final_pnl_pct or 0) <= 0:
                consecutive_losses += 1
            else:
                break
        metrics['consecutive_losses'] = consecutive_losses

        # Calculate consecutive wins (for recovery tracking)
        consecutive_wins = 0
        for trade in recent_trades:
            if (trade.final_pnl_pct or 0) > 0:
                consecutive_wins += 1
            else:
                break
        metrics['consecutive_wins'] = consecutive_wins

        # Calculate risk-reward ratio (average of winning trades / average of losing trades)
        winning_trades = [float(t.final_pnl_pct) for t in recent_trades if (t.final_pnl_pct or 0) > 0]
        losing_trades = [abs(float(t.final_pnl_pct)) for t in recent_trades if (t.final_pnl_pct or 0) < 0]

        if winning_trades and losing_trades:
            avg_win = sum(winning_trades) / len(winning_trades)
            avg_loss = sum(losing_trades) / len(losing_trades)
            metrics['risk_reward'] = avg_win / avg_loss if avg_loss > 0 else 1.0
        else:
            metrics['risk_reward'] = 1.0

        # Calculate hourly and daily P&L if timestamps available
        now = datetime.now()
        hourly_trades = [
            t for t in recent_trades
            if t.created_at and (now - t.created_at) < timedelta(hours=1)
        ]
        daily_trades = [
            t for t in recent_trades
            if t.created_at and (now - t.created_at) < timedelta(days=1)
        ]

        metrics['hourly_pnl'] = sum(
            float(t.final_pnl_pct or 0) for t in hourly_trades
        ) if hourly_trades else 0

        metrics['daily_pnl'] = sum(
            float(t.final_pnl_pct or 0) for t in daily_trades
        ) if daily_trades else 0

        # Calculate max drawdown
        cumulative = 0
        peak = 0
        max_drawdown = 0
        for trade in reversed(recent_trades):  # Process in chronological order
            cumulative += float(trade.final_pnl_pct or 0)
            peak = max(peak, cumulative)
            drawdown = cumulative - peak
            max_drawdown = min(max_drawdown, drawdown)
        metrics['max_drawdown'] = max_drawdown

        # Add expected metrics
        metrics['expected_win_rate'] = 70.0 if metrics['risk_reward'] > 1 else 50.0
        metrics['breakeven_wr'] = self.calculate_breakeven_wr(metrics['risk_reward'])
        metrics['kelly_fraction'] = self.calculate_kelly_fraction(
            metrics['win_rate'], metrics['risk_reward']
        )

        return metrics

    async def _evaluate_conditions(
        self,
        metrics: Dict[str, Any],
        config: Dict[str, Any],
        profile: str
    ) -> Tuple[str, Optional[str]]:
        """Evaluate circuit breaker conditions based on metrics and config"""

        # Check consecutive losses
        if metrics.get('consecutive_losses', 0) >= config['consecutive_loss_limit']:
            return 'paused', (
                f"Consecutive losses: {metrics['consecutive_losses']} "
                f"(limit: {config['consecutive_loss_limit']} for {profile})"
            )

        # Check losses in 10 trades (blacklist condition for high-WR)
        if profile == StrategyProfile.HIGH_WR and 'losses_in_10' in metrics:
            if metrics['losses_in_10'] >= config['losses_in_10_trades']:
                return 'blacklisted', (
                    f"HIGH-WR FAILURE: {metrics['losses_in_10']} losses in 10 trades "
                    f"(limit: {config['losses_in_10_trades']})"
                )

        # Check max drawdown
        if metrics.get('max_drawdown', 0) < config['max_drawdown_pct']:
            return 'paused', (
                f"Max drawdown: {metrics['max_drawdown']:.2f}% "
                f"(limit: {config['max_drawdown_pct']}%)"
            )

        # Check cumulative P&L thresholds
        if metrics.get('total_trades', 0) >= 10:
            if metrics.get('cumulative_pnl_10', 0) < config['max_drawdown_pct']:
                return 'paused', (
                    f"10-trade P&L: {metrics['cumulative_pnl_10']:.2f}% "
                    f"(limit: {config['max_drawdown_pct']}%)"
                )

        # Check win rate (especially important for high-WR strategies)
        if metrics.get('total_trades', 0) >= 20:
            if metrics.get('win_rate', 0) < config['min_win_rate_20']:
                if profile == StrategyProfile.HIGH_WR:
                    # Trigger strategy regeneration for high-WR
                    return 'paused', (
                        f"WIN RATE DEGRADATION: {metrics['win_rate']:.1f}% "
                        f"(minimum: {config['min_win_rate_20']}%) - Strategy regeneration needed"
                    )
                else:
                    return 'paused', (
                        f"Low win rate: {metrics['win_rate']:.1f}% over 20 trades "
                        f"(minimum: {config['min_win_rate_20']}%)"
                    )

        # Check rapid losses
        if metrics.get('hourly_pnl', 0) < config['rapid_loss_hourly']:
            return 'paused', (
                f"Rapid hourly loss: {metrics['hourly_pnl']:.2f}% "
                f"(limit: {config['rapid_loss_hourly']}%)"
            )

        if metrics.get('daily_pnl', 0) < config['rapid_loss_daily']:
            return 'paused', (
                f"Daily loss: {metrics['daily_pnl']:.2f}% "
                f"(limit: {config['rapid_loss_daily']}%)"
            )

        return 'active', None

    async def _check_recovery_progress(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        config: Dict[str, Any]
    ) -> Optional[str]:
        """Check if strategy meets recovery requirements"""

        strategy_key = f"{symbol}_{direction}_{webhook_source}"
        recovery_data = self.recovery_tracking.get(strategy_key, {})

        if not recovery_data:
            return None

        # Get trades since recovery started
        recovery_start = recovery_data.get('started_at')
        if not recovery_start:
            return None

        result = await db.execute(
            select(TradeSetup).where(
                TradeSetup.symbol == symbol,
                TradeSetup.direction == direction,
                TradeSetup.webhook_source == webhook_source,
                TradeSetup.status == 'completed',
                TradeSetup.created_at >= recovery_start
            ).order_by(TradeSetup.created_at.desc()).limit(10)
        )
        recovery_trades = result.scalars().all()

        if not recovery_trades:
            return "In recovery: No trades completed yet"

        # Check consecutive wins requirement
        consecutive_wins = 0
        for trade in recovery_trades:
            if (trade.final_pnl_pct or 0) > 0:
                consecutive_wins += 1
            else:
                break

        if consecutive_wins >= config['recovery_wins_required']:
            # Recovery successful - remove from tracking
            del self.recovery_tracking[strategy_key]
            logger.info(
                f"Recovery complete for {symbol} {direction}: "
                f"{consecutive_wins} consecutive wins"
            )
            return None

        # Check win rate over 10 trades
        if len(recovery_trades) >= 10:
            wins = sum(1 for t in recovery_trades if (t.final_pnl_pct or 0) > 0)
            recovery_wr = (wins / 10) * 100

            if recovery_wr >= config['recovery_win_rate_10']:
                # Recovery successful
                del self.recovery_tracking[strategy_key]
                logger.info(
                    f"Recovery complete for {symbol} {direction}: "
                    f"{recovery_wr:.1f}% win rate over 10 trades"
                )
                return None

        # Check P&L threshold
        recovery_pnl = sum(float(t.final_pnl_pct or 0) for t in recovery_trades)

        if recovery_pnl >= config['recovery_pnl_threshold']:
            # Recovery successful
            del self.recovery_tracking[strategy_key]
            logger.info(
                f"Recovery complete for {symbol} {direction}: "
                f"+{recovery_pnl:.2f}% P&L"
            )
            return None

        # Still in recovery
        return (
            f"In recovery: {consecutive_wins}/{config['recovery_wins_required']} wins, "
            f"P&L: {recovery_pnl:.2f}%/{config['recovery_pnl_threshold']}%"
        )

    def calculate_position_size_multiplier(
        self,
        symbol: str,
        direction: str,
        webhook_source: str,
        metrics: Dict[str, Any],
        circuit_breaker_status: str
    ) -> float:
        """
        Calculate position size multiplier based on current conditions
        Returns a value between 0.0 and 1.0 to multiply against base position size
        """
        strategy_key = f"{symbol}_{direction}_{webhook_source}"
        profile = self.strategy_profiles.get(strategy_key, StrategyProfile.STANDARD)
        config = CircuitBreakerConfig.get_config(profile)

        # Start with base multiplier for profile
        multiplier = config['position_size_multiplier']

        # Apply circuit breaker status adjustments
        if circuit_breaker_status == 'recovery':
            multiplier *= 0.25  # 25% size in recovery mode
        elif circuit_breaker_status == 'paused':
            return 0.0  # No trading when paused
        elif circuit_breaker_status == 'blacklisted':
            return 0.0  # No trading when blacklisted

        # Performance-based adjustments
        consecutive_losses = metrics.get('consecutive_losses', 0)

        if consecutive_losses >= 2:
            multiplier *= 0.5  # Half size after 2 losses
        elif consecutive_losses >= 1:
            multiplier *= 0.75  # 75% size after 1 loss

        # Drawdown adjustment
        if metrics.get('cumulative_pnl_10', 0) < -2.0:
            multiplier *= 0.7  # Reduce during drawdown

        # Win rate adjustment for high-WR strategies
        if profile == StrategyProfile.HIGH_WR:
            actual_wr = metrics.get('win_rate', 0)
            expected_wr = metrics.get('expected_win_rate', 70)

            if actual_wr < expected_wr - 10:
                multiplier *= 0.5  # Half size if significantly underperforming
            elif actual_wr < expected_wr - 5:
                multiplier *= 0.75

        # Apply Kelly Criterion boost (conservative)
        kelly_multiplier = metrics.get('kelly_fraction', 0)
        if kelly_multiplier > 0:
            multiplier *= (1 + kelly_multiplier * 0.5)  # Use 50% of Kelly suggestion

        # Ensure bounds
        return max(0.0, min(multiplier, 1.0))

    async def _generate_alert(
        self,
        symbol: str,
        direction: str,
        webhook_source: str,
        status: str,
        reason: str,
        metrics: Dict[str, Any]
    ):
        """Generate and store alert for monitoring system"""

        severity = 'CRITICAL' if status == 'blacklisted' else 'HIGH'

        alert = {
            'id': f"{symbol}_{direction}_{webhook_source}_{datetime.now().timestamp()}",
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'direction': direction,
            'webhook_source': webhook_source,
            'status': status,
            'severity': severity,
            'reason': reason,
            'metrics': {
                'win_rate': metrics.get('win_rate', 0),
                'consecutive_losses': metrics.get('consecutive_losses', 0),
                'max_drawdown': metrics.get('max_drawdown', 0),
                'cumulative_pnl_20': metrics.get('cumulative_pnl_20', 0)
            },
            'action': 'PAUSE_TRADING' if status == 'paused' else 'BLACKLIST_ASSET',
            'resolved': False
        }

        self.alerts.append(alert)

        # Log based on severity
        if severity == 'CRITICAL':
            logger.critical(f"[{symbol} {direction}] {reason}")
        else:
            logger.error(f"[{symbol} {direction}] {reason}")

    async def initiate_recovery(
        self,
        symbol: str,
        direction: str,
        webhook_source: str
    ):
        """Initiate recovery mode for a paused strategy"""
        strategy_key = f"{symbol}_{direction}_{webhook_source}"

        self.recovery_tracking[strategy_key] = {
            'started_at': datetime.now(),
            'initial_status': 'paused',
            'trades_completed': 0,
            'recovery_pnl': 0.0
        }

        logger.info(
            f"Initiated recovery mode for {symbol} {direction} ({webhook_source})"
        )

    async def update_asset_health(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        phase: str
    ):
        """
        Main entry point to update asset health after trade completion
        Enhanced version with adaptive thresholds
        """
        # Check circuit breakers
        status, reason, metrics = await self.check_circuit_breakers(
            db, symbol, direction, webhook_source, phase
        )

        # Log the evaluation
        logger.info(
            f"Circuit Breaker Check: {symbol} {direction} ({webhook_source}) | "
            f"Phase {phase} | Status: {status} | "
            f"WR: {metrics.get('win_rate', 0):.1f}% | "
            f"Consecutive Losses: {metrics.get('consecutive_losses', 0)} | "
            f"P&L(20): {metrics.get('cumulative_pnl_20', 0):.2f}%"
        )

        if reason:
            logger.warning(f"Reason: {reason}")

        # Update database based on status
        if status == 'paused':
            await self._pause_asset(db, symbol, direction, webhook_source, reason)
        elif status == 'blacklisted':
            await self._blacklist_asset(db, symbol, direction, webhook_source, reason)
        elif status == 'recovery':
            await self._update_recovery_status(db, symbol, direction, webhook_source, reason)
        else:
            # Update metrics even if active
            await self._update_asset_metrics(
                db, symbol, direction, webhook_source, metrics
            )

    async def _pause_asset(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        reason: str
    ):
        """Pause an asset with enhanced tracking"""

        # Get profile-specific config
        strategy_key = f"{symbol}_{direction}_{webhook_source}"
        profile = self.strategy_profiles.get(strategy_key, StrategyProfile.STANDARD)
        config = CircuitBreakerConfig.get_config(profile)

        # Get current pause count
        result = await db.execute(
            text("""
                SELECT pause_count FROM asset_status
                WHERE symbol = :symbol
                    AND direction = :direction
                    AND webhook_source = :webhook_source
            """),
            {"symbol": symbol, "direction": direction, "webhook_source": webhook_source}
        )
        row = result.fetchone()
        current_pause_count = row[0] if row else 0
        new_pause_count = current_pause_count + 1

        # Check if should blacklist instead
        if new_pause_count >= config['max_pause_count']:
            await self._blacklist_asset(
                db, symbol, direction, webhook_source,
                f"Exceeded max pause count ({config['max_pause_count']}): {reason}"
            )
            return

        logger.warning(
            f"⚠️ PAUSING ASSET: {symbol} {direction} ({webhook_source}) | "
            f"Profile: {profile} | Pause #{new_pause_count}/{config['max_pause_count']} | "
            f"Reason: {reason}"
        )

        await db.execute(
            text("""
                INSERT INTO asset_status (
                    symbol, direction, webhook_source, status, pause_reason,
                    paused_at, pause_count, strategy_profile, updated_at
                )
                VALUES (:symbol, :direction, :webhook_source, 'paused', :reason,
                        NOW(), :pause_count, :profile, NOW())
                ON CONFLICT (symbol, direction, webhook_source)
                DO UPDATE SET
                    status = 'paused',
                    pause_reason = :reason,
                    paused_at = NOW(),
                    pause_count = :pause_count,
                    strategy_profile = :profile,
                    updated_at = NOW()
            """),
            {
                "symbol": symbol,
                "direction": direction,
                "webhook_source": webhook_source,
                "reason": reason,
                "pause_count": new_pause_count,
                "profile": profile
            }
        )
        await db.commit()

        # Initiate recovery tracking
        await self.initiate_recovery(symbol, direction, webhook_source)

    async def _blacklist_asset(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        reason: str
    ):
        """Blacklist an asset (requires manual review)"""

        strategy_key = f"{symbol}_{direction}_{webhook_source}"
        profile = self.strategy_profiles.get(strategy_key, StrategyProfile.STANDARD)

        logger.error(
            f"🛑 BLACKLISTING ASSET: {symbol} {direction} ({webhook_source}) | "
            f"Profile: {profile} | Reason: {reason}"
        )

        await db.execute(
            text("""
                INSERT INTO asset_status (
                    symbol, direction, webhook_source, status, pause_reason,
                    paused_at, strategy_profile, updated_at
                )
                VALUES (:symbol, :direction, :webhook_source, 'blacklisted', :reason,
                        NOW(), :profile, NOW())
                ON CONFLICT (symbol, direction, webhook_source)
                DO UPDATE SET
                    status = 'blacklisted',
                    pause_reason = :reason,
                    paused_at = NOW(),
                    strategy_profile = :profile,
                    updated_at = NOW()
            """),
            {
                "symbol": symbol,
                "direction": direction,
                "webhook_source": webhook_source,
                "reason": reason,
                "profile": profile
            }
        )
        await db.commit()

    async def _update_recovery_status(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        reason: str
    ):
        """Update recovery status in database"""

        strategy_key = f"{symbol}_{direction}_{webhook_source}"
        profile = self.strategy_profiles.get(strategy_key, StrategyProfile.STANDARD)

        await db.execute(
            text("""
                UPDATE asset_status
                SET status = 'recovery',
                    pause_reason = :reason,
                    strategy_profile = :profile,
                    updated_at = NOW()
                WHERE symbol = :symbol
                    AND direction = :direction
                    AND webhook_source = :webhook_source
            """),
            {
                "symbol": symbol,
                "direction": direction,
                "webhook_source": webhook_source,
                "reason": reason,
                "profile": profile
            }
        )
        await db.commit()

    async def _update_asset_metrics(
        self,
        db: AsyncSession,
        symbol: str,
        direction: str,
        webhook_source: str,
        metrics: Dict[str, Any]
    ):
        """Update asset metrics in database"""

        strategy_key = f"{symbol}_{direction}_{webhook_source}"
        profile = self.strategy_profiles.get(strategy_key, StrategyProfile.STANDARD)

        await db.execute(
            text("""
                INSERT INTO asset_status (
                    symbol, direction, webhook_source, status,
                    cumulative_pnl_last_20, win_rate_last_20, total_trades,
                    consecutive_losses, expected_win_rate, expected_risk_reward,
                    strategy_profile, last_checked_at, updated_at
                )
                VALUES (:symbol, :direction, :webhook_source, 'active',
                        :pnl, :wr, :trades, :consecutive_losses, :expected_wr, :expected_rr,
                        :profile, NOW(), NOW())
                ON CONFLICT (symbol, direction, webhook_source)
                DO UPDATE SET
                    cumulative_pnl_last_20 = :pnl,
                    win_rate_last_20 = :wr,
                    total_trades = :trades,
                    consecutive_losses = :consecutive_losses,
                    expected_win_rate = :expected_wr,
                    expected_risk_reward = :expected_rr,
                    strategy_profile = :profile,
                    last_checked_at = NOW(),
                    updated_at = NOW()
            """),
            {
                "symbol": symbol,
                "direction": direction,
                "webhook_source": webhook_source,
                "pnl": metrics.get('cumulative_pnl_20', 0),
                "wr": metrics.get('win_rate', 0),
                "trades": metrics.get('total_trades', 0),
                "consecutive_losses": metrics.get('consecutive_losses', 0),
                "expected_wr": metrics.get('expected_win_rate', 50),
                "expected_rr": metrics.get('risk_reward', 1.0),
                "profile": profile
            }
        )
        await db.commit()

    def calculate_health_score(self, metrics: Dict[str, Any]) -> float:
        """
        Calculate overall health score (0-100) for a strategy
        """
        score = 100.0

        # Win rate component (40% weight)
        actual_wr = metrics.get('win_rate', 0)
        expected_wr = metrics.get('expected_win_rate', 50)

        if expected_wr > 0:
            wr_deviation = ((actual_wr - expected_wr) / expected_wr) * 100

            if wr_deviation < -20:
                score -= 40
            elif wr_deviation < -10:
                score -= 30
            elif wr_deviation < -5:
                score -= 20
            elif wr_deviation < 0:
                score -= 10

        # P&L component (40% weight)
        cumulative_pnl = metrics.get('cumulative_pnl_20', 0)

        if cumulative_pnl < -15:
            score -= 40
        elif cumulative_pnl < -10:
            score -= 30
        elif cumulative_pnl < -5:
            score -= 20
        elif cumulative_pnl < 0:
            score -= 10

        # Consecutive losses component (20% weight)
        consecutive_losses = metrics.get('consecutive_losses', 0)

        if consecutive_losses >= 5:
            score -= 20
        elif consecutive_losses >= 4:
            score -= 15
        elif consecutive_losses >= 3:
            score -= 10
        elif consecutive_losses >= 2:
            score -= 5

        return max(0, min(score, 100))

    async def get_circuit_breaker_summary(self, db: AsyncSession) -> Dict[str, Any]:
        """Get comprehensive summary of circuit breaker status"""

        result = await db.execute(
            text("""
                SELECT
                    symbol,
                    direction,
                    webhook_source,
                    status,
                    strategy_profile,
                    ROUND(cumulative_pnl_last_20::numeric, 2) as pnl,
                    ROUND(win_rate_last_20::numeric, 1) as win_rate,
                    consecutive_losses,
                    total_trades,
                    pause_count,
                    pause_reason,
                    paused_at
                FROM asset_status
                ORDER BY
                    CASE status
                        WHEN 'blacklisted' THEN 1
                        WHEN 'recovery' THEN 2
                        WHEN 'paused' THEN 3
                        WHEN 'active' THEN 4
                    END,
                    cumulative_pnl_last_20 ASC
            """)
        )

        assets = []
        for row in result.fetchall():
            asset = dict(row)

            # Calculate health score if we have metrics
            if asset.get('win_rate') and asset.get('pnl'):
                metrics = {
                    'win_rate': asset['win_rate'],
                    'cumulative_pnl_20': asset['pnl'],
                    'consecutive_losses': asset.get('consecutive_losses', 0),
                    'expected_win_rate': 70 if asset.get('strategy_profile') == 'HIGH_WR' else 50
                }
                asset['health_score'] = self.calculate_health_score(metrics)

            assets.append(asset)

        # Get recent alerts
        recent_alerts = [
            alert for alert in self.alerts
            if not alert['resolved'] and
            (datetime.now() - datetime.fromisoformat(alert['timestamp'])) < timedelta(hours=24)
        ]

        return {
            'assets': assets,
            'alerts': recent_alerts,
            'summary': {
                'total_assets': len(assets),
                'blacklisted': sum(1 for a in assets if a['status'] == 'blacklisted'),
                'paused': sum(1 for a in assets if a['status'] == 'paused'),
                'recovery': sum(1 for a in assets if a['status'] == 'recovery'),
                'active': sum(1 for a in assets if a['status'] == 'active'),
                'critical_alerts': sum(1 for a in recent_alerts if a['severity'] == 'CRITICAL'),
                'high_alerts': sum(1 for a in recent_alerts if a['severity'] == 'HIGH')
            }
        }


# Singleton instance
_circuit_breaker = None


def get_circuit_breaker() -> EnhancedCircuitBreaker:
    """Get or create singleton circuit breaker instance"""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = EnhancedCircuitBreaker()
    return _circuit_breaker


# Export main functions for backward compatibility
async def check_asset_status(
    db: AsyncSession,
    symbol: str,
    direction: str,
    webhook_source: str,
    phase: str = 'III'
) -> str:
    """Check if asset is allowed to trade"""
    cb = get_circuit_breaker()
    status, _, _ = await cb.check_circuit_breakers(
        db, symbol, direction, webhook_source, phase
    )
    return status


async def update_asset_health(
    db: AsyncSession,
    symbol: str,
    direction: str,
    webhook_source: str,
    phase: str
):
    """Update asset health after trade completion"""
    cb = get_circuit_breaker()
    await cb.update_asset_health(
        db, symbol, direction, webhook_source, phase
    )


async def get_position_size_multiplier(
    db: AsyncSession,
    symbol: str,
    direction: str,
    webhook_source: str
) -> float:
    """Get position size multiplier based on current conditions"""
    cb = get_circuit_breaker()

    # Get metrics and status
    status, _, metrics = await cb.check_circuit_breakers(
        db, symbol, direction, webhook_source, 'III'
    )

    # Calculate multiplier
    return cb.calculate_position_size_multiplier(
        symbol, direction, webhook_source, metrics, status
    )