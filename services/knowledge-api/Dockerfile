FROM python:3.12-slim

WORKDIR /service

RUN pip install uv

COPY services/knowledge-api/pyproject.toml services/knowledge-api/uv.lock ./
RUN uv sync --frozen --no-dev

COPY services/knowledge-api/app ./app
COPY services/knowledge-api/main.py ./

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
