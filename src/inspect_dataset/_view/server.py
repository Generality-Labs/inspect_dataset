"""aiohttp backend for the interactive dataset explorer."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any, cast

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
    if ds.get("records_cache") is not None:
        return cast(list[dict[str, Any]], ds["records_cache"])

    summary = ds["summary"]
    source_type: str = summary.get("source_type", "")
    dataset_name: str = summary.get("dataset_name", "")
    split: str = summary.get("split") or "train"
    revision: str | None = summary.get("revision")
    config: str | None = summary.get("config")

    if not source_type or not dataset_name:
        return None

    try:
        if source_type == "hf":
            from inspect_dataset.loader import load_hf_dataset

            records = await asyncio.to_thread(
                load_hf_dataset, dataset_name, split=split, revision=revision, config=config
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
    return cast(dict[str, Any], datasets[slug])


def _infer_field_type(values: list[Any]) -> str:
    """Infer a human-readable type label from a sample of field values."""
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "null"
    v = non_null[0]
    if isinstance(v, dict) and "bytes" in v:
        return "image"
    if isinstance(v, dict):
        return "dict"
    if isinstance(v, list):
        return "list"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    return "str"


def _compute_schema(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return per-field schema information from a list of records."""
    if not records:
        return []
    columns = list(records[0].keys())
    schema = []
    n = len(records)
    for col in columns:
        if col.startswith("__"):
            continue
        values = [r.get(col) for r in records]
        null_count = sum(1 for v in values if v is None)
        field_type = _infer_field_type([v for v in values if v is not None][:5])

        entry: dict[str, Any] = {
            "name": col,
            "type": field_type,
            "null_count": null_count,
            "total": n,
        }

        if field_type == "str":
            lengths = [len(str(v)) for v in values if v is not None]
            if lengths:
                entry["min_length"] = min(lengths)
                entry["max_length"] = max(lengths)
                entry["avg_length"] = round(sum(lengths) / len(lengths), 1)
            entry["unique_count"] = len({str(v) for v in values if v is not None})
        elif field_type in ("int", "float"):
            nums = [v for v in values if v is not None]
            if nums:
                entry["min"] = min(nums)
                entry["max"] = max(nums)
                entry["mean"] = round(sum(nums) / len(nums), 4)

        schema.append(entry)
    return schema


