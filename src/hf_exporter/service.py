from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from huggingface_hub import HfApi

try:
    from huggingface_hub import ModelFilter
except ImportError:  # pragma: no cover
    ModelFilter = None

load_dotenv()

MODEL_COLUMNS = [
    "modelId",
    "author",
    "downloads",
    "likes",
    "pipeline_tag",
    "library_name",
]


@lru_cache(maxsize=4)
def _build_api(token: str) -> HfApi:
    api = HfApi()
    if token:
        api.login(token=token)
    return api


def get_api() -> HfApi:
    token = os.getenv("HF_TOKEN", "")
    return _build_api(token)


def query_models(
    query: str,
    task: str | None = None,
    author: str | None = None,
    library: str | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, str] = {}
    if task:
        filters["task"] = task
    if author:
        filters["author"] = author
    if library:
        filters["library"] = library

    model_filter = ModelFilter(**filters) if ModelFilter and filters else (filters or None)
    models = list(get_api().list_models(search=query, filter=model_filter))
    return [normalize_model(model) for model in models]


def normalize_model(model: Any) -> dict[str, Any]:
    return {
        "modelId": getattr(model, "modelId", ""),
        "author": getattr(model, "author", None),
        "downloads": int(getattr(model, "downloads", 0) or 0),
        "likes": int(getattr(model, "likes", 0) or 0),
        "pipeline_tag": getattr(model, "pipeline_tag", None),
        "library_name": getattr(model, "library_name", None),
    }


def filter_rows(
    rows: list[dict[str, Any]],
    task: str | None = None,
    author: str | None = None,
    library: str | None = None,
    min_downloads: int | None = None,
    max_downloads: int | None = None,
    min_likes: int | None = None,
    max_likes: int | None = None,
) -> list[dict[str, Any]]:
    filtered = rows

    if task:
        task_text = task.strip().lower()
        filtered = [r for r in filtered if (r.get("pipeline_tag") or "").lower() == task_text]

    if author:
        author_text = author.strip().lower()
        filtered = [r for r in filtered if author_text in (str(r.get("author") or "").lower())]

    if library:
        library_text = library.strip().lower()
        filtered = [r for r in filtered if library_text in (str(r.get("library_name") or "").lower())]

    if min_downloads is not None:
        filtered = [r for r in filtered if int(r.get("downloads") or 0) >= min_downloads]

    if max_downloads is not None:
        filtered = [r for r in filtered if int(r.get("downloads") or 0) <= max_downloads]

    if min_likes is not None:
        filtered = [r for r in filtered if int(r.get("likes") or 0) >= min_likes]

    if max_likes is not None:
        filtered = [r for r in filtered if int(r.get("likes") or 0) <= max_likes]

    return filtered


def sort_rows(rows: list[dict[str, Any]], sort_by: str, sort_dir: str = "asc") -> list[dict[str, Any]]:
    if sort_by not in MODEL_COLUMNS:
        sort_by = "modelId"

    reverse = sort_dir.lower() == "desc"

    def key_fn(row: dict[str, Any]) -> Any:
        value = row.get(sort_by)
        if value is None:
            return "" if sort_by in {"modelId", "author", "pipeline_tag", "library_name"} else 0
        return value

    return sorted(rows, key=key_fn, reverse=reverse)


def paginate_rows(rows: list[dict[str, Any]], page: int, page_size: int) -> tuple[list[dict[str, Any]], int, int]:
    safe_page_size = max(1, page_size)
    total = len(rows)
    total_pages = max(1, math.ceil(total / safe_page_size))
    safe_page = min(max(1, page), total_pages)

    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    return rows[start:end], safe_page, total_pages


def export_rows(rows: list[dict[str, Any]], output: str, fmt: str) -> None:
    format_name = fmt.lower()

    if format_name == "csv":
        csv_rows = []
        for row in rows:
            csv_row = dict(row)
            csv_row.pop("notes", None)
            csv_rows.append(csv_row)
        dataframe = pd.DataFrame(csv_rows)
        dataframe.to_csv(output, index=False)
        return

    dataframe = pd.DataFrame(rows)
    dataframe.to_json(output, orient="records", indent=2)
