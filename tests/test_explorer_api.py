"""Tests for the explorer API endpoints added in v0.4."""

from __future__ import annotations

import pytest
from aiohttp import ClientSession
from aiohttp.test_utils import TestServer

from inspect_dataset._view.server import create_app


@pytest.fixture
async def server():
    """Start a test server with an empty (explorer-only) app."""
    app = create_app()
    srv = TestServer(app)
    await srv.start_server()
    yield srv
    await srv.close()


async def get(server: TestServer, path: str):
    async with ClientSession() as session:
        return await session.get(server.make_url(path))


async def post(server: TestServer, path: str, **kwargs):
    async with ClientSession() as session:
        return await session.post(server.make_url(path), **kwargs)


# ── Discovery endpoints ────────────────────────────────────────────────────


async def test_discover_cached_returns_list(server):
    resp = await get(server, "/api/discover/cached")
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data, list)
    for item in data[:5]:
        assert "repo_id" in item
        assert "size_on_disk" in item
        assert "splits" in item
        assert "configs" in item
        assert isinstance(item["configs"], list)


async def test_discover_cached_basic_returns_list(server):
    resp = await get(server, "/api/discover/cached-basic")
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data, list)
    for item in data[:5]:
        assert "repo_id" in item
        assert "size_on_disk" in item
        # Basic listing is scan-only: no splits/configs until cached-meta
        assert "splits" not in item
        assert "configs" not in item


async def test_discover_cached_meta_missing_param(server):
    resp = await get(server, "/api/discover/cached-meta")
    assert resp.status == 400
    body = await resp.json()
    assert "error" in body


async def test_discover_cached_meta_unknown_dataset(server):
    resp = await get(
        server,
        "/api/discover/cached-meta?dataset=definitely-does-not-exist/xyzzy",
    )
    assert resp.status == 404


async def test_discover_cached_meta_for_cached_dataset(server):
    basic_resp = await get(server, "/api/discover/cached-basic")
    datasets = await basic_resp.json()
    if not datasets:
        pytest.skip("No datasets in the local HF cache")

    repo_id = datasets[0]["repo_id"]
    resp = await get(server, f"/api/discover/cached-meta?dataset={repo_id}")
    assert resp.status == 200
    meta = await resp.json()
    assert isinstance(meta["splits"], list)
    assert isinstance(meta["configs"], list)
    assert len(meta["splits"]) > 0


async def test_discover_tasks_returns_list(server):
    resp = await get(server, "/api/discover/tasks")
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data, list)
    for item in data[:5]:
        assert "name" in item
        assert "package" in item


async def test_discover_hf_schema_missing_param(server):
    resp = await get(server, "/api/discover/hf-schema")
    assert resp.status == 400
    body = await resp.json()
    assert "error" in body


async def test_discover_hf_schema_unknown_dataset(server):
    resp = await get(
        server,
        "/api/discover/hf-schema?dataset=definitely-does-not-exist/xyzzy",
    )
    assert resp.status in (200, 404)


# ── Explorer session endpoints ─────────────────────────────────────────────


async def test_explore_load_missing_source(server):
    resp = await post(server, "/api/explore/load", json={})
    assert resp.status == 400
    body = await resp.json()
    assert "error" in body


async def test_explore_load_hf_dataset(server):
    """Load a small known-cached dataset and verify session response."""
    resp = await post(
        server,
        "/api/explore/load",
        json={
            "source": "math-ai/aime26",
            "source_type": "hf",
            "split": "test",
            "limit": 5,
        },
    )
    assert resp.status == 200, await resp.text()
    body = await resp.json()
    assert "session_id" in body
    assert body["source"] == "math-ai/aime26"
    assert body["total"] <= 5
    assert isinstance(body["columns"], list)
    assert len(body["columns"]) > 0


async def test_explore_schema_endpoint(server):
    load_resp = await post(
        server,
        "/api/explore/load",
        json={
            "source": "math-ai/aime26",
            "source_type": "hf",
            "split": "test",
            "limit": 5,
        },
    )
    assert load_resp.status == 200
    session_id = (await load_resp.json())["session_id"]

    schema_resp = await get(server, f"/api/explore/{session_id}/schema")
    assert schema_resp.status == 200
    body = await schema_resp.json()
    assert body["session_id"] == session_id
    assert "schema" in body
    assert isinstance(body["schema"], list)
    assert len(body["schema"]) > 0
    field = body["schema"][0]
    assert "name" in field
    assert "type" in field


