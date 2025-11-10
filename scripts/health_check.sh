#!/bin/bash

# Andre Assassin Health Check Script
# Comprehensive health check for all services and resources

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Service endpoints
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
NGINX_URL="${NGINX_URL:-http://localhost}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
OPTUNA_URL="${OPTUNA_URL:-http://localhost:8080}"

# Thresholds
DISK_WARNING_THRESHOLD=80  # Percentage
MEMORY_WARNING_THRESHOLD=80  # Percentage
CPU_WARNING_THRESHOLD=80  # Percentage

# Health check results
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Function to print colored output
print_header() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_check() {
    echo -n -e "${BLUE}[CHECK]${NC} $1... "
}

print_pass() {
    echo -e "${GREEN}✓ PASS${NC}"
    ((PASSED_CHECKS++))
    ((TOTAL_CHECKS++))
}

print_fail() {
    echo -e "${RED}✗ FAIL${NC} - $1"
    ((FAILED_CHECKS++))
    ((TOTAL_CHECKS++))
}

print_warning() {
    echo -e "${YELLOW}⚠ WARNING${NC} - $1"
    ((WARNING_CHECKS++))
    ((TOTAL_CHECKS++))
}

print_info() {
    echo -e "  ${BLUE}ℹ${NC} $1"
}

# Function to check Docker service
check_docker_service() {
    local service=$1
    local container_name=$2

    print_check "Docker service: $service"

    # Check if container exists
    if docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
        # Check if container is running
        if docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
            # Check container health
            HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "none")

            if [ "$HEALTH" = "healthy" ]; then
                print_pass

                # Get container stats
                STATS=$(docker stats --no-stream --format "table {{.CPUPerc}}\t{{.MemUsage}}" "$container_name" | tail -n 1)
                CPU=$(echo "$STATS" | awk '{print $1}')
                MEM=$(echo "$STATS" | awk '{print $2}')
                print_info "CPU: $CPU, Memory: $MEM"
            elif [ "$HEALTH" = "none" ]; then
                print_pass
                print_info "No health check defined"
            else
                print_warning "Container is running but health status is: $HEALTH"
            fi
        else
            print_fail "Container exists but is not running"
        fi
    else
        print_fail "Container not found"
    fi
}

# Function to check PostgreSQL
check_postgres() {
    print_check "PostgreSQL database"

    # Try to connect using docker exec
    if docker exec postgres pg_isready -U postgres &>/dev/null; then
        print_pass

        # Get database size and connection count
        DB_SIZE=$(docker exec postgres psql -U postgres -t -c "SELECT pg_size_pretty(pg_database_size('postgres'));" 2>/dev/null | tr -d ' ')
        CONN_COUNT=$(docker exec postgres psql -U postgres -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null | tr -d ' ')

        print_info "Database size: $DB_SIZE, Active connections: $CONN_COUNT"
    else
        # Try direct connection
        if command -v pg_isready &> /dev/null; then
            if pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" &>/dev/null; then
                print_pass
            else
                print_fail "Cannot connect to PostgreSQL"
            fi
        else
            print_fail "PostgreSQL not accessible"
        fi
    fi
}

