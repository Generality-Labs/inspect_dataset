from inspect_dataset._types import FieldMap
from inspect_dataset.scanners.latex_escapes import latex_escapes

FIELDS = FieldMap(question="q", answer="a")

# Real strings from AIME 2024 (Maxwell-Jia/AIME_2024).
AIME_2024_I_1 = (
    "When she walks $s+2$ kilometers per hour, the walk takes her 2 hours and 24 "
    "minutes. Suppose Aya walks at $s+\x0crac{1}{2}$ kilometers per hour."
)
AIME_2024_I_15 = (
    "The value of $r^2$ can be written as $\\\x0crac{p}{q}$, where $p$ and $q$ "
    "are relatively prime positive integers. Find $p+q$."
)
AIME_2024_II_8 = (
    "The difference $r_i-r_o$ can be written as $\tfrac{m}{n}$, where $m$ and $n$ "
    "are relatively prime positive integers. Find $m+n$."
)


def rec(question: str, answer: str = "1") -> list[dict]:
    return [{"q": question, "a": answer}]


def test_clean_latex_no_finding():
    assert latex_escapes(rec("Find $\\frac{1}{2} \\times x$."), FIELDS) == []


def test_form_feed_frac_flagged():
    findings = latex_escapes(rec(AIME_2024_I_1), FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "latex_escapes"
    assert f.severity == "medium"
    assert f.category == "format"
    assert f.metadata["field"] == "question"
    [hit] = f.metadata["hits"]
    assert hit["span"] == "\x0crac"
    assert hit["command"] == "\\frac"
    assert "s+\x0crac{1}{2}$" in hit["context"]
    assert "s+\\frac{1}{2}$" in hit["repaired_context"]
    assert "\\frac" in f.explanation


def test_form_feed_after_stray_backslash_absorbs_it():
    [f] = latex_escapes(rec(AIME_2024_I_15), FIELDS)
    [hit] = f.metadata["hits"]
    assert hit["span"] == "\\\x0crac"
    assert "$\\frac{p}{q}$" in hit["repaired_context"]


def test_double_backslash_before_escape_is_kept():
    # A LaTeX line break before the collapsed command stays a line break.
    [f] = latex_escapes(rec("$$a \\\\\x0crac{1}{2}$$"), FIELDS)
    [hit] = f.metadata["hits"]
    assert hit["span"] == "\x0crac"
    assert "\\\\\\frac{1}{2}" in hit["repaired_context"]


def test_tab_tfrac_flagged():
    [f] = latex_escapes(rec(AIME_2024_II_8), FIELDS)
    [hit] = f.metadata["hits"]
    assert hit["span"] == "\tfrac"
    assert hit["command"] == "\\tfrac"


def test_newline_and_carriage_return_flagged():
    text = "Show $a \neq b$ and $\\left( x \right)$ and $\x07lpha + \x08eta$."
    [f] = latex_escapes(rec(text), FIELDS)
    commands = [h["command"] for h in f.metadata["hits"]]
    assert commands == ["\\neq", "\\right", "\\alpha", "\\beta"]


def test_vertical_tab_flagged():
    [f] = latex_escapes(rec("Let $\x0bec{v}$ be a vector."), FIELDS)
    assert f.metadata["hits"][0]["command"] == "\\vec"


def test_all_math_delimiters_checked():
    for text in (
        "$$x \times y$$",
        "\\(x \times y\\)",
        "\\[x \times y\\]",
        "$x \times y$",
    ):
        findings = latex_escapes(rec(text), FIELDS)
        assert len(findings) == 1, text


def test_prose_outside_math_not_flagged():
    # MMLU-Pro prose: a paragraph break before "equations" is not \nequations.
    text = "Consider the other\n\nequations. The\ttext is fine."
    assert latex_escapes(rec(text), FIELDS) == []


def test_inline_math_does_not_span_blank_line():
    # Currency dollars must not pair up across paragraphs into fake math.
    text = "It costs $5.\n\nabla is not math here, and $6 is a price."
    assert latex_escapes(rec(text), FIELDS) == []


def test_escaped_dollar_does_not_open_math():
    assert latex_escapes(rec("Price \\$5 and\neq \\$6"), FIELDS) == []


def test_letters_must_complete_a_command():
    # "\n" + "equation" would be \nequation, which is not a command.
    assert latex_escapes(rec("$$x = 1\nequation$$"), FIELDS) == []


def test_newline_before_ordinary_math_not_flagged():
    assert latex_escapes(rec("$$\nx = 1\n$$"), FIELDS) == []


def test_line_break_before_single_letter_variable_not_flagged():
    # MMLU-Pro display math: a line starting with a variable is not \ne or \nu.
    assert latex_escapes(rec("the ground:\n$$\ne=\\frac{V}{V_s}$$"), FIELDS) == []
    assert latex_escapes(rec("value problem\n$$\nu'' + u = 0$$"), FIELDS) == []


def test_tab_before_single_letter_still_flagged():
    [f] = latex_escapes(rec("$f: A \to B$"), FIELDS)
    assert f.metadata["hits"][0]["command"] == "\\to"


def test_answer_field_checked():
    findings = latex_escapes(rec("What is half?", "$\x0crac{1}{2}$"), FIELDS)
    assert [f.metadata["field"] for f in findings] == ["answer"]


def test_choices_checked_with_index():
    records = [{"q": "Pick one.", "a": "B", "choices": ["$1$", "$\x0crac{1}{2}$"]}]
    findings = latex_escapes(records, FIELDS)
    assert [f.metadata["field"] for f in findings] == ["choices[1]"]


def test_non_string_choices_ignored():
    records = [{"q": "Pick one.", "a": "B", "choices": [1, None]}]
    assert latex_escapes(records, FIELDS) == []


def test_multiple_hits_in_one_field_one_finding():
    [f] = latex_escapes(rec("$\x0crac{1}{2} \times 3$"), FIELDS)
    assert len(f.metadata["hits"]) == 2


def test_line_number_reported():
    [f] = latex_escapes(rec("First line.\nThen $\x0crac{1}{2}$."), FIELDS)
    assert f.line == 2


def test_sample_id_used():
    fields = FieldMap(question="q", answer="a", id="id")
    records = [{"id": "2024-I-1", "q": AIME_2024_I_1, "a": "204"}]
    [f] = latex_escapes(records, fields)
    assert f.sample_id == "2024-I-1"
