# Hugging Face Model Exporter

General-purpose utility for Hugging Face model research.

You can use it as a command-line tool to search Hugging Face and export results, or use the web app for richer model research workflows with notes, rankings, and project isolation.

## Features

- Hugging Face search and filtering by query, task, author, and library.
- Command-line export to CSV or JSON.
- Multi-project research workflow with isolated project storage and an active project switch.
- Per-model note-taking and ranking (1-10) for evaluation workflows.
- Rich note details: role, category, model type, labels (tags), note text, pros, cons, context, and ranking.
- Search filtering by note metadata (role/category/model type/labels/ranking/text).
- Docker Compose workflows for CLI and web usage.
- FastAPI web API plus browser UI for search, records, and project management.

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- Optional: Docker and Docker Compose

## Quick Start (CLI Only)

If you only want to search Hugging Face and export results from the command line:

```bash
uv sync
uv run hf-exporter "text-generation" --output exports/models.csv
```

JSON export example:

```bash
uv run hf-exporter "llama" --fmt json --output exports/models.json
```

## Running Locally (Without Docker)

Install dependencies:

```bash
uv sync
```

Optional authentication (recommended for higher rate limits):

```bash
export HF_TOKEN=your_token_here
```

### CLI Usage

Basic usage:

```bash
uv run hf-exporter [OPTIONS] QUERY
```

Examples:

```bash
uv run hf-exporter "gpt" --task text-generation --author openai --output exports/gpt_models.csv
uv run hf-exporter "llama" --library transformers --note-role main --note-category llm-stack --min-ranking 7 --output exports/llama_main_candidates.csv
```

Run as a Python module:

```bash
uv run python -m hf_exporter "text-generation" --output exports/models.csv
```

Shell completion:

```bash
uv run python -m hf_exporter --install-completion
```

### Web UI + API

Start the server:

```bash
uv run uvicorn hf_exporter.web:app --host 0.0.0.0 --port 8000 --reload
```

Open:

- `http://localhost:8000` (search + export UI)
- `http://localhost:8000/records` (records management UI)
- `http://localhost:8000/projects` (project management UI)

## Running With Docker Compose

This repository includes three Compose services: interactive CLI, direct CLI, and web app.

### 1) Interactive CLI Container

```bash
docker compose run --rm hf-exporter
```

Inside the container, use the `hf` helper:

```bash
hf "text-generation"
hf "llama" --fmt json
hf "gpt" --task text-generation --author openai
```

If `--output` is omitted, `hf` writes to `/output/models.csv` or `/output/models.json`.
The `/output` directory is mapped to local `exports/`.

### 2) Direct CLI Service

```bash
docker compose run --rm hf-exporter-cli "text-generation" --output /output/models.csv
docker compose run --rm hf-exporter-cli "llama" --fmt json --output /output/models.json
```

### 3) Web Service

```bash
docker compose up hf-exporter-web
```

Open `http://localhost:8111` in your browser.

Authentication passthrough:

```bash
export HF_TOKEN=your_token_here
docker compose run --rm hf-exporter
```

## Notes, Rankings, and Research Metadata

Each model can have multiple evaluation records with:

- Role
- Category
- Model type
- Labels (tags)
- Ranking (1-10)
- Note text
- Pros
- Cons
- Context

These notes are queryable and filterable in both the web app and CLI export workflow.

## API Highlights

- `POST /api/search`: run live Hugging Face search.
- `GET /api/results`: fetch filtered/sorted/paginated cached results.
- `GET /api/export/full`: export full cached result set (`fmt=csv|json`).
- `GET /api/export/filtered`: export currently filtered result set (`fmt=csv|json`).
- `GET /api/notes/{model_id}` and `POST /api/notes/{model_id}`: read/add model notes.
- `GET/PUT/DELETE /api/note-entries/{note_id}`: note entry CRUD.
- `GET /api/records/entries` and `GET /api/records/summary`: records management and summaries.
- `GET/POST /api/projects`, `POST /api/projects/{project_id}/activate`, `DELETE /api/projects/{project_id}`.

## Storage

Project-scoped SQLite storage:

- `storage/projects/default/project.db`
- `storage/projects/{slug}/project.db`

The app bootstraps a `default` project automatically.
If legacy `storage/hf_exporter.db` exists, it is migrated once into `storage/projects/default/project.db` when appropriate.

Environment variables:

- `HF_TOKEN`: optional Hugging Face token.
- `HF_EXPORTER_DB_PATH`: direct DB path override (primarily CLI flow).
- `HF_EXPORTER_STORAGE_DIR`: base storage directory for project-aware web flow.

`storage/` is durable local app state and is intentionally ignored by git.

## Development

```bash
uv run ruff check
uv run pytest
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Code Of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
