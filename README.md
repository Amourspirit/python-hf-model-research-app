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
- Hugging Face Hub interactive shell (`hf-shell`) for downloading models with smart storage defaults.
- Docker Compose workflows for CLI, Hugging Face Hub shell, and web usage.
- Optional `.env` file support for all Compose services.
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

## Global Access (Linux and macOS)

To run the app from any directory (without `cd` into this project), install the CLI globally from the local project path:

```bash
uv tool install /absolute/path/to/hf-model-exporter
```

If needed, add `~/.local/bin` to your shell `PATH`.

Linux (bash):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

macOS (zsh):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

You can now use the CLI from anywhere:

```bash
hf-exporter "text-generation" --output ~/Downloads/models.csv
hf-exporter "llama" --fmt json --output ~/Downloads/models.json
```

To start the web app from anywhere, create a small wrapper script:

```bash
mkdir -p ~/.local/bin
cat > ~/.local/bin/hf-exporter-web <<'EOF'
#!/usr/bin/env bash
uv run --directory /absolute/path/to/hf-model-exporter uvicorn hf_exporter.web:app --host 0.0.0.0 --port 8000 --reload "$@"
EOF
chmod +x ~/.local/bin/hf-exporter-web
```

Then run:

```bash
hf-exporter-web
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

This repository includes four Compose services: interactive CLI, direct CLI, Hugging Face Hub shell, and web app.

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

### 4) Hugging Face Hub Shell

An interactive shell pre-configured for Hugging Face Hub downloads. Cache and download directories are mapped to `storage/hf-shell/` on the host.

```bash
docker compose run --rm hf-shell
```

Inside the shell, use the `hf` command:

```bash
hf download mlx-community/clip-vit-base-patch32
hf download google/gemma-3-1b-it --include "*.safetensors"
hf download --help
```

When no `--local-dir` is given, files are saved to a nested path derived from the repo ID:

```
storage/hf-shell/downloads/<owner>/<repo-name>/
```

To use an explicit destination:

```bash
hf download mlx-community/clip-vit-base-patch32 --local-dir /storage/hf-shell/downloads/my-clip
```

To run a single download without entering the shell:

```bash
docker compose run --rm hf-shell hf download mlx-community/clip-vit-base-patch32
```

To pass a token at runtime:

```bash
HF_TOKEN=hf_xxx docker compose run --rm hf-shell
```

## Environment Configuration

All Compose services load `.env` from the project root when it exists (optional — no error if absent). A documented template is provided at [`.env.example`](.env.example).

```bash
cp .env.example .env
```

Key variables:

| Variable | Default | Description |
|---|---|---|
| `HF_TOKEN` | _(unset)_ | Hugging Face User Access Token |
| `HF_HUB_OFFLINE` | `False` | Disable all network calls; use local cache only |
| `HF_HUB_DISABLE_TELEMETRY` | `True` | Disable telemetry across the HF Python ecosystem |
| `HF_SHELL_DOWNLOAD_DIR` | `/storage/hf-shell/downloads` | Root for implicit `hf download` destinations |
| `HF_SHELL_CACHE_DIR` | `/storage/hf-shell/cache` | Default `--cache-dir` passed to `hf download` |
| `HF_HOME` | `/storage/hf-shell` | HF home; parent of cache, assets, and token file |
| `HF_HUB_ETAG_TIMEOUT` | `10` | Seconds before metadata requests time out |
| `HF_HUB_DOWNLOAD_TIMEOUT` | `10` | Seconds before download requests time out |

See [`.env.example`](.env.example) for the full list including Xet transfer variables.

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

Hugging Face Hub shell storage:

- `storage/hf-shell/downloads/<owner>/<repo>/` — downloaded model files (nested by repo ID)
- `storage/hf-shell/cache/` — HF hub cache (symlinked blobs and snapshots)
- `storage/hf-shell/assets/` — downstream-library asset cache
- `storage/hf-shell/token` — active HF token file

Environment variables:

- `HF_TOKEN`: optional Hugging Face token.
- `HF_EXPORTER_DB_PATH`: direct DB path override (primarily CLI flow).
- `HF_EXPORTER_STORAGE_DIR`: base storage directory for project-aware web flow.
- `HF_SHELL_DOWNLOAD_DIR`: root for implicit `hf download` destinations.
- `HF_SHELL_CACHE_DIR`: default `--cache-dir` passed to `hf download`.

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
