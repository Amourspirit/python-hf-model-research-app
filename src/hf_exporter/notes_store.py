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


def get_database_path() -> Path:
    configured_path = os.getenv("HF_EXPORTER_DB_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path(__file__).resolve().parents[2] / "storage" / "hf_exporter.db"


def get_note_options() -> dict[str, list[str]]:
    return {
        "roles": ROLE_OPTIONS,
        "categories": CATEGORY_OPTIONS,
        "modelTypes": MODEL_TYPE_OPTIONS,
    }


def _get_connection() -> sqlite3.Connection:
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    _initialize_database(connection)
    return connection


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
        """
    )
    try:
        connection.execute("ALTER TABLE model_notes ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    connection.commit()


def has_note_filters(
    role: str | None = None,
    category: str | None = None,
    model_type: str | None = None,
    min_ranking: int | None = None,
    max_ranking: int | None = None,
    text: str | None = None,
) -> bool:
    return any([role, category, model_type, min_ranking is not None, max_ranking is not None, text])


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
    return _row_to_note(row)


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
    return [_row_to_note(row) for row in rows]


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

    notes_by_model: dict[str, list[dict[str, Any]]] = {model_id: [] for model_id in model_ids}
    for row in rows:
        note = _row_to_note(row)
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
) -> set[str]:
    if not has_note_filters(role, category, model_type, min_ranking, max_ranking, text):
        return set()

    query = ["SELECT DISTINCT model_id FROM model_notes WHERE 1 = 1"]
    params: list[Any] = []

    if role and category and role_category_mode.lower() == "or":
        query.append("AND (role = ? OR category = ?)")
        params.extend([role, category])
    else:
        if role:
            query.append("AND role = ?")
            params.append(role)

        if category:
            query.append("AND category = ?")
            params.append(category)

    if model_type:
        query.append("AND model_type = ?")
        params.append(model_type)

    if min_ranking is not None:
        query.append("AND ranking >= ?")
        params.append(min_ranking)

    if max_ranking is not None:
        query.append("AND ranking <= ?")
        params.append(max_ranking)

    if text:
        like_value = f"%{text.strip().lower()}%"
        query.append(
            """
            AND (
                LOWER(note_text) LIKE ? OR
                LOWER(pros) LIKE ? OR
                LOWER(cons) LIKE ? OR
                LOWER(context_text) LIKE ?
            )
            """
        )
        params.extend([like_value, like_value, like_value, like_value])

    with _get_connection() as connection:
        rows = connection.execute("\n".join(query), params).fetchall()

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
        raise ValueError("No fields were provided for update")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    set_clause = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values()) + [note_id]

    with _get_connection() as connection:
        cursor = connection.execute(
            f"UPDATE model_notes SET {set_clause} WHERE id = ?",
            params,
        )
        connection.commit()

    if cursor.rowcount == 0:
        raise ValueError(f"Note not found: {note_id}")

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

    total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    return {
        "items": [_row_to_note(row) for row in rows],
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
    }