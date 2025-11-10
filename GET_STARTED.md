# 🚀 Get Started on Your Droplet (178.128.174.80)

## Quick Start - 5 Minutes to Deployment

### Step 1: SSH into Your Droplet

```bash
ssh root@178.128.174.80
```

### Step 2: Install Prerequisites (if not already installed)

```bash
# Update system
apt-get update && apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt-get install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version

# Install git
apt-get install git -y
```

### Step 3: Clone Repository

```bash
cd /root
git clone https://github.com/andreoutberg/assassinbeta.git
cd assassinbeta
```

### Step 4: Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit configuration
nano .env
```

**Required Settings** (press Ctrl+X, then Y, then Enter to save):

```bash
# === BYBIT API (REQUIRED) ===
# Get testnet keys from: https://testnet.bybit.com/app/user/api-management
BYBIT_API_KEY=your_testnet_api_key_here
BYBIT_API_SECRET=your_testnet_secret_here
BYBIT_TESTNET=true

# === DATABASE (REQUIRED) ===
# Choose a strong password
POSTGRES_PASSWORD=YourStrongPasswordHere123!

# === ALERTS (RECOMMENDED) ===
# Discord webhook (optional but recommended)
DISCORD_WEBHOOK_URL=

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Email (optional)
EMAIL_ALERTS_ENABLED=false
EMAIL_USERNAME=
EMAIL_PASSWORD=
ALERT_EMAIL_TO=

# === GRAFANA (RECOMMENDED) ===
# Set strong admin password
GRAFANA_ADMIN_PASSWORD=YourStrongGrafanaPassword123!
```

### Step 5: Run One-Command Deployment

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

The script will:
- ✅ Check disk space (need 40GB available)
- ✅ Create required directories
- ✅ Build Docker images (~5 minutes)
- ✅ Start all services
- ✅ Run database migrations
- ✅ Verify health checks
- ✅ Test webhook endpoint
- ✅ Display access URLs

### Step 6: Verify Deployment

```bash
./scripts/health_check.sh
```

You should see:
```
✅ Docker daemon: running
✅ postgres: healthy
✅ redis: healthy
✅ backend: healthy
✅ nginx: healthy
✅ optuna-dashboard: healthy
✅ grafana: healthy
✅ API health check: OK
✅ Database connection: OK
✅ Redis connection: OK
✅ Disk space: 23GB free (good)
✅ Memory usage: 8.2GB / 16GB (51%)
```

---

## 🌐 Access Your System

Open these URLs in your browser:

| Service | URL | Notes |
|---------|-----|-------|
| **Main Dashboard** | http://178.128.174.80/dashboardbeta | Trading dashboard |
| **Optuna Dashboard** | http://178.128.174.80/optuna | Optimization monitoring |
| **Grafana** | http://178.128.174.80/grafana | Metrics (admin / your_password) |
| **API Docs** | http://178.128.174.80/docs | Interactive API documentation |
| **Health Check** | http://178.128.174.80/health | System status |

---

## 📡 Connect TradingView

### Step 1: Create a New Alert in TradingView

1. Go to TradingView chart
2. Click the Alert button (bell icon)
3. Set your conditions (e.g., "Moving Average Crossover")
4. Click "Notifications" tab

### Step 2: Configure Webhook

**Webhook URL**:
```
http://178.128.174.80/api/webhook/tradingview
```

**Message** (paste this):
```json
{
  "symbol": "{{ticker}}",
  "direction": "LONG",
  "entry_price": {{close}},
  "timeframe": "1h",
  "webhook_source": "MyStrategy1h"
}
```

**Important**: Change `webhook_source` for each different strategy!

### Step 3: Test Your Webhook

```bash
./scripts/test_webhook.sh
```

Or manually:
```bash
curl -X POST http://178.128.174.80/api/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "direction": "LONG",
    "entry_price": 43500.50,
    "timeframe": "1h",
    "webhook_source": "TestStrategy"
  }'
