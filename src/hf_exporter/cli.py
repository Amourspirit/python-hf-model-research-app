from typing import Any

import typer
from rich.console import Console
from rich.progress import Progress

from hf_exporter.notes_store import (
    find_matching_model_ids,
    get_note_summaries,
    has_note_filters,
    list_notes_for_models,
)
from hf_exporter.service import export_rows, query_models

app = typer.Typer()
console = Console()


def _prepare_export_rows(rows: list[dict[str, Any]], fmt: str) -> list[dict[str, Any]]:
    model_ids = [str(row.get("modelId", "")) for row in rows]
    summaries = get_note_summaries(model_ids)
    notes_by_model = list_notes_for_models(model_ids) if fmt == "json" else {}

    prepared_rows = []
    for row in rows:
        model_id = str(row.get("modelId", ""))
        payload = dict(row)
        summary = summaries.get(model_id)
        payload["note_count"] = int(summary.get("note_count", 0)) if summary else 0
        payload["average_ranking"] = summary.get("average_ranking") if summary else None
        if fmt == "json":
            payload["notes"] = notes_by_model.get(model_id, [])
        prepared_rows.append(payload)
    return prepared_rows


@app.command()
def export(
    query: str,
    task: str = None,
    author: str = None,
    library: str = None,
    output: str = "models.csv",
    fmt: str = "csv",  # csv|json
    note_role: str = None,
    note_category: str = None,
    note_model_type: str = None,
    min_ranking: int = typer.Option(default=None, min=1, max=10),
    max_ranking: int = typer.Option(default=None, min=1, max=10),
    note_text: str = None,
):
    """Export HF models matching query."""

    format_name = fmt.lower()
    if format_name not in {"csv", "json"}:
        raise typer.BadParameter("fmt must be either 'csv' or 'json'.", param_hint="fmt")

    if min_ranking is not None and max_ranking is not None and min_ranking > max_ranking:
        raise typer.BadParameter(
            "min_ranking cannot be greater than max_ranking.",
            param_hint="min_ranking",
        )

    with Progress() as progress:
        progress_task = progress.add_task("[green]Fetching models...", total=None)
        rows = query_models(query, task, author, library)
        progress.remove_task(progress_task)

    fetched_count = len(rows)

    if has_note_filters(
        role=note_role,
        category=note_category,
        model_type=note_model_type,
        min_ranking=min_ranking,
        max_ranking=max_ranking,
        text=note_text,
    ):
        matched_model_ids = find_matching_model_ids(
            role=note_role,
            category=note_category,
            model_type=note_model_type,
            min_ranking=min_ranking,
            max_ranking=max_ranking,
            text=note_text,
        )
        rows = [row for row in rows if row.get("modelId") in matched_model_ids]

    console.print(f"[green]Found {fetched_count} models; exporting {len(rows)}[/green]")

    export_rows(_prepare_export_rows(rows, format_name), output, format_name)

    if format_name == "csv":
        console.print(f"[blue]Exported CSV to {output}[/blue]")
    else:
        console.print(f"[blue]Exported JSON to {output}[/blue]")
