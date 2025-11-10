# Andre Assassin - DigitalOcean Quick Start Guide

Optimized deployment guide for DigitalOcean Droplet:
- **IP:** 178.128.174.80
- **Specs:** 8 CPU, 16GB RAM, 320GB SSD
- **OS:** Ubuntu 22.04 LTS

## Prerequisites

This guide assumes you have:
- Root or sudo access to the droplet
- SSH key configured
- Domain name (optional, for SSL)

---

## 1. Initial Server Setup (5 minutes)

### Connect to Your Droplet
```bash
# From your local machine
ssh root@178.128.174.80

# Or with SSH key
ssh -i ~/.ssh/your_key root@178.128.174.80
```

### Create Non-Root User (Recommended)
```bash
# Create user
adduser andre

# Add to sudo group
usermod -aG sudo andre

# Copy SSH keys
rsync --archive --chown=andre:andre ~/.ssh /home/andre

# Switch to new user
su - andre
```

### Update System
```bash
# Update package lists and upgrade
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y \
    curl \
    wget \
    git \
    vim \
    htop \
    ufw \
    fail2ban \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release
```

---

## 2. Configure Firewall (3 minutes)

### Setup UFW (Uncomplicated Firewall)
```bash
# Set default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (IMPORTANT: Do this first!)
sudo ufw allow 22/tcp comment 'SSH'

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'

# Allow Grafana (optional, remove for production)
sudo ufw allow 3000/tcp comment 'Grafana'

# Allow Optuna Dashboard (optional, remove for production)
sudo ufw allow 8080/tcp comment 'Optuna'

# Allow Webhook endpoint (if exposed directly)
sudo ufw allow 8000/tcp comment 'Webhook API'

# Enable firewall
sudo ufw --force enable

# Check status
sudo ufw status verbose
```

### Configure Fail2ban (Optional but Recommended)
```bash
# Create jail.local
sudo tee /etc/fail2ban/jail.local << 'EOF'
[sshd]
enabled = true
port = 22
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600

[docker]
enabled = true
filter = docker
logpath = /var/log/docker.log
maxretry = 5
bantime = 3600
EOF

# Restart fail2ban
sudo systemctl restart fail2ban
sudo systemctl enable fail2ban
```

---

## 3. Install Docker (5 minutes)

### One-Command Docker Installation
```bash
# Official Docker installation script
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add current user to docker group
sudo usermod -aG docker $USER

# Apply group changes (or logout/login)
newgrp docker

# Verify installation
docker --version
docker compose version
```

### Configure Docker for Production
```bash
# Set Docker daemon options
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "iptables": true,
  "live-restore": true
}
EOF

# Restart Docker
sudo systemctl restart docker
```

---

## 4. Deploy Andre Assassin (10 minutes)

### Clone Repository
```bash
# Navigate to home directory
cd ~

# Clone the repository
git clone https://github.com/yourusername/andre-assassin.git
cd andre-assassin

# Or download from release
wget https://github.com/yourusername/andre-assassin/archive/v1.0.tar.gz
tar -xzf v1.0.tar.gz
cd andre-assassin-1.0
```

### Configure Environment
```bash
# Copy environment template
cp .env.example .env

# Generate secure passwords
POSTGRES_PASSWORD=$(openssl rand -base64 32)
REDIS_PASSWORD=$(openssl rand -base64 32)
SECRET_KEY=$(openssl rand -base64 48)

# Update .env file with secure values
cat > .env << EOF
# Database Configuration
POSTGRES_DB=andre_assassin
POSTGRES_USER=andre_admin
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_DB=0

# Application Settings
SECRET_KEY=${SECRET_KEY}
DEBUG=false
ALLOWED_HOSTS=178.128.174.80,localhost

# API Configuration
API_PORT=8000
WORKERS=4
WORKER_CONNECTIONS=1000
WORKER_CLASS=gevent
MAX_REQUESTS=1000
MAX_REQUESTS_JITTER=50

# Webhook Settings
WEBHOOK_SECRET=$(openssl rand -base64 32)
WEBHOOK_TIMEOUT=30
WEBHOOK_MAX_RETRIES=3

# Performance Tuning (Optimized for 16GB RAM)
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
REDIS_POOL_SIZE=50
REDIS_SOCKET_KEEPALIVE=true

# Resource Limits
CONTAINER_MEMORY_LIMIT=2g
CONTAINER_CPU_LIMIT=2

# Monitoring
ENABLE_GRAFANA=true
ENABLE_OPTUNA=true
GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 16)

# Timezone
TZ=UTC
EOF

echo "Environment configured with secure passwords!"
```

### Quick Deploy Script
```bash
# Create one-command deployment script
cat > quick_deploy.sh << 'SCRIPT'
#!/bin/bash
set -e

echo "Starting Andre Assassin deployment..."

# Create necessary directories
mkdir -p data/{postgres,redis,backups,logs,grafana,prometheus}

# Set permissions
chmod -R 755 data/

# Build and start services
docker compose build --no-cache
docker compose up -d

# Wait for services to be ready
echo "Waiting for services to start..."
sleep 15

# Check service health
docker compose ps

# Run database migrations (if applicable)
docker compose exec -T backend python manage.py migrate 2>/dev/null || true

# Display status
echo ""
echo "================================"
echo "Deployment Complete!"
echo "================================"
echo "Main Application: http://178.128.174.80"
echo "API Endpoint: http://178.128.174.80:8000"
echo "Grafana: http://178.128.174.80:3000"
echo "Optuna: http://178.128.174.80:8080"
echo ""
echo "Check status: docker compose ps"
echo "View logs: docker compose logs -f"
echo "================================"
SCRIPT

# Make executable and run
chmod +x quick_deploy.sh
./quick_deploy.sh
```

