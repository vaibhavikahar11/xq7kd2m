# ─────────────────────────────────────────────────────────────────────────────
# backend/Dockerfile — FastAPI wind-forecast API
#
# Uses python:3.11-slim for broad compatibility and small image size.
# Runs as a non-root user for security.
# The committed data files (backend/data/*.csv.gz) are COPY'd into the image
# and resolved at runtime via config.py's __file__-relative DATA_DIR.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# System dependencies (curl used by Docker health-check)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source — including data/*.csv.gz
COPY . .

# Create a non-root user and switch to it
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
