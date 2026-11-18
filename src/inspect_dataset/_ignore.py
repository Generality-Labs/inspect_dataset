"""Read an eval's ignore file and apply it to a finished scan run.

The file is named ``.inspect-dataset.yaml``. Its one top-level key is ``ignore``, a list of
entries that each name a ``scanner`` and give the ``reason`` it is turned off for this eval:

    ignore:
      - scanner: duplicate_questions
        reason: Several questions share one passage by design.

An ignored scanner still runs. ``apply_ignores`` removes its findings from the run and records
the status ``ignored`` with the reason and the number of findings removed.

When a task is scanned, ``find_ignore_file`` looks for the file in the folder that holds the
task's source, and nowhere else.
"""

from __future__ import annotations

import importlib.util
import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from inspect_dataset._types import ScanRun

IGNORE_FILE_NAME = ".inspect-dataset.yaml"

_ENTRY_KEYS = ("scanner", "reason")


class IgnoreFileError(ValueError):
    """The ignore file could not be parsed or does not follow the expected layout."""


def load_ignore_file(path: Path) -> dict[str, str]:
    """Read an ignore file and return a mapping from scanner name to reason.

    An empty file, or a mapping without ``ignore``, gives an empty mapping.

    Raises:
        IgnoreFileError: If the file is not valid YAML or does not follow the expected layout.
            The message names the position of the entry at fault, such as ``ignore[1]``.
    """
    try:
        data: Any = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise IgnoreFileError(f"the file is not valid YAML: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise IgnoreFileError("the top level must be a mapping with the key 'ignore'")
    unknown = sorted(str(k) for k in data if k != "ignore")
    if unknown:
        raise IgnoreFileError(
            f"unknown top-level key {unknown[0]!r}; the only top-level key is 'ignore'"
        )
    entries = data.get("ignore")
    if entries is None:
        return {}
    if not isinstance(entries, list):
        raise IgnoreFileError("ignore must be a list of entries with 'scanner' and 'reason'")
    ignores: dict[str, str] = {}
    for i, entry in enumerate(entries):
        where = f"ignore[{i}]"
        if not isinstance(entry, dict):
            raise IgnoreFileError(
                f"{where}: an entry must be a mapping with 'scanner' and 'reason'"
            )
        extra = sorted(str(k) for k in entry if k not in _ENTRY_KEYS)
        if extra:
            raise IgnoreFileError(
                f"{where}: unknown key {extra[0]!r}; an entry has only 'scanner' and 'reason'"
            )
        values: dict[str, str] = {}
        for key in _ENTRY_KEYS:
            value = entry.get(key)
            if value is None:
                raise IgnoreFileError(f"{where}: {key} is required")
            if not isinstance(value, str):
                raise IgnoreFileError(f"{where}: {key} must be a string")
            if not value.strip():
                raise IgnoreFileError(f"{where}: {key} must not be blank")
            values[key] = value.strip()
        scanner = values["scanner"]
        if scanner in ignores:
            raise IgnoreFileError(f"{where}: scanner {scanner!r} is listed more than once")
        ignores[scanner] = values["reason"]
    return ignores


def apply_ignores(run: ScanRun, ignores: Mapping[str, str]) -> None:
    """Remove the findings of each ignored scanner that ran, and record it as ignored.

    A scanner whose status is not ``ran``, or that has no status in the run, is left alone.
    """
    for scanner, reason in ignores.items():
        status = run.scanner_status.get(scanner)
        if status is None or status.get("status") != "ran":
            continue
        kept = [f for f in run.findings if f.scanner != scanner]
        removed = len(run.findings) - len(kept)
        run.findings = kept
        run.scanner_status[scanner] = {"status": "ignored", "reason": reason, "findings": removed}


def task_source_dir(task_spec: str) -> Path | None:
    """Return the folder that holds the source of the task named by ``task_spec``.

    The rules are tried in this order:

    - ``path/to/task.py@name``, where the left side is an existing file: that file's folder.
    - ``package.module@name``: the folder of that module's file.
    - ``package/name``, where the module ``package.name`` exists: the folder of that module's
      file. For a package this is the package's own folder.
    - Otherwise, a task that the inspect_ai registry finds under ``task_spec``: the folder of
      the file that defines the task function. ``inspect_evals/mmlu_0_shot`` gives the folder
      of ``inspect_evals/mmlu/mmlu.py``.

    Returns:
        The folder, or ``None`` when no rule applies, when an import or a lookup raises, or
        when inspect_ai is not installed.
    """
    try:
        return _task_source_dir(task_spec)
    except Exception:
        # Importing a module runs its code, which can raise any exception.
        return None


def find_ignore_file(task_spec: str) -> Path | None:
    """Return the ignore file in the folder that holds the task's source, if there is one.

    Only that folder is checked. Parent folders and the current directory are not searched.
    """
    source_dir = task_source_dir(task_spec)
    if source_dir is None:
        return None
    path = source_dir / IGNORE_FILE_NAME
    return path if path.is_file() else None


def _task_source_dir(task_spec: str) -> Path | None:
    if "@" in task_spec:
        left = task_spec.rsplit("@", 1)[0]
        if Path(left).is_file():
            return Path(left).parent
        return _module_dir(left)
    if "/" in task_spec:
        package, name = task_spec.split("/", 1)
        module_dir = _module_dir(f"{package}.{name}")
        if module_dir is not None:
            return module_dir
    return _registry_task_dir(task_spec)


def _module_dir(module: str) -> Path | None:
    spec = importlib.util.find_spec(module)
    # A built-in or frozen module has no file, and its origin is not a path.
    if spec is None or not spec.has_location or spec.origin is None:
        return None
    return Path(spec.origin).parent


def _registry_task_dir(task_spec: str) -> Path | None:
    try:
        from inspect_ai._util.registry import registry_lookup
    except ImportError:
        return None
    task = registry_lookup("task", task_spec)
    if not callable(task):
        return None
    source = inspect.getsourcefile(inspect.unwrap(task))
    return None if source is None else Path(source).parent
