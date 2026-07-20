from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console

from inspect_dataset.loader import (
    load_hf_dataset,
    load_local_samples,
    load_task_from_spec,
    resolve_fields,
)
from inspect_dataset.report import print_report, save_findings
from inspect_dataset.scanner import (
    AnyScanner,
    ScannerDef,
    run_scanners,
    run_scanners_async,
)
from inspect_dataset.scanners import (
    ALL_SCANNER_NAMES,
    BUILTIN_SCANNER_NAMES,
    BUILTIN_SCANNERS,
    LLM_SCANNER_FACTORIES,
)


def _load_scanner_module(module_name: str) -> list[ScannerDef]:
    """Import a module and collect its ScannerDef objects.

    A module-level ``SCANNERS`` list takes precedence; otherwise every public
    attribute that is a ``ScannerDef`` is collected.
    """
    import importlib

    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise click.BadParameter(
            f"Could not import scanner module {module_name!r}: {e}",
            param_hint="--scanner-module",
        ) from e

    declared = getattr(module, "SCANNERS", None)
    if declared is not None:
        defs = [s for s in declared if isinstance(s, ScannerDef)]
    else:
        defs = [
            obj
            for name in dir(module)
            if not name.startswith("_")
            for obj in [getattr(module, name)]
            if isinstance(obj, ScannerDef)
        ]
    if not defs:
        raise click.BadParameter(
            f"No ScannerDef objects found in module {module_name!r}",
            param_hint="--scanner-module",
        )
    return defs


@click.group()
def cli() -> None:
    """inspect-dataset — dataset quality scanner for AI evaluation benchmarks."""
    # Load .env files (cwd first, then home), mirroring inspect_ai behaviour.
    # Existing env vars take precedence.
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    load_dotenv(dotenv_path=Path.home() / ".env", override=False)


