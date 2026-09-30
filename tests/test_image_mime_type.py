"""Tests for the image_mime_type scanner."""

import base64

import pytest

from inspect_dataset._types import FieldMap
from inspect_dataset.scanner import ScannerNotApplicable, run_scanners
from inspect_dataset.scanners.image_mime_type import (
    detect_mime_from_bytes,
    image_mime_type,
    mime_from_extension,
)

FIELDS = FieldMap(question="q", answer="a", image="img")
FIELDS_NO_IMAGE = FieldMap(question="q", answer="a")

# Minimal valid headers for various image formats
JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20
PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
WEBP_HEADER = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20
GIF_HEADER = b"GIF89a" + b"\x00" * 20
BMP_HEADER = b"BM" + b"\x00" * 20
TIFF_LE_HEADER = b"II\x2a\x00" + b"\x00" * 20
TIFF_BE_HEADER = b"MM\x00\x2a" + b"\x00" * 20


def _hf_image(raw_bytes: bytes, path: str) -> dict:
    """Simulate a HuggingFace Image(decode=False) dict."""
    return {"bytes": raw_bytes, "path": path}


# -- detect_mime_from_bytes --------------------------------------------------


def test_detect_jpeg():
    assert detect_mime_from_bytes(JPEG_HEADER) == "image/jpeg"


def test_detect_png():
    assert detect_mime_from_bytes(PNG_HEADER) == "image/png"


def test_detect_webp():
    assert detect_mime_from_bytes(WEBP_HEADER) == "image/webp"


def test_detect_gif():
    assert detect_mime_from_bytes(GIF_HEADER) == "image/gif"


def test_detect_bmp():
    assert detect_mime_from_bytes(BMP_HEADER) == "image/bmp"


def test_detect_tiff_le():
    assert detect_mime_from_bytes(TIFF_LE_HEADER) == "image/tiff"


def test_detect_tiff_be():
    assert detect_mime_from_bytes(TIFF_BE_HEADER) == "image/tiff"


def test_detect_unknown():
    assert detect_mime_from_bytes(b"\x00\x01\x02\x03" * 5) is None


# -- mime_from_extension -----------------------------------------------------


def test_ext_jpg():
    assert mime_from_extension("photo.jpg") == "image/jpeg"


def test_ext_jpeg():
    assert mime_from_extension("photo.jpeg") == "image/jpeg"


def test_ext_png():
    assert mime_from_extension("photo.png") == "image/png"


def test_ext_webp():
    assert mime_from_extension("photo.webp") == "image/webp"


def test_ext_unknown():
    assert mime_from_extension("data.xyz") is None


def test_ext_no_extension():
    assert mime_from_extension("noext") is None


# -- scanner integration: HuggingFace dict images ----------------------------


def test_matching_mime_no_finding():
    """JPEG bytes with .jpg path → no finding."""
    records = [{"q": "What?", "a": "Yes", "img": _hf_image(JPEG_HEADER, "photo.jpg")}]
    assert image_mime_type(records, FIELDS) == []


def test_mismatch_jpeg_declared_webp_actual():
    """The HLE bug: path says .jpeg but data is actually WebP."""
    records = [{"q": "What?", "a": "Yes", "img": _hf_image(WEBP_HEADER, "photo.jpeg")}]
    findings = image_mime_type(records, FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "image_mime_type"
    assert f.severity == "high"
    assert f.category == "format"
    assert f.metadata["declared_mime"] == "image/jpeg"
    assert f.metadata["actual_mime"] == "image/webp"
    assert f.sample_index == 0


def test_mismatch_png_declared_jpeg_actual():
    records = [{"q": "What?", "a": "Yes", "img": _hf_image(JPEG_HEADER, "photo.png")}]
    findings = image_mime_type(records, FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["declared_mime"] == "image/png"
    assert findings[0].metadata["actual_mime"] == "image/jpeg"


def test_no_image_field_not_applicable():
    records = [{"q": "What?", "a": "Yes"}]
    run = run_scanners(records, FIELDS_NO_IMAGE, [image_mime_type])
    assert run.findings == []
    assert run.scanner_status["image_mime_type"]["status"] == "not_applicable"


def test_direct_call_without_image_field_raises_not_applicable():
    with pytest.raises(ScannerNotApplicable, match="no image field"):
        image_mime_type([{"q": "What?", "a": "Yes"}], FIELDS_NO_IMAGE)


def test_none_image_skipped():
    records = [{"q": "What?", "a": "Yes", "img": None}]
    assert image_mime_type(records, FIELDS) == []


def test_too_short_bytes_skipped():
    records = [{"q": "What?", "a": "Yes", "img": _hf_image(b"\xff\xd8", "x.png")}]
    assert image_mime_type(records, FIELDS) == []


def test_unknown_actual_format_skipped():
    """If magic bytes don't match any known format, skip (no false positive)."""
    records = [{"q": "What?", "a": "Yes", "img": _hf_image(b"\x00" * 20, "photo.png")}]
    assert image_mime_type(records, FIELDS) == []


def test_multiple_records_mixed():
    """Two records: one matching, one mismatched → only one finding."""
    records = [
        {"q": "Q1", "a": "A1", "img": _hf_image(JPEG_HEADER, "a.jpg")},
        {"q": "Q2", "a": "A2", "img": _hf_image(PNG_HEADER, "b.jpeg")},
    ]
    findings = image_mime_type(records, FIELDS)
    assert len(findings) == 1
    assert findings[0].sample_index == 1
    assert findings[0].metadata["declared_mime"] == "image/jpeg"
    assert findings[0].metadata["actual_mime"] == "image/png"


# -- data URI images ---------------------------------------------------------


def test_data_uri_matching():
    uri = "data:image/png;base64," + base64.b64encode(PNG_HEADER).decode()
    records = [{"q": "What?", "a": "Yes", "img": uri}]
    assert image_mime_type(records, FIELDS) == []


def test_data_uri_mismatch():
    uri = "data:image/jpeg;base64," + base64.b64encode(PNG_HEADER).decode()
    records = [{"q": "What?", "a": "Yes", "img": uri}]
    findings = image_mime_type(records, FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["declared_mime"] == "image/jpeg"
    assert findings[0].metadata["actual_mime"] == "image/png"


# -- sample_id propagation --------------------------------------------------


def test_sample_id_from_id_field():
    fields = FieldMap(question="q", answer="a", image="img", id="sid")
    records = [
        {
            "q": "What?",
            "a": "Yes",
            "img": _hf_image(WEBP_HEADER, "x.jpg"),
            "sid": "hle_91e88c21",
        },
    ]
    findings = image_mime_type(records, fields)
    assert len(findings) == 1
    assert findings[0].sample_id == "hle_91e88c21"
