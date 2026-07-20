"""API tests for serving local annotation datasets in the view server."""

import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from inspect_dataset._view.server import create_app
from inspect_dataset.loader import load_local_samples
from inspect_dataset.report import save_findings
from inspect_dataset.scanner import run_scanners
from inspect_dataset.scanners import BUILTIN_SCANNER_NAMES

GOLD_MD = """\
---
title: T
source: x.pdf
page: 1
tier: financial
---

# Title

| Item | 2023 |
| --- | ---: |
| Cash | 10 |
"""

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fccff0bf1e00057f027f8f2b6c1e0000000049454e44ae426082"
)


@pytest.fixture
def findings_dir(tmp_path):
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "s1.json").write_text(
        json.dumps(
            {
                "id": "s1",
                "task_type": "page_roundtrip",
                "pdf_path": "corpus/x.pdf",
                "page_number": 1,
                "tier": "financial",
                "ground_truth_markdown_path": "s1.md",
            }
        )
    )
    (samples / "s1.md").write_text(GOLD_MD)

    cache = tmp_path / "cache" / "s1"
    cache.mkdir(parents=True)
    (cache / "page.png").write_bytes(PNG_1PX)
    (cache / "pymupdf.txt").write_text("Title Item 2023 Cash 10\n")

    records, fields = load_local_samples(samples)
    run = run_scanners(
        records,
        fields,
        [BUILTIN_SCANNER_NAMES["markdown_integrity"]],
        dataset_name=str(samples),
        source_type="local",
    )
    out = tmp_path / "findings"
    save_findings(run, out, records=records, fields=fields, files_root=str(tmp_path / "cache"))
    return out


async def test_sample_detail_serves_artifacts(findings_dir):
    app = create_app(findings_dir)
    async with TestClient(TestServer(app)) as client:
        datasets = await (await client.get("/api/datasets")).json()
        slug = datasets[0]["slug"]
        detail = await (await client.get(f"/api/{slug}/sample/0")).json()

    assert detail["id"] == "s1"
    assert detail["answer"].startswith("# Title")
    assert detail["line_offset"] == 7
    assert [img["field"] for img in detail["images"]] == ["page"]
    assert detail["images"][0]["data_url"].startswith("data:image/png;base64,")
    assert [t["name"] for t in detail["tool_outputs"]] == ["pymupdf"]


def test_summary_records_files_root(findings_dir):
    summary = json.loads((findings_dir / "scan_summary.json").read_text())
    assert summary["source_type"] == "local"
    assert summary["files_root"].endswith("cache")
