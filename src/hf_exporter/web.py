from __future__ import annotations

import os
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from hf_exporter.notes_store import (
    CATEGORY_OPTIONS,
    MODEL_TYPE_OPTIONS,
    ROLE_OPTIONS,
    add_custom_category,
    add_custom_role,
    create_note,
    delete_custom_category,
    delete_custom_role,
    delete_note,
    delete_notes_for_model,
    find_matching_model_ids,
    get_all_categories,
    get_all_roles,
    get_database_path,
    get_note,
    get_note_options,
    get_note_summaries,
    get_records_summary,
    has_note_filters,
    list_notes,
    list_notes_for_models,
    list_record_entries,
    update_note,
)
from hf_exporter.projects import (
    bootstrap_default_project,
    create_project,
    delete_project,
    get_active_project_id,
    get_project,
    list_projects,
    set_active_project,
)
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
RECORDS_FILE = STATIC_DIR / "records.html"
PROJECTS_FILE = STATIC_DIR / "projects.html"

@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    bootstrap_default_project()
    yield


app = FastAPI(title="HF Model Exporter Web", lifespan=_lifespan)

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
    note_role: str | None = None
    note_category: str | None = None
    note_model_type: str | None = None
    note_text: str | None = None
    min_ranking: int | None = None
    max_ranking: int | None = None
    note_role_category_mode: Literal["and", "or"] = "or"
    sort_by: str = "downloads"
    sort_dir: Literal["asc", "desc"] = "desc"
    page: int = 1
    page_size: int = 25


class NoteCreateRequest(BaseModel):
    role: str
    category: str
    model_type: str
    ranking: int = Field(ge=1, le=10)
    note_text: str = ""
    pros: str = ""
    cons: str = ""
    context_text: str = ""

    @model_validator(mode="after")
    def validate_payload(self) -> "NoteCreateRequest":
        opts = get_note_options()
        if self.role not in opts["roles"]:
            raise ValueError(f"Invalid role: {self.role!r}")
        if self.category not in opts["categories"]:
            raise ValueError(f"Invalid category: {self.category!r}")
        if self.model_type not in MODEL_TYPE_OPTIONS:
            raise ValueError("Invalid model_type")
        if not any([
            self.note_text.strip(),
            self.pros.strip(),
            self.cons.strip(),
            self.context_text.strip(),
        ]):
            raise ValueError("At least one content field is required")
        return self


class NoteUpdateRequest(BaseModel):
    role: str | None = None
    category: str | None = None
    model_type: str | None = None
    ranking: int | None = Field(default=None, ge=1, le=10)
    note_text: str | None = None
    pros: str | None = None
    cons: str | None = None
    context_text: str | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "NoteUpdateRequest":
        opts = get_note_options()
        if self.role is not None and self.role not in opts["roles"]:
            raise ValueError(f"Invalid role: {self.role!r}")
        if self.category is not None and self.category not in opts["categories"]:
            raise ValueError(f"Invalid category: {self.category!r}")
        if self.model_type is not None and self.model_type not in MODEL_TYPE_OPTIONS:
            raise ValueError("Invalid model_type")
        if not any(
            value is not None
            for value in [
                self.role,
                self.category,
                self.model_type,
                self.ranking,
                self.note_text,
                self.pros,
                self.cons,
                self.context_text,
            ]
        ):
            raise ValueError("At least one field is required")
        return self


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