---

## 5. Post-Deployment Configuration (5 minutes)

### Set Up SSL with Let's Encrypt (Optional but Recommended)
```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com \
  --non-interactive --agree-tos --email your@email.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

### Configure Nginx Reverse Proxy
```bash
# Install Nginx
sudo apt install -y nginx

# Create configuration
sudo tee /etc/nginx/sites-available/andre-assassin << 'EOF'
server {
    listen 80;
    server_name 178.128.174.80;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Main application
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Webhook endpoint
    location /webhook {
        proxy_pass http://localhost:8000/webhook;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # Allow larger payloads for webhooks
        client_max_body_size 10M;
    }

    # Grafana
    location /grafana/ {
        proxy_pass http://localhost:3000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req zone=api burst=20 nodelay;
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/andre-assassin /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Set Up Monitoring
```bash
# Create monitoring script
cat > ~/monitor.sh << 'SCRIPT'
#!/bin/bash
# Simple monitoring script

while true; do
    clear
    echo "=== Andre Assassin Monitor ==="
    echo "Time: $(date)"
    echo ""

    # Service status
    echo "=== Services ==="
    docker compose ps
    echo ""

    # Resource usage
    echo "=== Resources ==="
    docker stats --no-stream
    echo ""

    # Disk usage
    echo "=== Disk Usage ==="
    df -h | grep -E '^/dev/|Filesystem'
    echo ""

    # Memory
    echo "=== Memory ==="
    free -h

    sleep 5
done
SCRIPT

chmod +x ~/monitor.sh
# Run with: ~/monitor.sh
```

### Configure Automated Backups
```bash
# Add to crontab
crontab -e

# Add these lines:
# Daily backup at 2 AM
0 2 * * * /home/andre/andre-assassin/scripts/backup.sh

# Weekly system update Sunday at 3 AM
0 3 * * 0 apt update && apt upgrade -y

# Clean Docker resources weekly
0 4 * * 0 docker system prune -a -f --volumes
```

---

## 6. Security Hardening (Optional)

### Additional Security Measures
```bash
# Disable root SSH login
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Enable automatic security updates
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades

# Set up log rotation
sudo tee /etc/logrotate.d/andre-assassin << 'EOF'
/home/andre/andre-assassin/data/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 640 andre andre
    sharedscripts
    postrotate
        docker compose restart backend >/dev/null 2>&1 || true
    endscript
}
EOF
```

---

## 7. Verification & Testing

### Run Complete Health Check
```bash
cd ~/andre-assassin
./scripts/health_check.sh
```

### Test Webhook Endpoint
```bash
./scripts/test_webhook.sh -u http://178.128.174.80:8000/webhook
```

### Performance Benchmark
```bash
# Install Apache Bench
sudo apt install -y apache2-utils

# Test API performance
ab -n 1000 -c 10 http://178.128.174.80:8000/health
```

---

## 8. Quick Commands Reference

```bash
# Service Management
docker compose up -d              # Start all services
docker compose down               # Stop all services
docker compose restart            # Restart all services
docker compose logs -f            # View logs
docker compose ps                 # Check status

# Backup & Restore
./scripts/backup.sh               # Create backup
./scripts/restore.sh backup.tar.gz # Restore from backup

# Monitoring
./scripts/health_check.sh         # Health check
docker stats                      # Resource usage
htop                             # System monitor

# Troubleshooting
docker compose logs backend -f    # Backend logs
docker exec -it postgres psql -U andre_admin  # Database console
docker exec -it redis redis-cli   # Redis console

# Updates
git pull                          # Update code
docker compose build --no-cache   # Rebuild images
docker compose up -d              # Deploy updates
```

---

## Optimization Tips for Your Droplet

Given your droplet's specifications (8 CPU, 16GB RAM):

### 1. Optimize PostgreSQL
```bash
# Edit PostgreSQL configuration
docker exec -it postgres bash
cat >> /var/lib/postgresql/data/postgresql.conf << EOF
# Optimized for 16GB RAM
shared_buffers = 4GB
effective_cache_size = 12GB
maintenance_work_mem = 1GB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
max_worker_processes = 8
max_parallel_workers_per_gather = 4
max_parallel_workers = 8
EOF
```

### 2. Optimize Redis
```bash
# Set Redis max memory
docker exec -it redis redis-cli CONFIG SET maxmemory 2gb
docker exec -it redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### 3. Enable Swap (Recommended)
```bash
# Create 8GB swap file
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Optimize swappiness
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

---

## Support & Troubleshooting

If you encounter issues:

1. Check the [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) guide
2. Review logs: `docker compose logs -f`
3. Run health check: `./scripts/health_check.sh`
4. Check DigitalOcean monitoring dashboard
5. Review droplet metrics in DigitalOcean control panel

---

## Estimated Total Setup Time: 25-30 minutes

Your Andre Assassin instance should now be running on your DigitalOcean droplet!

Access URLs:
- Main Application: http://178.128.174.80
- API Endpoint: http://178.128.174.80:8000
- Grafana Dashboard: http://178.128.174.80:3000
- Optuna Dashboard: http://178.128.174.80:8080

Remember to:
- Set up domain name and SSL certificate
- Configure webhook sources to point to your server
- Set up regular backups
- Monitor resource usage
- Keep the system updated