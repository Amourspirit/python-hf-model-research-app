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
uv run hf-exporter export "gpt" --task text-generation --author openai --output exports/gpt_models.csv
```

Run as a Python module:

Note: module invocation is single-command style (`python -m hf_exporter QUERY ...`).

```bash
uv run python -m hf_exporter "text-generation" --output exports/models.csv
```

### CLI Parameters

The module command is:

```bash
uv run python -m hf_exporter [OPTIONS] QUERY
```

Supported argument and options:

- `QUERY` (required argument): Search text used to find matching Hugging Face models.
- `--task TEXT`: Filter results by pipeline task (for example `text-generation`).
- `--author TEXT`: Filter results to models published by a specific author or organization.
- `--output TEXT` (default: `models.csv`): Output file path for the exported results.
- `--fmt TEXT` (default: `csv`): Output format. Use `csv` or `json`.
- `--install-completion`: Install shell tab-completion for your current shell (for example `bash`, `zsh`, or `fish`). This is a one-time setup command that adds completion support so the CLI can autocomplete flags and arguments when you press `Tab`.
- `--show-completion`: Print shell completion script so you can copy/customize it manually.
- `--help`: Show command help and exit.

`--install-completion` details:

- It does not run an export. It only configures shell completion.
- It installs completion for the shell you are currently using.
- After running it, restart your terminal session (or reload your shell profile) to enable completions.

Install completion:

```bash
uv run python -m hf_exporter --install-completion
```

Example usage after completion is installed:

```bash
# Type this, then press Tab to complete available options
uv run python -m hf_exporter --

# Type this, then press Tab to complete the option name (for example --output)
uv run python -m hf_exporter "text-generation" --ou
```

## Auth

Set `HF_TOKEN` to increase rate limits:

Set in `.env` file or:

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
