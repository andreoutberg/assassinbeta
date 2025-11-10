# Andre Assassin Deployment Checklist

## Pre-Deployment Requirements

### System Prerequisites
- [ ] Ubuntu 20.04+ or compatible Linux distribution
- [ ] Docker 20.10+ installed
- [ ] Docker Compose 2.0+ installed
- [ ] Git installed
- [ ] At least 10GB free disk space
- [ ] At least 4GB RAM available
- [ ] Python 3.9+ installed (for scripts)
- [ ] curl and wget installed

### Network Requirements
- [ ] Port 80 open for HTTP
- [ ] Port 443 open for HTTPS (if using SSL)
- [ ] Port 5432 accessible for PostgreSQL (internal)
- [ ] Port 6379 accessible for Redis (internal)
- [ ] Port 8000 accessible for backend API (internal)
- [ ] Port 3000 accessible for Grafana (optional)
- [ ] Port 8080 accessible for Optuna Dashboard (optional)

## Deployment Steps

### 1. Repository Setup
- [ ] Repository cloned to server
  ```bash
  git clone https://github.com/yourusername/andre-assassin.git
  cd andre-assassin
  ```
- [ ] Correct branch checked out
- [ ] Latest changes pulled

### 2. Environment Configuration
- [ ] `.env` file created from `.env.example`
- [ ] Database credentials configured
- [ ] Redis connection configured
- [ ] Secret keys generated
- [ ] Webhook URLs configured
- [ ] API tokens set (if applicable)
- [ ] Timezone configured
- [ ] Debug mode disabled for production

### 3. Directory Structure
- [ ] Data directories created:
  - [ ] `./data/postgres`
  - [ ] `./data/redis`
  - [ ] `./data/backups`
  - [ ] `./data/logs`
- [ ] Correct permissions set (755 for directories, 644 for files)
- [ ] Log rotation configured

### 4. Docker Setup
- [ ] Docker images built successfully
  ```bash
  docker-compose build --no-cache
  ```
- [ ] No build errors
- [ ] All images tagged correctly
- [ ] Old images cleaned up

### 5. Service Startup
- [ ] PostgreSQL container started and healthy
- [ ] Redis container started and healthy
- [ ] Backend API container started and healthy
- [ ] Nginx container started and healthy
- [ ] Optuna Dashboard container started (if enabled)
- [ ] Grafana container started (if enabled)
- [ ] All containers networked correctly

### 6. Database Setup
- [ ] Database migrations completed
- [ ] Initial data seeded (if applicable)
- [ ] Database connections verified
- [ ] Indexes created and optimized
- [ ] Database backup tested

### 7. Health Checks
- [ ] All services respond to health checks
- [ ] API endpoints return 200 OK
- [ ] Database queries execute successfully
- [ ] Redis operations work
- [ ] Webhook endpoint accessible
- [ ] Grafana dashboards load (if enabled)
- [ ] Optuna studies visible (if enabled)

### 8. Webhook Configuration
- [ ] Webhook endpoint tested with sample data
- [ ] Webhook authentication working
- [ ] Webhook processing verified in logs
- [ ] Rate limiting configured
- [ ] Error handling tested

### 9. Monitoring & Alerts
- [ ] Grafana dashboards configured
- [ ] Alert rules created
- [ ] Notification channels configured
- [ ] Log aggregation working
- [ ] Metrics being collected
- [ ] Health check endpoint monitored

### 10. Security
- [ ] Firewall rules configured
- [ ] SSL certificates installed (if applicable)
- [ ] Secure headers configured in Nginx
- [ ] Database access restricted
- [ ] API rate limiting enabled
- [ ] Secrets properly managed
- [ ] CORS settings configured

### 11. Backup & Recovery
- [ ] Backup script scheduled (cron)
- [ ] Backup location configured
- [ ] Backup retention policy set
- [ ] Recovery procedure tested
- [ ] Backup notifications configured

### 12. Performance
- [ ] Resource limits set for containers
- [ ] Database connection pooling configured
- [ ] Redis maxmemory policy set
- [ ] Nginx caching configured
- [ ] Application logging optimized

## Post-Deployment Verification

### Functional Tests
- [ ] Can receive and process webhooks
- [ ] Database operations work correctly
- [ ] API responds to all endpoints
- [ ] Authentication/authorization working
- [ ] Data persistence verified

### Performance Tests
- [ ] Response times acceptable (<500ms)
- [ ] Can handle expected load
- [ ] Memory usage stable
- [ ] CPU usage reasonable
- [ ] No memory leaks detected

### Monitoring Verification
- [ ] Metrics visible in Grafana
- [ ] Logs accessible and readable
- [ ] Alerts trigger correctly
- [ ] Health checks passing

## Production Ready
- [ ] All critical checks passed
- [ ] Documentation updated
- [ ] Team notified
- [ ] Rollback plan documented
- [ ] Support contacts listed
- [ ] **Ready for production traffic**

## Sign-off
- [ ] Technical Lead approval
- [ ] Operations approval
- [ ] Security review completed
- [ ] Deployment documented

---

## Quick Verification Commands

```bash
# Check all services
docker-compose ps

# Check logs
docker-compose logs --tail=50

# Run health check
./scripts/health_check.sh

# Test webhook
./scripts/test_webhook.sh

# Check resource usage
docker stats --no-stream
```

## Emergency Contacts
- Technical Lead: _________________
- DevOps: _________________
- On-call: _________________

## Notes
_Add any deployment-specific notes here_

---

**Deployment Date:** _________________
**Deployed By:** _________________
**Version:** _________________