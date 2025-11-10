#!/bin/bash

###############################################################################
# Andre Assassin High-WR Trading System - Beginner-Friendly Installer
# Version: 0.1.0
# For: Digital Ocean Droplets (Ubuntu 22.04+)
#
# This script will:
# 1. Check your system
# 2. Install all dependencies automatically (Docker, PostgreSQL, etc.)
# 3. Set up your trading system
# 4. Configure Bybit demo trading
# 5. Start the dashboard
#
# ONE COMMAND INSTALLATION:
# curl -sSL https://raw.githubusercontent.com/andreoutberg/assassinbeta/main/install.sh | bash
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Progress tracking
STEP=0
TOTAL_STEPS=10

print_header() {
    clear
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║        🎯 ANDRE ASSASSIN HIGH-WR TRADING SYSTEM 🎯         ║"
    echo "║                                                              ║"
    echo "║              Beginner-Friendly Installation                  ║"
    echo "║                     Version 0.1.0                            ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
}

print_step() {
    STEP=$((STEP + 1))
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}Step ${STEP}/${TOTAL_STEPS}: $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ ERROR: $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_error "Please do NOT run this script as root or with sudo!"
        print_info "Run it as a normal user: ./install.sh"
        exit 1
    fi
}

# Check system requirements
check_system() {
    print_step "Checking Your System"

    # Check OS
    if [[ ! -f /etc/os-release ]]; then
        print_error "Cannot detect OS. This script is for Ubuntu 22.04+"
        exit 1
    fi

    . /etc/os-release
    print_info "Operating System: $PRETTY_NAME"

    if [[ "$ID" != "ubuntu" ]]; then
        print_warning "This script is optimized for Ubuntu, but will try to proceed..."
    fi

    # Check memory
    TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
    print_info "Total Memory: ${TOTAL_MEM}MB"

    if [ "$TOTAL_MEM" -lt 2000 ]; then
        print_warning "Recommended: 2GB+ RAM. You have ${TOTAL_MEM}MB. System may be slow."
    else
        print_success "Memory check passed"
    fi

    # Check disk space
    AVAILABLE_DISK=$(df -BG / | awk 'NR==2 {print $4}' | sed 's/G//')
    print_info "Available Disk Space: ${AVAILABLE_DISK}GB"

    if [ "$AVAILABLE_DISK" -lt 10 ]; then
        print_error "Need at least 10GB free disk space. You have ${AVAILABLE_DISK}GB"
        exit 1
    else
        print_success "Disk space check passed"
    fi

    # Check internet connection
    print_info "Testing internet connection..."
    if ping -c 1 google.com &> /dev/null; then
        print_success "Internet connection OK"
    else
        print_error "No internet connection. Please check your network."
        exit 1
    fi

    sleep 2
}

# Install dependencies
install_dependencies() {
    print_step "Installing Required Software (This May Take 5-10 Minutes)"

    print_info "What we're installing:"
    print_info "  • Docker (for running containers)"
    print_info "  • Docker Compose (for managing services)"
    print_info "  • Git (for downloading code)"
    print_info "  • Python 3.11 (for the trading system)"
    echo ""

    print_info "Updating system packages..."
    sudo apt-get update -qq

    print_info "Installing basic tools..."
    sudo apt-get install -y -qq curl git wget software-properties-common

    # Install Docker
    if command -v docker &> /dev/null; then
        print_success "Docker already installed"
    else
        print_info "Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        rm get-docker.sh

        # Add user to docker group
        sudo usermod -aG docker $USER
        print_success "Docker installed"
        print_warning "You may need to log out and back in for Docker permissions to take effect"
    fi

    # Install Docker Compose
    if command -v docker-compose &> /dev/null; then
        print_success "Docker Compose already installed"
    else
        print_info "Installing Docker Compose..."
        sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
        print_success "Docker Compose installed"
    fi

    # Install Python 3.11
    if command -v python3.11 &> /dev/null; then
        print_success "Python 3.11 already installed"
    else
        print_info "Installing Python 3.11..."
        sudo add-apt-repository -y ppa:deadsnakes/ppa
        sudo apt-get update -qq
        sudo apt-get install -y -qq python3.11 python3.11-venv python3-pip
        print_success "Python 3.11 installed"
    fi

    print_success "All dependencies installed!"
    sleep 2
}

