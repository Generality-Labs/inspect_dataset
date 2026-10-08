"""Detect mojibake: UTF-8 text that was decoded with the wrong codec.

When UTF-8 bytes are decoded as Windows-1252, Latin-1 or Mac Roman, each
multi-byte character turns into two to four characters from that codec's
upper half: ``é`` becomes ``Ã©`` (cp1252) or ``√©`` (Mac Roman). This scanner
looks for runs of such characters that form well-formed UTF-8 byte sequences,
re-encodes them with the suspected codec and decodes them as UTF-8. It reports
a span only when that repair succeeds and gives a character from a block that
ordinary text uses. Legitimate text sometimes forms valid UTF-8 too, such as an
apostrophe before an accented letter read as Mac Roman. Those decode to IPA,
Armenian or NKo characters, so the block check rejects them.
"""

from __future__ import annotations

import contextlib
import re
import unicodedata
from dataclasses import dataclass

from inspect_dataset._types import FieldMap, Finding, Record, Severity
from inspect_dataset.scanner import ScannerDef, get_sample_id

_CODEC_NAMES = {"cp1252": "Windows-1252", "latin-1": "Latin-1", "mac_roman": "Mac Roman"}

# East Asian repairs. A single one is weak evidence: an accented letter
# followed by two symbols ("é", no-break space, "»" in French) also decodes to
# a CJK character.
_EAST_ASIAN_BLOCKS: tuple[tuple[int, int], ...] = (
    (0x3000, 0x30FF),  # CJK punctuation, kana
    (0x3400, 0x4DBF),  # CJK Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xAC00, 0xD7A3),  # Hangul syllables
    (0xFF00, 0xFFEF),  # full-width forms
)
_COMMON_BLOCKS: tuple[tuple[int, int], ...] = (
    (0x00A0, 0x017F),  # Latin-1 Supplement, Latin Extended-A
    (0x0386, 0x03CE),  # Greek letters
    (0x2000, 0x27BF),  # punctuation, currency, arrows, maths, symbols
    *_EAST_ASIAN_BLOCKS,
    (0xFEFF, 0xFEFF),  # byte order mark
    (0x1F300, 0x1FAFF),  # emoji
)
# In Mac Roman the lead bytes for Cyrillic are dashes and curly quotes, which
# legitimately precede accented letters ("—école"), so Cyrillic repairs are
# only trusted from Windows-1252.
_CYRILLIC = (0x0400, 0x045F)

# Mac Roman pairs made of a square root or approximately-equal sign followed
# by a maths symbol are real maths as often as mojibake (√π is ù).
_MATH_LEADS = frozenset("√≈")
_MATH_CONTINUATIONS = frozenset("≠∞±≤≥µ∂∑∏π∫Ω")

# Windows-1252 "Å" followed by a superscript digit is an area or volume in
# ångströms (Å², Å³) as often as mojibake (Å³ is ų).
_UNIT_PAIRS = frozenset({"Å¹", "Å²", "Å³"})

_MAX_LAYERS = 4
_CONTEXT = 20


def _byte_table(codec: str) -> dict[str, int]:
    table: dict[str, int] = {}
    for b in range(0x80, 0x100):
        with contextlib.suppress(UnicodeDecodeError):
            table[bytes([b]).decode(codec)] = b
    if codec == "cp1252":
        # Fold Latin-1 in: its upper half differs from cp1252 only in 0x80-0x9F,
        # where Latin-1 has C1 control characters. Decoders that fall back to
        # Latin-1 for the five bytes cp1252 leaves undefined produce a mix.
        for b in range(0x80, 0xA0):
            table.setdefault(chr(b), b)
    return table


def _char_class(table: dict[str, int], lo: int, hi: int) -> str:
    chars = "".join(re.escape(ch) for ch, b in table.items() if lo <= b <= hi)
    return f"[{chars}]"


@dataclass(frozen=True)
class _Codec:
    name: str
    table: dict[str, int]
    pattern: re.Pattern[str]
    blocks: tuple[tuple[int, int], ...]


def _make_codec(name: str, blocks: tuple[tuple[int, int], ...]) -> _Codec:
    table = _byte_table(name)
    cont = _char_class(table, 0x80, 0xBF)
    lead2 = _char_class(table, 0xC2, 0xDF)
    lead3 = _char_class(table, 0xE0, 0xEF)
    lead4 = _char_class(table, 0xF0, 0xF4)
    pattern = re.compile(f"{lead2}{cont}|{lead3}{cont}{{2}}|{lead4}{cont}{{3}}")
    return _Codec(name, table, pattern, blocks)


_CODECS = (
    _make_codec("cp1252", (*_COMMON_BLOCKS, _CYRILLIC)),
    _make_codec("mac_roman", _COMMON_BLOCKS),
)


@dataclass
class _Span:
    start: int
    end: int
    codec: str
    repair: str
    weak: bool
    sequences: int = 1


def _in_blocks(char: str, blocks: tuple[tuple[int, int], ...]) -> bool:
    cp = ord(char)
    return any(lo <= cp <= hi for lo, hi in blocks)


def _decode(seq: str, codec: _Codec) -> str | None:
    try:
        char = bytes(codec.table[ch] for ch in seq).decode("utf-8")
    except UnicodeDecodeError:
        return None
    if unicodedata.category(char) != "Cn" and _in_blocks(char, codec.blocks):
        return char
    return None


