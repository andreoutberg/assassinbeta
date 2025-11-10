#!/bin/bash

# Andre Assassin Backup Script
# Creates comprehensive backups of database, Redis, and configuration files

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_DIR}/data/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="andre_assassin_backup_${TIMESTAMP}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

# Retention settings (days)
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

# S3 Configuration (optional)
S3_BUCKET="${S3_BUCKET:-}"
S3_PATH="${S3_PATH:-andre-assassin-backups}"
AWS_PROFILE="${AWS_PROFILE:-default}"

# Remote backup server (optional)
REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_USER="${REMOTE_USER:-}"
REMOTE_PATH="${REMOTE_PATH:-/backups/andre-assassin}"

# Database configuration
DB_CONTAINER="${DB_CONTAINER:-postgres}"
DB_NAME="${POSTGRES_DB:-andre_assassin}"
DB_USER="${POSTGRES_USER:-postgres}"

# Redis configuration
REDIS_CONTAINER="${REDIS_CONTAINER:-redis}"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."

    # Check if backup directory exists
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR"
        print_success "Created backup directory: $BACKUP_DIR"
    fi

    # Check disk space (require at least 1GB)
    AVAILABLE_SPACE=$(df "$BACKUP_DIR" | awk 'NR==2 {print $4}')
    if [ "$AVAILABLE_SPACE" -lt 1048576 ]; then
        print_error "Insufficient disk space for backup! At least 1GB required."
        exit 1
    fi

    # Check if containers are running
    if ! docker ps | grep -q "$DB_CONTAINER"; then
        print_warning "PostgreSQL container is not running"
    fi

    if ! docker ps | grep -q "$REDIS_CONTAINER"; then
        print_warning "Redis container is not running"
    fi

    print_success "Prerequisites check completed"
}

# Function to backup PostgreSQL database
backup_postgres() {
    print_status "Backing up PostgreSQL database..."

    if docker ps | grep -q "$DB_CONTAINER"; then
        # Create backup directory
        mkdir -p "${BACKUP_PATH}/postgres"

        # Dump database
        if docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" \
            > "${BACKUP_PATH}/postgres/database.sql" 2>/dev/null; then

            # Get file size
            SIZE=$(du -h "${BACKUP_PATH}/postgres/database.sql" | awk '{print $1}')
            print_success "PostgreSQL backup completed (${SIZE})"

            # Also backup roles and permissions
            docker exec "$DB_CONTAINER" pg_dumpall -U "$DB_USER" --roles-only \
                > "${BACKUP_PATH}/postgres/roles.sql" 2>/dev/null || true
        else
            print_error "Failed to backup PostgreSQL database"
            return 1
        fi

        # Backup table schemas separately
        docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" --schema-only \
            > "${BACKUP_PATH}/postgres/schema.sql" 2>/dev/null || true

    else
        print_warning "PostgreSQL container not running, skipping database backup"
    fi
}

# Function to backup Redis data
backup_redis() {
    print_status "Backing up Redis data..."

    if docker ps | grep -q "$REDIS_CONTAINER"; then
        # Create backup directory
        mkdir -p "${BACKUP_PATH}/redis"

        # Trigger Redis save
        docker exec "$REDIS_CONTAINER" redis-cli BGSAVE &>/dev/null || true
        sleep 2

        # Check if save completed
        while docker exec "$REDIS_CONTAINER" redis-cli LASTSAVE | grep -q "Waiting"; do
            sleep 1
        done

        # Copy dump file
        if docker cp "${REDIS_CONTAINER}:/data/dump.rdb" "${BACKUP_PATH}/redis/dump.rdb" 2>/dev/null; then
            SIZE=$(du -h "${BACKUP_PATH}/redis/dump.rdb" | awk '{print $1}')
            print_success "Redis backup completed (${SIZE})"
        else
            print_warning "Could not backup Redis data"
        fi

        # Export Redis configuration
        docker exec "$REDIS_CONTAINER" redis-cli CONFIG GET "*" \
            > "${BACKUP_PATH}/redis/redis_config.txt" 2>/dev/null || true

    else
        print_warning "Redis container not running, skipping Redis backup"
    fi
}

