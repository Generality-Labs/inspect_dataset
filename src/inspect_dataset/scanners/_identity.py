"""What makes two records the same sample, for scanners that compare samples.

A sample is its question text, its answer choices and its images. Text is lowercased with
whitespace collapsed. Choices keep their order, because a letter answer names a position and a
model sees the choices in that order. Images are compared by content, so the same picture as a
file and as a data URI match. An image without bytes, such as a URL, is compared by its path.

The pieces are separate so that a scanner can group by text and choices first, then compare
images within a group.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import unquote_to_bytes

from inspect_dataset._types import FieldMap, Record
from inspect_dataset.scanners._answers import record_choices, resolve_choice

TextKey = tuple[str, tuple[str, ...] | None]
ImageKey = tuple[str, ...] | None


def normalise_text(value: Any) -> str:
    """Lowercased text with runs of whitespace collapsed to one space."""
    return " ".join(("" if value is None else str(value)).split()).lower()


def text_key(record: Record, fields: FieldMap) -> TextKey:
    """The normalised question and, when the record has a choices list, its normalised choices."""
    choices = record_choices(record, fields)
    return (
        normalise_text(record.get(fields.question)),
        None if choices is None else tuple(normalise_text(c) for c in choices),
    )


def image_hash(image: Any) -> str | None:
    """A content hash of one image, its path when it has no bytes, or None.

    Takes the shapes HuggingFace ``Image(decode=False)`` and task mode give: a
    ``{"bytes", "path"}`` dict, a data URI, a path or URL string, or raw bytes.
    """
    if isinstance(image, Mapping):
        raw = image.get("bytes")
        if raw:
            return _sha256(raw)
        path = image.get("path")
        return f"path:{path}" if path else None
    if isinstance(image, bytes | bytearray | memoryview):
        return _sha256(image) if image else None
    if isinstance(image, str) and image:
        raw = _data_uri_bytes(image) if image.startswith("data:") else None
        return _sha256(raw) if raw else f"path:{image}"
    return None


def image_key(record: Record, fields: FieldMap) -> ImageKey:
    """The hashes of the record's images in order, or None when it has none."""
    if fields.image is None:
        return None
    value = record.get(fields.image)
    images = value if isinstance(value, list | tuple) else [value]
    hashes = tuple(h for h in (image_hash(i) for i in images) if h is not None)
    return hashes or None


def sample_key(record: Record, fields: FieldMap) -> tuple[TextKey, ImageKey]:
    """Everything that identifies a sample: text, choices and images."""
    return text_key(record, fields), image_key(record, fields)


def answer_key(record: Record, fields: FieldMap) -> frozenset[str]:
    """The record's answers as a set of normalised strings, letters resolved to choice text.

    In task mode this is every target string when ``target`` is the answer field. Otherwise it
    is the answer field's value, or each element of a list answer.
    """
    targets = record.get("targets")
    if fields.scorers is not None and fields.answer == "target" and isinstance(targets, list):
        values: Sequence[Any] = targets
    else:
        answer = record.get(fields.answer)
        values = answer if isinstance(answer, list | tuple) else [answer]
    choices = record_choices(record, fields)
    return frozenset(normalise_text(_resolved(v, choices)) for v in values)


def _resolved(answer: Any, choices: Sequence[Any] | None) -> Any:
    text = resolve_choice(answer, choices) if choices is not None else None
    return answer if text is None else text


def _sha256(raw: bytes | bytearray | memoryview) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _data_uri_bytes(uri: str) -> bytes | None:
    header, sep, payload = uri.partition(",")
    if not sep:
        return None
    if header.lower().endswith(";base64"):
        try:
            return base64.b64decode(payload)
        except (binascii.Error, ValueError):
            return None
    return unquote_to_bytes(payload)
