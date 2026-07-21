"""Stable routing and ordering for public practice cards."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


PRACTICE_DECK_CATEGORIES = (
    ("kanji_reading", "한자 읽기"),
    ("orthography", "표기"),
    ("word_formation", "단어 형성"),
    ("context_defined", "문맥 규정"),
    ("paraphrase", "유의 표현"),
    ("usage", "용법"),
    ("counter", "수량 표현"),
    ("date", "날짜"),
    ("month", "월"),
    ("weekday", "요일"),
)
PRACTICE_DECK_LEVELS = {
    "kanji_reading": ("N5", "N4", "N3", "N2", "N1"),
    "orthography": ("N5", "N4", "N3", "N2"),
    "word_formation": ("N2",),
    "context_defined": ("N5", "N4", "N3", "N2", "N1"),
    "paraphrase": ("N5", "N4", "N3", "N2", "N1"),
    "usage": ("N4", "N3", "N2", "N1"),
    "counter": ("N5",),
    "date": ("N5",),
    "month": ("N5",),
    "weekday": ("N5",),
}
PRACTICE_DECK_CATEGORY_BY_QUESTION_TYPE = {
    "kanji_reading": "kanji_reading",
    "orthography": "orthography",
    "word_formation": "word_formation",
    "context_defined": "context_defined",
    "paraphrase": "paraphrase",
    "usage": "usage",
    "counter_reading": "counter",
    "date_reading": "date",
    "month_reading": "month",
    "weekday_reading": "weekday",
}
PRACTICE_DECK_LABELS = dict(PRACTICE_DECK_CATEGORIES)
REFERENCE_MEMORY_CATEGORIES = frozenset({"counter", "date", "month", "weekday"})
LEXICAL_FORM_QUESTION_TYPES = frozenset(
    {"kanji_reading", "orthography", "word_formation"}
)
PRACTICE_ROOT_LABEL = "종합 실전"

_LEADING_NUMBER_RE = re.compile(r"^(?P<number>\d+)")
_COUNTER_CELL_RE = re.compile(r"matrix-r(?P<row>\d+)-c(?P<column>\d+)")
_WEEKDAY_ORDER = {
    "月曜日": 1,
    "火曜日": 2,
    "水曜日": 3,
    "木曜日": 4,
    "金曜日": 5,
    "土曜日": 6,
    "日曜日": 7,
}


class PracticeQuestionContractError(ValueError):
    """Raised when a resolved practice note cannot be routed into the deck."""


def practice_deck_key(question_type: str, jlpt_level: str) -> str:
    """Return the stable leaf deck key for one practice question."""
    category = PRACTICE_DECK_CATEGORY_BY_QUESTION_TYPE.get(question_type)
    if category is None or jlpt_level not in PRACTICE_DECK_LEVELS[category]:
        raise PracticeQuestionContractError(
            f"unsupported practice deck route: {question_type}/{jlpt_level}"
        )
    return f"practice:{category}:{jlpt_level}"


def practice_deck_name(question_type: str, jlpt_level: str) -> str:
    """Return the visible deck name for one practice question."""
    category = PRACTICE_DECK_CATEGORY_BY_QUESTION_TYPE.get(question_type)
    if category is None:
        raise PracticeQuestionContractError(
            f"unknown practice question type: {question_type}"
        )
    practice_deck_key(question_type, jlpt_level)
    if category in REFERENCE_MEMORY_CATEGORIES:
        return f"JLPT MAX덱::어휘::{jlpt_level}::{PRACTICE_DECK_LABELS[category]}"
    return (
        f"JLPT MAX덱::{PRACTICE_ROOT_LABEL}::어휘::{jlpt_level}::"
        f"{PRACTICE_DECK_LABELS[category]}"
    )


def practice_sort_key(question: Mapping[str, Any]) -> str:
    """Return a semantic Browser and fresh-card order for a practice note."""
    question_type = str(question.get("question_type", ""))
    question_id = str(question.get("question_id", ""))
    prompt = str(question.get("prompt_jp", ""))
    if not question_id:
        raise PracticeQuestionContractError("practice question lacks question_id")

    if question_type in LEXICAL_FORM_QUESTION_TYPES:
        lexical_prefix = f"lfq:{question_type}:"
        if (
            not question_id.startswith(lexical_prefix)
            or question_id == lexical_prefix
        ):
            raise PracticeQuestionContractError(
                f"lexical practice question id is invalid: {question_id}"
            )
        return question_id

    if question_type in {"date_reading", "month_reading"}:
        match = _LEADING_NUMBER_RE.match(prompt)
        if match is None:
            raise PracticeQuestionContractError(
                f"numbered practice prompt is invalid: {question_id}"
            )
        return f"{question_type}:{int(match.group('number')):03d}"

    if question_type == "weekday_reading":
        try:
            order = _WEEKDAY_ORDER[prompt]
        except KeyError as error:
            raise PracticeQuestionContractError(
                f"weekday practice prompt is invalid: {question_id}"
            ) from error
        return f"weekday_reading:{order:02d}"

    if question_type == "counter_reading":
        source_cells = question.get("source_cell_ids")
        source_page = question.get("source_page")
        if (
            not isinstance(source_cells, list)
            or len(source_cells) != 1
            or not isinstance(source_cells[0], str)
            or not isinstance(source_page, int)
        ):
            raise PracticeQuestionContractError(
                f"counter practice source is invalid: {question_id}"
            )
        match = _COUNTER_CELL_RE.search(source_cells[0])
        if match is None:
            raise PracticeQuestionContractError(
                f"counter practice route is invalid: {question_id}"
            )
        return (
            f"counter_reading:{int(match.group('row')):02d}:"
            f"{source_page:04d}:{int(match.group('column')):02d}"
        )

    if question_type in {"context_defined", "paraphrase", "usage"}:
        return f"expression:{question_id}"
    raise PracticeQuestionContractError(
        f"unsupported practice sort route: {question_type}/{question_id}"
    )