```

You should see: `{"status":"created","signal_id":1}`

### Step 4: Watch It Work!

1. **View Dashboard**: http://178.128.174.80/dashboardbeta
2. Your signal appears in "Recent Signals"
3. System enters **Phase I** (collecting 20-40 trades)
4. After baseline: **Phase II** optimization starts
5. Watch live at: http://178.128.174.80/optuna
6. Best strategy auto-deploys to **Phase III**

---

## 🎯 What Happens Next?

### Phase I: Baseline Collection (2-7 days)
- System collects 20-40 trades from your TradingView alerts
- Validates statistical edge (targeting 60%+ win rate)
- **You see**: Signals appearing on dashboard
- **Action needed**: None - keep sending alerts!

### Phase II: Optimization (3-5 minutes)
- Optuna runs 100 trials automatically
- Multi-objective optimization: Win Rate, R/R, Expected Value
- **You see**: Live optimization at http://178.128.174.80/optuna
- **Action needed**: None - it's automatic!

### Phase III: Live Trading (ongoing)
- Best strategy deployed automatically
- Performance monitored continuously
- Alerts sent if performance degrades
- **You see**: Active strategy on dashboard
- **Action needed**: Monitor performance, adjust if needed

---

## 🛠️ Daily Operations

### Check System Health
```bash
cd /root/assassinbeta
./scripts/health_check.sh
```

### View Logs
```bash
# All backend logs
docker compose logs -f backend

# Last 100 lines
docker compose logs --tail=100 backend

# Errors only
./scripts/monitor_logs.sh --errors-only
```

### Backup Database
```bash
./scripts/backup.sh
```

Backups saved to: `/root/assassinbeta/backups/`

### Check Database Size
```bash
curl http://178.128.174.80/api/admin/database/size | jq
```

### Manual Cleanup (if needed)
```bash
# Preview what will be deleted
./scripts/cleanup_database.sh --dry-run

# Actually cleanup
./scripts/cleanup_database.sh
```

---

## 🔧 Maintenance Commands

### Restart Services
```bash
cd /root/assassinbeta
docker compose restart
```

### Restart Specific Service
```bash
docker compose restart backend
docker compose restart nginx
```

### View Service Status
```bash
docker compose ps
```

### Update to Latest Version
```bash
cd /root/assassinbeta
git pull origin main
docker compose up -d --build
```

### Stop All Services
```bash
docker compose down
```

### Start All Services
```bash
docker compose up -d
```

---

## 📊 Monitoring

### Grafana Dashboards

Access: http://178.128.174.80/grafana
- **Username**: admin
- **Password**: (what you set in .env)

**Dashboards Available**:
1. **Trading Overview**: Webhooks, win rates, P&L
2. **Database Health**: Size monitoring, table sizes, cleanup status
3. **System Metrics**: CPU, memory, disk, API performance

### Optuna Dashboard

Access: http://178.128.174.80/optuna

**What You'll See**:
- All optimization studies
- Trial progress (0-100)
- Pareto front visualization
- Hyperparameter importance
- Compare multiple strategies

### Alerts

Configure in `.env`:
- **Discord**: Get instant notifications in Discord channel
- **Telegram**: Get alerts on your phone
- **Email**: Get important alerts via email

**Alert Types**:
- Optimization complete
- Strategy degradation
- Database size warning
- System health issues
- Circuit breaker triggers

---

## 🐛 Troubleshooting

### Services Won't Start

```bash
# Check what's failing
docker compose ps

# View logs for specific service
docker compose logs backend
docker compose logs postgres

# Restart failed service
docker compose restart backend
```

### Can't Access Dashboard

```bash
# Check nginx is running
docker compose ps nginx

# Check nginx logs
docker compose logs nginx

# Test from server
curl http://localhost/health
```

### Webhook Not Working

```bash
# Test webhook endpoint
./scripts/test_webhook.sh

# Check backend logs for webhook processing
docker compose logs backend | grep webhook

# Check firewall (should allow port 80)
ufw status
```

### Out of Disk Space

```bash
# Check disk usage
df -h

# Check database size
curl http://178.128.174.80/api/admin/database/size | jq

# Emergency cleanup
./scripts/cleanup_database.sh

# Or manual cleanup
docker compose exec backend python -c "
from app.services.database_retention import DatabaseRetentionService
import asyncio
service = DatabaseRetentionService()
asyncio.run(service.emergency_cleanup(target_gb=25))
"
```

### Database Connection Errors

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check PostgreSQL logs
docker compose logs postgres

# Verify credentials in .env
cat .env | grep POSTGRES
```

