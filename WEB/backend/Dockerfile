FROM python:3.12-slim

WORKDIR /app

# Install Rust toolchain (needed for alafia_crypto native extension)
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.cargo/bin:${PATH}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build & install the Rust crypto extension
COPY alafia_crypto/ ./alafia_crypto/
RUN pip install --no-cache-dir maturin && \
    cd alafia_crypto && maturin build --release && \
    pip install --no-cache-dir target/wheels/*.whl && \
    cd .. && rm -rf alafia_crypto/target

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
