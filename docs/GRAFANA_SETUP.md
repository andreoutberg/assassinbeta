# Grafana & Prometheus Monitoring Setup Guide

## Overview

This guide provides comprehensive instructions for setting up and using the Grafana + Prometheus monitoring stack for the Andre Assassin Trading System. The monitoring stack provides real-time insights into trading performance, system health, and optimization metrics.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Grafana   │────▶│  Prometheus  │────▶│   Backend   │
│  (Port 3001)│     │  (Port 9090) │     │  (Port 8000)│
└─────────────┘     └──────────────┘     └─────────────┘
                            │
                    ┌───────┼────────┐
                    │       │        │
              ┌─────▼──┐ ┌─▼─────┐ ┌▼──────┐
              │Postgres│ │ Redis │ │ Node  │
              │Exporter│ │Export.│ │Export.│
              └────────┘ └───────┘ └───────┘
```

## Quick Start

### 1. Environment Configuration

Copy the example environment file and configure monitoring settings:

```bash
cp .env.example .env
```

Edit `.env` and update the monitoring section:

```env
# Prometheus Metrics
ENABLE_METRICS=true
PROMETHEUS_PORT=9090
PROMETHEUS_RETENTION_DAYS=30
PROMETHEUS_RETENTION_SIZE_GB=10

# Grafana Dashboard
GRAFANA_PORT=3001
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=your_secure_password_here
```

### 2. Start the Monitoring Stack

```bash
# Start all services including monitoring
docker-compose up -d

# Or start only monitoring services
docker-compose up -d prometheus grafana postgres-exporter redis-exporter
```

### 3. Access the Dashboards

- **Grafana**: http://localhost:3001/grafana/
  - Default login: admin / (password from .env)
- **Prometheus**: http://localhost:9090/prometheus/
- **Metrics Endpoint**: http://localhost/metrics

## Grafana Dashboard Features

### Trading Overview Dashboard

The main dashboard provides comprehensive monitoring of:

#### 1. **Webhook Metrics**
- Total webhooks received (hourly/daily)
- Webhook processing time
- Webhook errors by source
- Real-time webhook rate

#### 2. **Trading Signals & Positions**
- Active signals count
- Active trades by strategy
- Trade execution history
- Signal-to-trade conversion rate

#### 3. **Win Rate & Performance**
- Overall win rate percentage
- Win rates by source and strategy
- Win rate trends over time
- Strategy comparison matrix

#### 4. **Profit & Loss Tracking**
- Cumulative P&L over time
- P&L by strategy
- Daily/Weekly/Monthly P&L
- Maximum drawdown

#### 5. **Optimization Metrics**
- Optimization runs (success/failure)
- Optimization duration histogram
- Best optimization scores
- Hyperparameter evolution

#### 6. **System Performance**
- API latency percentiles (p50, p95, p99)
- Database connection pool status
- Redis cache hit rate
- Memory usage by service

#### 7. **Alerts & Health**
- Active alerts count
- Alert history
- System health score
- Component status indicators

## Custom Metrics Integration

### Adding New Metrics

1. **Define metrics in `app/services/metrics.py`:**

```python
from prometheus_client import Counter, Gauge, Histogram

# Example: New trade metric
trade_slippage_gauge = Gauge(
    'andre_trade_slippage',
    'Slippage in basis points',
    ['symbol', 'exchange'],
    registry=registry
)
```

2. **Update metric in your code:**

```python
from app.services.metrics import metrics_service

# Record slippage
metrics_service.trade_slippage_gauge.labels(
    symbol='BTC/USDT',
    exchange='bybit'
).set(slippage_bps)
```

3. **Add to Grafana dashboard:**
   - Navigate to Grafana
   - Edit dashboard
   - Add new panel
   - Query: `andre_trade_slippage{symbol="BTC/USDT"}`

## Prometheus Queries

### Useful PromQL Examples

```promql
# Average win rate over last hour
avg_over_time(andre_win_rate[1h])

# Trade execution rate
rate(andre_trades_executed_total[5m]) * 60

# P95 API latency
histogram_quantile(0.95,
  sum(rate(andre_api_request_duration_seconds_bucket[5m]))
  by (endpoint, le)
)

# Redis memory usage trend
deriv(andre_redis_memory_usage_bytes[5m])

# Alert on low win rate
andre_win_rate < 0.5
```

## Alert Configuration

### Setting Up Alerts

1. **Create alert rules in Grafana:**
   - Go to Alerting → Alert rules
   - Click "New alert rule"
   - Configure conditions

2. **Example Alert Rules:**

```yaml
# Low Win Rate Alert
- alert: LowWinRate
  expr: andre_win_rate < 0.5
  for: 5m
  annotations:
    summary: "Win rate below 50%"
    description: "Win rate is {{ $value }}%"

# High API Latency
- alert: HighAPILatency
  expr: histogram_quantile(0.95, andre_api_request_duration_seconds_bucket) > 1
  for: 2m
  annotations:
    summary: "API P95 latency above 1s"

# Database Connection Pool Exhausted
- alert: DBPoolExhausted
  expr: andre_db_connections_idle == 0
  for: 1m
  annotations:
    summary: "No idle database connections"
