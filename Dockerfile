# ==============================================================================
# Multi-Stage Production Dockerfile for ResearchAI Autonomous Orchestrator Agent
# Security: Non-root user execution, minimal attack surface, healthcheck
# ==============================================================================

# Stage 1: Build & Dependency Resolution
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final Runtime Image
FROM python:3.11-slim AS runner

WORKDIR /app

# Install runtime utilities (curl for container healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged system user & group
RUN groupadd -r appgroup && useradd -r -g appgroup -u 1001 appuser

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application source code
COPY --chown=appuser:appgroup . .

# Prepare persistent data directory with proper ownership
RUN mkdir -p /app/data && chown -R appuser:appgroup /app/data /home/appuser

# Switch to non-root user
USER appuser

# Expose Observability Health & Webhook Ports
EXPOSE 8080 8443

# Container Healthcheck via /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default Command: Start Autonomous Telegram Ingress Agent
CMD ["python", "bot.py"]
