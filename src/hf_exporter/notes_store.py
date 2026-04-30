from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLE_OPTIONS = [
    "main",
    "candidate",
    "fallback",
    "specialist",
    "experimental",
    "archived",
    "other",
]

CATEGORY_OPTIONS = [
    "llm-stack",
    "image-generation",
    "evaluation",
    "benchmarking",
    "deployment",
    "operations",
    "research",
    "other",
]

MODEL_TYPE_OPTIONS = [
    "MLX",
    "GGUF",
    "Transformers",
    "Diffusers",
    "ONNX",
    "Safetensors",
    "Other",
]


def get_database_path(project_id: str | None = None) -> Path:
    configured_path = os.getenv("HF_EXPORTER_DB_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    from hf_exporter.projects import get_active_project_id, get_project_db_path
    slug = project_id if project_id else get_active_project_id()
    return get_project_db_path(slug)


def get_note_options(project_id: str | None = None) -> dict[str, list[str]]:
    with _get_connection(project_id=project_id) as connection:
        custom_roles = [row["name"] for row in connection.execute("SELECT name FROM custom_roles ORDER BY name").fetchall()]
        custom_categories = [row["name"] for row in connection.execute("SELECT name FROM custom_categories ORDER BY name").fetchall()]
    
    return {
        "roles": ROLE_OPTIONS + custom_roles,
        "categories": CATEGORY_OPTIONS + custom_categories,
        "modelTypes": MODEL_TYPE_OPTIONS,
    }


def _get_connection(project_id: str | None = None) -> sqlite3.Connection:
    database_path = get_database_path(project_id=project_id)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    _initialize_database(connection)
    return connection


def initialize_project_database(project_id: str | None = None) -> Path:
    database_path = get_database_path(project_id=project_id)
    with _get_connection(project_id=project_id):
        pass
    return database_path


def _initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS model_notes (
            id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            role TEXT NOT NULL,
            category TEXT NOT NULL,
            model_type TEXT NOT NULL,
            ranking INTEGER NOT NULL,
            note_text TEXT NOT NULL DEFAULT '',
            pros TEXT NOT NULL DEFAULT '',
            cons TEXT NOT NULL DEFAULT '',
            context_text TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_model_notes_model_id
            ON model_notes(model_id);

        CREATE INDEX IF NOT EXISTS idx_model_notes_role_category
            ON model_notes(role, category);

        CREATE INDEX IF NOT EXISTS idx_model_notes_model_type
            ON model_notes(model_type);

        CREATE INDEX IF NOT EXISTS idx_model_notes_ranking
            ON model_notes(ranking);

        CREATE INDEX IF NOT EXISTS idx_model_notes_created_at
            ON model_notes(created_at DESC);

        CREATE TABLE IF NOT EXISTS custom_roles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS custom_categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

            CREATE TABLE IF NOT EXISTS labels (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS note_labels (
                note_id TEXT NOT NULL REFERENCES model_notes(id) ON DELETE CASCADE,
                label_id TEXT NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
                PRIMARY KEY (note_id, label_id)
            );

            CREATE INDEX IF NOT EXISTS idx_note_labels_label_id
                ON note_labels(label_id);
        """
    )
    try:
        connection.execute("ALTER TABLE model_notes ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    connection.commit()


def _ensure_label(connection: sqlite3.Connection, name: str) -> str:
    name = name.strip().lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    label_id = str(uuid.uuid4())
    connection.execute(
        "INSERT OR IGNORE INTO labels (id, name, created_at) VALUES (?, ?, ?)",
        (label_id, name, now_iso),
    )
    row = connection.execute("SELECT id FROM labels WHERE name = ?", (name,)).fetchone()
    return str(row["id"])


def _get_labels_for_notes(connection: sqlite3.Connection, note_ids: list[str]) -> dict[str, list[str]]:
    if not note_ids:
        return {}
    placeholders = ", ".join("?" for _ in note_ids)
    rows = connection.execute(
        f"SELECT nl.note_id, l.name FROM note_labels nl JOIN labels l ON l.id = nl.label_id WHERE nl.note_id IN ({placeholders}) ORDER BY l.name",
        note_ids,
    ).fetchall()
    result: dict[str, list[str]] = {}
    for row in rows:
        result.setdefault(str(row["note_id"]), []).append(str(row["name"]))
    return result


def has_note_filters(
    role: str | None = None,
    category: str | None = None,
    model_type: str | None = None,
    min_ranking: int | None = None,
    max_ranking: int | None = None,
    text: str | None = None,
    label: str | None = None,
) -> bool:
    return any([role, category, model_type, min_ranking is not None, max_ranking is not None, text, label])


def create_note(
    model_id: str,
    role: str,
    category: str,
    model_type: str,
    ranking: int,
    note_text: str,
    pros: str,
    cons: str,
    context_text: str,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "id": str(uuid.uuid4()),
        "model_id": model_id,
        "role": role,
        "category": category,
        "model_type": model_type,
        "ranking": int(ranking),
        "note_text": note_text.strip(),
        "pros": pros.strip(),
        "cons": cons.strip(),
        "context_text": context_text.strip(),
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    with _get_connection() as connection:
        connection.execute(
            """
            INSERT INTO model_notes (
                id, model_id, role, category, model_type, ranking,
                note_text, pros, cons, context_text, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["model_id"],
                payload["role"],
                payload["category"],
                payload["model_type"],
                payload["ranking"],
                payload["note_text"],
                payload["pros"],
                payload["cons"],
                payload["context_text"],
                payload["created_at"],
                payload["updated_at"],
            ),
        )
        if labels:
            for label_name in labels:
                label_name = label_name.strip().lower()
                if label_name:
                    label_id = _ensure_label(connection, label_name)
                    connection.execute(
                        "INSERT OR IGNORE INTO note_labels (note_id, label_id) VALUES (?, ?)",
                        (payload["id"], label_id),
                    )
        connection.commit()

    return get_note(payload["id"])


def get_note(note_id: str) -> dict[str, Any]:
    with _get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, model_id, role, category, model_type, ranking,
                   note_text, pros, cons, context_text, created_at, updated_at
            FROM model_notes
            WHERE id = ?
            """,
            (note_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Note not found: {note_id}")
        note = _row_to_note(row)
        labels_map = _get_labels_for_notes(connection, [note_id])
    note["labels"] = labels_map.get(note_id, [])
    return note


def list_notes(model_id: str) -> list[dict[str, Any]]:
    with _get_connection() as connection:
        rows = connection.execute(
            """
                 SELECT id, model_id, role, category, model_type, ranking,
                     note_text, pros, cons, context_text, created_at, updated_at
            FROM model_notes
            WHERE model_id = ?
                 ORDER BY datetime(updated_at) DESC, datetime(created_at) DESC, rowid DESC
            """,
            (model_id,),
        ).fetchall()
        notes = [_row_to_note(row) for row in rows]
        if notes:
            labels_map = _get_labels_for_notes(connection, [n["id"] for n in notes])
            for note in notes:
                note["labels"] = labels_map.get(note["id"], [])
    return notes


def list_notes_for_models(model_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not model_ids:
        return {}

    placeholders = ", ".join("?" for _ in model_ids)
    with _get_connection() as connection:
        rows = connection.execute(
            f"""
                 SELECT id, model_id, role, category, model_type, ranking,
                     note_text, pros, cons, context_text, created_at, updated_at
            FROM model_notes
            WHERE model_id IN ({placeholders})
                 ORDER BY datetime(updated_at) DESC, datetime(created_at) DESC, rowid DESC
            """,
            model_ids,
        ).fetchall()

        all_notes = [_row_to_note(row) for row in rows]
        if all_notes:
            labels_map = _get_labels_for_notes(connection, [n["id"] for n in all_notes])
            for note in all_notes:
                note["labels"] = labels_map.get(note["id"], [])

    notes_by_model: dict[str, list[dict[str, Any]]] = {mid: [] for mid in model_ids}
    for note in all_notes:
        notes_by_model.setdefault(note["modelId"], []).append(note)
    return notes_by_model


def get_note_summaries(model_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not model_ids:
        return {}

    placeholders = ", ".join("?" for _ in model_ids)
    with _get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT model_id,
                   COUNT(*) AS note_count,
                   ROUND(AVG(ranking), 2) AS average_ranking,
                   MAX(created_at) AS latest_created_at
            FROM model_notes
            WHERE model_id IN ({placeholders})
            GROUP BY model_id
            """,
            model_ids,
        ).fetchall()

    return {
        str(row["model_id"]): {
            "note_count": int(row["note_count"] or 0),
            "average_ranking": float(row["average_ranking"]) if row["average_ranking"] is not None else None,
            "latest_created_at": row["latest_created_at"],
        }
        for row in rows
    }


def find_matching_model_ids(
    role: str | None = None,
    category: str | None = None,
    model_type: str | None = None,
    min_ranking: int | None = None,
    max_ranking: int | None = None,
    text: str | None = None,
    role_category_mode: str = "and",
    label: str | None = None,
) -> set[str]:
    if not has_note_filters(role, category, model_type, min_ranking, max_ranking, text, label):
        return set()

    joins = ""
    where_clauses = ["1 = 1"]
    params: list[Any] = []

    if label:
        joins = (
            " JOIN note_labels _nl ON _nl.note_id = mn.id"
            " JOIN labels _l ON _l.id = _nl.label_id"
        )
        where_clauses.append("LOWER(_l.name) = LOWER(?)")
        params.append(label.strip())

    if role and category and role_category_mode.lower() == "or":
        where_clauses.append("(mn.role = ? OR mn.category = ?)")
        params.extend([role, category])
    else:
        if role:
            where_clauses.append("mn.role = ?")
            params.append(role)
        if category:
            where_clauses.append("mn.category = ?")
            params.append(category)

    if model_type:
        where_clauses.append("mn.model_type = ?")
        params.append(model_type)

    if min_ranking is not None:
        where_clauses.append("mn.ranking >= ?")
        params.append(min_ranking)

    if max_ranking is not None:
        where_clauses.append("mn.ranking <= ?")
        params.append(max_ranking)

    if text:
        like_value = f"%{text.strip().lower()}%"
        where_clauses.append(
            "(LOWER(mn.note_text) LIKE ? OR LOWER(mn.pros) LIKE ? OR"
            " LOWER(mn.cons) LIKE ? OR LOWER(mn.context_text) LIKE ?)"
        )
        params.extend([like_value, like_value, like_value, like_value])

    sql = (
        f"SELECT DISTINCT mn.model_id FROM model_notes mn{joins}"
        f" WHERE {' AND '.join(where_clauses)}"
    )
    with _get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()

    return {str(row["model_id"]) for row in rows}


def update_note(
    note_id: str,
    role: str | None = None,
    category: str | None = None,
    model_type: str | None = None,
    ranking: int | None = None,
    note_text: str | None = None,
    pros: str | None = None,
    cons: str | None = None,
    context_text: str | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}

    if role is not None:
        updates["role"] = role
    if category is not None:
        updates["category"] = category
    if model_type is not None:
        updates["model_type"] = model_type
    if ranking is not None:
        updates["ranking"] = int(ranking)
    if note_text is not None:
        updates["note_text"] = note_text.strip()
    if pros is not None:
        updates["pros"] = pros.strip()
    if cons is not None:
        updates["cons"] = cons.strip()
    if context_text is not None:
        updates["context_text"] = context_text.strip()

    if not updates:
        if labels is None:
            raise ValueError("No fields were provided for update")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    set_clause = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values()) + [note_id]

    with _get_connection() as connection:
        cursor = connection.execute(
            f"UPDATE model_notes SET {set_clause} WHERE id = ?",
            params,
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Note not found: {note_id}")
        if labels is not None:
            connection.execute("DELETE FROM note_labels WHERE note_id = ?", (note_id,))
            for label_name in labels:
                label_name = label_name.strip().lower()
                if label_name:
                    label_id = _ensure_label(connection, label_name)
                    connection.execute(
                        "INSERT OR IGNORE INTO note_labels (note_id, label_id) VALUES (?, ?)",
                        (note_id, label_id),
                    )
        connection.commit()

    return get_note(note_id)


def delete_note(note_id: str) -> str:
    with _get_connection() as connection:
        row = connection.execute("SELECT model_id FROM model_notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            raise ValueError(f"Note not found: {note_id}")

        model_id = str(row["model_id"])
        connection.execute("DELETE FROM model_notes WHERE id = ?", (note_id,))
        connection.commit()
    return model_id


def delete_notes_for_model(model_id: str) -> int:
    with _get_connection() as connection:
        cursor = connection.execute("DELETE FROM model_notes WHERE model_id = ?", (model_id,))
        connection.commit()
    return int(cursor.rowcount or 0)


def list_record_entries(
    role: str | None = None,
    category: str | None = None,
    model_type: str | None = None,
    text: str | None = None,
    min_ranking: int | None = None,
    max_ranking: int | None = None,
    role_category_mode: str = "and",
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 25,
    label: str | None = None,
) -> dict[str, Any]:
    where_clause, params = _build_filters(
        role=role,
        category=category,
        model_type=model_type,
        text=text,
        min_ranking=min_ranking,
        max_ranking=max_ranking,
        role_category_mode=role_category_mode,
    )

    if label:
        label_sub = (
            " AND id IN ("
            "SELECT nl.note_id FROM note_labels nl"
            " JOIN labels l ON l.id = nl.label_id"
            " WHERE LOWER(l.name) = LOWER(?)"
            ")"
        )
        where_clause = where_clause + label_sub
        params = params + [label.strip()]

    allowed_sort = {
        "model_id": "model_id",
        "role": "role",
        "category": "category",
        "model_type": "model_type",
        "ranking": "ranking",
        "created_at": "created_at",
        "updated_at": "updated_at",
    }
    sort_column = allowed_sort.get(sort_by, "updated_at")
    sort_direction = "ASC" if sort_dir.lower() == "asc" else "DESC"

    safe_page_size = max(1, min(250, page_size))
    safe_page = max(1, page)
    offset = (safe_page - 1) * safe_page_size

    with _get_connection() as connection:
        total_row = connection.execute(
            f"SELECT COUNT(*) AS total FROM model_notes WHERE {where_clause}",
            params,
        ).fetchone()
        total = int(total_row["total"] if total_row else 0)

        rows = connection.execute(
            f"""
            SELECT id, model_id, role, category, model_type, ranking,
                   note_text, pros, cons, context_text, created_at, updated_at
            FROM model_notes
            WHERE {where_clause}
            ORDER BY {sort_column} {sort_direction}, rowid DESC
            LIMIT ? OFFSET ?
            """,
            params + [safe_page_size, offset],
        ).fetchall()

        notes = [_row_to_note(row) for row in rows]
        if notes:
            labels_map = _get_labels_for_notes(connection, [n["id"] for n in notes])
            for note in notes:
                note["labels"] = labels_map.get(note["id"], [])

    total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    return {
        "items": notes,
        "meta": {
            "total": total,
            "page": min(safe_page, total_pages),
            "pageSize": safe_page_size,
            "totalPages": total_pages,
            "sortBy": sort_column,
            "sortDir": sort_direction.lower(),
        },
    }


def get_records_summary() -> dict[str, Any]:
    with _get_connection() as connection:
        total_records = int(connection.execute("SELECT COUNT(*) AS total FROM model_notes").fetchone()["total"])
        total_models = int(
            connection.execute("SELECT COUNT(DISTINCT model_id) AS total FROM model_notes").fetchone()["total"]
        )

        by_role_rows = connection.execute(
            "SELECT role AS key, COUNT(*) AS value FROM model_notes GROUP BY role ORDER BY value DESC"
        ).fetchall()
        by_category_rows = connection.execute(
            "SELECT category AS key, COUNT(*) AS value FROM model_notes GROUP BY category ORDER BY value DESC"
        ).fetchall()
        by_model_type_rows = connection.execute(
            "SELECT model_type AS key, COUNT(*) AS value FROM model_notes GROUP BY model_type ORDER BY value DESC"
        ).fetchall()
        top_model_rows = connection.execute(
            """
            SELECT model_id, COUNT(*) AS note_count, ROUND(AVG(ranking), 2) AS average_ranking
            FROM model_notes
            GROUP BY model_id
            ORDER BY note_count DESC, model_id ASC
            LIMIT 20
            """
        ).fetchall()

    return {
        "totalRecords": total_records,
        "totalModels": total_models,
        "byRole": [{"key": str(row["key"]), "value": int(row["value"])} for row in by_role_rows],
        "byCategory": [{"key": str(row["key"]), "value": int(row["value"])} for row in by_category_rows],
        "byModelType": [{"key": str(row["key"]), "value": int(row["value"])} for row in by_model_type_rows],
        "topModels": [
            {
                "modelId": str(row["model_id"]),
                "noteCount": int(row["note_count"]),
                "averageRanking": float(row["average_ranking"]) if row["average_ranking"] is not None else None,
            }
            for row in top_model_rows
        ],
    }


def _build_filters(
    role: str | None = None,
    category: str | None = None,
    model_type: str | None = None,
    text: str | None = None,
    min_ranking: int | None = None,
    max_ranking: int | None = None,
    role_category_mode: str = "and",
) -> tuple[str, list[Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []

    if role and category and role_category_mode.lower() == "or":
        clauses.append("(role = ? OR category = ?)")
        params.extend([role, category])
    else:
        if role:
            clauses.append("role = ?")
            params.append(role)
        if category:
            clauses.append("category = ?")
            params.append(category)

    if model_type:
        clauses.append("model_type = ?")
        params.append(model_type)

    if min_ranking is not None:
        clauses.append("ranking >= ?")
        params.append(min_ranking)

    if max_ranking is not None:
        clauses.append("ranking <= ?")
        params.append(max_ranking)

    if text:
        like_value = f"%{text.strip().lower()}%"
        clauses.append(
            """
            (
                LOWER(model_id) LIKE ? OR
                LOWER(note_text) LIKE ? OR
                LOWER(pros) LIKE ? OR
                LOWER(cons) LIKE ? OR
                LOWER(context_text) LIKE ?
            )
            """
        )
        params.extend([like_value, like_value, like_value, like_value, like_value])

    return " AND ".join(clauses), params


def _row_to_note(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "modelId": row["model_id"],
        "role": row["role"],
        "category": row["category"],
        "modelType": row["model_type"],
        "ranking": int(row["ranking"]),
        "noteText": row["note_text"],
        "pros": row["pros"],
        "cons": row["cons"],
        "contextText": row["context_text"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "labels": [],
    }


def get_all_roles() -> list[dict[str, Any]]:
    """Get all available roles (built-in and custom)."""
    with _get_connection() as connection:
        custom_roles = connection.execute("SELECT id, name, created_at FROM custom_roles ORDER BY name").fetchall()
    
    # Built-in roles
    builtin_roles = [{"id": None, "name": name, "created_at": None, "isBuiltin": True} for name in ROLE_OPTIONS]
    # Custom roles
    custom_list = [{"id": row["id"], "name": row["name"], "created_at": row["created_at"], "isBuiltin": False} for row in custom_roles]
    
    return builtin_roles + custom_list


def get_all_categories() -> list[dict[str, Any]]:
    """Get all available categories (built-in and custom)."""
    with _get_connection() as connection:
        custom_cats = connection.execute("SELECT id, name, created_at FROM custom_categories ORDER BY name").fetchall()
    
    # Built-in categories
    builtin_cats = [{"id": None, "name": name, "created_at": None, "isBuiltin": True} for name in CATEGORY_OPTIONS]
    # Custom categories
    custom_list = [{"id": row["id"], "name": row["name"], "created_at": row["created_at"], "isBuiltin": False} for row in custom_cats]
    
    return builtin_cats + custom_list


def add_custom_role(name: str) -> dict[str, Any]:
    """Add a new custom role."""
    name = name.strip()
    if not name:
        raise ValueError("Role name cannot be empty")
    if name in ROLE_OPTIONS:
        raise ValueError(f"Role '{name}' already exists as a built-in role")
    
    role_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    
    with _get_connection() as connection:
        try:
            connection.execute(
                "INSERT INTO custom_roles (id, name, created_at) VALUES (?, ?, ?)",
                (role_id, name, now_iso)
            )
            connection.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"Role '{name}' already exists")
    
    return {"id": role_id, "name": name, "created_at": now_iso, "isBuiltin": False}


def add_custom_category(name: str) -> dict[str, Any]:
    """Add a new custom category."""
    name = name.strip()
    if not name:
        raise ValueError("Category name cannot be empty")
    if name in CATEGORY_OPTIONS:
        raise ValueError(f"Category '{name}' already exists as a built-in category")
    
    cat_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    
    with _get_connection() as connection:
        try:
            connection.execute(
                "INSERT INTO custom_categories (id, name, created_at) VALUES (?, ?, ?)",
                (cat_id, name, now_iso)
            )
            connection.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"Category '{name}' already exists")
    
    return {"id": cat_id, "name": name, "created_at": now_iso, "isBuiltin": False}


def delete_custom_role(role_id: str) -> bool:
    """Delete a custom role."""
    with _get_connection() as connection:
        result = connection.execute("DELETE FROM custom_roles WHERE id = ?", (role_id,))
        connection.commit()
    return result.rowcount > 0


def delete_custom_category(category_id: str) -> bool:
    """Delete a custom category."""
    with _get_connection() as connection:
        result = connection.execute("DELETE FROM custom_categories WHERE id = ?", (category_id,))
        connection.commit()
    return result.rowcount > 0


def get_all_labels() -> list[str]:
    """Return all label names in alphabetical order."""
    with _get_connection() as connection:
        rows = connection.execute("SELECT name FROM labels ORDER BY name").fetchall()
    return [str(row["name"]) for row in rows]