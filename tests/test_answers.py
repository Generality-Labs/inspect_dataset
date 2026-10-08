"""Letter targets resolved to the text of the choice they name."""

from __future__ import annotations

import pytest

from inspect_dataset._types import FieldMap
from inspect_dataset.scanner import ScannerNotApplicable
from inspect_dataset.scanners._answers import (
    VERBATIM_SCORERS,
    choice_letters,
    record_choices,
    require_compared,
    require_verbatim_scorer,
    resolve_choice,
    resolved_answer,
)

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


def test_choice_letters_marks_rows_whose_target_names_a_choice():
    fields = FieldMap(question="q", answer="a", choices="choices")
    records = [
        {"a": "b", "choices": CHOICES},
        {"a": "D", "choices": CHOICES},
        {"a": "mri", "choices": CHOICES},
        {"a": "A"},
    ]
    assert choice_letters(records, fields) == ["B", "", "", ""]
    assert choice_letters(records, FieldMap(question="q", answer="a")) == ["", "", "", ""]


# ---------------------------------------------------------------------------
# Scorer gate for the answer-text rules (issue #33)
# ---------------------------------------------------------------------------


def _scored_with(scorers: list[str] | None) -> FieldMap:
    return FieldMap(question="q", answer="a", scorers=scorers)


def test_unknown_scorer_applies():
    require_verbatim_scorer(_scored_with(None), "answer_length")


@pytest.mark.parametrize("scorer", sorted(VERBATIM_SCORERS))
def test_verbatim_scorer_applies(scorer):
    require_verbatim_scorer(_scored_with([scorer]), "answer_length")


def test_verbatim_scorers_are_the_text_comparing_builtins():
    expected = {"inspect_ai/exact", "inspect_ai/match", "inspect_ai/includes", "inspect_ai/pattern"}
    assert expected == VERBATIM_SCORERS


def test_verbatim_scorer_alongside_another_applies():
    require_verbatim_scorer(_scored_with(["inspect_ai/exact", "inspect_ai/f1"]), "answer_length")


def test_non_verbatim_scorer_is_not_applicable_and_named():
    with pytest.raises(ScannerNotApplicable) as excinfo:
        require_verbatim_scorer(_scored_with(["inspect_ai/choice"]), "answer_length")
    assert str(excinfo.value) == (
        "answer_length assumes a scorer that compares answer text verbatim; "
        "this task scores with inspect_ai/choice"
    )


def test_every_non_verbatim_scorer_is_named():
    with pytest.raises(ScannerNotApplicable, match=r"scores with inspect_ai/f1, custom_scorer$"):
        require_verbatim_scorer(_scored_with(["inspect_ai/f1", "custom_scorer"]), "x")


def test_task_without_scorer_is_not_applicable():
    with pytest.raises(ScannerNotApplicable) as excinfo:
        require_verbatim_scorer(_scored_with([]), "inconsistent_format")
    assert str(excinfo.value) == (
        "inconsistent_format assumes a scorer that compares answer text verbatim; "
        "this task has no scorer"
    )


# ---------------------------------------------------------------------------
# What each scorer compares: case, punctuation, length
# ---------------------------------------------------------------------------

ALL_ASPECTS = ("case", "punctuation", "length")


@pytest.mark.parametrize(
    ("scorers", "compared"),
    [
        (None, {"case", "punctuation", "length"}),
        (["inspect_ai/exact"], {"length"}),
        (["inspect_ai/match"], {"length"}),
        (["inspect_ai/includes"], {"punctuation", "length"}),
        (["inspect_ai/pattern"], {"case", "punctuation", "length"}),
        (["inspect_ai/exact", "inspect_ai/includes"], {"punctuation", "length"}),
    ],
)
def test_the_aspects_a_scorer_compares(scorers, compared):
    assert require_compared(_scored_with(scorers), "x", ALL_ASPECTS) == compared


def test_partial_credit_alongside_exact_makes_length_not_decisive():
    with pytest.raises(ScannerNotApplicable) as excinfo:
        require_compared(_scored_with(["inspect_ai/f1", "inspect_ai/exact"]), "x", ALL_ASPECTS)
    assert str(excinfo.value) == (
        "x assumes a scorer that compares answer text verbatim; this task scores with "
        "inspect_ai/f1, inspect_ai/exact, which do not depend on the answer's case, "
        "punctuation or length (f1 gives partial credit)"
    )


def test_a_scorer_without_a_text_comparison_keeps_the_short_reason():
    with pytest.raises(ScannerNotApplicable, match=r"scores with inspect_ai/choice$"):
        require_compared(_scored_with(["inspect_ai/choice"]), "x", ("length",))
