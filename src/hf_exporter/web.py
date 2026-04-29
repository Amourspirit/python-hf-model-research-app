from __future__ import annotations

import os
import tempfile
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from hf_exporter.service import (
    MODEL_COLUMNS,
    export_rows,
    filter_rows,
    paginate_rows,
    query_models,
    sort_rows,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"

app = FastAPI(title="HF Model Exporter Web")

CACHE_TTL_SECONDS = 900

_CACHE_LOCK = Lock()
_CACHE: dict[str, dict[str, object]] = {}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    task: str | None = None
    author: str | None = None
    library: str | None = None


class TableState(BaseModel):
    task: str | None = None
    author: str | None = None
    library: str | None = None
    min_downloads: int | None = None
    max_downloads: int | None = None
    min_likes: int | None = None
    max_likes: int | None = None
    sort_by: str = "downloads"
    sort_dir: Literal["asc", "desc"] = "desc"
    page: int = 1
    page_size: int = 25


def _now_epoch() -> float:
    return time.time()


def _purge_expired_cache() -> None:
    cutoff = _now_epoch() - CACHE_TTL_SECONDS
    with _CACHE_LOCK:
        expired_keys = [
            key for key, entry in _CACHE.items() if float(entry.get("created_at", 0.0)) < cutoff
        ]
        for key in expired_keys:
            _CACHE.pop(key, None)


def _set_cache(rows: list[dict], query: str) -> str:
    cache_key = str(uuid.uuid4())
    with _CACHE_LOCK:
        _CACHE[cache_key] = {
            "rows": rows,
            "query": query,
            "created_at": _now_epoch(),
        }
    return cache_key


def _get_cached_rows(cache_key: str) -> list[dict]:
    if not cache_key:
        raise HTTPException(status_code=400, detail="cache_key is required.")

    _purge_expired_cache()
    with _CACHE_LOCK:
        entry = _CACHE.get(cache_key)

    if not entry:
        raise HTTPException(status_code=400, detail="Invalid or expired cache_key. Run a search first.")

    return list(entry.get("rows", []))


def _clear_cache(cache_key: str | None = None) -> None:
    with _CACHE_LOCK:
        if cache_key:
            _CACHE.pop(cache_key, None)
            return
        _CACHE.clear()


def _build_table_payload(rows: list[dict], state: TableState) -> dict:
    filtered = filter_rows(
        rows,
        task=state.task,
        author=state.author,
        library=state.library,
        min_downloads=state.min_downloads,
        max_downloads=state.max_downloads,
        min_likes=state.min_likes,
        max_likes=state.max_likes,
    )
    sorted_rows = sort_rows(filtered, state.sort_by, state.sort_dir)
    page_rows, page, total_pages = paginate_rows(sorted_rows, state.page, state.page_size)

    return {
        "items": page_rows,
        "meta": {
            "totalFetched": len(rows),
            "totalFiltered": len(filtered),
            "page": page,
            "pageSize": max(1, state.page_size),
            "totalPages": total_pages,
            "sortBy": state.sort_by,
            "sortDir": state.sort_dir,
        },
    }


def _export_response(
    rows: list[dict],
    fmt: Literal["csv", "json"],
    prefix: str,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    suffix = ".csv" if fmt == "csv" else ".json"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        output_path = temp_file.name

    export_rows(rows, output_path, fmt)
    filename = f"{prefix}.{fmt}"

    def cleanup_file(path: str) -> None:
        if os.path.exists(path):
            os.remove(path)

    background_tasks.add_task(cleanup_file, output_path)

    media_type = "text/csv" if fmt == "csv" else "application/json"
    return FileResponse(output_path, media_type=media_type, filename=filename)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_FILE)


@app.post("/api/search")
def search_models(payload: SearchRequest) -> dict:
    _purge_expired_cache()
    rows = query_models(payload.query, payload.task, payload.author, payload.library)
    cache_key = _set_cache(rows, payload.query)

    state = TableState(task=payload.task, author=payload.author, library=payload.library, page=1)
    payload_data = _build_table_payload(rows, state)
    payload_data["cacheKey"] = cache_key
    return payload_data


@app.get("/api/results")
def get_results(
    cache_key: str = Query(min_length=1),
    task: str | None = None,
    author: str | None = None,
    library: str | None = None,
    min_downloads: int | None = Query(default=None, ge=0),
    max_downloads: int | None = Query(default=None, ge=0),
    min_likes: int | None = Query(default=None, ge=0),
    max_likes: int | None = Query(default=None, ge=0),
    sort_by: str = Query(default="downloads"),
    sort_dir: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=250),
) -> dict:
    rows = _get_cached_rows(cache_key)

    if sort_by not in MODEL_COLUMNS:
        raise HTTPException(status_code=400, detail=f"Invalid sort_by field: {sort_by}")

    state = TableState(
        task=task,
        author=author,
        library=library,
        min_downloads=min_downloads,
        max_downloads=max_downloads,
        min_likes=min_likes,
        max_likes=max_likes,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    payload_data = _build_table_payload(rows, state)
    payload_data["cacheKey"] = cache_key
    return payload_data


@app.post("/api/reset")
def reset_results(cache_key: str | None = None) -> dict:
    _clear_cache(cache_key)
    return {"status": "ok"}


@app.get("/api/export/full")
def export_full(
    background_tasks: BackgroundTasks,
    cache_key: str = Query(min_length=1),
    fmt: Literal["csv", "json"] = "json",
) -> FileResponse:
    rows = _get_cached_rows(cache_key)

    return _export_response(rows, fmt, "hf_export_full", background_tasks)


@app.get("/api/export/filtered")
def export_filtered(
    background_tasks: BackgroundTasks,
    cache_key: str = Query(min_length=1),
    fmt: Literal["csv", "json"] = "json",
    task: str | None = None,
    author: str | None = None,
    library: str | None = None,
    min_downloads: int | None = Query(default=None, ge=0),
    max_downloads: int | None = Query(default=None, ge=0),
    min_likes: int | None = Query(default=None, ge=0),
    max_likes: int | None = Query(default=None, ge=0),
    sort_by: str = Query(default="downloads"),
    sort_dir: Literal["asc", "desc"] = "desc",
) -> FileResponse:
    rows = _get_cached_rows(cache_key)

    filtered_rows = filter_rows(
        rows,
        task=task,
        author=author,
        library=library,
        min_downloads=min_downloads,
        max_downloads=max_downloads,
        min_likes=min_likes,
        max_likes=max_likes,
    )
    sorted_rows = sort_rows(filtered_rows, sort_by, sort_dir)

    return _export_response(sorted_rows, fmt, "hf_export_filtered", background_tasks)
