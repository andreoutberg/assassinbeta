# Claude Code Usage Guide

## Overview
This document provides guidance for working with the Andre Assassin High-WR Trading System using Claude Code.

## Superpowers Plugin

**Status**: Installed and active (`superpowers@superpowers-marketplace`)

**Usage**: Utilize superpowers plugin capabilities when available for:
- Enhanced code analysis and exploration
- Advanced pattern matching and search
- Specialized workflows for trading system development
- Better integration with Python/FastAPI frameworks

## System Architecture

### Core Components
- **Backend**: FastAPI application (`app/main.py`)
- **Database**: PostgreSQL with async SQLAlchemy
- **Cache**: Redis
- **Exchange**: Bybit API integration
- **Frontend**: React/TypeScript (in `frontend/` directory)
- **Reverse Proxy**: Nginx

### Key Services
1. **PriceTracker** - Real-time price monitoring via WebSocket
2. **StatisticsEngine** - Trade analytics and performance metrics
3. **SignalGenerator** - Trading signal generation
4. **PhaseManager** - Multi-phase strategy management
5. **StrategySelector** - Optimal strategy selection
6. **AssetHealthMonitor** - Circuit breaker for failing assets

## Webhook Configuration

### Production Webhook URL
```
http://206.189.116.95/api/webhook/tradingview
```
or
```
https://206.189.116.95/api/webhook/tradingview
```

### Endpoint Details
- **Path**: `/api/webhook/tradingview`
- **Method**: POST
- **Content-Type**: application/json
- **Implementation**: `app/api/api_routes.py:200`

### Payload Format
```json
{
  "symbol": "{{ticker}}",
  "direction": "LONG",
  "entry_price": {{close}},
  "timeframe": "1h",
  "webhook_source": "MyStrategy1h"
}
```

### Testing Webhooks
```bash
# Using built-in test script
./scripts/test_webhook.sh

# Manual test
curl -X POST http://206.189.116.95/api/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "direction": "LONG",
    "entry_price": 50000,
    "timeframe": "1h",
    "webhook_source": "TestStrategy"
  }'
```

## Docker Services

### Running Containers
- `highwr_backend` - FastAPI backend (port 8000 internal)
- `assassinbeta_optuna_dashboard` - Optimization dashboard (port 8080)
- `assassinbeta_nginx` - Reverse proxy (ports 80, 443)
- `postgres` - PostgreSQL database
- `redis` - Redis cache

### Port Mapping
| Service | Internal Port | External Port | Purpose |
|---------|---------------|---------------|---------|
| Backend | 8000 | 80/443 (via nginx) | API endpoints |
| Optuna Dashboard | 8080 | 8080 | Strategy optimization UI |
| Nginx | 80, 443 | 80, 443 | Reverse proxy |
| PostgreSQL | 5432 | - | Database |
| Redis | 6379 | - | Cache |

## Development Workflow

### Common Tasks

#### 1. Check System Health
```bash
curl http://localhost/api/health
```

#### 2. View Logs
```bash
docker logs highwr_backend --tail 100 -f
```

#### 3. Database Access
```bash
docker exec -it postgres psql -U trading -d high_wr_db
```

#### 4. Redis Access
```bash
docker exec -it redis redis-cli
```

#### 5. Run Tests
```bash
cd /root/assassinbeta
pytest tests/
```

### Important Directories
- `/root/assassinbeta/app/` - Backend application code
- `/root/assassinbeta/frontend/` - React frontend
- `/root/assassinbeta/scripts/` - Utility scripts
- `/root/assassinbeta/docs/` - Documentation
- `/root/assassinbeta/migrations/` - Database migrations

## Configuration

### Environment Variables
Located in `/root/assassinbeta/.env`

**Key Settings:**
- `BYBIT_API_KEY` / `BYBIT_API_SECRET` - Exchange credentials
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `WEBHOOK_PORT` - Backend service port (default: 8000)
- `OPTIMIZE_FOR_WIN_RATE` - Strategy optimization mode
- `DISCORD_WEBHOOK_URL` - Notifications

### Strategy Configuration
- `MIN_WIN_RATE` - Minimum acceptable win rate (default: 0.65)
- `MIN_TRADES_FOR_EVALUATION` - Minimum trades before strategy eval
- `OPTUNA_N_TRIALS` - Number of optimization trials

## Code Navigation

### Key Files by Function

**API Endpoints:**
- `app/api/api_routes.py` - Main API routes (webhook, health, stats)
- `app/api/strategy_routes.py` - Strategy management endpoints
- `app/api/routes/beta_api.py` - Beta dashboard API
- `app/api/routes/websocket.py` - WebSocket connections

**Services:**
- `app/services/price_tracker.py` - Real-time price tracking
- `app/services/strategy_processor_async.py` - Async strategy processing
- `app/services/signal_generator.py` - Signal generation logic
- `app/services/bybit_client.py` - Exchange API client

**Database Models:**
- `app/database/models.py` - SQLAlchemy models
- `app/database/strategy_models.py` - Strategy-specific models

**Configuration:**
- `app/config/settings.py` - Application settings
- `app/config/phase_config.py` - Phase management config

## Best Practices

### When Working with Claude Code

1. **Use Superpowers Plugin** - Leverage advanced capabilities when available
2. **Check Running Services** - Always verify Docker containers are running
3. **Review Logs** - Check backend logs for webhook processing
4. **Test Changes** - Use test_webhook.sh to verify modifications
5. **Database Sessions** - Be aware of async SQLAlchemy session management
6. **Background Tasks** - Remember FastAPI dependency sessions close after response

### Code Modifications

1. **API Changes** - Test with curl or test_webhook.sh
2. **Database Changes** - Create migrations, don't modify schema directly
3. **Service Changes** - Restart backend container after modifications
4. **Frontend Changes** - Rebuild frontend if needed

### Security Considerations

- Webhook authentication via `WEBHOOK_API_KEY`
- Rate limiting configured in settings
- CORS origins restricted in production
- Sensitive credentials in `.env` (never commit)

## Troubleshooting

### Common Issues

**1. Webhook Not Receiving Data**
- Check nginx logs: `docker logs assassinbeta_nginx`
- Verify backend is running: `docker ps | grep backend`
- Test locally: `./scripts/test_webhook.sh`

**2. Database Connection Issues**
- Check PostgreSQL: `docker logs postgres`
- Verify connection string in `.env`
- Test connection: `docker exec postgres pg_isready`

**3. Redis Connection Issues**
- Check Redis: `docker logs redis`
- Test connection: `docker exec redis redis-cli ping`

**4. Strategy Not Optimizing**
- Check Optuna dashboard: `http://localhost:8080`
- Verify MIN_BASELINE_TRADES threshold met
- Review backend logs for optimization errors

## Resources

- **Main Documentation**: `/root/assassinbeta/README.md`
- **Getting Started**: `/root/assassinbeta/GET_STARTED.md`
- **Deployment Guide**: `/root/assassinbeta/DEPLOYMENT.md`
- **Performance Guide**: `/root/assassinbeta/docs/PERFORMANCE.md`
- **Grafana Setup**: `/root/assassinbeta/docs/GRAFANA_SETUP.md`

## Notes

- Current public IP: `206.189.116.95`
- System runs in Docker Compose environment
- Backend uses uvicorn with 4 workers
- Frontend is a separate React application
- Optimization runs via Celery worker (if enabled)

---

**Last Updated**: 2025-11-11
**System Version**: 0.1.0
**Environment**: Production
