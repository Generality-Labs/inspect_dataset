from inspect_dataset._types import FieldMap
from inspect_dataset.scanners.markdown_integrity import markdown_integrity

FIELDS = FieldMap(question="q", answer="a")


def rec(answer: str, **extra) -> list[dict]:
    return [{"q": "reproduce the page", "a": answer, **extra}]


GOOD_TABLE = """\
| Item | 2023 | 2022 |
| --- | ---: | ---: |
| Cash | 10 | 20 |
| **Total** | 10 | 20 |
"""


def test_well_formed_table_no_findings():
    assert markdown_integrity(rec(GOOD_TABLE), FIELDS) == []


def test_column_count_mismatch_flagged():
    md = "| A | B |\n| --- | --- |\n| 1 | 2 | 3 |\n"
    findings = markdown_integrity(rec(md), FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "medium"
    assert f.line == 3
    assert f.metadata["expected_cols"] == 2
    assert f.metadata["actual_cols"] == 3


def test_missing_delimiter_row_flagged():
    md = "| A | B |\n| 1 | 2 |\n"
    findings = markdown_integrity(rec(md), FIELDS)
    assert len(findings) == 1
    assert "delimiter" in findings[0].explanation


def test_empty_row_flagged_low():
    md = "| A | B |\n| --- | --- |\n|  |  |\n"
    findings = markdown_integrity(rec(md), FIELDS)
    assert len(findings) == 1
    assert findings[0].severity == "low"


def test_section_row_with_empty_value_cells_ok():
    md = "| A | B | C |\n| --- | --- | --- |\n| **ASSETS** |  |  |\n"
    assert markdown_integrity(rec(md), FIELDS) == []


def test_heading_jump_flagged():
    md = "# Title\n\n### Sub-sub\n"
    findings = markdown_integrity(rec(md), FIELDS)
    assert len(findings) == 1
    assert findings[0].severity == "low"
    assert findings[0].line == 3


def test_heading_step_down_ok():
    md = "## Title\n\n# Top\n\n## Again\n"
    assert markdown_integrity(rec(md), FIELDS) == []


def test_empty_image_link_flagged():
    md = "Some text\n\n![chart]()\n"
    findings = markdown_integrity(rec(md), FIELDS)
    assert len(findings) == 1
    assert findings[0].line == 3


def test_body_offset_applied():
    md = "| A | B |\n| --- | --- |\n| 1 | 2 | 3 |\n"
    findings = markdown_integrity(rec(md, __md_body_offset__=7), FIELDS)
    assert findings[0].line == 10


def test_table_at_end_of_text_checked():
    md = "intro\n\n| A | B |\n| 1 | 2 |"
    findings = markdown_integrity(rec(md), FIELDS)
    assert len(findings) == 1


def test_plain_answer_no_findings():
    assert markdown_integrity(rec("yes"), FIELDS) == []
