"""aiohttp backend for the interactive dataset explorer."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "www" / "dist"


class _WWWResource(web.StaticResource):
    """SPA-aware static resource (mirrors inspect_ai pattern).

    Serves /index.html for any path that doesn't match an existing
    static file, and disables caching so we never serve stale assets.
    """

    def __init__(self) -> None:
        super().__init__(
            "",
            os.path.abspath((Path(__file__).parent / "www" / "dist").as_posix()),
        )

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        filename = request.match_info["filename"]
        if not filename:
            request.match_info["filename"] = "index.html"
        else:
            candidate = STATIC_DIR / filename
            if not candidate.exists() and "." not in Path(filename).name:
                request.match_info["filename"] = "index.html"

        response = await super()._handle(request)

        # Disable caching — only served locally
        response.headers.update(
            {
                "Expires": "Fri, 01 Jan 1990 00:00:00 GMT",
                "Pragma": "no-cache",
                "Cache-Control": ("no-cache, no-store, max-age=0, must-revalidate"),
            }
        )
        return response


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def _detect_mime(data: bytes) -> str:
    """Sniff MIME type from magic bytes. Falls back to image/jpeg."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:3] == b"GIF":
        return "image/gif"
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _to_data_url(data: bytes, path: str = "") -> str:
    """Encode bytes as a base64 data URL, guessing MIME from path or magic bytes."""
    mime: str | None = None
    if path:
        mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = _detect_mime(data)
    encoded = base64.b64encode(data).decode()
    return f"data:{mime};base64,{encoded}"


def _make_slug(dataset_name: str) -> str:
    """flaviagiammarino/vqa-rad -> flaviagiammarino--vqa-rad"""
    return dataset_name.replace("/", "--")


def _load_dataset_dir(path: Path) -> dict[str, Any]:
    """Load a single findings directory into a dataset state dict."""
    summary_file = path / "scan_summary.json"
    if not summary_file.exists():
        raise FileNotFoundError(
            f"No scan_summary.json in {path}. Run `inspect-dataset scan ... -o <dir>` first."
        )

    summary = _load_json(summary_file)

    # Load all scanner findings files (one per scanner, e.g. answer_length.json)
    skip = {"scan_summary.json", "triage.json", "samples.json"}
    all_findings: list[dict[str, Any]] = []
    for f in sorted(path.glob("*.json")):
        if f.name in skip:
            continue
        all_findings.extend(_load_json(f))

    # Assign stable IDs to findings if not present
    for i, finding in enumerate(all_findings):
        finding.setdefault("id", i)

    triage_file = path / "triage.json"
    triage: dict[str, str] = {}
    if triage_file.exists():
        triage = _load_json(triage_file)

    samples_file = path / "samples.json"
    samples: list[dict[str, Any]] = []
    if samples_file.exists():
        samples = _load_json(samples_file)

    slug = _make_slug(summary.get("dataset_name", path.name))

    return {
        "slug": slug,
        "path": path,
        "summary": summary,
        "findings": all_findings,
        "samples": samples,
        "triage": triage,
        "triage_file": triage_file,
        "records_cache": None,
    }


