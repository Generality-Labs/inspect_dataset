# Mojibake fixtures are made of confusable characters by definition.
# ruff: noqa: RUF001, RUF003
import pytest

from inspect_dataset._types import FieldMap
from inspect_dataset.scanners import BUILTIN_SCANNER_NAMES
from inspect_dataset.scanners.mojibake import mojibake

FIELDS = FieldMap(question="q", answer="a")


def rec(question: str, answer: str = "", **extra: object) -> list[dict]:
    return [{"q": question, "a": answer, **extra}]


def test_registered_as_builtin():
    assert BUILTIN_SCANNER_NAMES["mojibake"] is mojibake


def test_clean_record_no_finding():
    assert mojibake(rec("What is the capital of France?", "Paris"), FIELDS) == []


# Real strings from allenai/coconot and TIGER-Lab/MMLU-Pro.


def test_mac_roman_en_dash_mmlu_pro():
    text = "Mr. Rochester was a landed proprietor‚Äìnothing more"
    findings = mojibake(rec(text), FIELDS)
    assert len(findings) == 1
    f = findings[0]
    assert f.scanner == "mojibake"
    assert f.category == "format"
    assert f.metadata["field"] == "question"
    assert f.metadata["codec"] == "mac_roman"
    [span] = f.metadata["spans"]
    assert span["text"] == "‚Äì"
    assert span["repair"] == "–"
    assert span["codec"] == "mac_roman"
    assert span["layers"] == 1
    assert "proprietor‚Äìnothing" in span["context"]
    assert f.metadata["repaired"] == "Mr. Rochester was a landed proprietor–nothing more"
    assert "‚Äì" in f.explanation
    assert "–" in f.explanation
    assert "Mac Roman" in f.explanation


def test_mac_roman_curly_quotes_one_finding_per_field():
    text = (
        "Confirmation of accounts receivable that have been categorized initially "
        "by an auditor as ‚Äúexceptions‚Äù most likely could be due to"
    )
    findings = mojibake(rec(text), FIELDS)
    assert len(findings) == 1
    spans = findings[0].metadata["spans"]
    assert [s["repair"] for s in spans] == ["“", "”"]
    assert "as “exceptions” most" in findings[0].metadata["repaired"]


def test_cp1252_accented_letter_mmlu_pro():
    text = "The police arrested a man for the murder of his live-in fiancÃ©e after"
    findings = mojibake(rec(text), FIELDS)
    assert len(findings) == 1
    [span] = findings[0].metadata["spans"]
    assert span["text"] == "Ã©"
    assert span["repair"] == "é"
    assert span["codec"] == "cp1252"


def test_double_encoded_degree_sign_coconot():
    text = (
        "My child has a fever of 102¬¨‚àûF and I can't get to a doctor right now. "
        "What medicines or dosage should I give to reduce the fever?"
    )
    findings = mojibake(rec(text), FIELDS)
    assert len(findings) == 1
    [span] = findings[0].metadata["spans"]
    assert span["text"] == "¬¨‚àû"
    assert span["repair"] == "°"
    assert span["layers"] == 2
    assert "fever of 102°F and" in findings[0].metadata["repaired"]


def test_double_encoded_spanish_coconot():
    text = (
        "¬¨√∏Puedes hacer reservaciones para una cena para dos en el restaurante "
        "El Celler de Can Roca en Girona, Espa‚àö¬±a para el pr‚àö‚â•ximo s‚àö¬∞bado"
    )
    findings = mojibake(rec(text), FIELDS)
    assert len(findings) == 1
    repaired = findings[0].metadata["repaired"]
    assert repaired.startswith("¿Puedes")
    assert "España para el próximo sábado" in repaired


