from __future__ import annotations

import re

from inspect_dataset._types import FieldMap, Finding, Record, Severity
from inspect_dataset.scanner import ScannerDef, get_sample_id
from inspect_dataset.scanners.latex_escapes import _ESCAPED_COMMAND, _command_name

# Control characters except for standard whitespace (\n \r \t are borderline —
# we flag \t and other non-printable controls but not \n/\r which can be
# legitimate in multi-line answers).
_CONTROL_CHARS = frozenset(range(0x20)) - {0x0A, 0x0D}  # exclude \n \r

# Tabs are normal indentation inside fenced code and Asymptote blocks. An
# unclosed fence runs to the end of the text, as in Markdown.
_CODE_BLOCK = re.compile(r"```.*?(?:```|\Z)|\[asy\].*?\[/asy\]", re.DOTALL)
# Tabs as layout rather than as a typing slip: indentation, as in code pasted
# without a fence (tracebacks and diffs in issue text), and a tab after a list
# bullet or number at the start of a line ("•\tItem", "3.\tItem").
_INDENT = re.compile(r"^[ \t]*(?:(?:[•\-*]|\d+[.)]?)\t)?[ \t]*", re.MULTILINE)
# A line with two or more tabs after its indentation is a table row: the tabs
# separate its columns.
_TABLE_ROW = re.compile(r"^[ \t]*[^\n\t]+\t[^\n\t]*\t[^\n]*$", re.MULTILINE)


def _without_layout_tabs(text: str) -> str:
    text = _CODE_BLOCK.sub(lambda m: m.group().replace("\t", ""), text)
    text = _TABLE_ROW.sub(lambda m: m.group().replace("\t", ""), text)
    return _INDENT.sub(lambda m: m.group().replace("\t", ""), text)


def _collapsed_commands(text: str) -> list[re.Match[str]]:
    r"""LaTeX commands whose backslash a string escape consumed ("\frac" became "\x0c" + "rac")."""
    return [m for m in _ESCAPED_COMMAND.finditer(text) if _command_name(m) is not None]


def _names(commands: list[re.Match[str]]) -> list[str]:
    names: list[str] = []
    for m in commands:
        name = "\\" + str(_command_name(m))
        if name not in names:
            names.append(name)
    return names


def _find_bad_chars(text: str) -> list[str]:
    seen: list[str] = []
    for ch in text:
        cp = ord(ch)
        if (cp in _CONTROL_CHARS or cp == 0x7F) and repr(ch) not in seen:  # 0x7F = DEL
            seen.append(repr(ch))
    return seen


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings = []
    for i, record in enumerate(records):
        for field_role, field_name in (("question", fields.question), ("answer", fields.answer)):
            text = str(record.get(field_name, "") or "")
            # A command can collapse at the start of a line, where its tab looks like
            # indentation, so commands are found before layout tabs are dropped.
            collapsed = _collapsed_commands(text)
            bad = _find_bad_chars(
                _without_layout_tabs(text) + "".join(m.group(1) for m in collapsed)
            )
            if not bad:
                continue
            commands = _names(collapsed)
            metadata: dict[str, object] = {"field": field_role, "bad_chars": bad, "value": text}
            severity: Severity = "low"
            cause = (
                "These are likely data entry errors and may cause silent failures in "
                "downstream processing."
            )
            if commands:
                # A collapsed command is corrupted text, not stray whitespace.
                severity = "medium"
                metadata["latex_commands"] = commands
                cause = (
                    f"They look like LaTeX {', '.join(commands)} with the backslash read as "
                    "a string escape, so the text the model sees is corrupted."
                )
            findings.append(
                Finding(
                    scanner="encoding_issues",
                    severity=severity,
                    category="format",
                    explanation=(
                        f"The {field_role} contains non-printable character(s) "
                        f"{', '.join(bad)}. {cause} Value: {text!r}"
                    ),
                    sample_index=i,
                    sample_id=get_sample_id(record, fields, i),
                    metadata=metadata,
                )
            )
    return findings


encoding_issues = ScannerDef(
    name="encoding_issues",
    fn=_scan,
    description=(
        "Flag questions or answers containing non-printable or control characters "
        "(tabs, nulls, etc.) that are likely data entry errors. Tabs used as indentation, "
        "or inside fenced code and Asymptote blocks, are ignored. A control character that "
        'swallowed the start of a LaTeX command (a tab, then "extbf") is named and medium.'
    ),
)
