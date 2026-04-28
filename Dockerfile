FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
WORKDIR /app
COPY pyproject.toml README.md ./
RUN uv sync --no-dev
COPY src/ src/
ENTRYPOINT ["uv", "run", "hf-exporter"]
