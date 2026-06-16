FROM python:3.12-slim

WORKDIR /app

# Install system deps for building Python packages + Chromium runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libxshmfence1 \
    libxfixes3 libx11-6 libx11-xcb1 libxcb1 libxext6 libxi6 \
    libxtst6 libglib2.0-0 libdbus-1-3 libexpat1 \
    fonts-liberation wget ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy backend source
COPY backend/ ./backend/

# Install Python deps
RUN pip install --no-cache-dir ./backend

# Install Playwright Chromium + ALL system deps it needs
RUN pip install playwright && playwright install --with-deps chromium

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "backend.server.app:app", "--host", "0.0.0.0", "--port", "8080"]
