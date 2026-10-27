FROM python:3.12-slim

# System dependencies (curl used by the Docker health-check)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies before copying source so Docker can cache the
# layer and avoid re-installing on every code change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Uvicorn with --reload so code changes in the mounted volume are picked up
# automatically during local development.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
