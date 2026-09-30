"""Field overrides in task mode change only the roles given and keep the task's context."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

import inspect_dataset.cli as cli_mod
from inspect_dataset._types import FieldMap
from inspect_dataset.cli import cli

_TASK_FIELDS = FieldMap(
    question="input",
    answer="target",
    id="id",
    image="images",
    choices="choices",
    scorers=["inspect_ai/choice"],
)


def _scan_fields(tmp_path: Path, monkeypatch, args: list[str]) -> FieldMap:
    def fake_load_task_from_spec(spec, limit=None):
        records = [
            {
                "input": "Which colour?",
                "question": "metadata question",
                "target": "A",
                "targets": ["A"],
                "id": "s1",
                "choices": ["red", "blue"],
                "images": [],
                "picture": [],
            }
        ]
        return records, FieldMap(**vars(_TASK_FIELDS))

    seen: list[FieldMap] = []
    real_run_scanners = cli_mod.run_scanners

    def spy_run_scanners(records, fields, *a, **kw):
        seen.append(fields)
        return real_run_scanners(records, fields, *a, **kw)

    monkeypatch.setattr(cli_mod, "load_task_from_spec", fake_load_task_from_spec)
    monkeypatch.setattr(cli_mod, "run_scanners", spy_run_scanners)
    out = tmp_path / "findings"
    result = CliRunner().invoke(cli, ["scan", "some.module@t", "-o", str(out), *args])
    assert result.exit_code == 0, result.output
    return seen[0]


def test_answer_override_keeps_choices_image_and_scorers(tmp_path: Path, monkeypatch):
    fields = _scan_fields(
        tmp_path, monkeypatch, ["--answer-field", "targets", "--answer-subfield", "*"]
    )
    assert fields == FieldMap(
        question="input",
        answer="targets",
        id="id",
        image="images",
        answer_subfield="*",
        choices="choices",
        scorers=["inspect_ai/choice"],
    )


def test_question_override_keeps_the_task_answer(tmp_path: Path, monkeypatch):
    fields = _scan_fields(tmp_path, monkeypatch, ["--question-field", "question"])
    assert (fields.question, fields.answer, fields.id) == ("question", "target", "id")
    assert fields.image == "images"
    assert fields.scorers == ["inspect_ai/choice"]


def test_image_override_applies_in_task_mode(tmp_path: Path, monkeypatch):
    fields = _scan_fields(tmp_path, monkeypatch, ["--image-field", "picture"])
    assert fields.image == "picture"
    assert fields.choices == "choices"


def test_no_override_keeps_the_task_field_map(tmp_path: Path, monkeypatch):
    assert _scan_fields(tmp_path, monkeypatch, []) == _TASK_FIELDS