@cli.command()
@click.argument("dataset")
@click.option("--split", default="train", show_default=True, help="Dataset split to load.")
@click.option("--revision", default=None, help="Dataset revision / commit SHA to pin.")
@click.option(
    "--question-field",
    default=None,
    help="Column name for questions (auto-detected if omitted).",
)
@click.option(
    "--answer-field",
    default=None,
    help="Column name for answers (auto-detected if omitted).",
)
@click.option(
    "--id-field",
    default=None,
    help="Column name for sample IDs (auto-detected if omitted).",
)
@click.option(
    "--image-field",
    default=None,
    help=(
        "Column name for images. Used by duplicate_questions to distinguish "
        "same-question/different-image pairs from true duplicates."
    ),
)
@click.option(
    "--scanners",
    default=None,
    help=(
        "Comma-separated list of scanners to run. "
        f"Available: {', '.join(sorted(ALL_SCANNER_NAMES))}. "
        "Defaults to all static scanners (LLM scanners require --model)."
    ),
)
@click.option(
    "--scanner-module",
    "scanner_modules",
    multiple=True,
    help=(
        "Python module providing extra scanners (a module-level SCANNERS list, "
        "or any ScannerDef attributes). Repeatable."
    ),
)
@click.option(
    "--model",
    default=None,
    envvar="INSPECT_DATASET_MODEL",
    help=(
        "LLM model for AI-powered scanners "
        "(e.g. openai/gpt-4o-mini). Enables: "
        "ambiguity, label_correctness, answerability. "
        "[env: INSPECT_DATASET_MODEL]"
    ),
)
@click.option(
    "--max-answer-words",
    default=4,
    show_default=True,
    help="Threshold for the answer_length scanner.",
)
@click.option(
    "--files-root",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help=(
        "Directory of per-sample extraction artifacts (<files-root>/<sample_id>/ "
        "with tool text outputs). Enables the cross-artifact scanners "
        "text_layer_recall and numeric_provenance."
    ),
)
@click.option("--limit", default=None, type=int, help="Cap number of samples loaded.")
@click.option(
    "-o",
    "--output-dir",
    default=None,
    type=click.Path(),
    help=(
        "Save findings JSON + REPORT.md to this directory "
        "(default: findings/<dataset>_<YYYY-MM-DDTHH-MM-SS>)."
    ),
)
def scan(
    dataset: str,
    split: str,
    revision: str | None,
    question_field: str | None,
    answer_field: str | None,
    id_field: str | None,
    image_field: str | None,
    scanners: str | None,
    scanner_modules: tuple[str, ...],
    model: str | None,
    max_answer_words: int,
    files_root: str | None,
    limit: int | None,
    output_dir: str | None,
) -> None:
    r"""Scan a dataset for quality issues.

    DATASET is one of:

    \b
      - A HuggingFace dataset path:    flaviagiammarino/vqa-rad
      - An inspect_ai registry name:   inspect_evals/medqa
      - A file + task name:            path/to/task.py@task_fn
      - A module + task name:          inspect_evals.medqa@medqa
      - A local annotation directory:  path/to/data/samples/
    """
    console = Console()

    # Plugin scanners from --scanner-module
    plugin_scanners: list[ScannerDef] = []
    for module_name in scanner_modules:
        plugin_scanners.extend(_load_scanner_module(module_name))
    plugin_by_name = {s.name: s for s in plugin_scanners}
    available_names = ALL_SCANNER_NAMES | set(plugin_by_name)

    # Resolve scanners
    scanner_list: list[AnyScanner]
    if scanners:
        names = [n.strip() for n in scanners.split(",")]
        unknown = [n for n in names if n not in available_names]
        if unknown:
            raise click.BadParameter(
                f"Unknown scanner(s): {', '.join(unknown)}. "
                f"Available: {', '.join(sorted(available_names))}",
                param_hint="--scanners",
            )
        static_names = [n for n in names if n in BUILTIN_SCANNER_NAMES or n in plugin_by_name]
        llm_names = [n for n in names if n in LLM_SCANNER_FACTORIES]
        scanner_list = [BUILTIN_SCANNER_NAMES.get(n) or plugin_by_name[n] for n in static_names]
    else:
        scanner_list = [*BUILTIN_SCANNERS, *plugin_scanners]
        llm_names = list(LLM_SCANNER_FACTORIES) if model else []

    # Instantiate LLM scanners if --model provided
    llm_scanners = []
    if model:
        if not llm_names:
            llm_names = list(LLM_SCANNER_FACTORIES)
        for name in llm_names:
            llm_scanners.append(LLM_SCANNER_FACTORIES[name](model))
    elif llm_names and scanners:
        # User asked for LLM scanners without --model
        raise click.UsageError(
            f"LLM scanner(s) ({', '.join(llm_names)}) require "
            f"--model. Example: --model openai/gpt-4o-mini"
        )

    # Apply per-scanner options
    if max_answer_words != 4:
        from inspect_dataset.scanners.answer_length import _make_scanner

        scanner_list = [
            _make_scanner(max_answer_words) if s.name == "answer_length" else s
            for s in scanner_list
        ]

    # Detect the source type.
    # - An existing directory → local annotation directory
    # - "@" present → always a task spec (module@fn or file@fn)
    # - "package/task" with no "@" → task if "package" is an installed Python
    #   package (importlib.util.find_spec returns non-None); HF slugs like
    #   "owner/dataset" have no corresponding Python package.
    import importlib.util as _ilu

    is_local = Path(dataset).is_dir()
    is_task = not is_local and (
        "@" in dataset or ("/" in dataset and _ilu.find_spec(dataset.split("/")[0]) is not None)
    )
    resolved_split: str | None = split

    if is_local:
        dataset = str(Path(dataset).resolve())
        console.print(f"Loading local samples from [bold]{dataset}[/bold]...")
        records, fields = load_local_samples(dataset, limit=limit)
        resolved_split = None
        if question_field or answer_field or id_field:
            fields = resolve_fields(records, question_field, answer_field, id_field, image_field)
    elif is_task:
        console.print(f"Loading inspect_ai task [bold]{dataset}[/bold]...")
        records, fields = load_task_from_spec(dataset, limit=limit)
        # Allow field overrides even on the task path
        if question_field or answer_field or id_field:
            fields = resolve_fields(records, question_field, answer_field, id_field, image_field)
    else:
        console.print(f"Loading [bold]{dataset}[/bold] split=[bold]{split}[/bold]...")
        records = load_hf_dataset(dataset, split=split, revision=revision, limit=limit)
        fields = resolve_fields(records, question_field, answer_field, id_field, image_field)

    if files_root is not None:
        from inspect_dataset.scanner import get_sample_id as _gsid

        root = Path(files_root)
        attached = 0
        for idx, record in enumerate(records):
            sample_dir = root / str(_gsid(record, fields, idx))
            if sample_dir.is_dir():
                record["__artifacts_dir__"] = str(sample_dir)
                attached += 1
        console.print(
            f"  Artifacts: {attached}/{len(records)} samples have a directory under {root}"
        )

    console.print(f"  Loaded {len(records):,} samples.")
    console.print(
        f"  Fields: question=[bold]{fields.question}[/bold]  "
        f"answer=[bold]{fields.answer}[/bold]"
        + (f"  id=[bold]{fields.id}[/bold]" if fields.id else "")
    )

    all_scanners = scanner_list + llm_scanners
    console.print(f"\nRunning {len(all_scanners)} scanner(s)...")
    if llm_scanners:
        console.print(
            f"  LLM scanners: {', '.join(s.name for s in llm_scanners)} "
            f"(model: [bold]{model}[/bold])"
        )

    source_type = "local" if is_local else ("inspect_task" if is_task else "hf")

    if llm_scanners:
        import asyncio

        run = asyncio.run(
            run_scanners_async(
                records,
                fields,
                all_scanners,
                dataset_name=dataset,
                split=resolved_split,
                source_type=source_type,
                revision=revision,
            )
        )
    else:
        run = run_scanners(
            records,
            fields,
            scanner_list,
            dataset_name=dataset,
            split=resolved_split,
            source_type=source_type,
            revision=revision,
        )

    print_report(run, console=console)

    if output_dir is None:
        base = Path(dataset).resolve().name if is_local else dataset.split("/")[-1]
        slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
        output_dir = f"findings/{slug}_{timestamp}"

    out = Path(output_dir)
    save_findings(
        run,
        out,
        records=records,
        fields=fields,
        files_root=str(Path(files_root).resolve()) if files_root else None,
    )
    console.print(f"Findings saved to [bold]{out}[/bold]")


