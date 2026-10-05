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
# Run (open mode, dev only):
#   docker run -p 8000:8000 trust-layer:latest
#
# Run (production, with API key):
#   docker run -p 8000:8000 \
#     -e TRUST_LAYER_API_KEY=your-secret-key \
#     -e REGION_PROFILE="UAE (DOH)" \
#     trust-layer:latest
#
# Health check:
#   curl http://localhost:8000/health

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the trust layer and API
COPY trust_layer/ ./trust_layer/
COPY app.py .
COPY README.md .
COPY LICENSE .
COPY INTEGRATION.md .

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
