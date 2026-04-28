# HuggingFace Model Exporter

CLI tool to export full lists of Hugging Face models matching a query to CSV or JSON.

## Requirements

- Python 3.12+
- uv (Astral)

## Install Dependencies

```bash
uv sync
```

## Usage

Export to CSV (default format):

```bash
uv run hf-exporter export "text-generation" --output models.csv
```

Export to JSON:

```bash
uv run hf-exporter export "llama" --fmt json --output models.json
```

Filter by task and author:

```bash
uv run hf-exporter export "gpt" --task text-generation --author openai --output gpt_models.csv
```

Run as a Python module:

```bash
uv run python -m hf_exporter export "text-generation" --output models.csv
```

## Auth

Set `HF_TOKEN` to increase rate limits:

```bash
export HF_TOKEN=your_token_here
```

## Development

Run lint and tests:

```bash
uv run ruff check --fix
uv run pytest
```

## Docker

Build image:

```bash
docker build -t hf-exporter .
```
