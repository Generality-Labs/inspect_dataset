from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from inspect_dataset._types import FieldMap, Record

# Common field name candidates for auto-detection, in priority order
_QUESTION_CANDIDATES = ["question", "prompt", "input", "text", "query", "instruction"]
_ANSWER_CANDIDATES = ["answer", "label", "target", "output", "response", "gold"]
_ID_CANDIDATES = ["id", "sample_id", "idx", "index", "qid"]


def auto_detect_fields(columns: list[str]) -> FieldMap:
    """Infer question/answer/id field names from column names."""

    def pick(candidates: list[str]) -> str | None:
        for c in candidates:
            if c in columns:
                return c
        # Case-insensitive fallback
        lower = {col.lower(): col for col in columns}
        for c in candidates:
            if c in lower:
                return lower[c]
        return None

    question = pick(_QUESTION_CANDIDATES)
    answer = pick(_ANSWER_CANDIDATES)

    if question is None or answer is None:
        raise ValueError(
            f"Could not auto-detect question/answer fields from columns: {columns}. "
            "Use --question-field and --answer-field to specify them explicitly."
        )

    return FieldMap(
        question=question,
        answer=answer,
        id=pick(_ID_CANDIDATES),
    )


def load_hf_dataset(
    path: str,
    split: str = "train",
    revision: str | None = None,
    limit: int | None = None,
) -> list[Record]:
    """Load a HuggingFace dataset into a list of plain dicts.

    Image fields (bytes dicts) and other non-serialisable types are preserved
    as-is — scanners that don't need them will simply ignore them.
    """
    try:
        from datasets import load_dataset
    except ImportError:
        raise ImportError(
            "The 'datasets' package is required to load HuggingFace datasets. "
            "Install it with: pip install datasets"
        )

    from datasets import Image as HFImage

    kwargs: dict[str, Any] = {"split": split}
    if revision:
        kwargs["revision"] = revision

    dataset = load_dataset(path, **kwargs)

    # Disable PIL decoding for image columns so they arrive as raw bytes dicts.
    # This avoids a Pillow dependency and keeps records JSON-serialisable.
    for col_name, feature in dataset.features.items():
        if isinstance(feature, HFImage):
            dataset = dataset.cast_column(col_name, HFImage(decode=False))

    if limit is not None:
        dataset = dataset.select(range(min(limit, len(dataset))))

    return [dict(row) for row in dataset]


