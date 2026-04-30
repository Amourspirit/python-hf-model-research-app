# HuggingFace Model Exporter

CLI tool to export full lists of Hugging Face models matching a query to CSV or JSON.

The web app also supports persistent SQLite-backed model evaluation notes and rankings stored under the project `storage/` directory.

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

Filter by library and note metadata:

```bash
uv run hf-exporter export "llama" --library transformers --note-role main --note-category llm-stack --min-ranking 7 --output exports/llama_main_candidates.csv
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
- `--library TEXT`: Filter results by library name (for example `transformers`).
- `--output TEXT` (default: `models.csv`): Output file path for the exported results.
- `--fmt TEXT` (default: `csv`): Output format. Use `csv` or `json`.
- `--note-role TEXT`: Filter to models with notes matching the selected role.
- `--note-category TEXT`: Filter to models with notes matching the selected category.
- `--note-model-type TEXT`: Filter to models with notes matching the selected model type.
- `--min-ranking INTEGER`: Minimum note ranking filter (1-10).
- `--max-ranking INTEGER`: Maximum note ranking filter (1-10).
- `--note-text TEXT`: Free-text note filter across notes/pros/cons/context.
- `--install-completion`: Install shell tab-completion for your current shell (for example `bash`, `zsh`, or `fish`). This is a one-time setup command that adds completion support so the CLI can autocomplete flags and arguments when you press `Tab`.
- `--show-completion`: Print shell completion script so you can copy/customize it manually.
- `--help`: Show command help and exit.

Export behavior with notes:

- CSV exports include flat note summary columns (`note_count`, `average_ranking`).
- JSON exports include both summary columns and nested `notes` per model.

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

Routes:

- `http://localhost:8000`: Search and filter Hugging Face models.
- `http://localhost:8000/records`: Full records management (list/filter/create/update/delete entries, plus model-level bulk delete).

What the web app supports:

- Live Hugging Face search by `query` (plus optional `task` and `author`).
- Server-side cached result set after each search.
- Sortable table columns.
- Server-side filtering by `task`, `author`, `library`, `min/max downloads`, and `min/max likes`.
- Server-side filtering by note role, note category, model type, ranking range, and note text.
- Role/category note filtering on the search page supports explicit OR matching.
- Pagination with default page size of `25`.
- Export full search result set as JSON or CSV.
- Export current filtered result set as JSON or CSV.
- Reset action to clear cached results and table state.
- Per-model evaluation entries with role, category, model type, notes, pros, cons, context, and 1-10 ranking.
- Entry-level CRUD in the records manager plus model-level bulk delete.

Main API endpoints:

- `POST /api/search`: runs live query against Hugging Face and returns first page of data.
- `GET /api/results`: returns filtered/sorted/paginated rows from cached search results.
- `GET /api/export/full`: exports all fetched rows as `fmt=json|csv`.
- `GET /api/export/filtered`: exports filtered rows as `fmt=json|csv`.
- `POST /api/reset`: clears current cached result set.
- `GET /api/notes/options`: returns allowed values for note role, category, and model type.
- `GET /api/notes/{model_id}`: returns note history and summary for a model.
- `POST /api/notes/{model_id}`: appends a new evaluation entry for a model.
- `GET /api/note-entries/{note_id}`: returns a single evaluation entry.
- `PUT /api/note-entries/{note_id}`: updates an existing evaluation entry.
- `DELETE /api/note-entries/{note_id}`: deletes an evaluation entry.
- `DELETE /api/notes/model/{model_id}`: deletes all entries for a model.
- `GET /api/records/entries`: lists/filter/sorts/paginates record entries.
- `GET /api/records/summary`: aggregate counts and top-model summaries for sidebars.

## Persistent Storage

SQLite note data is stored in `storage/hf_exporter.db` by default for local runs.

Override the database path with:

```bash
export HF_EXPORTER_DB_PATH=/custom/path/hf_exporter.db
```

The `storage/` directory is intentionally gitignored and should be treated as local durable application state.

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

Docker Compose also mounts the local `storage/` directory into `/storage` and sets `HF_EXPORTER_DB_PATH=/storage/hf_exporter.db`, so note data survives container restarts.
