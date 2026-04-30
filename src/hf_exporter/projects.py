from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

BASE_STORAGE_DIR = Path(__file__).resolve().parents[2] / "storage"
PROJECTS_DIR = BASE_STORAGE_DIR / "projects"
ACTIVE_FILE = PROJECTS_DIR / "_active"
LEGACY_DB_PATH = BASE_STORAGE_DIR / "hf_exporter.db"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,49}$")
_LOCK = Lock()


def _meta_path(slug: str) -> Path:
    return PROJECTS_DIR / slug / "meta.json"


def _db_path(slug: str) -> Path:
    return PROJECTS_DIR / slug / "project.db"


def _read_meta(slug: str) -> dict[str, Any]:
    path = _meta_path(slug)
    if path.exists():
        return json.loads(path.read_text())
    return {"id": slug, "displayName": slug, "createdAt": ""}


def _write_meta(slug: str, meta: dict[str, Any]) -> None:
    _meta_path(slug).write_text(json.dumps(meta, indent=2))


def get_project_db_path(slug: str) -> Path:
    return _db_path(slug)


def get_active_project_id() -> str:
    if ACTIVE_FILE.exists():
        slug = ACTIVE_FILE.read_text().strip()
        if slug and (PROJECTS_DIR / slug).is_dir():
            return slug
    return "default"


def set_active_project(slug: str) -> dict[str, Any]:
    if not (PROJECTS_DIR / slug).is_dir():
        raise ValueError(f"Project not found: {slug!r}")
    with _LOCK:
        ACTIVE_FILE.write_text(slug)
    return get_project(slug)


def get_project(slug: str) -> dict[str, Any]:
    if not (PROJECTS_DIR / slug).is_dir():
        raise ValueError(f"Project not found: {slug!r}")
    meta = _read_meta(slug)
    return {
        "id": slug,
        "displayName": meta.get("displayName", slug),
        "createdAt": meta.get("createdAt", ""),
        "databasePath": str(_db_path(slug)),
        "isActive": get_active_project_id() == slug,
    }


def list_projects() -> list[dict[str, Any]]:
    if not PROJECTS_DIR.exists():
        return []
    active_id = get_active_project_id()
    projects = []
    for entry in sorted(PROJECTS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        meta = _read_meta(entry.name)
        projects.append({
            "id": entry.name,
            "displayName": meta.get("displayName", entry.name),
            "createdAt": meta.get("createdAt", ""),
            "databasePath": str(_db_path(entry.name)),
            "isActive": active_id == entry.name,
        })
    return projects


def create_project(display_name: str, slug: str | None = None) -> dict[str, Any]:
    display_name = display_name.strip()
    if not display_name:
        raise ValueError("Display name cannot be empty")

    if slug is None:
        slug = re.sub(r"[^a-z0-9_-]", "-", display_name.lower())
        slug = re.sub(r"-+", "-", slug).strip("-")
        slug = slug[:50] or "project"

    slug = slug.lower().strip()
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"Slug {slug!r} is invalid. Use lowercase letters, digits, hyphens, underscores; "
            "must start with a letter or digit; max 50 chars."
        )

    project_dir = PROJECTS_DIR / slug
    with _LOCK:
        if project_dir.exists():
            raise ValueError(f"Project with slug {slug!r} already exists")
        project_dir.mkdir(parents=True, exist_ok=False)
        now_iso = datetime.now(timezone.utc).isoformat()
        meta = {"id": slug, "displayName": display_name, "createdAt": now_iso}
        _write_meta(slug, meta)

    return {
        "id": slug,
        "displayName": display_name,
        "createdAt": now_iso,
        "databasePath": str(_db_path(slug)),
        "isActive": False,
    }


def delete_project(slug: str) -> None:
    if slug == "default":
        raise ValueError("Cannot delete the default project")
    project_dir = PROJECTS_DIR / slug
    if not project_dir.is_dir():
        raise ValueError(f"Project not found: {slug!r}")
    with _LOCK:
        active = get_active_project_id()
        shutil.rmtree(project_dir)
        if active == slug:
            ACTIVE_FILE.write_text("default")


def bootstrap_default_project() -> None:
    """Ensure the default project exists. Migrate legacy DB if present."""
    default_dir = PROJECTS_DIR / "default"
    default_dir.mkdir(parents=True, exist_ok=True)

    meta_file = _meta_path("default")
    if not meta_file.exists():
        _write_meta("default", {
            "id": "default",
            "displayName": "Default",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        })

    default_db = _db_path("default")
    if not default_db.exists() and LEGACY_DB_PATH.exists():
        shutil.copy2(LEGACY_DB_PATH, default_db)

    if not ACTIVE_FILE.exists():
        ACTIVE_FILE.write_text("default")
