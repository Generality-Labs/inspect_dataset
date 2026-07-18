import pytest

from inspect_dataset._types import FieldMap
from inspect_dataset.scanners.numeric_provenance import numeric_provenance
from inspect_dataset.scanners.text_layer_recall import text_layer_recall

FIELDS = FieldMap(question="q", answer="a", id="id")

PAGE_TEXT = (
    "CONSOLIDATED BALANCE SHEETS\nItem 2023\nCash and equivalents $ 48,304\nTotal assets 272,425\n"
)

GOLD_MD = """\
# CONSOLIDATED BALANCE SHEETS

| Item | 2023 |
| --- | ---: |
| Cash and equivalents | $ 48,304 |
| Total assets | 272,425 |
"""


@pytest.fixture
def artifacts_dir(tmp_path):
    sample = tmp_path / "s1"
    sample.mkdir()
    (sample / "pymupdf.txt").write_text(PAGE_TEXT)
    (sample / "pdfplumber.txt").write_text(PAGE_TEXT)
    (sample / "ground_truth.md").write_text(GOLD_MD)
    (sample / "index.md").write_text("# index page, not a tool output\nsomething unrelated\n")
    return sample


def record(artifacts_dir, answer=GOLD_MD, **extra):
    rec = {
        "id": "s1",
        "q": "page_roundtrip x.pdf#page=1",
        "a": answer,
        "task_type": "page_roundtrip",
        "__artifacts_dir__": str(artifacts_dir),
    }
    rec.update(extra)
    return rec


# ---------------------------------------------------------------------------
# text_layer_recall
# ---------------------------------------------------------------------------


def test_faithful_gold_no_findings(artifacts_dir):
    assert text_layer_recall([record(artifacts_dir)], FIELDS) == []


def test_gold_word_no_tool_saw_flagged_high(artifacts_dir):
    bad = GOLD_MD.replace("equivalents", "equivalentz")
    findings = text_layer_recall([record(artifacts_dir, answer=bad)], FIELDS)
    # A swapped word is both a hallucination ("equivalentz" nowhere on the
    # page) and an omission ("equivalents" everywhere but the gold).
    assert len(findings) == 2
    unsupported = next(f for f in findings if "unsupported_words" in f.metadata)
    assert unsupported.severity == "high"
    assert "equivalentz" in unsupported.metadata["unsupported_words"]
    assert unsupported.line == 5
    omitted = next(f for f in findings if "omitted_words" in f.metadata)
    assert "equivalents" in omitted.metadata["omitted_words"]


def test_word_all_tools_found_missing_from_page_gold_flagged(artifacts_dir):
    partial = GOLD_MD.replace("| Total assets | 272,425 |\n", "")
    findings = text_layer_recall([record(artifacts_dir, answer=partial)], FIELDS)
    omissions = [f for f in findings if "missing from the gold" in f.explanation]
    assert len(omissions) == 1
    assert omissions[0].severity == "medium"
    assert "assets" in omissions[0].metadata["omitted_words"]


def test_element_gold_not_checked_for_omissions(artifacts_dir):
    table_only = "| Item | 2023 |\n| --- | --- |\n| Cash and equivalents | $ 48,304 |"
    rec = record(artifacts_dir, answer=table_only, task_type="element_reproduction")
    assert text_layer_recall([rec], FIELDS) == []


def test_word_found_by_one_tool_not_flagged(artifacts_dir):
    (artifacts_dir / "pdfplumber.txt").write_text(PAGE_TEXT.replace("BALANCE", ""))
    assert text_layer_recall([record(artifacts_dir)], FIELDS) == []


def test_ocr_resistant_skipped(artifacts_dir):
    bad = GOLD_MD.replace("equivalents", "equivalentz")
    rec = record(artifacts_dir, answer=bad, ocr_resistant=True)
    assert text_layer_recall([rec], FIELDS) == []


def test_no_artifacts_dir_skipped():
    rec = {"id": "s1", "q": "?", "a": GOLD_MD, "task_type": "page_roundtrip"}
    assert text_layer_recall([rec], FIELDS) == []


def test_empty_tool_outputs_skipped(tmp_path):
    sample = tmp_path / "s1"
    sample.mkdir()
    (sample / "pymupdf.txt").write_text("   \n")
    rec = record(sample)
    assert text_layer_recall([rec], FIELDS) == []


def test_hyphenated_linebreaks_joined(tmp_path):
    sample = tmp_path / "s1"
    sample.mkdir()
    (sample / "pymupdf.txt").write_text("correctly hyphen-\nated words\n")
    rec = record(sample, answer="correctly hyphenated words")
    assert text_layer_recall([rec], FIELDS) == []


def test_latex_math_spans_excluded(tmp_path):
    sample = tmp_path / "s1"
    sample.mkdir()
    (sample / "pymupdf.txt").write_text("The quality gate Q(d, t) < θ applies\n")
    gold = "The quality gate\n\n$$Q(d, t) < \\theta \\implies \\text{apply}$$\n\napplies\n"
    rec = record(sample, answer=gold)
    assert text_layer_recall([rec], FIELDS) == []


def test_ligatures_normalised(tmp_path):
    sample = tmp_path / "s1"
    sample.mkdir()
    (sample / "pymupdf.txt").write_text("proﬁt and loss\n")
    rec = record(sample, answer="profit and loss")
    assert text_layer_recall([rec], FIELDS) == []


# ---------------------------------------------------------------------------
# numeric_provenance
# ---------------------------------------------------------------------------


def test_all_numbers_present_no_findings(artifacts_dir):
    assert numeric_provenance([record(artifacts_dir)], FIELDS) == []


def test_number_no_tool_saw_flagged(artifacts_dir):
    bad = GOLD_MD.replace("272,425", "272,426")
    findings = numeric_provenance([record(artifacts_dir, answer=bad)], FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "high"
    assert "272426" in f.metadata["missing_numbers"]
    assert f.line == 6


def test_comma_and_dollar_normalisation(artifacts_dir):
    gold = "Cash 48304 and total 272425"
    assert numeric_provenance([record(artifacts_dir, answer=gold)], FIELDS) == []


def test_number_in_one_tool_suffices(artifacts_dir):
    (artifacts_dir / "pdfplumber.txt").write_text("nothing numeric here")
    assert numeric_provenance([record(artifacts_dir)], FIELDS) == []


def test_numeric_ocr_resistant_skipped(artifacts_dir):
    bad = GOLD_MD.replace("272,425", "999,999")
    rec = record(artifacts_dir, answer=bad, ocr_resistant=True)
    assert numeric_provenance([rec], FIELDS) == []