async def _load_records_cached(ds: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Lazy-load the original dataset records and cache them in the dataset dict.

    Returns None (without raising) if the dataset cannot be loaded —
    callers fall back to samples.json data without images.
    """
    cached: list[dict[str, Any]] | None = ds.get("records_cache")
    if cached is not None:
        return cached

    summary = ds["summary"]
    source_type: str = summary.get("source_type", "")
    dataset_name: str = summary.get("dataset_name", "")
    split: str = summary.get("split") or "train"
    revision: str | None = summary.get("revision")

    if not source_type or not dataset_name:
        return None

    try:
        if source_type == "hf":
            from inspect_dataset.loader import load_hf_dataset

            records = await asyncio.to_thread(
                load_hf_dataset, dataset_name, split=split, revision=revision
            )
        elif source_type == "inspect_task":
            from inspect_dataset.loader import load_task_from_spec

            records, _ = await asyncio.to_thread(load_task_from_spec, dataset_name)
        elif source_type == "local":
            from inspect_dataset.loader import load_local_samples

            records, fields = await asyncio.to_thread(load_local_samples, dataset_name)
            files_root = summary.get("files_root")
            if files_root:
                from inspect_dataset.scanner import get_sample_id

                root = Path(files_root)
                for idx, record in enumerate(records):
                    sample_dir = root / str(get_sample_id(record, fields, idx))
                    if sample_dir.is_dir():
                        record["__artifacts_dir__"] = str(sample_dir)
        else:
            return None

        ds["records_cache"] = records
        return records
    except Exception as exc:
        logger.warning("Could not load dataset for image serving: %s", exc)
        return None


def _get_dataset(request: web.Request) -> dict[str, Any]:
    """Look up a dataset dict by slug from the URL, raising 404 if not found."""
    slug = request.match_info["slug"]
    datasets: dict[str, Any] = request.app["datasets"]
    if slug not in datasets:
        raise web.HTTPNotFound(reason=f"Dataset '{slug}' not found.")
    ds: dict[str, Any] = datasets[slug]
    return ds


def create_app(
    findings_dirs: list[str | Path] | str | Path,
) -> web.Application:
    """Create the aiohttp application for serving the explorer UI.

    Accepts one or more findings directories.  A single string/Path is treated
    as a list of one.
    """
    if isinstance(findings_dirs, (str, Path)):
        findings_dirs = [findings_dirs]

    datasets: dict[str, Any] = {}
    for d in findings_dirs:
        ds = _load_dataset_dir(Path(d).resolve())
        datasets[ds["slug"]] = ds

    if not datasets:
        raise FileNotFoundError("No valid findings directories found.")

    app = web.Application()
    app["datasets"] = datasets

    # Dataset list
    app.router.add_get("/api/datasets", handle_datasets)

    # Per-dataset endpoints — all namespaced under /api/{slug}/
    app.router.add_get("/api/{slug}/summary", handle_summary)
    app.router.add_get("/api/{slug}/samples", handle_samples)
    app.router.add_get("/api/{slug}/findings", handle_findings)
    app.router.add_get("/api/{slug}/triage", handle_get_triage)
    app.router.add_post("/api/{slug}/triage", handle_post_triage)
    app.router.add_get("/api/{slug}/export", handle_export)
    app.router.add_get("/api/{slug}/sample/{idx}", handle_sample)

    # Serve the SPA via WWWResource (mirrors inspect_ai pattern)
    if STATIC_DIR.exists():
        app.router.register_resource(_WWWResource())
    else:

        async def _not_built(_: web.Request) -> web.Response:
            return web.Response(
                text="Frontend not built. Run `npm run build` in _view/www/",
                content_type="text/plain",
            )

        app.router.add_get("/", _not_built)

    return app


async def handle_datasets(request: web.Request) -> web.Response:
    """List all loaded datasets with summary counts."""
    datasets: dict[str, Any] = request.app["datasets"]
    result = []
    for slug, ds in datasets.items():
        summary = ds["summary"]
        result.append(
            {
                "slug": slug,
                "dataset_name": summary.get("dataset_name", slug),
                "split": summary.get("split"),
                "total_samples": summary.get("total_samples", 0),
                "total_findings": len(ds["findings"]),
                "by_severity": summary.get("by_severity", {}),
            }
        )
    return web.json_response(result)


async def handle_summary(request: web.Request) -> web.Response:
    ds = _get_dataset(request)
    return web.json_response(ds["summary"])


async def handle_samples(request: web.Request) -> web.Response:
    ds = _get_dataset(request)
    return web.json_response(ds["samples"])


async def handle_findings(request: web.Request) -> web.Response:
    ds = _get_dataset(request)
    findings = ds["findings"]
    triage = ds["triage"]

    # Enrich findings with triage status
    enriched = []
    for f in findings:
        entry = dict(f)
        entry["triage_status"] = triage.get(str(f["id"]), "pending")
        enriched.append(entry)

    return web.json_response(enriched)


async def handle_get_triage(request: web.Request) -> web.Response:
    ds = _get_dataset(request)
    return web.json_response(ds["triage"])


async def handle_post_triage(request: web.Request) -> web.Response:
    ds = _get_dataset(request)
    body = await request.json()
    finding_id = str(body.get("finding_id", ""))
    status = body.get("status", "")

    if status not in ("confirmed", "dismissed", "pending"):
        return web.json_response(
            {"error": "status must be confirmed, dismissed, or pending"},
            status=400,
        )

    triage = ds["triage"]
    if status == "pending":
        triage.pop(finding_id, None)
    else:
        triage[finding_id] = status

    _save_json(ds["triage_file"], triage)
    return web.json_response({"ok": True})


async def handle_export(request: web.Request) -> web.Response:
    """Export sample IDs that have no confirmed findings."""
    ds = _get_dataset(request)
    findings = ds["findings"]
    triage = ds["triage"]

    # Collect sample indices with confirmed findings
    confirmed_indices: set[int] = set()
    for f in findings:
        fid = str(f["id"])
        if triage.get(fid) == "confirmed":
            idx = f.get("sample_index")
            if idx is not None:
                confirmed_indices.add(idx)

    # Get total samples from summary
    total = ds["summary"].get("total_samples", 0)
    clean_ids = sorted(set(range(total)) - confirmed_indices)

    text = "\n".join(str(i) for i in clean_ids) + "\n"
    return web.Response(
        text=text,
        content_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=clean_ids.txt"},
    )


async def handle_sample(request: web.Request) -> web.Response:
    """Return full sample data for one record, including images as data URLs."""
    ds = _get_dataset(request)
    try:
        idx = int(request.match_info["idx"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid index"}, status=400)

    # Base data from pre-serialised samples.json (always available)
    samples: list[dict[str, Any]] = ds["samples"]
    basic = next((s for s in samples if s["index"] == idx), None)
    result: dict[str, Any] = {
        "index": idx,
        "question": basic["question"] if basic else "",
        "answer": basic["answer"] if basic else "",
        "id": basic.get("id") if basic else None,
        "images": [],
        "files": [],
    }

    # Attempt to enrich with image bytes from the original dataset
    records = await _load_records_cached(ds)
    if records is not None and 0 <= idx < len(records):
        record = records[idx]

        # HF image fields arrive as {"bytes": b"...", "path": "..."}
        for key, val in record.items():
            if key.startswith("__"):
                continue
            if isinstance(val, dict) and isinstance(val.get("bytes"), bytes) and val["bytes"]:
                result["images"].append(
                    {
                        "field": key,
                        "data_url": _to_data_url(val["bytes"], val.get("path") or ""),
                    }
                )

        # Extraction-cache artifacts (local annotation datasets): page image,
        # per-tool text outputs, and the markdown body's line offset so the
        # frontend can anchor file-based finding lines.
        artifacts_dir = record.get("__artifacts_dir__")
        if artifacts_dir:
            adir = Path(str(artifacts_dir))
            page_png = adir / "page.png"
            if page_png.exists():
                result["images"].append(
                    {"field": "page", "data_url": _to_data_url(page_png.read_bytes(), "page.png")}
                )
            from inspect_dataset.scanners._artifacts import tool_texts

            result["tool_outputs"] = [
                {"name": name, "text": text} for name, text in tool_texts(record).items()
            ]
        offset = record.get("__md_body_offset__")
        if isinstance(offset, int):
            result["line_offset"] = offset

        # inspect_ai Sample.files stored under __files__
        files_map: dict[str, Any] = record.get("__files__") or {}
        for name, data in files_map.items():
            if isinstance(data, bytes):
                result["files"].append(
                    {
                        "name": name,
                        "data_url": _to_data_url(data, name),
                    }
                )
            elif isinstance(data, str):
                result["files"].append({"name": name, "data_url": data})

    return web.json_response(result)


def run_server(
    findings_dirs: list[str | Path] | str | Path,
    port: int = 7576,
) -> None:
    """Start the view server (blocking)."""
    app = create_app(findings_dirs)
    logger.info("Starting inspect-dataset viewer on http://localhost:%d", port)
    web.run_app(app, host="localhost", port=port, print=None)
