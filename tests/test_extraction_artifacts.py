from inspect_dataset._types import FieldMap
from inspect_dataset.scanners.extraction_artifacts import extraction_artifacts

FIELDS = FieldMap(question="q", answer="a")


def rec(question: str, answer: str) -> list[dict]:
    return [{"q": question, "a": answer}]


def test_clean_record_no_finding():
    records = rec("what is shown?", "the profit margin")
    assert extraction_artifacts(records, FIELDS) == []


def test_ligature_flagged():
    findings = extraction_artifacts(rec("what?", "proﬁt margin"), FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "low"
    assert f.category == "format"
    assert "ligature fi (U+FB01)" in f.metadata["artifacts"]


def test_replacement_char_is_medium():
    findings = extraction_artifacts(rec("what?", "total � 42"), FIELDS)
    assert len(findings) == 1
    assert findings[0].severity == "medium"


def test_soft_hyphen_flagged():
    findings = extraction_artifacts(rec("what?", "para\u00adgraph"), FIELDS)
    assert len(findings) == 1


def test_line_number_reported():
    records = rec("what?", "clean line\nsecond\u00a0line")
    findings = extraction_artifacts(records, FIELDS)
    assert findings[0].line == 2


def test_body_offset_applied():
    records = [{"q": "what?", "a": "bad text", "__md_body_offset__": 6}]
    findings = extraction_artifacts(records, FIELDS)
    assert findings[0].line == 7


def test_counts_aggregated():
    findings = extraction_artifacts(rec("what?", "ﬁrst ﬁne"), FIELDS)
    assert findings[0].metadata["artifacts"]["ligature fi (U+FB01)"] == 2


def test_question_and_answer_scanned_separately():
    findings = extraction_artifacts(rec("so\u00adft?", "an\u00a0swer"), FIELDS)
    assert {f.metadata["field"] for f in findings} == {"question", "answer"}
