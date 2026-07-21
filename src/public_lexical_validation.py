"""Validate approved lexical-form questions included in the public bundle."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

QUESTION_FIELDS = (
    "answer_jp",
    "answer_ko",
    "choice_notes_ko",
    "choices",
    "correct_index",
    "explanation_ko",
    "prompt_jp",
    "prompt_ko",
    "question_type",
    "source_reference_ids",
)
PROMPT_INSTRUCTION_BY_TYPE = {
    "kanji_reading": "밑줄 친 단어의 올바른 읽기를 고르세요.",
    "orthography": "밑줄 친 히라가나의 올바른 표기를 고르세요.",
    "word_formation": "빈칸에 들어갈 가장 알맞은 것을 고르세요.",
}
WORD_FORMATION_BLANK = "（　）"
WORD_FORMATION_RELATION_TYPES = frozenset(
    {"compound", "derivation", "prefix", "suffix"}
)
_JAPANESE_SENTENCE_ENDINGS = ("。", "！", "？")
_KANJI_RE = re.compile(r"[\u3007\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff々〆ヶ]")
_META_SURFACE_MARKS = frozenset({"～", "〜", "~"})
_COMMON_META_INSTRUCTIONS = (
    "選びなさい",
    "選んでください",
    "選んで下さい",
    "答えなさい",
    "答えてください",
    "正しいもの",
    "最も適切",
    "どれですか",
)
_META_INSTRUCTIONS_BY_TYPE = {
    "kanji_reading": ("読み方", "どう読む", "どう読み"),
    "orthography": ("表記を", "書き方", "漢字で"),
    "word_formation": (
        "付けて",
        "付ける",
        "加えて",
        "組み合わせ",
        "できる言葉",
        "作られる言葉",
        "成り立つ",
        "接頭辞",
        "接尾辞",
        "複合語",
        "派生語",
    ),
}
_KOREAN_SENTENCE_ENDINGS = (".", "!", "?")
_HANGUL_RE = re.compile(r"[가-힣]")
_JAPANESE_SCRIPT_RE = re.compile(
    r"[々〇〆〻ぁ-ゟァ-ヺー-ヿㇰ-ㇿ"
    r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\U0001aff0-\U0001afff\U0001b000-\U0001b122"
    r"\U00020000-\U0002fa1f\U00030000-\U000323af]"
)
_KATAKANA_WORD_RE = re.compile(r"^[ァ-ヺヽ-ヿ・ー]+$")
_HIRAGANA_READING_RE = re.compile(r"^[ぁ-ゖゝ-ゟ・ー]+$")
_GENERIC_CHOICE_NOTE_RE = re.compile(
    r"^(?:정답|오답)(?:(?:이|가)?\s*(?:아니다|아닙니다|이다|입니다))?[.!]?$"
)
_GENERIC_DIAGNOSIS_RE = re.compile(
    r"^[「『‘'\"].+[」』’'\"](?:은|는|이|가)?\s*"
    r"(?:잘못된|틀린|올바르지\s+않은)\s*"
    r"(?:읽기|표기|형태|선택지|답)(?:이|가)?\s*"
    r"(?:이다|입니다)?[.!]?$"
)
_SOURCE_PROVENANCE_PATTERNS = (
    re.compile(
        r"(?:해커스|다락원|파고다|네이버\s*사전|"
        r"동양(?:북스|문고|\s*N[1-5]|\s+자료)|"
        r"(?i:(?:hackers|dongyang|darakwon|pagoda)"
        r"(?:[-_\s]+n[1-5])?|naver[-_\s]?dict))"
    ),
    re.compile(r"동양의\s+(?:(?:\S+)\s+){0,3}자료"),
    re.compile(r"출판사\s*(?:자료|근거|출처|출전|단어장)"),
    re.compile(
        r"(?:제공(?:된)?|주어진)\s+"
        r"(?:(?:\S+)\s+){0,3}(?:자료|근거|출처|출전|단어장)"
        r".{0,120}(?:읽기|표기|표준|완성어|형성\s*요소|접두\s*요소|접미\s*요소)"
    ),
)
_LEXICAL_SOURCE_PROVENANCE_PATTERNS = (
    re.compile(r"(?:근거|출처|출전)\s+(?:표기|읽기|정보|내용)"),
    re.compile(
        r"(?:제공(?:된)?|주어진|제시된)\s+(?:(?:\S+)\s+){0,6}"
        r"(?:자료|근거|출처|출전|단어장|항목)"
        r"(?:에서|에서는|에|가|는|이|은|\s+모두)?"
        r".{0,180}(?:읽|표기|제시|확인|뒷받침|명시|기록|대응)"
    ),
    re.compile(
        r"(?:두|세|네|다섯|모든|양쪽|여러)(?:\s+N[1-5])?\s+"
        r"(?:제시\s+)?(?:어휘\s+)?(?:자료|근거|출처|출전|단어장|항목)"
        r"(?:\s+(?:자료|근거|출처|출전|항목))?"
        r"(?:\s+모두|가|는|이|은|에|에서|에서는)"
        r".{0,180}(?:읽|표기|제시|확인|뒷받침|명시|기록|대응)"
    ),
    re.compile(
        r"(?:이\s+)?(?:자료|근거|출처|출전|단어장|항목)"
        r"(?:\s+(?:자료|근거|출처|출전|어휘\s+항목|단어\s+항목|항목))?"
        r"(?:에서|에서는|에|가|는|이|은|의|와|과)"
        r".{0,180}(?:읽기|표기|제시|뒷받침|명시|기록|대응|"
        r"표준\s*(?:읽기|표기)|완성어|형성\s*요소|접두\s*요소|접미\s*요소)"
    ),
    re.compile(r"제시된\s+어휘에서.{0,120}(?:읽|표기|정답)"),
    re.compile(
        r"(?:이\s+)?(?:형성\s+)?근거(?:와|과|의|에서).{0,100}"
        r"(?:형성|구성|완성|접두|접미)"
    ),
    re.compile(r"(?:이\s+)?형성\s+근거(?:와|과|의|에서)"),
)
_READING_NOTE_MARKERS = (
    "읽",
    "음절",
    "음독",
    "훈독",
    "탁음",
    "장음",
    "촉음",
    "요음",
    "발음",
    "연탁",
)
_ORTHOGRAPHY_NOTE_MARKERS = (
    "표기",
    "한자",
    "글자",
    "문자",
    "동음",
    "비표준",
    "조합",
    "오기",
    "혼동",
    "문맥",
    "뜻",
    "의미",
)
_WORD_FORMATION_NOTE_MARKERS = (
    "넣",
    "치환",
    "완성",
    "단어",
    "표현",
    "성립",
    "비표준",
    "문맥",
    "문장",
    "상황",
    "자리",
    "뜻",
    "의미",
)


class LexicalFormQuestionContractError(ValueError):
    """Raised when a lexical-form model response violates the contract."""


def validate_learner_visible_korean_prose(
    value: str,
    *,
    field_name: str = "learner-visible Korean prose",
    lexical_provenance: bool = False,
) -> str:
    """Reject publisher/provenance scaffolding without banning ordinary nouns."""
    if not isinstance(value, str) or not value.strip():
        raise LexicalFormQuestionContractError(f"{field_name} is empty")
    normalized = unicodedata.normalize("NFKC", value)
    patterns = _SOURCE_PROVENANCE_PATTERNS
    if lexical_provenance:
        patterns = (*patterns, *_LEXICAL_SOURCE_PROVENANCE_PATTERNS)
    for pattern in patterns:
        if pattern.search(normalized) is not None:
            raise LexicalFormQuestionContractError(
                f"{field_name} exposes source provenance"
            )
    return value




def _strict_keys(value: Mapping[str, Any], expected: set[str] | frozenset[str], label: str) -> None:
    if set(value) != set(expected):
        raise LexicalFormQuestionContractError(f"{label} fields changed")




def _canonical_form(evidence: Mapping[str, Any]) -> tuple[str, str]:
    items = evidence.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise LexicalFormQuestionContractError(
            "lexical evidence must contain one canonical form"
        )
    surface = items[0].get("surface")
    reading = items[0].get("reading")
    if (
        not isinstance(surface, str)
        or not surface.strip()
        or surface != surface.strip()
        or not isinstance(reading, str)
        or not reading.strip()
        or reading != reading.strip()
    ):
        raise LexicalFormQuestionContractError("canonical lexical form is incomplete")
    return surface, reading


def _source_reference_ids(evidence: Mapping[str, Any]) -> list[str]:
    references = evidence.get("source_references")
    if not isinstance(references, list) or not references:
        raise LexicalFormQuestionContractError("lexical evidence lacks source references")
    result: list[str] = []
    for reference in references:
        if not isinstance(reference, dict):
            raise LexicalFormQuestionContractError("source reference must be an object")
        candidate_id = reference.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise LexicalFormQuestionContractError("source reference lacks candidate_id")
        result.append(candidate_id)
    if len(result) != len(set(result)):
        raise LexicalFormQuestionContractError("source references are duplicated")
    return result


def _canonical_meaning_variants(evidence: Mapping[str, Any]) -> set[str]:
    variants: set[str] = set()
    canonical: set[str] = set()
    covered_targets = evidence.get("covered_targets")
    if not isinstance(covered_targets, list) or not covered_targets:
        raise LexicalFormQuestionContractError("lexical evidence lacks covered targets")
    for target in covered_targets:
        if not isinstance(target, dict):
            raise LexicalFormQuestionContractError("covered target must be an object")
        canonical_value = target.get("canonical_meaning")
        if isinstance(canonical_value, str) and canonical_value.strip():
            canonical.add(unicodedata.normalize("NFKC", canonical_value).strip())
        for key in ("canonical_meaning", "meaning"):
            value = target.get(key)
            if isinstance(value, str) and value.strip():
                variants.add(unicodedata.normalize("NFKC", value).strip())
    if len(canonical) != 1:
        raise LexicalFormQuestionContractError(
            "lexical evidence lacks one canonical meaning"
        )
    return variants


def _canonical_forms(
    evidence: Mapping[str, Any], surface: str, reading: str
) -> list[tuple[str, str]]:
    raw = evidence.get("canonical_forms")
    if not isinstance(raw, list) or not raw:
        raise LexicalFormQuestionContractError(
            "canonical_forms must be a nonempty form array"
        )
    forms: list[tuple[str, str]] = []
    for form in raw:
        if not isinstance(form, dict) or set(form) != {"surface", "reading"}:
            raise LexicalFormQuestionContractError(
                "canonical form fields changed"
            )
        form_surface = form.get("surface")
        form_reading = form.get("reading")
        if (
            not isinstance(form_surface, str)
            or not form_surface.strip()
            or form_surface != form_surface.strip()
            or not isinstance(form_reading, str)
            or not form_reading.strip()
            or form_reading != form_reading.strip()
        ):
            raise LexicalFormQuestionContractError(
                "canonical form is incomplete"
            )
        forms.append((form_surface, form_reading))
    if len(forms) != len(set(forms)):
        raise LexicalFormQuestionContractError("canonical forms are duplicated")
    if (surface, reading) not in forms:
        raise LexicalFormQuestionContractError(
            "canonical forms omit the learner-visible form"
        )
    accepted_surfaces = evidence.get("accepted_surfaces")
    if accepted_surfaces is not None and accepted_surfaces != sorted(
        {form_surface for form_surface, _ in forms}
    ):
        raise LexicalFormQuestionContractError(
            "accepted surfaces do not match canonical forms"
        )
    accepted_readings = evidence.get("accepted_readings")
    if accepted_readings is not None and accepted_readings != sorted(
        {form_reading for _, form_reading in forms}
    ):
        raise LexicalFormQuestionContractError(
            "accepted readings do not match canonical forms"
        )
    return forms


def _katakana_surface_hiragana_reading(surface: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", surface)
    if _KATAKANA_WORD_RE.fullmatch(normalized) is None:
        return None
    reading = "".join(
        chr(ord(character) - 0x60)
        if "ァ" <= character <= "ヶ"
        else character
        for character in normalized
    )
    if (
        reading == normalized
        or _HIRAGANA_READING_RE.fullmatch(reading) is None
    ):
        return None
    return reading


def canonical_question_form(
    evidence: Mapping[str, Any],
) -> tuple[str, str]:
    """Return the usable surface/reading pair for one lexical question.

    Orthography evidence occasionally selects a Katakana surface as its own
    reading. Use its deterministic Hiragana transliteration as the displayed
    cue, whether or not the canonical inventory already records that reading.
    Other question types and genuinely same-surface/same-reading evidence
    retain their selected pair.
    """
    surface, reading = _canonical_form(evidence)
    _canonical_forms(evidence, surface, reading)
    if evidence.get("question_type") != "orthography" or surface != reading:
        return surface, reading
    hiragana_reading = _katakana_surface_hiragana_reading(surface)
    if hiragana_reading is not None:
        return surface, hiragana_reading
    return surface, reading


def _distinct_variants(
    evidence: Mapping[str, Any], surface: str, reading: str
) -> list[str]:
    forms = _canonical_forms(evidence, *_canonical_form(evidence))
    return sorted(
        {
            form_surface
            for form_surface, form_reading in forms
            if (
                form_reading == reading
                and form_surface != surface
                and form_surface != reading
            )
        }
    )


def _distinct_readings(
    evidence: Mapping[str, Any], surface: str, reading: str
) -> list[str]:
    forms = _canonical_forms(evidence, *_canonical_form(evidence))
    return sorted(
        {
            form_reading
            for form_surface, form_reading in forms
            if form_surface == surface and form_reading != reading
        }
    )


def _normalized_word_formation_proof(
    value: Mapping[str, Any],
) -> dict[str, str] | None:
    answer_surface = value.get("answer_surface")
    answer_component = value.get("answer_component")
    blanked_surface = value.get("blanked_surface")
    relation_type = value.get("relation_type")
    if (
        any(
            not isinstance(field_value, str)
            or not field_value
            or field_value != field_value.strip()
            for field_value in (
                answer_surface,
                answer_component,
                blanked_surface,
                relation_type,
            )
        )
    ):
        return None
    assert isinstance(answer_surface, str)
    assert isinstance(answer_component, str)
    assert isinstance(blanked_surface, str)
    assert isinstance(relation_type, str)
    if (
        relation_type not in WORD_FORMATION_RELATION_TYPES
        or blanked_surface.count(WORD_FORMATION_BLANK) != 1
        or blanked_surface.replace(WORD_FORMATION_BLANK, answer_component)
        != answer_surface
        or answer_component == answer_surface
    ):
        return None
    return {
        "answer_surface": answer_surface,
        "answer_component": answer_component,
        "blanked_surface": blanked_surface,
        "relation_type": relation_type,
    }


def word_formation_proof(
    evidence: Mapping[str, Any],
) -> dict[str, str] | None:
    """Return one hash-bound, structurally proven word-formation operation."""
    items = evidence.get("items")
    if (
        not isinstance(items, list)
        or len(items) != 1
        or not isinstance(items[0], dict)
        or not isinstance(items[0].get("surface"), str)
    ):
        return None
    canonical_surface = items[0]["surface"]
    lexical = evidence.get("word_formation_evidence")
    if isinstance(lexical, dict) and lexical.get("deterministic") is True:
        proof = _normalized_word_formation_proof(lexical)
        if proof is not None and proof["answer_surface"] == canonical_surface:
            return proof
    reviewed = evidence.get("reviewed_word_formation_resolution")
    if isinstance(reviewed, dict):
        if (
            reviewed.get("status") == "approved"
            and reviewed.get("evidence_hash") == evidence.get("evidence_hash")
        ):
            proof = _normalized_word_formation_proof(reviewed)
            if proof is not None and proof["answer_surface"] == canonical_surface:
                return proof
    return None


def _word_formation_sources_are_n2(evidence: Mapping[str, Any]) -> bool:
    covered_targets = evidence.get("covered_targets")
    return (
        evidence.get("jlpt_level") == "N2"
        and isinstance(covered_targets, list)
        and bool(covered_targets)
        and all(
            isinstance(target, dict)
            and target.get("question_type") == "word_formation"
            and target.get("jlpt_level") == "N2"
            for target in covered_targets
        )
    )




def _deterministic_block_reason(
    evidence: Mapping[str, Any],
    *,
    approved_formation_proof: Mapping[str, str] | None = None,
) -> str | None:
    surface, reading = canonical_question_form(evidence)
    question_type = evidence.get("question_type")
    if surface[:1] in _META_SURFACE_MARKS or surface[-1:] in _META_SURFACE_MARKS:
        return "source_error"
    if question_type == "kanji_reading":
        if _KANJI_RE.search(surface) is None:
            return "kana_default"
    if question_type == "orthography":
        if surface == reading:
            return "kana_default"
    if question_type == "word_formation":
        if not _word_formation_sources_are_n2(evidence):
            return "level_mismatch"
        if (
            approved_formation_proof is None
            and word_formation_proof(evidence) is None
        ):
            return "insufficient_lexical_evidence"
    return None




def _is_single_japanese_sentence(value: str) -> bool:
    return (
        value == value.strip()
        and "\n" not in value
        and value.endswith(_JAPANESE_SENTENCE_ENDINGS)
        and sum(value.count(ending) for ending in _JAPANESE_SENTENCE_ENDINGS) == 1
    )


def _is_single_korean_sentence(value: str) -> bool:
    return (
        value == value.strip()
        and "\n" not in value
        and value.endswith(_KOREAN_SENTENCE_ENDINGS)
        and sum(value.count(ending) for ending in _KOREAN_SENTENCE_ENDINGS) == 1
        and _HANGUL_RE.search(value) is not None
    )


def _contains_meta_instruction(value: str, question_type: str) -> bool:
    phrases = (*_COMMON_META_INSTRUCTIONS, *_META_INSTRUCTIONS_BY_TYPE[question_type])
    return any(phrase in value for phrase in phrases)


def _has_one_marked_target(value: str, target: str) -> bool:
    marker = f"【{target}】"
    context = value.replace(marker, "", 1).rstrip("。！？").strip()
    return (
        value.count("【") == 1
        and value.count("】") == 1
        and value.count(marker) == 1
        and value.count(target) == 1
        and len(context) >= 2
    )


def _is_component_choice(value: str) -> bool:
    return bool(value) and all(
        unicodedata.category(character)[0] in {"L", "N"} for character in value
    )


def _word_formation_choices_are_components(
    answer_surface: str,
    blanked_surface: str,
    choices: Sequence[str],
) -> bool:
    prefix, suffix = blanked_surface.split(WORD_FORMATION_BLANK)
    for choice in choices:
        if choice == answer_surface:
            return False
        if prefix and suffix and choice.startswith(prefix) and choice.endswith(suffix):
            return False
        if prefix and not suffix and choice.startswith(prefix):
            return False
        if suffix and not prefix and choice.endswith(suffix):
            return False
    return True


def _contains_any(value: str, markers: Sequence[str]) -> bool:
    return any(marker in value for marker in markers)


def _quotes_exact_choice(note: str, choice: str) -> bool:
    return any(
        opening + choice + closing in note
        for opening, closing in (
            ("「", "」"),
            ("『", "』"),
            ("‘", "’"),
            ("'", "'"),
            ('"', '"'),
        )
    )


def _validate_prompt_translation(
    prompt_ko: str,
    question_type: str,
) -> None:
    if (
        not _is_single_korean_sentence(prompt_ko)
        or prompt_ko in PROMPT_INSTRUCTION_BY_TYPE.values()
    ):
        raise LexicalFormQuestionContractError(
            "prompt_ko must be a natural Korean sentence translation"
        )
    if question_type == "word_formation":
        if prompt_ko.count(WORD_FORMATION_BLANK) != 1:
            raise LexicalFormQuestionContractError(
                "word formation Korean translation must preserve the blank"
            )
    elif WORD_FORMATION_BLANK in prompt_ko:
        raise LexicalFormQuestionContractError(
            "non-formation Korean translation contains a blank"
        )
    normalized_prompt = unicodedata.normalize("NFKC", prompt_ko)
    if _JAPANESE_SCRIPT_RE.search(normalized_prompt) is not None:
        raise LexicalFormQuestionContractError(
            "Korean translation contains Japanese script"
        )
    if "【" in prompt_ko or "】" in prompt_ko:
        marked_targets = re.findall(r"【([^【】]+)】", prompt_ko)
        if (
            not marked_targets
            or len(marked_targets) != prompt_ko.count("【")
            or len(marked_targets) != prompt_ko.count("】")
        ):
            raise LexicalFormQuestionContractError(
                "Korean translation has an invalid marked target"
            )
        if any(
            _HANGUL_RE.search(target) is None
            for target in marked_targets
        ):
            raise LexicalFormQuestionContractError(
                "Korean translation marked target must be translated into Hangul"
            )


def _validate_choice_notes(
    *,
    question_type: str,
    surface: str,
    reading: str,
    choices: Sequence[str],
    correct_index: int,
    notes: Sequence[str],
    formation_proof: Mapping[str, str] | None,
) -> None:
    for index, (choice, note) in enumerate(zip(choices, notes, strict=True)):
        validate_learner_visible_korean_prose(
            note,
            field_name=f"choice_notes_ko[{index}]",
            lexical_provenance=True,
        )
        if (
            _GENERIC_CHOICE_NOTE_RE.fullmatch(note.strip()) is not None
            or _GENERIC_DIAGNOSIS_RE.fullmatch(note.strip()) is not None
        ):
            raise LexicalFormQuestionContractError("choice note is generic")
        if not _quotes_exact_choice(note, choice):
            raise LexicalFormQuestionContractError(
                "choice note does not quote its exact choice"
            )

        if question_type == "kanji_reading":
            if not _contains_any(note, _READING_NOTE_MARKERS):
                raise LexicalFormQuestionContractError(
                    "reading choice note lacks a pronunciation diagnosis"
                )
            if index == correct_index and (surface not in note or "읽" not in note):
                raise LexicalFormQuestionContractError(
                    "correct reading note lacks the written form and reading relation"
                )
        elif question_type == "orthography":
            if not _contains_any(note, _ORTHOGRAPHY_NOTE_MARKERS):
                raise LexicalFormQuestionContractError(
                    "orthography choice note lacks a written-form diagnosis"
                )
            if index == correct_index and (reading not in note or "표기" not in note):
                raise LexicalFormQuestionContractError(
                    "correct orthography note lacks the reading and written form relation"
                )
        elif question_type == "word_formation":
            if formation_proof is None:
                raise LexicalFormQuestionContractError(
                    "word formation choice note lacks a formation proof"
                )
            substituted_surface = formation_proof["blanked_surface"].replace(
                WORD_FORMATION_BLANK,
                choice,
            )
            if substituted_surface not in note or not _contains_any(
                note, _WORD_FORMATION_NOTE_MARKERS
            ):
                raise LexicalFormQuestionContractError(
                    "word formation choice note lacks the actual substitution result"
                )
        else:
            raise LexicalFormQuestionContractError(
                "unsupported lexical question type"
            )


def _validate_explanation(
    *,
    question_type: str,
    surface: str,
    reading: str,
    answer_jp: str,
    explanation_ko: str,
    formation_proof: Mapping[str, str] | None,
) -> None:
    validate_learner_visible_korean_prose(
        explanation_ko,
        field_name="explanation_ko",
        lexical_provenance=True,
    )
    if question_type == "kanji_reading":
        if (
            surface not in explanation_ko
            or reading not in explanation_ko
            or not _contains_any(explanation_ko, ("문맥", "뜻", "의미"))
            or "읽" not in explanation_ko
        ):
            raise LexicalFormQuestionContractError(
                "kanji reading explanation lacks meaning and reading structure"
            )
    elif question_type == "orthography":
        if (
            reading not in explanation_ko
            or surface not in explanation_ko
            or not _contains_any(explanation_ko, ("문맥", "뜻", "의미"))
            or "표기" not in explanation_ko
        ):
            raise LexicalFormQuestionContractError(
                "orthography explanation lacks meaning and written-form structure"
            )
    elif question_type == "word_formation":
        if (
            formation_proof is None
            or answer_jp not in explanation_ko
            or formation_proof["answer_surface"] not in explanation_ko
            or not _contains_any(explanation_ko, ("뜻", "의미"))
            or not _contains_any(explanation_ko, ("문맥", "문장", "상황"))
        ):
            raise LexicalFormQuestionContractError(
                "word formation explanation lacks completion, meaning, and context"
            )
    else:
        raise LexicalFormQuestionContractError("unsupported lexical question type")


def _validate_question(
    value: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    approved_formation_proof: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    _strict_keys(value, set(QUESTION_FIELDS), "final question")
    question_type = value.get("question_type")
    if question_type != evidence.get("question_type"):
        raise LexicalFormQuestionContractError("question type changed")
    prompt_jp = value.get("prompt_jp")
    prompt_ko = value.get("prompt_ko")
    choices = value.get("choices")
    correct_index = value.get("correct_index")
    answer_jp = value.get("answer_jp")
    answer_ko = value.get("answer_ko")
    explanation_ko = value.get("explanation_ko")
    choice_notes_ko = value.get("choice_notes_ko")
    source_reference_ids = value.get("source_reference_ids")
    if (
        not isinstance(prompt_jp, str)
        or not prompt_jp.strip()
        or not isinstance(prompt_ko, str)
        or not prompt_ko.strip()
        or not isinstance(choices, list)
        or len(choices) != 4
        or any(not isinstance(choice, str) or not choice.strip() for choice in choices)
        or len({unicodedata.normalize("NFKC", choice).strip() for choice in choices}) != 4
        or not isinstance(correct_index, int)
        or isinstance(correct_index, bool)
        or not 0 <= correct_index < 4
        or not isinstance(answer_jp, str)
        or not answer_jp.strip()
        or not isinstance(answer_ko, str)
        or not answer_ko.strip()
        or not isinstance(explanation_ko, str)
        or not explanation_ko.strip()
        or not isinstance(choice_notes_ko, list)
        or len(choice_notes_ko) != 4
        or any(not isinstance(note, str) or not note.strip() for note in choice_notes_ko)
        or not isinstance(source_reference_ids, list)
        or any(not isinstance(item, str) or not item for item in source_reference_ids)
    ):
        raise LexicalFormQuestionContractError("proposed lexical question is incomplete")
    if answer_jp != choices[correct_index]:
        raise LexicalFormQuestionContractError("answer does not match correct choice")
    expected_references = _source_reference_ids(evidence)
    if source_reference_ids != expected_references:
        raise LexicalFormQuestionContractError("source reference binding changed")

    surface, reading = canonical_question_form(evidence)
    formation_proof = (
        approved_formation_proof or word_formation_proof(evidence)
        if question_type == "word_formation"
        else None
    )
    block_reason = _deterministic_block_reason(
        evidence,
        approved_formation_proof=formation_proof,
    )
    if block_reason is not None:
        raise LexicalFormQuestionContractError(
            f"lexical evidence requires block: {block_reason}"
        )
    validate_learner_visible_korean_prose(
        prompt_ko,
        field_name="prompt_ko",
    )
    validate_learner_visible_korean_prose(
        answer_ko,
        field_name="answer_ko",
        lexical_provenance=True,
    )
    _validate_prompt_translation(
        prompt_ko,
        str(question_type),
    )
    if question_type == "kanji_reading":
        accepted_alternatives = {
            unicodedata.normalize("NFKC", value)
            for value in _distinct_readings(evidence, surface, reading)
        }
        normalized_choices = {
            unicodedata.normalize("NFKC", choice) for choice in choices
        }
        if accepted_alternatives.intersection(normalized_choices):
            raise LexicalFormQuestionContractError(
                "reading choices include an accepted alternative"
            )
        meaning_variants = _canonical_meaning_variants(evidence)
        normalized_front = unicodedata.normalize("NFKC", prompt_jp)
        if (
            answer_jp != reading
            or not _has_one_marked_target(prompt_jp, surface)
            or reading in prompt_jp
            or reading in prompt_ko
            or any(meaning in normalized_front for meaning in meaning_variants)
            or not _is_single_japanese_sentence(prompt_jp)
            or _contains_meta_instruction(prompt_jp, question_type)
        ):
            raise LexicalFormQuestionContractError(
                "kanji reading is not canonical or leaks the answer"
            )
    elif question_type == "orthography":
        accepted_alternatives = {
            unicodedata.normalize("NFKC", value)
            for value in _distinct_variants(evidence, surface, reading)
        }
        normalized_choices = {
            unicodedata.normalize("NFKC", choice) for choice in choices
        }
        if accepted_alternatives.intersection(normalized_choices):
            raise LexicalFormQuestionContractError(
                "orthography choices include an accepted alternative"
            )
        if (
            answer_jp != surface
            or not _has_one_marked_target(prompt_jp, reading)
            or surface in prompt_jp
            or surface in prompt_ko
            or not _is_single_japanese_sentence(prompt_jp)
            or _contains_meta_instruction(prompt_jp, question_type)
        ):
            raise LexicalFormQuestionContractError(
                "orthography is not the sole canonical written answer"
            )
    elif question_type == "word_formation":
        if (
            formation_proof is None
            or prompt_jp.count(WORD_FORMATION_BLANK) != 1
            or not _is_single_japanese_sentence(prompt_jp)
            or _contains_meta_instruction(prompt_jp, question_type)
            or any(mark in prompt_jp for mark in ("【", "】", "「", "」", "『", "』"))
            or not all(_is_component_choice(choice) for choice in choices)
        ):
            raise LexicalFormQuestionContractError(
                "word formation lacks a contextual component answer"
            )
        formed_surface = formation_proof["answer_surface"]
        answer_component = formation_proof["answer_component"]
        blanked_surface = formation_proof["blanked_surface"]
        completed_prompt = prompt_jp.replace(WORD_FORMATION_BLANK, answer_jp)
        if (
            answer_jp != answer_component
            or answer_component in prompt_ko
            or prompt_jp.count(blanked_surface) != 1
            or not _word_formation_choices_are_components(
                formed_surface,
                blanked_surface,
                choices,
            )
            or completed_prompt.count(formed_surface) != 1
        ):
            raise LexicalFormQuestionContractError(
                "word formation lacks a bound boundary component"
            )
    else:
        raise LexicalFormQuestionContractError("unsupported lexical question type")
    _validate_explanation(
        question_type=str(question_type),
        surface=surface,
        reading=reading,
        answer_jp=answer_jp,
        explanation_ko=explanation_ko,
        formation_proof=formation_proof,
    )
    _validate_choice_notes(
        question_type=str(question_type),
        surface=surface,
        reading=reading,
        choices=choices,
        correct_index=correct_index,
        notes=choice_notes_ko,
        formation_proof=formation_proof,
    )
    return {
        "answer_jp": answer_jp,
        "answer_ko": answer_ko,
        "choice_notes_ko": list(choice_notes_ko),
        "choices": list(choices),
        "correct_index": correct_index,
        "explanation_ko": explanation_ko,
        "prompt_jp": prompt_jp,
        "prompt_ko": prompt_ko,
        "question_type": question_type,
        "source_reference_ids": list(source_reference_ids),
    }


def validate_approved_lexical_question(
    question: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Revalidate one approved learner-visible question at a final boundary."""
    _strict_keys(question, set(QUESTION_FIELDS), "approved lexical question")
    adapted_evidence, approved_formation_proof = _approved_question_evidence(
        question,
        evidence,
    )
    return _validate_question(
        question,
        adapted_evidence,
        approved_formation_proof=approved_formation_proof,
    )


