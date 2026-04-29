import time

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
