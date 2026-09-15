# Phase 5 food classifier — training, evaluation, ONNX export.
#
# Native architecture on purpose: training is the slow step and emulation would
# tax it. TFLite (Android) and Core ML (iOS) conversion live in
# Dockerfile.export, which has to be linux/amd64 — see the note there.
#
#   cd WEB && docker compose --profile ml build food-vision
FROM python:3.12-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore \
    TORCH_HOME=/opt/torch \
    PYTHONPATH=/ml \
    PYTHONUNBUFFERED=1

# PyPI's linux/arm64 torch wheel is the CUDA build (+cu130). The CPU index
# serves the same release without GPU libraries this image can never use.
ARG TORCH=2.14.0
ARG TORCHVISION=0.29.0
RUN pip install --only-binary=:all: --index-url https://download.pytorch.org/whl/cpu \
      torch==${TORCH} torchvision==${TORCHVISION}

# --only-binary: a package with no wheel for this platform must fail the build
# by name, not try to compile in an image that has no compiler.
COPY requirements-train.txt /tmp/requirements-train.txt
RUN pip install --only-binary=:all: -r /tmp/requirements-train.txt

# ImageNet weights baked in, so a training run never depends on the network.
RUN python -c "from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights as W; mobilenet_v3_small(weights=W.IMAGENET1K_V1)"

WORKDIR /ml
