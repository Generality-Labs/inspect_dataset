import pytest

from inspect_dataset._types import FieldMap
from inspect_dataset.scanner import ScannerNotApplicable
from inspect_dataset.scanners.binary_question_ratio import binary_question_ratio

FIELDS = FieldMap(question="q", answer="a")


def records(*answers: str) -> list[dict]:
    return [{"q": f"question {i}", "a": a} for i, a in enumerate(answers)]


def test_all_open_answers_no_finding():
    recs = records("axial", "brain", "right upper lobe", "mri", "female")
    assert binary_question_ratio(recs, FIELDS) == []


def test_exactly_half_binary_no_finding():
    # 50% yes/no — at threshold, not above
    recs = records(*["yes"] * 5, *["axial"] * 5)
    assert binary_question_ratio(recs, FIELDS) == []


def test_above_threshold_flagged():
    # 60% yes/no
    recs = records(*["yes"] * 6, *["axial"] * 4)
    findings = binary_question_ratio(recs, FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "binary_question_ratio"
    assert f.severity == "low"
    assert f.category == "distribution"
    assert f.sample_index == -1
    assert f.sample_id is None


def test_all_yes_no_flagged():
    recs = records(*["yes"] * 5, *["no"] * 5)
    findings = binary_question_ratio(recs, FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["binary_count"] == 10
    assert findings[0].metadata["fraction"] == 1.0


def test_metadata_counts():
    recs = records(*["yes"] * 7, *["no"] * 3)
    findings = binary_question_ratio(recs, FIELDS)
    m = findings[0].metadata
    assert m["yes_count"] == 7
    assert m["no_count"] == 3
    assert m["binary_count"] == 10


def test_naive_majority_score_correct():
    # 7 yes, 3 no → majority is yes → naive score = 7/10
    recs = records(*["yes"] * 7, *["no"] * 3)
    findings = binary_question_ratio(recs, FIELDS)
    assert findings[0].metadata["naive_majority_score"] == 0.7


def test_empty_answers_excluded():
    # 6 yes/no + 4 empty → 6/6 = 100% binary (empty excluded)
    recs = records(*["yes"] * 6, *[""] * 4)
    findings = binary_question_ratio(recs, FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["total"] == 6


def test_all_empty_no_finding():
    assert binary_question_ratio(records("", ""), FIELDS) == []


# ---------------------------------------------------------------------------
# Grouping by subset (issue #36)
# ---------------------------------------------------------------------------

GROUPED = FieldMap(question="q", answer="a", group="subset")


def grouped_records(**subsets: list[str]) -> list[dict]:
    return [
        {"q": f"{name} question {i}", "a": a, "subset": name}
        for name, answers in subsets.items()
        for i, a in enumerate(answers)
    ]


def test_binary_subset_hidden_in_open_answer_whole():
    recs = grouped_records(judge=["yes"] * 15 + ["no"] * 5, open=[f"answer {i}" for i in range(30)])
    assert binary_question_ratio(recs, FIELDS) == []
    findings = binary_question_ratio(recs, GROUPED)
    assert len(findings) == 1
    f = findings[0]
    assert f.sample_index == -1
    assert f.metadata["group"] == "judge"
    assert f.metadata["binary_count"] == 20
    assert f.metadata["naive_majority_score"] == 0.75
    assert f.explanation.startswith("In group subset='judge', 20/20 samples (100%)")


def test_groups_below_minimum_size_are_skipped():
    recs = grouped_records(tiny=["yes"] * 19, open=[f"answer {i}" for i in range(30)])
    assert binary_question_ratio(recs, GROUPED) == []


def test_all_groups_below_minimum_size_is_not_applicable():
    recs = grouped_records(a=["yes"] * 5, b=["no"] * 5)
    with pytest.raises(ScannerNotApplicable, match=r"fewer than 20.*--no-group-by"):
        binary_question_ratio(recs, GROUPED)


def test_ungrouped_finding_is_unchanged():
    f = binary_question_ratio(records(*["yes"] * 6, *["no"] * 4), FIELDS)[0]
    assert "group" not in f.metadata
    assert f.explanation.startswith("10/10 samples (100%) have binary yes/no answers.")


# ---------------------------------------------------------------------------
# Letter targets with choices (issue #33)
# ---------------------------------------------------------------------------

CHOICE_FIELDS = FieldMap(question="q", answer="a", choices="choices")


def mc_records(*rows: tuple[str, list[str]]) -> list[dict]:
    return [{"q": f"question {i}", "a": a, "choices": c} for i, (a, c) in enumerate(rows)]


def test_yes_no_choices_are_measured_as_choice_text():
    rows = [("A", ["Yes", "No"])] * 7 + [("B", ["Yes", "No"])] * 3
    findings = binary_question_ratio(mc_records(*rows), CHOICE_FIELDS)
    assert len(findings) == 1
    m = findings[0].metadata
    assert (m["yes_count"], m["no_count"], m["binary_count"]) == (7, 3, 10)
    assert m["measured"] == "choice_text"
    assert "choice text" in findings[0].explanation


def test_letters_without_choices_are_not_binary():
    rows = [("A", ["Yes", "No"])] * 7 + [("B", ["Yes", "No"])] * 3
    assert binary_question_ratio(mc_records(*rows), FIELDS) == []


def test_open_choice_texts_no_finding():
    rows = [("A", ["mri", "ct"]), ("B", ["axial", "coronal"])] * 5
    assert binary_question_ratio(mc_records(*rows), CHOICE_FIELDS) == []


def test_text_yes_no_targets_with_choices_are_unchanged():
    rows = [("yes", ["yes", "no"])] * 6 + [("no", ["yes", "no"])] * 4
    findings = binary_question_ratio(mc_records(*rows), CHOICE_FIELDS)
    plain = binary_question_ratio(mc_records(*rows), FIELDS)
    assert [f.to_dict() for f in findings] == [f.to_dict() for f in plain]
    assert "measured" not in findings[0].metadata