@cli.command(name="tasks")
def list_tasks() -> None:
    """List inspect_ai tasks available via installed packages."""
    from rich.table import Table

    try:
        from inspect_ai._util.entrypoints import ensure_entry_points
        from inspect_ai._util.registry import (
            registry_find,
            registry_info,
        )
    except ImportError:
        raise click.ClickException(
            "inspect_ai is required for this command. "
            "Install it with: pip install 'inspect-dataset[inspect]'"
        ) from None

    ensure_entry_points()
    tasks = registry_find(lambda info: info.type == "task")

    console = Console()
    if not tasks:
        console.print("No inspect_ai tasks found.")
        return

    table = Table(title=f"inspect_ai Tasks ({len(tasks)} registered)")
    table.add_column("Name", style="bold")
    table.add_column("Package")

    rows: list[tuple[str, str]] = []
    for t in tasks:
        info = registry_info(t)
        name = info.name
        package = name.split("/")[0] if "/" in name else ""
        rows.append((name, package))

    for name, package in sorted(rows):
        table.add_row(name, package)

    console.print(table)


@cli.command(name="scanners")
def list_scanners() -> None:
    """List all registered scanners."""
    from rich.table import Table

    console = Console()
    table = Table(title="Registered Scanners")
    table.add_column("Scanner", style="bold")
    table.add_column("Type")
    table.add_column("Description")

    for s in BUILTIN_SCANNERS:
        table.add_row(s.name, "static", s.description)
    for name, factory in LLM_SCANNER_FACTORIES.items():
        # Build a temporary instance to read its description
        desc = factory("_placeholder").description
        table.add_row(name, "llm", desc)

    console.print(table)


