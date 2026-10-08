from inspect_dataset._types import FieldMap
from inspect_dataset.scanners.encoding_issues import encoding_issues

FIELDS = FieldMap(question="q", answer="a")


def rec(question: str, answer: str) -> list[dict]:
    return [{"q": question, "a": answer}]


def test_clean_record_no_finding():
    assert encoding_issues(rec("what is shown?", "yes"), FIELDS) == []


def test_tab_in_answer_flagged():
    findings = encoding_issues(rec("what structures are visible?", "skull\tcartilage"), FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "encoding_issues"
    assert f.severity == "low"
    assert f.category == "format"
    assert f.metadata["field"] == "answer"


def test_tab_in_question_flagged():
    findings = encoding_issues(rec("what\tis shown?", "yes"), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["field"] == "question"


def test_null_byte_flagged():
    findings = encoding_issues(rec("what is shown?", "yes\x00no"), FIELDS)
    assert len(findings) == 1


def test_newline_not_flagged():
    # \n and \r are legitimate in multi-line text
    assert encoding_issues(rec("what is shown?", "line one\nline two"), FIELDS) == []


def test_both_fields_bad_two_findings():
    findings = encoding_issues(rec("q\x01estion", "ans\twer"), FIELDS)
    assert len(findings) == 2
    fields_flagged = {f.metadata["field"] for f in findings}
    assert fields_flagged == {"question", "answer"}


def test_bad_chars_in_metadata():
    findings = encoding_issues(rec("what?", "skull\tcartilage"), FIELDS)
    assert findings[0].metadata["bad_chars"] == ["'\\t'"]


def test_del_character_flagged():
    findings = encoding_issues(rec("what?", "ans\x7fwer"), FIELDS)
    assert len(findings) == 1


# MATH (EleutherAI/hendrycks_math) indents Asymptote code with tabs.
MATH_ASY = (
    "Below is the graph of $y = a \\sin bx$. Find $b.$\n\n"
    "[asy]import TrigMacros;\n\nreal g(real x)\n{\n\treturn (-2*sin(x/3));\n}\n[/asy]"
)


def test_tab_inside_asy_block_not_flagged():
    assert encoding_issues(rec(MATH_ASY, "3"), FIELDS) == []


def test_tab_inside_fenced_code_not_flagged():
    text = "Fix this:\n```python\ndef f():\n\treturn 1\n```"
    assert encoding_issues(rec(text, "ok"), FIELDS) == []


def test_tab_inside_unclosed_fence_not_flagged():
    assert encoding_issues(rec("```\nif x:\n\ty = 1", "ok"), FIELDS) == []


def test_tab_outside_code_still_flagged():
    text = MATH_ASY + "\n\nthree\tdresses"
    findings = encoding_issues(rec(text, "3"), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["bad_chars"] == ["'\\t'"]


def test_tab_after_closed_fence_still_flagged():
    text = "```\n\tx = 1\n```\nthree\tdresses"
    findings = encoding_issues(rec(text, "ok"), FIELDS)
    assert len(findings) == 1


def test_tab_between_asy_blocks_still_flagged():
    # MATH math_0a71fa24 has tabs just after a closing [/asy].
    text = "[asy]\n\tdraw(a);\n[/asy] \tWhat fraction?\n[asy]\n\tdraw(b);\n[/asy]"
    findings = encoding_issues(rec(text, "1/2"), FIELDS)
    assert len(findings) == 1


def test_other_control_char_inside_code_still_flagged():
    text = '[asy]\n\tlabel("$\x0crac{1}{2}$");\n[/asy]'
    findings = encoding_issues(rec(text, "3"), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["bad_chars"] == ["'\\x0c'"]


def test_tab_used_as_indentation_not_flagged():
    traceback = 'Traceback:\n\tFile "a.py", line 1\n\t\traise ValueError\n  \tindented after spaces'
    assert encoding_issues(rec(traceback, "ok"), FIELDS) == []


def test_tab_inside_a_line_still_flagged_after_indentation():
    findings = encoding_issues(rec("\tthree\tdresses", "ok"), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["bad_chars"] == ["'\\t'"]


def test_control_character_from_a_latex_command_is_named_and_medium():
    # "\textsubscript" in a non-raw string: a tab, then "extsubscript"
    question = "In a crystal similar to Mn\textsubscript{3}Ge, which property holds?"
    findings = encoding_issues(rec(question, "ok"), FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "medium"
    assert f.metadata["latex_commands"] == ["\\textsubscript"]
    assert "\\textsubscript" in f.explanation
    assert "escape" in f.explanation


def test_backspace_and_form_feed_from_latex_are_named():
    question = "Find \beta given \frac{1}{2}"
    findings = encoding_issues(rec(question, "ok"), FIELDS)
    assert findings[0].metadata["latex_commands"] == ["\\beta", "\\frac"]
    assert findings[0].severity == "medium"


def test_a_stray_tab_in_prose_stays_low():
    findings = encoding_issues(rec("what?", "skull\tcartilage"), FIELDS)
    assert findings[0].severity == "low"
    assert "latex_commands" not in findings[0].metadata


def test_a_latex_command_at_the_start_of_a_line_is_not_indentation():
    question = "What is the half-life of\n\textsuperscript{227}Th?"
    findings = encoding_issues(rec(question, "ok"), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["latex_commands"] == ["\\textsuperscript"]


def test_tabs_separating_table_columns_not_flagged():
    table = "Translate:\n1\tApo onadewadewa\tYou will be good.\n2\tApo onanae\tYou will go."
    assert encoding_issues(rec(table, "ok"), FIELDS) == []


def test_a_tab_after_a_bullet_not_flagged():
    text = "Include:\n•\tBreakdown of income\n-\tFor revenue\n3.\tFor expenses"
    assert encoding_issues(rec(text, "ok"), FIELDS) == []


def test_a_single_tab_inside_prose_still_flagged():
    findings = encoding_issues(rec("She bought three\tdresses.", "ok"), FIELDS)
    assert findings[0].metadata["bad_chars"] == ["'\\t'"]
