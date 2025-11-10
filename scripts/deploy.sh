#!/bin/bash

# Andre Assassin Automated Deployment Script
# This script handles the complete deployment process with error handling and rollback

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DEPLOY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${DEPLOY_DIR}/data/backups"
LOG_FILE="${DEPLOY_DIR}/data/logs/deploy_$(date +%Y%m%d_%H%M%S).log"
ROLLBACK_TAG="rollback_$(date +%Y%m%d_%H%M%S)"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1" | tee -a "$LOG_FILE"
}

print_error() {
    echo -e "${RED}✗${NC} $1" | tee -a "$LOG_FILE"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1" | tee -a "$LOG_FILE"
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."

    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed!"
        echo "Please install Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
    print_success "Docker found: $(docker --version)"

    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed!"
        echo "Please install Docker Compose: https://docs.docker.com/compose/install/"
        exit 1
    fi
    print_success "Docker Compose found: $(docker-compose --version)"

    # Check Git
    if ! command -v git &> /dev/null; then
        print_error "Git is not installed!"
        echo "Please install Git: apt-get install git"
        exit 1
    fi
    print_success "Git found: $(git --version)"

    # Check disk space (require at least 5GB)
    AVAILABLE_SPACE=$(df "$DEPLOY_DIR" | awk 'NR==2 {print $4}')
    if [ "$AVAILABLE_SPACE" -lt 5242880 ]; then
        print_error "Insufficient disk space! At least 5GB required."
        exit 1
    fi
    print_success "Sufficient disk space available: $(( AVAILABLE_SPACE / 1024 / 1024 ))GB"

    # Check memory (require at least 2GB)
    AVAILABLE_MEM=$(free -m | awk 'NR==2 {print $7}')
    if [ "$AVAILABLE_MEM" -lt 2048 ]; then
        print_warning "Low memory available: ${AVAILABLE_MEM}MB. Recommended: 4GB+"
    else
        print_success "Sufficient memory available: ${AVAILABLE_MEM}MB"
    fi
}

# Function to create required directories
create_directories() {
    print_status "Creating required directories..."

    directories=(
        "data/postgres"
        "data/redis"
        "data/backups"
        "data/logs"
        "data/grafana"
        "data/prometheus"
    )

    for dir in "${directories[@]}"; do
        mkdir -p "${DEPLOY_DIR}/${dir}"
        chmod 755 "${DEPLOY_DIR}/${dir}"
        print_success "Created ${dir}"
    done
}

# Function to validate .env file
validate_env() {
    print_status "Validating .env configuration..."

    if [ ! -f "${DEPLOY_DIR}/.env" ]; then
        if [ -f "${DEPLOY_DIR}/.env.example" ]; then
            print_warning ".env file not found. Creating from .env.example..."
            cp "${DEPLOY_DIR}/.env.example" "${DEPLOY_DIR}/.env"
            print_error "Please edit .env file and configure all required values!"
            exit 1
        else
            print_error ".env file not found and no .env.example available!"
            exit 1
        fi
    fi

    # Check required variables
    required_vars=(
        "POSTGRES_DB"
        "POSTGRES_USER"
        "POSTGRES_PASSWORD"
        "REDIS_PASSWORD"
        "SECRET_KEY"
    )

    source "${DEPLOY_DIR}/.env"

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            print_error "Required variable ${var} is not set in .env!"
            exit 1
        fi
    done

    print_success ".env file validated"
}

# Function to backup current deployment
backup_current() {
    print_status "Creating backup of current deployment..."

    BACKUP_FILE="${BACKUP_DIR}/backup_${ROLLBACK_TAG}.tar.gz"

    # Tag current images for rollback
    docker-compose images -q | while read image_id; do
        if [ ! -z "$image_id" ]; then
            docker tag "$image_id" "${image_id}:${ROLLBACK_TAG}" 2>/dev/null || true
        fi
    done

    # Backup .env and docker-compose files
    tar -czf "$BACKUP_FILE" \
        -C "$DEPLOY_DIR" \
        .env \
        docker-compose.yml \
        docker-compose.prod.yml 2>/dev/null || true

    print_success "Backup created: $BACKUP_FILE"
}

# Function to build Docker images
build_images() {
    print_status "Building Docker images..."

    cd "$DEPLOY_DIR"

    # Build with no cache for clean build
    if docker-compose build --no-cache; then
        print_success "Docker images built successfully"
    else
        print_error "Failed to build Docker images"
        rollback
        exit 1
    fi
}

