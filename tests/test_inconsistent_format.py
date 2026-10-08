import pytest

from inspect_dataset._types import FieldMap
from inspect_dataset.scanner import ScannerNotApplicable
from inspect_dataset.scanners.inconsistent_format import inconsistent_format

FIELDS = FieldMap(question="q", answer="a")


def records(*answers: str) -> list[dict]:
    return [{"q": f"question {i}", "a": a} for i, a in enumerate(answers)]


# ---------------------------------------------------------------------------
# Capitalisation
# ---------------------------------------------------------------------------


def test_all_lowercase_no_finding():
    assert inconsistent_format(records("yes", "no", "blue", "red", "green"), FIELDS) == []


def test_uppercase_outlier_in_lowercase_majority():
    # 9 lowercase, 1 uppercase → outlier flagged
    recs = records(*["yes"] * 9, "Yes")
    findings = [
        f for f in inconsistent_format(recs, FIELDS) if f.metadata.get("issue") == "capitalisation"
    ]
    assert len(findings) == 1
    assert findings[0].sample_index == 9
    assert findings[0].severity == "low"
    assert findings[0].category == "format"


def test_lowercase_outlier_in_uppercase_majority():
    # 9 uppercase-first, 1 lowercase → flagged
    recs = records(*["Yes"] * 9, "yes")
    findings = [
        f for f in inconsistent_format(recs, FIELDS) if f.metadata.get("issue") == "capitalisation"
    ]
    assert len(findings) == 1
    assert findings[0].sample_index == 9


def test_mixed_capitalisation_below_threshold_no_finding():
    # 50/50 split — neither majority
    recs = records(*["yes", "Yes"] * 5)
    findings = [
        f for f in inconsistent_format(recs, FIELDS) if f.metadata.get("issue") == "capitalisation"
    ]
    assert findings == []


# ---------------------------------------------------------------------------
# Trailing punctuation
# ---------------------------------------------------------------------------


def test_mostly_no_punctuation_outlier_flagged():
    recs = records(*["yes"] * 9, "yes.")
    findings = [
        f
        for f in inconsistent_format(recs, FIELDS)
        if f.metadata.get("issue") == "trailing_punctuation"
    ]
    assert len(findings) == 1
    assert findings[0].sample_index == 9


def test_mostly_punctuation_outlier_flagged():
    recs = records(*["yes."] * 9, "yes")
    findings = [
        f
        for f in inconsistent_format(recs, FIELDS)
        if f.metadata.get("issue") == "trailing_punctuation"
    ]
    assert len(findings) == 1
    assert findings[0].sample_index == 9


def test_mixed_punctuation_below_threshold_no_finding():
    recs = records(*["yes.", "yes"] * 5)
    findings = [
        f
        for f in inconsistent_format(recs, FIELDS)
        if f.metadata.get("issue") == "trailing_punctuation"
    ]
    assert findings == []


# ---------------------------------------------------------------------------
# Length outliers
# ---------------------------------------------------------------------------


def test_length_outlier_flagged():
    # 20 one-word answers + one 20-word outlier — outlier exceeds mean + 3*stdev
    long = (
        "one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
    )
    recs = records(*["yes"] * 20, long)
    findings = [
        f for f in inconsistent_format(recs, FIELDS) if f.metadata.get("issue") == "length_outlier"
    ]
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert findings[0].sample_index == 20


def test_uniform_lengths_no_length_outlier():
    recs = records(*["one two three"] * 10)
    findings = [
        f for f in inconsistent_format(recs, FIELDS) if f.metadata.get("issue") == "length_outlier"
    ]
    assert findings == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_single_record_no_findings():
    assert inconsistent_format(records("yes"), FIELDS) == []


def test_empty_answers_ignored():
    # Only one non-empty answer — below minimum for comparison
    assert inconsistent_format(records("", "yes"), FIELDS) == []


def test_all_empty_no_findings():
    assert inconsistent_format(records("", ""), FIELDS) == []


# ---------------------------------------------------------------------------
# Non-scalar answer columns (issue #26)
# ---------------------------------------------------------------------------


def test_list_answers_are_not_applicable():
    recs = [{"q": "q", "a": [f"answer {i}"]} for i in range(10)]
    with pytest.raises(ScannerNotApplicable, match=r"'a'.*list"):
        inconsistent_format(recs, FIELDS)


def test_subfield_compares_elements_across_rows():
    fields = FieldMap(question="q", answer="a", answer_subfield="text")
    recs = [{"q": "q", "a": [{"text": "yes"}, {"text": "no"}]} for _ in range(5)]
    recs.append({"q": "q", "a": [{"text": "no"}, {"text": "Yes"}]})
    findings = [
        f for f in inconsistent_format(recs, fields) if f.metadata.get("issue") == "capitalisation"
    ]
    assert len(findings) == 1
    assert findings[0].sample_index == 5
    assert findings[0].metadata == {
        "answer": "Yes",
        "issue": "capitalisation",
        "answer_subfield": "text",
        "element_index": 1,
    }


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


def test_consistent_subsets_are_flagged_only_when_pooled():
    # BBH shape: one subset answers valid/invalid, another Yes/No
    recs = grouped_records(formal=["valid", "invalid"] * 5, causal=["Yes", "No"])
    assert len(inconsistent_format(recs, FIELDS)) == 2
    assert inconsistent_format(recs, GROUPED) == []


