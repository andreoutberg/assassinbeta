"""
Prometheus Metrics Service for Andre Assassin Trading System

Provides comprehensive metrics tracking for:
- Webhook events
- Trading signals and trades
- Optimization runs
- Win rates and P&L
- API latencies
- System health
"""

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
from prometheus_fastapi_instrumentator import Instrumentator
from typing import Optional, Dict, Any
import time
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Create a custom registry to avoid conflicts
registry = CollectorRegistry()

# ============== WEBHOOK METRICS ==============
webhook_received_total = Counter(
    'andre_webhook_received_total',
    'Total number of webhooks received',
    ['source', 'symbol', 'action'],
    registry=registry
)

webhook_processing_time = Histogram(
    'andre_webhook_processing_seconds',
    'Time spent processing webhooks',
    ['source'],
    registry=registry
)

webhook_errors_total = Counter(
    'andre_webhook_errors_total',
    'Total number of webhook processing errors',
    ['source', 'error_type'],
    registry=registry
)

# ============== TRADING METRICS ==============
active_signals_gauge = Gauge(
    'andre_active_signals',
    'Number of active trading signals',
    ['source', 'symbol', 'direction'],
    registry=registry
)

active_trades_gauge = Gauge(
    'andre_active_trades',
    'Number of active trades',
    ['symbol', 'direction', 'strategy'],
    registry=registry
)

trades_executed_total = Counter(
    'andre_trades_executed_total',
    'Total number of trades executed',
    ['symbol', 'direction', 'strategy', 'result'],
    registry=registry
)

trade_pnl_gauge = Gauge(
    'andre_trade_pnl',
    'Current P&L for active trades',
    ['symbol', 'trade_id'],
    registry=registry
)

cumulative_pnl_gauge = Gauge(
    'andre_cumulative_pnl',
    'Cumulative P&L over time',
    ['strategy', 'period'],
    registry=registry
)

win_rate_gauge = Gauge(
    'andre_win_rate',
    'Current win rate percentage',
    ['source', 'strategy', 'timeframe'],
    registry=registry
)

# ============== OPTIMIZATION METRICS ==============
optimization_runs_total = Counter(
    'andre_optimization_runs_total',
    'Total number of optimization runs',
    ['optimizer', 'status'],
    registry=registry
)

optimization_duration = Histogram(
    'andre_optimization_duration_seconds',
    'Time spent running optimizations',
    ['optimizer'],
    buckets=[10, 30, 60, 120, 300, 600, 1800, 3600],
    registry=registry
)

optimization_best_score = Gauge(
    'andre_optimization_best_score',
    'Best optimization score achieved',
    ['optimizer', 'objective'],
    registry=registry
)

hyperparameters_gauge = Gauge(
    'andre_hyperparameters',
    'Current hyperparameter values',
    ['parameter', 'strategy'],
    registry=registry
)

# ============== ALERT METRICS ==============
alerts_triggered_total = Counter(
    'andre_alerts_triggered_total',
    'Total number of alerts triggered',
    ['alert_type', 'severity', 'symbol'],
    registry=registry
)

active_alerts_gauge = Gauge(
    'andre_active_alerts',
    'Number of currently active alerts',
    ['alert_type', 'severity'],
    registry=registry
)

