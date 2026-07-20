import json

import pytest

from inspect_dataset.loader import load_local_samples, split_frontmatter

MD = """\
---
title: Consolidated Balance Sheets
source: fin.pdf
page: 1
---

# CONSOLIDATED BALANCE SHEETS

| Item | 2023 |
| --- | ---: |
| Cash | 10 |
"""


@pytest.fixture
def samples_dir(tmp_path):
    (tmp_path / "page_001.json").write_text(
        json.dumps(
            {
                "id": "page_001",
                "task_type": "page_roundtrip",
                "pdf_path": "corpus/fin.pdf",
                "page_number": 1,
                "ground_truth_markdown_path": "page_001.md",
            }
        )
    )
    (tmp_path / "page_001.md").write_text(MD)
    (tmp_path / "table_001.json").write_text(
        json.dumps(
            {
                "id": "table_001",
                "task_type": "element_reproduction",
                "element_type": "table",
                "pdf_path": "corpus/fin.pdf",
                "page_number": 1,
                "ground_truth_table": {
                    "headers": ["Item", "2023"],
                    "rows": [["Cash", "10"]],
                    "markdown": "| Item | 2023 |\n| --- | --- |\n| Cash | 10 |",
                },
            }
        )
    )
    (tmp_path / "README.md").write_text("# not a sample")
    return tmp_path


def test_loads_all_json_annotations(samples_dir):
    records, fields = load_local_samples(samples_dir)
    assert len(records) == 2
    assert fields.question == "__task__"
    assert fields.answer == "gold_markdown"
    assert fields.id == "id"


def test_sidecar_markdown_body_loaded_without_frontmatter(samples_dir):
    records, _ = load_local_samples(samples_dir)
    page = next(r for r in records if r["id"] == "page_001")
    assert page["gold_markdown"].startswith("# CONSOLIDATED")
    assert page["__frontmatter__"] == {
        "title": "Consolidated Balance Sheets",
        "source": "fin.pdf",
        "page": "1",
    }
    assert page["__md_body_offset__"] == 6


def test_embedded_table_markdown_used_when_no_sidecar(samples_dir):
    records, _ = load_local_samples(samples_dir)
    table = next(r for r in records if r["id"] == "table_001")
    assert table["gold_markdown"].startswith("| Item |")


def test_question_synthesised_from_task_fields(samples_dir):
    records, _ = load_local_samples(samples_dir)
    page = next(r for r in records if r["id"] == "page_001")
    assert page["__task__"] == "page_roundtrip corpus/fin.pdf#page=1"


def test_missing_sidecar_yields_empty_answer(tmp_path):
    (tmp_path / "s.json").write_text(
        json.dumps({"id": "s", "ground_truth_markdown_path": "missing.md"})
    )
    records, _ = load_local_samples(tmp_path)
    assert records[0]["gold_markdown"] == ""
    assert records[0]["__markdown_path__"].endswith("missing.md")
    assert "__frontmatter__" not in records[0]


def test_limit_respected(samples_dir):
    records, _ = load_local_samples(samples_dir, limit=1)
    assert len(records) == 1


def test_empty_dir_raises(tmp_path):
    with pytest.raises(ValueError, match="No JSON annotation files"):
        load_local_samples(tmp_path)


def test_split_frontmatter_no_frontmatter():
    fm, body, offset = split_frontmatter("# Title\n")
    assert fm == {}
    assert body == "# Title\n"
    assert offset == 0
