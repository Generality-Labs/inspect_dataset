"""Tests for the answerability LLM scanner."""

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
    with patch("inspect_dataset.scanners.answerability.get_model") as mock:
        yield mock


def test_unanswerable_without_context_flagged(patch_get_model):
    patch_get_model.return_value = _mock_model(
        ["YES\nThe question refers to 'this image' but no image is provided."]
    )
    from inspect_dataset.scanners.answerability import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "What is shown in this image?", "a": "a cat"}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "answerability"
    assert f.severity == "medium"
    assert f.category == "question_quality"
    assert f.metadata["has_context"] is False


def test_answerable_standalone_not_flagged(patch_get_model):
    patch_get_model.return_value = _mock_model(["NO\nThis is a general knowledge question."])
    from inspect_dataset.scanners.answerability import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "What is the capital of France?", "a": "Paris"}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 0


def test_unanswerable_with_context_flagged(patch_get_model):
    patch_get_model.return_value = _mock_model(
        ["YES\nThe context discusses weather, not geography."]
    )
    from inspect_dataset.scanners.answerability import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [
        {
            "q": "What is the capital of France?",
            "a": "Paris",
            "context": "It was a sunny day with clear skies.",
        }
    ]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 1
    assert findings[0].metadata["has_context"] is True
    assert findings[0].metadata["context_field"] == "context"


def test_answerable_with_context_not_flagged(patch_get_model):
    patch_get_model.return_value = _mock_model(["NO\nThe context directly answers the question."])
    from inspect_dataset.scanners.answerability import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [
        {
            "q": "What is the capital of France?",
            "a": "Paris",
            "context": "France is a country in Europe. Its capital is Paris.",
        }
    ]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 0


def test_empty_question_skipped(patch_get_model):
    patch_get_model.return_value = _mock_model(["YES\nflagged"])
    from inspect_dataset.scanners.answerability import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [{"q": "", "a": "yes"}]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 0


def test_context_field_detection():
    """Test that _find_context_field finds common context column names."""
    from inspect_dataset.scanners.answerability import _find_context_field

    record = {"q": "question", "a": "answer", "passage": "some text"}
    result = _find_context_field(record, FIELDS)
    assert result == "passage"

    record2 = {"q": "question", "a": "answer", "document": "some doc"}
    result2 = _find_context_field(record2, FIELDS)
    assert result2 == "document"

    # No context field
    record3 = {"q": "question", "a": "answer"}
    result3 = _find_context_field(record3, FIELDS)
    assert result3 is None


def test_multiple_records_mixed(patch_get_model):
    patch_get_model.return_value = _mock_model(
        [
            "YES\nUnanswerable",
            "NO\nAnswerable",
            "YES\nAlso unanswerable",
        ]
    )
    from inspect_dataset.scanners.answerability import _make_scanner

    scanner = _make_scanner("fake-model")
    records = [
        {"q": "What is in this image?", "a": "a cat"},
        {"q": "What is 2+2?", "a": "4"},
        {"q": "What does the chart show?", "a": "growth"},
    ]
    findings = asyncio.run(scanner(records, FIELDS))
    assert len(findings) == 2
    assert findings[0].sample_index == 0
    assert findings[1].sample_index == 2