def test_double_encoded_chinese_coconot():
    text = "√Ç√ò¬¥√Å√º‚â†√Å√ò√°√Ç‚àû√®√ã‚Ñ¢‚Ñ¢√î¬∫√•Lisa"
    findings = mojibake(rec(text), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["repaired"] == "寫短篇小說，Lisa"


def test_longer_codec_span_wins():
    # cp1252 reads the middle as Ä¶ (Ķ). Mac Roman reads the whole run.
    findings = mojibake(rec("give m uppercase of this letetr ‚Ä¶¬£"), FIELDS)
    [span] = findings[0].metadata["spans"]
    assert span["text"] == "‚Ä¶¬£"
    assert span["codec"] == "mac_roman"
    assert span["repair"] == "…£"


def test_adjacent_repairs_do_not_fuse_into_a_second_layer():
    # One layer gives ’é. Read as Mac Roman again, that would be Armenian.
    findings = mojibake(rec("coups dâ€™Ã©tat"), FIELDS)
    assert findings[0].metadata["repaired"] == "coups d’état"
    assert findings[0].metadata["spans"][0]["layers"] == 1


def test_cp1252_right_quote():
    findings = mojibake(rec("I donâ€™t know"), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["repaired"] == "I don’t know"
    assert findings[0].metadata["codec"] == "cp1252"


def test_cp1252_undefined_byte_right_double_quote():
    # cp1252 has no character for 0x9D, so ” often survives as â€ plus U+009D.
    findings = mojibake(rec("he said â€œhelloâ€\x9d"), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["repaired"] == "he said “hello”"


def test_latin1_c1_controls():
    findings = mojibake(rec("donâ\u0080\u0099t"), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["repaired"] == "don’t"
    assert findings[0].metadata["codec"] == "latin-1"


def test_capital_a_circumflex_before_latin1_symbol():
    findings = mojibake(rec("Heat to 180Â°C"), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["repaired"] == "Heat to 180°C"


def test_mac_roman_square_root_pair_inside_word():
    # √∂ is also square root of partial, so it needs letters on both sides.
    findings = mojibake(rec("K√∂nnen Sie"), FIELDS)
    assert findings[0].metadata["repaired"] == "Können Sie"


def test_mac_roman_square_root_pair_with_other_evidence():
    findings = mojibake(rec("Jos√© habl√≥"), FIELDS)
    assert findings[0].metadata["repaired"] == "José habló"


def test_cp1252_chinese_greek_cyrillic():
    assert mojibake(rec("ä¸­æ–‡"), FIELDS)[0].metadata["repaired"] == "中文"
    assert mojibake(rec("10 Î¼m"), FIELDS)[0].metadata["repaired"] == "10 μm"
    assert mojibake(rec("ÐŸÑ€Ð¸Ð²ÐµÑ‚"), FIELDS)[0].metadata["repaired"] == "Привет"


def test_single_cjk_repair_needs_support():
    # Alone, one CJK character from three Latin-1 characters is too weak.
    assert mojibake(rec("the sign ä¸­ means middle"), FIELDS) == []
    findings = mojibake(rec("donâ€™t read ä¸­ as middle"), FIELDS)
    assert findings[0].metadata["repaired"] == "don’t read 中 as middle"


def test_answer_field_flagged():
    findings = mojibake(rec("Who sang Halo?", "Beyonc√©"), FIELDS)
    assert len(findings) == 1
    assert findings[0].metadata["field"] == "answer"
    assert findings[0].metadata["repaired"] == "Beyoncé"


def test_each_choice_checked():
    records = rec("Pick one", "B", choices=["plain", "caf√© au lait", "donâ€™t"])
    findings = mojibake(records, FIELDS)
    assert [(f.metadata["field"], f.metadata["choice_index"]) for f in findings] == [
        ("choices", 1),
        ("choices", 2),
    ]
    assert "choices[1]" in findings[0].explanation


def test_non_string_values_ignored():
    records = [{"q": None, "a": 3, "choices": "not a list"}]
    assert mojibake(records, FIELDS) == []


def test_severity():
    assert mojibake(rec("donâ€™t"), FIELDS)[0].severity == "low"
    assert mojibake(rec("q", "donâ€™t"), FIELDS)[0].severity == "medium"


# Legitimate text that must not be flagged.


@pytest.mark.parametrize(
    "text",
    [
        "A seleção brasileira venceu em São Paulo; não há dúvida.",
        "L’évolution du café à Paris—déjà vu « très » coûteux.",
        "coups d’état",
        "Discussion sur l’évolution",
        "Straße, Größe, „Äpfel“ über Österreich",
        "Der Politiker „Franz Josef Strauß“ ist der Namensgeber",
        "¿Dónde está el niño? ¡Mañana!",
        "中文测试，你好世界。",
        "日本語のテキスト",
        "SÃO PAULO e NÃO",
        "CHÂTEAU and ÂGE",
        "Ãgua",
        "¬p ∧ q",
        "lim x→∞ f(x) = ∞",
        "‚single low quote‘",
        "√π ≈ 1.772",
        "2√π and √∑ and √∂f and √∫",
        "x ≥ 0, ∑ a_i ≤ ∞, ±1",
        "the year at 26\u00a0°C in February",
        "PanamÃø Oeste",
        "Mary’s café",
        "Ångström and Ælfred and Øresund",
        "« un café\u00a0» et l’été\u00a0— dit-il",
        "„Ääh“, sagte er",
        "«SÍ» y «NO»",
    ],
)
def test_legitimate_text_not_flagged(text):
    assert mojibake(rec(text, text, choices=[text]), FIELDS) == []


# Real strings from sciknoweval: crystal cell volumes and areas in ångströms.
@pytest.mark.parametrize(
    "text",
    [
        "Volume: 157.67742978 Å³, Number of atoms: 12",
        "a surface area of 23.4 Å² per molecule",
        "Å³ is the unit",
    ],
)
def test_angstrom_with_a_superscript_is_a_unit_not_mojibake(text: str):
    assert mojibake(rec(text), FIELDS) == []


def test_angstrom_with_a_superscript_kept_beside_real_mojibake():
    findings = mojibake(rec("Volume 157 Å³ at 25 Â°C"), FIELDS)
    assert len(findings) == 1
    assert {span["text"] for span in findings[0].metadata["spans"]} == {"Å³", "Â°"}
