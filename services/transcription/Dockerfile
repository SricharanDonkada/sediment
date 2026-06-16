FROM python:3.12-slim

# ffmpeg is required by faster-whisper / torchaudio for audio decoding.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv for dependency management. Pinned for reproducible builds.
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/uv

WORKDIR /app
# Copy both the service and its local path dependency.
COPY shared /app/shared
COPY services/transcription /app/services/transcription

WORKDIR /app/services/transcription
RUN uv sync --no-dev

# Models are downloaded at runtime and cached in this dir (mounted as a volume).
ENV HF_HOME=/models

CMD ["uv", "run", "python", "-m", "app.worker"]
