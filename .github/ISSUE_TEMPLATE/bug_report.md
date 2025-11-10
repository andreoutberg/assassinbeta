---
name: 🐛 Bug Report
about: Create a report to help us improve AssassinBeta
title: '[BUG] '
labels: 'bug, needs-triage'
assignees: ''
---

## 🐛 Bug Description
<!-- A clear and concise description of what the bug is -->

## 📋 To Reproduce
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '...'
3. Execute command '...'
4. See error

## ✅ Expected Behavior
<!-- A clear and concise description of what you expected to happen -->

## 📸 Screenshots
<!-- If applicable, add screenshots to help explain your problem -->
[SCREENSHOT: Add your screenshot here]

## 🖥️ Environment
Please complete the following information:

**System Info:**
- OS: [e.g., Ubuntu 22.04]
- Python Version: [e.g., 3.12.1]
- AssassinBeta Version: [e.g., v0.1]
- Installation Method: [Docker/Manual/Script]

**Trading Environment:**
- Exchange: [Bybit Testnet/Mainnet]
- TradingView: [Free/Pro/Premium]
- Number of Active Trades: [e.g., 100]
- Current Phase Distribution: [e.g., Phase I: 50, Phase II: 10, Phase III: 0]

## 📝 Logs
<!-- Please include relevant logs -->

<details>
<summary>Error Logs</summary>

```
Paste your error logs here
Use: pm2 logs assassin-beta --lines 100
```

</details>

<details>
<summary>Database Query Results</summary>

```sql
-- Include any relevant database queries
-- Example: SELECT * FROM trade_setups WHERE status = 'error' LIMIT 5;
```

</details>

## 🔧 Additional Context
<!-- Add any other context about the problem here -->

### Have you tried?
- [ ] Restarting the system (`pm2 restart assassin-beta`)
- [ ] Checking database connections
- [ ] Verifying API keys are correct
- [ ] Looking at similar issues

### Impact
- [ ] 🔴 Critical - System is down
- [ ] 🟠 High - Major feature broken
- [ ] 🟡 Medium - Minor feature affected
- [ ] 🟢 Low - Cosmetic issue

---
<!-- Thank you for contributing to AssassinBeta! -->