def split_frontmatter(text: str) -> tuple[dict[str, str], str, int]:
    """Split YAML frontmatter from a markdown document.

    Returns ``(frontmatter, body, body_offset)`` where ``body_offset`` is the
    number of lines removed from the top of the file, so line numbers in the
    body can be mapped back to file line numbers.

    Only flat ``key: value`` frontmatter is parsed; anything else is kept as a
    raw string value.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text, 0
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm: dict[str, str] = {}
            for raw in lines[1:i]:
                key, sep, value = raw.partition(":")
                if sep:
                    fm[key.strip()] = value.strip()
            body_start = i + 1
            if body_start < len(lines) and lines[body_start].strip() == "":
                body_start += 1
            return fm, "".join(lines[body_start:]), body_start
    return {}, text, 0


def load_local_samples(
    path: str | Path, limit: int | None = None
) -> tuple[list[Record], FieldMap]:
    """Load a directory of JSON annotation files with markdown sidecars.

    Supports a common annotation layout for document benchmarks:
    each ``*.json`` file is one sample; a field ending in ``_markdown_path``
    points to a sidecar Markdown gold file (relative to the JSON file), whose
    YAML frontmatter is stripped into ``__frontmatter__``. The markdown body
    becomes the answer; ``__md_body_offset__`` records how many leading lines
    were stripped so scanner findings can report real file line numbers.

    Samples without a sidecar fall back to an embedded
    ``ground_truth_table.markdown`` string when present.
    """
    directory = Path(path)
    json_files = sorted(
        p for p in directory.glob("*.json") if p.name != "provenance.json"
    )
    records: list[Record] = []
    for json_path in json_files:
        try:
            data = json.loads(json_path.read_text())
        except json.JSONDecodeError as e:
            raise ValueError(f"{json_path} is not valid JSON: {e}") from e
        if not isinstance(data, dict):
            continue
        record: Record = dict(data)
        record["__json_path__"] = str(json_path)

        md_rel = next(
            (
                v
                for k, v in data.items()
                if k.endswith("_markdown_path") and isinstance(v, str)
            ),
            None,
        )
        answer = ""
        if md_rel is not None:
            md_path = json_path.parent / md_rel
            record["__markdown_path__"] = str(md_path)
            if md_path.exists():
                fm, body, offset = split_frontmatter(md_path.read_text())
                record["__frontmatter__"] = fm
                record["__md_body_offset__"] = offset
                answer = body
        else:
            table = data.get("ground_truth_table")
            if isinstance(table, dict) and isinstance(table.get("markdown"), str):
                answer = table["markdown"]
        record["gold_markdown"] = answer

        parts = [str(data[k]) for k in ("task_type", "element_type") if data.get(k)]
        source = data.get("pdf_path") or data.get("source")
        if source:
            page = data.get("page_number")
            parts.append(f"{source}#page={page}" if page is not None else str(source))
        record["__task__"] = " ".join(parts) or json_path.stem
        records.append(record)
        if limit is not None and len(records) >= limit:
            break

    if not records:
        raise ValueError(f"No JSON annotation files found in {directory}")
    id_field = "id" if all("id" in r for r in records) else None
    return records, FieldMap(question="__task__", answer="gold_markdown", id=id_field)


def _input_to_str(input: Any) -> str:
    """Extract question text from an inspect_ai Sample.input value.

    Handles both plain strings and list[ChatMessage] (Pydantic objects or dicts).
    For message lists, uses the content of the last user message.
    """
    if isinstance(input, str):
        return input
    if isinstance(input, list) and input:
        for msg in reversed(input):
            role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
            if role == "user":
                content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    # ContentBlock list — join text parts
                    return " ".join(
                        str(getattr(part, "text", "") or (part.get("text", "") if isinstance(part, dict) else ""))
                        for part in content
                        if (getattr(part, "type", None) or (part.get("type") if isinstance(part, dict) else None)) == "text"
                    )
        # Fallback: stringify first message content
        msg = input[0]
        content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
        return str(content) if content is not None else ""
    return str(input)


def _target_to_str(target: Any) -> str:
    """Extract answer text from an inspect_ai Sample.target value."""
    if isinstance(target, list):
        return target[0] if target else ""
    return str(target) if target is not None else ""


def load_inspect_task(task_or_fn: Any, limit: int | None = None) -> tuple[list[Record], FieldMap]:
    """Load records from an inspect_ai Task object or task function.

    Converts each ``inspect_ai.Sample`` to a plain ``Record`` dict using the
    fixed field mapping: ``input`` → question, ``target`` → answer, ``id`` → id.
    ``choices`` and ``metadata`` are preserved in the record for scanners that
    can use them. ``files`` is stored under ``__files__`` for future use by the
    view server.

    Returns a ``(records, fields)`` tuple — the ``FieldMap`` is pre-set so no
    auto-detection is needed.
    """
    task = task_or_fn() if callable(task_or_fn) else task_or_fn
    dataset = getattr(task, "dataset", None)
    if dataset is None:
        raise ValueError("Task has no dataset")

    records: list[Record] = []
    for sample in dataset:
        record: Record = {
            "input": _input_to_str(sample.input),
            "target": _target_to_str(sample.target),
            "id": sample.id,
        }
        if sample.choices:
            record["choices"] = sample.choices
        if sample.metadata:
            # Merge metadata into record so scanners can access it directly
            for k, v in sample.metadata.items():
                record.setdefault(k, v)
        if sample.files:
            record["__files__"] = sample.files
        records.append(record)
        if limit is not None and len(records) >= limit:
            break

    fields = FieldMap(question="input", answer="target", id="id")
    return records, fields


def _find_task_in_module(module: Any, hint: str) -> Any:
    """Find a single @task-decorated callable in a module.

    First tries an attribute named ``hint`` (the task name from the spec).
    If that is itself a module or non-callable, falls back to scanning for
    ``@task``-registered callables via the inspect_ai registry.

    Returns the callable, or raises ``ValueError`` with a helpful message.
    """
    candidate = getattr(module, hint, None)
    # Accept callables (task functions) and Task-like objects directly
    if candidate is not None and (callable(candidate) or hasattr(candidate, "dataset")):
        return candidate

    # hint resolved to a non-callable (e.g. a submodule) — scan for @task fns
    try:
        from inspect_ai._util.registry import is_registry_object, registry_info as _rinfo
        task_fns = [
            obj
            for name in dir(module)
            if not name.startswith("_")
            for obj in [getattr(module, name, None)]
            if obj is not None and callable(obj)
            and is_registry_object(obj)
            and _rinfo(obj).type == "task"
        ]
    except ImportError:
        task_fns = []

    if len(task_fns) == 1:
        return task_fns[0]
    if len(task_fns) > 1:
        names = ", ".join(
            getattr(fn, "__name__", str(fn)) for fn in task_fns
        )
        raise ValueError(
            f"Module {module.__name__!r} contains multiple tasks: {names}. "
            f"Specify one explicitly, e.g. {module.__name__}@<task_name>"
        )
    raise AttributeError(
        f"Module {module.__name__!r} has no @task-decorated callable named {hint!r} "
        f"and no unique @task callable was found."
    )


def load_task_from_spec(spec: str, limit: int | None = None) -> tuple[list[Record], FieldMap]:
    """Load records from a task spec string.

    Accepts the same spec formats as ``inspect eval``:

    - Package + task name:    ``inspect_evals/gpqa_diamond``  (mirrors inspect CLI)
    - Module + task name:     ``inspect_evals.gpqa@gpqa_diamond``
    - File + task name:       ``path/to/task.py@task_fn``     (via inspect_ai registry)

    For ``package/task_name`` specs, the module ``package.task_name`` is imported
    directly and the task function is located by name or by scanning for
    ``@task``-decorated callables. This works even when the inspect_ai entry-point
    loader cannot run (e.g. optional dependencies of the eval package are missing).

    For ``module@attr`` specs (left side contains ``.``), the attribute is imported
    directly from the module.

    For ``file@task`` specs (left side is an existing file path), this delegates to
    ``inspect_ai``'s loader.

    Raises ``ImportError`` if ``inspect_ai`` is not installed and the spec requires it.
    """
    has_at = "@" in spec

    if has_at:
        left, right = spec.rsplit("@", 1)
        left_path = Path(left)

        if not left_path.exists():
            # module@attr — import the module directly
            try:
                module = importlib.import_module(left)
            except ImportError as e:
                raise ImportError(f"Could not import module {left!r}: {e}") from e
            task_obj = _find_task_in_module(module, right)
            return load_inspect_task(task_obj, limit=limit)

        # file@task — delegate to inspect_ai
    else:
        # package/task_name — try direct module import first
        if "/" in spec:
            pkg, task_name = spec.split("/", 1)
            try:
                module = importlib.import_module(f"{pkg}.{task_name}")
                task_obj = _find_task_in_module(module, task_name)
                return load_inspect_task(task_obj, limit=limit)
            except (ImportError, AttributeError, ValueError):
                pass  # fall through to inspect_ai registry

    # Fall through: delegate to inspect_ai's registry / file loader
    try:
        from inspect_ai._eval.loader import load_task_spec as _inspect_load_task_spec
    except ImportError:
        raise ImportError(
            "inspect_ai is required to load tasks by spec. "
            "Install it with: pip install inspect-ai"
        )

    tasks = _inspect_load_task_spec(spec)
    if not tasks:
        raise ValueError(f"No tasks found for spec {spec!r}")
    if len(tasks) > 1:
        raise ValueError(
            f"Spec {spec!r} matched {len(tasks)} tasks; use a more specific spec "
            f"(e.g. include the task name after @)."
        )
    return load_inspect_task(tasks[0], limit=limit)


def resolve_fields(
    records: list[Record],
    question_field: str | None,
    answer_field: str | None,
    id_field: str | None,
    image_field: str | None = None,
) -> FieldMap:
    """Return a FieldMap from explicit overrides or auto-detection."""
    if not records:
        raise ValueError("Dataset is empty")

    columns = list(records[0].keys())

    if question_field is not None and answer_field is not None:
        return FieldMap(
            question=question_field,
            answer=answer_field,
            id=id_field,
            image=image_field,
        )

    detected = auto_detect_fields(columns)

    # Allow partial overrides
    return FieldMap(
        question=question_field or detected.question,
        answer=answer_field or detected.answer,
        id=id_field if id_field is not None else detected.id,
        image=image_field,
    )
