"""The viewer serves task-mode images, which the loader collects from the sample input."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from inspect_dataset._view.server import _record_images, _record_to_json_safe, create_app
from inspect_dataset.loader import load_task_from_spec
from inspect_dataset.report import save_findings
from inspect_dataset.scanner import run_scanners

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
PNG_URI = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()

_TASK_FILE = """
from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser, ContentImage, ContentText


@task
def pictures():
    return Task(
        dataset=[
            Sample(
                input=[
                    ChatMessageUser(
                        content=[
                            ContentText(text="Which is larger?"),
                            ContentImage(image={path!r}),
                            ContentImage(image={uri!r}),
                            ContentImage(image="https://example.com/x.png"),
                        ]
                    )
                ],
                target="A",
                id="s1",
            )
        ]
    )
"""


@pytest.fixture
def task_spec(tmp_path: Path) -> str:
    image = tmp_path / "left.png"
    image.write_bytes(PNG_BYTES)
    task_file = tmp_path / "pictures_task.py"
    task_file.write_text(_TASK_FILE.format(path=str(image), uri=PNG_URI))
    return f"{task_file}@pictures"


def test_record_images_lists_every_image_that_has_data():
    record = {
        "images": [{"bytes": PNG_BYTES, "path": "a.png"}, PNG_URI, {"bytes": None, "path": "u"}],
        "choices": ["red", "blue"],
        "img": {"bytes": PNG_BYTES, "path": "b.png"},
    }
    assert _record_images(record) == [
        {"field": "images[0]", "data_url": PNG_URI},
        {"field": "images[1]", "data_url": PNG_URI},
        {"field": "img", "data_url": PNG_URI},
    ]


def test_json_safe_record_replaces_images_in_lists():
    record = {"images": [{"bytes": PNG_BYTES, "path": "a.png"}, PNG_URI], "choices": ["x", "y"]}
    assert _record_to_json_safe(record) == {
        "images": [
            {"__type": "image", "path": "a.png"},
            {"__type": "image", "path": "data:image/png"},
        ],
        "choices": ["x", "y"],
    }


def test_json_safe_record_replaces_images_inside_structs():
    record = {
        "struct": {"img": {"bytes": PNG_BYTES, "path": "a.png"}, "caption": "x"},
        "meta": {"figures": [PNG_URI], (1, 2): "pair"},
    }
    assert _record_to_json_safe(record) == {
        "struct": {"img": {"__type": "image", "path": "a.png"}, "caption": "x"},
        "meta": {"figures": [{"__type": "image", "path": "data:image/png"}], "(1, 2)": "pair"},
    }


async def test_sample_detail_serves_task_images(tmp_path: Path, task_spec: str):
    records, fields = load_task_from_spec(task_spec)
    run = run_scanners(records, fields, [], dataset_name=task_spec, source_type="inspect_task")
    out = tmp_path / "findings"
    save_findings(run, out, records=records, fields=fields)
    assert "\\x89PNG" not in (out / "samples.json").read_text()

    async with TestClient(TestServer(create_app(out))) as client:
        slug = (await (await client.get("/api/datasets")).json())[0]["slug"]
        detail = await (await client.get(f"/api/{slug}/sample/0")).json()

    assert detail["question"] == "Which is larger?"
    assert [i["field"] for i in detail["images"]] == ["images[0]", "images[1]"]
    assert all(i["data_url"] == PNG_URI for i in detail["images"])


async def test_explorer_serves_task_images_without_bytes(task_spec: str):
    async with TestClient(TestServer(create_app())) as client:
        load = await client.post(
            "/api/explore/load", json={"source": task_spec, "source_type": "inspect_task"}
        )
        assert load.status == 200, await load.text()
        session_id = (await load.json())["session_id"]
        rows = await (await client.get(f"/api/explore/{session_id}/records")).text()
        detail = await (await client.get(f"/api/explore/{session_id}/record/0")).json()

    assert "\\x89PNG" not in rows
    assert '"__type": "image"' in rows or '"__type":"image"' in rows
    assert [i["field"] for i in detail["images"]] == ["images[0]", "images[1]"]