# Function to backup configuration files
backup_configs() {
    print_status "Backing up configuration files..."

    # Create config backup directory
    mkdir -p "${BACKUP_PATH}/config"

    # List of files to backup
    config_files=(
        ".env"
        "docker-compose.yml"
        "docker-compose.prod.yml"
        "docker-compose.override.yml"
        "nginx.conf"
        "prometheus.yml"
        "grafana.ini"
    )

    backed_up=0
    for file in "${config_files[@]}"; do
        if [ -f "${PROJECT_DIR}/${file}" ]; then
            cp "${PROJECT_DIR}/${file}" "${BACKUP_PATH}/config/" 2>/dev/null
            ((backed_up++))
        fi
    done

    # Backup scripts directory
    if [ -d "${PROJECT_DIR}/scripts" ]; then
        cp -r "${PROJECT_DIR}/scripts" "${BACKUP_PATH}/config/" 2>/dev/null || true
    fi

    print_success "Configuration backup completed ($backed_up files)"
}

# Function to backup Docker images
backup_docker_images() {
    print_status "Backing up Docker images (optional)..."

    if [ "${BACKUP_DOCKER_IMAGES:-false}" = "true" ]; then
        mkdir -p "${BACKUP_PATH}/docker"

        # Get list of project images
        docker-compose images -q | while read image_id; do
            if [ ! -z "$image_id" ]; then
                IMAGE_NAME=$(docker inspect --format='{{index .RepoTags 0}}' "$image_id" 2>/dev/null | tr '/:' '_')
                docker save "$image_id" | gzip > "${BACKUP_PATH}/docker/${IMAGE_NAME}.tar.gz"
            fi
        done

        print_success "Docker images backup completed"
    else
        print_status "Skipping Docker images backup (set BACKUP_DOCKER_IMAGES=true to enable)"
    fi
}

# Function to create backup metadata
create_metadata() {
    print_status "Creating backup metadata..."

    cat > "${BACKUP_PATH}/backup_metadata.json" << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "backup_name": "${BACKUP_NAME}",
    "hostname": "$(hostname)",
    "project_dir": "${PROJECT_DIR}",
    "components": {
        "postgres": $([ -d "${BACKUP_PATH}/postgres" ] && echo "true" || echo "false"),
        "redis": $([ -d "${BACKUP_PATH}/redis" ] && echo "true" || echo "false"),
        "config": $([ -d "${BACKUP_PATH}/config" ] && echo "true" || echo "false"),
        "docker": $([ -d "${BACKUP_PATH}/docker" ] && echo "true" || echo "false")
    },
    "docker_version": "$(docker --version)",
    "docker_compose_version": "$(docker-compose --version)",
    "disk_usage": "$(du -sh "${BACKUP_PATH}" | awk '{print $1}')"
}
EOF

    print_success "Metadata created"
}

# Function to compress backup
compress_backup() {
    print_status "Compressing backup..."

    cd "$BACKUP_DIR"

    if tar -czf "${BACKUP_NAME}.tar.gz" "${BACKUP_NAME}"; then
        # Get compressed size
        SIZE=$(du -h "${BACKUP_NAME}.tar.gz" | awk '{print $1}')
        print_success "Backup compressed: ${BACKUP_NAME}.tar.gz (${SIZE})"

        # Remove uncompressed directory
        rm -rf "${BACKUP_NAME}"
    else
        print_error "Failed to compress backup"
        return 1
    fi
}

# Function to upload to S3
upload_to_s3() {
    if [ -z "$S3_BUCKET" ]; then
        return 0
    fi

    print_status "Uploading to S3..."

    if command -v aws &> /dev/null; then
        if aws s3 cp "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" \
            "s3://${S3_BUCKET}/${S3_PATH}/${BACKUP_NAME}.tar.gz" \
            --profile "$AWS_PROFILE"; then
            print_success "Backup uploaded to S3: s3://${S3_BUCKET}/${S3_PATH}/${BACKUP_NAME}.tar.gz"
        else
            print_error "Failed to upload to S3"
        fi
    else
        print_warning "AWS CLI not installed, skipping S3 upload"
    fi
}

