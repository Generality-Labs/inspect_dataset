from inspect_dataset._types import FieldMap
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
