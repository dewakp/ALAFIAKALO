FROM python:3.12-slim

WORKDIR /app

# Build toolchain for liboqs (Open Quantum Safe) — the constant-time ML-DSA
# implementation used for SIGNING. Kept in the identity image only; verifier apps
# stay pure-Python (dilithium-py verifies liboqs-signed tokens).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git libssl-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Trigger liboqs-python's one-time native build at image-build time (not at boot).
RUN python -c "import oqs; print('liboqs ready:', 'ML-DSA-65' in oqs.get_enabled_sig_mechanisms())"

COPY app ./app
COPY scripts ./scripts

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
