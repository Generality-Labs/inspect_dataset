"""Scanner: detect mismatches between declared image MIME type and actual data.

HuggingFace image columns store images as ``{"bytes": <raw>, "path": "name.ext"}``.
The MIME type sent to model APIs is typically inferred from the ``path`` extension.
If the actual image data (identified via magic bytes) doesn't match the declared
extension, model APIs such as Anthropic will reject the request with HTTP 400.

This scanner reads the first bytes of each image to detect the real format and
compares it against the extension declared in the ``path`` field.
"""

from __future__ import annotations

import base64
from typing import Any

from inspect_dataset._types import FieldMap, Finding, Record
from inspect_dataset.scanner import ScannerDef, get_sample_id

# -- magic-byte signatures for common image formats -------------------------

_SIGNATURES: list[tuple[str, bytes, int | None, bytes | None]] = [
    # (mime_type, prefix, offset_for_extra_check, extra_bytes)
    ("image/png", b"\x89PNG\r\n\x1a\n", None, None),
    ("image/webp", b"RIFF", 8, b"WEBP"),
    ("image/gif", b"GIF8", None, None),
    ("image/bmp", b"BM", None, None),
    ("image/tiff", b"II\x2a\x00", None, None),
    ("image/tiff", b"MM\x00\x2a", None, None),
    # JPEG last — its 2-byte prefix is short; placing it after longer prefixes
    # avoids false positives.
    ("image/jpeg", b"\xff\xd8\xff", None, None),
]

# Extension → MIME type (lowercase, without leading dot)
_EXT_TO_MIME: dict[str, str] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "svg": "image/svg+xml",
    "ico": "image/x-icon",
    "heic": "image/heic",
    "heif": "image/heif",
    "avif": "image/avif",
}


def detect_mime_from_bytes(data: bytes) -> str | None:
    """Return the MIME type detected from the magic bytes, or None if unknown."""
    for mime, prefix, extra_offset, extra_bytes in _SIGNATURES:
        if data[: len(prefix)] == prefix:
            if (
                extra_offset is not None
                and extra_bytes is not None
                and data[extra_offset : extra_offset + len(extra_bytes)] != extra_bytes
            ):
                continue
            return mime
    return None


def mime_from_extension(path: str) -> str | None:
    """Derive MIME type from a file path/name extension."""
    dot = path.rfind(".")
    if dot == -1:
        return None
    ext = path[dot + 1 :].lower()
    return _EXT_TO_MIME.get(ext)


def _get_image_bytes(img: Any) -> bytes | None:
    """Extract raw bytes from various image representations."""
    if isinstance(img, bytes):
        return img
    if isinstance(img, str):
        # Might be a base64-encoded data URI or raw base64
        if img.startswith("data:"):
            # data:image/png;base64,<payload>
            parts = img.split(",", 1)
            if len(parts) == 2:
                try:
                    return base64.b64decode(parts[1])
                except Exception:
                    return None
        # Try raw base64
        try:
            return base64.b64decode(img)
        except Exception:
            return None
    if isinstance(img, dict):
        # HuggingFace Image(decode=False) → {"bytes": ..., "path": ...}
        raw = img.get("bytes")
        if isinstance(raw, bytes):
            return raw
        if isinstance(raw, str):
            try:
                return base64.b64decode(raw)
            except Exception:
                return None
    return None


def _get_declared_mime(img: Any) -> str | None:
    """Extract the declared MIME type from the image representation."""
    if isinstance(img, str) and img.startswith("data:"):
        # data:image/png;base64,<payload>
        header = img.split(",", 1)[0]  # "data:image/png;base64"
        mime_part = header.replace("data:", "").split(";")[0]
        return mime_part or None
    if isinstance(img, dict):
        path = img.get("path")
        if isinstance(path, str) and path:
            return mime_from_extension(path)
    return None


def _scan(records: list[Record], fields: FieldMap) -> list[Finding]:
    if fields.image is None:
        return []

    findings: list[Finding] = []
    for i, record in enumerate(records):
        img = record.get(fields.image)
        if img is None:
            continue

        raw = _get_image_bytes(img)
        if raw is None or len(raw) < 12:
            continue

        declared = _get_declared_mime(img)
        if declared is None:
            continue

        actual = detect_mime_from_bytes(raw)
        if actual is None:
            # Unknown format — can't verify
            continue

        if declared != actual:
            findings.append(
                Finding(
                    scanner="image_mime_type",
                    severity="high",
                    category="format",
                    explanation=(
                        f"Declared MIME type '{declared}' does not match actual "
                        f"image data which is '{actual}'. This will cause HTTP 400 "
                        f"errors with model APIs that validate MIME types "
                        f"(e.g. Anthropic)."
                    ),
                    sample_index=i,
                    sample_id=get_sample_id(record, fields, i),
                    metadata={
                        "declared_mime": declared,
                        "actual_mime": actual,
                    },
                )
            )
    return findings


image_mime_type = ScannerDef(
    name="image_mime_type",
    fn=_scan,
    description=(
        "Detect mismatches between declared image MIME type (from file extension "
        "or data URI header) and actual image data (from magic bytes). "
        "Such mismatches cause HTTP 400 errors with model APIs like Anthropic."
    ),
)
