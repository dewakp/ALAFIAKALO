# Ollama for Cloud Run (NVIDIA L4 GPU) with the models baked into the image so a
# scale-to-zero cold start doesn't re-download them every time.
#
# BOTH models must be here. Only gpt-oss:20b was baked, so every food-photo
# analysis in production failed: /ai/vision asks Ollama for the vision model and
# Ollama answers /api/chat with 404 for a model it does not have. Chat worked,
# which made the service look healthy while vision had never worked at all.
#
# The vision model is llava, NOT moondream -- moondream is a grounding model and
# answers the food schema with bounding boxes, so every photo fails (CLAUDE.md
# §3a). It must match OLLAMA_VISION_MODEL, which deploy.sh sets explicitly.
FROM ollama/ollama:latest

ENV OLLAMA_HOST=0.0.0.0:11434
# Keep the model resident once loaded; -1 = never unload while the instance is warm.
ENV OLLAMA_KEEP_ALIVE=-1

# Pull the model during build: start the server, pull, stop. The blobs land in
# /root/.ollama/models and are committed into this image layer.
RUN bash -c '/bin/ollama serve & SRV=$!; \
    for i in $(seq 1 30); do /bin/ollama list >/dev/null 2>&1 && break; sleep 1; done; \
    /bin/ollama pull gpt-oss:20b; \
    /bin/ollama pull llava; \
    /bin/ollama list; \
    kill $SRV; wait $SRV 2>/dev/null || true'

EXPOSE 11434
