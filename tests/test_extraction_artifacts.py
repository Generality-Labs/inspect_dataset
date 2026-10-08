import pytest

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
    records = [{"q": "what?", "a": "bad\u00a0text", "__md_body_offset__": 6}]
    findings = extraction_artifacts(records, FIELDS)
    assert findings[0].line == 7


def test_counts_aggregated():
    findings = extraction_artifacts(rec("what?", "ﬁrst ﬁne"), FIELDS)
    assert findings[0].metadata["artifacts"]["ligature fi (U+FB01)"] == 2


def test_question_and_answer_scanned_separately():
    findings = extraction_artifacts(rec("so\u00adft?", "an\u00a0swer"), FIELDS)
    assert {f.metadata["field"] for f in findings} == {"question", "answer"}


def test_non_breaking_space_alone_not_flagged_in_a_published_dataset():
    for source in ("hf", "inspect_task"):
        fields = FieldMap(question="q", answer="a", source_type=source)
        assert extraction_artifacts(rec("Given n\u00a0=\u00a03, what?", "4"), fields) == []


def test_non_breaking_space_counted_beside_another_artifact():
    fields = FieldMap(question="q", answer="a", source_type="hf")
    (finding,) = extraction_artifacts(rec("the \ufb01rst\u00a0step", "4"), fields)
    assert finding.metadata["artifacts"] == {
        "ligature fi (U+FB01)": 1,
        "non-breaking space (U+00A0)": 1,
    }


def test_non_breaking_space_alone_still_flagged_in_local_annotations():
    fields = FieldMap(question="q", answer="a", source_type="local")
    assert len(extraction_artifacts(rec("what?", "gold\u00a0text"), fields)) == 1


@pytest.mark.parametrize(
    "word",
    [
        "\u0995\u09cd\u200c\u09b7",  # Bengali: ka, virama, ZWNJ, ssa
        "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645",  # Persian: mi-khaham
        "\u0c15\u0c4d\u200d\u0c37",  # Telugu: ka, virama, ZWJ, ssa
    ],
)
def test_a_joiner_inside_a_word_of_a_script_that_uses_it_is_spelling(word: str):
    assert extraction_artifacts(rec(f"How many apples? {word}", "4"), FIELDS) == []


def test_a_joiner_between_latin_letters_still_flagged():
    (finding,) = extraction_artifacts(rec("pro\u200ccess the data", "4"), FIELDS)
    assert finding.metadata["artifacts"] == {"zero-width non-joiner (U+200C)": 1}