async def test_explore_records_endpoint(server):
    load_resp = await post(
        server,
        "/api/explore/load",
        json={
            "source": "math-ai/aime26",
            "source_type": "hf",
            "split": "test",
            "limit": 10,
        },
    )
    assert load_resp.status == 200
    session_id = (await load_resp.json())["session_id"]

    records_resp = await get(server, f"/api/explore/{session_id}/records?offset=0&limit=5")
    assert records_resp.status == 200
    body = await records_resp.json()
    assert body["offset"] == 0
    assert body["limit"] == 5
    assert isinstance(body["rows"], list)
    assert len(body["rows"]) <= 5
    for row in body["rows"]:
        assert "__index" in row


async def test_explore_record_detail(server):
    load_resp = await post(
        server,
        "/api/explore/load",
        json={
            "source": "math-ai/aime26",
            "source_type": "hf",
            "split": "test",
            "limit": 3,
        },
    )
    assert load_resp.status == 200
    session_id = (await load_resp.json())["session_id"]

    detail_resp = await get(server, f"/api/explore/{session_id}/record/0")
    assert detail_resp.status == 200
    body = await detail_resp.json()
    assert body["index"] == 0
    assert "record" in body
    assert "images" in body
    assert "files" in body


async def test_explore_record_out_of_range(server):
    load_resp = await post(
        server,
        "/api/explore/load",
        json={
            "source": "math-ai/aime26",
            "source_type": "hf",
            "split": "test",
            "limit": 3,
        },
    )
    session_id = (await load_resp.json())["session_id"]
    resp = await get(server, f"/api/explore/{session_id}/record/9999")
    assert resp.status == 404


async def test_explore_unknown_session(server):
    resp = await get(server, "/api/explore/does-not-exist/schema")
    assert resp.status == 404


async def test_datasets_endpoint_empty(server):
    """With no findings dirs loaded, /api/datasets returns empty list."""
    resp = await get(server, "/api/datasets")
    assert resp.status == 200
    assert await resp.json() == []


# ── Scanner endpoints ──────────────────────────────────────────────────────


async def test_list_scanners(server):
    resp = await get(server, "/api/scanners")
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data, list)
    kinds = {s["kind"] for s in data}
    assert kinds == {"static", "llm"}
    for s in data:
        assert "name" in s
        assert "description" in s
    names = {s["name"] for s in data}
    assert "answer_length" in names
    assert "ambiguity" in names


async def _load_session(server) -> str:
    resp = await post(
        server,
        "/api/explore/load",
        json={
            "source": "math-ai/aime26",
            "source_type": "hf",
            "split": "test",
            "limit": 5,
        },
    )
    assert resp.status == 200, await resp.text()
    return (await resp.json())["session_id"]


async def test_explore_scan_selected_static(server):
    session_id = await _load_session(server)
    resp = await post(
        server,
        f"/api/explore/{session_id}/scan",
        json={"scanners": ["answer_length", "duplicate_questions"]},
    )
    assert resp.status == 200, await resp.text()
    body = await resp.json()
    assert body["session_id"] == session_id
    assert body["total_findings"] == len(body["findings"])
    for f in body["findings"]:
        assert "id" in f
        assert f["scanner"] in ("answer_length", "duplicate_questions")
        assert f["severity"] in ("high", "medium", "low")
        assert "sample_index" in f
        assert "explanation" in f


async def test_explore_scan_defaults_to_all_static(server):
    session_id = await _load_session(server)
    resp = await post(server, f"/api/explore/{session_id}/scan", json={})
    assert resp.status == 200, await resp.text()
    body = await resp.json()
    assert isinstance(body["findings"], list)


async def test_explore_scan_unknown_scanner(server):
    session_id = await _load_session(server)
    resp = await post(
        server,
        f"/api/explore/{session_id}/scan",
        json={"scanners": ["not_a_scanner"]},
    )
    assert resp.status == 400
    body = await resp.json()
    assert "not_a_scanner" in body["error"]


async def test_explore_scan_llm_requires_model(server):
    session_id = await _load_session(server)
    resp = await post(
        server,
        f"/api/explore/{session_id}/scan",
        json={"scanners": ["ambiguity"]},
    )
    assert resp.status == 400
    body = await resp.json()
    assert "model" in body["error"]


async def test_explore_scan_unknown_session(server):
    resp = await post(server, "/api/explore/nope/scan", json={})
    assert resp.status == 404
