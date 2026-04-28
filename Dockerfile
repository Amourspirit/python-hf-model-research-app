FROM python:3.12-slim
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"
WORKDIR /app
COPY pyproject.toml README.md ./
RUN uv sync --frozen --no-dev
COPY src/ src/
ENTRYPOINT ["uv", "run", "hf-exporter"]
