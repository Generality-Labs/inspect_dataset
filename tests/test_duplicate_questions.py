import base64

from inspect_dataset._types import FieldMap
from inspect_dataset.scanners.duplicate_questions import duplicate_questions

FIELDS = FieldMap(question="q", answer="a")


def recs(*pairs: tuple[str, str]) -> list[dict]:
    """Build records from (question, answer) pairs."""
    return [{"q": q, "a": a} for q, a in pairs]


# ---------------------------------------------------------------------------
# No image field — classify by answer agreement
# ---------------------------------------------------------------------------


def test_no_duplicates_no_findings():
    data = recs(("what is A?", "yes"), ("what is B?", "no"), ("what is C?", "yes"))
    assert duplicate_questions(data, FIELDS) == []


def test_no_image_same_answer_is_high():
    data = recs(("is it broken?", "no"), ("other q", "yes"), ("is it broken?", "no"))
    findings = duplicate_questions(data, FIELDS)
    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].metadata["answers_agree"] is True


def test_no_image_different_answer_is_low():
    data = recs(
        ("is the heart enlarged?", "yes"), ("other", "no"), ("is the heart enlarged?", "no")
    )
    findings = duplicate_questions(data, FIELDS)
    assert len(findings) == 1
    assert findings[0].severity == "low"
    assert findings[0].metadata["answers_agree"] is False


def test_no_image_triplicate_same_answer_is_high():
    data = recs(("same?", "yes"), ("same?", "yes"), ("same?", "yes"))
    findings = duplicate_questions(data, FIELDS)
    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].metadata["duplicate_count"] == 3


# ---------------------------------------------------------------------------
# With image field — three-way classification
# ---------------------------------------------------------------------------

IMG_FIELDS = FieldMap(question="q", answer="a", image="img")

IMG1 = {"bytes": b"image-one", "path": None}
IMG2 = {"bytes": b"image-two", "path": None}
IMG3 = {"bytes": b"image-three", "path": None}


def img_rec(question: str, answer: str, img: dict) -> dict:
    return {"q": question, "a": answer, "img": img}


def test_exact_duplicate_same_image_is_high():
    # Same question, same image → real duplicate
    data = [img_rec("is this normal?", "no", IMG1), img_rec("is this normal?", "no", IMG1)]
    findings = duplicate_questions(data, IMG_FIELDS)
    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].metadata["duplicate_type"] == "exact"