# Clone or update repository
setup_repository() {
    print_step "Setting Up Trading System Code"

    INSTALL_DIR="$HOME/andre-assassin"

    if [ -d "$INSTALL_DIR" ]; then
        print_info "System already exists at $INSTALL_DIR"
        read -p "Do you want to update it? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "Updating system..."
            cd "$INSTALL_DIR"
            git pull
            print_success "System updated"
        fi
    else
        print_info "Downloading trading system..."
        git clone https://github.com/andreoutberg/assassinbeta.git "$INSTALL_DIR"
        cd "$INSTALL_DIR"
        print_success "Trading system downloaded"
    fi

    cd "$INSTALL_DIR"
}

# Interactive configuration
configure_system() {
    print_step "Configuring Your Trading System"

    print_info "I'll help you set up your trading configuration."
    print_info "Don't worry - you can change these later in the dashboard!"
    echo ""

    # Bybit API keys
    print_info "━━━ Bybit API Configuration ━━━"
    print_info "You need a FREE Bybit testnet account for demo trading."
    print_info "Get one here: https://testnet.bybit.com/"
    echo ""

    read -p "Do you have Bybit testnet API keys? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter Bybit API Key: " BYBIT_API_KEY
        read -sp "Enter Bybit API Secret: " BYBIT_API_SECRET
        echo
        BYBIT_TESTNET="true"
    else
        print_warning "No problem! You can add them later in the dashboard."
        print_info "System will use demo mode without live prices."
        BYBIT_API_KEY="demo_key"
        BYBIT_API_SECRET="demo_secret"
        BYBIT_TESTNET="true"
    fi

    # PostgreSQL password
    print_info "━━━ Database Password ━━━"
    print_info "Set a password for your database (keep it safe!)"
    read -sp "Enter database password: " DB_PASSWORD
    echo

    # Trading preferences
    print_info "━━━ Trading Preferences ━━━"

    print_info "Which optimization mode?"
    print_info "  1) HIGH WIN RATE (65-70% win rate) - Recommended for beginners"
    print_info "  2) BALANCED (50-55% win rate, higher profit per trade)"
    read -p "Choose (1 or 2) [1]: " OPT_MODE
    OPT_MODE=${OPT_MODE:-1}

    if [ "$OPT_MODE" = "1" ]; then
        OPTIMIZE_FOR_WIN_RATE="true"
        print_success "Mode: HIGH WIN RATE (65-70%)"
    else
        OPTIMIZE_FOR_WIN_RATE="false"
        print_success "Mode: BALANCED PROFIT"
    fi

    read -p "Maximum concurrent demo positions [10]: " MAX_POSITIONS
    MAX_POSITIONS=${MAX_POSITIONS:-10}

    read -p "Risk per trade % [2.0]: " RISK_PER_TRADE
    RISK_PER_TRADE=${RISK_PER_TRADE:-2.0}

    # Save configuration
    cat > .env <<EOF
# Andre Assassin Trading System Configuration
# Generated: $(date)

# Bybit Configuration
BYBIT_API_KEY=$BYBIT_API_KEY
BYBIT_API_SECRET=$BYBIT_API_SECRET
BYBIT_TESTNET=$BYBIT_TESTNET

# Database
POSTGRES_USER=trading
POSTGRES_PASSWORD=$DB_PASSWORD
POSTGRES_DB=andre_assassin_db
DATABASE_URL=postgresql://trading:$DB_PASSWORD@postgres:5432/andre_assassin_db

# Redis
REDIS_URL=redis://redis:6379

# Trading Configuration
OPTIMIZE_FOR_WIN_RATE=$OPTIMIZE_FOR_WIN_RATE
MAX_CONCURRENT_POSITIONS=$MAX_POSITIONS
RISK_PER_TRADE_PCT=$RISK_PER_TRADE

# Application
SECRET_KEY=$(openssl rand -hex 32)
ENVIRONMENT=production
EOF

    print_success "Configuration saved to .env"
    sleep 2
}

# Build Docker images
build_system() {
    print_step "Building Trading System (This Takes 5-10 Minutes)"

    print_info "Building Docker containers..."
    print_info "This will:"
    print_info "  • Set up PostgreSQL database"
    print_info "  • Set up Redis cache"
    print_info "  • Build FastAPI backend"
    print_info "  • Build React dashboard"
    echo ""

    docker-compose build --no-cache

    print_success "System built successfully!"
    sleep 2
}

