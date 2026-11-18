"""Read an eval's ignore file and apply it to a finished scan run.

The file is named ``.inspect-dataset.yaml``. Its one top-level key is ``ignore``, a list of
entries that each name a ``scanner`` and give the ``reason`` it is turned off for this eval:

    ignore:
      - scanner: duplicate_questions
        reason: Several questions share one passage by design.

An ignored scanner still runs. ``apply_ignores`` removes its findings from the run and records
the status ``ignored`` with the reason and the number of findings removed.
"""

from __future__ import annotations

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
