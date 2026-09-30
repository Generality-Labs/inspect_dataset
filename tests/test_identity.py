"""The identity of a sample: its question text, choices and images."""

from __future__ import annotations

import base64
import hashlib

import pytest

from inspect_dataset._types import FieldMap
from inspect_dataset.scanners._identity import (
    answer_key,
    image_hash,
    image_key,
    normalise_text,
    sample_key,
    text_key,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
PNG_URI = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()
PNG_SHA = "sha256:" + hashlib.sha256(PNG_BYTES).hexdigest()

FIELDS = FieldMap(question="q", answer="a")
CHOICE_FIELDS = FieldMap(question="q", answer="a", choices="choices")
IMG_FIELDS = FieldMap(question="q", answer="a", image="img")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("  What IS\n\tthis?  ", "what is this?"), (None, ""), ("", ""), (3, "3")],
)
def test_normalise_text_lowercases_and_collapses_whitespace(text, expected):
    assert normalise_text(text) == expected


def test_text_key_without_choices_field_is_the_question_alone():
    assert text_key({"q": "Is it?", "choices": ["x"]}, FIELDS) == ("is it?", None)


def test_text_key_includes_normalised_choices_in_order():
    record = {"q": "Pick one. OPTIONS:", "choices": ["Big  Red", "small blue"]}
    assert text_key(record, CHOICE_FIELDS) == ("pick one. options:", ("big red", "small blue"))


def test_text_key_differs_when_only_the_choices_differ():
    a = {"q": "Which order is right? OPTIONS:", "choices": ["old red car", "red old car"]}
    b = {"q": "Which order is right? OPTIONS:", "choices": ["big wooden box", "wooden big box"]}
    assert text_key(a, CHOICE_FIELDS) != text_key(b, CHOICE_FIELDS)


def test_text_key_keeps_choice_order():
    a = {"q": "q", "choices": ["x", "y"]}
    b = {"q": "q", "choices": ["y", "x"]}
    assert text_key(a, CHOICE_FIELDS) != text_key(b, CHOICE_FIELDS)


def test_bytes_image_hashes_its_content():
    assert image_hash({"bytes": PNG_BYTES, "path": "a.png"}) == PNG_SHA


def test_data_uri_hashes_its_decoded_content():
    assert image_hash(PNG_URI) == PNG_SHA


def test_same_image_as_file_and_data_uri_has_the_same_key():
    as_file = {"img": [{"bytes": PNG_BYTES, "path": "/tmp/chart.png"}]}
    as_uri = {"img": [PNG_URI]}
    assert image_key(as_file, IMG_FIELDS) == image_key(as_uri, IMG_FIELDS)


def test_same_bytes_under_different_paths_have_the_same_hash():
    assert image_hash({"bytes": PNG_BYTES, "path": "a.png"}) == image_hash(
        {"bytes": PNG_BYTES, "path": "b.png"}
    )


def test_url_image_without_bytes_falls_back_to_its_path():
    assert image_hash({"bytes": None, "path": "https://x/y.png"}) == "path:https://x/y.png"
    assert image_hash("https://x/y.png") == "path:https://x/y.png"


def test_raw_bytes_hash_their_content():
    assert image_hash(PNG_BYTES) == PNG_SHA


@pytest.mark.parametrize("value", [None, {"bytes": None, "path": None}, "", 42])
def test_unusable_image_has_no_hash(value):
    assert image_hash(value) is None


def test_image_key_of_a_list_keeps_image_order():
    other = {"bytes": b"other", "path": None}
    a = image_key({"img": [PNG_URI, other]}, IMG_FIELDS)
    b = image_key({"img": [other, PNG_URI]}, IMG_FIELDS)
    assert a is not None
    assert a != b
    assert a[0] == PNG_SHA


@pytest.mark.parametrize("value", [None, []])
def test_image_key_without_images_is_none(value):
    assert image_key({"img": value}, IMG_FIELDS) is None


def test_image_key_without_an_image_field_is_none():
    assert image_key({"img": PNG_URI}, FIELDS) is None


def test_sample_key_combines_text_choices_and_images():
    fields = FieldMap(question="q", answer="a", image="img", choices="choices")
    record = {"q": "What is it?", "choices": ["A cat"], "img": PNG_URI}
    assert sample_key(record, fields) == (("what is it?", ("a cat",)), (PNG_SHA,))


# ---------------------------------------------------------------------------
# answer_key — the answers compared between duplicates
# ---------------------------------------------------------------------------

TASK_FIELDS = FieldMap(
    question="input", answer="target", id="id", choices="choices", scorers=["inspect_ai/choice"]
)


def test_answer_key_normalises_a_scalar_answer():
    assert answer_key({"a": "  Yes "}, FIELDS) == frozenset({"yes"})


def test_answer_key_resolves_a_letter_to_its_choice_text():
    choices = ["Paris", "London"]
    letter = answer_key({"a": "A", "choices": choices}, CHOICE_FIELDS)
    text = answer_key({"a": "paris", "choices": choices}, CHOICE_FIELDS)
    assert letter == text == frozenset({"paris"})


def test_answer_key_of_a_list_answer_is_a_set():
    assert answer_key({"a": ["x", "Y"]}, FIELDS) == answer_key({"a": ["y", "x"]}, FIELDS)


def test_answer_key_uses_every_task_target():
    a = {"input": "q", "target": "B", "targets": ["B", "A"], "choices": ["x", "y"]}
    b = {"input": "q", "target": "A", "targets": ["A", "B"], "choices": ["x", "y"]}
    assert answer_key(a, TASK_FIELDS) == answer_key(b, TASK_FIELDS) == frozenset({"x", "y"})


def test_answer_key_uses_the_answer_field_when_it_is_not_the_task_target():
    fields = FieldMap(question="input", answer="label", scorers=["inspect_ai/match"])
    record = {"input": "q", "target": "1", "targets": ["1", "2"], "label": "one"}
    assert answer_key(record, fields) == frozenset({"one"})


def test_answer_key_ignores_a_targets_column_outside_task_mode():
    fields = FieldMap(question="input", answer="target")
    assert answer_key({"target": "1", "targets": ["1", "2"]}, fields) == frozenset({"1"})