def test_majority_is_computed_per_group():
    # Pooled there is no 80% majority, so the lone "Yes" in subset a is hidden
    recs = grouped_records(a=[*["yes"] * 9, "Yes"], b=["Yes"] * 11)
    assert inconsistent_format(recs, FIELDS) == []
    findings = inconsistent_format(recs, GROUPED)
    assert len(findings) == 1
    f = findings[0]
    assert f.sample_index == 9
    assert f.metadata == {"answer": "Yes", "issue": "capitalisation", "group": "a"}
    assert f.explanation == (
        "Capitalisation differs from the majority in group subset='a'. "
        "majority of answers are lowercase but this is not: 'Yes'"
    )


def test_trailing_punctuation_per_group():
    recs = grouped_records(a=[*["yes"] * 9, "yes."], b=["Done."] * 11)
    findings = inconsistent_format(recs, GROUPED)
    assert [(f.sample_index, f.metadata["issue"], f.metadata["group"]) for f in findings] == [
        (9, "trailing_punctuation", "a")
    ]
    assert "group subset='a'" in findings[0].explanation


def test_length_outlier_uses_group_statistics():
    short = [*["yes"] * 20, "one two three four five six"]
    long = ["one two three four five six seven eight nine ten"] * 20
    recs = grouped_records(short=short, long=long)
    assert [
        f for f in inconsistent_format(recs, FIELDS) if f.metadata["issue"] == "length_outlier"
    ] == []
    findings = inconsistent_format(recs, GROUPED)
    assert len(findings) == 1
    f = findings[0]
    assert f.sample_index == 20
    assert f.metadata["group"] == "short"
    assert f.metadata["mean_word_count"] == round((20 + 6) / 21, 2)
    assert f.explanation.startswith("Answer is a length outlier in group subset='short': 6 words")


def test_rows_missing_the_group_field_form_a_none_group():
    recs = grouped_records(a=["yes"] * 10)
    recs += [{"q": f"loose {i}", "a": a} for i, a in enumerate([*["Yes"] * 9, "yes"])]
    findings = inconsistent_format(recs, GROUPED)
    assert len(findings) == 1
    assert findings[0].sample_index == 19
    assert findings[0].metadata["group"] is None
    assert "group subset=None" in findings[0].explanation


def test_ungrouped_findings_have_no_group_key():
    findings = inconsistent_format(records(*["yes"] * 9, "Yes"), FIELDS)
    assert findings[0].metadata == {"answer": "Yes", "issue": "capitalisation"}
    assert findings[0].explanation == (
        "Capitalisation differs from dataset majority. "
        "majority of answers are lowercase but this is not: 'Yes'"
    )


def test_unhashable_group_values_are_not_applicable():
    recs = [{"q": "q", "a": "yes", "subset": ["x"]} for _ in range(5)]
    with pytest.raises(ScannerNotApplicable, match=r"'subset'.*list"):
        inconsistent_format(recs, GROUPED)


# ---------------------------------------------------------------------------
# The task's scorer (issue #33)
# ---------------------------------------------------------------------------


def test_non_verbatim_scorer_is_not_applicable():
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/choice"])
    recs = records("one two three four five six", "Yes", "yes", "yes", "yes.")
    with pytest.raises(ScannerNotApplicable, match="this task scores with inspect_ai/choice"):
        inconsistent_format(recs, fields)


def test_scorer_gate_comes_before_the_answer_type_check():
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/f1"])
    recs = [{"q": "q", "a": ["a list", "of answers"]}]
    with pytest.raises(ScannerNotApplicable, match="scores with inspect_ai/f1"):
        inconsistent_format(recs, fields)


def test_verbatim_scorer_measures_as_before():
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/pattern"])
    recs = records("one two three four five six", "yes", "no", "blue", "red", "green", "Big")
    findings = inconsistent_format(recs, fields)
    assert findings
    assert findings == inconsistent_format(recs, FIELDS)


def _issues(findings):
    return sorted({f.metadata["issue"] for f in findings})


CASE_AND_PUNCTUATION = ["yes", "no", "blue", "red", "green", "Big", "pink.", "grey", "teal", "gold"]


def test_exact_folds_case_and_punctuation_so_only_length_is_checked():
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/exact"])
    recs = records(*CASE_AND_PUNCTUATION)
    assert _issues(inconsistent_format(recs, FIELDS)) == ["capitalisation", "trailing_punctuation"]
    assert inconsistent_format(recs, fields) == []


def test_includes_folds_case_but_compares_punctuation():
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/includes"])
    assert _issues(inconsistent_format(records(*CASE_AND_PUNCTUATION), fields)) == [
        "trailing_punctuation"
    ]


def test_exact_still_flags_a_length_outlier():
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/exact"])
    answers = ["a b"] * 20 + ["one two three four five six seven eight nine ten eleven twelve"]
    assert _issues(inconsistent_format(records(*answers), fields)) == ["length_outlier"]


def test_partial_credit_alongside_exact_is_not_applicable():
    fields = FieldMap(question="q", answer="a", scorers=["inspect_ai/f1", "inspect_ai/exact"])
    with pytest.raises(ScannerNotApplicable, match="f1 gives partial credit"):
        inconsistent_format(records(*CASE_AND_PUNCTUATION), fields)
