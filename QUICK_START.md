# 🚀 Quick Start Guide - From Zero to Trading in 5 Minutes!

Welcome to AssassinBeta! This guide will help you get your automated trading system running in just 5 simple steps. No prior technical experience required!

## 📋 Prerequisites

Before we begin, you'll need:

✅ **A computer with internet** (or cloud server)
✅ **$6/month for hosting** (DigitalOcean droplet - optional, can run locally)
✅ **Bybit account** (free testnet account for practice)
✅ **TradingView account** (free account is fine)
✅ **Basic ability to copy/paste commands** (we'll guide you!)

---

## 📍 Step 1: Get a Digital Ocean Droplet ($6/month)

> 💡 **Note:** You can also run this on your own computer for testing. Skip to Step 2 if running locally.

### 1.1 Create Your Server

1. **Sign up at DigitalOcean** → [Get $200 free credit](https://www.digitalocean.com/try)
2. Click **"Create Droplet"**
3. Choose these settings:
   - **Region:** Choose closest to you
   - **Image:** Ubuntu 22.04 LTS
   - **Size:** Basic → Regular → **$6/month** (1 GB RAM, 1 CPU)
   - **Authentication:** Password (easier for beginners)

[SCREENSHOT: DigitalOcean droplet creation page with $6 option selected]

4. Click **"Create Droplet"** and wait 1 minute
5. You'll receive an IP address like `164.90.145.32`

### 1.2 Connect to Your Server

**Windows Users:**
```bash
# Download PuTTY: https://putty.org
# Enter your IP address and click "Open"
# Login as: root
# Password: (the one you created)
```

**Mac/Linux Users:**
```bash
ssh root@YOUR_IP_ADDRESS
# Enter password when prompted
```

[SCREENSHOT: Terminal showing successful SSH connection]

---

## ⚡ Step 2: Run Installation Command

Once connected to your server (or in your local terminal), run this single command:

```bash
curl -sSL https://raw.githubusercontent.com/andreoutberg/assassinbeta/main/install.sh | bash
```

This magical command will:
- ✅ Install Python, PostgreSQL, Redis, and all dependencies
- ✅ Set up the database with proper tables
- ✅ Configure the system environment
- ✅ Start the trading system automatically
- ✅ Set up PM2 for process management

**Expected output:**
```
🚀 AssassinBeta Installer v0.1
================================
✅ Installing system dependencies...
✅ Setting up Python environment...
✅ Configuring PostgreSQL database...
✅ Installing AssassinBeta...
✅ Starting services...

🎉 Installation Complete!
Dashboard: http://YOUR_IP:8000
Logs: pm2 logs assassin-beta
```

[SCREENSHOT: Installation process completing successfully]

---

## 🔑 Step 3: Configure Bybit Testnet

Let's set up your **FREE** Bybit testnet account for paper trading:

### 3.1 Create Testnet Account

1. Go to → [testnet.bybit.com](https://testnet.bybit.com)
2. Click **"Register"** and create account
3. **Important:** This is NOT real money - perfect for learning!

### 3.2 Get API Keys

1. Click your profile → **"API"**
2. Click **"Create New Key"**
3. Settings:
   - **Name:** AssassinBeta
   - **Permissions:** ✅ Read, ✅ Trade
   - **IP restriction:** Your server's IP (from Step 1)
4. **SAVE THESE SAFELY:**
   - API Key: `xxxxx-xxxxx-xxxxx`
   - Secret Key: `xxxxx-xxxxx-xxxxx`

[SCREENSHOT: Bybit API key creation page with correct permissions]

### 3.3 Add Keys to AssassinBeta

```bash
# On your server, edit the config
nano /root/assassinbeta/.env

# Add your keys (replace xxx with actual keys):
BYBIT_API_KEY=xxxxx-xxxxx-xxxxx
BYBIT_SECRET_KEY=xxxxx-xxxxx-xxxxx
BYBIT_TESTNET=true

# Save: Ctrl+O, Enter, Ctrl+X

# Restart system to load new keys
pm2 restart assassin-beta
```

---

## 🖥️ Step 4: Open Dashboard

Your trading dashboard is now live! Open your browser and visit:

```
http://YOUR_SERVER_IP:8000
```

You should see:
- 📊 **Live Trading Panel** - Current positions and P&L
- 📈 **Strategy Performance** - Win rates and risk/reward ratios
- 🔄 **Phase Status** - Which phase each asset is in
- 📉 **Real-time Charts** - Live price action (WebSocket)

[SCREENSHOT: Dashboard overview showing all panels]

### Dashboard Features:

| Section | Description | What to Look For |
|---------|-------------|------------------|
| **Active Trades** | Live positions | Green = profit, Red = loss |
| **Phase Monitor** | System evolution status | Phase I → II → III progression |
| **Strategy Metrics** | Performance stats | WR% > 50%, RR > 1.0 is good |
| **WebSocket Status** | Connection health | Should show "Connected" |

---

## 🎮 Step 5: Start Demo Trading

### 5.1 Configure TradingView Webhook

1. Open [TradingView.com](https://tradingview.com)
2. Create/Open a chart (any crypto pair)
3. Add an indicator (example: RSI)
4. Click indicator → "Create Alert"
5. Alert Settings:
   ```
   Webhook URL: http://YOUR_SERVER_IP:8000/webhook/tradingview

   Message (copy exactly):
   {
     "symbol": "{{ticker}}",
     "direction": "{{strategy.order.action}}",
     "price": {{close}},
     "source": "tradingview_rsi"
   }
   ```

[SCREENSHOT: TradingView alert configuration with webhook]

### 5.2 Monitor Your First Trade

Watch the magic happen:

1. **Alert Triggered** → TradingView sends signal
2. **Phase Detection** → System determines current phase
3. **Strategy Selection** → AI picks best strategy
4. **Trade Execution** → Position opened on Bybit testnet
5. **Live Monitoring** → Dashboard updates in real-time

```bash
# Watch live logs to see the process:
pm2 logs assassin-beta --lines 50

# You'll see:
[INFO] Webhook received: BTCUSDT LONG
[INFO] Phase I detected - collecting baseline data
[INFO] Trade created: ID 1234, Entry: 65432.10
[INFO] WebSocket tracking prices...
```

---

## 🐛 Troubleshooting Common Issues

### Issue: "Connection Refused" on Dashboard

**Solution:**
```bash
# Check if service is running
pm2 status

# If not running:
pm2 start ecosystem.config.js

# Check firewall
ufw allow 8000
```

### Issue: "No Trades Appearing"

**Solution:**
```bash
# Check webhook is receiving signals
tail -f /root/assassinbeta/logs/webhook.log

# Verify database connection
pm2 logs assassin-beta | grep -i error

# Test webhook manually
curl -X POST http://localhost:8000/webhook/test \
  -H "Content-Type: application/json" \
  -d '{"test": "signal"}'
```

### Issue: "Database Connection Error"

**Solution:**
```bash
# Restart PostgreSQL
systemctl restart postgresql

# Check database exists
sudo -u postgres psql -c "\l"

# Recreate if needed
cd /root/assassinbeta
python scripts/setup_database.py
```

### Issue: "WebSocket Disconnected"

**Solution:**
```bash
# Restart price tracker
pm2 restart assassin-price-tracker

# Check connection count
netstat -an | grep 8000 | wc -l

# Clear stuck connections
pm2 restart all
```

---

## 🎯 Next Steps

Congratulations! Your AssassinBeta system is now running. Here's what to do next:

### Week 1: Learning Phase
- ✅ Watch the system collect baseline data (Phase I)
- ✅ Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand how it works
- ✅ Monitor dashboard daily to see patterns

### Week 2: Optimization Phase
- ✅ See Phase II activate (after 10 baseline trades)
- ✅ Watch strategy validation in action
- ✅ Review performance metrics

### Week 3: Profit Phase
- ✅ Phase III activation for top performers
- ✅ Compare testnet results
- ✅ Consider live trading setup

### Advanced Configuration

Once comfortable, explore:
- 🔧 [Custom Strategies](docs/CUSTOM_STRATEGIES.md)
- 📊 [Advanced Analytics](docs/ANALYTICS.md)
- 🤖 [AI Integration](docs/AI_SETUP.md)
- 💰 [Live Trading Migration](docs/GO_LIVE.md)

---

## 📚 Resources

- **Video Tutorial:** [YouTube - Complete Setup](https://youtube.com/assassinbeta)
- **Discord Community:** [Join 5000+ traders](https://discord.gg/assassinbeta)
- **Documentation:** [Full Docs](https://docs.assassinbeta.com)
- **Support:** support@assassinbeta.com

---

## 🎉 Success Checklist

Make sure you've completed everything:

- [ ] Server/computer ready
- [ ] AssassinBeta installed
- [ ] Bybit testnet API configured
- [ ] Dashboard accessible
- [ ] TradingView webhook connected
- [ ] First test trade executed
- [ ] Logs showing no errors
- [ ] Phase I data collection started

---

<div align="center">
  <h3>🚀 You're Now Running AssassinBeta!</h3>
  <p>
    Join our community to share your results and get help<br>
    <a href="https://discord.gg/assassinbeta">Discord</a> •
    <a href="https://twitter.com/assassinbeta">Twitter</a> •
    <a href="https://github.com/andreoutberg/assassinbeta">GitHub</a>
  </p>
</div>