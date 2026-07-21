"""Tests for the gold_fidelity vision LLM scanner."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from inspect_dataset._types import FieldMap

FIELDS = FieldMap(question="q", answer="a")

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fccff0bf1e00057f027f8f2b6c1e0000000049454e44ae426082"
)


def _mock_model(responses: list[str], captured: list | None = None) -> MagicMock:
    model = MagicMock()
    call_idx = 0

    async def _generate(messages):
        nonlocal call_idx
        if captured is not None:
            captured.append(messages)
        resp = MagicMock()
        resp.completion = responses[call_idx % len(responses)]
        call_idx += 1
        return resp

    model.generate = _generate
    return model


@pytest.fixture
def patch_get_model():
    with patch("inspect_dataset.scanners.gold_fidelity.get_model") as mock:
        yield mock


def _sample_dir(tmp_path, name: str, with_image: bool = True):
    d = tmp_path / name
    d.mkdir()
    if with_image:
        (d / "page.png").write_bytes(PNG_1PX)
    return str(d)


def test_unfaithful_gold_flagged(patch_get_model, tmp_path):
    patch_get_model.return_value = _mock_model(["YES\nThe total reads 90 but the image shows 100."])
    from inspect_dataset.scanners.gold_fidelity import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [
        {"q": "reproduce", "a": "| Total | 90 |", "__artifacts_dir__": _sample_dir(tmp_path, "s0")}
    ]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "gold_fidelity"
    assert f.severity == "high"
    assert f.category == "label_quality"
    assert "90" in f.explanation


def test_faithful_gold_not_flagged(patch_get_model, tmp_path):
    patch_get_model.return_value = _mock_model(["NO\nMatches the image."])
    from inspect_dataset.scanners.gold_fidelity import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [
        {"q": "reproduce", "a": "| Total | 100 |", "__artifacts_dir__": _sample_dir(tmp_path, "s0")}
    ]
    findings = asyncio.run(scanner(records, FIELDS))
    assert findings == []


def test_record_without_page_image_skipped(patch_get_model, tmp_path):
    patch_get_model.return_value = _mock_model(["YES\nflagged"])
    from inspect_dataset.scanners.gold_fidelity import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [
        {
            "q": "reproduce",
            "a": "text",
            "__artifacts_dir__": _sample_dir(tmp_path, "s0", with_image=False),
        },
        {"q": "reproduce", "a": "text"},  # no artifacts dir at all
    ]
    findings = asyncio.run(scanner(records, FIELDS))
    assert findings == []


def test_empty_answer_skipped(patch_get_model, tmp_path):
    patch_get_model.return_value = _mock_model(["YES\nflagged"])
    from inspect_dataset.scanners.gold_fidelity import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "reproduce", "a": "", "__artifacts_dir__": _sample_dir(tmp_path, "s0")}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert findings == []


def test_image_sent_as_content_block(patch_get_model, tmp_path):
    captured: list = []
    patch_get_model.return_value = _mock_model(["NO\nok"], captured=captured)
    from inspect_dataset.scanners.gold_fidelity import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "reproduce", "a": "text", "__artifacts_dir__": _sample_dir(tmp_path, "s0")}]
    asyncio.run(scanner(records, FIELDS))

    assert len(captured) == 1
    user_msg = captured[0][-1]
    block_types = [b.type for b in user_msg.content]
    assert block_types == ["image", "text"]
    assert user_msg.content[0].image.startswith("data:image/png;base64,")


def test_mixed_records_index_preserved(patch_get_model, tmp_path):
    patch_get_model.return_value = _mock_model(["YES\nwrong", "NO\nok", "YES\nwrong"])
    from inspect_dataset.scanners.gold_fidelity import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [
        {"q": "reproduce", "a": "a0", "__artifacts_dir__": _sample_dir(tmp_path, "s0")},
        {"q": "reproduce", "a": "a1", "__artifacts_dir__": _sample_dir(tmp_path, "s1")},
        {"q": "reproduce", "a": "a2", "__artifacts_dir__": _sample_dir(tmp_path, "s2")},
    ]
    findings = asyncio.run(scanner(records, FIELDS))
    assert [f.sample_index for f in findings] == [0, 2]