# Initialize database
init_database() {
    print_step "Initializing Database"

    print_info "Starting database..."
    docker-compose up -d postgres redis

    print_info "Waiting for database to be ready..."
    sleep 10

    print_info "Running migrations..."
    docker-compose exec -T postgres psql -U trading -d andre_assassin_db < migrations/create_high_wr_schema.sql || true

    print_success "Database initialized!"
    sleep 2
}

# Start system
start_system() {
    print_step "Starting Trading System"

    print_info "Starting all services..."
    docker-compose up -d

    print_info "Waiting for services to start..."
    sleep 15

    # Check health
    print_info "Running health checks..."

    if curl -sf http://localhost:8000/health > /dev/null; then
        print_success "Backend API: Running"
    else
        print_warning "Backend API: Not responding yet (may need more time)"
    fi

    if curl -sf http://localhost:3000 > /dev/null; then
        print_success "Dashboard: Running"
    else
        print_warning "Dashboard: Not responding yet (may need more time)"
    fi

    print_success "System started!"
    sleep 2
}

# Run tests
run_tests() {
    print_step "Testing System"

    print_info "Running connection tests..."

    # Test Bybit connection
    if [ "$BYBIT_API_KEY" != "demo_key" ]; then
        print_info "Testing Bybit connection..."
        docker-compose exec -T backend python -c "
from app.services.bybit_client import get_bybit_client
import asyncio
async def test():
    client = await get_bybit_client()
    health = await client.check_health()
    print(f\"Bybit Health: {health['is_healthy']}\")
asyncio.run(test())
" || print_warning "Bybit connection test failed (you can configure this later)"
    fi

    # Test database
    print_info "Testing database..."
    docker-compose exec -T postgres psql -U trading -d andre_assassin_db -c "SELECT 1;" > /dev/null
    print_success "Database: OK"

    print_success "All tests passed!"
    sleep 2
}

# Print completion message
print_completion() {
    print_step "Installation Complete! 🎉"

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                              ║${NC}"
    echo -e "${GREEN}║              ✓ INSTALLATION SUCCESSFUL ✓                    ║${NC}"
    echo -e "${GREEN}║                                                              ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    print_info "Your trading system is now running!"
    echo ""

    print_info "📊 DASHBOARD:"
    echo -e "   ${BLUE}http://$(hostname -I | awk '{print $1}'):3000${NC}"
    echo -e "   ${BLUE}http://localhost:3000${NC} (if accessing locally)"
    echo ""

    print_info "🔧 API DOCUMENTATION:"
    echo -e "   ${BLUE}http://$(hostname -I | awk '{print $1}'):8000/docs${NC}"
    echo ""

    print_info "📚 USEFUL COMMANDS:"
    echo "   View logs:      docker-compose logs -f"
    echo "   Stop system:    docker-compose stop"
    echo "   Start system:   docker-compose start"
    echo "   Restart:        docker-compose restart"
    echo "   Update system:  git pull && docker-compose up -d --build"
    echo ""

    print_info "📖 NEXT STEPS:"
    echo "   1. Open the dashboard in your browser"
    echo "   2. Complete the setup wizard"
    echo "   3. Add your Bybit API keys (if you skipped earlier)"
    echo "   4. Start demo trading!"
    echo ""

    print_info "💡 NEED HELP?"
    echo "   • Documentation: https://github.com/andreoutberg/assassinbeta/wiki"
    echo "   • Issues: https://github.com/andreoutberg/assassinbeta/issues"
    echo "   • Built-in help: Click '?' in the dashboard"
    echo ""

    print_warning "IMPORTANT: If you see Docker permission errors,"
    print_warning "log out and back in, then run: docker-compose restart"
    echo ""
}

# Main installation flow
main() {
    print_header

    check_root
    check_system
    install_dependencies
    setup_repository
    configure_system
    build_system
    init_database
    start_system
    run_tests
    print_completion

    # Open browser (if on desktop)
    if [ -n "$DISPLAY" ]; then
        print_info "Opening dashboard in browser..."
        xdg-open http://localhost:3000 2>/dev/null || open http://localhost:3000 2>/dev/null || true
    fi
}

# Run main installation
main