```

## Performance Optimization

### Metric Collection Best Practices

1. **Use appropriate metric types:**
   - Counter: For cumulative values (trades executed)
   - Gauge: For current values (active positions)
   - Histogram: For distributions (latencies)

2. **Label cardinality:**
   - Avoid high-cardinality labels (user IDs)
   - Use bounded label sets (status codes)

3. **Scrape intervals:**
   - Backend: 10s (trading metrics)
   - Database: 30s (connection pools)
   - System: 30s (CPU/memory)

### Storage Optimization

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

storage:
  tsdb:
    retention.time: 30d
    retention.size: 10GB
```

## Troubleshooting

### Common Issues

1. **Grafana not accessible:**
```bash
# Check container status
docker-compose ps grafana

# View logs
docker-compose logs -f grafana

# Restart service
docker-compose restart grafana
```

2. **No metrics appearing:**
```bash
# Verify metrics endpoint
curl http://localhost:8000/metrics

# Check Prometheus targets
curl http://localhost:9090/prometheus/targets

# Verify scrape configuration
docker-compose exec prometheus cat /etc/prometheus/prometheus.yml
```

3. **Dashboard not loading:**
```bash
# Re-provision dashboards
docker-compose restart grafana

# Check provisioning
docker-compose exec grafana ls -la /etc/grafana/provisioning/
```

## Advanced Configuration

### Custom Datasources

Add additional datasources in `grafana/provisioning/datasources/`:

```yaml
apiVersion: 1
datasources:
  - name: PostgreSQL
    type: postgres
    url: postgres:5432
    database: high_wr_db
    user: $POSTGRES_USER
    secureJsonData:
      password: $POSTGRES_PASSWORD
```

### Dashboard Templates

Create dashboard templates in `grafana/dashboards/`:

```json
{
  "dashboard": {
    "title": "Custom Dashboard",
    "panels": [...],
    "templating": {
      "list": [
        {
          "name": "symbol",
          "type": "query",
          "query": "label_values(andre_active_trades, symbol)"
        }
      ]
    }
  }
}
```

### Prometheus Recording Rules

Create recording rules for complex queries:

```yaml
# prometheus/rules/recording.yml
groups:
  - name: trading_aggregates
    interval: 30s
    rules:
      - record: trading:win_rate:5m
        expr: |
          sum(rate(andre_trades_executed_total{result="win"}[5m])) /
          sum(rate(andre_trades_executed_total[5m]))
```

## Backup & Recovery

### Backing Up Grafana

```bash
# Backup dashboards and settings
docker-compose exec grafana tar -czf /tmp/grafana-backup.tar.gz \
  /var/lib/grafana/grafana.db \
  /etc/grafana/provisioning/

# Copy backup to host
docker cp andre_grafana:/tmp/grafana-backup.tar.gz ./backups/
```

### Backing Up Prometheus Data

```bash
# Create snapshot
curl -X POST http://localhost:9090/prometheus/api/v1/admin/tsdb/snapshot

# Copy snapshot
docker cp andre_prometheus:/prometheus/snapshots/ ./backups/
```

## Security Considerations

### 1. Access Control

```nginx
# nginx/conf.d/default.conf
location /metrics {
    allow 172.25.0.0/16;  # Docker network only
    deny all;
}
```

### 2. Authentication

```yaml
# grafana.ini
[auth]
disable_login_form = false
disable_signout_menu = false

[auth.basic]
enabled = true

[auth.anonymous]
enabled = false
```

### 3. HTTPS Configuration

```nginx
server {
    listen 443 ssl;
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    location /grafana/ {
        proxy_pass http://grafana:3000/;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

## Monitoring Checklist

### Daily Monitoring Tasks

- [ ] Check overall system health score
- [ ] Review win rate trends
- [ ] Monitor P&L performance
- [ ] Check for active alerts
- [ ] Verify webhook processing rates

### Weekly Monitoring Tasks

- [ ] Review optimization success rates
- [ ] Analyze API latency trends
- [ ] Check database connection pool usage
- [ ] Review error rates by component
- [ ] Validate backup completions

### Monthly Monitoring Tasks

- [ ] Analyze strategy performance metrics
- [ ] Review and tune alert thresholds
- [ ] Clean up old Prometheus data
- [ ] Update dashboard configurations
- [ ] Performance baseline comparison

## Integration with Trading Strategies

### Phase-Based Monitoring

Monitor strategy phases (I, II, III) with specific metrics:

```python
# Phase I: Conservative
if phase == 1:
    metrics_service.update_hyperparameter('risk_level', 'phase_1', 0.5)

# Phase II: Moderate
elif phase == 2:
    metrics_service.update_hyperparameter('risk_level', 'phase_2', 1.0)

# Phase III: Aggressive
elif phase == 3:
    metrics_service.update_hyperparameter('risk_level', 'phase_3', 2.0)
```

### Optuna Integration

Track optimization metrics:

```python
def optuna_callback(study, trial):
    metrics_service.record_optimization_run(
        optimizer='optuna',
        status='complete'
    )
    metrics_service.update_optimization_score(
        optimizer='optuna',
        objective='sharpe_ratio',
        score=trial.value
    )
```

## Support & Resources

### Documentation

- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [PromQL Tutorial](https://prometheus.io/docs/prometheus/latest/querying/basics/)

### Community

- Project Issues: [GitHub Issues](https://github.com/your-repo/issues)
- Discord: [Trading Community Discord](https://discord.gg/trading)

### Troubleshooting Resources

- Grafana Labs Community: https://community.grafana.com/
- Prometheus Users Group: https://groups.google.com/g/prometheus-users

---

**Last Updated**: November 2024
**Version**: 1.0.0
**Maintained By**: Andre Assassin Development Team