def test_same_question_different_image_same_answer_is_medium():
    # Same question, different images, same answer → image-independent question
    data = [img_rec("is this an mri?", "no", IMG1), img_rec("is this an mri?", "no", IMG2)]
    findings = duplicate_questions(data, IMG_FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["duplicate_type"] == "question_reuse"
    assert findings[0].severity == "medium"
    assert findings[0].metadata["answers_agree"] is True


def test_same_question_different_image_different_answer_is_low():
    # Same question, different images, different answers → standard VQA reuse
    data = [
        img_rec("is the heart enlarged?", "yes", IMG1),
        img_rec("is the heart enlarged?", "no", IMG2),
    ]
    findings = duplicate_questions(data, IMG_FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["duplicate_type"] == "question_reuse"
    assert findings[0].severity == "low"
    assert findings[0].metadata["answers_agree"] is False


def test_mixed_exact_and_reuse_findings():
    # idx 0 and 1: same question + same image (exact duplicate, HIGH)
    # idx 2: same question + different image, different answer (VQA reuse, LOW)
    data = [
        img_rec("what is shown?", "brain", IMG1),
        img_rec("what is shown?", "brain", IMG1),
        img_rec("what is shown?", "heart", IMG2),
    ]
    findings = duplicate_questions(data, IMG_FIELDS)
    exact = [f for f in findings if f.metadata.get("duplicate_type") == "exact"]
    reuse = [f for f in findings if f.metadata.get("duplicate_type") == "question_reuse"]
    assert [(f.severity, f.metadata["duplicate_indices"]) for f in exact] == [("high", [0, 1])]
    assert [(f.severity, f.metadata["duplicate_indices"]) for f in reuse] == [("low", [0, 1, 2])]


def test_no_duplicates_with_image_no_findings():
    data = [
        img_rec("is this normal?", "yes", IMG1),
        img_rec("is the heart enlarged?", "no", IMG2),
    ]
    assert duplicate_questions(data, IMG_FIELDS) == []


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def test_case_insensitive_normalisation():
    data = recs(("What Is A?", "yes"), ("what is a?", "yes"))
    findings = duplicate_questions(data, FIELDS)
    assert len(findings) == 1


def test_whitespace_normalisation():
    data = recs(("  what is a?  ", "yes"), ("what is a?", "yes"))
    findings = duplicate_questions(data, FIELDS)
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# Indices and IDs
# ---------------------------------------------------------------------------


def test_finding_indices_are_correct():
    data = recs(("unique", "x"), ("dup", "y"), ("other", "z"), ("dup", "y"))
    findings = duplicate_questions(data, FIELDS)
    assert [f.sample_index for f in findings] == [1]
    assert findings[0].metadata["duplicate_indices"] == [1, 3]


def test_sample_id_from_field():
    fields = FieldMap(question="q", answer="a", id="id")
    data = [
        {"q": "same", "a": "yes", "id": "id-0"},
        {"q": "same", "a": "yes", "id": "id-1"},
    ]
    findings = duplicate_questions(data, fields)
    assert [f.sample_id for f in findings] == ["id-0"]
    assert findings[0].metadata["duplicate_ids"] == ["id-0", "id-1"]


def test_one_finding_per_group_on_its_first_row():
    fields = FieldMap(question="q", answer="a", id="id")
    data = [
        {"q": "other", "a": "x", "id": "s0"},
        {"q": "dup", "a": "y", "id": "s1"},
        {"q": "dup", "a": "y", "id": "s2"},
        {"q": "dup", "a": "y", "id": "s3"},
    ]
    [finding] = duplicate_questions(data, fields)
    assert (finding.sample_index, finding.sample_id) == (1, "s1")
    assert finding.metadata == {
        "question": "dup",
        "answers_agree": True,
        "duplicate_indices": [1, 2, 3],
        "duplicate_ids": ["s1", "s2", "s3"],
        "duplicate_count": 3,
    }


def test_large_group_lists_only_the_first_indices_in_the_explanation():
    data = recs(*[("same?", "yes")] * 40)
    [finding] = duplicate_questions(data, FIELDS)
    assert "and 30 more" in finding.explanation
    assert "39" not in finding.explanation
    assert finding.metadata["duplicate_indices"] == list(range(40))


# ---------------------------------------------------------------------------
# List-valued image field — one key per sample from all of its images
# ---------------------------------------------------------------------------


def test_same_image_list_is_an_exact_duplicate():
    data = [img_rec("which is larger?", "A", [IMG1, IMG2]) for _ in range(2)]
    findings = duplicate_questions(data, IMG_FIELDS)
    assert [(f.metadata["duplicate_type"], f.severity) for f in findings] == [("exact", "high")]


def test_image_lists_differing_in_one_image_are_question_reuse():
    data = [
        img_rec("which is larger?", "A", [IMG1, IMG2]),
        img_rec("which is larger?", "B", [IMG1, IMG3]),
    ]
    findings = duplicate_questions(data, IMG_FIELDS)
    assert [(f.metadata["duplicate_type"], f.severity) for f in findings] == [
        ("question_reuse", "low")
    ]


def test_same_question_with_and_without_an_image_is_question_reuse():
    # A task that mixes image and text-only samples gives the text-only ones an empty list
    data = [img_rec("what is 2+2?", "4", [IMG1]), img_rec("what is 2+2?", "4", [])]
    findings = duplicate_questions(data, IMG_FIELDS)
    assert [(f.metadata["duplicate_type"], f.severity) for f in findings] == [
        ("question_reuse", "medium")
    ]


def test_missing_image_next_to_an_image_is_question_reuse():
    data = [img_rec("is this normal?", "yes", IMG1), {"q": "is this normal?", "a": "no"}]
    findings = duplicate_questions(data, IMG_FIELDS)
    assert [(f.metadata["duplicate_type"], f.severity) for f in findings] == [
        ("question_reuse", "low")
    ]


# ---------------------------------------------------------------------------
# Sample identity — choices and image content
# ---------------------------------------------------------------------------

CHOICE_FIELDS = FieldMap(question="q", answer="a", choices="choices")
HYPERBATON = "Which sentence has the correct adjective order: OPTIONS:"


def choice_rec(question: str, answer: str, choices: list[str], **extra) -> dict:
    return {"q": question, "a": answer, "choices": choices, **extra}


def test_rows_differing_only_in_choices_are_not_duplicates():
    data = [
        choice_rec(HYPERBATON, "A", ["old red car", "red old car"]),
        choice_rec(HYPERBATON, "B", ["wooden big box", "big wooden box"]),
        choice_rec(HYPERBATON, "A", ["tiny green cup", "green tiny cup"]),
    ]
    assert duplicate_questions(data, CHOICE_FIELDS) == []


def test_same_text_and_choices_are_duplicates():
    data = [
        choice_rec(HYPERBATON, "A", ["old red car", "red old car"]),
        choice_rec(HYPERBATON, "B", ["wooden big box", "big wooden box"]),
        choice_rec(HYPERBATON, "A", ["Old red car", "red  old car"]),
    ]
    findings = duplicate_questions(data, CHOICE_FIELDS)
    assert [f.metadata["duplicate_indices"] for f in findings] == [[0, 2]]
    assert findings[0].severity == "high"


def test_whitespace_inside_the_question_is_collapsed():
    data = recs(("what  is\n a?", "yes"), ("what is a?", "yes"))
    assert duplicate_questions(data, FIELDS)


def test_same_text_and_choices_with_different_images_are_question_reuse():
    fields = FieldMap(question="q", answer="a", image="img", choices="choices")
    data = [
        choice_rec("What is shown?", "A", ["cat", "dog"], img=IMG1),
        choice_rec("What is shown?", "B", ["cat", "dog"], img=IMG2),
    ]
    findings = duplicate_questions(data, fields)
    assert findings
    assert {f.metadata["duplicate_type"] for f in findings} == {"question_reuse"}


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
PNG_URI = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()


def test_same_image_as_a_file_and_a_data_uri_is_an_exact_duplicate():
    data = [
        img_rec("what is shown?", "a chart", [{"bytes": PNG_BYTES, "path": "/data/chart.png"}]),
        img_rec("what is shown?", "a chart", [PNG_URI]),
    ]
    findings = duplicate_questions(data, IMG_FIELDS)
    assert findings
    assert {f.metadata["duplicate_type"] for f in findings} == {"exact"}


def test_letter_and_text_answers_naming_the_same_choice_agree():
    data = [
        choice_rec("capital of france?", "A", ["Paris", "London"]),
        choice_rec("capital of france?", "paris", ["Paris", "London"]),
    ]
    findings = duplicate_questions(data, CHOICE_FIELDS)
    assert findings
    assert all(f.metadata["answers_agree"] is True for f in findings)
    assert all(f.severity == "high" for f in findings)


TASK_FIELDS = FieldMap(question="input", answer="target", id="id", scorers=["inspect_ai/f1"])


def task_rec(sid: str, targets: list[str]) -> dict:
    return {"input": "passage. how many?", "target": targets[0], "targets": targets, "id": sid}


def test_list_targets_in_any_order_agree():
    data = [task_rec("q1", ["3", "three"]), task_rec("q2", ["three", "3"])]
    findings = duplicate_questions(data, TASK_FIELDS)
    assert findings
    assert all(f.metadata["answers_agree"] is True for f in findings)


def test_list_targets_with_different_members_disagree():
    data = [task_rec("q1", ["3", "three"]), task_rec("q2", ["3"])]
    findings = duplicate_questions(data, TASK_FIELDS)
    assert findings
    assert all(f.metadata["answers_agree"] is False for f in findings)
