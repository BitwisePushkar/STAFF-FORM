# ── Build stage ─────────────────────────────────────────────────────────────── #
FROM python:3.13-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# System deps needed to compile mysqlclient
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    default-libmysqlclient-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first to leverage layer cache
COPY pyproject.toml uv.lock* ./

# Install all dependencies into a virtual environment
RUN uv sync --frozen --no-dev


# ── Runtime stage ────────────────────────────────────────────────────────────── #
FROM python:3.13-slim AS runtime

# Runtime-only system deps (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Copy the pre-built venv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy entire project into /app
COPY . /app/

# Set WORKDIR to where manage.py lives so all management commands resolve correctly
WORKDIR /app/main

# Create required directories
RUN mkdir -p /app/media /app/static

# migrate → collectstatic → gunicorn (wsgi module is main.wsgi because WORKDIR is /app/main)
CMD ["sh", "-c", \
    "python manage.py migrate --noinput && \
     python manage.py collectstatic --noinput && \
     gunicorn --bind 0.0.0.0:8112 --workers 3 --timeout 120 main.wsgi:application"]