# ============== API METRICS ==============
api_request_duration = Histogram(
    'andre_api_request_duration_seconds',
    'API request duration',
    ['method', 'endpoint', 'status'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=registry
)

api_requests_total = Counter(
    'andre_api_requests_total',
    'Total number of API requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

external_api_latency = Histogram(
    'andre_external_api_latency_seconds',
    'External API call latency',
    ['api', 'endpoint'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=registry
)

# ============== DATABASE METRICS ==============
db_connections_active = Gauge(
    'andre_db_connections_active',
    'Number of active database connections',
    registry=registry
)

db_connections_idle = Gauge(
    'andre_db_connections_idle',
    'Number of idle database connections',
    registry=registry
)

db_query_duration = Histogram(
    'andre_db_query_duration_seconds',
    'Database query duration',
    ['query_type', 'table'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=registry
)

# ============== REDIS METRICS ==============
redis_operations_total = Counter(
    'andre_redis_operations_total',
    'Total number of Redis operations',
    ['operation', 'status'],
    registry=registry
)

redis_hit_rate_gauge = Gauge(
    'andre_redis_hit_rate',
    'Redis cache hit rate percentage',
    registry=registry
)

redis_memory_usage_gauge = Gauge(
    'andre_redis_memory_usage_bytes',
    'Redis memory usage in bytes',
    registry=registry
)

# ============== SYSTEM METRICS ==============
system_health_gauge = Gauge(
    'andre_system_health',
    'Overall system health score (0-100)',
    registry=registry
)

component_status_gauge = Gauge(
    'andre_component_status',
    'Component status (1=up, 0=down)',
    ['component'],
    registry=registry
)

background_tasks_gauge = Gauge(
    'andre_background_tasks',
    'Number of background tasks',
    ['task_type', 'status'],
    registry=registry
)


class MetricsService:
    """Service for managing Prometheus metrics"""

    def __init__(self):
        self.instrumentator = None
        self._start_time = time.time()

    def init_fastapi_instrumentation(self, app):
        """Initialize FastAPI instrumentation"""
        self.instrumentator = Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
            should_respect_env_var=True,
            should_instrument_requests_inprogress=True,
            excluded_handlers=["/metrics", "/health"],
            env_var_name="ENABLE_METRICS",
            inprogress_name="andre_http_requests_inprogress",
            inprogress_labels=True,
        )

        # Add custom metrics
        self.instrumentator.add(self._http_request_duration_metric())
        self.instrumentator.add(self._http_request_size_metric())
        self.instrumentator.add(self._http_response_size_metric())

        # Instrument the app
        self.instrumentator.instrument(app)

        logger.info("FastAPI instrumentation initialized")

    def _http_request_duration_metric(self):
        """Custom HTTP request duration metric"""
        def instrumentation(info):
            api_request_duration.labels(
                method=info.request.method,
                endpoint=info.request.url.path,
                status=info.response.status_code
            ).observe(info.modified_duration)
        return instrumentation

    def _http_request_size_metric(self):
        """Custom HTTP request size metric"""
        request_size = Histogram(
            'andre_http_request_size_bytes',
            'HTTP request size in bytes',
            ['method', 'endpoint'],
            registry=registry
        )

        def instrumentation(info):
            if info.request.headers.get("content-length"):
                request_size.labels(
                    method=info.request.method,
                    endpoint=info.request.url.path
                ).observe(int(info.request.headers["content-length"]))
        return instrumentation

    def _http_response_size_metric(self):
        """Custom HTTP response size metric"""
        response_size = Histogram(
            'andre_http_response_size_bytes',
            'HTTP response size in bytes',
            ['method', 'endpoint', 'status'],
            registry=registry
        )

        def instrumentation(info):
            if info.response.headers.get("content-length"):
                response_size.labels(
                    method=info.request.method,
                    endpoint=info.request.url.path,
                    status=info.response.status_code
                ).observe(int(info.response.headers["content-length"]))
        return instrumentation

    # ============== WEBHOOK METRICS METHODS ==============
    def record_webhook(self, source: str, symbol: str, action: str):
        """Record a webhook event"""
        webhook_received_total.labels(source=source, symbol=symbol, action=action).inc()

    def record_webhook_processing_time(self, source: str, duration: float):
        """Record webhook processing time"""
        webhook_processing_time.labels(source=source).observe(duration)

    def record_webhook_error(self, source: str, error_type: str):
        """Record a webhook error"""
        webhook_errors_total.labels(source=source, error_type=error_type).inc()

    # ============== TRADING METRICS METHODS ==============
    def update_active_signals(self, source: str, symbol: str, direction: str, count: int):
        """Update active signals gauge"""
        active_signals_gauge.labels(source=source, symbol=symbol, direction=direction).set(count)

    def update_active_trades(self, symbol: str, direction: str, strategy: str, count: int):
        """Update active trades gauge"""
        active_trades_gauge.labels(symbol=symbol, direction=direction, strategy=strategy).set(count)

    def record_trade_execution(self, symbol: str, direction: str, strategy: str, result: str):
        """Record trade execution"""
        trades_executed_total.labels(
            symbol=symbol,
            direction=direction,
            strategy=strategy,
            result=result
        ).inc()

    def update_trade_pnl(self, symbol: str, trade_id: str, pnl: float):
        """Update trade P&L"""
        trade_pnl_gauge.labels(symbol=symbol, trade_id=trade_id).set(pnl)

    def update_cumulative_pnl(self, strategy: str, period: str, pnl: float):
        """Update cumulative P&L"""
        cumulative_pnl_gauge.labels(strategy=strategy, period=period).set(pnl)

    def update_win_rate(self, source: str, strategy: str, timeframe: str, rate: float):
        """Update win rate"""
        win_rate_gauge.labels(source=source, strategy=strategy, timeframe=timeframe).set(rate)

    # ============== OPTIMIZATION METRICS METHODS ==============
    def record_optimization_run(self, optimizer: str, status: str):
        """Record an optimization run"""
        optimization_runs_total.labels(optimizer=optimizer, status=status).inc()

    def record_optimization_duration(self, optimizer: str, duration: float):
        """Record optimization duration"""
        optimization_duration.labels(optimizer=optimizer).observe(duration)

    def update_optimization_score(self, optimizer: str, objective: str, score: float):
        """Update best optimization score"""
        optimization_best_score.labels(optimizer=optimizer, objective=objective).set(score)

    def update_hyperparameter(self, parameter: str, strategy: str, value: float):
        """Update hyperparameter value"""
        hyperparameters_gauge.labels(parameter=parameter, strategy=strategy).set(value)

    # ============== ALERT METRICS METHODS ==============
    def record_alert(self, alert_type: str, severity: str, symbol: str = ""):
        """Record an alert"""
        alerts_triggered_total.labels(alert_type=alert_type, severity=severity, symbol=symbol).inc()

    def update_active_alerts(self, alert_type: str, severity: str, count: int):
        """Update active alerts count"""
        active_alerts_gauge.labels(alert_type=alert_type, severity=severity).set(count)

    # ============== DATABASE METRICS METHODS ==============
    def update_db_connections(self, active: int, idle: int):
        """Update database connection metrics"""
        db_connections_active.set(active)
        db_connections_idle.set(idle)

    def record_db_query(self, query_type: str, table: str, duration: float):
        """Record database query duration"""
        db_query_duration.labels(query_type=query_type, table=table).observe(duration)

    # ============== REDIS METRICS METHODS ==============
    def record_redis_operation(self, operation: str, status: str):
        """Record Redis operation"""
        redis_operations_total.labels(operation=operation, status=status).inc()

    def update_redis_hit_rate(self, rate: float):
        """Update Redis hit rate"""
        redis_hit_rate_gauge.set(rate)

    def update_redis_memory(self, bytes_used: int):
        """Update Redis memory usage"""
        redis_memory_usage_gauge.set(bytes_used)

    # ============== SYSTEM METRICS METHODS ==============
    def update_system_health(self, score: float):
        """Update system health score (0-100)"""
        system_health_gauge.set(min(100, max(0, score)))

    def update_component_status(self, component: str, is_up: bool):
        """Update component status"""
        component_status_gauge.labels(component=component).set(1 if is_up else 0)

    def update_background_tasks(self, task_type: str, status: str, count: int):
        """Update background tasks count"""
        background_tasks_gauge.labels(task_type=task_type, status=status).set(count)

    def record_external_api_call(self, api: str, endpoint: str, duration: float):
        """Record external API call latency"""
        external_api_latency.labels(api=api, endpoint=endpoint).observe(duration)

    def get_metrics(self):
        """Generate Prometheus metrics"""
        return generate_latest(registry)


# Create singleton instance
metrics_service = MetricsService()