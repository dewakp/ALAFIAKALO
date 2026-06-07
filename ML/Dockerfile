# ═══════════════════════════════════════════════════════════════════════════════
#  HEBCS — Holistic ESRD Biometric Composite Score
#  Docker image for reproducible inference and pipeline execution
# ═══════════════════════════════════════════════════════════════════════════════

FROM python:3.13-slim AS base

LABEL maintainer="HEBCS Contributors"
LABEL description="HEBCS: Holistic ESRD Biometric Composite Score model system"
LABEL version="1.0.0"

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY config.yaml .
COPY predict.py .
COPY feature_bridge.py .
COPY drift_monitor.py .
COPY models/ models/

# Patient data is NOT baked into the image — mount at runtime via -v
# e.g.  docker run -v $(pwd)/data:/app/data hebcs ...

# Healthcheck — verify models load
RUN python -c "from predict import HEBCSPredictor; p = HEBCSPredictor.load(); print('Models OK')"

# Default: print model info
ENTRYPOINT ["python", "predict.py"]
CMD ["--info"]

# ═══════════════════════════════════════════════════════════════════════════════
#  Usage:
#    docker build -t hebcs .
#    docker run hebcs --info
#    docker run -v $(pwd)/data:/app/data hebcs --features data/features/health_features.csv --row -1
#    docker run hebcs --whatif calories=2500 potassium=1800 --json
# ═══════════════════════════════════════════════════════════════════════════════
