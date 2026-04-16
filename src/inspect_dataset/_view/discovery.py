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
    if dtype in ("bool",):
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
    if not dataset_info:
        return None

    # Pick the first config (or the matching one)
    for info in dataset_info.values():
        features = info.get("features", {})
        if features:
            return _parse_hf_features(features)

    return None


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
    return list(
        {s["split"] for s in splits_data if isinstance(s, dict) and "split" in s}
    )


def list_cached_hf_datasets() -> list[dict[str, Any]]:
    """Return metadata for all HuggingFace datasets in the local cache."""
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
                        or stem.startswith(f"{split_name}-")
                        or stem.startswith(f"{split_name}.")
                    ):
                        found.add(split_name)
        return sorted(found) or ["train"]

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=16) as pool:
        splits_results = list(pool.map(_splits_for_repo, dataset_repos))

    result = [
        {
            "repo_id": repo.repo_id,
            "size_on_disk": repo.size_on_disk,
            "splits": splits,
            "last_modified": repo.last_modified,
        }
        for repo, splits in zip(dataset_repos, splits_results)
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
