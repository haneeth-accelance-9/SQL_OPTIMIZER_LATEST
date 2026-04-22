# syntax=docker/dockerfile:1

# Stage 1: Builder - Install dependencies
FROM python:3.11-slim AS builder

# Proxy for corporate network — inject at build time:
#   docker build --build-arg HTTP_PROXY=... --build-arg HTTPS_PROXY=...
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=$HTTP_PROXY \
    HTTPS_PROXY=$HTTPS_PROXY \
    http_proxy=$HTTP_PROXY \
    https_proxy=$HTTPS_PROXY

WORKDIR /app

# Install uv from official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY pyproject.toml .

# Install dependencies — uv resolves agentic-ai-sdk from the bayer-artifactory index
# declared in [tool.uv.index]. Credentials are injected via uv's named-index env vars:
#   UV_INDEX_BAYER_ARTIFACTORY_USERNAME / UV_INDEX_BAYER_ARTIFACTORY_PASSWORD
# Build with:
#   docker build --secret id=artifactory_user --secret id=artifactory_token ...
RUN --mount=type=secret,id=artifactory_user \
    --mount=type=secret,id=artifactory_token \
    UV_INDEX_BAYER_ARTIFACTORY_USERNAME=$(cat /run/secrets/artifactory_user) \
    UV_INDEX_BAYER_ARTIFACTORY_PASSWORD=$(cat /run/secrets/artifactory_token) \
    uv pip install --system --no-cache -e .

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY pyproject.toml ./
COPY src/ ./src/
COPY configs/ ./configs/
COPY cli/ ./cli/

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    CONFIG_PATH=configs/config.yaml \
    DEBUGPY_ENABLE=false \
    DEBUGPY_WAIT=false \
    DEBUGPY_PORT=5678

# Health check — tests the A2A /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" || exit 1

# Run the agent
CMD ["python", "-m", "src"]