# Function to start services
start_services() {
    print_status "Starting services..."

    cd "$DEPLOY_DIR"

    # Stop existing services
    docker-compose down 2>/dev/null || true

    # Start services
    if docker-compose up -d; then
        print_success "Services started"
    else
        print_error "Failed to start services"
        rollback
        exit 1
    fi

    # Wait for services to be healthy
    print_status "Waiting for services to be healthy..."
    sleep 10

    # Check service health
    services=("postgres" "redis" "backend" "nginx")
    for service in "${services[@]}"; do
        if docker-compose ps | grep -q "${service}.*Up"; then
            print_success "${service} is running"
        else
            print_error "${service} is not running"
            rollback
            exit 1
        fi
    done
}

# Function to run database migrations
run_migrations() {
    print_status "Running database migrations..."

    # Wait for database to be ready
    sleep 5

    # Run migrations
    if docker-compose exec -T backend python manage.py migrate 2>/dev/null || \
       docker-compose exec -T backend alembic upgrade head 2>/dev/null || \
       docker-compose exec -T backend flask db upgrade 2>/dev/null; then
        print_success "Database migrations completed"
    else
        print_warning "Could not run migrations automatically. Please run manually if needed."
    fi
}

# Function to test webhook endpoint
test_webhook() {
    print_status "Testing webhook endpoint..."

    # Get the webhook URL (assuming it's on port 8000)
    WEBHOOK_URL="http://localhost:8000/webhook"

    # Send test webhook
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d '{"test": "data", "source": "deployment_test"}' 2>/dev/null || echo "000")

    if [ "$RESPONSE" = "200" ] || [ "$RESPONSE" = "201" ] || [ "$RESPONSE" = "204" ]; then
        print_success "Webhook endpoint responding (HTTP $RESPONSE)"
    else
        print_warning "Webhook endpoint returned HTTP $RESPONSE (may need configuration)"
    fi
}

# Function to perform health checks
health_check() {
    print_status "Running health checks..."

    if [ -f "${DEPLOY_DIR}/scripts/health_check.sh" ]; then
        bash "${DEPLOY_DIR}/scripts/health_check.sh"
    else
        # Basic health check
        docker-compose ps
    fi
}

# Function to display access URLs
display_urls() {
    print_status "Deployment completed successfully!"
    echo ""
    echo "================================="
    echo "Access URLs:"
    echo "================================="
    echo "Main Application: http://localhost"
    echo "API Backend: http://localhost:8000"
    echo "Grafana Dashboard: http://localhost:3000"
    echo "Optuna Dashboard: http://localhost:8080"
    echo ""
    echo "Default Credentials:"
    echo "Grafana: admin/admin (change on first login)"
    echo ""
    echo "Useful Commands:"
    echo "View logs: docker-compose logs -f"
    echo "Check status: docker-compose ps"
    echo "Stop services: docker-compose down"
    echo "================================="
}

# Function to rollback deployment
rollback() {
    print_error "Deployment failed! Starting rollback..."

    cd "$DEPLOY_DIR"

    # Stop current services
    docker-compose down 2>/dev/null || true

    # Restore from backup if exists
    if [ -f "${BACKUP_DIR}/backup_${ROLLBACK_TAG}.tar.gz" ]; then
        tar -xzf "${BACKUP_DIR}/backup_${ROLLBACK_TAG}.tar.gz" -C "$DEPLOY_DIR"
        print_success "Configuration restored from backup"
    fi

    # Try to restore tagged images
    docker images | grep "$ROLLBACK_TAG" | while read image; do
        IMAGE_ID=$(echo $image | awk '{print $3}')
        ORIGINAL_TAG=$(echo $image | awk '{print $1}' | sed "s/:${ROLLBACK_TAG}//")
        docker tag "$IMAGE_ID" "$ORIGINAL_TAG:latest" 2>/dev/null || true
    done

    print_warning "Rollback completed. Previous deployment state restored."
}

# Main deployment flow
main() {
    echo "================================="
    echo "Andre Assassin Deployment Script"
    echo "================================="
    echo ""

    # Create log directory if it doesn't exist
    mkdir -p "$(dirname "$LOG_FILE")"

    print_status "Starting deployment process..."
    print_status "Logging to: $LOG_FILE"
    echo ""

    # Run deployment steps
    check_prerequisites
    create_directories
    validate_env
    backup_current
    build_images
    start_services
    run_migrations
    test_webhook
    health_check

    # Display success message and URLs
    display_urls

    print_success "Deployment completed successfully!"
    print_status "Check logs at: $LOG_FILE"
}

# Handle interrupts
trap 'print_error "Deployment interrupted!"; rollback; exit 1' INT TERM

# Run main function
main "$@"