### High Memory Usage

```bash
# Check memory usage
free -h

# Check per-container usage
docker stats

# Restart if needed
docker compose restart
```

---

## 🔒 Security Checklist

Before going live with real trading:

- [ ] Changed default PostgreSQL password (strong password)
- [ ] Set strong Grafana admin password
- [ ] Set strong SECRET_KEY in .env
- [ ] Configured firewall (only ports 22, 80, 443 open)
- [ ] Enabled alert notifications (Discord/Telegram/Email)
- [ ] Reviewed CORS settings (restrict if needed)
- [ ] Webhook rate limiting enabled
- [ ] Tested backup and restore
- [ ] Set up automated daily backups
- [ ] Monitoring alerts configured
- [ ] Reviewed logs for errors
- [ ] Tested with Bybit testnet first
- [ ] Read SECURITY.md

### Configure Firewall

```bash
# Install UFW if not installed
apt-get install ufw -y

# Allow SSH (don't lock yourself out!)
ufw allow 22/tcp

# Allow HTTP
ufw allow 80/tcp

# Allow HTTPS (for future SSL)
ufw allow 443/tcp

# Enable firewall
ufw enable

# Check status
ufw status
```

---

## 💰 Going Live (Production)

Once you've tested with testnet and everything works:

### Step 1: Get Production API Keys

1. Go to https://www.bybit.com/app/user/api-management
2. Create new API keys
3. **Important**: Enable only what you need (spot trading, no withdrawals)

### Step 2: Update Configuration

```bash
cd /root/assassinbeta
nano .env
```

Change:
```bash
BYBIT_API_KEY=your_LIVE_api_key_here
BYBIT_API_SECRET=your_LIVE_secret_here
BYBIT_TESTNET=false  # IMPORTANT: Set to false

APP_ENV=production
DEBUG=false
```

### Step 3: Restart Services

```bash
docker compose down
docker compose up -d
```

### Step 4: Verify

```bash
./scripts/health_check.sh
```

### Step 5: Start Small

- Begin with small position sizes
- Test with one strategy first
- Monitor closely for first week
- Gradually scale up

---

## 📚 Additional Resources

**Documentation**:
- [DEPLOYMENT.md](DEPLOYMENT.md) - Complete deployment guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
- [docs/TRADINGVIEW_INTEGRATION.md](docs/TRADINGVIEW_INTEGRATION.md) - TradingView setup
- [docs/OPTUNA_INTEGRATION.md](docs/OPTUNA_INTEGRATION.md) - Optimization guide
- [docs/PERFORMANCE.md](docs/PERFORMANCE.md) - Performance benchmarks

**Community**:
- GitHub Issues: https://github.com/andreoutberg/assassinbeta/issues
- GitHub Discussions: https://github.com/andreoutberg/assassinbeta/discussions

**Logs Location**:
- Application logs: `/root/assassinbeta/logs/`
- Docker logs: `docker compose logs`

---

## ✅ Success Checklist

After deployment, verify:

- [ ] All services are running (`docker compose ps`)
- [ ] Health check passes (`./scripts/health_check.sh`)
- [ ] Dashboard accessible (http://178.128.174.80/dashboardbeta)
- [ ] Optuna accessible (http://178.128.174.80/optuna)
- [ ] Grafana accessible (http://178.128.174.80/grafana)
- [ ] Webhook test passes (`./scripts/test_webhook.sh`)
- [ ] TradingView alert created and webhook configured
- [ ] Alert notification channel tested (Discord/Telegram/Email)
- [ ] Database backup tested (`./scripts/backup.sh`)
- [ ] Firewall configured (`ufw status`)
- [ ] Monitoring dashboards reviewed
- [ ] Documentation bookmarked

---

## 🎉 You're Live!

Your Andre Assassin trading system is now running!

**Next**:
1. Create TradingView alerts with different `webhook_source` names
2. Watch Phase I baseline collection
3. Monitor Optuna optimization in Phase II
4. Review strategy performance in Phase III
5. Scale up gradually

**Remember**: The system is fully automated. You just need to:
- Send TradingView webhooks
- Monitor the dashboards
- Respond to alerts if needed

Good luck with your trading! 📈💰

---

**Questions?** Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) or create an issue on GitHub.
