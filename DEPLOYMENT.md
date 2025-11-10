# Andre Assassin Production Deployment Guide

## Complete Step-by-Step Guide for DigitalOcean Deployment

**Target Server:** 178.128.174.80
**System Specs:** 8 CPU, 16GB RAM, 58GB Disk
**Version:** v0.1.1
**Last Updated:** November 10, 2025

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Part 1: Initial Server Setup](#part-1-initial-server-setup)
3. [Part 2: Clone Repository](#part-2-clone-repository)
4. [Part 3: Configuration](#part-3-configuration)
5. [Part 4: Create Required Directories](#part-4-create-required-directories)
6. [Part 5: Database Initialization](#part-5-database-initialization)
7. [Part 6: Docker Deployment](#part-6-docker-deployment)
8. [Part 7: Verification](#part-7-verification)
9. [Part 8: TradingView Webhook Setup](#part-8-tradingview-webhook-setup)
10. [Part 9: Monitoring](#part-9-monitoring)
11. [Part 10: Common Commands](#part-10-common-commands)
12. [Part 11: Troubleshooting](#part-11-troubleshooting)
13. [Part 12: Maintenance](#part-12-maintenance)
14. [Part 13: Security Checklist](#part-13-security-checklist)
15. [Part 14: Going Live](#part-14-going-live)
16. [Appendix A: Full Example .env](#appendix-a-full-example-env)
17. [Appendix B: Testing Webhook](#appendix-b-testing-webhook)
18. [Appendix C: Quick Start (TL;DR)](#appendix-c-quick-start-tldr)

---

## Prerequisites

### Required Before Starting
- [ ] SSH access to DigitalOcean droplet at 178.128.174.80
- [ ] Root or sudo privileges on the server
- [ ] GitHub account (for cloning the repository)
- [ ] Bybit account with API keys (testnet for testing, live for production)
- [ ] Basic terminal/command line knowledge
- [ ] TradingView account (for sending webhook signals)

### Optional But Recommended
- [ ] Domain name (for HTTPS access)
- [ ] Discord/Telegram account for alerts
- [ ] Email account for notifications

---

## Part 1: Initial Server Setup

### Step 1: Connect to Your Server
```bash
# From your local terminal
ssh root@178.128.174.80

# If you have a specific SSH key
ssh -i ~/.ssh/your_key root@178.128.174.80
```

### Step 2: Update System Packages
```bash
# Update package lists
apt update

# Upgrade installed packages
apt upgrade -y

# Install essential tools
apt install -y curl wget git nano htop net-tools ufw
```

### Step 3: Install Docker and Docker Compose
```bash
# Install Docker prerequisites
apt install -y apt-transport-https ca-certificates curl software-properties-common gnupg lsb-release

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update packages with Docker repository
apt update

# Install Docker
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Verify Docker installation
docker --version
# Should output: Docker version 24.x.x or higher

# Test Docker
docker run hello-world
# Should show "Hello from Docker!" message
```

### Step 4: Configure Firewall
```bash
# Enable UFW firewall
ufw --force enable

# Allow SSH (IMPORTANT - do this first!)
ufw allow 22/tcp

# Allow HTTP
ufw allow 80/tcp

# Allow HTTPS
ufw allow 443/tcp

# Allow backend port
ufw allow 8000/tcp

# Allow frontend port (development)
ufw allow 3000/tcp

# Allow Optuna dashboard
ufw allow 8080/tcp

# Check firewall status
ufw status
```

### Step 5: Create Application User (Optional but Recommended)
```bash
# Create a dedicated user for the application
adduser --system --group --home /home/trader trader

# Add to docker group
usermod -aG docker trader

# Switch to trader user for remaining setup
su - trader
```

---

## Part 2: Clone Repository

### Step 1: Create Project Directory
```bash
# Create directory for the application
mkdir -p /opt/andre-assassin
cd /opt/andre-assassin
```

### Step 2: Clone Repository
```bash
# Clone the repository
git clone https://github.com/andreoutberg/assassinbeta.git .

# Or if you have a different repository URL
git clone https://github.com/your-username/andre-assassin.git .

# Verify files are present
ls -la
# Should show docker-compose.yml, app/, frontend/, etc.
```

### Step 3: Set Permissions
```bash
# Ensure proper ownership
chown -R $(whoami):$(whoami) /opt/andre-assassin

# Set proper permissions
chmod -R 755 /opt/andre-assassin
```

---

## Part 3: Configuration

### Step 1: Create Environment File
```bash
# Copy the example environment file
cp .env.example .env

# Open for editing
nano .env
```

### Step 2: Configure Essential Variables

Here's what each section needs:

#### **BYBIT CONFIGURATION** (Most Important!)
```bash
# For TESTING (use testnet first!)
BYBIT_API_KEY=your_testnet_api_key_here
BYBIT_API_SECRET=your_testnet_secret_here
BYBIT_TESTNET=true

# Get testnet keys from: https://testnet.bybit.com/app/user/api-management
# API Key permissions needed:
# - Spot Trading: Read, Trade
# - Derivatives Trading: Read, Trade
# - Wallet: Read
```

#### **DATABASE CONFIGURATION**
```bash
# Generate a strong password
POSTGRES_PASSWORD=$(openssl rand -base64 32)
echo "Your PostgreSQL password: $POSTGRES_PASSWORD"

# Edit .env and set:
POSTGRES_USER=trading
POSTGRES_PASSWORD=use_the_generated_password_above
POSTGRES_DB=andre_assassin_db
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

#### **REDIS CONFIGURATION**
```bash
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_URL=redis://redis:6379/0
```

#### **WEBHOOK CONFIGURATION**
```bash
# Generate a secure webhook key
WEBHOOK_API_KEY=$(openssl rand -hex 32)
echo "Your webhook key: $WEBHOOK_API_KEY"

# Set in .env:
WEBHOOK_API_KEY=use_the_generated_key_above
WEBHOOK_RATE_LIMIT=60
WEBHOOK_ALLOWED_IPS=  # Leave empty to allow all
WEBHOOK_TIMEOUT_SECONDS=30
```

#### **TRADING CONFIGURATION**
```bash
# High Win Rate Mode (Conservative)
OPTIMIZE_FOR_WIN_RATE=true
HIGH_WIN_RATE_MODE=true
MAX_CONCURRENT_POSITIONS=10
RISK_PER_TRADE_PCT=2.0
MAX_DAILY_LOSS_PCT=6.0
MAX_POSITION_SIZE_PCT=10.0

# Trading Pairs
TRADING_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,DOGE/USDT

# Strategy Settings
MIN_WIN_RATE=0.65
MIN_TRADES_FOR_EVALUATION=20
STRATEGY_EVALUATION_PERIOD=7

# Optuna Optimization
OPTUNA_N_TRIALS=100        # 3-5 minutes
OPTUNA_N_JOBS=4            # Use 4 CPU cores
OPTUNA_TIMEOUT=300         # 5 minute timeout
MIN_BASELINE_TRADES=30
```

#### **APPLICATION CONFIGURATION**
```bash
# Generate a secure secret key
SECRET_KEY=$(openssl rand -hex 64)
echo "Your secret key: $SECRET_KEY"

# Set in .env:
APP_ENV=production
DEBUG=false
SECRET_KEY=use_the_generated_secret_above

# CORS - Update with your IP
CORS_ORIGINS=http://178.128.174.80:3000,http://178.128.174.80:8000
```

#### **SERVICE PORTS**
```bash
BACKEND_PORT=8000
FRONTEND_PORT=3000
POSTGRES_PORT=5432
REDIS_PORT=6379
PGADMIN_PORT=5050
```

#### **ALERT CONFIGURATION** (Optional but Recommended)
```bash
# Discord Alerts
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_URL
DISCORD_ALERTS_ENABLED=true

# Telegram Alerts
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
TELEGRAM_ALERTS_ENABLED=false

# Email Alerts
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_ALERTS_ENABLED=false
```

---

## Part 4: Create Required Directories

```bash
# Create necessary directories
mkdir -p logs
mkdir -p data
mkdir -p scripts

# Create database initialization script
cat > scripts/init_db.sql << 'EOF'
-- Initialize Andre Assassin Database
-- This file is automatically executed when PostgreSQL container starts

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "btree_gist";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create enum types
CREATE TYPE IF NOT EXISTS position_status AS ENUM ('open', 'closed', 'cancelled');
CREATE TYPE IF NOT EXISTS position_direction AS ENUM ('LONG', 'SHORT');
CREATE TYPE IF NOT EXISTS signal_source AS ENUM ('tradingview', 'manual', 'ai');
CREATE TYPE IF NOT EXISTS close_reason AS ENUM ('TP', 'SL', 'manual', 'trailing', 'timeout', 'error');

-- Main tables will be created by the application migrations
-- This script just ensures the database is ready

GRANT ALL PRIVILEGES ON DATABASE andre_assassin_db TO trading;
EOF

# Set proper permissions
chmod 644 scripts/init_db.sql
chmod -R 755 logs data
```

---

## Part 5: Database Initialization

### Understanding Database Setup
The database will be automatically initialized when you first start the Docker containers. The system will:
1. Create the PostgreSQL database
2. Run the initialization script
3. Apply all migrations
4. Create necessary tables and indexes

### Verify Database Schema (After First Run)
```bash
# Connect to database (after containers are running)
docker exec -it highwr_postgres psql -U trading -d andre_assassin_db

# List tables
\dt

# Should see tables like:
# - demo_positions
# - signals
# - strategies
# - optimization_history
# - signal_quality

# Exit PostgreSQL
\q
```

---

## Part 6: Docker Deployment

### Step 1: Build Docker Images
```bash
# Build all services (this takes 3-5 minutes)
docker compose build

# You should see:
# => Building backend...
# => Building frontend...
# Successfully built!
```

### Step 2: Start Services
```bash
# Start all services in detached mode
docker compose up -d

# You should see:
# Creating network "andre-assassin_trading_network"
# Creating highwr_postgres ... done
# Creating highwr_redis    ... done
# Creating highwr_backend  ... done
# Creating highwr_frontend ... done
```

### Step 3: Check Service Status
```bash
# Check if all containers are running
docker compose ps

# Should show:
# NAME                STATUS          PORTS
# highwr_postgres     Up (healthy)    0.0.0.0:5432->5432/tcp
# highwr_redis        Up (healthy)    0.0.0.0:6379->6379/tcp
# highwr_backend      Up (healthy)    0.0.0.0:8000->8000/tcp
# highwr_frontend     Up              0.0.0.0:3000->3000/tcp
```

### Step 4: View Logs
```bash
# View all logs
docker compose logs -f

# View specific service logs
docker compose logs -f backend
docker compose logs -f postgres

# Look for:
# backend  | INFO:     Application startup complete
# backend  | INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 5: Verify Health
```bash
# Check container health
docker ps --format "table {{.Names}}\t{{.Status}}"

# All containers should show "Up" and "healthy"
```

---

## Part 7: Verification

### Step 1: Check Backend Health
```bash
# From the server
curl http://localhost:8000/health

# Should return:
{
  "status": "healthy",
  "timestamp": "2025-11-10T12:00:00Z",
  "services": {
    "database": "connected",
    "redis": "connected",
    "bybit": "connected"
  }
}
```

### Step 2: Check From External
```bash
# From your local machine
curl http://178.128.174.80:8000/health

# Should return same health response
```

### Step 3: Check Frontend
```bash
# Open in browser
http://178.128.174.80:3000

# Should see the Andre Assassin dashboard
```

### Step 4: Check WebSocket Connection
```bash
# Test WebSocket endpoint
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: SGVsbG8sIHdvcmxkIQ==" \
  http://localhost:8000/ws

# Should return HTTP 101 Switching Protocols
```

### Step 5: Check Database Connection
```bash
# Test database connectivity
docker exec highwr_backend python -c "
from app.database.connection import test_connection
print(test_connection())
"

# Should return: Database connection successful
```

### Step 6: Check Redis Connection
```bash
# Test Redis
docker exec highwr_redis redis-cli ping

# Should return: PONG
```

---

## Part 8: TradingView Webhook Setup

### Webhook Configuration

#### **Webhook URL**
```
http://178.128.174.80:8000/api/webhook/tradingview
```

#### **Webhook JSON Format**
```json
{
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "price": "{{close}}",
  "time": "{{timenow}}",
  "alert_message": "{{strategy.order.comment}}",
  "api_key": "your_webhook_api_key_from_env"
}
```

### TradingView Alert Setup

1. **Open TradingView Chart**
   - Go to your strategy/indicator
   - Click on "Alerts" (clock icon)

2. **Create Alert**
   - Condition: Your strategy signal
   - Webhook URL: `http://178.128.174.80:8000/api/webhook/tradingview`
   - Message: Use the JSON format above

3. **Test with curl**
```bash
# Test webhook endpoint
curl -X POST http://178.128.174.80:8000/api/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "action": "buy",
    "price": "50000",
    "time": "2025-11-10 12:00:00",
    "alert_message": "Test signal",
    "api_key": "your_webhook_api_key"
  }'

# Expected response:
{
  "status": "success",
  "message": "Webhook received",
  "signal_id": "uuid-here"
}
```

### Verify Webhook Reception
```bash
# Check backend logs for webhook
docker compose logs -f backend | grep webhook

# Should see:
# INFO: Webhook received from TradingView
# INFO: Signal processed: BTCUSDT buy
```

### Common Webhook Response Codes
- **200**: Success - Signal received and processed
- **401**: Unauthorized - Check your API key
- **422**: Invalid data - Check JSON format
- **429**: Rate limited - Too many requests
- **500**: Server error - Check logs

---

## Part 9: Monitoring

### Real-Time Log Monitoring
```bash
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Last 100 lines
docker compose logs --tail=100 backend

# Errors only
docker compose logs -f backend 2>&1 | grep ERROR
```

### Dashboard Access

#### **Main Dashboard**
```
http://178.128.174.80:3000/dashboard
```
- View active positions
- Monitor P&L
- Check signal history
- View strategy performance

#### **Optuna Dashboard**
```
http://178.128.174.80:8080
```
- View optimization progress
- Check hyperparameter tuning
- Monitor trial results

### Database Monitoring (Optional - PgAdmin)
```bash
# Enable PgAdmin
docker compose --profile tools up -d pgadmin

# Access at:
http://178.128.174.80:5050

# Login:
Email: admin@andreassassin.com
Password: (from PGADMIN_PASSWORD in .env)

# Add server:
Host: postgres
Port: 5432
Database: andre_assassin_db
Username: trading
Password: (from POSTGRES_PASSWORD in .env)
```

### System Resource Monitoring
```bash
# Check Docker resource usage
docker stats

# Check disk space
df -h

# Check memory
free -h

# Monitor processes
htop
```

---

## Part 10: Common Commands

### Service Management
```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart all services
docker compose restart

# Restart specific service
docker compose restart backend

# Rebuild and restart
docker compose up -d --build

# Stop and remove everything (WARNING: removes data)
docker compose down -v
```

### Log Management
```bash
# View all logs
docker compose logs

# Follow logs in real-time
docker compose logs -f

# View specific service logs
docker compose logs backend
docker compose logs postgres
docker compose logs redis
docker compose logs frontend

# Save logs to file
docker compose logs > system_logs_$(date +%Y%m%d).txt
```

### Container Access
```bash
# Shell into backend container
docker compose exec backend bash

# Shell into database
docker compose exec postgres psql -U trading -d andre_assassin_db

# Shell into Redis
docker compose exec redis redis-cli

# Python shell in backend
docker compose exec backend python
```

### Backup Commands
```bash
# Backup database
docker compose exec postgres pg_dump -U trading andre_assassin_db > backup_$(date +%Y%m%d).sql

# Restore database
docker compose exec -T postgres psql -U trading andre_assassin_db < backup.sql

# Backup entire data directory
tar -czf andre_backup_$(date +%Y%m%d).tar.gz /opt/andre-assassin/data /opt/andre-assassin/logs
```

---

## Part 11: Troubleshooting

### Services Won't Start

#### **Problem**: Container fails to start
```bash
# Check logs
docker compose logs backend

# Common fixes:
# 1. Check .env file exists
ls -la .env

# 2. Verify environment variables
docker compose config

# 3. Check port conflicts
netstat -tulpn | grep -E '8000|3000|5432|6379'

# 4. Rebuild images
docker compose build --no-cache
docker compose up -d
```

### Database Connection Errors

#### **Problem**: "could not connect to database"
```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check database logs
docker compose logs postgres

# Test connection manually
docker compose exec postgres psql -U trading -d andre_assassin_db -c "SELECT 1;"

# Common fixes:
# 1. Wait for database to be ready (30-60 seconds after start)
# 2. Check POSTGRES_PASSWORD in .env
# 3. Restart database
docker compose restart postgres
```

### Webhook Not Receiving Data

#### **Problem**: TradingView webhooks not working
```bash
# Test webhook endpoint
curl -X POST http://localhost:8000/api/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"test": "data", "api_key": "your_key"}'

# Check firewall
ufw status

# Check backend logs
docker compose logs -f backend | grep webhook

# Common fixes:
# 1. Verify WEBHOOK_API_KEY matches
# 2. Check firewall allows port 8000
# 3. Ensure backend is running
```

### Optuna Dashboard Blank

#### **Problem**: Can't see Optuna dashboard
```bash
# Check if Optuna service is running
docker compose ps | grep optuna

# Start Optuna dashboard manually
docker run -d \
  --name optuna-dashboard \
  --network andre-assassin_trading_network \
  -p 8080:8080 \
  -e DATABASE_URL=postgresql://trading:password@postgres:5432/andre_assassin_db \
  optuna/optuna-dashboard

# Check logs
docker logs optuna-dashboard
```

### WebSocket Disconnected

#### **Problem**: Real-time updates not working
```bash
# Test WebSocket
wscat -c ws://localhost:8000/ws

# Check nginx configuration (if using)
docker compose exec frontend cat /etc/nginx/nginx.conf | grep -A5 "location /ws"

# Common fixes:
# 1. Restart backend
docker compose restart backend

# 2. Check CORS settings in .env
# 3. Clear browser cache
```

### High Memory Usage

#### **Problem**: System using too much memory
```bash
# Check memory usage
docker stats

# Limit container memory
# Edit docker-compose.yml and add:
#   deploy:
#     resources:
#       limits:
#         memory: 2G

# Restart containers
docker compose down
docker compose up -d

# Clear Redis cache
docker compose exec redis redis-cli FLUSHALL
```

### Disk Space Issues

#### **Problem**: Running out of disk space
```bash
# Check disk usage
df -h

# Find large files
du -sh /opt/andre-assassin/* | sort -h

# Clean Docker
docker system prune -af --volumes

# Clean logs
truncate -s 0 logs/*.log

# Remove old backups
rm -f backup_*.sql
```

---

## Part 12: Maintenance

### Daily Tasks
```bash
# Check system health
curl http://localhost:8000/health

# Check active positions
docker compose exec backend python -c "
from app.services.position_manager import get_active_positions
print(get_active_positions())
"

# Monitor logs for errors
docker compose logs --since 24h | grep ERROR
```

### Weekly Tasks
```bash
# Backup database
mkdir -p /backups
docker compose exec postgres pg_dump -U trading andre_assassin_db > /backups/weekly_$(date +%Y%m%d).sql

# Rotate logs
find /opt/andre-assassin/logs -name "*.log" -mtime +7 -delete

# Update optimization strategies
docker compose exec backend python -c "
from app.services.optuna_optimizer import run_optimization
run_optimization()
"
```

### Updating Code
```bash
# Backup current state
tar -czf backup_before_update_$(date +%Y%m%d).tar.gz /opt/andre-assassin

# Pull latest changes
cd /opt/andre-assassin
git pull origin main

# Rebuild and restart
docker compose down
docker compose build --no-cache
docker compose up -d

# Run migrations
docker compose exec backend python migrate.py

# Verify health
curl http://localhost:8000/health
```

### Emergency Procedures
```bash
# EMERGENCY STOP (closes all positions)
docker compose exec backend python -c "
from app.services.emergency import emergency_stop
emergency_stop()
"

# Backup everything immediately
tar -czf emergency_backup_$(date +%Y%m%d_%H%M%S).tar.gz /opt/andre-assassin

# Reset to clean state (WARNING: loses data)
docker compose down -v
docker compose up -d
```

---

## Part 13: Security Checklist

### Initial Security Setup
- [ ] Changed default PostgreSQL password
- [ ] Generated strong SECRET_KEY
- [ ] Generated secure WEBHOOK_API_KEY
- [ ] Configured firewall (UFW) with only necessary ports
- [ ] Disabled root SSH login (optional)
- [ ] Set up fail2ban for brute force protection

### API Security
- [ ] BYBIT_API_KEY has minimum required permissions
- [ ] API keys are not committed to git
- [ ] Webhook endpoint has authentication
- [ ] Rate limiting enabled
- [ ] CORS properly configured

### Database Security
- [ ] Strong PostgreSQL password (30+ characters)
- [ ] Database not exposed to internet (only localhost)
- [ ] Regular backups configured
- [ ] PgAdmin disabled in production

### Application Security
- [ ] DEBUG=false in production
- [ ] APP_ENV=production
- [ ] Alert notifications configured
- [ ] Error tracking enabled
- [ ] Logs not exposing sensitive data

### Network Security
- [ ] HTTPS configured (if using domain)
- [ ] Only required ports open in firewall
- [ ] Regular security updates applied
- [ ] Docker images regularly updated

---

## Part 14: Going Live

### Pre-Production Checklist
- [ ] System thoroughly tested on testnet
- [ ] All webhooks tested and working
- [ ] Backup procedures tested
- [ ] Alert channels configured and tested
- [ ] Risk parameters reviewed
- [ ] Win rate optimization completed

### Switch to Production
```bash
# Step 1: Stop system
docker compose down

# Step 2: Backup testnet data
tar -czf testnet_backup_$(date +%Y%m%d).tar.gz data/ logs/

# Step 3: Update .env for production
nano .env

# Change these values:
BYBIT_TESTNET=false
BYBIT_API_KEY=your_live_api_key
BYBIT_API_SECRET=your_live_api_secret
APP_ENV=production
DEBUG=false

# Step 4: Clear testnet data (optional)
rm -rf data/positions/*
rm -rf logs/*

# Step 5: Start in production mode
docker compose up -d

# Step 6: Verify production mode
docker compose exec backend python -c "
import os
print('Production Mode:', os.getenv('BYBIT_TESTNET') == 'false')
print('Environment:', os.getenv('APP_ENV'))
"
```

### Production Monitoring
```bash
# Set up monitoring script
cat > /opt/andre-assassin/monitor.sh << 'EOF'
#!/bin/bash
# Andre Assassin Health Monitor

check_health() {
    response=$(curl -s http://localhost:8000/health)
    if [[ $response != *"healthy"* ]]; then
        echo "ALERT: System unhealthy!"
        # Send alert (implement your notification here)
    fi
}

# Run every 5 minutes
while true; do
    check_health
    sleep 300
done
EOF

chmod +x /opt/andre-assassin/monitor.sh
nohup /opt/andre-assassin/monitor.sh &
```

### Final Smoke Test
```bash
# 1. Check all services running
docker compose ps

# 2. Verify production configuration
docker compose exec backend env | grep -E "BYBIT_TESTNET|APP_ENV|DEBUG"

# 3. Send test webhook
curl -X POST http://178.128.174.80:8000/api/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "action": "buy",
    "price": "50000",
    "alert_message": "Production test",
    "api_key": "your_production_webhook_key"
  }'

# 4. Check dashboard
# Open: http://178.128.174.80:3000

# 5. Monitor first real trade
docker compose logs -f backend
```

---

## Appendix A: Full Example .env

```bash
# ===============================================
# ANDRE ASSASSIN PRODUCTION CONFIGURATION
# ===============================================

# BYBIT CONFIGURATION
BYBIT_API_KEY=KxQz9mPqR8vN3wLt5y
BYBIT_API_SECRET=7hJ9kLmNpQrStVwXyZ2aBcDeFgHjKmNpQrS
BYBIT_TESTNET=false

# DATABASE CONFIGURATION
POSTGRES_USER=trading
POSTGRES_PASSWORD=Xk9$mP2@nQ8#vR5&tL3*wY7^zB4!hJ6
POSTGRES_DB=andre_assassin_db
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
DATABASE_URL=postgresql://trading:Xk9$mP2@nQ8#vR5&tL3*wY7^zB4!hJ6@postgres:5432/andre_assassin_db

# REDIS CONFIGURATION
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_URL=redis://redis:6379/0

# WEBHOOK CONFIGURATION
WEBHOOK_API_KEY=a7f8d9e2c4b6a1d3e5f7g9h2j4k6m8n0p2q4r6s8t0v2w4x6y8z0
WEBHOOK_RATE_LIMIT=60
WEBHOOK_ALLOWED_IPS=
WEBHOOK_TIMEOUT_SECONDS=30

# TRADING CONFIGURATION
OPTIMIZE_FOR_WIN_RATE=true
HIGH_WIN_RATE_MODE=true
MAX_CONCURRENT_POSITIONS=10
RISK_PER_TRADE_PCT=2.0
MAX_DAILY_LOSS_PCT=6.0
MAX_POSITION_SIZE_PCT=10.0
TRADING_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,DOGE/USDT,AVAX/USDT
MIN_WIN_RATE=0.65
MIN_TRADES_FOR_EVALUATION=20
STRATEGY_EVALUATION_PERIOD=7

# OPTUNA OPTIMIZATION
OPTUNA_N_TRIALS=100
OPTUNA_N_JOBS=4
OPTUNA_TIMEOUT=300
MIN_BASELINE_TRADES=30

# APPLICATION CONFIGURATION
APP_ENV=production
DEBUG=false
SECRET_KEY=9f8e7d6c5b4a3d2f1g0h9i8j7k6l5m4n3o2p1q0r9s8t7u6v5w4x3y2z1a0b9c8
CORS_ORIGINS=http://178.128.174.80:3000,http://178.128.174.80:8000

# SERVICE PORTS
BACKEND_PORT=8000
FRONTEND_PORT=3000
POSTGRES_PORT=5432
REDIS_PORT=6379
PGADMIN_PORT=5050

# FRONTEND CONFIGURATION
VITE_API_URL=http://backend:8000
VITE_WS_URL=ws://backend:8000/ws
VITE_PUBLIC_API_URL=http://178.128.174.80:8000
VITE_PUBLIC_WS_URL=ws://178.128.174.80:8000/ws
NODE_ENV=production

# PERFORMANCE SETTINGS
WORKERS=4
MAX_CONNECTIONS=100
CONNECTION_TIMEOUT=30
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60

# MONITORING & LOGGING
LOG_LEVEL=INFO
LOG_TO_FILE=true
LOG_FILE_PATH=/app/logs/app.log
LOG_MAX_SIZE_MB=100
LOG_BACKUP_COUNT=10
ENABLE_METRICS=true
METRICS_PORT=9090

# ALERT CONFIGURATION
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/1234567890/abcdefghijklmnop
DISCORD_ALERTS_ENABLED=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALERTS_ENABLED=false
EMAIL_ALERTS_ENABLED=false

# OPTIONAL SERVICES
ENABLE_PGADMIN=false
PGADMIN_EMAIL=admin@andreassassin.com
PGADMIN_PASSWORD=AdminPass123!@#
```

---

## Appendix B: Testing Webhook

### Basic Webhook Test
```bash
#!/bin/bash
# save as test_webhook.sh

WEBHOOK_URL="http://178.128.174.80:8000/api/webhook/tradingview"
API_KEY="your_webhook_api_key"

# Test BUY signal
curl -X POST $WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d "{
    \"symbol\": \"BTCUSDT\",
    \"action\": \"buy\",
    \"price\": \"50000\",
    \"time\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"alert_message\": \"Test BUY signal\",
    \"api_key\": \"$API_KEY\"
  }"

echo ""
sleep 2

# Test SELL signal
curl -X POST $WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d "{
    \"symbol\": \"BTCUSDT\",
    \"action\": \"sell\",
    \"price\": \"51000\",
    \"time\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"alert_message\": \"Test SELL signal\",
    \"api_key\": \"$API_KEY\"
  }"
```

### Advanced Webhook Test
```python
#!/usr/bin/env python3
# save as test_webhook.py

import requests
import json
from datetime import datetime

WEBHOOK_URL = "http://178.128.174.80:8000/api/webhook/tradingview"
API_KEY = "your_webhook_api_key"

def send_signal(symbol, action, price):
    payload = {
        "symbol": symbol,
        "action": action,
        "price": str(price),
        "time": datetime.utcnow().isoformat(),
        "alert_message": f"Test {action} signal for {symbol}",
        "api_key": API_KEY
    }

    response = requests.post(WEBHOOK_URL, json=payload)
    print(f"Sent {action} signal for {symbol}")
    print(f"Response: {response.status_code}")
    print(f"Body: {response.text}")
    print("-" * 50)
    return response

# Test multiple signals
signals = [
    ("BTCUSDT", "buy", 50000),
    ("ETHUSDT", "buy", 3000),
    ("SOLUSDT", "sell", 100),
    ("DOGEUSDT", "buy", 0.10),
]

for symbol, action, price in signals:
    send_signal(symbol, action, price)
```

---

## Appendix C: Quick Start (TL;DR)

For experienced users, here's the rapid deployment:

```bash
# 1. SSH into server
ssh root@178.128.174.80

# 2. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh

# 3. Clone repository
git clone https://github.com/andreoutberg/assassinbeta.git /opt/andre-assassin
cd /opt/andre-assassin

# 4. Configure environment
cp .env.example .env
# Edit .env with your API keys and passwords
nano .env

# 5. Create directories and init script
mkdir -p logs data scripts
cat > scripts/init_db.sql << 'EOF'
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
GRANT ALL PRIVILEGES ON DATABASE andre_assassin_db TO trading;
EOF

# 6. Start services
docker compose up -d

# 7. Check health
sleep 30
curl http://localhost:8000/health

# 8. Configure firewall
ufw allow 22,80,443,8000,3000,8080/tcp
ufw --force enable

# 9. Access dashboard
# http://178.128.174.80:3000

# 10. Send test webhook
curl -X POST http://178.128.174.80:8000/api/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSDT","action":"buy","price":"50000","api_key":"your_key"}'
```

---

## Support and Resources

### Documentation
- GitHub Repository: https://github.com/andreoutberg/assassinbeta
- API Documentation: http://178.128.174.80:8000/docs
- System Architecture: See ARCHITECTURE.md

### Common Issues Database
- Database migrations: Run `docker compose exec backend python migrate.py`
- WebSocket issues: Check CORS_ORIGINS in .env
- Memory issues: Adjust Docker resource limits
- Webhook failures: Verify API_KEY and firewall settings

### Getting Help
1. Check logs: `docker compose logs -f`
2. Check documentation in /docs folder
3. Review troubleshooting section
4. Check GitHub issues

### Emergency Contacts
- System Administrator: [Your contact]
- Trading Support: [Support contact]
- Technical Issues: [Tech contact]

---

## Final Notes

**Remember:**
- Always test on testnet first
- Keep your API keys secure
- Regular backups are essential
- Monitor your positions actively
- Start with small position sizes
- Review logs daily

**Success Indicators:**
- All containers show "healthy" status
- Dashboard accessible at http://178.128.174.80:3000
- Health endpoint returns all services connected
- Webhooks return 200 status codes
- No ERROR messages in logs

---

*Last Updated: November 10, 2025*
*Version: 0.1.1*
*Andre Assassin - High-WR Trading System*