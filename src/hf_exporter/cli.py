import typer
import os
from huggingface_hub import HfApi
import pandas as pd
from rich.console import Console
from rich.progress import Progress

try:
    from huggingface_hub import ModelFilter
except ImportError:
    ModelFilter = None

app = typer.Typer()
console = Console()
api = HfApi()

@app.command()
def export(
    query: str,
    task: str = None,
    author: str = None,
    output: str = "models.csv",
    fmt: str = "csv",  # csv|json
):
    """Export HF models matching query."""
    if os.getenv("HF_TOKEN"):
        api.login(token=os.getenv("HF_TOKEN"))
    
    filters = {}
    if task:
        filters["task"] = task
    if author:
        filters["author"] = author
    
    with Progress() as progress:
        task = progress.add_task("[green]Fetching models...", total=None)
        model_filter = ModelFilter(**filters) if ModelFilter and filters else (filters or None)
        models = list(api.list_models(search=query, filter=model_filter))
        progress.remove_task(task)
    
    console.print(f"[green]Found {len(models)} models[/green]")
    
    data = [{"modelId": m.modelId, "downloads": getattr(m, 'downloads', 0),
             "likes": getattr(m, 'likes', 0), "pipeline_tag": getattr(m, 'pipeline_tag', None),
             "library_name": getattr(m, 'library_name', None)} for m in models]
    
    df = pd.DataFrame(data)
    if fmt == "csv":
        df.to_csv(output, index=False)
        console.print(f"[blue]Exported CSV to {output}[/blue]")
    else:
        df.to_json(output, orient="records", indent=2)
        console.print(f"[blue]Exported JSON to {output}[/blue]")
