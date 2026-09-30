"""Tests for load_inspect_task and import_task."""

from __future__ import annotations

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, accuracy, choice, match, scorer

from inspect_dataset.loader import (
    _input_to_str,
    _target_to_str,
    load_inspect_task,
    load_task_from_spec,
)
from inspect_dataset.scanners._answers import answer_texts, resolved_answer
from inspect_dataset.scanners.answer_length import answer_length

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


def test_list_target_keeps_every_target():
    task = _make_task(_Sample("q", ["yes", "correct"]))
    records, _ = load_inspect_task(task)
    assert records[0]["targets"] == ["yes", "correct"]


def test_scalar_target_is_a_one_element_target_list():
    task = _make_task(_Sample("q", "liver"))
    records, _ = load_inspect_task(task)
    assert records[0]["targets"] == ["liver"]


def test_empty_list_target_has_no_targets():
    task = _make_task(_Sample("q", []))
    records, _ = load_inspect_task(task)
    assert records[0]["target"] == ""
    assert records[0]["targets"] == []


def test_every_target_is_measured_through_the_star_subfield():
    task = _make_task(
        _Sample("q1", ["4", "four apples in a basket on the table"], id="a"),
        _Sample("q2", "Paris", id="b"),
    )
    records, fields = load_inspect_task(task)
    fields.answer = "targets"
    fields.answer_subfield = "*"
    assert answer_texts(records, fields, "answer_length") == [
        ["4", "four apples in a basket on the table"],
        ["Paris"],
    ]
    findings = answer_length.fn(records, fields)
    assert [(f.sample_id, f.metadata["element_index"]) for f in findings] == [("a", 1)]


def test_metadata_merged_into_record():
    task = _make_task(_Sample("q", "a", metadata={"topic": "radiology", "difficulty": "hard"}))
    records, _ = load_inspect_task(task)
    assert records[0]["topic"] == "radiology"
    assert records[0]["difficulty"] == "hard"


# ---------------------------------------------------------------------------
# Group field auto-detection (issue #36)
# ---------------------------------------------------------------------------


def _task_with_metadata(*metadata: dict) -> _Task:
    return _make_task(*(_Sample(f"q{i}", "a", id=i, metadata=m) for i, m in enumerate(metadata)))


def test_single_subset_candidate_is_the_group():
    task = _task_with_metadata({"dataset_name": "navigate"}, {"dataset_name": "web_of_lies"})
    _, fields = load_inspect_task(task)
    assert fields.group == "dataset_name"


def test_no_subset_candidate_means_no_group():
    task = _task_with_metadata({"topic": "a"}, {"topic": "b"})
    _, fields = load_inspect_task(task)
    assert fields.group is None


def test_two_subset_candidates_mean_no_group():
    task = _task_with_metadata(
        {"subject": "law", "category": "x"}, {"subject": "math", "category": "y"}
    )
    _, fields = load_inspect_task(task)
    assert fields.group is None


def test_candidate_with_one_value_is_ignored():
    task = _task_with_metadata({"subject": "law"}, {"subject": "law"})
    _, fields = load_inspect_task(task)
    assert fields.group is None


def test_single_valued_candidate_does_not_block_another():
    task = _task_with_metadata(
        {"subject": "law", "category": "x"}, {"subject": "math", "category": "x"}
    )
    _, fields = load_inspect_task(task)
    assert fields.group == "subject"


def test_candidate_with_non_scalar_values_is_ignored():
    task = _task_with_metadata({"category": ["a"]}, {"category": ["b"]})
    _, fields = load_inspect_task(task)
    assert fields.group is None


def test_candidate_missing_from_some_samples_still_counts():
    task = _task_with_metadata({"subject": "law"}, {"subject": "math"}, {})
    _, fields = load_inspect_task(task)
    assert fields.group == "subject"


def test_choices_preserved():
    task = _make_task(_Sample("which modality?", "mri", choices=["mri", "ct", "xray"]))
    records, _ = load_inspect_task(task)
    assert records[0]["choices"] == ["mri", "ct", "xray"]


def test_choices_field_set_when_a_sample_has_choices():
    task = _make_task(
        _Sample("open question", "liver"),
        _Sample("which modality?", "A", choices=["mri", "ct"]),
    )
    records, fields = load_inspect_task(task)
    assert fields.choices == "choices"
    assert "choices" not in records[0]


def test_choices_field_unset_without_choices():
    _, fields = load_inspect_task(_make_task(_Sample("q", "a"), _Sample("q2", "b")))
    assert fields.choices is None


def test_choices_in_metadata_do_not_set_the_choices_field():
    task = _make_task(_Sample("q", "a", metadata={"choices": {"label": ["A"], "text": ["x"]}}))
    _, fields = load_inspect_task(task)
    assert fields.choices is None


def test_real_sample_choices_resolve_from_letter_target():
    task = Task(dataset=[Sample(input="Pick", target="B", choices=["red", "blue"], id="s1")])
    records, fields = load_inspect_task(task)
    assert records[0]["choices"] == ["red", "blue"]
    assert resolved_answer(records[0], fields) == "blue"


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
# load_inspect_task — scorer registry names on the FieldMap
# ---------------------------------------------------------------------------


@scorer(metrics=[accuracy()])
def custom_scorer():
    async def score(state, target):
        return Score(value=1)

    return score


def _real_task(**kwargs) -> Task:
    return Task(dataset=[Sample(input="What is 2+2?", target="4", id="s1")], **kwargs)


def test_builtin_scorer_registry_name():
    _, fields = load_inspect_task(_real_task(scorer=choice()))
    assert fields.scorers == ["inspect_ai/choice"]


def test_multiple_scorers_keep_their_order():
    _, fields = load_inspect_task(_real_task(scorer=[match(), choice()]))
    assert fields.scorers == ["inspect_ai/match", "inspect_ai/choice"]


def test_custom_scorer_registry_name():
    _, fields = load_inspect_task(_real_task(scorer=custom_scorer()))
    assert fields.scorers == ["custom_scorer"]


def test_task_without_scorer_has_empty_scorer_list():
    _, fields = load_inspect_task(_real_task())
    assert fields.scorers == []


def test_stand_in_task_without_scorer_attribute():
    _, fields = load_inspect_task(_make_task(_Sample("q", "a")))
    assert fields.scorers == []


def test_single_scorer_not_in_a_list():
    task = _make_task(_Sample("q", "a"))
    task.scorer = choice()  # type: ignore[attr-defined]
    _, fields = load_inspect_task(task)
    assert fields.scorers == ["inspect_ai/choice"]


def test_non_registry_scorer_is_skipped():
    async def plain(state, target):
        return Score(value=1)

    task = _make_task(_Sample("q", "a"))
    task.scorer = [plain, choice()]  # type: ignore[attr-defined]
    _, fields = load_inspect_task(task)
    assert fields.scorers == ["inspect_ai/choice"]


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
