FROM python:3.12-slim

# ffmpeg is required for audio normalization.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv for dependency management.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
# Copy both the service and its local path dependency.
COPY shared /app/shared
COPY services/ingestion /app/services/ingestion

WORKDIR /app/services/ingestion
RUN uv sync --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
