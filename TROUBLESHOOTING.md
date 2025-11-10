# Andre Assassin Troubleshooting Guide

This guide covers common issues and their solutions when deploying and running Andre Assassin.

## Table of Contents
1. [Services Won't Start](#services-wont-start)
2. [Database Connection Failed](#database-connection-failed)
3. [Out of Memory](#out-of-memory)
4. [Disk Full](#disk-full)
5. [Webhook Not Received](#webhook-not-received)
6. [Grafana Not Accessible](#grafana-not-accessible)
7. [How to Read Logs](#how-to-read-logs)
8. [How to Restart Services](#how-to-restart-services)
9. [Common Docker Issues](#common-docker-issues)
10. [Performance Issues](#performance-issues)

---

## Services Won't Start

### Problem
One or more Docker containers fail to start or keep restarting.

### Diagnostics
```bash
# Check container status
docker-compose ps

# Check container logs
docker-compose logs [service_name]

# Check recent events
docker events --since 10m
```

### Common Causes and Solutions

#### 1. Port Already in Use
**Error:** `bind: address already in use`

**Solution:**
```bash
# Find what's using the port
sudo lsof -i :PORT_NUMBER

# Kill the process
sudo kill -9 PID

# Or change the port in docker-compose.yml
```

#### 2. Missing Environment Variables
**Error:** `KeyError` or `environment variable not set`

**Solution:**
```bash
# Check .env file exists
ls -la .env

# Copy from example if missing
cp .env.example .env

# Edit and fill in required values
nano .env
```

#### 3. Incorrect File Permissions
**Error:** `Permission denied`

**Solution:**
```bash
# Fix directory permissions
sudo chown -R $USER:$USER ./data
chmod -R 755 ./data
```

#### 4. Docker Daemon Not Running
**Error:** `Cannot connect to the Docker daemon`

**Solution:**
```bash
# Start Docker
sudo systemctl start docker

# Enable Docker on boot
sudo systemctl enable docker

# Check Docker status
sudo systemctl status docker
```

---

## Database Connection Failed

### Problem
Application cannot connect to PostgreSQL database.

### Diagnostics
```bash
# Test database connection
docker exec postgres pg_isready -U postgres

# Check PostgreSQL logs
docker logs postgres --tail 50

# Try connecting manually
docker exec -it postgres psql -U postgres
```

### Common Causes and Solutions

#### 1. Database Not Initialized
**Solution:**
```bash
# Initialize database
docker-compose down -v
docker-compose up -d postgres
sleep 10
docker-compose up -d
```

#### 2. Wrong Credentials
**Solution:**
```bash
# Check credentials in .env
grep POSTGRES .env

# Ensure they match in all services
# Update docker-compose.yml if needed
```

#### 3. Network Issues
**Solution:**
```bash
# Recreate network
docker-compose down
docker network prune -f
docker-compose up -d
```

#### 4. Database Corruption
**Solution:**
```bash
# Backup current data
docker exec postgres pg_dump -U postgres dbname > backup.sql

# Reset database
docker-compose down -v
docker-compose up -d postgres
docker exec -i postgres psql -U postgres < backup.sql
```

---

## Out of Memory

### Problem
Containers crash with OOM (Out of Memory) errors.

### Diagnostics
```bash
# Check memory usage
free -h
docker stats --no-stream

# Check system logs
dmesg | grep -i "killed process"
journalctl -u docker --since "1 hour ago" | grep -i oom
```

### Solutions

#### 1. Increase Swap Space
```bash
# Create swap file (4GB)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

#### 2. Limit Container Memory
Edit `docker-compose.yml`:
```yaml
services:
  backend:
    mem_limit: 2g
    memswap_limit: 2g
```

#### 3. Optimize Application
```bash
# Reduce worker processes
# Edit .env
WORKERS=2  # Instead of 4

# Reduce database connections
MAX_CONNECTIONS=50  # Instead of 100
```

#### 4. Clean Docker Resources
```bash
# Remove unused containers, images, volumes
docker system prune -a --volumes

# Remove specific large images
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
docker rmi IMAGE_ID
```

---

## Disk Full

### Problem
No space left on device errors.

### Diagnostics
```bash
# Check disk usage
df -h
du -sh /var/lib/docker
du -sh ./data/*
```

### Solutions

#### 1. Clean Docker System
```bash
# Complete cleanup
docker system prune -a --volumes -f

# Clean build cache
docker builder prune -a -f
```

#### 2. Clean Logs
```bash
# Truncate container logs
truncate -s 0 $(docker inspect --format='{{.LogPath}}' CONTAINER_NAME)

# Rotate logs
docker-compose logs --tail 0 > /dev/null

# Clean system logs
sudo journalctl --vacuum-time=7d
```

#### 3. Remove Old Backups
```bash
# Keep only last 7 days of backups
find ./data/backups -type f -mtime +7 -delete
```

#### 4. Move Data to Larger Disk
```bash
# Stop services
docker-compose down

# Move Docker root
sudo systemctl stop docker
sudo mv /var/lib/docker /new/path/docker
sudo ln -s /new/path/docker /var/lib/docker
sudo systemctl start docker
```

---

## Webhook Not Received

### Problem
Webhooks are not being processed or received.

### Diagnostics
```bash
# Test webhook endpoint
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'

# Check backend logs
docker logs backend --tail 100 | grep -i webhook

# Check nginx access logs
docker logs nginx --tail 100
```

### Common Causes and Solutions

#### 1. Firewall Blocking
```bash
# Check firewall rules
sudo ufw status

# Allow webhook port
sudo ufw allow 8000/tcp
sudo ufw reload
```

#### 2. Incorrect URL Configuration
```bash
# Check webhook URL in source system
# Should be: http://YOUR_SERVER_IP:8000/webhook

# Test from external network
curl -X POST http://YOUR_EXTERNAL_IP:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "external"}'
```

#### 3. Authentication Issues
```bash
# Check if authentication is required
grep WEBHOOK_SECRET .env

# Test with authentication
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_SECRET" \
  -d '{"test": "auth"}'
```

#### 4. Rate Limiting
```bash
# Check rate limit settings
grep RATE_LIMIT .env

# Increase or disable for testing
RATE_LIMIT=1000  # requests per minute
```

---

## Grafana Not Accessible

### Problem
Cannot access Grafana dashboard at port 3000.

### Diagnostics
```bash
# Check if Grafana is running
docker ps | grep grafana

# Check Grafana logs
docker logs grafana --tail 50

# Test connection
curl -I http://localhost:3000
```

### Solutions

#### 1. Container Not Running
```bash
# Start Grafana
docker-compose up -d grafana

# Check status
docker-compose ps grafana
```

#### 2. Permission Issues
```bash
# Fix Grafana data directory permissions
sudo chown -R 472:472 ./data/grafana
```

#### 3. Configuration Issues
```bash
# Reset Grafana
docker-compose stop grafana
rm -rf ./data/grafana/*
docker-compose up -d grafana

# Default login: admin/admin
```

#### 4. Port Conflict
```bash
# Change port in docker-compose.yml
ports:
  - "3001:3000"  # Use 3001 instead
```

---

## How to Read Logs

### Viewing Logs

#### All Services
```bash
# Follow all logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail 100
```

#### Specific Service
```bash
# Backend logs
docker logs backend -f

# PostgreSQL logs
docker logs postgres --tail 50

# Redis logs
docker logs redis --tail 50
```

#### Filter Logs
```bash
# Search for errors
docker-compose logs | grep -i error

# Search for specific timestamp
docker-compose logs | grep "2024-01-15"

# Search in specific service
docker logs backend | grep -i "webhook"
```

### Log Locations

**Container Logs:**
```bash
# Find log location
docker inspect CONTAINER_NAME | grep LogPath

# View directly
sudo cat /var/lib/docker/containers/CONTAINER_ID/CONTAINER_ID-json.log
```

**Application Logs:**
```bash
# Inside data directory
ls -la ./data/logs/

# View application log
tail -f ./data/logs/app.log
```

### Understanding Log Levels

- **DEBUG:** Detailed information for diagnosing problems
- **INFO:** General informational messages
- **WARNING:** Warning messages about potential issues
- **ERROR:** Error messages that need attention
- **CRITICAL:** Critical issues that may cause service failure

---

## How to Restart Services

### Restart All Services
```bash
# Graceful restart
docker-compose restart

# Stop and start
docker-compose down
docker-compose up -d
```

### Restart Specific Service
```bash
# Restart backend only
docker-compose restart backend

# Force recreate
docker-compose up -d --force-recreate backend
```

### Hard Reset
```bash
# Complete reset (WARNING: Deletes data)
docker-compose down -v
docker-compose up -d
```

### Rolling Restart (Zero Downtime)
```bash
# Scale up
docker-compose up -d --scale backend=2

# Wait for new instance
sleep 30

# Scale down
docker-compose up -d --scale backend=1
```

---

## Common Docker Issues

### Docker Compose Version Issues
```bash
# Check version
docker-compose --version

# Update Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### Container Name Conflicts
```bash
# Remove old containers
docker rm -f $(docker ps -aq)

# Or rename in docker-compose.yml
container_name: andre_assassin_backend_v2
```

### Image Pull Errors
```bash
# Login to registry if needed
docker login

# Pull manually
docker pull postgres:14
docker pull redis:7-alpine

# Build with no cache
docker-compose build --no-cache
```

### Network Issues
```bash
# List networks
docker network ls

# Remove unused networks
docker network prune -f

# Create custom network
docker network create andre_network
```

---

## Performance Issues

### Slow Response Times

#### Diagnose
```bash
# Check resource usage
docker stats

# Check database query performance
docker exec postgres psql -U postgres -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

#### Optimize
```bash
# Increase database connections
# Edit .env
DB_POOL_SIZE=20

# Add indexes
docker exec postgres psql -U postgres -d dbname -c "CREATE INDEX idx_name ON table(column);"

# Enable caching
REDIS_CACHE_TTL=3600
```

### High CPU Usage

#### Diagnose
```bash
# Top processes in container
docker exec backend top

# System load
uptime
htop
```

#### Fix
```bash
# Limit CPU usage
# Edit docker-compose.yml
services:
  backend:
    cpus: '2.0'

# Reduce workers
WORKERS=2
```

### Memory Leaks

#### Diagnose
```bash
# Monitor memory over time
while true; do docker stats --no-stream; sleep 60; done

# Check for growing processes
docker exec backend ps aux --sort=-%mem | head
```

#### Fix
```bash
# Set memory limits
# Edit docker-compose.yml
services:
  backend:
    mem_limit: 2g
    restart: unless-stopped

# Enable automatic restart on OOM
```

---

## Emergency Procedures

### Complete System Recovery
```bash
#!/bin/bash
# Emergency recovery script

# 1. Stop everything
docker-compose down

# 2. Backup current state
tar -czf emergency_backup_$(date +%Y%m%d_%H%M%S).tar.gz ./data .env docker-compose.yml

# 3. Clean Docker system
docker system prune -a -f --volumes

# 4. Restore from last known good backup
tar -xzf ./data/backups/last_known_good.tar.gz

# 5. Restart services
docker-compose up -d

# 6. Verify services
./scripts/health_check.sh
```

### Contact Support

If issues persist after trying these solutions:

1. Collect diagnostic information:
```bash
# Generate diagnostic report
docker-compose ps > diagnostic_report.txt
docker-compose logs --tail 1000 >> diagnostic_report.txt
df -h >> diagnostic_report.txt
free -h >> diagnostic_report.txt
```

2. Check documentation:
- README.md
- DEPLOYMENT_CHECKLIST.md
- Project wiki/documentation

3. Contact technical support with:
- Diagnostic report
- Error messages
- Steps to reproduce
- Environment details

---

## Quick Reference Commands

```bash
# Status check
docker-compose ps

# View logs
docker-compose logs -f

# Restart service
docker-compose restart [service]

# Run health check
./scripts/health_check.sh

# Test webhook
./scripts/test_webhook.sh

# Create backup
./scripts/backup.sh

# Clean system
docker system prune -a

# Check resources
docker stats
df -h
free -h
```

---

Remember: Always backup your data before performing major troubleshooting steps!