def _attach_note_summary(row: dict[str, Any], summary: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(row)
    payload["note_count"] = int(summary.get("note_count", 0)) if summary else 0
    payload["average_ranking"] = summary.get("average_ranking") if summary else None
    return payload


def _filter_rows_by_notes(rows: list[dict[str, Any]], state: TableState) -> list[dict[str, Any]]:
    if not has_note_filters(
        state.note_role,
        state.note_category,
        state.note_model_type,
        state.min_ranking,
        state.max_ranking,
        state.note_text,
    ):
        return rows

    matched_model_ids = find_matching_model_ids(
        role=state.note_role,
        category=state.note_category,
        model_type=state.note_model_type,
        min_ranking=state.min_ranking,
        max_ranking=state.max_ranking,
        text=state.note_text,
        role_category_mode=state.note_role_category_mode,
    )

    if not matched_model_ids:
        return []

    return [row for row in rows if row.get("modelId") in matched_model_ids]


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
    note_filtered = _filter_rows_by_notes(filtered, state)
    sorted_rows = sort_rows(note_filtered, state.sort_by, state.sort_dir)
    page_rows, page, total_pages = paginate_rows(sorted_rows, state.page, state.page_size)
    summaries = get_note_summaries([str(row.get("modelId", "")) for row in page_rows])
    items = [_attach_note_summary(row, summaries.get(str(row.get("modelId", "")))) for row in page_rows]

    return {
        "items": items,
        "meta": {
            "totalFetched": len(rows),
            "totalFiltered": len(note_filtered),
            "page": page,
            "pageSize": max(1, state.page_size),
            "totalPages": total_pages,
            "sortBy": state.sort_by,
            "sortDir": state.sort_dir,
            "databasePath": str(get_database_path()),
            "activeProject": get_active_project_id(),
        },
    }


def _prepare_export_rows(rows: list[dict[str, Any]], fmt: Literal["csv", "json"]) -> list[dict[str, Any]]:
    model_ids = [str(row.get("modelId", "")) for row in rows]
    summaries = get_note_summaries(model_ids)
    notes_by_model = list_notes_for_models(model_ids) if fmt == "json" else {}

    prepared_rows = []
    for row in rows:
        model_id = str(row.get("modelId", ""))
        payload = _attach_note_summary(row, summaries.get(model_id))
        if fmt == "json":
            payload["notes"] = notes_by_model.get(model_id, [])
        prepared_rows.append(payload)
    return prepared_rows


def _export_response(
    rows: list[dict],
    fmt: Literal["csv", "json"],
    prefix: str,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    suffix = ".csv" if fmt == "csv" else ".json"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        output_path = temp_file.name

    export_rows(_prepare_export_rows(rows, fmt), output_path, fmt)
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


@app.get("/records")
def records_page() -> FileResponse:
    return FileResponse(RECORDS_FILE)


@app.get("/projects")
def projects_page() -> FileResponse:
    return FileResponse(PROJECTS_FILE)


# ---------------------------------------------------------------------------
# Project API
# ---------------------------------------------------------------------------

class ProjectCreateRequest(BaseModel):
    displayName: str = Field(min_length=1, max_length=120)
    slug: str | None = None
    autoActivate: bool = True


@app.get("/api/projects")
def api_list_projects() -> dict[str, Any]:
    return {"items": list_projects()}


@app.post("/api/projects", status_code=201)
def api_create_project(payload: ProjectCreateRequest) -> dict[str, Any]:
    try:
        return create_project(
            display_name=payload.displayName,
            slug=payload.slug,
            auto_activate=payload.autoActivate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/active")
def api_get_active_project() -> dict[str, Any]:
    slug = get_active_project_id()
    try:
        return get_project(slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}")
def api_get_project(project_id: str) -> dict[str, Any]:
    try:
        return get_project(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/activate")
def api_activate_project(project_id: str) -> dict[str, Any]:
    try:
        return set_active_project(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/projects/{project_id}")
def api_delete_project(project_id: str) -> dict[str, str]:
    try:
        delete_project(project_id)
    except ValueError as exc:
        status = 400 if "default" in str(exc) else 404
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"status": "ok"}


@app.get("/api/notes/options")
def note_options() -> dict[str, list[str]]:
    return get_note_options()


@app.get("/api/notes/{model_id:path}")
def get_model_notes(model_id: str) -> dict[str, Any]:
    notes = list_notes(model_id)
    summary = get_note_summaries([model_id]).get(model_id, {"note_count": 0, "average_ranking": None})
    return {"items": notes, "summary": summary}


@app.post("/api/notes/{model_id:path}", status_code=201)
def create_model_note(model_id: str, payload: NoteCreateRequest) -> dict[str, Any]:
    note = create_note(
        model_id=model_id,
        role=payload.role,
        category=payload.category,
        model_type=payload.model_type,
        ranking=payload.ranking,
        note_text=payload.note_text,
        pros=payload.pros,
        cons=payload.cons,
        context_text=payload.context_text,
    )
    notes = list_notes(model_id)
    summary = get_note_summaries([model_id]).get(model_id, {"note_count": 0, "average_ranking": None})
    return {"item": note, "items": notes, "summary": summary}


@app.get("/api/note-entries/{note_id}")
def get_note_entry(note_id: str) -> dict[str, Any]:
    try:
        return get_note(note_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/note-entries/{note_id}")
def update_note_entry(note_id: str, payload: NoteUpdateRequest) -> dict[str, Any]:
    try:
        item = update_note(
            note_id=note_id,
            role=payload.role,
            category=payload.category,
            model_type=payload.model_type,
            ranking=payload.ranking,
            note_text=payload.note_text,
            pros=payload.pros,
            cons=payload.cons,
            context_text=payload.context_text,
        )
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    model_id = str(item["modelId"])
    notes = list_notes(model_id)
    summary = get_note_summaries([model_id]).get(model_id, {"note_count": 0, "average_ranking": None})
    return {"item": item, "items": notes, "summary": summary}


@app.delete("/api/note-entries/{note_id}")
def delete_note_entry(note_id: str) -> dict[str, Any]:
    try:
        model_id = delete_note(note_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    summary = get_note_summaries([model_id]).get(model_id, {"note_count": 0, "average_ranking": None})
    return {"status": "ok", "modelId": model_id, "summary": summary}


@app.delete("/api/notes/model/{model_id:path}")
def delete_model_note_entries(model_id: str) -> dict[str, Any]:
    deleted = delete_notes_for_model(model_id)
    return {"status": "ok", "modelId": model_id, "deleted": deleted}


@app.get("/api/records/summary")
def records_summary() -> dict[str, Any]:
    summary = get_records_summary()
    summary["databasePath"] = str(get_database_path())
    summary["activeProject"] = get_active_project_id()
    return summary


@app.get("/api/records/entries")
def records_entries(
    role: str | None = None,
    category: str | None = None,
    model_type: str | None = None,
    text: str | None = None,
    min_ranking: int | None = Query(default=None, ge=1, le=10),
    max_ranking: int | None = Query(default=None, ge=1, le=10),
    role_category_mode: Literal["and", "or"] = "and",
    sort_by: Literal[
        "updated_at",
        "created_at",
        "model_id",
        "role",
        "category",
        "model_type",
        "ranking",
    ] = "updated_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=250),
) -> dict[str, Any]:
    payload = list_record_entries(
        role=role,
        category=category,
        model_type=model_type,
        text=text,
        min_ranking=min_ranking,
        max_ranking=max_ranking,
        role_category_mode=role_category_mode,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    payload["meta"]["databasePath"] = str(get_database_path())
    payload["meta"]["activeProject"] = get_active_project_id()
    return payload


@app.get("/api/roles")
def list_roles() -> dict[str, Any]:
    """Get all available roles (built-in and custom)."""
    return {"items": get_all_roles()}


@app.post("/api/roles", status_code=201)
def create_role(payload: dict[str, str]) -> dict[str, Any]:
    """Create a new custom role."""
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Role name is required")
    try:
        return add_custom_role(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/roles/{role_id}")
def remove_role(role_id: str) -> dict[str, str]:
    """Delete a custom role."""
    if not delete_custom_role(role_id):
        raise HTTPException(status_code=404, detail="Role not found")
    return {"message": "Role deleted"}


@app.get("/api/categories")
def list_categories() -> dict[str, Any]:
    """Get all available categories (built-in and custom)."""
    return {"items": get_all_categories()}


@app.post("/api/categories", status_code=201)
def create_category(payload: dict[str, str]) -> dict[str, Any]:
    """Create a new custom category."""
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")
    try:
        return add_custom_category(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/categories/{category_id}")
def remove_category(category_id: str) -> dict[str, str]:
    """Delete a custom category."""
    if not delete_custom_category(category_id):
        raise HTTPException(status_code=404, detail="Category not found")
    return {"message": "Category deleted"}


@app.get("/api/models/{model_id:path}")
def get_model_metadata(model_id: str) -> dict[str, Any]:
    """Fetch HuggingFace model metadata by model ID."""
    try:
        from hf_exporter.service import get_api, normalize_model
        api = get_api()
        model_info = api.model_info(model_id)
        return normalize_model(model_info)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Model not found: {str(e)}")


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
    note_role: str | None = None,
    note_category: str | None = None,
    note_model_type: str | None = None,
    note_text: str | None = None,
    min_ranking: int | None = Query(default=None, ge=1, le=10),
    max_ranking: int | None = Query(default=None, ge=1, le=10),
    note_role_category_mode: Literal["and", "or"] = "or",
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
        note_role=note_role,
        note_category=note_category,
        note_model_type=note_model_type,
        note_text=note_text,
        min_ranking=min_ranking,
        max_ranking=max_ranking,
        note_role_category_mode=note_role_category_mode,
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
    note_role: str | None = None,
    note_category: str | None = None,
    note_model_type: str | None = None,
    note_text: str | None = None,
    min_ranking: int | None = Query(default=None, ge=1, le=10),
    max_ranking: int | None = Query(default=None, ge=1, le=10),
    note_role_category_mode: Literal["and", "or"] = "or",
    sort_by: str = Query(default="downloads"),
    sort_dir: Literal["asc", "desc"] = "desc",
) -> FileResponse:
    rows = _get_cached_rows(cache_key)

    state = TableState(
        task=task,
        author=author,
        library=library,
        min_downloads=min_downloads,
        max_downloads=max_downloads,
        min_likes=min_likes,
        max_likes=max_likes,
        note_role=note_role,
        note_category=note_category,
        note_model_type=note_model_type,
        note_text=note_text,
        min_ranking=min_ranking,
        max_ranking=max_ranking,
        note_role_category_mode=note_role_category_mode,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    filtered_rows = filter_rows(
        rows,
        task=state.task,
        author=state.author,
        library=state.library,
        min_downloads=state.min_downloads,
        max_downloads=state.max_downloads,
        min_likes=state.min_likes,
        max_likes=state.max_likes,
    )
    note_filtered_rows = _filter_rows_by_notes(filtered_rows, state)
    sorted_rows = sort_rows(note_filtered_rows, sort_by, sort_dir)

    return _export_response(sorted_rows, fmt, "hf_export_filtered", background_tasks)
