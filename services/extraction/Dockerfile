FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/uv

WORKDIR /app
COPY shared /app/shared
COPY services/extraction /app/services/extraction

WORKDIR /app/services/extraction
RUN uv sync --no-dev

CMD ["uv", "run", "python", "-m", "app.worker"]
