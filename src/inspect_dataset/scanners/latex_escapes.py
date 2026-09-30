from __future__ import annotations

import re
from typing import Any

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef, get_sample_id

# Control characters produced by Python (and JSON) string escapes, mapped to the
# letter the escape consumed. "\frac" in a non-raw string becomes "\x0c" + "rac".
_ESCAPE_LETTERS = {
    "\x07": "a",
    "\x08": "b",
    "\t": "t",
    "\n": "n",
    "\x0b": "v",
    "\x0c": "f",
    "\r": "r",
}

# Common LaTeX control words that start with one of the escape letters above.
_COMMANDS = frozenset(
    {
        # \a
        "alpha", "approx", "angle", "ast", "arccos", "arcsin", "arctan", "arg",
        "aleph", "amalg", "asymp", "arrowvert",
        # \b
        "beta", "begin", "boxed", "bar", "binom", "bf", "big", "bigg", "bigl",
        "bigr", "biggl", "biggr", "bmod", "bot", "bullet", "backslash", "because",
        "bigcup", "bigcap", "bigoplus", "bigotimes", "bigvee", "bigwedge",
        "boldsymbol", "bowtie", "boxtimes", "breve",
        # \f
        "frac", "forall", "flat", "frown", "fbox", "footnotesize",
        # \n
        "neq", "ne", "nabla", "not", "neg", "nu", "ni", "notin", "nleq", "ngeq",
        "nmid", "newline", "nonumber", "noindent", "nexists", "nsubseteq",
        "nparallel", "natural", "nearrow", "nwarrow", "nless", "ngtr", "nsim",
        "ncong", "normalsize",
        # \r
        "right", "rho", "rightarrow", "rangle", "rceil", "rfloor", "rm", "rbrace",
        "rbrack", "rvert", "rVert", "rightleftharpoons", "rightharpoonup",
        "rightharpoondown", "restriction", "rtimes", "rmoustache",
        # \t
        "times", "text", "theta", "tfrac", "tbinom", "tan", "tanh", "tau", "to",
        "top", "triangle", "tilde", "textbf", "textit", "textrm", "texttt",
        "textsf", "textup", "textnormal", "textstyle", "therefore", "tt",
        "triangleq", "triangleleft", "triangleright", "tiny", "textcolor",
        "textsuperscript", "textsubscript", "tag",
        # \v
        "vec", "varepsilon", "varphi", "vartheta", "varrho", "varsigma", "varpi",
        "varkappa", "varnothing", "vee", "vert", "vdots", "vdash", "vline",
        "vspace", "vskip", "vphantom",
    }
)  # fmt: skip

_ESCAPED_COMMAND = re.compile("([\x07\x08\t\n\x0b\x0c\r])([A-Za-z]+)")

# A display-math line often starts with a one-letter variable, so a line break
# followed by one letter ("\n" + "u") is layout, not a collapsed \nu or \ne.
_LINE_BREAKS = frozenset("\n\r")

# Math regions: $$...$$, \[...\], \(...\) and $...$. Inline $...$ may not
# contain a blank line, since TeX ends inline math at a paragraph break. That
# keeps currency dollars in separate paragraphs from pairing up.
_MATH = re.compile(
    r"(?<!\\)\$\$.+?(?<!\\)\$\$"
    r"|\\\[.+?\\\]"
    r"|\\\(.+?\\\)"
    r"|(?<!\\)\$(?:[^$\\\n]|\\.|\n(?![ \t\r]*\n))+\$",
    re.DOTALL,
)

_CONTEXT = 20
_MAX_IN_EXPLANATION = 3


def _hits(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for math in _MATH.finditer(text):
        for m in _ESCAPED_COMMAND.finditer(text, math.start(), math.end()):
            escape, letters = m.group(1), m.group(2)
            if escape in _LINE_BREAKS and len(letters) < 2:
                continue
            name = _ESCAPE_LETTERS[escape] + letters
            if name not in _COMMANDS:
                continue
            start, end = m.start(), m.end()
            # An odd run of backslashes before the escape leaves one stray
            # backslash that belongs to the command ("\\\frac" in the source).
            run = len(text[:start]) - len(text[:start].rstrip("\\"))
            if run % 2 == 1:
                start -= 1
            command = "\\" + name
            before = text[max(0, start - _CONTEXT) : start]
            after = text[end : end + _CONTEXT]
            hits.append(
                {
                    "offset": start,
                    "span": text[start:end],
                    "command": command,
                    "context": before + text[start:end] + after,
                    "repaired_context": before + command + after,
                }
            )
    return hits


def _texts(record: Record, fields: FieldMap) -> list[tuple[str, str]]:
    texts = [
        ("question", str(record.get(fields.question, "") or "")),
        ("answer", str(record.get(fields.answer, "") or "")),
    ]
    choices = record.get("choices")
    if isinstance(choices, list):
        texts.extend(
            (f"choices[{j}]", choice)
            for j, choice in enumerate(choices)  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            if isinstance(choice, str)
        )
    return texts


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings: list[Finding] = []
    for i, record in enumerate(records):
        for field_role, text in _texts(record, fields):
            hits = _hits(text)
            if not hits:
                continue
            shown = "; ".join(
                f"{h['context']!r} should likely be {h['repaired_context']!r}"
                for h in hits[:_MAX_IN_EXPLANATION]
            )
            more = len(hits) - _MAX_IN_EXPLANATION
            if more > 0:
                shown += f"; and {more} more"
            commands = ", ".join(dict.fromkeys(h["command"] for h in hits))
            line: int | None = None
            if not field_role.startswith("choices"):
                offset_val = record.get("__md_body_offset__", 0)
                offset = offset_val if isinstance(offset_val, int) else 0
                line = text.count("\n", 0, hits[0]["offset"]) + 1 + offset
            findings.append(
                Finding(
                    scanner="latex_escapes",
                    severity="medium",
                    category="format",
                    explanation=(
                        f"The {field_role} has LaTeX math where a backslash was "
                        f"consumed by a string escape, turning {commands} into a "
                        f"control character plus letters. The model sees broken "
                        f"math. {shown}"
                    ),
                    sample_index=i,
                    sample_id=get_sample_id(record, fields, i),
                    line=line,
                    metadata={"field": field_role, "hits": hits},
                )
            )
    return findings


latex_escapes = ScannerDef(
    name="latex_escapes",
    fn=_scan,
    description=(
        "Flag LaTeX commands inside math whose backslash was eaten by a Python "
        "string escape, such as \\frac stored as a form feed followed by 'rac'."
    ),
)