def _approved_question_evidence(
    question: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str] | None]:
    """Adapt either resolver evidence or the smaller frozen approved shape."""
    if "items" in evidence:
        return dict(evidence), None

    question_type = question.get("question_type")
    if question_type != evidence.get("question_type"):
        raise LexicalFormQuestionContractError(
            "approved lexical question type changed"
        )
    covered_targets = evidence.get("covered_targets")
    if not isinstance(covered_targets, list) or not covered_targets:
        raise LexicalFormQuestionContractError(
            "approved lexical question lacks covered targets"
        )
    canonical_inventory: set[tuple[str, str]] | None = None
    for target in covered_targets:
        if not isinstance(target, dict):
            raise LexicalFormQuestionContractError(
                "approved lexical covered target changed"
            )
        forms = target.get("canonical_forms")
        if not isinstance(forms, list) or not forms:
            raise LexicalFormQuestionContractError(
                "approved lexical target lacks canonical forms"
            )
        target_inventory: set[tuple[str, str]] = set()
        for form in forms:
            if not isinstance(form, dict) or set(form) != {"surface", "reading"}:
                raise LexicalFormQuestionContractError(
                    "approved lexical canonical form changed"
                )
            surface = form.get("surface")
            reading = form.get("reading")
            if (
                not isinstance(surface, str)
                or not surface.strip()
                or surface != surface.strip()
                or not isinstance(reading, str)
                or not reading.strip()
                or reading != reading.strip()
            ):
                raise LexicalFormQuestionContractError(
                    "approved lexical canonical form is incomplete"
                )
            target_inventory.add((surface, reading))
        if len(target_inventory) != len(forms):
            raise LexicalFormQuestionContractError(
                "approved lexical canonical forms are duplicated"
            )
        if canonical_inventory is None:
            canonical_inventory = target_inventory
        elif target_inventory != canonical_inventory:
            raise LexicalFormQuestionContractError(
                "approved lexical canonical inventories disagree"
            )
    if canonical_inventory is None:
        raise LexicalFormQuestionContractError(
            "approved lexical canonical inventory is empty"
        )
    canonical_forms = [
        {"surface": surface, "reading": reading}
        for surface, reading in sorted(canonical_inventory)
    ]

    prompt_jp = question.get("prompt_jp")
    answer_jp = question.get("answer_jp")
    if not isinstance(prompt_jp, str) or not isinstance(answer_jp, str):
        raise LexicalFormQuestionContractError(
            "approved lexical question answer changed"
        )
    adapted = dict(evidence)
    adapted["canonical_forms"] = canonical_forms
    approved_formation_proof: dict[str, str] | None = None
    if question_type in {"kanji_reading", "orthography"}:
        marked_targets = re.findall(r"【([^【】]+)】", prompt_jp)
        if len(marked_targets) != 1:
            raise LexicalFormQuestionContractError(
                "approved lexical prompt target changed"
            )
        if question_type == "kanji_reading":
            surface, reading = marked_targets[0], answer_jp
        else:
            surface, reading = answer_jp, marked_targets[0]
        derived_katakana_reading = (
            question_type == "orthography"
            and (surface, surface) in canonical_inventory
            and _katakana_surface_hiragana_reading(surface) == reading
        )
        if (
            (surface, reading) not in canonical_inventory
            and not derived_katakana_reading
        ):
            raise LexicalFormQuestionContractError(
                "approved lexical answer is not canonical"
            )
        if derived_katakana_reading:
            reading = surface
    elif question_type == "word_formation":
        formed_surface = evidence.get("formed_surface")
        formed_reading = evidence.get("formed_reading")
        if (
            not isinstance(formed_surface, str)
            or not formed_surface
            or not isinstance(formed_reading, str)
            or not formed_reading
            or (formed_surface, formed_reading) not in canonical_inventory
        ):
            raise LexicalFormQuestionContractError(
                "approved word formation surface changed"
            )
        choices = question.get("choices")
        if not isinstance(choices, list) or any(
            not isinstance(choice, str) or not choice for choice in choices
        ):
            raise LexicalFormQuestionContractError(
                "approved word formation choices changed"
            )
        matching_candidates = {
            (choice, candidate)
            for choice in choices
            for index in range(len(formed_surface))
            if formed_surface.startswith(choice, index)
            for candidate in (
                formed_surface[:index]
                + WORD_FORMATION_BLANK
                + formed_surface[index + len(choice) :],
            )
            if prompt_jp.count(candidate) == 1
        }
        if len(matching_candidates) != 1:
            raise LexicalFormQuestionContractError(
                "approved word formation boundary is ambiguous"
            )
        answer_component, blanked_surface = next(iter(matching_candidates))
        if answer_component != answer_jp:
            raise LexicalFormQuestionContractError(
                "approved word formation answer changed"
            )
        approved_formation_proof = {
            "answer_component": answer_component,
            "answer_surface": formed_surface,
            "blanked_surface": blanked_surface,
        }
        surface, reading = formed_surface, formed_reading
    else:
        raise LexicalFormQuestionContractError(
            "unsupported approved lexical question type"
        )
    adapted["items"] = [{"surface": surface, "reading": reading}]
    return adapted, approved_formation_proof
