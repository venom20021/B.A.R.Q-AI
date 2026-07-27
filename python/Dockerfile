# ─── BARQ Python Sidecar — Docker for Fly.io ──────────────────────────
# Multi-stage build: lean runtime, Playwright browsers, full pip install.
# ───────────────────────────────────────────────────────────────────────

# ── Stage 1: Install system deps + Playwright browsers ───────────────
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy AS base

WORKDIR /app

# Install system packages that BARQ needs beyond what Playwright image ships
# NOTE: Voice/vision packages (portaudio, libgl) stay local — not needed on server.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Stage 2: Install Python dependencies ─────────────────────────────
FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium for auto-apply)
RUN playwright install chromium

# ── Stage 3: Runtime image ───────────────────────────────────────────
FROM deps AS runtime

WORKDIR /app

# Copy BARQ Python source
COPY . .

# Create data directories that BARQ expects
RUN mkdir -p data/brains data/generated

# Fly.io injects the PORT env var automatically
# Use it, fall back to 8080
ENV PORT=8080
ENV SIDECAR_PORT=8080
ENV SIDECAR_HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1
ENV TURSO_ENABLED=true

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --log-level info"]
