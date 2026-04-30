import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from hf_exporter import web


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
    {
        "modelId": "alice/c-model",
        "author": "alice",
        "downloads": 310,
        "likes": 16,
        "pipeline_tag": "text-generation",
        "library_name": "diffusers",
    },
]


def test_search_results_and_pagination(monkeypatch):
    monkeypatch.setattr(web, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    client = TestClient(web.app)

    response = client.post("/api/search", json={"query": "llama"})
    assert response.status_code == 200
    body = response.json()
    assert body["cacheKey"]
    assert body["meta"]["totalFetched"] == 3
    assert body["meta"]["pageSize"] == 25

    page_two = client.get(
        "/api/results",
        params={
            "cache_key": body["cacheKey"],
            "page": 2,
            "page_size": 1,
            "sort_by": "downloads",
            "sort_dir": "desc",
        },
    )
    assert page_two.status_code == 200
    payload = page_two.json()
    assert payload["meta"]["page"] == 2
    assert payload["items"][0]["modelId"] == "org/a-model"


def test_filtered_export_csv(monkeypatch):
    monkeypatch.setattr(web, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    client = TestClient(web.app)

    search = client.post("/api/search", json={"query": "llama"})
    assert search.status_code == 200
    cache_key = search.json()["cacheKey"]

    export = client.get(
        "/api/export/filtered",
        params={
            "cache_key": cache_key,
            "fmt": "csv",
            "task": "text-generation",
            "min_downloads": 100,
        },
    )
    assert export.status_code == 200
    text = export.text
    assert "org/a-model" in text
    assert "alice/c-model" in text
    assert "org/b-model" not in text


def test_library_filter(monkeypatch):
    monkeypatch.setattr(web, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    client = TestClient(web.app)

    search = client.post("/api/search", json={"query": "model"})
    assert search.status_code == 200
    cache_key = search.json()["cacheKey"]

    filtered = client.get("/api/results", params={"cache_key": cache_key, "library": "keras"})
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["meta"]["totalFiltered"] == 1
    assert payload["items"][0]["modelId"] == "org/b-model"


def test_reset_clears_cache(monkeypatch):
    monkeypatch.setattr(web, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    client = TestClient(web.app)

    search = client.post("/api/search", json={"query": "llama"})
    assert search.status_code == 200
    cache_key = search.json()["cacheKey"]

    reset = client.post("/api/reset")
    assert reset.status_code == 200

    after_reset = client.get("/api/results", params={"cache_key": cache_key})
    assert after_reset.status_code == 400


def test_results_require_cache_key(monkeypatch):
    monkeypatch.setattr(web, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    client = TestClient(web.app)

    response = client.get("/api/results")
    assert response.status_code == 422


def test_export_requires_cache_key(monkeypatch):
    monkeypatch.setattr(web, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    client = TestClient(web.app)

    response = client.get("/api/export/full")
    assert response.status_code == 422


def test_expired_cache_key_returns_400(monkeypatch):
    monkeypatch.setattr(web, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    client = TestClient(web.app)

    search = client.post("/api/search", json={"query": "llama"})
    cache_key = search.json()["cacheKey"]

    with web._CACHE_LOCK:
        web._CACHE[cache_key]["created_at"] = time.time() - (web.CACHE_TTL_SECONDS + 5)

    response = client.get("/api/results", params={"cache_key": cache_key})
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_reset_single_cache_key(monkeypatch):
    monkeypatch.setattr(web, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    client = TestClient(web.app)

    search_one = client.post("/api/search", json={"query": "llama"}).json()
    search_two = client.post("/api/search", json={"query": "bert"}).json()

    reset_one = client.post("/api/reset", params={"cache_key": search_one["cacheKey"]})
    assert reset_one.status_code == 200

    first_result = client.get("/api/results", params={"cache_key": search_one["cacheKey"]})
    second_result = client.get("/api/results", params={"cache_key": search_two["cacheKey"]})
    assert first_result.status_code == 400
    assert second_result.status_code == 200


def test_note_options_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_EXPORTER_DB_PATH", str(tmp_path / "notes.db"))
    client = TestClient(web.app)

    response = client.get("/api/notes/options")
    assert response.status_code == 200
    body = response.json()
    assert "main" in body["roles"]
    assert "llm-stack" in body["categories"]
    assert "GGUF" in body["modelTypes"]


def test_create_and_list_notes(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_EXPORTER_DB_PATH", str(tmp_path / "notes.db"))
    client = TestClient(web.app)

    create_response = client.post(
        "/api/notes/org/a-model",
        json={
            "role": "main",
            "category": "llm-stack",
            "model_type": "GGUF",
            "ranking": 8,
            "note_text": "Strong local inference candidate.",
            "pros": "Fast quantized runtime",
            "cons": "Lower context window",
            "context_text": "Primary chat model for desktop stack",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["item"]["modelId"] == "org/a-model"
    assert created["summary"]["note_count"] == 1
    assert created["summary"]["average_ranking"] == 8.0

    list_response = client.get("/api/notes/org/a-model")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["role"] == "main"
    assert payload["items"][0]["category"] == "llm-stack"
    assert payload["items"][0]["modelType"] == "GGUF"


def test_create_note_requires_content(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_EXPORTER_DB_PATH", str(tmp_path / "notes.db"))
    client = TestClient(web.app)

    response = client.post(
        "/api/notes/org/a-model",
        json={
            "role": "main",
            "category": "llm-stack",
            "model_type": "GGUF",
            "ranking": 7,
            "note_text": "",
            "pros": "",
            "cons": "",
            "context_text": "",
        },
    )
    assert response.status_code == 422


def test_note_filters_affect_results(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_EXPORTER_DB_PATH", str(tmp_path / "notes.db"))
    monkeypatch.setattr(web, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    client = TestClient(web.app)

    search = client.post("/api/search", json={"query": "llama"})
    cache_key = search.json()["cacheKey"]

    client.post(
        "/api/notes/org/a-model",
        json={
            "role": "main",
            "category": "llm-stack",
            "model_type": "GGUF",
            "ranking": 9,
            "note_text": "Primary stack candidate.",
            "pros": "Reliable",
            "cons": "",
            "context_text": "",
        },
    )
    client.post(
        "/api/notes/org/b-model",
        json={
            "role": "candidate",
            "category": "image-generation",
            "model_type": "Transformers",
            "ranking": 4,
            "note_text": "Only for experiments.",
            "pros": "",
            "cons": "Weak quality",
            "context_text": "",
        },
    )

    filtered = client.get(
        "/api/results",
        params={
            "cache_key": cache_key,
            "note_role": "main",
            "min_ranking": 8,
        },
    )
    assert filtered.status_code == 200
    body = filtered.json()
    assert body["meta"]["totalFiltered"] == 1
    assert body["items"][0]["modelId"] == "org/a-model"
    assert body["items"][0]["note_count"] == 1


def test_note_role_category_or_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_EXPORTER_DB_PATH", str(tmp_path / "notes.db"))
    monkeypatch.setattr(web, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    client = TestClient(web.app)

    search = client.post("/api/search", json={"query": "llama"})
    cache_key = search.json()["cacheKey"]

    client.post(
        "/api/notes/org/a-model",
        json={
            "role": "main",
            "category": "llm-stack",
            "model_type": "GGUF",
            "ranking": 8,
            "note_text": "A",
            "pros": "",
            "cons": "",
            "context_text": "",
        },
    )
    client.post(
        "/api/notes/org/b-model",
        json={
            "role": "candidate",
            "category": "llm-stack",
            "model_type": "Transformers",
            "ranking": 7,
            "note_text": "B",
            "pros": "",
            "cons": "",
            "context_text": "",
        },
    )

    and_result = client.get(
        "/api/results",
        params={
            "cache_key": cache_key,
            "note_role": "main",
            "note_category": "llm-stack",
            "note_role_category_mode": "and",
        },
    )
    assert and_result.status_code == 200
    assert and_result.json()["meta"]["totalFiltered"] == 1

    or_result = client.get(
        "/api/results",
        params={
            "cache_key": cache_key,
            "note_role": "main",
            "note_category": "llm-stack",
            "note_role_category_mode": "or",
        },
    )
    assert or_result.status_code == 200
    assert or_result.json()["meta"]["totalFiltered"] == 2


def test_export_json_includes_notes_and_csv_stays_flat(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_EXPORTER_DB_PATH", str(tmp_path / "notes.db"))
    monkeypatch.setattr(web, "query_models", lambda query, task=None, author=None, library=None: SAMPLE_ROWS)
    client = TestClient(web.app)

    search = client.post("/api/search", json={"query": "llama"})
    cache_key = search.json()["cacheKey"]

    client.post(
        "/api/notes/org/a-model",
        json={
            "role": "main",
            "category": "llm-stack",
            "model_type": "MLX",
            "ranking": 10,
            "note_text": "Best fit for local Apple Silicon.",
            "pros": "Excellent MLX support",
            "cons": "",
            "context_text": "Laptop deployment",
        },
    )

    json_export = client.get("/api/export/full", params={"cache_key": cache_key, "fmt": "json"})
    assert json_export.status_code == 200
    payload = json.loads(json_export.text)
    assert payload[0]["note_count"] >= 1
    assert isinstance(payload[0]["notes"], list)

    csv_export = client.get("/api/export/full", params={"cache_key": cache_key, "fmt": "csv"})
    assert csv_export.status_code == 200
    assert "notes" not in csv_export.text.splitlines()[0]
    assert "note_count" in csv_export.text.splitlines()[0]


def test_note_entry_crud_and_model_bulk_delete(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_EXPORTER_DB_PATH", str(tmp_path / "notes.db"))
    client = TestClient(web.app)

    create_a = client.post(
        "/api/notes/org/a-model",
        json={
            "role": "main",
            "category": "llm-stack",
            "model_type": "GGUF",
            "ranking": 8,
            "note_text": "Alpha",
            "pros": "",
            "cons": "",
            "context_text": "",
        },
    )
    create_b = client.post(
        "/api/notes/org/a-model",
        json={
            "role": "candidate",
            "category": "llm-stack",
            "model_type": "Transformers",
            "ranking": 6,
            "note_text": "Beta",
            "pros": "",
            "cons": "",
            "context_text": "",
        },
    )

    note_id = create_a.json()["item"]["id"]
    update_response = client.put(
        f"/api/note-entries/{note_id}",
        json={"ranking": 9, "pros": "Improved", "note_text": "Updated"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["item"]["ranking"] == 9

    get_response = client.get(f"/api/note-entries/{note_id}")
    assert get_response.status_code == 200
    assert get_response.json()["pros"] == "Improved"

    delete_entry = client.delete(f"/api/note-entries/{note_id}")
    assert delete_entry.status_code == 200
    assert delete_entry.json()["modelId"] == "org/a-model"

    second_note_id = create_b.json()["item"]["id"]
    assert client.get(f"/api/note-entries/{second_note_id}").status_code == 200

    delete_model = client.delete("/api/notes/model/org/a-model")
    assert delete_model.status_code == 200
    assert delete_model.json()["deleted"] >= 1

    after_delete = client.get("/api/notes/org/a-model")
    assert after_delete.status_code == 200
    assert after_delete.json()["items"] == []


def test_records_summary_and_entries_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_EXPORTER_DB_PATH", str(tmp_path / "notes.db"))
    client = TestClient(web.app)

    client.post(
        "/api/notes/org/a-model",
        json={
            "role": "main",
            "category": "llm-stack",
            "model_type": "GGUF",
            "ranking": 8,
            "note_text": "Alpha",
            "pros": "",
            "cons": "",
            "context_text": "",
        },
    )
    client.post(
        "/api/notes/org/b-model",
        json={
            "role": "candidate",
            "category": "image-generation",
            "model_type": "Transformers",
            "ranking": 5,
            "note_text": "Bravo",
            "pros": "",
            "cons": "",
            "context_text": "",
        },
    )

    summary = client.get("/api/records/summary")
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["totalRecords"] == 2
    assert summary_payload["totalModels"] == 2
    assert isinstance(summary_payload["topModels"], list)

    entries = client.get(
        "/api/records/entries",
        params={"role": "main", "sort_by": "updated_at", "sort_dir": "desc", "page": 1, "page_size": 25},
    )
    assert entries.status_code == 200
    entries_payload = entries.json()
    assert entries_payload["meta"]["total"] == 1
    assert entries_payload["items"][0]["modelId"] == "org/a-model"


def test_records_page_route_exists():
    client = TestClient(web.app)
    response = client.get("/records")
    assert response.status_code == 200


def test_database_path_defaults_to_storage_directory(monkeypatch):
    monkeypatch.delenv("HF_EXPORTER_DB_PATH", raising=False)
    database_path = web.get_database_path()
    assert isinstance(database_path, Path)
    assert database_path.name == "hf_exporter.db"
    assert database_path.parent.name == "storage"
