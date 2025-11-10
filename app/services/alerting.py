"""
Alerting System

Sends notifications via Discord, Telegram, and Email.

Alert Types:
- Kill switch triggers (drawdown limits exceeded)
- WebSocket disconnects / connection issues
- Learned level validation failures
- Trade execution events
- System health warnings

Usage:
    from app.services.alerting import AlertingService

    alerter = AlertingService()
    await alerter.send_alert(
        alert_type="kill_switch",
        severity="critical",
        message="Daily drawdown limit exceeded (-15%)",
        data={"drawdown_pct": -15.2}
    )
"""

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Dict, Optional

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Alert types"""

    KILL_SWITCH = "kill_switch"
    WEBSOCKET_DISCONNECT = "websocket_disconnect"
    VALIDATION_FAILURE = "validation_failure"
    TRADE_EXECUTION = "trade_execution"
    SYSTEM_HEALTH = "system_health"
    DATABASE_ERROR = "database_error"
    OPTIMIZATION_COMPLETE = "optimization_complete"
    STRATEGY_DEGRADATION = "strategy_degradation"
    PHASE_TRANSITION = "phase_transition"


class AlertingService:
    """
    Unified alerting service

    Sends alerts to Discord, Telegram, and Email based on severity.
    """

    def __init__(self):
        # Alert channels (loaded from settings)
        self.discord_webhook_url = getattr(settings, "DISCORD_WEBHOOK_URL", None)
        self.telegram_bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        self.telegram_chat_id = getattr(settings, "TELEGRAM_CHAT_ID", None)
        self.email_enabled = getattr(settings, "EMAIL_ALERTS_ENABLED", False)
        self.email_smtp_host = getattr(settings, "EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.email_smtp_port = getattr(settings, "EMAIL_SMTP_PORT", 587)
        self.email_username = getattr(settings, "EMAIL_USERNAME", None)
        self.email_password = getattr(settings, "EMAIL_PASSWORD", None)
        self.alert_email_to = getattr(settings, "ALERT_EMAIL_TO", None)

        # Rate limiting (prevent spam)
        self.alert_cooldowns: Dict[str, datetime] = {}
        self.COOLDOWN_SECONDS = 300  # 5 minutes

    async def send_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, bool]:
        """
        Send alert via configured channels

        Args:
            alert_type: Type of alert
            severity: Severity level
            message: Alert message
            data: Additional data (optional)

        Returns:
            {"discord": True, "telegram": True, "email": False}
        """
        # Check rate limiting
        alert_key = f"{alert_type}_{message}"
        if self._is_rate_limited(alert_key):
            logger.debug(f"Alert rate-limited: {alert_key}")
            return {"discord": False, "telegram": False, "email": False}

        logger.info(f"Sending {severity} alert: {message}")

        # Format alert
        formatted_alert = self._format_alert(alert_type, severity, message, data)

        # Send to channels based on severity
        results = {}

        # Discord (all severities)
        if self.discord_webhook_url:
            results["discord"] = await self._send_discord(formatted_alert, severity)
        else:
            results["discord"] = False
            logger.debug("Discord webhook not configured")

        # Telegram (WARNING and above)
        if severity in [AlertSeverity.WARNING, AlertSeverity.ERROR, AlertSeverity.CRITICAL]:
            if self.telegram_bot_token and self.telegram_chat_id:
                results["telegram"] = await self._send_telegram(formatted_alert, severity)
            else:
                results["telegram"] = False
                logger.debug("Telegram not configured")
        else:
            results["telegram"] = False

        # Email (ERROR and CRITICAL only)
        if severity in [AlertSeverity.ERROR, AlertSeverity.CRITICAL]:
            if self.email_enabled and self.alert_email_to:
                results["email"] = await self._send_email(formatted_alert, severity, message)
            else:
                results["email"] = False
                logger.debug("Email alerts not configured")
        else:
            results["email"] = False

        # Update cooldown
        self.alert_cooldowns[alert_key] = datetime.utcnow()

        return results

    def _is_rate_limited(self, alert_key: str) -> bool:
        """Check if alert is rate-limited"""
        if alert_key not in self.alert_cooldowns:
            return False

        last_sent = self.alert_cooldowns[alert_key]
        elapsed = (datetime.utcnow() - last_sent).total_seconds()

        return elapsed < self.COOLDOWN_SECONDS

    def _format_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        data: Optional[Dict] = None,
    ) -> Dict:
        """Format alert with metadata"""
        # Emoji based on severity
        emoji_map = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.ERROR: "❌",
            AlertSeverity.CRITICAL: "🚨",
        }

        emoji = emoji_map.get(severity, "📢")

        # Format data as readable string
        data_str = ""
        if data:
            data_str = "\n\n**Additional Data:**\n"
            for key, value in data.items():
                data_str += f"• {key}: {value}\n"

        return {
            "emoji": emoji,
            "severity": severity.value.upper(),
            "alert_type": alert_type.value.replace("_", " ").title(),
            "message": message,
            "data": data or {},
            "data_str": data_str,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _send_discord(self, alert: Dict, severity: AlertSeverity) -> bool:
        """Send alert to Discord via webhook"""
        try:
            # Color based on severity
            color_map = {
                AlertSeverity.INFO: 0x3498DB,  # Blue
                AlertSeverity.WARNING: 0xF39C12,  # Orange
                AlertSeverity.ERROR: 0xE74C3C,  # Red
                AlertSeverity.CRITICAL: 0x992D22,  # Dark red
            }

            color = color_map.get(severity, 0x95A5A6)

            # Build Discord embed
            embed = {
                "title": f"{alert['emoji']} {alert['severity']} - {alert['alert_type']}",
                "description": alert["message"] + alert["data_str"],
                "color": color,
                "timestamp": alert["timestamp"],
                "footer": {"text": "Andre Assassin Alerting System"},
            }

            payload = {"embeds": [embed]}

            # Send webhook
            async with aiohttp.ClientSession() as session:
                async with session.post(self.discord_webhook_url, json=payload) as resp:
                    if resp.status == 204:
                        logger.info("Alert sent to Discord")
                        return True
                    else:
                        logger.error(f"Discord webhook failed: {resp.status}")
                        return False

        except Exception as e:
            logger.error(f"Discord alert failed: {e}")
            return False

    async def _send_telegram(self, alert: Dict, severity: AlertSeverity) -> bool:
        """Send alert to Telegram"""
        try:
            # Format message
            message = (
                f"{alert['emoji']} **{alert['severity']}** - {alert['alert_type']}\n\n"
                f"{alert['message']}"
                f"{alert['data_str']}\n\n"
                f"_Timestamp: {alert['timestamp']}_"
            )

            # Telegram API URL
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"

            payload = {"chat_id": self.telegram_chat_id, "text": message, "parse_mode": "Markdown"}

            # Send message
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        logger.info("Alert sent to Telegram")
                        return True
                    else:
                        logger.error(f"Telegram API failed: {resp.status}")
                        return False

        except Exception as e:
            logger.error(f"Telegram alert failed: {e}")
            return False

    async def _send_email(self, alert: Dict, severity: AlertSeverity, subject: str) -> bool:
        """Send alert via email"""
        try:
            # Create email
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{alert['severity']}] {subject}"
            msg["From"] = self.email_username
            msg["To"] = self.alert_email_to

            # Plain text version
            text = (
                f"{alert['emoji']} {alert['severity']} - {alert['alert_type']}\n\n"
                f"{alert['message']}\n"
                f"{alert['data_str']}\n"
                f"Timestamp: {alert['timestamp']}"
            )

            # HTML version
            html = f"""
            <html>
              <body>
                <h2>{alert['emoji']} {alert['severity']} - {alert['alert_type']}</h2>
                <p>{alert['message']}</p>
                {
                    f"<h3>Additional Data:</h3><ul>"
                    f"{''.join([f'<li>{k}: {v}</li>' for k, v in alert['data'].items()])}"
                    f"</ul>"
                    if alert['data']
                    else ""
                }
                <p><em>Timestamp: {alert['timestamp']}</em></p>
              </body>
            </html>
            """

            msg.attach(MIMEText(text, "plain"))
            msg.attach(MIMEText(html, "html"))

            # Send email
            with smtplib.SMTP(self.email_smtp_host, self.email_smtp_port) as server:
                server.starttls()
                server.login(self.email_username, self.email_password)
                server.send_message(msg)

            logger.info("Alert sent via email")
            return True

        except Exception as e:
            logger.error(f"Email alert failed: {e}")
            return False

    # ===== CONVENIENCE METHODS FOR COMMON ALERTS =====

    async def alert_kill_switch_triggered(
        self, trigger_type: str, current_value: float, limit: float
    ):
        """Alert when kill switch triggers"""
        await self.send_alert(
            alert_type=AlertType.KILL_SWITCH,
            severity=AlertSeverity.CRITICAL,
            message=f"🚨 Kill switch triggered: {trigger_type}",
            data={
                "trigger_type": trigger_type,
                "current_value": f"{current_value:.2f}%",
                "limit": f"{limit:.2f}%",
                "action": "All trading STOPPED",
            },
        )

    async def alert_websocket_disconnect(self, symbol: str, exchange: str, error: str):
        """Alert on WebSocket disconnect"""
        await self.send_alert(
            alert_type=AlertType.WEBSOCKET_DISCONNECT,
            severity=AlertSeverity.WARNING,
            message=f"WebSocket disconnected: {symbol} on {exchange}",
            data={
                "symbol": symbol,
                "exchange": exchange,
                "error": error,
                "action": "Attempting reconnection",
            },
        )

    async def alert_validation_failure(self, symbol: str, validation_type: str, reason: str):
        """Alert on learned level validation failure"""
        await self.send_alert(
            alert_type=AlertType.VALIDATION_FAILURE,
            severity=AlertSeverity.WARNING,
            message=f"Validation failed: {symbol} - {validation_type}",
            data={
                "symbol": symbol,
                "validation_type": validation_type,
                "reason": reason,
                "action": "Using fallback levels",
            },
        )

    async def alert_trade_executed(
        self, symbol: str, direction: str, entry_price: float, position_size: float
    ):
        """Alert on trade execution (INFO level)"""
        await self.send_alert(
            alert_type=AlertType.TRADE_EXECUTION,
            severity=AlertSeverity.INFO,
            message=f"Trade executed: {direction.upper()} {symbol} @ ${entry_price:,.2f}",
            data={
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "position_size": position_size,
            },
        )

    async def alert_database_error(self, operation: str, error: str):
        """Alert on database errors"""
        await self.send_alert(
            alert_type=AlertType.DATABASE_ERROR,
            severity=AlertSeverity.ERROR,
            message=f"Database error during: {operation}",
            data={"operation": operation, "error": error},
        )

    async def alert_system_health_warning(
        self, component: str, metric: str, current_value: Any, threshold: Any
    ):
        """Alert on system health warnings"""
        await self.send_alert(
            alert_type=AlertType.SYSTEM_HEALTH,
            severity=AlertSeverity.WARNING,
            message=f"System health warning: {component} - {metric}",
            data={
                "component": component,
                "metric": metric,
                "current_value": current_value,
                "threshold": threshold,
            },
        )

    async def alert_optimization_complete(
        self,
        symbol: str,
        direction: str,
        webhook_source: str,
        win_rate: float,
        rr_ratio: float,
        trials: int,
    ):
        """Alert when Optuna optimization completes"""
        await self.send_alert(
            alert_type=AlertType.OPTIMIZATION_COMPLETE,
            severity=AlertSeverity.INFO,
            message=f"✅ Optimization complete: {webhook_source} - {symbol} {direction}",
            data={
                "webhook_source": webhook_source,
                "symbol": symbol,
                "direction": direction,
                "best_win_rate": f"{win_rate:.1f}%",
                "best_rr_ratio": f"{rr_ratio:.2f}",
                "trials_completed": trials,
                "action": "Strategy ready for Phase III promotion",
            },
        )

    async def alert_strategy_degradation(
        self,
        symbol: str,
        direction: str,
        webhook_source: str,
        current_wr: float,
        expected_wr: float,
        recent_losses: int,
    ):
        """Alert when strategy performance degrades"""
        await self.send_alert(
            alert_type=AlertType.STRATEGY_DEGRADATION,
            severity=AlertSeverity.WARNING,
            message=f"⚠️ Strategy performance degraded: {webhook_source} - {symbol} {direction}",
            data={
                "webhook_source": webhook_source,
                "symbol": symbol,
                "direction": direction,
                "current_win_rate": f"{current_wr:.1f}%",
                "expected_win_rate": f"{expected_wr:.1f}%",
                "recent_losses": recent_losses,
                "action": "Consider re-optimization or circuit breaker",
            },
        )

    async def alert_phase_transition(
        self,
        symbol: str,
        direction: str,
        webhook_source: str,
        from_phase: str,
        to_phase: str,
        reason: str,
    ):
        """Alert on phase transitions (I → II → III)"""
        severity = AlertSeverity.INFO if to_phase == "III" else AlertSeverity.INFO
        await self.send_alert(
            alert_type=AlertType.PHASE_TRANSITION,
            severity=severity,
            message=f"📊 Phase transition: {webhook_source} - {symbol} {direction} ({from_phase} → {to_phase})",
            data={
                "webhook_source": webhook_source,
                "symbol": symbol,
                "direction": direction,
                "from_phase": from_phase,
                "to_phase": to_phase,
                "reason": reason,
            },
        )


# Global instance
_alerting_service: Optional[AlertingService] = None


def get_alerting_service() -> AlertingService:
    """Get or create global alerting service"""
    global _alerting_service
    if _alerting_service is None:
        _alerting_service = AlertingService()
    return _alerting_service
