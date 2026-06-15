# ---------- Stage 1: build ----------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build tools needed by some pip packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy backend source
COPY backend/ ./backend/

# Install Python deps
RUN pip install --no-cache-dir ./backend

# Install Playwright Chromium (required by browser-use)
RUN pip install playwright && playwright install --with-deps chromium

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim

WORKDIR /app

# Chromium runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libxshmfence1 \
    fonts-liberation wget ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages and Playwright browsers from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

# Copy app code
COPY backend/ ./backend/

# The .env is NOT baked in — pass secrets via Cloud Run env vars or Secret Manager
ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "backend.server.app:app", "--host", "0.0.0.0", "--port", "8080"]
