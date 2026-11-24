import importlib
from pathlib import Path

import pytest

from inspect_dataset._ignore import (
    IGNORE_FILE_NAME,
    IgnoreFileError,
    apply_ignores,
    find_ignore_file,
    load_ignore_file,
    task_source_dir,
)
from inspect_dataset._types import Finding, ScanRun

GOOD = (
    "ignore:\n"
    "  - scanner: duplicate_questions\n"
    "    reason: Several questions share one passage by design.\n"
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / IGNORE_FILE_NAME
    path.write_text(text)
    return path


def _finding(scanner: str) -> Finding:
    return Finding(
        scanner=scanner,
        severity="low",
        category="question_quality",
        explanation="e",
        sample_index=0,
    )


def test_the_file_name():
    assert IGNORE_FILE_NAME == ".inspect-dataset.yaml"


def test_load_maps_scanner_to_reason(tmp_path: Path):
    assert load_ignore_file(_write(tmp_path, GOOD)) == {
        "duplicate_questions": "Several questions share one passage by design."
    }


@pytest.mark.parametrize("text", ["", "# nothing\n", "{}\n", "ignore: []\n"])
def test_an_empty_file_ignores_nothing(tmp_path: Path, text: str):
    assert load_ignore_file(_write(tmp_path, text)) == {}


@pytest.mark.parametrize(
    "text",
    [
        "ignore:\n  - scanner: duplicate_questions\n",  # no reason
        "ignore:\n  - scanner: duplicate_questions\n    reason: '  '\n",  # blank reason
        "ignore:\n  - reason: why\n",  # no scanner
        "ignore:\n  - scanner: a\n    reason: r\n    sample: 3\n",  # unknown entry key
        # listed twice
        "ignore:\n  - scanner: a\n    reason: r\n  - scanner: a\n    reason: again\n",
        "ignore:\n  duplicate_questions: why\n",  # not a list
        "- scanner: a\n  reason: r\n",  # top level is not a mapping
        "ignored:\n  - scanner: a\n    reason: r\n",  # unknown top-level key
        "ignore: [\n",  # does not parse
        "ignore:\n  - duplicate_questions\n",  # entry is a string
        "ignore:\n  - scanner: 3\n    reason: r\n",  # scanner is not a string
        "ignore:\n  - scanner: a\n    reason: No\n",  # reason is read as a boolean
        "ignore:\n  - scanner: '  '\n    reason: r\n",  # blank scanner
        "ignore:\n  - scanner: a\n    scanner: b\n    reason: r\n",  # repeated entry key
        # repeated top-level key
        "ignore:\n  - scanner: a\n    reason: r\nignore:\n  - scanner: b\n    reason: r\n",
        "ignore:\n  - scanner: a\n    reason: |\n      line one\n      line two\n",  # two lines
        'ignore:\n  - scanner: a\n    reason: "one\\rtwo"\n',  # carriage return
        "? !!seq ''\n: x\n",  # key that cannot be hashed
        "? !!map ''\n: x\n",  # key that cannot be hashed
        "? !!set ''\n: x\n",  # key that cannot be hashed
    ],
)
def test_a_malformed_file_is_an_error(tmp_path: Path, text: str):
    with pytest.raises(IgnoreFileError):
        load_ignore_file(_write(tmp_path, text))


def test_a_file_that_is_not_utf8_is_an_error(tmp_path: Path):
    path = tmp_path / IGNORE_FILE_NAME
    path.write_bytes(b"\xff\xfe" + "ignore: []\n".encode("utf-16-le"))
    with pytest.raises(IgnoreFileError, match="UTF-8"):
        load_ignore_file(path)


@pytest.mark.parametrize("name", ["missing.yaml", ""])
def test_a_path_that_cannot_be_opened_is_an_error(tmp_path: Path, name: str):
    # The empty name gives tmp_path itself, a directory.
    with pytest.raises(IgnoreFileError, match="could not be opened"):
        load_ignore_file(tmp_path / name)


def test_a_missing_reason_names_the_entry(tmp_path: Path):
    text = "ignore:\n  - scanner: a\n    reason: r\n  - scanner: b\n"
    with pytest.raises(IgnoreFileError, match=r"ignore\[1\]"):
        load_ignore_file(_write(tmp_path, text))


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("ignore:\n  - scanner: a\n    scanner: b\n    reason: r\n", "scanner"),
        (
            "ignore:\n  - scanner: a\n    reason: r\nignore:\n  - scanner: b\n    reason: r\n",
            "ignore",
        ),
    ],
)
def test_a_repeated_key_is_named(tmp_path: Path, text: str, key: str):
    with pytest.raises(IgnoreFileError, match=f"'{key}'"):
        load_ignore_file(_write(tmp_path, text))


def test_a_reason_with_a_line_break_names_the_entry(tmp_path: Path):
    text = (
        "ignore:\n  - scanner: a\n    reason: r\n"
        "  - scanner: b\n    reason: |\n      line one\n      line two\n"
    )
    with pytest.raises(IgnoreFileError, match=r"ignore\[1\]: reason"):
        load_ignore_file(_write(tmp_path, text))


