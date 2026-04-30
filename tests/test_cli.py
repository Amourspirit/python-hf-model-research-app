import json

from typer.testing import CliRunner

from hf_exporter import cli


runner = CliRunner()


SAMPLE_ROWS = [
    {
        "modelId": "org/a-model",
        "author": "org",
        "downloads": 120,
        "likes": 8,
        "pipeline_tag": "text-generation",
        "library_name": "transformers",
    },
    {
        "modelId": "org/b-model",
        "author": "org",
        "downloads": 30,
        "likes": 24,
        "pipeline_tag": "text-classification",
        "library_name": "keras",
    },
]


def test_export_csv_includes_note_summary(monkeypatch, tmp_path):
    output_file = tmp_path / "models.csv"

    monkeypatch.setattr(cli, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    monkeypatch.setattr(
        cli,
        "get_note_summaries",
        lambda model_ids: {
            "org/a-model": {"note_count": 2, "average_ranking": 8.5},
            "org/b-model": {"note_count": 0, "average_ranking": None},
        },
    )
    monkeypatch.setattr(cli, "list_notes_for_models", lambda model_ids: {})

    result = runner.invoke(
        cli.app,
        ["llama", "--output", str(output_file), "--fmt", "csv"],
    )

    assert result.exit_code == 0
    content = output_file.read_text()
    assert "note_count" in content
    assert "average_ranking" in content
    assert "org/a-model" in content


def test_export_with_note_filters(monkeypatch, tmp_path):
    output_file = tmp_path / "filtered.csv"

    monkeypatch.setattr(cli, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    monkeypatch.setattr(cli, "get_note_summaries", lambda model_ids: {})
    monkeypatch.setattr(cli, "list_notes_for_models", lambda model_ids: {})
    monkeypatch.setattr(cli, "find_matching_model_ids", lambda **kwargs: {"org/a-model"})

    result = runner.invoke(
        cli.app,
        [
            "llama",
            "--output",
            str(output_file),
            "--fmt",
            "csv",
            "--note-role",
            "main",
            "--min-ranking",
            "7",
        ],
    )

    assert result.exit_code == 0
    content = output_file.read_text()
    assert "org/a-model" in content
    assert "org/b-model" not in content


def test_export_json_includes_notes(monkeypatch, tmp_path):
    output_file = tmp_path / "models.json"

    monkeypatch.setattr(cli, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    monkeypatch.setattr(
        cli,
        "get_note_summaries",
        lambda model_ids: {"org/a-model": {"note_count": 1, "average_ranking": 9.0}},
    )
    monkeypatch.setattr(
        cli,
        "list_notes_for_models",
        lambda model_ids: {
            "org/a-model": [
                {
                    "id": "n1",
                    "modelId": "org/a-model",
                    "role": "main",
                    "category": "llm-stack",
                    "modelType": "GGUF",
                    "ranking": 9,
                    "noteText": "Strong fit",
                    "pros": "Fast",
                    "cons": "",
                    "contextText": "",
                    "createdAt": "2026-04-29T00:00:00+00:00",
                }
            ]
        },
    )

    result = runner.invoke(
        cli.app,
        ["llama", "--output", str(output_file), "--fmt", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(output_file.read_text())
    assert isinstance(payload, list)
    assert payload[0]["notes"]
    assert "note_count" in payload[0]


def test_export_rejects_invalid_ranking_range(monkeypatch, tmp_path):
    output_file = tmp_path / "invalid.csv"
    monkeypatch.setattr(cli, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)

    result = runner.invoke(
        cli.app,
        [
            "llama",
            "--output",
            str(output_file),
            "--fmt",
            "csv",
            "--min-ranking",
            "9",
            "--max-ranking",
            "5",
        ],
    )

    assert result.exit_code != 0
    assert "min_ranking cannot be greater" in result.output
