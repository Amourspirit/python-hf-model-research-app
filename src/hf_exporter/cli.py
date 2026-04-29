import typer
from rich.console import Console
from rich.progress import Progress
from hf_exporter.service import export_rows, query_models

app = typer.Typer()
console = Console()

@app.command()
def export(
    query: str,
    task: str = None,
    author: str = None,
    output: str = "models.csv",
    fmt: str = "csv",  # csv|json
):
    """Export HF models matching query."""

    with Progress() as progress:
        progress_task = progress.add_task("[green]Fetching models...", total=None)
        rows = query_models(query, task, author)
        progress.remove_task(progress_task)

    console.print(f"[green]Found {len(rows)} models[/green]")

    format_name = fmt.lower()
    export_rows(rows, output, format_name)

    if format_name == "csv":
        console.print(f"[blue]Exported CSV to {output}[/blue]")
    else:
        console.print(f"[blue]Exported JSON to {output}[/blue]")