def test_a_folded_reason_on_one_line_loads_stripped(tmp_path: Path):
    text = (
        "ignore:\n  - scanner: a\n    reason: >\n"
        "      Several questions\n      share one passage.\n"
    )
    assert load_ignore_file(_write(tmp_path, text)) == {"a": "Several questions share one passage."}


def _run() -> ScanRun:
    return ScanRun(
        dataset_name="d",
        split=None,
        total_samples=3,
        findings=[
            _finding("duplicate_questions"),
            _finding("duplicate_questions"),
            _finding("answer_length"),
        ],
        scanner_status={
            "duplicate_questions": {"status": "ran"},
            "answer_length": {"status": "ran"},
            "image_mime_type": {"status": "not_applicable", "reason": "no images"},
        },
    )


def test_an_ignored_scanner_keeps_its_count_and_loses_its_findings():
    run = _run()
    apply_ignores(run, {"duplicate_questions": "by design"})
    assert [f.scanner for f in run.findings] == ["answer_length"]
    assert run.scanner_status["duplicate_questions"] == {
        "status": "ignored",
        "reason": "by design",
        "findings": 2,
    }
    assert run.scanner_status["answer_length"] == {"status": "ran"}


def test_an_ignored_scanner_with_no_findings_records_zero():
    run = _run()
    run.findings = []
    apply_ignores(run, {"answer_length": "r"})
    assert run.scanner_status["answer_length"] == {
        "status": "ignored",
        "reason": "r",
        "findings": 0,
    }


def test_a_not_applicable_scanner_stays_not_applicable():
    run = _run()
    apply_ignores(run, {"image_mime_type": "r"})
    assert run.scanner_status["image_mime_type"] == {
        "status": "not_applicable",
        "reason": "no images",
    }


def test_a_scanner_that_did_not_run_is_left_out():
    run = _run()
    apply_ignores(run, {"llm_answer_check": "r"})
    assert "llm_answer_check" not in run.scanner_status
    assert len(run.findings) == 3


def _package(root: Path, name: str) -> Path:
    pkg = root / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    return pkg


def test_a_file_spec_looks_beside_the_file(tmp_path: Path):
    (tmp_path / "task.py").write_text("")
    ignore = _write(tmp_path, GOOD)
    assert find_ignore_file(f"{tmp_path / 'task.py'}@my_task") == ignore


def test_a_module_spec_looks_beside_the_module(fake_packages: Path):
    pkg = _package(fake_packages, "ids_ignore_a")
    (pkg / "tasks.py").write_text("")
    ignore = _write(pkg, GOOD)
    assert find_ignore_file("ids_ignore_a.tasks@my_task") == ignore


def test_a_package_task_spec_looks_in_the_eval_folder(fake_packages: Path):
    pkg = _package(fake_packages, "ids_ignore_b")
    eval_dir = _package(pkg, "drop")
    ignore = _write(eval_dir, GOOD)
    assert find_ignore_file("ids_ignore_b/drop") == ignore


def test_a_registry_name_looks_beside_the_task_functions_source(fake_packages: Path, monkeypatch):
    pkg = _package(fake_packages, "ids_ignore_c")
    eval_dir = _package(pkg, "mmlu")
    (eval_dir / "mmlu.py").write_text("def mmlu_0_shot():\n    return None\n")
    ignore = _write(eval_dir, GOOD)
    module = importlib.import_module("ids_ignore_c.mmlu.mmlu")
    monkeypatch.setattr(
        "inspect_ai._util.registry.registry_lookup",
        lambda type, name: module.mmlu_0_shot if name == "ids_ignore_c/mmlu_0_shot" else None,
    )
    assert find_ignore_file("ids_ignore_c/mmlu_0_shot") == ignore


def test_a_registered_inspect_evals_task_resolves_to_its_eval_folder():
    pytest.importorskip("inspect_evals")
    assert task_source_dir("inspect_evals/mmlu_0_shot").parts[-2:] == ("inspect_evals", "mmlu")


def test_no_file_beside_the_task_gives_none(tmp_path: Path):
    (tmp_path / "task.py").write_text("")
    assert find_ignore_file(f"{tmp_path / 'task.py'}@my_task") is None


def test_the_parent_folder_is_not_searched(fake_packages: Path):
    pkg = _package(fake_packages, "ids_ignore_d")
    _package(pkg, "drop")
    _write(pkg, GOOD)
    assert find_ignore_file("ids_ignore_d/drop") is None


def test_an_unresolvable_spec_gives_none():
    assert task_source_dir("no_such_owner_pkg_xyz/boolq") is None
    assert task_source_dir("no_such_module_xyz@task") is None


def test_a_built_in_module_without_a_file_gives_none():
    assert task_source_dir("sys@x") is None
