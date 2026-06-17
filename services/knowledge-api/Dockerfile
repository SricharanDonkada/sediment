FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/uv

WORKDIR /app
COPY shared /app/shared
COPY services/knowledge-api /app/services/knowledge-api

WORKDIR /app/services/knowledge-api
RUN uv sync --no-dev

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