def _resolve_findings_dirs(paths: tuple[str, ...]) -> list[str]:
    """Expand paths into a flat list of valid findings directories.

    A path is a findings dir if it directly contains scan_summary.json.
    Otherwise it is treated as a parent dir and its immediate children are
    checked.  This supports all three invocation styles:

        inspect-dataset view findings/vqa-rad/        # single dir
        inspect-dataset view results/                 # parent dir
        inspect-dataset view results/a/ results/b/   # explicit list
    """
    dirs: list[str] = []
    for p in paths:
        path = Path(p)
        if (path / "scan_summary.json").exists():
            dirs.append(str(path))
        else:
            for child in sorted(path.iterdir()):
                if child.is_dir() and (child / "scan_summary.json").exists():
                    dirs.append(str(child))
    return dirs


@cli.command(name="view")
@click.argument("findings_dirs", nargs=-1, required=False, type=click.Path(exists=True))
@click.option(
    "--port",
    default=7576,
    show_default=True,
    help="Port for the local viewer server.",
)
@click.option(
    "--no-open",
    is_flag=True,
    default=False,
    help="Don't automatically open the browser.",
)
def view(findings_dirs: tuple[str, ...], port: int, no_open: bool) -> None:
    r"""Launch the interactive dataset explorer.

    When called without arguments, opens the explorer home screen where you can
    browse cached HuggingFace datasets and installed inspect tasks.

    Optionally pass one or more findings directories to pre-load scan results:

    \b
      # Open explorer (no pre-loaded findings)
      inspect-dataset view

      # Single findings dir
      inspect-dataset view findings/vqa-rad/

      # Parent dir (all subdirs with scan_summary.json are loaded)
      inspect-dataset view results/

      # Explicit list
      inspect-dataset view results/vqa-rad/ results/medqa/
    """
    import webbrowser

    from inspect_dataset._view.server import create_app, run_server

    console = Console()

    dirs: list[str] = []
    if findings_dirs:
        dirs = _resolve_findings_dirs(findings_dirs)
        if not dirs:
            raise click.ClickException(
                "No findings directories found. "
                "Each directory must contain a scan_summary.json file. "
                "Run `inspect-dataset scan ... -o <dir>` first."
            )

    dir_paths: list[str | Path] = list(dirs)
    try:
        create_app(dir_paths)  # validate before starting
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e

    url = f"http://localhost:{port}"
    if dirs:
        label = dirs[0] if len(dirs) == 1 else f"{len(dirs)} datasets"
        console.print(f"Starting viewer at [bold]{url}[/bold] ({label})")
    else:
        console.print(f"Starting dataset explorer at [bold]{url}[/bold]")

    if not no_open:
        webbrowser.open(url)

    dirs_arg: list[str | Path] | None = list(dirs) if dirs else None
    run_server(dirs_arg, port=port)


@cli.command()
@click.argument("findings_dir", type=click.Path(exists=True))
def report(findings_dir: str) -> None:
    """Print a summary report from a saved findings directory."""
    import json

    console = Console()
    path = Path(findings_dir)
    summary_file = path / "scan_summary.json"

    if not summary_file.exists():
        raise click.ClickException(f"No scan_summary.json found in {findings_dir}")

    summary = json.loads(summary_file.read_text())
    console.print_json(json.dumps(summary, indent=2))

    report_file = path / "REPORT.md"
    if report_file.exists():
        console.print(f"\nFull report: [bold]{report_file}[/bold]")
