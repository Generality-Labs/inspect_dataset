from inspect_dataset._types import FieldMap
from inspect_dataset.scanners.forced_choice_leakage import forced_choice_leakage

FIELDS = FieldMap(question="q", answer="a")


def rec(question: str, answer: str) -> list[dict]:
    return [{"q": question, "a": answer}]


def test_no_or_no_finding():
    assert forced_choice_leakage(rec("is this an mri?", "yes"), FIELDS) == []


def test_or_answer_matches_flagged():
    findings = forced_choice_leakage(rec("is this an mri or a ct scan?", "mri"), FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "forced_choice_leakage"
    assert f.severity == "medium"
    assert f.category == "leakage"


def test_or_answer_not_in_options_no_finding():
    # "or" present but answer is unrelated
    assert forced_choice_leakage(rec("is this big or small?", "yes"), FIELDS) == []


def test_left_option_matched():
    findings = forced_choice_leakage(rec("is the lesion on the left or right?", "left"), FIELDS)
    assert len(findings) == 1


def test_right_option_matched():
    findings = forced_choice_leakage(rec("is the lesion on the left or right?", "right"), FIELDS)
    assert len(findings) == 1


def test_case_insensitive_match():
    findings = forced_choice_leakage(
        rec("is this supratentorial or infratentorial?", "Supratentorial"), FIELDS
    )
    assert len(findings) == 1


def test_article_stripped_from_options():
    # "an mri" → "mri" after stripping article
    findings = forced_choice_leakage(rec("is this an mri or a ct scan?", "ct scan"), FIELDS)
    assert len(findings) == 1


def test_multiple_records_only_matching_flagged():
    records = [
        {"q": "is this an mri or ct?", "a": "mri"},  # flagged
        {"q": "what is the diagnosis?", "a": "cancer"},  # not flagged
        {"q": "is this normal or abnormal?", "a": "yes"},  # not flagged (answer not an option)
    ]
    findings = forced_choice_leakage(records, FIELDS)
    assert len(findings) == 1
    assert findings[0].sample_index == 0


def test_metadata_contains_options():
    findings = forced_choice_leakage(rec("is this an mri or a ct scan?", "mri"), FIELDS)
    assert "options" in findings[0].metadata
    assert len(findings[0].metadata["options"]) >= 2
