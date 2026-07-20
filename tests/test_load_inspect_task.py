"""Tests for load_inspect_task and import_task."""

from __future__ import annotations

import pytest

from inspect_dataset.loader import (
    _input_to_str,
    _target_to_str,
    load_inspect_task,
    load_task_from_spec,
)

# ---------------------------------------------------------------------------
# Helpers — minimal stand-ins for inspect_ai objects
# ---------------------------------------------------------------------------


class _Msg:
    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


class _ContentBlock:
    def __init__(self, type: str, text: str) -> None:
        self.type = type
        self.text = text


class _Sample:
    def __init__(
        self,
        input: object,
        target: object = "",
        id: object = None,
        metadata: dict | None = None,
        choices: list | None = None,
        files: dict | None = None,
    ) -> None:
        self.input = input
        self.target = target
        self.id = id
        self.metadata = metadata
        self.choices = choices
        self.files = files


class _Task:
    def __init__(self, dataset: list[_Sample]) -> None:
        self.dataset = dataset


# ---------------------------------------------------------------------------
# _input_to_str
# ---------------------------------------------------------------------------


def test_input_str_passthrough():
    assert _input_to_str("what is shown?") == "what is shown?"


def test_input_message_list_last_user():
    msgs = [_Msg("system", "you are a doctor"), _Msg("user", "what organ is this?")]
    assert _input_to_str(msgs) == "what organ is this?"


def test_input_message_list_last_user_wins():
    msgs = [
        _Msg("user", "first question"),
        _Msg("assistant", "answer"),
        _Msg("user", "follow-up?"),
    ]
    assert _input_to_str(msgs) == "follow-up?"


def test_input_message_list_no_user_falls_back_to_first():
    msgs = [_Msg("system", "system prompt")]
    assert _input_to_str(msgs) == "system prompt"


def test_input_message_list_content_blocks():
    block = _ContentBlock(type="text", text="describe the scan")
    msg = _Msg("user", "ignored")  # content will be overridden
    msg.content = [block]  # type: ignore[assignment]
    assert _input_to_str([msg]) == "describe the scan"


def test_input_dict_messages():
    msgs = [{"role": "user", "content": "what is the diagnosis?"}]
    assert _input_to_str(msgs) == "what is the diagnosis?"


# ---------------------------------------------------------------------------
# _target_to_str
# ---------------------------------------------------------------------------


def test_target_str_passthrough():
    assert _target_to_str("yes") == "yes"


def test_target_list_first_element():
    assert _target_to_str(["yes", "correct"]) == "yes"


def test_target_empty_list():
    assert _target_to_str([]) == ""


def test_target_none():
    assert _target_to_str(None) == ""


# ---------------------------------------------------------------------------
# load_inspect_task
# ---------------------------------------------------------------------------


def _make_task(*samples: _Sample) -> _Task:
    return _Task(list(samples))


def test_basic_string_input():
    task = _make_task(_Sample("what organ?", "liver", id=1))
    records, fields = load_inspect_task(task)
    assert len(records) == 1
    assert records[0]["input"] == "what organ?"
    assert records[0]["target"] == "liver"
    assert records[0]["id"] == 1
    assert fields.question == "input"
    assert fields.answer == "target"
    assert fields.id == "id"


def test_callable_task_is_invoked():
    task = _make_task(_Sample("q", "a"))
    records, _ = load_inspect_task(lambda: task)
    assert len(records) == 1


def test_list_target_uses_first():
    task = _make_task(_Sample("q", ["yes", "correct"]))
    records, _ = load_inspect_task(task)
    assert records[0]["target"] == "yes"


def test_metadata_merged_into_record():
    task = _make_task(_Sample("q", "a", metadata={"topic": "radiology", "difficulty": "hard"}))
    records, _ = load_inspect_task(task)
    assert records[0]["topic"] == "radiology"
    assert records[0]["difficulty"] == "hard"


def test_choices_preserved():
    task = _make_task(_Sample("which modality?", "mri", choices=["mri", "ct", "xray"]))
    records, _ = load_inspect_task(task)
    assert records[0]["choices"] == ["mri", "ct", "xray"]


def test_files_stored_under_dunder_key():
    task = _make_task(_Sample("q", "a", files={"image.jpg": "data:image/jpeg;base64,abc="}))
    records, _ = load_inspect_task(task)
    assert records[0]["__files__"] == {"image.jpg": "data:image/jpeg;base64,abc="}


def test_limit_respected():
    task = _make_task(*[_Sample(f"q{i}", f"a{i}") for i in range(10)])
    records, _ = load_inspect_task(task, limit=3)
    assert len(records) == 3


def test_multiple_samples_all_loaded():
    task = _make_task(
        _Sample("q1", "a1", id="s1"),
        _Sample("q2", "a2", id="s2"),
        _Sample("q3", "a3", id="s3"),
    )
    records, _ = load_inspect_task(task)
    assert len(records) == 3
    assert [r["id"] for r in records] == ["s1", "s2", "s3"]


# ---------------------------------------------------------------------------
# load_task_from_spec — module@attr path (no inspect_ai needed for this path)
# ---------------------------------------------------------------------------


def test_load_task_from_spec_module_at_attr():
    # Use a dotted module name so the module-import branch is taken
    import sys
    import types

    task = _make_task(_Sample("q", "a", id=1))
    fake_mod = types.ModuleType("_fake_pkg._fake_mod")
    fake_mod.my_task = task  # type: ignore[attr-defined]
    sys.modules["_fake_pkg._fake_mod"] = fake_mod

    records, _fields = load_task_from_spec("_fake_pkg._fake_mod@my_task")
    assert len(records) == 1
    assert records[0]["input"] == "q"

    del sys.modules["_fake_pkg._fake_mod"]


def test_load_task_from_spec_bad_module():
    # Dotted name triggers the module-import branch; module doesn't exist
    with pytest.raises(ImportError, match=r"no_such_pkg\.no_such_mod"):
        load_task_from_spec("no_such_pkg.no_such_mod@something")


def test_load_task_from_spec_bad_attr():
    # Dotted module exists but attribute does not
    with pytest.raises(AttributeError, match="no_such_attr_xyz"):
        load_task_from_spec("os.path@no_such_attr_xyz")
