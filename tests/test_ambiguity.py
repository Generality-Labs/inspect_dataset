"""Tests for the ambiguity LLM scanner."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from inspect_dataset._types import FieldMap

FIELDS = FieldMap(question="q", answer="a")


def _mock_model(responses: list[str]) -> MagicMock:
    """Create a mock model that returns canned responses in order."""
    model = MagicMock()
    call_idx = 0

    async def _generate(messages):
        nonlocal call_idx
        resp = MagicMock()
        resp.completion = responses[call_idx % len(responses)]
        call_idx += 1
        return resp

    model.generate = _generate
    return model


@pytest.fixture
def patch_get_model():
    with patch("inspect_dataset.scanners.ambiguity.get_model") as mock:
        yield mock


def test_ambiguous_question_flagged(patch_get_model):
    patch_get_model.return_value = _mock_model(
        ["YES\nThis question is ambiguous because 'big' is subjective."]
    )
    from inspect_dataset.scanners.ambiguity import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "is it big?", "a": "yes"}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "ambiguity"
    assert f.severity == "medium"
    assert f.category == "question_quality"
    assert "ambiguous" in f.explanation.lower()
    assert f.metadata["llm_reasoning"] != ""


def test_clear_question_not_flagged(patch_get_model):
    patch_get_model.return_value = _mock_model(["NO\nThis question is clear and unambiguous."])
    from inspect_dataset.scanners.ambiguity import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "What is 2+2?", "a": "4"}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 0


def test_empty_question_skipped(patch_get_model):
    patch_get_model.return_value = _mock_model(["YES\nflagged"])
    from inspect_dataset.scanners.ambiguity import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "", "a": "yes"}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 0


def test_multiple_records_mixed(patch_get_model):
    patch_get_model.return_value = _mock_model(
        [
            "YES\nAmbiguous",
            "NO\nClear",
            "YES\nAlso ambiguous",
        ]
    )
    from inspect_dataset.scanners.ambiguity import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [
        {"q": "is it big?", "a": "yes"},
        {"q": "What is 2+2?", "a": "4"},
        {"q": "is it good?", "a": "yes"},
    ]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 2
    assert findings[0].sample_index == 0
    assert findings[1].sample_index == 2


def test_scanner_metadata(patch_get_model):
    patch_get_model.return_value = _mock_model(["YES\nThe question is vague."])
    from inspect_dataset.scanners.ambiguity import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "is it big?", "a": "yes"}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert findings[0].metadata["question"] == "is it big?"
    assert findings[0].metadata["answer"] == "yes"
    assert "llm_raw_response" in findings[0].metadata
