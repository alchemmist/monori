FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY common ./common
COPY ci ./ci
COPY server/pyproject.toml ./server/pyproject.toml

RUN python -m pip install --no-cache-dir "uv==0.11.26" && \
    uv sync --frozen --group ci --no-dev

ENV PATH="/app/.venv/bin:${PATH}"