def _record_to_json_safe(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a record to a JSON-serialisable dict.

    Image bytes dicts are replaced with a placeholder so the frontend
    knows an image is present without transmitting the raw bytes here.
    Use the dedicated /record/:idx endpoint to get actual image data.
    """
    result: dict[str, Any] = {}
    for key, val in record.items():
        if key.startswith("__"):
            continue
        if isinstance(val, dict) and isinstance(val.get("bytes"), bytes):
            result[key] = {"__type": "image", "path": val.get("path") or ""}
        elif isinstance(val, bytes):
            result[key] = {"__type": "bytes", "size": len(val)}
        else:
            try:
                json.dumps(val)
                result[key] = val
            except (TypeError, ValueError):
                result[key] = str(val)
    return result


def create_app(
    findings_dirs: list[str | Path] | str | Path | None = None,
) -> web.Application:
    """Create the aiohttp application for serving the explorer UI.

    Accepts one or more findings directories, or None to start in
    explorer-only mode (no pre-loaded datasets).
    A single string/Path is treated as a list of one.
    """
    if findings_dirs is None:
        findings_dirs = []
    elif isinstance(findings_dirs, str | Path):
        findings_dirs = [findings_dirs]

    datasets: dict[str, Any] = {}
    for d in findings_dirs:
        ds = _load_dataset_dir(Path(d).resolve())
        datasets[ds["slug"]] = ds

    app = web.Application()
    app["datasets"] = datasets
    app["explorer_sessions"] = {}  # session_id -> ExplorerSession dict

    # Dataset list (findings-mode)
    app.router.add_get("/api/datasets", handle_datasets)

    # Per-dataset endpoints — all namespaced under /api/{slug}/
    app.router.add_get("/api/{slug}/summary", handle_summary)
    app.router.add_get("/api/{slug}/samples", handle_samples)
    app.router.add_get("/api/{slug}/findings", handle_findings)
    app.router.add_get("/api/{slug}/triage", handle_get_triage)
    app.router.add_post("/api/{slug}/triage", handle_post_triage)
    app.router.add_get("/api/{slug}/export", handle_export)
    app.router.add_get("/api/{slug}/sample/{idx}", handle_sample)

    # Explorer discovery endpoints
    app.router.add_get("/api/discover/cached", handle_discover_cached)
    app.router.add_get("/api/discover/tasks", handle_discover_tasks)
    app.router.add_get("/api/discover/hf-schema", handle_discover_hf_schema)

    # Scanner listing + on-demand scanning of an explorer session
    app.router.add_get("/api/scanners", handle_list_scanners)
    app.router.add_post("/api/explore/{session_id}/scan", handle_explore_scan)

    # Explorer session endpoints
    app.router.add_post("/api/explore/load", handle_explore_load)
    app.router.add_get("/api/explore/{session_id}/schema", handle_explore_schema)
    app.router.add_get("/api/explore/{session_id}/records", handle_explore_records)
    app.router.add_get("/api/explore/{session_id}/record/{idx}", handle_explore_record)

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


# ---------------------------------------------------------------------------
# Discovery handlers
# ---------------------------------------------------------------------------


async def handle_discover_cached(request: web.Request) -> web.Response:
    """List all HuggingFace datasets in the local cache."""
    from inspect_dataset._view.discovery import list_cached_hf_datasets

    result = await asyncio.to_thread(list_cached_hf_datasets)
    return web.json_response(result)


async def handle_discover_tasks(request: web.Request) -> web.Response:
    """List all installed inspect_ai @task callables."""
    from inspect_dataset._view.discovery import list_installed_tasks

    result = await asyncio.to_thread(list_installed_tasks)
    return web.json_response(result)


async def handle_discover_hf_schema(request: web.Request) -> web.Response:
    """Fetch field schema for an HF dataset from the dataset-viewer API.

    Query params: dataset (required), config (optional)
    """
    repo_id = request.rel_url.query.get("dataset", "").strip()
    if not repo_id:
        return web.json_response({"error": "dataset is required"}, status=400)
    config = request.rel_url.query.get("config") or None

    from inspect_dataset._view.discovery import fetch_hf_schema

    schema = await asyncio.to_thread(fetch_hf_schema, repo_id, config)
    if schema is None:
        return web.json_response(
            {"error": "Schema not available from HF API"},
            status=404,
        )
    return web.json_response({"dataset": repo_id, "schema": schema})


# ---------------------------------------------------------------------------
# Explorer session handlers
# ---------------------------------------------------------------------------


async def handle_explore_load(request: web.Request) -> web.Response:
    """Load a dataset into a new explorer session.

    Request body::

        {
          "source": "cais/hle",          # HF slug or inspect task spec
          "source_type": "hf",           # "hf" | "inspect_task"
          "split": "test",               # optional, default "train"
          "limit": 500,                  # optional
          "config": "dimensions"         # optional HF config/subset name
        }

    Returns a session ID and basic metadata.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)

    source: str = body.get("source", "").strip()
    source_type: str = body.get("source_type", "hf")
    split: str = body.get("split", "train")
    limit: int | None = body.get("limit")
    config: str | None = body.get("config") or None

    if not source:
        return web.json_response({"error": "source is required"}, status=400)

    try:
        if source_type == "inspect_task":
            from inspect_dataset.loader import load_task_from_spec

            records, fields = await asyncio.to_thread(load_task_from_spec, source, limit)
        else:
            from inspect_dataset._types import FieldMap
            from inspect_dataset.loader import load_hf_dataset, resolve_fields

            records = await asyncio.to_thread(load_hf_dataset, source, split, None, limit, config)
            try:
                fields = resolve_fields(records, None, None, None, None)
            except Exception:
                fields = FieldMap(question="", answer="", id=None, image=None)
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=422)

    session_id = str(uuid.uuid4())

    # Prefer HF API schema (accurate types, no sampling needed) for HF datasets
    schema: list[dict[str, Any]] | None = None
    if source_type == "hf":
        from inspect_dataset._view.discovery import fetch_hf_schema

        try:
            schema = await asyncio.to_thread(fetch_hf_schema, source, config)
        except Exception as exc:
            logger.warning("Could not fetch HF schema for %s: %s", source, exc)

    if not schema:
        schema = _compute_schema(records)

    session: dict[str, Any] = {
        "session_id": session_id,
        "source": source,
        "source_type": source_type,
        "split": split,
        "config": config,
        "total": len(records),
        "records": records,
        "fields": fields,
        "schema": schema,
    }
    request.app["explorer_sessions"][session_id] = session

    return web.json_response(
        {
            "session_id": session_id,
            "source": source,
            "source_type": source_type,
            "split": split,
            "config": config,
            "total": len(records),
            "columns": [s["name"] for s in schema],
        }
    )


def _get_session(request: web.Request) -> dict[str, Any]:
    session_id = request.match_info["session_id"]
    sessions: dict[str, Any] = request.app["explorer_sessions"]
    if session_id not in sessions:
        raise web.HTTPNotFound(reason=f"Session '{session_id}' not found.")
    return cast(dict[str, Any], sessions[session_id])


async def handle_list_scanners(_request: web.Request) -> web.Response:
    """List available scanners with their descriptions and kind."""
    from inspect_dataset.scanners import BUILTIN_SCANNERS, LLM_SCANNER_FACTORIES

    scanners = [
        {"name": s.name, "description": s.description, "kind": "static"} for s in BUILTIN_SCANNERS
    ]
    scanners.extend(
        {"name": name, "description": "", "kind": "llm"} for name in sorted(LLM_SCANNER_FACTORIES)
    )
    return web.json_response(scanners)