# Function to upload to remote server
upload_to_remote() {
    if [ -z "$REMOTE_HOST" ]; then
        return 0
    fi

    print_status "Uploading to remote server..."

    if command -v scp &> /dev/null; then
        # Create remote directory
        ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_PATH}" 2>/dev/null || true

        # Upload backup
        if scp "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" \
            "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/"; then
            print_success "Backup uploaded to ${REMOTE_HOST}:${REMOTE_PATH}/"
        else
            print_error "Failed to upload to remote server"
        fi
    else
        print_warning "scp not available, skipping remote upload"
    fi
}

# Function to clean old backups
clean_old_backups() {
    print_status "Cleaning old backups..."

    # Clean local backups
    find "$BACKUP_DIR" -name "andre_assassin_backup_*.tar.gz" -type f -mtime +$BACKUP_RETENTION_DAYS -delete

    REMAINING=$(ls -1 "$BACKUP_DIR"/andre_assassin_backup_*.tar.gz 2>/dev/null | wc -l)
    print_success "Old backups cleaned. Remaining backups: $REMAINING"

    # Clean S3 backups if configured
    if [ ! -z "$S3_BUCKET" ] && command -v aws &> /dev/null; then
        # List and delete old S3 backups
        CUTOFF_DATE=$(date -d "$BACKUP_RETENTION_DAYS days ago" +%Y-%m-%d)
        aws s3 ls "s3://${S3_BUCKET}/${S3_PATH}/" --profile "$AWS_PROFILE" | \
            awk '{if ($1 < "'$CUTOFF_DATE'") print $4}' | \
            while read file; do
                aws s3 rm "s3://${S3_BUCKET}/${S3_PATH}/${file}" --profile "$AWS_PROFILE"
            done
    fi
}

# Function to send notification
send_notification() {
    local status=$1
    local message=$2

    # Webhook notification
    if [ ! -z "$BACKUP_WEBHOOK_URL" ]; then
        curl -X POST "$BACKUP_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"status\": \"$status\", \"message\": \"$message\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
            2>/dev/null || true
    fi

    # Email notification (requires mail command)
    if [ ! -z "$BACKUP_EMAIL" ] && command -v mail &> /dev/null; then
        echo "$message" | mail -s "Andre Assassin Backup: $status" "$BACKUP_EMAIL"
    fi
}

# Function to verify backup
verify_backup() {
    print_status "Verifying backup..."

    if [ -f "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" ]; then
        # Test archive integrity
        if tar -tzf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" &>/dev/null; then
            print_success "Backup verified successfully"
            return 0
        else
            print_error "Backup verification failed - archive corrupted"
            return 1
        fi
    else
        print_error "Backup file not found"
        return 1
    fi
}

# Main backup flow
main() {
    echo "==========================================="
    echo "Andre Assassin Backup Script"
    echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "==========================================="
    echo ""

    # Load environment variables
    if [ -f "${PROJECT_DIR}/.env" ]; then
        source "${PROJECT_DIR}/.env"
    fi

    START_TIME=$(date +%s)

    # Run backup steps
    check_prerequisites
    backup_postgres
    backup_redis
    backup_configs
    backup_docker_images
    create_metadata
    compress_backup

    # Verify backup
    if verify_backup; then
        # Upload to remote locations
        upload_to_s3
        upload_to_remote

        # Clean old backups
        clean_old_backups

        # Calculate duration
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))

        echo ""
        echo "==========================================="
        print_success "Backup completed successfully!"
        echo "Backup file: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
        echo "Size: $(du -h "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" | awk '{print $1}')"
        echo "Duration: ${DURATION} seconds"
        echo "==========================================="

        # Send success notification
        send_notification "SUCCESS" "Backup ${BACKUP_NAME} completed successfully in ${DURATION} seconds"

        exit 0
    else
        print_error "Backup failed!"

        # Send failure notification
        send_notification "FAILURE" "Backup ${BACKUP_NAME} failed"

        exit 1
    fi
}

# Handle interrupts
trap 'print_error "Backup interrupted!"; exit 1' INT TERM

# Run main function
main "$@"