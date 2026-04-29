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

## Web API And Browser UI

Start the web app locally:

```bash
uv run uvicorn hf_exporter.web:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000` in your browser.

What the web app supports:

- Live Hugging Face search by `query` (plus optional `task` and `author`).
- Server-side cached result set after each search.
- Sortable table columns.
- Server-side filtering by `task`, `author`, `library`, `min/max downloads`, and `min/max likes`.
- Pagination with default page size of `25`.
- Export full search result set as JSON or CSV.
- Export current filtered result set as JSON or CSV.
- Reset action to clear cached results and table state.

Main API endpoints:

- `POST /api/search`: runs live query against Hugging Face and returns first page of data.
- `GET /api/results`: returns filtered/sorted/paginated rows from cached search results.
- `GET /api/export/full`: exports all fetched rows as `fmt=json|csv`.
- `GET /api/export/filtered`: exports filtered rows as `fmt=json|csv`.
- `POST /api/reset`: clears current cached result set.

## Development

Run lint and tests:

```bash
uv run ruff check --fix
uv run pytest
```

## Docker

Build the image:

```bash
docker build -t hf-exporter .
```

Use Docker Compose for the recommended workflows.

Interactive shell mode:

```bash
docker compose run --rm hf-exporter
```

This starts a normal `bash` shell inside the container. In that shell, use the `hf` helper command:

```bash
hf "text-generation"
hf "llama" --fmt json
hf "gpt" --task text-generation --author openai
```

`hf` behavior:

- Runs the project CLI from inside the container.
- Writes output to `/output`, which is mapped to the local `exports/` directory.
- If `--output` is omitted, it chooses a default file name based on format:
- CSV output defaults to `/output/models.csv`.
- JSON output defaults to `/output/models.json`.
- If you provide `--output`, your path is used instead.

Examples with explicit output:

```bash
hf "text-generation" --output /output/text-generation.csv
hf "llama" --fmt json --output /output/llama.json
```

Direct CLI mode without an interactive shell:

```bash
docker compose run --rm hf-exporter-cli "text-generation" --output /output/models.csv
docker compose run --rm hf-exporter-cli "llama" --fmt json --output /output/models.json
```

Run the browser API service in Docker Compose:

```bash
docker compose up hf-exporter-web
```

Then open `http://localhost:8000` in your browser.

Authentication in Docker:

```bash
export HF_TOKEN=your_token_here
docker compose run --rm hf-exporter
```

The Compose services pass `HF_TOKEN` through if it is set in your shell. If it is unset, the container still starts and runs without authentication.