def _codec_spans(text: str, codec: _Codec) -> list[_Span]:
    spans: list[_Span] = []
    i = 0
    while i < len(text):
        m = codec.pattern.match(text, i)
        char = _decode(m.group(), codec) if m else None
        if m is None or char is None:
            i += 1
            continue
        seq = m.group()
        weak = (
            _in_blocks(char, _EAST_ASIAN_BLOCKS)
            or (
                codec.name == "mac_roman"
                and len(seq) == 2
                and seq[0] in _MATH_LEADS
                and seq[1] in _MATH_CONTINUATIONS
            )
            or seq in _UNIT_PAIRS
        )
        if spans and spans[-1].end == m.start():
            last = spans[-1]
            last.end = m.end()
            last.repair += char
            last.weak = last.weak and weak
            last.sequences += 1
        else:
            spans.append(_Span(m.start(), m.end(), codec.name, char, weak))
        i = m.end()
    return spans


def _find_spans(text: str) -> list[_Span]:
    """Find runs of repairable UTF-8 sequences, one span per run and codec.

    Where codecs disagree about a stretch of text, the longer span wins.
    """
    candidates = [s for codec in _CODECS for s in _codec_spans(text, codec)]
    candidates.sort(key=lambda s: s.start - s.end)
    chosen: list[_Span] = []
    for s in candidates:
        if all(s.end <= c.start or c.end <= s.start for c in chosen):
            chosen.append(s)
    return sorted(chosen, key=lambda s: s.start)


def _keep_weak(span: _Span, text: str, has_strong_span: bool) -> bool:
    """Keep a weak span that has support from its field or its surroundings."""
    if has_strong_span or span.sequences > 1:
        return True
    before = text[span.start - 1] if span.start > 0 else ""
    after = text[span.end] if span.end < len(text) else ""
    return before.isalpha() and after.isalpha()


def _apply(text: str, spans: list[_Span]) -> str:
    out: list[str] = []
    pos = 0
    for s in spans:
        out.append(text[pos : s.start])
        out.append(s.repair)
        pos = s.end
    out.append(text[pos:])
    return "".join(out)


def _codec_label(span_text: str, codec: str) -> str:
    if codec != "cp1252":
        return codec
    # Only C1 control characters in the 0x80-0x9F range means Latin-1.
    upper = [ch for ch in span_text if 0x80 <= _CODECS[0].table[ch] <= 0x9F]
    if upper and all(0x80 <= ord(ch) <= 0x9F for ch in upper):
        return "latin-1"
    return "cp1252"


def _repair(text: str) -> tuple[list[dict[str, object]], str]:
    """Return the mojibake spans in ``text`` and the fully repaired text."""
    spans = _find_spans(text)
    strong = any(not s.weak for s in spans)
    spans = [s for s in spans if not s.weak or _keep_weak(s, text, strong)]
    results: list[dict[str, object]] = []
    for s in spans:
        layers = 1
        # Text decoded wrongly more than once repairs one layer at a time.
        while layers < _MAX_LAYERS:
            inner = _find_spans(s.repair)
            if not inner:
                break
            s.repair, layers = _apply(s.repair, inner), layers + 1
        span_text = text[s.start : s.end]
        results.append(
            {
                "text": span_text,
                "context": text[max(0, s.start - _CONTEXT) : s.end + _CONTEXT],
                "codec": _codec_label(span_text, s.codec),
                "layers": layers,
                "repair": s.repair,
                "start": s.start,
                "end": s.end,
            }
        )
    return results, _apply(text, spans)


def _describe(span: dict[str, object]) -> str:
    codec = _CODEC_NAMES[str(span["codec"])]
    layers = span["layers"]
    how = codec if layers == 1 else f"{codec}, decoded wrongly {layers} times"
    return f"{span['text']!r} should read {span['repair']!r} ({how}) in {span['context']!r}"


def _fields_to_check(record: Record, fields: FieldMap) -> list[tuple[str, int | None, str]]:
    out: list[tuple[str, int | None, str]] = []
    for role, name in (("question", fields.question), ("answer", fields.answer)):
        value = record.get(name)
        if isinstance(value, str):
            out.append((role, None, value))
    choices = record.get("choices")
    if isinstance(choices, list):
        for j, choice in enumerate(choices):
            if isinstance(choice, str):
                out.append(("choices", j, choice))
    return out


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    findings: list[Finding] = []
    for i, record in enumerate(records):
        for role, choice_index, text in _fields_to_check(record, fields):
            spans, repaired = _repair(text)
            if not spans:
                continue
            label = role if choice_index is None else f"choices[{choice_index}]"
            shown = "; ".join(_describe(s) for s in spans[:3])
            more = f"; and {len(spans) - 3} more" if len(spans) > 3 else ""
            severity: Severity = "low" if role == "question" else "medium"
            metadata: dict[str, object] = {"field": role}
            if choice_index is not None:
                metadata["choice_index"] = choice_index
            metadata |= {
                "codec": spans[0]["codec"],
                "spans": spans,
                "repaired": repaired,
            }
            findings.append(
                Finding(
                    scanner="mojibake",
                    severity=severity,
                    category="format",
                    explanation=(
                        f"The {label} contains UTF-8 text decoded with the wrong "
                        f"codec (mojibake): {shown}{more}."
                    ),
                    sample_index=i,
                    sample_id=get_sample_id(record, fields, i),
                    metadata=metadata,
                )
            )
    return findings


mojibake = ScannerDef(
    name="mojibake",
    fn=_scan,
    description=(
        "Flag UTF-8 text decoded with the wrong codec (Windows-1252, Latin-1 or "
        "Mac Roman) in questions, answers and choices, with the repaired text."
    ),
)
