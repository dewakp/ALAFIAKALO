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

# --proxy-headers makes uvicorn trust X-Forwarded-Proto, so request.url.scheme is
# the scheme the CLIENT used. Without it TLS terminates at Cloud Run's front end
# and the app believes every request is plain http — so FastAPI's automatic
# trailing-slash redirect answered
#   GET https://api.alafia.app/api/v1/notifications
# with  307 -> http://api.alafia.app/api/v1/notifications/
# The browser blocks that as mixed content, the fetch fails, and the page showed
# "No notifications" to a user with 18 of them. Every generated absolute URL had
# the same defect; this is the general fix, and the trailing slashes on the call
# sites are the belt to its braces.
#
# forwarded-allow-ips="*" is correct HERE specifically: Cloud Run is the only
# ingress and it overwrites these headers, so there is no untrusted hop that
# could forge them.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
