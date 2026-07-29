# Ollama for Cloud Run (NVIDIA L4 GPU) with gpt-oss:20b baked into the image so a
# scale-to-zero cold start doesn't re-download ~13 GB every time.
FROM ollama/ollama:latest

ENV OLLAMA_HOST=0.0.0.0:11434
# Keep the model resident once loaded; -1 = never unload while the instance is warm.
ENV OLLAMA_KEEP_ALIVE=-1

# Pull the model during build: start the server, pull, stop. The blobs land in
# /root/.ollama/models and are committed into this image layer.
RUN bash -c '/bin/ollama serve & SRV=$!; \
    for i in $(seq 1 30); do /bin/ollama list >/dev/null 2>&1 && break; sleep 1; done; \
    /bin/ollama pull gpt-oss:20b; \
    kill $SRV; wait $SRV 2>/dev/null || true'

EXPOSE 11434
