# Identity Trust Assessment — deployable middleware container
#
# Deploy this inside the hospital's infrastructure. It exposes the
# trust engine as a REST API on port 8000. No patient data leaves
# the container's network — this runs entirely on-premise or in a
# UAE-based private cloud.
#
# Build:
#   docker build -t trust-layer:latest .
#
# Run (production, with API key and Neon Database):
#   docker run -p 8000:8000 \
#     -e TRUST_LAYER_API_KEY=your-secret-key \
#     -e REGION_PROFILE="UAE (DOH)" \
#     -e DATABASE_URL="postgresql://user:password@host/dbname?sslmode=require" \
#     trust-layer:latest

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (curl for healthcheck, libpq-dev for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application code (this includes trust_layer/, app.py, database.py, etc.)
COPY . .

# Run as non-root user
RUN useradd -m -u 1000 trustuser && chown -R trustuser:trustuser /app
USER trustuser

# Expose the API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the API
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
