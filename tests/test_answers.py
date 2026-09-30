"""Letter targets resolved to the text of the choice they name."""

from __future__ import annotations

import pytest

from inspect_dataset._types import FieldMap
from inspect_dataset.scanners._answers import record_choices, resolve_choice, resolved_answer

CHOICES = ["mri", "ct", "xray"]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("A", "mri"), ("b", "ct"), (" C\n", "xray")],
)
def test_letter_resolves_to_choice_text(answer, expected):
    assert resolve_choice(answer, CHOICES) == expected


@pytest.mark.parametrize("answer", ["D", "Z", "AB", "", "1", "mri", "(A)", None, 0])
def test_non_letter_or_out_of_range_answer_does_not_resolve(answer):
    assert resolve_choice(answer, CHOICES) is None


@pytest.mark.parametrize("choices", [None, [], "abc", {"label": ["A"], "text": ["mri"]}])
def test_missing_or_non_list_choices_do_not_resolve(choices):
    assert resolve_choice("A", choices) is None


def test_tuple_choices_resolve():
    assert resolve_choice("B", ("yes", "no")) == "no"


def test_record_choices_reads_the_choices_field():
    fields = FieldMap(question="q", answer="a", choices="opts")
    assert record_choices({"opts": CHOICES}, fields) == CHOICES
    assert record_choices({"opts": "not a list"}, fields) is None
    assert record_choices({}, fields) is None


def test_record_choices_is_none_without_a_choices_field():
    assert record_choices({"choices": CHOICES}, FieldMap(question="q", answer="a")) is None


def test_resolved_answer_uses_the_choice_text():
    fields = FieldMap(question="q", answer="a", choices="choices")
    assert resolved_answer({"a": "B", "choices": CHOICES}, fields) == "ct"


def test_resolved_answer_keeps_an_answer_that_does_not_resolve():
    fields = FieldMap(question="q", answer="a", choices="choices")
    assert resolved_answer({"a": "Q", "choices": CHOICES}, fields) == "Q"
    assert resolved_answer({"a": "B"}, fields) == "B"
    no_choices_field = FieldMap(question="q", answer="a")
    assert resolved_answer({"a": "B", "choices": CHOICES}, no_choices_field) == "B"


def test_resolved_answer_maps_over_a_list_answer():
    fields = FieldMap(question="q", answer="targets", choices="choices")
    record = {"targets": ["A", "C"], "choices": CHOICES}
    assert resolved_answer(record, fields) == ["mri", "xray"]
