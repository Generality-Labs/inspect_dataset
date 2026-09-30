import pytest

from inspect_dataset._types import FieldMap
from inspect_dataset.scanner import ScannerNotApplicable
from inspect_dataset.scanners.answer_length import _make_scanner, answer_length

FIELDS = FieldMap(question="q", answer="a")


def records(*answers: str) -> list[dict]:
    return [{"q": f"question {i}", "a": a} for i, a in enumerate(answers)]


def test_short_answer_no_finding():
    assert answer_length(records("yes", "no", "blue"), FIELDS) == []


def test_answer_at_threshold_no_finding():
    # Default threshold is 4; exactly 4 words should not be flagged
    assert answer_length(records("one two three four"), FIELDS) == []


def test_long_answer_flagged():
    findings = answer_length(records("one two three four five"), FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "answer_length"
    assert f.severity == "medium"
    assert f.category == "label_quality"
    assert f.sample_index == 0
    assert f.metadata["word_count"] == 5


def test_only_long_answers_flagged():
    findings = answer_length(records("yes", "one two three four five", "no"), FIELDS)
    assert len(findings) == 1
    assert findings[0].sample_index == 1


def test_custom_threshold():
    scanner = _make_scanner(max_words=2)
    findings = scanner(records("one two three"), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["word_count"] == 3


def test_custom_threshold_short_no_finding():
    scanner = _make_scanner(max_words=2)
    assert scanner(records("one two"), FIELDS) == []


def test_empty_answer_skipped():
    assert answer_length(records(""), FIELDS) == []


def test_sample_id_from_field():
    fields = FieldMap(question="q", answer="a", id="id")
    recs = [{"q": "question", "a": "one two three four five", "id": "sample-42"}]
    findings = answer_length(recs, fields)
    assert findings[0].sample_id == "sample-42"


def test_sample_id_defaults_to_index():
    findings = answer_length(records("one two three four five"), FIELDS)
    assert findings[0].sample_id == 0


# ---------------------------------------------------------------------------
# Non-scalar answer columns (issue #26)
# ---------------------------------------------------------------------------


def test_numeric_answers_are_measured_as_scalars():
    assert answer_length([{"q": "q", "a": 42}, {"q": "q", "a": 3.5}], FIELDS) == []


def test_dict_answer_raises_not_applicable_naming_its_keys():
    recs = [{"q": "q", "a": {"text": "one two three four five", "start": 3}}]
    with pytest.raises(ScannerNotApplicable, match=r"'a'.*dict.*text, start"):
        answer_length(recs, FIELDS)


def test_mixed_scalar_and_list_column_is_not_applicable():
    recs = [{"q": "q", "a": "one two three four five"}, {"q": "q", "a": ["x", "y"]}]
    with pytest.raises(ScannerNotApplicable, match="1 of 2 rows"):
        answer_length(recs, FIELDS)


def test_subfield_selects_scalar_in_dict():
    fields = FieldMap(question="q", answer="a", answer_subfield="value")
    recs = [
        {"q": "q", "a": {"value": "Paris", "aliases": ["City of Light"]}},
        {"q": "q", "a": {"value": "one two three four five", "aliases": []}},
    ]
    findings = answer_length(recs, fields)
    assert [f.sample_index for f in findings] == [1]
    assert findings[0].metadata == {
        "word_count": 5,
        "answer": "one two three four five",
        "answer_subfield": "value",
        "element_index": 0,
    }


def test_subfield_maps_over_lists_and_reports_longest_element_once_per_row():
    fields = FieldMap(question="q", answer="a", answer_subfield="text")
    recs = [{"q": "q", "a": [{"text": "short"}, {"text": "a b c d e"}, {"text": "a b c d e f"}]}]
    findings = answer_length(recs, fields)
    assert len(findings) == 1
    assert findings[0].metadata["word_count"] == 6
    assert findings[0].metadata["element_index"] == 2


def test_star_subfield_measures_each_string_in_a_list():
    fields = FieldMap(question="q", answer="a", answer_subfield="*")
    recs = [{"q": "q", "a": ["yes", "no"]}, {"q": "q", "a": ["yes", "one two three four five"]}]
    findings = answer_length(recs, fields)
    assert [f.sample_index for f in findings] == [1]
    assert findings[0].metadata["element_index"] == 1


def test_array_answer_suggests_star_and_star_measures_each_element():
    np = pytest.importorskip("numpy")
    recs = [{"q": "q", "a": np.array(["yes", "one two three four five"])}]
    with pytest.raises(ScannerNotApplicable, match=r"ndarray.*pass --answer-subfield '\*'"):
        answer_length(recs, FIELDS)

    findings = answer_length(recs, FieldMap(question="q", answer="a", answer_subfield="*"))
    assert len(findings) == 1
    assert findings[0].metadata["answer"] == "one two three four five"
    assert findings[0].metadata["element_index"] == 1


def test_subfield_resolving_to_non_scalar_is_not_applicable():
    fields = FieldMap(question="q", answer="a", answer_subfield="labels")
    recs = [{"q": "q", "a": {"labels": [{"label": [0, 1]}]}}]
    with pytest.raises(ScannerNotApplicable, match=r"'a\.labels'"):
        answer_length(recs, fields)


def test_missing_subfield_key_counts_as_empty():
    fields = FieldMap(question="q", answer="a", answer_subfield="value")
    recs = [{"q": "q", "a": {"value": "Paris"}}, {"q": "q", "a": {"other": "a b c d e"}}]
    assert answer_length(recs, fields) == []


def test_subfield_matching_no_row_is_not_applicable():
    fields = FieldMap(question="q", answer="a", answer_subfield="valeu")
    with pytest.raises(ScannerNotApplicable, match="'valeu' matched no value"):
        answer_length([{"q": "q", "a": {"value": "a b c d e"}}], fields)


# ---------------------------------------------------------------------------
# The task's scorer (issue #33)
# ---------------------------------------------------------------------------


def test_non_verbatim_scorer_is_not_applicable():
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/choice"])
    recs = records("one two three four five six", "Yes", "yes", "yes", "yes.")
    with pytest.raises(ScannerNotApplicable, match="this task scores with inspect_ai/choice"):
        answer_length(recs, fields)


def test_scorer_gate_comes_before_the_answer_type_check():
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/f1"])
    recs = [{"q": "q", "a": ["a list", "of answers"]}]
    with pytest.raises(ScannerNotApplicable, match="scores with inspect_ai/f1"):
        answer_length(recs, fields)


def test_verbatim_scorer_measures_as_before():
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/exact", "inspect_ai/f1"])
    recs = records("one two three four five six", "yes", "no", "blue", "red", "green", "Big")
    findings = answer_length(recs, fields)
    assert findings
    assert findings == answer_length(recs, FIELDS)
