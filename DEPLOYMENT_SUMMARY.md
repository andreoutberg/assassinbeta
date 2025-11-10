# Andre Assassin v0.2.0 - Deployment Summary

## 🎯 System Overview

**Andre Assassin** is an automated high win-rate trading system that:
- Receives TradingView webhook signals
- Validates statistical edge (60%+ win rate)
- Optimizes TP/SL using Optuna Bayesian optimization
- Automatically deploys profitable strategies
- Monitors performance with real-time dashboards

## 📦 What's Included in v0.2.0

### Core System
- ✅ FastAPI backend with webhook endpoint
- ✅ PostgreSQL database with retention policies
- ✅ Redis caching layer
- ✅ CCXT Bybit integration (testnet + mainnet ready)
- ✅ Optuna multi-objective optimization
- ✅ Three-phase validation system (I → II → III)
- ✅ Multi-source tracking (multiple TradingView strategies)

### Monitoring & Analytics
- ✅ Optuna Dashboard (real-time optimization visualization)
- ✅ Grafana + Prometheus metrics
- ✅ Database health monitoring
- ✅ Multi-channel alerting (Discord/Telegram/Email)
- ✅ WebSocket real-time updates

### Infrastructure
- ✅ Docker Compose orchestration
- ✅ Nginx reverse proxy with routing
- ✅ Health checks for all services
- ✅ Database migrations
- ✅ Automated backups
- ✅ Log rotation

### Documentation
- ✅ Complete deployment guide
- ✅ Architecture documentation
- ✅ API documentation
- ✅ TradingView webhook setup guide
- ✅ Troubleshooting guide
- ✅ Module-level README files

## 🚀 Quick Start

### Prerequisites
- Ubuntu/Debian server (tested on DigitalOcean)
- 8+ CPU cores, 16GB+ RAM, 40GB+ disk
- Docker & Docker Compose installed
- Git installed

### One-Command Deployment

```bash
# Clone repository
git clone https://github.com/andreoutberg/assassinbeta.git
cd assassinbeta

# Run deployment script
./scripts/deploy.sh
```

The script will:
1. Check prerequisites
2. Create required directories
3. Configure environment variables
4. Build Docker images
5. Start all services
6. Run database migrations
7. Verify health checks
8. Display access URLs

### Manual Deployment

```bash
# 1. Configure environment
cp .env.example .env
nano .env  # Edit with your settings

# 2. Build and start services
docker-compose build
docker-compose up -d

# 3. Check health
./scripts/health_check.sh

# 4. Test webhook
./scripts/test_webhook.sh
```

## 🌐 Access Points

After deployment at **178.128.174.80**:

| Service | URL | Purpose |
|---------|-----|---------|
| **Main Dashboard** | http://178.128.174.80/dashboardbeta | Trading dashboard |
| **Optuna Dashboard** | http://178.128.174.80/optuna | Optimization monitoring |
| **Grafana** | http://178.128.174.80/grafana | Metrics & analytics |
| **API Docs** | http://178.128.174.80/docs | FastAPI Swagger UI |
| **Webhook Endpoint** | http://178.128.174.80/api/webhook/tradingview | TradingView alerts |
| **Health Check** | http://178.128.174.80/health | System health |

## 🔧 Configuration

### Required Environment Variables

```bash
# Bybit API (get from https://testnet.bybit.com/app/user/api-management)
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_api_secret_here
BYBIT_TESTNET=true  # Set false for live trading

# Database
POSTGRES_PASSWORD=choose_secure_password_here

# Alerts (optional but recommended)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
EMAIL_ALERTS_ENABLED=true
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
ALERT_EMAIL_TO=alerts@yourcompany.com

# Grafana
GRAFANA_ADMIN_PASSWORD=choose_strong_password
```

### TradingView Webhook Setup

**Webhook URL**: `http://178.128.174.80/api/webhook/tradingview`

**Alert Message**:
```json
{
  "symbol": "{{ticker}}",
  "direction": "LONG",
  "entry_price": {{close}},
  "timeframe": "1h",
  "webhook_source": "Edge2Trend1h"
}
```

Change `webhook_source` for each strategy you track.

## 📊 System Features

### Three-Phase Validation
1. **Phase I**: Collect 20-40 baseline trades, validate statistical edge
2. **Phase II**: Optimize TP/SL with Optuna (100 trials, 3-5 minutes)
3. **Phase III**: Deploy best strategy for live trading

### Automated Optimization
- Multi-objective: Win Rate, Risk/Reward, Expected Value
- NSGA-II sampler for Pareto front discovery
- Walk-forward validation on unseen data
- Resumable optimization (PostgreSQL persistence)

### Database Management
- **Automatic retention policies** prevent disk overflow
- Price samples: 30 days retention
- Baseline trades: 90 days retention
- Completed trades: 180 days retention
- Optuna trials: 90 days retention
- Alerts at 30GB, 35GB, 38GB (40GB total disk)

