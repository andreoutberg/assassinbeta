# Backend Dockerfile for High-WR Trading System
# Multi-stage build for optimal size and caching

# ==========================================
# Base stage with system dependencies
# ==========================================
FROM python:3.14-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    curl \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# ==========================================
# Dependencies stage
# ==========================================
FROM base as dependencies

WORKDIR /app

# Copy only requirements file for better caching
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# ==========================================
# Development stage
# ==========================================
FROM dependencies as development

# Set working directory
WORKDIR /app

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/cache /app/scripts

# Install development dependencies
RUN pip install --no-cache-dir \
    pytest==7.4.3 \
    pytest-asyncio==0.21.1 \
    pytest-cov==4.1.0 \
    ipython==8.18.1

# Health check script
COPY scripts/health_check.py /app/scripts/
RUN chmod +x /app/scripts/health_check.py

# Expose port
EXPOSE 8000

# Health check configuration
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python /app/scripts/health_check.py || exit 1

# Development command with hot reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ==========================================
# Production stage
# ==========================================
FROM dependencies as production

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy application code with proper ownership
COPY --chown=appuser:appuser . .

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/data /app/cache /app/scripts && \
    chown -R appuser:appuser /app

# Health check script
COPY --chown=appuser:appuser scripts/health_check.py /app/scripts/
RUN chmod +x /app/scripts/health_check.py

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check configuration
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python /app/scripts/health_check.py || exit 1

# Production command without reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]