"""Tests for the label_correctness LLM scanner."""

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
    with patch("inspect_dataset.scanners.label_correctness.get_model") as mock:
        yield mock


def test_incorrect_label_flagged(patch_get_model):
    patch_get_model.return_value = _mock_model(
        ["YES\nThe answer is factually incorrect. 2+2=4, not 5."]
    )
    from inspect_dataset.scanners.label_correctness import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "What is 2+2?", "a": "5"}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "label_correctness"
    assert f.severity == "high"
    assert f.category == "label_quality"
    assert "incorrect" in f.explanation.lower()


def test_correct_label_not_flagged(patch_get_model):
    patch_get_model.return_value = _mock_model(["NO\nThe answer is correct."])
    from inspect_dataset.scanners.label_correctness import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "What is 2+2?", "a": "4"}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 0


def test_empty_answer_skipped(patch_get_model):
    patch_get_model.return_value = _mock_model(["YES\nflagged"])
    from inspect_dataset.scanners.label_correctness import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "What is 2+2?", "a": ""}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 0


def test_empty_question_skipped(patch_get_model):
    patch_get_model.return_value = _mock_model(["YES\nflagged"])
    from inspect_dataset.scanners.label_correctness import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "", "a": "4"}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 0


def test_multiple_records_mixed(patch_get_model):
    patch_get_model.return_value = _mock_model(
        [
            "YES\nWrong answer",
            "NO\nCorrect",
            "YES\nAlso wrong",
        ]
    )
    from inspect_dataset.scanners.label_correctness import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [
        {"q": "What is 2+2?", "a": "5"},
        {"q": "What is 3+3?", "a": "6"},
        {"q": "Capital of France?", "a": "Berlin"},
    ]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 2
    assert findings[0].sample_index == 0
    assert findings[1].sample_index == 2


def test_scanner_metadata(patch_get_model):
    patch_get_model.return_value = _mock_model(["YES\nFactually wrong."])
    from inspect_dataset.scanners.label_correctness import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "What is 2+2?", "a": "5"}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert findings[0].metadata["question"] == "What is 2+2?"
    assert findings[0].metadata["answer"] == "5"
    assert "llm_raw_response" in findings[0].metadata