### Multi-Source Tracking
- Track unlimited TradingView strategies simultaneously
- Each `webhook_source` gets independent optimization
- Separate Optuna studies per source
- Per-source analytics and performance tracking

## 🛠️ Maintenance

### Daily Operations

```bash
# Check system health
./scripts/health_check.sh

# View logs
./scripts/monitor_logs.sh backend

# Database backup
./scripts/backup.sh
```

### Database Cleanup

```bash
# Manual cleanup (with dry-run preview)
./scripts/cleanup_database.sh

# Check database size
curl http://178.128.174.80/api/admin/database/size
```

### Updating System

```bash
# Pull latest changes
git pull origin main

# Update and restart
./scripts/update.sh
```

## 🔒 Security Checklist

Before going live:

- [ ] Changed default PostgreSQL password
- [ ] Set strong Grafana admin password
- [ ] Set strong SECRET_KEY in .env
- [ ] Configured firewall (UFW or DigitalOcean firewall)
- [ ] Enabled alert notifications
- [ ] Reviewed CORS settings
- [ ] Webhook rate limiting enabled
- [ ] Tested backup and restore
- [ ] Configured automated backups
- [ ] Set up monitoring alerts

## 📈 Performance Benchmarks

Expected performance on 8 CPU / 16GB RAM:

- **API response time**: < 100ms (p95)
- **Webhook processing**: < 50ms
- **Optimization runtime**: 3-5 minutes (100 trials)
- **Dashboard load time**: < 1.5 seconds
- **WebSocket latency**: < 100ms
- **Database queries**: < 10ms (p95)

## 🐛 Troubleshooting

### Services won't start
```bash
docker-compose logs -f backend
docker-compose restart backend
```

### Database connection failed
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check credentials in .env
cat .env | grep POSTGRES
```

### Webhook not received
```bash
# Test webhook endpoint
./scripts/test_webhook.sh

# Check backend logs
docker-compose logs -f backend | grep webhook
```

### Out of disk space
```bash
# Check disk usage
df -h

# Run emergency cleanup
docker-compose exec backend python -c "
from app.services.database_retention import DatabaseRetentionService
import asyncio
service = DatabaseRetentionService()
asyncio.run(service.emergency_cleanup(target_gb=25))
"
```

## 📚 Documentation

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Complete step-by-step deployment guide
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
- **[.claude/claude.md](.claude/claude.md)** - AI assistant reference guide
- **[docs/TRADINGVIEW_INTEGRATION.md](docs/TRADINGVIEW_INTEGRATION.md)** - TradingView setup
- **[docs/OPTUNA_INTEGRATION.md](docs/OPTUNA_INTEGRATION.md)** - Optuna optimization guide
- **[docs/STATISTICS.md](docs/STATISTICS.md)** - Statistical methods explained
- **[docs/GRAFANA_SETUP.md](docs/GRAFANA_SETUP.md)** - Grafana dashboard guide

## 🎓 Next Steps

After successful deployment:

1. **Test with testnet**: Use Bybit testnet to validate system
2. **Configure strategies**: Set up TradingView alerts with different `webhook_source` values
3. **Monitor Phase I**: Watch baseline collection for 20-40 trades
4. **Review optimization**: Check Optuna Dashboard when Phase II starts
5. **Validate Phase III**: Monitor live strategy performance
6. **Set up alerts**: Configure Discord/Telegram/Email notifications
7. **Schedule backups**: Set up cron job for daily backups
8. **Review analytics**: Use Grafana dashboards for insights

## 💡 Tips for Success

1. **Start with one strategy**: Test with one TradingView strategy before scaling
2. **Use testnet first**: Validate everything works with Bybit testnet
3. **Monitor disk space**: Check database size weekly
4. **Review logs daily**: Look for errors or warnings
5. **Test webhook regularly**: Ensure TradingView connectivity
6. **Backup before updates**: Always backup before system updates
7. **Document strategies**: Keep notes on each `webhook_source` strategy
8. **Review Pareto fronts**: Understand optimization trade-offs
9. **Adjust retention**: Modify retention periods based on usage
10. **Stay updated**: Watch GitHub releases for updates

## 🆘 Support

- **Issues**: https://github.com/andreoutberg/assassinbeta/issues
- **Discussions**: https://github.com/andreoutberg/assassinbeta/discussions
- **Documentation**: Read all docs in `docs/` directory
- **Logs**: Check logs with `./scripts/monitor_logs.sh`

## 📝 Version Information

- **Version**: 0.2.0
- **Release Date**: November 2025
- **Python**: 3.11+
- **PostgreSQL**: 16
- **Redis**: 7
- **Docker**: 20.10+
- **Docker Compose**: 2.0+

## 🎉 You're Ready!

Your Andre Assassin trading system is configured and ready to deploy.

Simply run:
```bash
./scripts/deploy.sh
```

And start receiving TradingView signals!

---

**Built with ❤️ for automated high win-rate trading**
