FROM python:3.12-slim

WORKDIR /app

# Install Rust toolchain (needed for alafia_crypto native extension)
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.cargo/bin:${PATH}"

# Text recognition for documents that have no selectable text — a photo of a
# report, or a scanned PDF. `extract.py` already detected the second case and
# called it `needs_ocr`; nothing could act on it until now.
#
# ⚠️ Tesseract runs IN THIS CONTAINER and nothing leaves. That is the whole
# reason it is here rather than a vision model: §3al records that a
# lab-report photo carries the patient's name, address and record number in
# its header, that `scrub_payload` cannot redact image bytes, and that whether
# a photo may reach a third party at all is a product decision. It is also
# deterministic — a vision model asked to read a potassium value can invent
# one, and §3ab exists because a wrong value in `lab_results` is
# indistinguishable from a real one.
#
# poppler-utils renders a scanned PDF's pages to images for the same path.
#
# ⚠️ `tesseract-ocr-osd` is named EXPLICITLY, and it was not before. It is the
# page-orientation pack — a different thing from a recognition language: -eng
# reads the words, -osd decides which way up the page is, and `_upright()`
# cannot work without it. Paper photographed on a desk is routinely sideways,
# and §48 measured what that costs: 4 records upright, ZERO at 90/180/270, with
# `_upright`'s except branch logging at DEBUG and returning the page unturned.
# A SILENT total loss.
#
# It arrived transitively with `tesseract-ocr` (verified in the serving image:
# tessdata held eng and osd). An undeclared dependency that happens to be
# satisfied is not a satisfied dependency — a base-image or packaging change
# could have deleted the rotation repair with nothing failing. OPEN_ITEMS 50a.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd poppler-utils \
    && rm -rf /var/lib/apt/lists/*

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
