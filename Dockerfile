# syntax=docker/dockerfile:1
# Multi-stage production Dockerfile for Semantic Fashion Search & Recommendation Microservice

# ==============================================================================
# Stage 1: Build & Dependency Resolution
# ==============================================================================
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Create isolated virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy package metadata and application source
COPY pyproject.toml README.md ./
COPY app ./app

# Install project dependencies using prebuilt wheels (no C compilation needed)
RUN pip install --upgrade pip setuptools wheel && \
    pip install --extra-index-url https://download.pytorch.org/whl/cpu .

# ==============================================================================
# Stage 2: Minimal Non-Root Runtime
# ==============================================================================
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    HOST=0.0.0.0 \
    HF_HOME=/home/appuser/.cache/huggingface

# Create dedicated non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application package and data
COPY app /app/app
COPY data /app/data
COPY evals /app/evals
COPY pyproject.toml README.md /app/

# Ensure non-root ownership
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Start microservice
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]