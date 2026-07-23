"""Dataset discovery utilities for the explorer UI.

Provides:
- list_cached_hf_datasets()  — scan the local HuggingFace cache
- list_installed_tasks()     — discover @task-decorated callables from installed
  packages
- fetch_hf_schema()          — fetch field schema from HF dataset-viewer /info
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

HF_DATASETS_SERVER = "https://datasets-server.huggingface.co"


def _hf_request(path: str) -> dict[str, Any] | None:
    """Make a GET request to the HF dataset-viewer API.

    Returns the parsed JSON body, or None on any error.
    Respects HF_TOKEN if set in the environment.
    """
    try:
        import requests  # type: ignore[import-untyped]
    except ImportError:
        return None

    headers: dict[str, str] = {}
    token = os.environ.get("HF_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.get(
            f"{HF_DATASETS_SERVER}{path}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        return resp.json()  # type: ignore[no-any-return]
    except Exception as exc:
        logger.debug("HF API request failed for %s: %s", path, exc)
        return None


def _dtype_to_simple(dtype: str, type_tag: str) -> str:
    """Convert an HF dtype / _type pair to a simple label."""
    if type_tag == "Image":
        return "image"
    if type_tag in ("List", "Sequence"):
        return "list"
    if type_tag == "ClassLabel":
        return "int"
    if type_tag in ("Translation", "TranslationVariableLanguages"):
        return "dict"
    if dtype == "bool":
        return "bool"
    if dtype in ("int8", "int16", "int32", "int64", "uint8", "uint16", "uint32"):
        return "int"
    if dtype in ("float16", "float32", "float64"):
        return "float"
    return "str"


def _parse_hf_features(
    features: dict[str, Any],
) -> list[dict[str, Any]]:
    """Recursively flatten HF features dict into a list of SchemaField dicts."""
    result: list[dict[str, Any]] = []
    for name, spec in features.items():
        if not isinstance(spec, dict):
            continue
        type_tag: str = spec.get("_type", "")
        dtype: str = spec.get("dtype", "")
        simple = _dtype_to_simple(dtype, type_tag)
        entry: dict[str, Any] = {
            "name": name,
            "type": simple,
            "hf_type": type_tag or dtype,
            "null_count": 0,
            "total": 0,
        }
        result.append(entry)
    return result


def fetch_hf_schema(
    repo_id: str,
    config: str | None = None,
) -> list[dict[str, Any]] | None:
    """Return a list of SchemaField-compatible dicts from the HF /info endpoint.

    Returns None if the API is unavailable or the dataset is not found.
    """
    path = f"/info?dataset={repo_id}"
    if config:
        path += f"&config={config}"
    data = _hf_request(path)
    if data is None:
        return None

    dataset_info: dict[str, Any] = data.get("dataset_info", {})
    if not isinstance(dataset_info, dict) or not dataset_info:
        return None

    # When a config is requested the API returns that config's info dict
    # directly (with "features" at the top level); otherwise dataset_info is
    # keyed by config name, e.g. {"default": {..., "features": {...}}}.
    if isinstance(dataset_info.get("features"), dict):
        return _parse_hf_features(dataset_info["features"])

    # Prefer the requested config, then fall back to the first one with features.
    ordered = []
    if config and isinstance(dataset_info.get(config), dict):
        ordered.append(dataset_info[config])
    ordered.extend(v for v in dataset_info.values() if isinstance(v, dict))
    for info in ordered:
        features = info.get("features", {})
        if features:
            return _parse_hf_features(features)

    return None


def fetch_hf_configs(repo_id: str) -> list[str] | None:
    """Return available config/subset names from the HF /info endpoint.

    Returns None if the API is unavailable.
    """
    data = _hf_request(f"/info?dataset={repo_id}")
    if data is None:
        return None
    dataset_info: dict[str, Any] = data.get("dataset_info", {})
    if not dataset_info:
        return None
    return sorted(dataset_info.keys())


def fetch_hf_splits(
    repo_id: str,
    config: str | None = None,
) -> list[str] | None:
    """Return available split names from the HF /splits endpoint.

    Returns None if the API is unavailable.
    """
    path = f"/splits?dataset={repo_id}"
    if config:
        path += f"&config={config}"
    data = _hf_request(path)
    if data is None:
        return None
    splits_data = data.get("splits", [])
    return list({s["split"] for s in splits_data if isinstance(s, dict) and "split" in s})


def _scan_dataset_repos() -> list[Any]:
    """Scan the local HF cache and return dataset repos sorted by repo_id."""
    try:
        from huggingface_hub import scan_cache_dir
    except ImportError:
        return []

    try:
        info = scan_cache_dir()
    except Exception as exc:
        logger.warning("Could not scan HF cache: %s", exc)
        return []

    dataset_repos = [r for r in info.repos if r.repo_type == "dataset"]
    dataset_repos.sort(key=lambda r: r.repo_id)
    return dataset_repos


def _splits_for_repo(repo: Any) -> list[str]:
    """Return splits for a single repo, using API then fallback."""
    api_splits = fetch_hf_splits(repo.repo_id)
    if api_splits is not None:
        return sorted(api_splits) or ["train"]
    # Offline fallback: match whole path segments to avoid substring hits
    # on repos whose name contains a split word (e.g. "trainset/foo")
    known = ("train", "test", "validation", "dev")
    found: set[str] = set()
    for rev in repo.revisions:
        for f in rev.files:
            stem = f.file_name.lower()
            for split_name in known:
                if (
                    f"/{split_name}-" in stem
                    or f"/{split_name}." in stem
                    or stem.startswith((f"{split_name}-", f"{split_name}."))
                ):
                    found.add(split_name)
    return sorted(found) or ["train"]


def _configs_for_repo(repo: Any) -> list[str]:
    """Return config/subset names for a single repo, using API then fallback.

    Returns ``[]`` when a real config name can't be determined — callers
    then load with no ``name`` kwarg, preserving pre-config behaviour for
    single-config datasets (whose sole config may not be named "default").

    Offline fallback: HF lays multi-config datasets out as
    ``<config>/<split>-*.parquet``; single-config ones use a generic
    ``data/`` directory rather than a real config name, so that (and any
    directory holding no data files, e.g. ``images/``) is excluded.
    """
    api_configs = fetch_hf_configs(repo.repo_id)
    if api_configs is not None:
        return api_configs
    data_exts = (".parquet", ".json", ".jsonl", ".csv", ".arrow")
    found: set[str] = set()
    for rev in repo.revisions:
        for f in rev.files:
            parts = f.file_path.relative_to(rev.snapshot_path).parts
            if len(parts) > 1 and parts[0] != "data" and parts[-1].lower().endswith(data_exts):
                found.add(parts[0])
    return sorted(found)


# Splits/configs per repo, keyed by (repo_id, size_on_disk, last_modified) so
# entries invalidate when the cached snapshot changes. Metadata lookups hit
# the HF dataset-viewer API (or walk the snapshot's file tree), so caching
# them for the life of the server keeps repeat page loads instant.
_META_CACHE: dict[tuple[str, int, float | None], dict[str, list[str]]] = {}


def _meta_cache_key(repo: Any) -> tuple[str, int, float | None]:
    return (repo.repo_id, repo.size_on_disk, repo.last_modified)


def _meta_for_repo(repo: Any) -> dict[str, list[str]]:
    key = _meta_cache_key(repo)
    cached = _META_CACHE.get(key)
    if cached is None:
        cached = {"splits": _splits_for_repo(repo), "configs": _configs_for_repo(repo)}
        _META_CACHE[key] = cached
    return cached


def list_cached_hf_datasets_basic() -> list[dict[str, Any]]:
    """Return cached HF datasets from the local scan only — no network.

    Fast enough to serve immediately; splits/configs are omitted and can be
    filled in per dataset via cached_dataset_meta().
    """
    return [
        {
            "repo_id": repo.repo_id,
            "size_on_disk": repo.size_on_disk,
            "last_modified": repo.last_modified,
        }
        for repo in _scan_dataset_repos()
    ]


def cached_dataset_meta(repo_id: str) -> dict[str, list[str]] | None:
    """Return {"splits": [...], "configs": [...]} for one cached dataset.

    Results are memoised per snapshot. Returns None if the repo is not in
    the local cache.
    """
    for repo in _scan_dataset_repos():
        if repo.repo_id == repo_id:
            return _meta_for_repo(repo)
    return None


def list_cached_hf_datasets() -> list[dict[str, Any]]:
    """Return full metadata for all HuggingFace datasets in the local cache."""
    dataset_repos = _scan_dataset_repos()

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=16) as pool:
        meta_results = list(pool.map(_meta_for_repo, dataset_repos))

    result = [
        {
            "repo_id": repo.repo_id,
            "size_on_disk": repo.size_on_disk,
            "splits": meta["splits"],
            "configs": meta["configs"],
            "last_modified": repo.last_modified,
        }
        for repo, meta in zip(dataset_repos, meta_results, strict=True)
    ]
    return result


def list_installed_tasks() -> list[dict[str, Any]]:
    """Return all inspect_ai @task callables registered via installed packages."""
    try:
        from inspect_ai._util.entrypoints import ensure_entry_points
        from inspect_ai._util.registry import registry_find, registry_info
    except ImportError:
        return []

    try:
        ensure_entry_points()
        tasks = registry_find(lambda info: info.type == "task")
    except Exception as exc:
        logger.warning("Could not list inspect tasks: %s", exc)
        return []

    result = []
    for t in tasks:
        try:
            info = registry_info(t)
            name = info.name
            package = name.split("/")[0] if "/" in name else ""
            result.append({"name": name, "package": package})
        except Exception:
            continue

    return sorted(result, key=lambda x: x["name"])
