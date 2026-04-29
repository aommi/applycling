FROM python:3.12-slim

WORKDIR /app

# Install Playwright/Chromium system dependencies for PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2t64 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium

# Install Python dependencies
COPY pyproject.toml README.md ./
COPY applycling/ applycling/
RUN pip install --no-cache-dir .[postgres]

# Copy application code
COPY . .

# Install Playwright with system Chromium (no browser download needed)
RUN python -m playwright install chromium --with-deps || true

CMD ["python", "-m", "applycling.cli", "--help"]
