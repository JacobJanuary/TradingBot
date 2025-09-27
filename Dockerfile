# Multi-stage build for optimized image size
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 trader && \
    mkdir -p /app/logs /app/reports /app/backups && \
    chown -R trader:trader /app

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder --chown=trader:trader /root/.local /home/trader/.local

# Copy application code
COPY --chown=trader:trader . .

# Switch to non-root user
USER trader

# Add local bin to PATH
ENV PATH=/home/trader/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command
CMD ["python", "main.py", "--config", "/app/config/config.yaml"]