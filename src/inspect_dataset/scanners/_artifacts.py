"""Shared helpers for cross-artifact scanners.

Cross-artifact scanners compare gold answers against extraction artifacts on
disk (tool outputs from the benchmark's extraction cache). Records opt in by
carrying ``__artifacts_dir__`` — set by the CLI's ``--files-root`` option,
which resolves ``<files_root>/<sample_id>/`` per record. Within an artifacts
directory, every non-empty ``*.txt`` / ``*.md`` file except ``ground_truth.*``
and ``index.md`` is treated as one extraction tool's text output.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from inspect_dataset._types import Record

_TABLE_DELIMITER = re.compile(r"^\|[\s:|-]+\|?\s*$")
_IMAGE_LINK = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HEADING_PREFIX = re.compile(r"^#{1,6}\s+")
# LaTeX math renders as glyphs in the PDF (\tau -> τ), so math spans cannot be
# verified against a text layer and are excluded from token extraction.
_MATH_SPAN = re.compile(r"\$\$.*?\$\$|\$[^$\n]*\$", re.DOTALL)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_WORD = re.compile(r"[a-z]{2,}")


def tool_texts(record: Record) -> dict[str, str]:
    """Read the non-empty tool text outputs for a record, keyed by file stem."""
    artifacts_dir = record.get("__artifacts_dir__")
    if not artifacts_dir:
        return {}
    directory = Path(str(artifacts_dir))
    texts: dict[str, str] = {}
    for path in sorted(directory.glob("*")):
        if path.suffix not in (".txt", ".md"):
            continue
        if path.name == "index.md" or path.stem.startswith("ground_truth"):
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        if text.strip():
            # Re-join words hyphenated across line breaks before tokenising.
            texts[path.stem] = text.replace("-\n", "")
    return texts


def strip_markdown(text: str, strip_math: bool = True) -> str:
    r"""Reduce markdown to comparable text.

    ``strip_math`` removes LaTeX math spans entirely — right for checking
    whether gold content exists on the page (LaTeX commands never appear in a
    text layer), wrong for checking what the gold covers (math spans can
    contain literal words like ``\text{apply}`` that do render on the page).
    """
    if strip_math:
        text = _MATH_SPAN.sub(" ", text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if _TABLE_DELIMITER.match(stripped):
            continue
        stripped = _IMAGE_LINK.sub(" ", stripped)
        stripped = _LINK.sub(r"\1", stripped)
        stripped = _HEADING_PREFIX.sub("", stripped)
        stripped = stripped.replace("|", " ").replace("**", "").replace("`", "")
        lines.append(stripped)
    return "\n".join(lines)


def word_tokens(text: str) -> set[str]:
    return set(_WORD.findall(unicodedata.normalize("NFKC", text).lower()))


def number_sources(text: str) -> dict[str, str]:
    """Map each normalised number to its first original spelling in text."""
    numbers: dict[str, str] = {}
    for match in _NUMBER.findall(unicodedata.normalize("NFKC", text)):
        normalised = match.replace(",", "").rstrip(".")
        if normalised and normalised not in numbers:
            numbers[normalised] = match
    return numbers


def number_tokens(text: str) -> set[str]:
    return set(number_sources(text))


def find_line(text: str, needle: str) -> int | None:
    """1-based line of the first case-insensitive occurrence of needle."""
    lowered = needle.lower()
    for line_no, line in enumerate(text.splitlines(), start=1):
        if lowered in line.lower():
            return line_no
    return None


def body_offset(record: Record) -> int:
    offset = record.get("__md_body_offset__", 0)
    return offset if isinstance(offset, int) else 0