# Function to check Redis
check_redis() {
    print_check "Redis cache"

    # Try to ping Redis using docker exec
    if docker exec redis redis-cli ping &>/dev/null; then
        print_pass

        # Get Redis info
        USED_MEM=$(docker exec redis redis-cli INFO memory | grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
        CONNECTED_CLIENTS=$(docker exec redis redis-cli INFO clients | grep "connected_clients" | cut -d: -f2 | tr -d '\r')

        print_info "Memory usage: $USED_MEM, Connected clients: $CONNECTED_CLIENTS"
    else
        # Try direct connection
        if command -v redis-cli &> /dev/null; then
            if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping &>/dev/null; then
                print_pass
            else
                print_fail "Cannot connect to Redis"
            fi
        else
            print_fail "Redis not accessible"
        fi
    fi
}

# Function to check HTTP endpoint
check_http_endpoint() {
    local name=$1
    local url=$2
    local expected_code=${3:-200}

    print_check "$name endpoint"

    if command -v curl &> /dev/null; then
        RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")

        if [ "$RESPONSE" = "$expected_code" ]; then
            print_pass

            # Get response time
            RESPONSE_TIME=$(curl -s -o /dev/null -w "%{time_total}" "$url" 2>/dev/null || echo "N/A")
            print_info "Response time: ${RESPONSE_TIME}s"
        elif [ "$RESPONSE" = "000" ]; then
            print_fail "Cannot reach $url"
        else
            print_warning "Returned HTTP $RESPONSE (expected $expected_code)"
        fi
    else
        print_warning "curl not installed, cannot check HTTP endpoints"
    fi
}

# Function to check disk space
check_disk_space() {
    print_check "Disk space"

    DISK_USAGE=$(df -h "$PROJECT_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
    DISK_AVAILABLE=$(df -h "$PROJECT_DIR" | awk 'NR==2 {print $4}')

    if [ "$DISK_USAGE" -lt "$DISK_WARNING_THRESHOLD" ]; then
        print_pass
        print_info "Usage: ${DISK_USAGE}%, Available: ${DISK_AVAILABLE}"
    elif [ "$DISK_USAGE" -lt 90 ]; then
        print_warning "Disk usage is ${DISK_USAGE}% (Available: ${DISK_AVAILABLE})"
    else
        print_fail "Critical: Disk usage is ${DISK_USAGE}%"
    fi
}

# Function to check memory usage
check_memory() {
    print_check "Memory usage"

    if command -v free &> /dev/null; then
        MEM_TOTAL=$(free -m | awk 'NR==2 {print $2}')
        MEM_USED=$(free -m | awk 'NR==2 {print $3}')
        MEM_AVAILABLE=$(free -m | awk 'NR==2 {print $7}')
        MEM_USAGE=$(( (MEM_USED * 100) / MEM_TOTAL ))

        if [ "$MEM_USAGE" -lt "$MEMORY_WARNING_THRESHOLD" ]; then
            print_pass
            print_info "Usage: ${MEM_USAGE}% (${MEM_USED}MB/${MEM_TOTAL}MB), Available: ${MEM_AVAILABLE}MB"
        elif [ "$MEM_USAGE" -lt 90 ]; then
            print_warning "Memory usage is ${MEM_USAGE}% (Available: ${MEM_AVAILABLE}MB)"
        else
            print_fail "Critical: Memory usage is ${MEM_USAGE}%"
        fi
    else
        print_warning "Cannot check memory usage"
    fi
}

# Function to check CPU load
check_cpu_load() {
    print_check "CPU load"

    if command -v uptime &> /dev/null; then
        LOAD_AVG=$(uptime | awk -F'load average:' '{print $2}')
        CPU_COUNT=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo "1")
        LOAD_1MIN=$(echo "$LOAD_AVG" | awk '{print $1}' | sed 's/,//')

        # Calculate load percentage (rough estimate)
        LOAD_PCT=$(echo "$LOAD_1MIN $CPU_COUNT" | awk '{printf "%.0f", ($1/$2)*100}')

        if [ "$LOAD_PCT" -lt "$CPU_WARNING_THRESHOLD" ]; then
            print_pass
            print_info "Load average: $LOAD_AVG (${CPU_COUNT} cores)"
        elif [ "$LOAD_PCT" -lt 100 ]; then
            print_warning "High CPU load: $LOAD_AVG (${CPU_COUNT} cores)"
        else
            print_fail "Critical CPU load: $LOAD_AVG (${CPU_COUNT} cores)"
        fi
    else
        print_warning "Cannot check CPU load"
    fi
}

# Function to check logs for errors
check_logs() {
    print_check "Recent error logs"

    ERROR_COUNT=0

    # Check Docker logs for errors
    for container in postgres redis backend nginx; do
        if docker ps --format '{{.Names}}' | grep -q "$container"; then
            ERRORS=$(docker logs "$container" 2>&1 | tail -100 | grep -iE "error|exception|fatal" | wc -l)
            ERROR_COUNT=$((ERROR_COUNT + ERRORS))
        fi
    done

    if [ "$ERROR_COUNT" -eq 0 ]; then
        print_pass
        print_info "No recent errors in logs"
    elif [ "$ERROR_COUNT" -lt 10 ]; then
        print_warning "Found $ERROR_COUNT error entries in recent logs"
    else
        print_fail "Found $ERROR_COUNT error entries in recent logs"
    fi
}

# Function to check Docker network
check_docker_network() {
    print_check "Docker network"

    NETWORK_NAME="${PROJECT_NAME:-andre-assassin}_default"

    if docker network ls | grep -q "$NETWORK_NAME"; then
        print_pass

        # Count connected containers
        CONNECTED=$(docker network inspect "$NETWORK_NAME" -f '{{len .Containers}}' 2>/dev/null || echo "0")
        print_info "Connected containers: $CONNECTED"
    else
        print_warning "Docker network not found (may use different name)"
    fi
}

# Function to print summary
print_summary() {
    print_header "HEALTH CHECK SUMMARY"

    echo ""
    echo -e "Total Checks:    ${BLUE}$TOTAL_CHECKS${NC}"
    echo -e "Passed:          ${GREEN}$PASSED_CHECKS${NC}"
    echo -e "Warnings:        ${YELLOW}$WARNING_CHECKS${NC}"
    echo -e "Failed:          ${RED}$FAILED_CHECKS${NC}"
    echo ""

    if [ "$FAILED_CHECKS" -eq 0 ]; then
        if [ "$WARNING_CHECKS" -eq 0 ]; then
            echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${GREEN}         SYSTEM IS HEALTHY${NC}"
            echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            exit 0
        else
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${YELLOW}    SYSTEM IS OPERATIONAL WITH WARNINGS${NC}"
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            exit 0
        fi
    else
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${RED}      SYSTEM HAS CRITICAL ISSUES${NC}"
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        exit 1
    fi
}

# Main execution
main() {
    echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     Andre Assassin Health Check       ║${NC}"
    echo -e "${CYAN}║        $(date '+%Y-%m-%d %H:%M:%S')         ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"

    # System Resources
    print_header "SYSTEM RESOURCES"
    check_disk_space
    check_memory
    check_cpu_load

    # Docker Services
    print_header "DOCKER SERVICES"
    check_docker_service "PostgreSQL" "postgres"
    check_docker_service "Redis" "redis"
    check_docker_service "Backend" "backend"
    check_docker_service "Nginx" "nginx"
    check_docker_service "Grafana" "grafana"
    check_docker_service "Optuna" "optuna-dashboard"

    # Service Connectivity
    print_header "SERVICE CONNECTIVITY"
    check_postgres
    check_redis
    check_docker_network

    # HTTP Endpoints
    print_header "HTTP ENDPOINTS"
    check_http_endpoint "Nginx" "$NGINX_URL"
    check_http_endpoint "Backend API" "${BACKEND_URL}/health"
    check_http_endpoint "Backend Webhook" "${BACKEND_URL}/webhook" "200,201,204,405"
    check_http_endpoint "Grafana" "$GRAFANA_URL"
    check_http_endpoint "Optuna Dashboard" "$OPTUNA_URL"

    # Logs
    print_header "LOG ANALYSIS"
    check_logs

    # Summary
    print_summary
}

# Run main function
main "$@"