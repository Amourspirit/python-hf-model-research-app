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
            created_at TEXT NOT NULL
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
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with _get_connection() as connection:
        connection.execute(
            """
            INSERT INTO model_notes (
                id, model_id, role, category, model_type, ranking,
                note_text, pros, cons, context_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        connection.commit()

    return {
        "id": payload["id"],
        "modelId": payload["model_id"],
        "role": payload["role"],
        "category": payload["category"],
        "modelType": payload["model_type"],
        "ranking": payload["ranking"],
        "noteText": payload["note_text"],
        "pros": payload["pros"],
        "cons": payload["cons"],
        "contextText": payload["context_text"],
        "createdAt": payload["created_at"],
    }


def list_notes(model_id: str) -> list[dict[str, Any]]:
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, model_id, role, category, model_type, ranking,
                   note_text, pros, cons, context_text, created_at
            FROM model_notes
            WHERE model_id = ?
            ORDER BY datetime(created_at) DESC, rowid DESC
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
                   note_text, pros, cons, context_text, created_at
            FROM model_notes
            WHERE model_id IN ({placeholders})
            ORDER BY datetime(created_at) DESC, rowid DESC
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
) -> set[str]:
    if not has_note_filters(role, category, model_type, min_ranking, max_ranking, text):
        return set()

    query = ["SELECT DISTINCT model_id FROM model_notes WHERE 1 = 1"]
    params: list[Any] = []

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
    }