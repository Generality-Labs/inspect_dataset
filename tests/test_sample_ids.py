from inspect_dataset._types import FieldMap, Finding
from inspect_dataset.scanners.duplicate_questions import _scan


def _finding(**kwargs) -> Finding:
    return Finding(
        scanner="s",
        severity="low",
        category="question_quality",
        explanation="e",
        sample_index=0,
        **kwargs,
    )


def test_sample_ids_default_to_the_one_sample_id():
    assert _finding(sample_id="a").to_dict()["sample_ids"] == ["a"]


def test_integer_zero_is_an_id():
    assert _finding(sample_id=0).to_dict()["sample_ids"] == [0]


def test_no_sample_id_gives_an_empty_list():
    assert _finding().to_dict()["sample_ids"] == []


def test_given_sample_ids_are_emitted_unchanged():
    assert _finding(sample_id="a", sample_ids=["a", "b"]).to_dict()["sample_ids"] == ["a", "b"]


def test_duplicate_questions_lists_every_id_in_the_group():
    records = [{"q": "Same?", "a": "x", "id": f"s{i}"} for i in range(3)]
    fields = FieldMap(question="q", answer="a", id="id")
    (finding,) = _scan(records, fields)
    assert finding.sample_ids == ["s0", "s1", "s2"]
    assert finding.metadata["duplicate_ids"] == ["s0", "s1", "s2"]


def test_duplicate_questions_without_an_id_field_lists_row_indices():
    records = [{"q": "Same?", "a": "x"} for _ in range(2)]
    (finding,) = _scan(records, FieldMap(question="q", answer="a"))
    assert finding.sample_ids == [0, 1]


def test_duplicate_questions_leaves_out_a_row_with_no_id_value():
    records = [
        {"q": "Same?", "a": "x", "id": "s0"},
        {"q": "Same?", "a": "x"},
        {"q": "Same?", "a": "x", "id": "s2"},
    ]
    (finding,) = _scan(records, FieldMap(question="q", answer="a", id="id"))
    assert finding.sample_ids == ["s0", "s2"]
    assert finding.metadata["duplicate_ids"] == ["s0", None, "s2"]