async def handle_explore_scan(request: web.Request) -> web.Response:
    """Run selected scanners over an explorer session's records.

    Request body::

        {
          "scanners": ["answer_length", "duplicate_questions"],  # optional
          "model": "openai/gpt-4o-mini"                          # optional (LLM)
        }

    Omitting ``scanners`` runs all static scanners (plus LLM scanners when a
    ``model`` is given). Returns the findings with stable ids.
    """
    session = _get_session(request)
    try:
        body = await request.json()
    except Exception:
        body = {}

    requested: list[str] | None = body.get("scanners")
    model: str | None = body.get("model") or None

    from inspect_dataset.scanner import AnyScanner, run_scanners, run_scanners_async
    from inspect_dataset.scanners import BUILTIN_SCANNER_NAMES, LLM_SCANNER_FACTORIES

    names = requested or list(BUILTIN_SCANNER_NAMES)
    unknown = [
        n for n in names if n not in BUILTIN_SCANNER_NAMES and n not in LLM_SCANNER_FACTORIES
    ]
    if unknown:
        return web.json_response({"error": f"Unknown scanner(s): {', '.join(unknown)}"}, status=400)

    static: list[AnyScanner] = [
        BUILTIN_SCANNER_NAMES[n] for n in names if n in BUILTIN_SCANNER_NAMES
    ]
    llm_names = [n for n in names if n in LLM_SCANNER_FACTORIES]
    if llm_names and not model:
        return web.json_response(
            {"error": f"LLM scanner(s) ({', '.join(llm_names)}) require a model."},
            status=400,
        )

    records: list[dict[str, Any]] = session["records"]
    fields = session["fields"]

    try:
        if llm_names:
            llm = [LLM_SCANNER_FACTORIES[n](model) for n in llm_names]
            run = await run_scanners_async(records, fields, [*static, *llm])
        else:
            run = await asyncio.to_thread(run_scanners, records, fields, static)
    except Exception as exc:
        logger.warning("Scan failed for session %s: %s", session["session_id"], exc)
        return web.json_response({"error": str(exc)}, status=422)

    findings = [f.to_dict() for f in run.findings]
    for i, finding in enumerate(findings):
        finding["id"] = i
    return web.json_response(
        {
            "session_id": session["session_id"],
            "total_findings": len(findings),
            "findings": findings,
        }
    )


async def handle_explore_schema(request: web.Request) -> web.Response:
    """Return field schema + statistics for an explorer session."""
    session = _get_session(request)
    return web.json_response(
        {
            "session_id": session["session_id"],
            "source": session["source"],
            "total": session["total"],
            "schema": session["schema"],
        }
    )


async def handle_explore_records(request: web.Request) -> web.Response:
    """Return a paginated slice of records (JSON-safe, no raw bytes).

    Query params: offset (default 0), limit (default 100, max 500)
    """
    session = _get_session(request)
    try:
        offset = int(request.rel_url.query.get("offset", 0))
        limit = min(int(request.rel_url.query.get("limit", 100)), 500)
    except ValueError:
        return web.json_response({"error": "invalid offset/limit"}, status=400)

    records: list[dict[str, Any]] = session["records"]
    page = records[offset : offset + limit]
    rows = [{"__index": offset + i, **_record_to_json_safe(r)} for i, r in enumerate(page)]
    return web.json_response(
        {
            "session_id": session["session_id"],
            "offset": offset,
            "limit": limit,
            "total": session["total"],
            "rows": rows,
        }
    )


async def handle_explore_record(
    request: web.Request,
) -> web.Response:
    """Return one full record including images as data URLs."""
    session = _get_session(request)
    try:
        idx = int(request.match_info["idx"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid index"}, status=400)

    records: list[dict[str, Any]] = session["records"]
    if idx < 0 or idx >= len(records):
        return web.json_response({"error": "index out of range"}, status=404)

    record = records[idx]
    safe = _record_to_json_safe(record)

    images = []
    for key, val in record.items():
        if key.startswith("__"):
            continue
        if isinstance(val, dict) and isinstance(val.get("bytes"), bytes) and val["bytes"]:
            images.append(
                {
                    "field": key,
                    "data_url": _to_data_url(val["bytes"], val.get("path") or ""),
                }
            )

    files_map: dict[str, Any] = record.get("__files__") or {}
    files = []
    for name, data in files_map.items():
        if isinstance(data, bytes):
            files.append({"name": name, "data_url": _to_data_url(data, name)})
        elif isinstance(data, str):
            files.append({"name": name, "data_url": data})

    return web.json_response({"index": idx, "record": safe, "images": images, "files": files})


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------


def run_server(
    findings_dirs: list[str | Path] | str | Path | None = None,
    port: int = 7576,
) -> None:
    """Start the view server (blocking)."""
    app = create_app(findings_dirs)
    logger.info("Starting inspect-dataset viewer on http://localhost:%d", port)
    web.run_app(app, host="localhost", port=port, print=None)
