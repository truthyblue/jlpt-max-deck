#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""Build and import-verify an APKG from validated public bundle inputs."""

from __future__ import annotations

import copy
import hashlib
import html
import json
import os
import platform
import re
import shutil
import sys
import unicodedata
import wave
import zipfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, Protocol

from anki.collection import Collection
from anki.cards import CardId
from anki.consts import CardQueue, CardType
from anki.decks import DEFAULT_DECK_CONF_ID, DeckConfigId, DeckId
from anki.exporting import AnkiPackageExporter
from anki.import_export_pb2 import ImportAnkiPackageRequest
from anki.models import NotetypeDict, NotetypeId

from public_vocabulary_rendering import (
    AUDIO_INTERACTION,
    AUDIO_FRONT as BASE_AUDIO_FRONT,
    BACK as BASE_VOCABULARY_BACK,
    CSS as BASE_VOCABULARY_CSS,
    FRONT as BASE_VOCABULARY_FRONT,
    SOURCE_DISPLAY_NAMES,
    example_display_html,
    kanji_details_html,
)
from public_input_contract import (
    CONTENT_STAGE_ID,
    CONTENT_STAGE_MANIFEST,
    CONTENT_SUMMARY,
    DECK_LAYOUT,
    KANJI_NOTES,
    MEDIA_DIR,
    MEDIA_INVENTORY,
    MEDIA_JOBS,
    MEDIA_STAGE_ID,
    MEDIA_STAGE_MANIFEST,
    MEDIA_SUMMARY,
    PRACTICE_QUESTION_NOTES,
    REFERENCE_TABLE_NOTES,
    VOCABULARY_NOTES,
)
from public_kanji_rendering import (
    KANJI_CARD_CSS,
    kanji_display_html,
    kanji_reference_html,
    linked_vocabulary_html,
)
from public_hashing import sha256_file, sha256_json
from public_media import (
    MP3_MAX_ENCODER_PADDING_SAMPLES,
    MediaCodecError,
    inspect_cbr_mp3,
)
from public_lexical_validation import (
    QUESTION_FIELDS as LEXICAL_QUESTION_FIELDS,
    LexicalFormQuestionContractError,
    validate_approved_lexical_question,
    validate_learner_visible_korean_prose,
)
from public_ruby import (
    kanji_only_ruby_html,
    plain_japanese,
    safe_ruby_html,
)
from public_practice_contract import (
    PRACTICE_DECK_CATEGORIES,
    PRACTICE_DECK_LABELS,
    PRACTICE_DECK_LEVELS,
    PRACTICE_ROOT_LABEL,
    REFERENCE_MEMORY_CATEGORIES,
    practice_deck_key,
    practice_deck_name,
    practice_sort_key,
)
from public_release import (
    PRODUCT_VERSION,
    RELEASE_MANIFEST,
    RELEASE_NOTES,
    UPDATE_REPORT_JSON,
    UPDATE_REPORT_TEXT,
    package_name,
    write_release_artifacts,
)
from public_study_rendering import (
    STUDY_FEATURE_CSS,
    VOCABULARY_STUDY_SECTIONS,
    related_words_html,
    study_priority_html,
    usage_details_html,
    word_formation_html,
)
HONORIFIC_BADGE_LABELS = ("존경어", "겸양어", "정중어")
STYLE_BADGE_LABELS = (
    "격식", "문어", "구어", "친근어", "남성어", "여성어", "아동어", "간사이 방언",
)
MARKED_BADGE_LABELS = ("속어", "비속어", "비하어", "익살", "구식", "고어", "시어")
DOMAIN_BADGE_LABELS = (
    "의학", "항공", "스포츠", "생명과학", "불교", "경제·경영", "게임", "화학",
    "컴퓨터", "전기·전자", "수학", "지구과학", "언어학", "법률", "논리", "음악",
    "철학", "물리", "인쇄",
)
PARTIAL_LABEL_SUFFIX = "(일부 뜻)"


ROOT = Path(__file__).resolve().parents[1]
CODE_PATHS = (
    "src/public_apkg_builder.py",
    "src/public_hashing.py",
    "src/public_input_contract.py",
    "src/public_vocabulary_rendering.py",
    "src/public_kanji_rendering.py",
    "src/public_lexical_validation.py",
    "src/public_media.py",
    "src/public_practice_contract.py",
    "src/public_release.py",
    "src/public_ruby.py",
    "src/public_study_rendering.py",
)

PRODUCT_NAME = "JLPT MAX덱"
PACKAGE_NAME = package_name(PRODUCT_VERSION)
STAGE_ID = "09e-apkg"
STAGE_MANIFEST = f"manifests/{STAGE_ID}.json"
BUILD_REPORT = "build-report.json"
LOGICAL_MANIFEST = "apkg-logical-manifest.json"
RENDERED_SAMPLE_INDEX = "rendered-samples/index.json"
RENDERED_SAMPLE_STEM_MAX_LENGTH = 120
LOGICAL_MANIFEST_SCHEMA_VERSION = 3
APKG_POLICY_VERSION = "closed-apkg-build"
SAMPLE_RATE = 44100
MP3_BITRATE_KBPS = 128
AUDIO_SUFFIXES = (".wav", ".mp3")
HTML_AUTOPLAY_WORD_SCOPE_RE = re.compile(
    r'<[A-Za-z][^<>]*\bdata-audio-autoplay="word"[^<>]*>'
)
ANKI_VERSION = package_version("anki")
LEVELS = ("N5", "N4", "N3", "N2", "N1")
_KANJI_CHARACTER_RE = re.compile(
    r"[\u3007\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff々〆ヶ]"
)
_KANA_ONLY_RE = re.compile(r"^[\u3040-\u30ffー・･～〜~()（）]+$")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_CONTEXT_ANNOTATION_CHARACTERS = frozenset("()（）[]［］【】")
_LONG_VOWEL_BY_HIRAGANA = {
    **{character: "あ" for character in "ぁあかがさざただなはばぱまゃやらゎわ"},
    **{character: "い" for character in "ぃいきぎしじちぢにひびぴみりゐ"},
    **{character: "う" for character in "ぅうくぐすずつづぬふぶぷむゅゆるゔ"},
    **{character: "え" for character in "ぇえけげせぜてでねへべぺめれゑ"},
    **{character: "お" for character in "ぉおこごそぞとどのほぼぽもょよろを"},
}
EXPECTED_REFERENCE_PRACTICE_NOTES = 215
EXPECTED_REFERENCE_TABLE_NOTES = 9
EXPECTED_KANJI_NOTES = 2337
EXPECTED_KANJI_STATIC_MEDIA = 14

VOCABULARY_KIND = "vocabulary"
PRACTICE_QUESTION_KIND = "practice_question"
REFERENCE_TABLE_KIND = "reference_table"
KANJI_KIND = "kanji"
VOCABULARY_NOTETYPE = f"{PRODUCT_NAME} 어휘"
PRACTICE_QUESTION_NOTETYPE = f"{PRODUCT_NAME} 어휘문제"
REFERENCE_TABLE_NOTETYPE = f"{PRODUCT_NAME} 참조표"
KANJI_NOTETYPE = f"{PRODUCT_NAME} 일상무따"
VOCABULARY_TEMPLATE = "어휘"
AUDIO_TEMPLATE = "음성"
PRACTICE_QUESTION_TEMPLATE = "어휘문제"
REFERENCE_TABLE_TEMPLATE = "참조표"
KANJI_TEMPLATE = "한자"
HIRAGANA_FORM_TEMPLATE = "어휘(히라가나)"
HIRAGANA_FORM_POLICY_VERSION = "learner-hiragana-form-card-v1"

VOCABULARY_FIELDS = (
    "EntryID",
    "Word",
    "VocabularyContext",
    "Reading",
    "Meaning",
    "PartOfSpeech",
    "KanjiDetails",
    "MeaningSource",
    "JLPT",
    "Publishers",
    "CanonicalRecordHash",
    "WordAudio",
    "WordAudioFile",
    *(
        f"Example{index}{suffix}"
        for index in range(1, 5)
        for suffix in (
            "JP",
            "Reading",
            "KO",
            "Sense",
            "Audio",
            "Source",
            "SourceID",
        )
    ),
    "UsageRegister",
    "ConjugationDetails",
    "StudyPriority",
    "UsageDetails",
    "WordFormationDetails",
    "RelatedWords",
    "WordJLPT",
    "HiraganaWord",
    "HiraganaContext",
)
PRACTICE_QUESTION_FIELDS = (
    "QuestionID",
    "SortKey",
    "JLPT",
    "QuestionType",
    "QuestionLabel",
    "Instruction",
    "PromptJP",
    "PromptKO",
    "ChoicesHTML",
    "AnswerJP",
    "AnswerKO",
    "ExplanationHTML",
    "Source",
    "SourcePage",
    "SourceReferenceID",
    "AnswerAudio",
    "PromptRuby",
    "PromptKORuby",
    "ChoicesRubyHTML",
    "AnswerRuby",
    "AnswerKORuby",
    "ExplanationRubyHTML",
)
REFERENCE_TABLE_FIELDS = (
    "ReferenceID",
    "Title",
    "PartLabel",
    "JLPT",
    "TableKind",
    "TableHTML",
    "Source",
    "SourcePage",
)
KANJI_FIELDS = (
    "KanjiID",
    "Volume",
    "Unit",
    "Theme",
    "GlyphHTML",
    "Meaning",
    "KanjiReference",
    "LinkedVocabulary",
    "SourceFingerprint",
    "SortKey",
)


def _stable_id(label: str) -> int:
    digest = hashlib.sha256(f"jlpt-max-deck-v2:{label}".encode()).digest()
    return (int.from_bytes(digest[:8], "big") & ((1 << 62) - 1)) + 1_000_000_000_000


def _normalize_form(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.replace("〜", "～").replace("~", "～")
    return re.sub(r"\s+", "", normalized).strip()


def _is_kana_only(value: str) -> bool:
    return bool(_KANA_ONLY_RE.fullmatch(_normalize_form(value)))


def _reading_equivalence_key(value: str) -> str:
    hiragana = "".join(
        chr(ord(character) - 0x60)
        if "ァ" <= character <= "ヶ"
        else character
        for character in _normalize_form(value)
    )
    expanded: list[str] = []
    for character in hiragana:
        if character == "ー" and expanded:
            expanded.append(
                _LONG_VOWEL_BY_HIRAGANA.get(expanded[-1], character)
            )
        else:
            expanded.append(character)
    return "".join(expanded)


NOTETYPE_IDS: dict[str, NotetypeId] = {
    VOCABULARY_KIND: NotetypeId(_stable_id("notetype:vocabulary")),
    PRACTICE_QUESTION_KIND: NotetypeId(
        _stable_id("notetype:practice_question")
    ),
    REFERENCE_TABLE_KIND: NotetypeId(_stable_id("notetype:reference_table")),
    KANJI_KIND: NotetypeId(_stable_id("notetype:kanji")),
}
TEMPLATE_IDS = {
    VOCABULARY_TEMPLATE: _stable_id("template:vocabulary"),
    AUDIO_TEMPLATE: _stable_id("template:audio"),
    # Preserve the former ord=2 template identity and its card schedules.
    HIRAGANA_FORM_TEMPLATE: _stable_id("template:orthography"),
    PRACTICE_QUESTION_TEMPLATE: _stable_id("template:practice_question"),
    REFERENCE_TABLE_TEMPLATE: _stable_id("template:reference_table"),
    KANJI_TEMPLATE: _stable_id("template:kanji"),
}
_VOCABULARY_FIELD_STABLE_LABELS = {
    "VocabularyContext": "FrontHint",
    "WordJLPT": "OrthographyJLPT",
    "HiraganaWord": "OrthographyPrompt",
    "HiraganaContext": "OrthographyAnswerHTML",
}

FIELD_IDS = {
    VOCABULARY_KIND: {
        name: _stable_id(
            "field:vocabulary:"
            + _VOCABULARY_FIELD_STABLE_LABELS.get(name, name)
        )
        for name in VOCABULARY_FIELDS
    },
    PRACTICE_QUESTION_KIND: {
        name: _stable_id(f"field:practice_question:{name}")
        for name in PRACTICE_QUESTION_FIELDS
    },
    REFERENCE_TABLE_KIND: {
        name: _stable_id(f"field:reference_table:{name}")
        for name in REFERENCE_TABLE_FIELDS
    },
    KANJI_KIND: {
        name: _stable_id(f"field:kanji:{name}") for name in KANJI_FIELDS
    },
}

DECK_KEYS = (
    "root",
    "vocabulary",
    *(f"vocabulary:{level}" for level in LEVELS),
    "audio",
    *(f"audio:{level}" for level in LEVELS),
    *(
        f"practice:{category}:N5"
        for category, _label in PRACTICE_DECK_CATEGORIES
        if category in REFERENCE_MEMORY_CATEGORIES
    ),
    "practice",
    "practice:vocabulary",
    *(
        key
        for level in LEVELS
        for key in (
            f"practice:level:{level}",
            *(
                f"practice:{category}:{level}"
                for category, _label in PRACTICE_DECK_CATEGORIES
                if category not in REFERENCE_MEMORY_CATEGORIES
                and level in PRACTICE_DECK_LEVELS[category]
            ),
        )
    ),
    "reference_table",
    "kanji",
    "kanji:upper",
    "kanji:lower",
)
DECK_IDS: dict[str, DeckId] = {
    key: DeckId(_stable_id(f"deck:{key}")) for key in DECK_KEYS
}
DECK_CONFIG_IDS: dict[str, DeckConfigId] = {
    "vocabulary": DeckConfigId(_stable_id("deck-config:manual")),
    "audio": DeckConfigId(_stable_id("deck-config:core-auto")),
    "practice": DeckConfigId(_stable_id("deck-config:practice-auto")),
    "reference": DeckConfigId(_stable_id("deck-config:reference-manual")),
}
DECK_CONFIG_NAMES = {
    "vocabulary": "JLPT MAX덱 · 어휘",
    "audio": "JLPT MAX덱 · 음성",
    "practice": "JLPT MAX덱 · 실전",
    "reference": "JLPT MAX덱 · 참조·한자",
}
DECK_CONFIG_AUTOPLAY = {
    "vocabulary": True,
    "audio": True,
    "practice": True,
    "reference": False,
}

EXAMPLE4_SECTION = """
  {{#Example4JP}}<section class="example-panel audio-scope">
    <div class="section-label">예문 4</div>
    <div class="example-copy audio-trigger" role="button" tabindex="0"
         aria-label="예문 4 음성 재생">
      <div class="example-jp" lang="ja">{{Example4JP}}</div>
    </div>
    <div class="audio-slot">{{Example4Audio}}</div>
    <div class="example-ko">{{Example4KO}}</div>
  </section>{{/Example4JP}}
"""
VOCABULARY_FEATURE_METADATA = """    <div class="metadata-row">
      <span class="metadata-pill">{{PartOfSpeech}}</span>
      {{StudyPriority}}
      {{#UsageRegister}}<span class="usage-registers">{{UsageRegister}}</span>{{/UsageRegister}}
    </div>"""
WORD_LEVEL_FIELD = (
    "{{#WordJLPT}}{{WordJLPT}}{{/WordJLPT}}"
    "{{^WordJLPT}}{{JLPT}}{{/WordJLPT}}"
)
VOCABULARY_FRONT = BASE_VOCABULARY_FRONT.replace(
    "{{JLPT}}",
    WORD_LEVEL_FIELD,
    1,
).replace(
    '<div class="word" lang="ja">{{Word}}</div>',
    '<div class="word" lang="ja">{{Word}}</div>'
    '{{#VocabularyContext}}'
    '<div class="vocabulary-context" lang="ja">'
    "{{VocabularyContext}}"
    "</div>"
    "{{/VocabularyContext}}",
    1,
)
AUDIO_FRONT = BASE_AUDIO_FRONT.replace(
    "</main>",
    '{{#VocabularyContext}}'
    '<div class="vocabulary-context audio-vocabulary-context" lang="ja">'
    "{{VocabularyContext}}"
    "</div>"
    "{{/VocabularyContext}}"
    "</main>",
    1,
)
CONJUGATION_SECTION = """
  {{#ConjugationDetails}}{{ConjugationDetails}}{{/ConjugationDetails}}
"""
VOCABULARY_BACK = BASE_VOCABULARY_BACK.replace(
    "{{JLPT}}",
    WORD_LEVEL_FIELD,
    1,
).replace(
    '    <div class="metadata-pill">{{PartOfSpeech}}</div>',
    VOCABULARY_FEATURE_METADATA,
    1,
).replace(
    "\n  <footer class=\"compact-tools\">",
    EXAMPLE4_SECTION
    + CONJUGATION_SECTION
    + VOCABULARY_STUDY_SECTIONS
    + "\n  <footer class=\"compact-tools\">",
    1,
)
VOCABULARY_BACK = VOCABULARY_BACK.replace(
    '<section class="lexeme-block lexeme-answer audio-scope">',
    '<section class="lexeme-block lexeme-answer audio-scope" '
    'data-audio-autoplay="word">',
    1,
).replace(
    '<div class="audio-slot">{{WordAudio}}</div>',
    "{{WordAudioFile}}",
    1,
)
AUDIO_BACK = VOCABULARY_BACK.replace(
    ' data-audio-autoplay="word"',
    "",
    1,
).replace(
    WORD_LEVEL_FIELD,
    "{{JLPT}}",
    1,
)
HIRAGANA_FORM_FRONT = (
    "{{#HiraganaWord}}"
    + BASE_VOCABULARY_FRONT.replace(
        '<div class="word" lang="ja">{{Word}}</div>',
        '<div class="word" lang="ja">{{HiraganaWord}}</div>'
        "{{#HiraganaContext}}"
        '<div class="vocabulary-context" lang="ja">'
        "{{HiraganaContext}}"
        "</div>"
        "{{/HiraganaContext}}",
        1,
    )
    + "{{/HiraganaWord}}"
)

VOCABULARY_CSS = BASE_VOCABULARY_CSS + STUDY_FEATURE_CSS + """
.metadata-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 9px;
}
.vocabulary-context {
  margin-top: 8px;
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}
.vocabulary-context-target {
  color: var(--ink);
  font-weight: 850;
}
.metadata-row .metadata-pill { margin-top: 0; }
.usage-registers { display: inline-flex; gap: 5px; flex-wrap: wrap; justify-content: center; }
.usage-register-badge {
  display: inline-flex;
  align-items: center;
  min-height: 23px;
  padding: 3px 8px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 750;
  line-height: 1.3;
}
.usage-register-badge.is-honorific { border-style: double; }
.usage-register-badge.is-marked { background: var(--surface-muted); }
.usage-register-badge.is-field { border-style: dashed; }
.conjugation-panel {
  margin-top: 8px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  overflow: hidden;
}
.conjugation-panel > summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 9px 13px;
  cursor: pointer;
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .06em;
  list-style: none;
}
.conjugation-panel > summary::-webkit-details-marker { display: none; }
.conjugation-panel > summary::after { content: "▾"; color: var(--ink-soft); }
.conjugation-panel[open] > summary::after { content: "▴"; }
.conjugation-body { padding: 0 13px 12px; }
.conjugation-grid { display: grid; gap: 1px; }
.conjugation-row {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 7px 9px;
  border-radius: 6px;
}
.conjugation-row:nth-child(odd) { background: var(--surface-muted); }
.conjugation-label {
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 750;
  line-height: 1.4;
}
.conjugation-value {
  min-width: 0;
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
@media (max-width: 360px) {
  .conjugation-row { gap: 8px; }
}
"""

PRACTICE_QUESTION_FRONT = """
<main class="card-shell question-card">
  <header class="card-header"><span class="level-pill">{{JLPT}}</span></header>
  <div class="question-kicker">{{QuestionLabel}}</div>
  <div class="question-instruction">{{Instruction}}</div>
  <div class="question-prompt" lang="ja">{{PromptJP}}</div>
  {{#ChoicesHTML}}<section class="question-choices">{{ChoicesHTML}}</section>{{/ChoicesHTML}}
</main>
"""
PRACTICE_QUESTION_BACK = """
<main class="card-shell question-card question-answer-card">
  <header class="card-header"><span class="level-pill">{{JLPT}}</span></header>
  <div class="question-kicker">{{QuestionLabel}}</div>
  <div class="question-instruction">{{Instruction}}</div>
  <div class="question-prompt" lang="ja">{{PromptRuby}}</div>
  {{#PromptKORuby}}<div class="question-prompt-ko">{{PromptKORuby}}</div>{{/PromptKORuby}}
  {{#ChoicesRubyHTML}}<section class="question-choices">{{ChoicesRubyHTML}}</section>{{/ChoicesRubyHTML}}
  <hr id="answer">
  <section class="question-answer">
    <div class="answer-label">정답</div>
    <div class="answer-jp audio-scope">
      <div class="audio-trigger" role="button" tabindex="0"
           aria-label="정답 음성 재생" lang="ja">{{AnswerRuby}}</div>
      <div class="audio-slot">{{AnswerAudio}}</div>
    </div>
    {{#AnswerKORuby}}<div class="answer-ko">{{AnswerKORuby}}</div>{{/AnswerKORuby}}
    {{#ExplanationRubyHTML}}<div class="question-explanation">{{ExplanationRubyHTML}}</div>{{/ExplanationRubyHTML}}
  </section>
  <footer class="reference-source">{{Source}} · p.{{SourcePage}}</footer>
</main>
""" + AUDIO_INTERACTION
REFERENCE_TABLE_FRONT = """
<main class="card-shell reference-card reference-front">
  <header class="card-header"><span class="level-pill">{{JLPT}}</span></header>
  <div class="reference-kicker">참조표</div>
  <div class="table-title">{{Title}}</div>
  <div class="reference-part-label">{{PartLabel}}</div>
</main>
"""

KANJI_FRONT = """
<main class="card-shell kanji-card">
  <header class="card-header kanji-card-header">
    <span class="level-pill kanji-volume">{{Volume}}</span>
    <span class="kanji-context">{{Unit}} · {{Theme}}</span>
  </header>
  <section class="kanji-hero">{{GlyphHTML}}</section>
</main>
"""
KANJI_BACK = """
<main class="card-shell kanji-card kanji-answer-card">
  <header class="card-header kanji-card-header">
    <span class="level-pill kanji-volume">{{Volume}}</span>
    <span class="kanji-context">{{Unit}} · {{Theme}}</span>
  </header>
  <section class="kanji-hero">{{GlyphHTML}}</section>
  <hr id="answer">
  <div class="kanji-meaning">{{Meaning}}</div>
  {{#KanjiReference}}{{KanjiReference}}{{/KanjiReference}}
  {{#LinkedVocabulary}}{{LinkedVocabulary}}{{/LinkedVocabulary}}
</main>
""" + AUDIO_INTERACTION
REFERENCE_TABLE_BACK = """
<main class="card-shell reference-card table-card table-kind-{{TableKind}}">
  <header class="card-header"><span class="level-pill">{{JLPT}}</span></header>
  <div class="reference-kicker">참조표</div>
  <h1 class="table-title">{{Title}}</h1>
  <div class="reference-part-label">{{PartLabel}}</div>
  <section class="reference-groups">{{TableHTML}}</section>
  <footer class="reference-source">{{Source}} · p.{{SourcePage}}</footer>
</main>
""" + AUDIO_INTERACTION

REFERENCE_CSS = BASE_VOCABULARY_CSS + """
.question-card {
  --question-font-ko: "Noto Sans KR", "Noto Sans CJK KR", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  min-height: 45vh;
  font-family: var(--question-font-ko);
}
.question-kicker, .reference-kicker {
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .1em;
  text-align: center;
}
.question-kicker { font-size: 12px; }
.question-instruction {
  margin-top: 10px;
  color: var(--ink-soft);
  font-size: 13px;
  font-weight: 700;
  text-align: center;
}
.question-prompt {
  margin-top: 15px;
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: clamp(19px, 4.5vw, 26px);
  font-weight: 700;
  line-height: 1.6;
  overflow-wrap: anywhere;
  text-align: center;
}
.question-prompt-ko {
  margin-top: 7px;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.5;
  text-align: center;
}
.question-target,
.question-target-word {
  padding: 0 .04em .03em;
  border-bottom: 2px solid var(--accent);
  background: linear-gradient(transparent 68%, var(--accent-soft) 68%);
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
  text-decoration: none;
}
.question-target-word {
  display: inline-block;
  padding: 0 .18em;
  line-height: 1.2;
}
.question-blank {
  color: var(--accent);
  letter-spacing: 0;
  white-space: nowrap;
}
.question-options {
  display: grid;
  gap: 8px;
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
}
.question-option {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  align-items: stretch;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  text-align: left;
}
.question-option-marker,
.choice-note-marker {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
  font-family: "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif;
  font-weight: 700;
}
.question-option-marker-glyph,
.choice-note-marker-glyph { display: block; line-height: 1; }
.question-option-marker {
  align-self: stretch;
  font-size: 20px;
}
.choice-note-marker { font-size: 17px; min-height: 1.2em; }
.question-option-content { display: grid; min-width: 0; gap: 3px; }
.question-option-copy {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.question-option-translation {
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.question-answer-card .question-option.is-correct {
  border-color: color-mix(in srgb, var(--accent) 58%, var(--line));
  background: var(--accent-soft);
}
.question-card ruby {
  display: inline-grid;
  justify-items: center;
  margin-inline: -0.08em;
  vertical-align: baseline;
  line-height: 1;
  ruby-align: center;
  ruby-position: over;
  ruby-overhang: none;
}
.question-card rt {
  display: block;
  grid-area: 1 / 1;
  align-self: start;
  justify-self: center;
  transform: translateY(-100%);
  color: var(--ink-soft);
  font-family: -apple-system, BlinkMacSystemFont, "Hiragino Kaku Gothic ProN", sans-serif;
  font-size: .5em;
  font-weight: 600;
  line-height: 1.15;
  white-space: nowrap;
}
.question-card rb {
  display: block;
  grid-area: 1 / 1;
  align-self: baseline;
  line-height: 1;
}
.question-answer-card #answer { margin: 20px 0 15px; border: 0; border-top: 1px solid var(--line); }
.question-answer {
  padding: 14px;
  border: 1px solid color-mix(in srgb, var(--accent) 34%, var(--line));
  border-radius: 11px;
  background: var(--accent-soft);
  text-align: center;
}
.answer-label { color: var(--accent); font-size: 10px; font-weight: 800; letter-spacing: .08em; }
.answer-jp {
  margin-top: 6px;
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 21px;
  font-weight: 800;
  line-height: 1.55;
}
.answer-ko { margin-top: 6px; font-size: 14px; line-height: 1.5; }
.question-explanation {
  margin-top: 11px;
  padding-top: 11px;
  border-top: 1px solid var(--line);
  font-size: 13px;
  line-height: 1.55;
  text-align: left;
}
.choice-notes { display: grid; gap: 5px; margin: 9px 0 0; padding: 0; list-style: none; }
.choice-note {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  align-items: start;
  gap: 6px;
}
.reference-front { min-height: 45vh; }
.reference-front .reference-kicker { margin-top: min(14vh, 84px); }
.reference-prompt {
  margin-top: 14px;
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: clamp(28px, 8vw, 42px);
  font-weight: 700;
  line-height: 1.4;
  overflow-wrap: anywhere;
  text-align: center;
}
.reference-source {
  margin-top: 14px;
  padding-top: 9px;
  border-top: 1px solid var(--line);
  color: var(--ink-soft);
  font-size: 10px;
  text-align: right;
}
.table-title {
  margin: 14px 0 0;
  font-size: clamp(24px, 7vw, 36px);
  line-height: 1.35;
  text-align: center;
}
.reference-part-label {
  margin-top: 6px;
  color: var(--ink-soft);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: .04em;
  text-align: center;
}
.reference-groups {
  display: grid;
  align-items: start;
  gap: 10px;
  margin-top: 18px;
}
.reference-group {
  align-self: start;
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  overflow: hidden;
}
.reference-group-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 11px 12px;
  background: var(--surface-muted);
  font-weight: 800;
}
.reference-group-count { color: var(--ink-soft); font-size: 10px; font-weight: 650; }
.reference-rows { display: grid; }
.reference-row {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  padding: 8px 11px;
  border-top: 1px solid var(--line);
}
.reference-key { color: var(--ink-soft); font-size: 12px; font-weight: 700; }
.reference-value {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 15px;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.reference-calendar-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  padding: 10px;
}
.reference-cell {
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-muted);
}
.reference-cell-jp {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 14px;
  font-weight: 750;
  overflow-wrap: anywhere;
}
.reference-cell-ko { margin-top: 3px; color: var(--ink-soft); font-size: 10px; }
@media (min-width: 620px) {
  .reference-groups { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .table-kind-counter_matrix .reference-group:only-child {
    grid-column: 1 / -1;
    justify-self: center;
    width: calc((100% - 10px) / 2);
  }
  .reference-calendar-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
.table-kind-calendar_grid .reference-groups {
  grid-template-columns: minmax(0, 1fr);
}
@media (min-width: 620px) {
  .table-kind-calendar_grid .reference-groups {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .table-kind-calendar_grid .reference-group:last-child:nth-child(odd) {
    grid-column: 1 / -1;
  }
}
"""

KANJI_CSS = BASE_VOCABULARY_CSS + KANJI_CARD_CSS + """
.kanji-answer-card #answer { margin: 16px 0 12px; border: 0; border-top: 1px solid var(--line); }
"""


@dataclass(frozen=True)
class NotetypeSpec:
    kind: str
    name: str
    fields: tuple[str, ...]
    sort_field: str
    templates: tuple[tuple[str, str, str], ...]
    css: str


NOTETYPE_SPECS = {
    VOCABULARY_KIND: NotetypeSpec(
        kind=VOCABULARY_KIND,
        name=VOCABULARY_NOTETYPE,
        fields=VOCABULARY_FIELDS,
        sort_field="Word",
        templates=(
            (VOCABULARY_TEMPLATE, VOCABULARY_FRONT, VOCABULARY_BACK),
            (AUDIO_TEMPLATE, AUDIO_FRONT, AUDIO_BACK),
            (HIRAGANA_FORM_TEMPLATE, HIRAGANA_FORM_FRONT, VOCABULARY_BACK),
        ),
        css=VOCABULARY_CSS,
    ),
    PRACTICE_QUESTION_KIND: NotetypeSpec(
        kind=PRACTICE_QUESTION_KIND,
        name=PRACTICE_QUESTION_NOTETYPE,
        fields=PRACTICE_QUESTION_FIELDS,
        sort_field="SortKey",
        templates=(
            (
                PRACTICE_QUESTION_TEMPLATE,
                PRACTICE_QUESTION_FRONT,
                PRACTICE_QUESTION_BACK,
            ),
        ),
        css=REFERENCE_CSS,
    ),
    REFERENCE_TABLE_KIND: NotetypeSpec(
        kind=REFERENCE_TABLE_KIND,
        name=REFERENCE_TABLE_NOTETYPE,
        fields=REFERENCE_TABLE_FIELDS,
        sort_field="Title",
        templates=((REFERENCE_TABLE_TEMPLATE, REFERENCE_TABLE_FRONT, REFERENCE_TABLE_BACK),),
        css=REFERENCE_CSS,
    ),
    KANJI_KIND: NotetypeSpec(
        kind=KANJI_KIND,
        name=KANJI_NOTETYPE,
        fields=KANJI_FIELDS,
        sort_field="SortKey",
        templates=((KANJI_TEMPLATE, KANJI_FRONT, KANJI_BACK),),
        css=KANJI_CSS,
    ),
}


@dataclass(frozen=True)
class ClosedDeckInputs:
    content_root: Path
    media_root: Path
    content_manifest: dict[str, Any]
    media_manifest: dict[str, Any]
    deck_layout: dict[str, Any]
    summary: dict[str, Any]
    vocabulary_notes: list[dict[str, Any]]
    practice_question_notes: list[dict[str, Any]]
    reference_table_notes: list[dict[str, Any]]
    kanji_notes: list[dict[str, Any]]
    media_jobs: list[dict[str, Any]]
    media_inventory: list[dict[str, Any]]


class DeckBuildError(RuntimeError):
    """Raised when a Stage 9 boundary or built package fails closed."""


class _NoteFields(Protocol):
    def __getitem__(self, key: str) -> Any: ...


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeckBuildError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise DeckBuildError(f"{label} must be a JSON object")
    return value


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DeckBuildError(f"cannot read {label}: {exc}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DeckBuildError(f"cannot parse {label}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise DeckBuildError(f"{label}:{line_number} must be a JSON object")
        records.append(value)
    return records


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ensure_empty(path: Path, label: str) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise DeckBuildError(f"{label} must be empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _closed_manifest(root: Path, name: str, stage_id: str, label: str) -> dict[str, Any]:
    manifest = _read_json(root / name, f"{label} manifest")
    if (
        manifest.get("stage_id") != stage_id
        or manifest.get("stage_order") != 9
        or manifest.get("status") != "passed"
        or manifest.get("unresolved") != 0
    ):
        raise DeckBuildError(f"{label} boundary is not passed and closed")
    return manifest


def _verified_artifacts(
    root: Path,
    manifest: Mapping[str, Any],
    names: Sequence[str],
    label: str,
) -> dict[str, Path]:
    declared = manifest.get("output_artifacts")
    if not isinstance(declared, dict):
        raise DeckBuildError(f"{label} manifest lacks output artifacts")
    paths: dict[str, Path] = {}
    for name in names:
        path = root / name
        expected = declared.get(name)
        if not isinstance(expected, str) or not path.is_file() or sha256_file(path) != expected:
            raise DeckBuildError(f"{label} artifact hash changed: {name}")
        paths[name] = path
    return paths


def _valid_wave(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as audio:
            return (
                audio.getnchannels() == 1
                and audio.getsampwidth() == 2
                and audio.getframerate() == SAMPLE_RATE
                and audio.getnframes() > 0
            )
    except (OSError, EOFError, wave.Error):
        return False


def _valid_audio(path: Path, inventory: Mapping[str, Any]) -> bool:
    if path.suffix == ".wav":
        return (
            inventory.get("codec") in {None, "pcm_s16le"}
            and inventory.get("sample_rate") == SAMPLE_RATE
            and inventory.get("channels") == 1
            and inventory.get("sample_width") == 2
            and _valid_wave(path)
        )
    if path.suffix != ".mp3" or inventory.get("codec") != "mp3":
        return False
    try:
        info = inspect_cbr_mp3(path)
    except MediaCodecError:
        return False
    return (
        info.sample_rate == SAMPLE_RATE
        and info.channels == 1
        and info.bitrate_kbps == MP3_BITRATE_KBPS
        and inventory.get("sample_rate") == info.sample_rate
        and inventory.get("channels") == info.channels
        and inventory.get("bitrate_kbps") == info.bitrate_kbps
        and inventory.get("frame_count") == info.frame_count
        and inventory.get("sample_count") == info.sample_count
        and isinstance(inventory.get("source_frame_count"), int)
        and inventory["source_frame_count"] > 0
        and inventory["source_frame_count"] <= info.sample_count
        and info.sample_count - inventory["source_frame_count"]
        <= MP3_MAX_ENCODER_PADDING_SAMPLES
    )


def _validate_deck_layout(layout: Mapping[str, Any]) -> None:
    decks = layout.get("decks")
    if not isinstance(decks, list):
        raise DeckBuildError("deck layout lacks decks")
    by_key = {
        str(deck.get("key")): deck
        for deck in decks
        if isinstance(deck, dict)
    }
    if tuple(by_key) != DECK_KEYS:
        raise DeckBuildError("deck layout keys or ordering changed")
    expected_parents = {
        "root": None,
        "vocabulary": "root",
        "audio": "root",
        "practice": "root",
        "practice:vocabulary": "practice",
        "reference_table": "root",
        "kanji": "root",
        "kanji:upper": "kanji",
        "kanji:lower": "kanji",
        **{f"vocabulary:{level}": "vocabulary" for level in LEVELS},
        **{f"audio:{level}": "audio" for level in LEVELS},
        **{
            f"practice:{category}:N5": "vocabulary:N5"
            for category in REFERENCE_MEMORY_CATEGORIES
        },
        **{
            f"practice:level:{level}": "practice:vocabulary"
            for level in LEVELS
        },
        **{
            f"practice:{category}:{level}": f"practice:level:{level}"
            for category, _label in PRACTICE_DECK_CATEGORIES
            if category not in REFERENCE_MEMORY_CATEGORIES
            for level in PRACTICE_DECK_LEVELS[category]
        },
    }
    for key, parent in expected_parents.items():
        if by_key[key].get("parent") != parent:
            raise DeckBuildError(f"deck parent changed: {key}")
    expected_names = {
        "root": PRODUCT_NAME,
        "vocabulary": f"{PRODUCT_NAME}::어휘",
        "audio": f"{PRODUCT_NAME}::음성",
        "practice": f"{PRODUCT_NAME}::{PRACTICE_ROOT_LABEL}",
        "practice:vocabulary": (
            f"{PRODUCT_NAME}::{PRACTICE_ROOT_LABEL}::어휘"
        ),
        "reference_table": f"{PRODUCT_NAME}::참조표",
        "kanji": f"{PRODUCT_NAME}::일상무따",
        "kanji:upper": f"{PRODUCT_NAME}::일상무따::상권",
        "kanji:lower": f"{PRODUCT_NAME}::일상무따::하권",
        **{
            f"vocabulary:{level}": f"{PRODUCT_NAME}::어휘::{level}"
            for level in LEVELS
        },
        **{
            f"audio:{level}": f"{PRODUCT_NAME}::음성::{level}"
            for level in LEVELS
        },
        **{
            f"practice:{category}:N5": (
                f"{PRODUCT_NAME}::어휘::N5::{PRACTICE_DECK_LABELS[category]}"
            )
            for category in REFERENCE_MEMORY_CATEGORIES
        },
        **{
            f"practice:level:{level}": (
                f"{PRODUCT_NAME}::{PRACTICE_ROOT_LABEL}::어휘::{level}"
            )
            for level in LEVELS
        },
        **{
            f"practice:{category}:{level}": (
                f"{PRODUCT_NAME}::{PRACTICE_ROOT_LABEL}::어휘::{level}::"
                f"{PRACTICE_DECK_LABELS[category]}"
            )
            for category, _label in PRACTICE_DECK_CATEGORIES
            if category not in REFERENCE_MEMORY_CATEGORIES
            for level in PRACTICE_DECK_LEVELS[category]
        },
    }
    for key, name in expected_names.items():
        if by_key[key].get("name") != name:
            raise DeckBuildError(f"deck name changed: {key}")
    visible_top_level_order = sorted(
        str(deck["name"])
        for deck in by_key.values()
        if deck.get("parent") == "root"
    )
    if visible_top_level_order != [
        f"{PRODUCT_NAME}::어휘",
        f"{PRODUCT_NAME}::음성",
        f"{PRODUCT_NAME}::일상무따",
        f"{PRODUCT_NAME}::{PRACTICE_ROOT_LABEL}",
        f"{PRODUCT_NAME}::참조표",
    ]:
        raise DeckBuildError("top-level deck display order changed")
    expected_collapsed = {
        key: (
            key == "audio"
            or (
                key not in {
                    "root",
                    "vocabulary",
                    "practice",
                    "practice:vocabulary",
                    "kanji",
                    "vocabulary:N5",
                    *(f"practice:level:{level}" for level in LEVELS),
                }
            )
        )
        for key in DECK_KEYS
    }
    for key, collapsed in expected_collapsed.items():
        if (
            by_key[key].get("collapsed") is not collapsed
            or by_key[key].get("browser_collapsed") is not collapsed
        ):
            raise DeckBuildError(f"deck collapsed state changed: {key}")
    note_types = layout.get("note_types")
    expected_note_types = {
        REFERENCE_TABLE_KIND: {
            "name": REFERENCE_TABLE_NOTETYPE,
            "templates": [REFERENCE_TABLE_TEMPLATE],
        },
        PRACTICE_QUESTION_KIND: {
            "name": PRACTICE_QUESTION_NOTETYPE,
            "templates": [PRACTICE_QUESTION_TEMPLATE],
        },
        VOCABULARY_KIND: {
            "name": VOCABULARY_NOTETYPE,
            "templates": [
                VOCABULARY_TEMPLATE,
                AUDIO_TEMPLATE,
                HIRAGANA_FORM_TEMPLATE,
            ],
        },
        KANJI_KIND: {
            "name": KANJI_NOTETYPE,
            "templates": [KANJI_TEMPLATE],
        },
    }
    if not isinstance(note_types, dict) or set(note_types) != set(expected_note_types):
        raise DeckBuildError("deck layout note types changed")
    for kind, expected in expected_note_types.items():
        actual = note_types[kind]
        if not isinstance(actual, dict) or any(
            actual.get(name) != value for name, value in expected.items()
        ):
            raise DeckBuildError(f"deck layout note type changed: {kind}")
    expected_card_bearing_count = (
        (2 * len(LEVELS))
        + sum(
            len(PRACTICE_DECK_LEVELS[category])
            for category, _label in PRACTICE_DECK_CATEGORIES
        )
        + 3
    )
    parent_keys = {
        parent for parent in expected_parents.values() if parent is not None
    }
    expected_leaf_count = sum(key not in parent_keys for key in DECK_KEYS)
    if (
        layout.get("total_deck_count") != len(DECK_KEYS)
        or layout.get("leaf_deck_count") != expected_leaf_count
        or layout.get("card_bearing_deck_count")
        != expected_card_bearing_count
        or layout.get("template_count") != 6
    ):
        raise DeckBuildError("deck/template count contract changed")


def _closed_count(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DeckBuildError(f"{label} must be a non-negative integer")
    return value


def _normalized_kind_counts(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise DeckBuildError(f"{label} must be an object")
    counts: dict[str, int] = {}
    for raw_kind, raw_count in value.items():
        kind = str(raw_kind)
        count = _closed_count(raw_count, f"{label}.{kind}")
        if not kind or count == 0:
            raise DeckBuildError(f"{label} contains an empty kind or zero count")
        counts[kind] = count
    return dict(sorted(counts.items()))


def _reconcile_closed_input_counts(
    *,
    summary: Mapping[str, Any],
    media_summary: Mapping[str, Any],
    vocabulary_note_count: int,
    hiragana_form_card_count: int,
    practice_note_count: int,
    table_note_count: int,
    kanji_note_count: int,
    approved_example_count: int,
    blocked_example_count: int,
    notes_with_examples: int,
    notes_without_examples: int,
    media_job_counts: Mapping[str, int],
    inventory_kind_counts: Mapping[str, int],
) -> None:
    """Reconcile variable release sizes across closed content and media artifacts."""
    hiragana_form_card_count = _closed_count(
        hiragana_form_card_count,
        "hiragana-form card count",
    )
    job_counts = _normalized_kind_counts(media_job_counts, "media job counts")
    inventory_counts = _normalized_kind_counts(
        inventory_kind_counts, "media inventory kind counts"
    )
    if job_counts != inventory_counts:
        raise DeckBuildError("media job and inventory kind counts differ")

    media_count = sum(job_counts.values())
    static_count = job_counts.get("kanji_static", 0)
    audio_count = media_count - static_count
    expression_count = _closed_count(
        summary.get("expression_practice_note_count"),
        "expression practice note count",
    )
    lexical_form_count = _closed_count(
        summary.get("lexical_form_practice_note_count"),
        "lexical-form practice note count",
    )
    reference_count = _closed_count(
        summary.get("reference_practice_note_count"),
        "reference practice note count",
    )
    expected_summary_counts = {
        "approved_example_count": approved_example_count,
        "blocked_example_count": blocked_example_count,
        "example_audio_job_count": approved_example_count,
        "example_target_count": approved_example_count + blocked_example_count,
        "kanji_note_count": kanji_note_count,
        "media_job_count": media_count,
        "notes_with_examples": notes_with_examples,
        "notes_without_examples": notes_without_examples,
        "practice_question_note_count": practice_note_count,
        "reference_table_note_count": table_note_count,
        "hiragana_form_card_count": hiragana_form_card_count,
        "total_card_count": (
            vocabulary_note_count * 2
            + hiragana_form_card_count
            + practice_note_count
            + table_note_count
            + kanji_note_count
        ),
        "total_note_count": (
            vocabulary_note_count
            + practice_note_count
            + table_note_count
            + kanji_note_count
        ),
        "vocabulary_note_count": vocabulary_note_count,
        "word_audio_job_count": vocabulary_note_count,
    }
    supplemental_count = (
        media_count
        - job_counts.get("word", 0)
        - job_counts.get("example", 0)
        - static_count
    )
    kanji_summary = summary.get("kanji")
    if (
        summary.get("status") != "passed"
        or summary.get("unresolved") != 0
        or any(
            summary.get(key) != expected
            for key, expected in expected_summary_counts.items()
        )
        or expression_count + lexical_form_count + reference_count
        != practice_note_count
        or reference_count != EXPECTED_REFERENCE_PRACTICE_NOTES
        or summary.get("practice_ruby_note_count")
        != expression_count + lexical_form_count
        or summary.get("media_job_counts_by_kind") != job_counts
        or summary.get("supplemental_audio_job_count") != supplemental_count
        or table_note_count != EXPECTED_REFERENCE_TABLE_NOTES
        or kanji_note_count != EXPECTED_KANJI_NOTES
        or static_count != EXPECTED_KANJI_STATIC_MEDIA
        or job_counts.get("word", 0) != vocabulary_note_count
        or job_counts.get("example", 0) != approved_example_count
        or not isinstance(kanji_summary, Mapping)
        or kanji_summary.get("note_count") != kanji_note_count
        or kanji_summary.get("static_media_count") != static_count
    ):
        raise DeckBuildError(
            "content summary does not reconcile with note and media artifacts"
        )

    expected_media_summary = {
        "audio_count": audio_count,
        "example_count": approved_example_count,
        "kanji_static_count": static_count,
        "kind_counts": job_counts,
        "media_count": media_count,
        "word_count": vocabulary_note_count,
    }
    if (
        media_summary.get("status") != "passed"
        or media_summary.get("unresolved") != 0
        or any(
            media_summary.get(key) != expected
            for key, expected in expected_media_summary.items()
        )
    ):
        raise DeckBuildError(
            "media summary does not reconcile with jobs and inventory"
        )


def _reconcile_deck_layout_counts(
    *,
    layout: Mapping[str, Any],
    summary: Mapping[str, Any],
    vocabulary_notes: Sequence[Mapping[str, Any]],
    practice_notes: Sequence[Mapping[str, Any]],
    table_notes: Sequence[Mapping[str, Any]],
    kanji_notes: Sequence[Mapping[str, Any]],
) -> int:
    """Bind variable conditional cards to the closed layout and summary."""
    expected: dict[str, int] = {
        **{f"vocabulary:{level}": 0 for level in LEVELS},
        **{f"audio:{level}": 0 for level in LEVELS},
        **{
            f"practice:{category}:{level}": 0
            for category, _label in PRACTICE_DECK_CATEGORIES
            for level in PRACTICE_DECK_LEVELS[category]
        },
        "reference_table": 0,
        "kanji:upper": 0,
        "kanji:lower": 0,
    }
    hiragana_form_card_count = 0
    for record in vocabulary_notes:
        word = str(record.get("word", ""))
        if not word or record.get("vocabulary_front") != word:
            raise DeckBuildError(
                f"vocabulary front changed: {record.get('note_id')}"
            )
        hiragana_form_fields = _hiragana_form_field_values(record)
        routes = _vocabulary_card_routes(record, hiragana_form_fields)
        for key in routes.values():
            expected[key] += 1
        if HIRAGANA_FORM_TEMPLATE in routes:
            hiragana_form_card_count += 1

    for record in practice_notes:
        level = str(record.get("jlpt_level", ""))
        question_type = str(record.get("question_type", ""))
        try:
            expected_key = practice_deck_key(question_type, level)
        except ValueError as exc:
            raise DeckBuildError(
                f"unsupported practice-question deck: {record.get('note_id')}"
            ) from exc
        if record.get("deck_key") != expected_key:
            raise DeckBuildError(
                f"practice-question deck key changed: {record.get('note_id')}"
            )
        expected[expected_key] += 1

    for record in table_notes:
        if record.get("deck_key") != "reference_table":
            raise DeckBuildError(
                f"reference-table deck key changed: {record.get('note_id')}"
            )
        expected["reference_table"] += 1

    for record in kanji_notes:
        key = f"kanji:{record.get('volume_code', '')}"
        if key not in {"kanji:upper", "kanji:lower"} or record.get(
            "deck_keys"
        ) != [key]:
            raise DeckBuildError(
                f"kanji deck key changed: {record.get('note_id')}"
            )
        expected[key] += 1

    raw_counts = layout.get("card_counts_by_deck")
    if not isinstance(raw_counts, Mapping) or set(raw_counts) != set(expected):
        raise DeckBuildError("deck layout card-count keys changed")
    actual = {
        str(key): _closed_count(value, f"deck card count {key}")
        for key, value in raw_counts.items()
    }
    if actual != expected:
        raise DeckBuildError(
            "deck layout card counts do not reconcile with closed notes"
        )

    expected_note_counts = {
        VOCABULARY_KIND: len(vocabulary_notes),
        PRACTICE_QUESTION_KIND: len(practice_notes),
        REFERENCE_TABLE_KIND: len(table_notes),
        KANJI_KIND: len(kanji_notes),
    }
    note_types = layout.get("note_types")
    if not isinstance(note_types, Mapping) or any(
        not isinstance(note_types.get(kind), Mapping)
        or note_types[kind].get("note_count") != count
        for kind, count in expected_note_counts.items()
    ):
        raise DeckBuildError("deck layout note counts do not reconcile")
    if summary.get("total_card_count") != sum(expected.values()):
        raise DeckBuildError(
            "deck layout card counts do not reconcile with content summary"
        )
    return hiragana_form_card_count


def _apply_package_audio_policy(
    *,
    summary: Mapping[str, Any],
    practice_notes: Sequence[Mapping[str, Any]],
    media_jobs: Sequence[Mapping[str, Any]],
    media_inventory: Sequence[Mapping[str, Any]],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Prune legacy prompt clips from otherwise verified closed artifacts."""
    excluded_kind = "practice_prompt"
    excluded_jobs = {
        str(item.get("filename", ""))
        for item in media_jobs
        if item.get("kind") == excluded_kind
    }
    excluded_inventory = {
        str(item.get("filename", ""))
        for item in media_inventory
        if item.get("kind") == excluded_kind
    }
    prompt_note_files = {
        str(item.get("prompt_audio_filename", ""))
        for item in practice_notes
        if item.get("prompt_audio_filename") not in {None, ""}
    }
    if (
        "" in excluded_jobs
        or "" in excluded_inventory
        or "" in prompt_note_files
        or excluded_jobs != excluded_inventory
        or excluded_jobs != prompt_note_files
    ):
        raise DeckBuildError("legacy practice prompt audio bindings differ")

    active_notes: list[dict[str, Any]] = []
    for raw in practice_notes:
        note = dict(raw)
        note.pop("prompt_audio_filename", None)
        active_notes.append(note)
    active_jobs = [
        dict(item) for item in media_jobs if item.get("kind") != excluded_kind
    ]
    active_inventory = [
        dict(item)
        for item in media_inventory
        if item.get("kind") != excluded_kind
    ]
    active_counts = Counter(str(item.get("kind", "")) for item in active_jobs)
    if any(not kind for kind in active_counts):
        raise DeckBuildError("active package media contains an empty kind")
    active_summary = copy.deepcopy(dict(summary))
    active_summary["media_job_count"] = len(active_jobs)
    active_summary["media_job_counts_by_kind"] = dict(sorted(active_counts.items()))
    active_summary["supplemental_audio_job_count"] = (
        len(active_jobs)
        - active_counts.get("word", 0)
        - active_counts.get("example", 0)
        - active_counts.get("kanji_static", 0)
    )
    active_summary["excluded_media_job_counts"] = (
        {excluded_kind: len(excluded_jobs)} if excluded_jobs else {}
    )
    return active_summary, active_notes, active_jobs, active_inventory


def _require_zero_blocked_practice(summary: Mapping[str, Any]) -> None:
    if summary.get("blocked_expression_question_count") != 0:
        raise DeckBuildError(
            "release package requires zero blocked practice questions"
        )


def _require_complete_vocabulary_examples(summary: Mapping[str, Any]) -> None:
    if summary.get("blocked_example_count") != 0:
        raise DeckBuildError(
            "release package requires zero blocked vocabulary examples"
        )
    if summary.get("content_variant") == "public_source_materialized":
        # Public projection removes examples whose reviewed sense is backed
        # only by a non-public source.  A retained H/D word may thus
        # legitimately have no example, while blocked targets must stay zero.
        return
    if summary.get("notes_without_examples") != 0:
        raise DeckBuildError(
            "release package requires at least one approved example for every "
            "vocabulary note"
        )
    if summary.get("notes_with_examples") != summary.get(
        "vocabulary_note_count"
    ):
        raise DeckBuildError(
            "release package vocabulary example coverage is incomplete"
        )


def load_closed_inputs(content_root: Path, media_root: Path) -> ClosedDeckInputs:
    """Validate and load the only two data boundaries accepted by the builder."""
    content_manifest = _closed_manifest(
        content_root, CONTENT_STAGE_MANIFEST, CONTENT_STAGE_ID, "content"
    )
    content_names = (
        DECK_LAYOUT,
        KANJI_NOTES,
        MEDIA_JOBS,
        PRACTICE_QUESTION_NOTES,
        REFERENCE_TABLE_NOTES,
        CONTENT_SUMMARY,
        VOCABULARY_NOTES,
    )
    content_paths = _verified_artifacts(
        content_root, content_manifest, content_names, "content"
    )
    media_manifest = _closed_manifest(
        media_root, MEDIA_STAGE_MANIFEST, MEDIA_STAGE_ID, "media"
    )
    media_paths = _verified_artifacts(
        media_root,
        media_manifest,
        (MEDIA_INVENTORY, MEDIA_SUMMARY),
        "media",
    )
    content_manifest_hash = sha256_file(content_root / CONTENT_STAGE_MANIFEST)
    content_output_bundle = content_manifest.get("output_bundle_hash")
    media_jobs_hash = content_manifest["output_artifacts"].get(MEDIA_JOBS)
    media_inputs = media_manifest.get("input_hashes")
    if not isinstance(media_inputs, dict) or (
        media_inputs.get("content_manifest") != content_manifest_hash
        or media_inputs.get("content_output_bundle") != content_output_bundle
        or media_inputs.get("media_jobs") != media_jobs_hash
    ):
        raise DeckBuildError("media manifest is not bound to this content manifest")

    layout = _read_json(content_paths[DECK_LAYOUT], "deck layout")
    summary = _read_json(content_paths[CONTENT_SUMMARY], "content summary")
    vocabulary_notes = _read_jsonl(
        content_paths[VOCABULARY_NOTES], "vocabulary notes"
    )
    practice_notes = _read_jsonl(
        content_paths[PRACTICE_QUESTION_NOTES], "practice-question notes"
    )
    table_notes = _read_jsonl(
        content_paths[REFERENCE_TABLE_NOTES], "reference-table notes"
    )
    kanji_notes = _read_jsonl(content_paths[KANJI_NOTES], "kanji notes")
    media_jobs = _read_jsonl(content_paths[MEDIA_JOBS], "media jobs")
    inventory = _read_jsonl(media_paths[MEDIA_INVENTORY], "media inventory")
    media_summary = _read_json(media_paths[MEDIA_SUMMARY], "media summary")
    _validate_deck_layout(layout)

    approved_example_count = 0
    blocked_example_count = 0
    notes_with_examples = 0
    notes_without_examples = 0
    for note in vocabulary_notes:
        examples = note.get("examples")
        blocked_targets = note.get("blocked_example_target_ids")
        if not isinstance(examples, list) or not isinstance(blocked_targets, list):
            raise DeckBuildError(
                "vocabulary example partitions must be JSON arrays"
            )
        approved_example_count += len(examples)
        blocked_example_count += len(blocked_targets)
        if examples:
            notes_with_examples += 1
        else:
            notes_without_examples += 1
    media_job_counts = Counter(str(job.get("kind", "")) for job in media_jobs)
    inventory_kind_counts = Counter(
        str(item.get("kind", "")) for item in inventory
    )
    hiragana_form_card_count = _reconcile_deck_layout_counts(
        layout=layout,
        summary=summary,
        vocabulary_notes=vocabulary_notes,
        practice_notes=practice_notes,
        table_notes=table_notes,
        kanji_notes=kanji_notes,
    )
    _reconcile_closed_input_counts(
        summary=summary,
        media_summary=media_summary,
        vocabulary_note_count=len(vocabulary_notes),
        hiragana_form_card_count=hiragana_form_card_count,
        practice_note_count=len(practice_notes),
        table_note_count=len(table_notes),
        kanji_note_count=len(kanji_notes),
        approved_example_count=approved_example_count,
        blocked_example_count=blocked_example_count,
        notes_with_examples=notes_with_examples,
        notes_without_examples=notes_without_examples,
        media_job_counts=media_job_counts,
        inventory_kind_counts=inventory_kind_counts,
    )
    _require_complete_vocabulary_examples(summary)
    _require_zero_blocked_practice(summary)
    if summary.get("grammar_note_count") != 0:
        raise DeckBuildError("grammar notes are out of scope for this package")

    source_job_names = [str(item.get("filename", "")) for item in media_jobs]
    source_inventory_names = [
        str(item.get("filename", "")) for item in inventory
    ]
    if (
        any(not name for name in source_job_names)
        or any(not name for name in source_inventory_names)
        or len(source_job_names) != len(set(source_job_names))
        or len(source_inventory_names) != len(set(source_inventory_names))
        or set(source_job_names) != set(source_inventory_names)
    ):
        raise DeckBuildError("source media jobs and inventory filenames differ")
    media_dir = media_root / MEDIA_DIR
    actual_names = {path.name for path in media_dir.iterdir() if path.is_file()}
    if actual_names != set(source_job_names):
        raise DeckBuildError("media directory contains missing or orphaned files")

    summary, practice_notes, media_jobs, inventory = _apply_package_audio_policy(
        summary=summary,
        practice_notes=practice_notes,
        media_jobs=media_jobs,
        media_inventory=inventory,
    )

    jobs_by_name: dict[str, dict[str, Any]] = {}
    for job in media_jobs:
        name = str(job.get("filename", ""))
        if not name or name in jobs_by_name or job.get("required") is not True:
            raise DeckBuildError(f"invalid or duplicate required media job: {name}")
        jobs_by_name[name] = job
    inventory_by_name: dict[str, dict[str, Any]] = {}
    for item in inventory:
        name = str(item.get("filename", ""))
        if not name or name in inventory_by_name:
            raise DeckBuildError(f"invalid or duplicate media inventory item: {name}")
        inventory_by_name[name] = item
    if set(jobs_by_name) != set(inventory_by_name):
        raise DeckBuildError("media jobs and inventory filenames differ")
    for name in sorted(jobs_by_name):
        job = jobs_by_name[name]
        item = inventory_by_name[name]
        path = media_dir / name
        common_invalid = (
            item.get("content_input_hash") != job.get("input_hash")
            or item.get("kind") != job.get("kind")
            or not path.is_file()
            or path.stat().st_size != item.get("bytes")
            or sha256_file(path) != item.get("sha256")
        )
        is_static = job.get("kind") == "kanji_static"
        static_invalid = is_static and (
            item.get("synthesis_mode") != "copy"
            or item.get("sha256") != job.get("source_sha256")
        )
        audio_invalid = not is_static and (
            item.get("synthesis_mode") not in {"word", "example"}
            or not _valid_audio(path, item)
        )
        if common_invalid or static_invalid or audio_invalid:
            raise DeckBuildError(f"required media failed hash/format binding: {name}")

    note_ids = [
        str(note.get("note_id", ""))
        for notes in (vocabulary_notes, practice_notes, table_notes, kanji_notes)
        for note in notes
    ]
    if not all(note_ids) or len(note_ids) != len(set(note_ids)):
        raise DeckBuildError("note IDs are empty or duplicated across note types")
    if any(
        note.get("card_templates")
        != [
            VOCABULARY_TEMPLATE,
            AUDIO_TEMPLATE,
            *(
                [HIRAGANA_FORM_TEMPLATE]
                if isinstance(note.get("hiragana_form_card"), Mapping)
                else []
            ),
        ]
        for note in vocabulary_notes
    ):
        raise DeckBuildError("vocabulary notes must create shared vocabulary/audio cards")
    if any(
        note.get("card_templates") != [PRACTICE_QUESTION_TEMPLATE]
        for note in practice_notes
    ):
        raise DeckBuildError("practice-question template contract changed")
    if any(note.get("card_templates") != [REFERENCE_TABLE_TEMPLATE] for note in table_notes):
        raise DeckBuildError("reference-table template contract changed")
    if any(note.get("card_templates") != [KANJI_TEMPLATE] for note in kanji_notes):
        raise DeckBuildError("kanji template contract changed")
    if any("core" in note.get("tags", []) for note in vocabulary_notes):
        raise DeckBuildError("legacy core tag remains in the release")
    if any(
        set(note).intersection({"due", "queue", "reps", "lapses", "review_log"})
        for note in kanji_notes
    ):
        raise DeckBuildError("discarded kanji scheduling data reached the builder")

    return ClosedDeckInputs(
        content_root=content_root,
        media_root=media_root,
        content_manifest=content_manifest,
        media_manifest=media_manifest,
        deck_layout=layout,
        summary=summary,
        vocabulary_notes=vocabulary_notes,
        practice_question_notes=practice_notes,
        reference_table_notes=table_notes,
        kanji_notes=kanji_notes,
        media_jobs=media_jobs,
        media_inventory=inventory,
    )


def _source_display_name(source: str) -> str:
    prefix = source.split("-", 1)[0]
    return SOURCE_DISPLAY_NAMES.get(source, SOURCE_DISPLAY_NAMES.get(prefix, source))


def _sound_tag(value: Any) -> str:
    if value in {None, ""}:
        return ""
    filename = str(value)
    if Path(filename).name != filename or not filename.endswith(AUDIO_SUFFIXES):
        raise DeckBuildError(f"unsafe sound filename: {filename}")
    return f"[sound:{filename}]"


def _click_audio_tag(value: Any) -> str:
    if value in {None, ""}:
        return ""
    filename = str(value)
    if Path(filename).name != filename or not filename.endswith(AUDIO_SUFFIXES):
        raise DeckBuildError(f"unsafe click audio filename: {filename}")
    return (
        '<audio class="click-audio-player" preload="none" '
        f'src="{html.escape(filename)}"></audio>'
    )


def _kanji_details_display_html(details: Sequence[Mapping[str, Any]]) -> str:
    normalized: list[dict[str, str]] = []
    for detail in details:
        copied = {key: str(value) for key, value in detail.items()}
        radical_parts: list[str] = []
        for part in copied.get("radical", "").split("・"):
            canonical = unicodedata.normalize("NFC", part)
            if canonical and canonical not in radical_parts:
                radical_parts.append(canonical)
        copied["radical"] = "・".join(radical_parts)
        normalized.append(copied)
    return kanji_details_html(normalized)


REGISTER_BADGE_CLASSES = {
    **{label: "is-honorific" for label in HONORIFIC_BADGE_LABELS},
    **{label: "is-style" for label in STYLE_BADGE_LABELS},
    **{label: "is-marked" for label in MARKED_BADGE_LABELS},
    **{label: "is-field" for label in DOMAIN_BADGE_LABELS},
}


def _usage_register_html(labels: Any) -> str:
    if not isinstance(labels, list) or len(labels) > 2:
        raise DeckBuildError("usage register labels must be a list of at most two")
    if len(labels) != len(set(str(label) for label in labels)):
        raise DeckBuildError("usage register labels must be unique")
    output: list[str] = []
    for raw_label in labels:
        label = str(raw_label)
        base_label = label.removesuffix(PARTIAL_LABEL_SUFFIX)
        css_class = REGISTER_BADGE_CLASSES.get(base_label)
        if css_class is None:
            raise DeckBuildError(f"unknown usage register label: {label}")
        output.append(
            f'<span class="usage-register-badge {css_class}">{html.escape(label)}</span>'
        )
    return "".join(output)


def _conjugation_details_html(conjugations: Any) -> str:
    if not isinstance(conjugations, list) or len(conjugations) > 2:
        raise DeckBuildError("conjugations must contain at most two safe paradigms")
    if not conjugations:
        return ""
    panels: list[str] = []
    identities: set[str] = set()
    for paradigm in conjugations:
        if not isinstance(paradigm, dict):
            raise DeckBuildError("conjugation paradigm must be an object")
        raw_class_label = str(paradigm.get("class_label", ""))
        if not raw_class_label:
            raise DeckBuildError("conjugation paradigm lacks class_label")
        identity = str(paradigm.get("class", raw_class_label))
        if not identity or identity in identities:
            raise DeckBuildError("conjugation paradigm classes must be unique")
        identities.add(identity)
        forms = paradigm.get("forms")
        if not isinstance(forms, list) or not forms:
            raise DeckBuildError("conjugation paradigm must contain forms")
        rows: list[str] = []
        for form in forms:
            if not isinstance(form, dict) or set(form) != {"label", "value"}:
                raise DeckBuildError("conjugation form contract changed")
            label = str(form["label"])
            value = str(form["value"])
            if not label or not value:
                raise DeckBuildError("conjugation form contains an empty value")
            rows.append(
                '<div class="conjugation-row">'
                f'<span class="conjugation-label">{html.escape(label)}</span>'
                f'<span class="conjugation-value" lang="ja">{html.escape(value)}</span>'
                "</div>"
            )
        scope = paradigm.get("scope_label")
        if scope is not None and (not isinstance(scope, str) or not scope.strip()):
            raise DeckBuildError("conjugation scope_label must be non-empty text")
        summary_parts = ["활용", raw_class_label]
        if isinstance(scope, str):
            summary_parts.append(scope)
        summary = " · ".join(html.escape(part) for part in summary_parts)
        panels.append(
            '<details class="conjugation-panel">'
            f"<summary>{summary}</summary>"
            '<div class="conjugation-body"><div class="conjugation-grid">'
            + "".join(rows)
            + "</div></div></details>"
        )
    return "".join(panels)


def _front_context_html(
    value: Any,
    *,
    target: str,
    note_id: str,
    label: str,
) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise DeckBuildError(f"invalid {label} context: {note_id}")
    context = value
    if (
        not context
        or not target
        or context.count(target) != 1
        or _HANGUL_RE.search(context)
        or any(
            character in context
            for character in _CONTEXT_ANNOTATION_CHARACTERS
        )
        or "<" in context
        or ">" in context
    ):
        raise DeckBuildError(f"invalid {label} context: {note_id}")
    before, after = context.split(target, 1)
    return (
        html.escape(before)
        + '<span class="vocabulary-context-target">'
        + html.escape(target)
        + "</span>"
        + html.escape(after)
    )


def _hiragana_form_field_values(record: Mapping[str, Any]) -> dict[str, str]:
    payload = record.get("hiragana_form_card")
    empty = {
        "WordJLPT": "",
        "HiraganaWord": "",
        "HiraganaContext": "",
    }
    if payload is None:
        return empty

    note_id = str(record.get("note_id", ""))
    expected_payload_fields = {
        "alternate_word_forms",
        "front_context",
        "front_word",
        "policy_version",
        "reading",
        "source_record_ids",
        "word_jlpt_level",
        "word_source_record_ids",
    }
    if not isinstance(payload, Mapping) or set(payload) != expected_payload_fields:
        raise DeckBuildError(f"hiragana-form card payload changed: {note_id}")

    source_level = str(record.get("jlpt_level", ""))
    word_level = payload.get("word_jlpt_level")
    word = record.get("word")
    front_word = payload.get("front_word")
    front_context = payload.get("front_context")
    reading = payload.get("reading")
    source_record_ids = payload.get("source_record_ids")
    word_source_record_ids = payload.get("word_source_record_ids")
    alternate_word_forms = payload.get("alternate_word_forms")
    forms = record.get("forms")
    form_records = forms if isinstance(forms, list) else []

    def matching_support(surface: object) -> tuple[set[str], set[str]]:
        matching_forms = [
            form
            for form in form_records
            if isinstance(form, Mapping)
            and form.get("surface") == surface
            and _reading_equivalence_key(str(form.get("reading", "")))
            == _reading_equivalence_key(str(reading))
        ]
        source_ids = {
            str(value)
            for form in matching_forms
            for value in form.get("source_record_ids", [])
            if isinstance(value, str) and value
        }
        levels = {
            str(level)
            for form in matching_forms
            for source_levels in [form.get("source_levels")]
            if isinstance(source_levels, Mapping)
            for values in source_levels.values()
            if isinstance(values, list)
            for level in values
            if str(level) in LEVELS
        }
        return source_ids, levels

    front_source_ids, front_levels = matching_support(front_word)
    selected_word_source_ids, selected_word_levels = matching_support(word)
    if (
        payload.get("policy_version") != HIRAGANA_FORM_POLICY_VERSION
        or source_level not in LEVELS
        or not isinstance(word_level, str)
        or word_level not in LEVELS
        or LEVELS.index(word_level) <= LEVELS.index(source_level)
        or not isinstance(word, str)
        or not word
        or _KANJI_CHARACTER_RE.search(word) is None
        or not isinstance(front_word, str)
        or not front_word
        or not _is_kana_only(front_word.strip("～"))
        or front_word == word
        or not isinstance(reading, str)
        or not reading
        or reading != record.get("reading")
        or not isinstance(source_record_ids, list)
        or not source_record_ids
        or any(
            not isinstance(value, str) or not value
            for value in source_record_ids
        )
        or len(source_record_ids) != len(set(source_record_ids))
        or not set(source_record_ids).issubset(front_source_ids)
        or source_level not in front_levels
        or not isinstance(word_source_record_ids, list)
        or not word_source_record_ids
        or any(
            not isinstance(value, str) or not value
            for value in word_source_record_ids
        )
        or len(word_source_record_ids) != len(set(word_source_record_ids))
        or not set(word_source_record_ids).issubset(selected_word_source_ids)
        or word_level not in selected_word_levels
        or not isinstance(alternate_word_forms, list)
        or any(
            not isinstance(value, str)
            or not value
            or value == word
            or _KANJI_CHARACTER_RE.search(value) is None
            for value in alternate_word_forms
        )
        or len(alternate_word_forms) != len(set(alternate_word_forms))
        or any(
            word_level not in matching_support(alternate)[1]
            for alternate in alternate_word_forms
        )
    ):
        raise DeckBuildError(f"invalid hiragana-form card payload: {note_id}")

    return {
        "WordJLPT": html.escape(word_level),
        "HiraganaWord": html.escape(front_word),
        "HiraganaContext": _front_context_html(
            front_context,
            target=front_word,
            note_id=note_id,
            label="hiragana",
        ),
    }


def _vocabulary_card_routes(
    record: Mapping[str, Any],
    fields: Mapping[str, str],
) -> dict[str, str]:
    level = str(record.get("jlpt_level", ""))
    if level not in LEVELS:
        raise DeckBuildError(
            f"vocabulary JLPT level changed: {record.get('note_id')}"
        )
    routes = {
        VOCABULARY_TEMPLATE: f"vocabulary:{fields['WordJLPT'] or level}",
        AUDIO_TEMPLATE: f"audio:{level}",
    }
    if fields["HiraganaWord"]:
        routes[HIRAGANA_FORM_TEMPLATE] = f"vocabulary:{level}"
    if record.get("card_templates") != list(routes) or record.get(
        "deck_keys"
    ) != list(routes.values()):
        raise DeckBuildError(
            f"vocabulary card routes changed: {record.get('note_id')}"
        )
    return routes


def _vocabulary_field_values(record: Mapping[str, Any]) -> dict[str, str]:
    examples = record.get("examples")
    if not isinstance(examples, list) or len(examples) > 4:
        raise DeckBuildError(f"invalid example list: {record.get('note_id')}")
    note_id = str(record.get("note_id", ""))
    word = str(record.get("word", ""))
    try:
        study_fields = {
            "StudyPriority": study_priority_html(record["study_priority"]),
            "UsageDetails": usage_details_html(record.get("usage_details", [])),
            "WordFormationDetails": word_formation_html(
                record.get("word_formation", []), {}
            ),
            "RelatedWords": related_words_html(record.get("related_words", []), {}),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise DeckBuildError(
            f"invalid study features: {record.get('note_id')}: {exc}"
        ) from exc
    values = {
        "EntryID": html.escape(str(record["note_id"])),
        "Word": html.escape(word),
        "VocabularyContext": _front_context_html(
            record.get("vocabulary_context", ""),
            target=word,
            note_id=note_id,
            label="vocabulary",
        ),
        "Reading": html.escape(str(record["reading"])),
        "Meaning": html.escape(str(record["meaning"])),
        "PartOfSpeech": html.escape(str(record["part_of_speech"])),
        "UsageRegister": _usage_register_html(record.get("usage_registers", [])),
        "ConjugationDetails": _conjugation_details_html(
            record.get("conjugations", [])
        ),
        "KanjiDetails": _kanji_details_display_html(
            list(record.get("kanji_details", []))
        ),
        "MeaningSource": html.escape(
            " · ".join(_source_display_name(str(value)) for value in record.get("meaning_sources", []))
        ),
        "JLPT": html.escape(str(record["jlpt_level"])),
        "Publishers": html.escape(
            " · ".join(_source_display_name(str(value)) for value in record.get("publishers", []))
        ),
        "CanonicalRecordHash": html.escape(str(record["canonical_record_hash"])),
        "WordAudio": _sound_tag(record["word_audio_filename"]),
        "WordAudioFile": _click_audio_tag(record["word_audio_filename"]),
        **_hiragana_form_field_values(record),
        **study_fields,
    }
    for index in range(1, 5):
        prefix = f"Example{index}"
        example = examples[index - 1] if index <= len(examples) else None
        if example is None:
            values.update(
                {
                    f"{prefix}{suffix}": ""
                    for suffix in (
                        "JP",
                        "Reading",
                        "KO",
                        "Sense",
                        "Audio",
                        "Source",
                        "SourceID",
                    )
                }
            )
            continue
        values.update(
            {
                f"{prefix}JP": example_display_html(dict(example)),
                f"{prefix}Reading": html.escape(str(example["reading"])),
                f"{prefix}KO": html.escape(str(example["korean"])),
                f"{prefix}Sense": html.escape(str(example["sense"])),
                f"{prefix}Audio": _click_audio_tag(example["audio_filename"]),
                f"{prefix}Source": html.escape(_source_display_name(str(example["source"]))),
                f"{prefix}SourceID": html.escape(str(example["source_id"])),
            }
        )
    return values


_QUESTION_LABELS = {
    "kanji_reading": "한자 읽기",
    "orthography": "표기",
    "word_formation": "단어 형성",
    "context_defined": "문맥 규정",
    "paraphrase": "유의 표현",
    "usage": "용법",
    "counter_reading": "수 세기",
    "date_reading": "날짜 읽기",
    "month_reading": "달 읽기",
    "weekday_reading": "요일 읽기",
}
_SEMANTIC_QUESTION_TYPES = frozenset({"context_defined", "paraphrase", "usage"})
_LEXICAL_FORM_QUESTION_TYPES = frozenset(
    {"kanji_reading", "orthography", "word_formation"}
)
_LEXICAL_FORBIDDEN_OVERLAY_FIELDS = (
    "choice_translations_ko",
)
_RENDER_SAMPLE_PRACTICE_TYPES = (
    "kanji_reading",
    "orthography",
    "word_formation",
    "context_defined",
    "paraphrase",
    "usage",
    "counter_reading",
    "month_reading",
    "weekday_reading",
    "date_reading",
)
_OPTION_MARKERS = ("①", "②", "③", "④")
_RUBY_BLOCK_RE = re.compile(r"<ruby\b[^>]*>.*?</ruby>", re.IGNORECASE | re.DOTALL)
_CANONICAL_RUBY_BLOCK_RE = re.compile(
    r"^<ruby><rb>(?P<base>.*?)</rb><rt>(?P<reading>.*?)</rt></ruby>$",
    re.DOTALL,
)
_LEXICAL_MARKED_TARGET_RE = re.compile(r"【([^【】]+)】")
_QUESTION_TARGET_OPEN = '<span class="question-target">'
_QUESTION_TARGET_CLOSE = "</span>"


def _normalized_display_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _plain_target_html(
    value: str,
    target: str,
    *,
    marked: bool = False,
) -> str:
    """Escape learner text and add only our target emphasis markup."""
    if marked:
        marker = f"【{target}】"
        if not target or value.count(marker) != 1:
            raise DeckBuildError("invalid marked practice target")
        prefix, suffix = value.split(marker, 1)
    else:
        if not target or value.count(target) != 1:
            raise DeckBuildError("ambiguous practice target span")
        prefix, suffix = value.split(target, 1)
    return (
        html.escape(prefix)
        + '<span class="question-target">'
        + html.escape(target)
        + "</span>"
        + html.escape(suffix)
    )


def _lexical_marked_target(prompt: str, question_id: str) -> str:
    matches = _LEXICAL_MARKED_TARGET_RE.findall(prompt)
    if (
        len(matches) != 1
        or prompt.count("【") != 1
        or prompt.count("】") != 1
    ):
        raise DeckBuildError(
            f"invalid lexical practice target: {question_id}"
        )
    return matches[0]


def _ruby_units(value: str) -> list[tuple[str, str, bool]]:
    """Split sanitized ruby into visible atomic text/ruby units."""
    units: list[tuple[str, str, bool]] = []
    previous = 0
    for match in _RUBY_BLOCK_RE.finditer(value):
        for character in html.unescape(value[previous : match.start()]):
            units.append((html.escape(character, quote=False), character, False))
        markup = match.group(0)
        visible = plain_japanese(markup)
        if not visible:
            raise DeckBuildError("practice ruby block lacks visible text")
        units.append((markup, visible, True))
        previous = match.end()
    for character in html.unescape(value[previous:]):
        units.append((html.escape(character, quote=False), character, False))
    return units


def _annotate_ruby_base(
    markup: str,
    visible: str,
    start: int,
    end: int,
) -> str:
    """Emphasize part of a canonical ruby base without changing its reading."""
    match = _CANONICAL_RUBY_BLOCK_RE.fullmatch(markup)
    if (
        match is None
        or html.unescape(match.group("base")) != visible
        or not 0 <= start < end <= len(visible)
    ):
        raise DeckBuildError("practice ruby base cannot be annotated safely")
    rendered = (
        "<ruby><rb>"
        + html.escape(visible[:start], quote=False)
        + _QUESTION_TARGET_OPEN
        + html.escape(visible[start:end], quote=False)
        + _QUESTION_TARGET_CLOSE
        + html.escape(visible[end:], quote=False)
        + "</rb><rt>"
        + match.group("reading")
        + "</rt></ruby>"
    )
    if plain_japanese(rendered) != visible:
        raise DeckBuildError("practice ruby base annotation changed text")
    return rendered


def _ruby_target_html(
    rendered: str,
    plain: str,
    target: str,
    *,
    marked: bool = False,
) -> str:
    """Underline an exact visible range in trusted, sanitized ruby markup."""
    sanitized = kanji_only_ruby_html(rendered)
    normalized_plain = _normalized_display_text(plain)
    if plain_japanese(sanitized) != normalized_plain:
        raise DeckBuildError("practice ruby target round-trip changed")
    if marked:
        marker = f"【{target}】"
        if not target or normalized_plain.count(marker) != 1:
            raise DeckBuildError("invalid marked practice ruby target")
        marker_start = normalized_plain.index(marker)
        start = marker_start + 1
        end = start + len(target)
        dropped_positions = {marker_start, end}
        expected_plain = normalized_plain.replace(marker, target)
    else:
        if not target or normalized_plain.count(target) != 1:
            raise DeckBuildError("ambiguous practice ruby target span")
        start = normalized_plain.index(target)
        end = start + len(target)
        dropped_positions = set()
        expected_plain = normalized_plain

    units = _ruby_units(sanitized)
    has_partial_ruby = False
    position = 0
    for _, visible, is_ruby in units:
        unit_start = position
        unit_end = position + len(visible)
        overlap_start = max(start, unit_start)
        overlap_end = min(end, unit_end)
        if (
            is_ruby
            and overlap_start < overlap_end
            and (overlap_start > unit_start or overlap_end < unit_end)
        ):
            has_partial_ruby = True
            break
        position = unit_end

    output: list[str] = []
    position = 0
    opened = False
    closed = False
    if not has_partial_ruby:
        for markup, visible, is_ruby in units:
            unit_start = position
            unit_end = position + len(visible)
            if unit_start == start:
                output.append(_QUESTION_TARGET_OPEN)
                opened = True
            if is_ruby:
                output.append(markup)
            elif unit_start not in dropped_positions:
                output.append(markup)
            if unit_end == end:
                output.append(_QUESTION_TARGET_CLOSE)
                closed = True
            position = unit_end
        if not opened or not closed or plain_japanese("".join(output)) != expected_plain:
            raise DeckBuildError("practice ruby target annotation changed text")
        return "".join(output)

    outer_open = False
    annotated = False
    for markup, visible, is_ruby in units:
        unit_start = position
        unit_end = position + len(visible)
        overlap_start = max(start, unit_start)
        overlap_end = min(end, unit_end)
        overlaps = overlap_start < overlap_end
        partial_ruby = is_ruby and overlaps and (
            overlap_start > unit_start or overlap_end < unit_end
        )
        if partial_ruby:
            if outer_open:
                output.append(_QUESTION_TARGET_CLOSE)
                outer_open = False
            output.append(
                _annotate_ruby_base(
                    markup,
                    visible,
                    overlap_start - unit_start,
                    overlap_end - unit_start,
                )
            )
            annotated = True
        elif overlaps:
            if not outer_open:
                output.append(_QUESTION_TARGET_OPEN)
                outer_open = True
            if is_ruby or unit_start not in dropped_positions:
                output.append(markup)
            annotated = True
        else:
            if outer_open:
                output.append(_QUESTION_TARGET_CLOSE)
                outer_open = False
            if is_ruby or unit_start not in dropped_positions:
                output.append(markup)
        position = unit_end
    if outer_open:
        output.append(_QUESTION_TARGET_CLOSE)
    if not annotated or plain_japanese("".join(output)) != expected_plain:
        raise DeckBuildError("practice ruby target annotation changed text")
    return "".join(output)


def _practice_question_field_values(record: Mapping[str, Any]) -> dict[str, str]:
    question_id = str(record.get("question_id", ""))
    question_type = str(record.get("question_type", ""))
    label = _QUESTION_LABELS.get(question_type)
    if not question_id or label is None:
        raise DeckBuildError(f"invalid practice question: {question_id}")
    expected_sort_key = practice_sort_key(record)
    if record.get("sort_key") not in {None, expected_sort_key}:
        raise DeckBuildError(f"stale practice sort key: {question_id}")
    raw_choices = record.get("choices", [])
    if not isinstance(raw_choices, list):
        raise DeckBuildError(f"invalid practice choices: {question_id}")
    choices = [str(choice) for choice in raw_choices]
    if choices and (len(choices) != 4 or len(set(choices)) != 4):
        raise DeckBuildError(f"practice choices changed: {question_id}")

    def ruby_value(field: str, plain: str) -> str:
        raw = record.get(field)
        if raw in {None, ""}:
            return html.escape(plain)
        rendered = kanji_only_ruby_html(str(raw))
        if plain_japanese(rendered) != re.sub(r"\s+", " ", plain).strip():
            raise DeckBuildError(
                f"practice ruby round-trip changed: {question_id}/{field}"
            )
        if "（　）" in plain:
            normalized_blank = "（ ）"
            if rendered.count(normalized_blank) != plain.count("（　）"):
                raise DeckBuildError(
                    f"practice ruby blank changed: {question_id}/{field}"
                )
            rendered = rendered.replace(normalized_blank, "（　）")
        return rendered

    def exact_ruby_value(field: str, plain: str) -> str:
        raw = record.get(field)
        if not isinstance(raw, str) or not raw:
            raise DeckBuildError(
                f"practice exact ruby is missing: {question_id}/{field}"
            )
        rendered = safe_ruby_html(raw)
        if plain_japanese(rendered) != re.sub(r"\s+", " ", plain).strip():
            raise DeckBuildError(
                f"practice exact ruby round-trip changed: {question_id}/{field}"
            )
        return rendered

    def choices_list_html(
        values: Sequence[str],
        *,
        correct_index: int | None = None,
        translations: Sequence[str] | None = None,
    ) -> str:
        if not values:
            return ""
        if translations is not None and len(translations) != len(values):
            raise DeckBuildError(
                f"practice choice translations changed: {question_id}"
            )
        return '<ol class="question-options">' + "".join(
            '<li class="question-option'
            + (" is-correct" if index == correct_index else "")
            + '">'
            '<span class="question-option-marker">'
            f'<span class="question-option-marker-glyph">{_OPTION_MARKERS[index]}</span>'
            "</span>"
            '<span class="question-option-content">'
            f'<span class="question-option-copy" lang="ja">{choice}</span>'
            + (
                f'<span class="question-option-translation" lang="ko">'
                f'{translations[index]}</span>'
                if translations is not None
                else ""
            )
            + "</span>"
            "</li>"
            for index, choice in enumerate(values)
        ) + "</ol>"

    raw_ruby_choices = record.get("choices_ruby")
    if raw_ruby_choices is None:
        ruby_choices = [html.escape(choice) for choice in choices]
    elif (
        not isinstance(raw_ruby_choices, list)
        or len(raw_ruby_choices) != len(choices)
    ):
        raise DeckBuildError(f"practice ruby choices changed: {question_id}")
    else:
        ruby_choices = [
            kanji_only_ruby_html(str(raw_ruby_choices[index]))
            for index in range(len(choices))
        ]
        if any(
            plain_japanese(rendered) != re.sub(r"\s+", " ", plain).strip()
            for rendered, plain in zip(ruby_choices, choices, strict=True)
        ):
            raise DeckBuildError(
                f"practice ruby choice round-trip changed: {question_id}"
            )

    semantic_type = question_type in _SEMANTIC_QUESTION_TYPES
    lexical_type = question_type in _LEXICAL_FORM_QUESTION_TYPES
    lexical_answer_word_ruby = ""
    lexical_answer_word_meaning = ""
    correct_index_raw = record.get("correct_index")
    target = str(record.get("target_jp", ""))
    prompt = str(record.get("prompt_jp", ""))
    prompt_ko = str(record.get("prompt_ko", ""))
    choice_target_spans = record.get("choice_target_spans", [])
    if semantic_type:
        if (
            len(choices) != 4
            or not isinstance(correct_index_raw, int)
            or isinstance(correct_index_raw, bool)
            or not 0 <= correct_index_raw < 4
            or not target
            or not prompt
            or not prompt_ko
            or not isinstance(choice_target_spans, list)
        ):
            raise DeckBuildError(f"incomplete JLPT practice question: {question_id}")
        try:
            for field_name, value in (
                ("prompt_ko", prompt_ko),
                ("answer_ko", record.get("answer_ko")),
                ("explanation_ko", record.get("explanation_ko")),
            ):
                validate_learner_visible_korean_prose(
                    str(value or ""),
                    field_name=field_name,
                )
            for index, value in enumerate(record.get("choice_notes_ko", [])):
                validate_learner_visible_korean_prose(
                    str(value),
                    field_name=f"choice_notes_ko[{index}]",
                )
        except LexicalFormQuestionContractError as exc:
            raise DeckBuildError(
                f"learner-visible practice provenance leaked: {question_id}"
            ) from exc
        correct_index: int | None = correct_index_raw
    elif lexical_type:
        answer_jp = str(record.get("answer_jp", ""))
        answer_ko = str(record.get("answer_ko", ""))
        explanation_ko = str(record.get("explanation_ko", ""))
        prompt_instruction = str(record.get("prompt_instruction", ""))
        prompt_jp_ruby = record.get("prompt_jp_ruby")
        prompt_ko_ruby = record.get("prompt_ko_ruby")
        source_id = record.get("source_id")
        source_page = record.get("source_page")
        source_reference_id = record.get("source_reference_id")
        notes = record.get("choice_notes_ko")
        answer_word_jp = record.get("answer_word_jp")
        answer_word_reading = record.get("answer_word_reading")
        covered_targets = record.get("covered_targets")
        canonical_meanings = (
            {
                target.get("canonical_meaning")
                for target in covered_targets
                if isinstance(target, Mapping)
                and isinstance(target.get("canonical_meaning"), str)
                and target.get("canonical_meaning")
            }
            if isinstance(covered_targets, list)
            else set()
        )
        if (
            len(choices) != 4
            or not isinstance(correct_index_raw, int)
            or isinstance(correct_index_raw, bool)
            or not 0 <= correct_index_raw < 4
            or not prompt
            or not prompt_ko
            or not answer_jp
            or answer_jp != choices[correct_index_raw]
            or (question_type != "word_formation" and answer_jp in prompt)
            or not answer_ko
            or not explanation_ko
            or not prompt_instruction
            or prompt_ko == prompt_instruction
            or not isinstance(prompt_jp_ruby, str)
            or not prompt_jp_ruby
            or not isinstance(prompt_ko_ruby, str)
            or not prompt_ko_ruby
            or not isinstance(source_id, str)
            or not source_id
            or not isinstance(source_page, int)
            or isinstance(source_page, bool)
            or source_page <= 0
            or not isinstance(source_reference_id, str)
            or not source_reference_id
            or not isinstance(notes, list)
            or len(notes) != 4
            or any(not isinstance(note, str) or not note for note in notes)
            or any(
                record.get(field) is not None and record.get(field) != ""
                for field in _LEXICAL_FORBIDDEN_OVERLAY_FIELDS
            )
            or not isinstance(answer_word_jp, str)
            or not answer_word_jp
            or not isinstance(answer_word_reading, str)
            or not answer_word_reading
            or len(canonical_meanings) != 1
        ):
            raise DeckBuildError(
                f"incomplete lexical practice question: {question_id}"
            )
        lexical_question = {
            field: record.get(field) for field in LEXICAL_QUESTION_FIELDS
        }
        try:
            normalized_question = validate_approved_lexical_question(
                lexical_question,
                record,
            )
        except LexicalFormQuestionContractError as exc:
            raise DeckBuildError(
                f"invalid lexical practice pedagogy: {question_id}"
            ) from exc
        if normalized_question != lexical_question:
            raise DeckBuildError(
                f"normalized lexical practice question changed: {question_id}"
            )
        lexical_answer_word_ruby = exact_ruby_value(
            "answer_word_jp_ruby", answer_word_jp
        )
        lexical_answer_word_meaning = next(iter(canonical_meanings))
        front_payload = "\n".join([prompt, prompt_instruction])
        for leaked_value in (
            explanation_ko,
            str(record.get("answer_audio_filename", "")),
        ):
            if leaked_value and leaked_value in front_payload:
                raise DeckBuildError(
                    f"lexical practice answer leaked to front: {question_id}"
                )
        if question_type == "word_formation":
            formed_surface = record.get("formed_surface")
            formed_reading = record.get("formed_reading")
            if (
                prompt.count("（　）") != 1
                or not isinstance(formed_surface, str)
                or not formed_surface.strip()
                or formed_surface != formed_surface.strip()
                or not isinstance(formed_reading, str)
                or not formed_reading.strip()
                or formed_reading != formed_reading.strip()
                or formed_surface in prompt
                or prompt.replace("（　）", answer_jp).count(formed_surface) != 1
                or formed_surface != answer_word_jp
                or formed_reading != answer_word_reading
            ):
                raise DeckBuildError(
                    f"invalid word-formation rendering: {question_id}"
                )
        if question_type in {"kanji_reading", "orthography"}:
            marked_target = _lexical_marked_target(prompt, question_id)
            if (
                question_type == "kanji_reading"
                and (
                    marked_target != answer_word_jp
                    or answer_jp != answer_word_reading
                )
            ) or (
                question_type == "orthography"
                and (
                    marked_target != answer_word_reading
                    or answer_jp != answer_word_jp
                )
            ):
                raise DeckBuildError(
                    f"lexical answer word binding changed: {question_id}"
                )
        correct_index = correct_index_raw
    else:
        correct_index = (
            correct_index_raw
            if isinstance(correct_index_raw, int)
            and not isinstance(correct_index_raw, bool)
            and 0 <= correct_index_raw < len(choices)
            else None
        )
    if semantic_type:
        raw_choice_translations = record.get("choice_translations_ko")
        if (
            not isinstance(raw_choice_translations, list)
            or len(raw_choice_translations) != 4
            or any(
                not isinstance(translation, str) or not translation
                for translation in raw_choice_translations
            )
        ):
            raise DeckBuildError(
                f"practice choice translations changed: {question_id}"
            )
        choice_translations = [
            html.escape(translation) for translation in raw_choice_translations
        ]
    else:
        choice_translations = None

    prompt_ruby_plain = ruby_value("prompt_jp_ruby", prompt)
    if question_type in {"kanji_reading", "orthography"}:
        lexical_target = _lexical_marked_target(prompt, question_id)
        prompt_html = _plain_target_html(prompt, lexical_target, marked=True)
        prompt_ruby_html = _ruby_target_html(
            prompt_ruby_plain,
            prompt,
            lexical_target,
            marked=True,
        )
        choice_front_values = [html.escape(choice) for choice in choices]
        choice_back_values = ruby_choices
    elif question_type in {"context_defined", "word_formation"}:
        if prompt.count("（　）") != 1 or choice_target_spans:
            raise DeckBuildError(f"invalid blank rendering: {question_id}")
        prompt_html = html.escape(prompt).replace(
            "（　）", '<span class="question-blank">(　)</span>'
        )
        prompt_ruby_html = prompt_ruby_plain.replace(
            "（　）", '<span class="question-blank">(　)</span>'
        )
        choice_front_values = [html.escape(choice) for choice in choices]
        choice_back_values = ruby_choices
    elif question_type == "paraphrase":
        if choice_target_spans:
            raise DeckBuildError(f"invalid paraphrase target spans: {question_id}")
        prompt_html = _plain_target_html(prompt, target, marked=True)
        prompt_ruby_html = _ruby_target_html(
            prompt_ruby_plain,
            prompt,
            target,
            marked=True,
        )
        choice_front_values = [html.escape(choice) for choice in choices]
        choice_back_values = ruby_choices
    elif question_type == "usage":
        if prompt != target or len(choice_target_spans) != 4:
            raise DeckBuildError(f"invalid usage rendering: {question_id}")
        if any(not isinstance(span, str) for span in choice_target_spans):
            raise DeckBuildError(f"invalid usage target span: {question_id}")
        prompt_html = (
            '<span class="question-target-word">'
            + html.escape(target)
            + "</span>"
        )
        prompt_ruby_html = (
            '<span class="question-target-word">'
            + prompt_ruby_plain
            + "</span>"
        )
        choice_front_values = [
            _plain_target_html(choice, span)
            for choice, span in zip(choices, choice_target_spans, strict=True)
        ]
        choice_back_values = [
            _ruby_target_html(rendered, choice, span)
            for rendered, choice, span in zip(
                ruby_choices, choices, choice_target_spans, strict=True
            )
        ]
    else:
        prompt_html = html.escape(prompt)
        prompt_ruby_html = prompt_ruby_plain
        choice_front_values = [html.escape(choice) for choice in choices]
        choice_back_values = ruby_choices

    choices_html = choices_list_html(choice_front_values)
    choices_ruby_html = choices_list_html(
        choice_back_values,
        correct_index=correct_index if semantic_type or lexical_type else None,
        translations=choice_translations,
    )

    explanation_html = ""
    explanation_ruby_html = ""
    answer_ko = str(record.get("answer_ko", ""))
    answer_ko_ruby = ruby_value("answer_ko_ruby", answer_ko)
    if semantic_type or lexical_type:
        notes = record.get("choice_notes_ko")
        if not isinstance(notes, list) or len(notes) != 4:
            raise DeckBuildError(
                f"practice choice explanations changed: {question_id}"
            )
        explanation_html = (
            f'<div>{html.escape(str(record.get("explanation_ko", "")))}</div>'
            + '<ol class="choice-notes">'
            + "".join(
                '<li class="choice-note">'
                '<span class="choice-note-marker">'
                f'<span class="choice-note-marker-glyph">{_OPTION_MARKERS[index]}</span>'
                "</span>"
                f'<span>{html.escape(str(note))}</span>'
                "</li>"
                for index, note in enumerate(notes)
            )
            + "</ol>"
        )
        raw_ruby_notes = record.get("choice_notes_ko_ruby")
        if raw_ruby_notes is None:
            ruby_notes = [html.escape(str(note)) for note in notes]
        elif not isinstance(raw_ruby_notes, list) or len(raw_ruby_notes) != 4:
            raise DeckBuildError(
                f"practice ruby choice explanations changed: {question_id}"
            )
        else:
            ruby_notes = [
                kanji_only_ruby_html(str(value)) for value in raw_ruby_notes
            ]
            if any(
                plain_japanese(rendered)
                != re.sub(r"\s+", " ", str(plain)).strip()
                for rendered, plain in zip(ruby_notes, notes, strict=True)
            ):
                raise DeckBuildError(
                    f"practice ruby explanation round-trip changed: {question_id}"
                )
        rendered_explanation = ruby_value(
            "explanation_ko_ruby", str(record.get("explanation_ko", ""))
        )
        explanation_ruby_html = (
            f"<div>{rendered_explanation}</div>"
            + '<ol class="choice-notes">'
            + "".join(
                '<li class="choice-note">'
                '<span class="choice-note-marker">'
                f'<span class="choice-note-marker-glyph">{_OPTION_MARKERS[index]}</span>'
                "</span>"
                f'<span>{note}</span>'
                "</li>"
                for index, note in enumerate(ruby_notes)
            )
            + "</ol>"
        )
    source_id = str(record.get("source_id", ""))
    source_page = record.get("source_page")
    return {
        "AnswerJP": html.escape(str(record.get("answer_jp", ""))),
        "AnswerKO": html.escape(answer_ko),
        "AnswerRuby": (
            lexical_answer_word_ruby
            if lexical_type
            else ruby_value("answer_jp_ruby", str(record.get("answer_jp", "")))
        ),
        "AnswerKORuby": (
            html.escape(lexical_answer_word_meaning)
            if lexical_type
            else answer_ko_ruby
        ),
        "ChoicesHTML": choices_html,
        "ChoicesRubyHTML": choices_ruby_html,
        "ExplanationHTML": explanation_html,
        "ExplanationRubyHTML": explanation_ruby_html,
        "Instruction": html.escape(str(record.get("prompt_instruction", ""))),
        "JLPT": html.escape(str(record.get("jlpt_level", ""))),
        "PromptJP": prompt_html,
        "PromptKO": html.escape(prompt_ko),
        "PromptRuby": prompt_ruby_html,
        "PromptKORuby": ruby_value("prompt_ko_ruby", prompt_ko),
        "QuestionID": html.escape(question_id),
        "SortKey": html.escape(expected_sort_key),
        "QuestionLabel": html.escape(label),
        "QuestionType": html.escape(question_type),
        "Source": html.escape(_source_display_name(source_id)),
        "SourcePage": html.escape("" if source_page is None else str(source_page)),
        "SourceReferenceID": html.escape(
            str(record.get("source_reference_id", ""))
        ),
        "AnswerAudio": _sound_tag(record.get("answer_audio_filename", "")),
    }


_COUNTER_CELL = re.compile(r"^matrix-r(?P<row>\d+)-c(?P<column>\d+)$")
_CALENDAR_CELL = re.compile(
    r"^calendar-t(?P<table>\d+)-r(?P<row>\d+)-c(?P<column>\d+)$"
)


def _reference_cell_parts(value: str) -> tuple[str, str]:
    semantic = re.search(r"[0-9가-힣]", value)
    if semantic is None or semantic.start() == 0:
        return value.strip(), ""
    return value[: semantic.start()].strip(), value[semantic.start() :].strip()


def _reference_audio_copy(
    content: str,
    audio_filename: Any,
    *,
    css_class: str,
    aria_label: str,
) -> str:
    if audio_filename in {None, ""}:
        return f'<span class="{css_class}" lang="ja">{content}</span>'
    filename = str(audio_filename)
    if Path(filename).name != filename or not filename.endswith(AUDIO_SUFFIXES):
        raise DeckBuildError(f"unsafe click audio filename: {filename}")
    return (
        f'<span class="{css_class} audio-scope">'
        '<span class="audio-trigger" role="button" tabindex="0" '
        f'aria-label="{html.escape(aria_label)}" lang="ja">{content}</span>'
        f'<audio class="click-audio-player" preload="none" '
        f'src="{html.escape(filename)}"></audio></span>'
    )


def _counter_reference_html(
    rows: Mapping[int, Mapping[int, str]],
    audio_by_cell: Mapping[tuple[int, int], str],
) -> str:
    columns = sorted(rows.get(0, {}))
    expected_row_columns = {0, *columns}
    if (
        set(rows) != set(range(12))
        or not 1 <= len(columns) <= 2
        or any(column not in range(1, 6) for column in columns)
        or any(set(rows[row]) != expected_row_columns for row in range(1, 12))
    ):
        raise DeckBuildError("counter reference grid is incomplete")
    groups: list[str] = []
    for column in columns:
        output = [
            '<section class="reference-group">',
            '<div class="reference-group-heading">',
            _reference_audio_copy(
                html.escape(rows[0][column]),
                audio_by_cell.get((0, column), ""),
                css_class="reference-group-title",
                aria_label="분류 음성 재생",
            ),
            '<span class="reference-group-count">11개</span>',
            "</div><div class=\"reference-rows\">",
        ]
        for row in range(1, 12):
            output.extend(
                (
                    '<div class="reference-row">',
                    _reference_audio_copy(
                        html.escape(rows[row][0]),
                        audio_by_cell.get((row, 0), ""),
                        css_class="reference-key",
                        aria_label="수 음성 재생",
                    ),
                    _reference_audio_copy(
                        html.escape(rows[row][column]),
                        audio_by_cell.get((row, column), ""),
                        css_class="reference-value",
                        aria_label="수량 표현 음성 재생",
                    ),
                    "</div>",
                )
            )
        output.append("</div></section>")
        groups.append("".join(output))
    return "".join(groups)


def _calendar_reference_group(
    title: str,
    values: Sequence[tuple[str, str]],
) -> str:
    cells: list[str] = []
    for value, audio_filename in values:
        japanese, korean = _reference_cell_parts(value)
        japanese_html = _reference_audio_copy(
            html.escape(japanese),
            audio_filename,
            css_class="reference-cell-jp",
            aria_label=f"{japanese} 음성 재생",
        )
        cells.append(
            '<div class="reference-cell">'
            + japanese_html
            + (
                f'<div class="reference-cell-ko">{html.escape(korean)}</div>'
                if korean
                else ""
            )
            + "</div>"
        )
    return (
        '<section class="reference-group">'
        '<div class="reference-group-heading">'
        f"<span>{html.escape(title)}</span>"
        f'<span class="reference-group-count">{len(values)}개</span>'
        "</div>"
        '<div class="reference-calendar-grid">'
        + "".join(cells)
        + "</div></section>"
    )


def _reference_table_field_values(record: Mapping[str, Any]) -> dict[str, str]:
    cells = record.get("cells")
    if not isinstance(cells, list):
        raise DeckBuildError(f"invalid reference table: {record.get('note_id')}")
    accepted = [cell for cell in cells if isinstance(cell, dict) and cell.get("status") == "accepted"]
    if len(accepted) != record.get("packaged_cell_count"):
        raise DeckBuildError(f"reference table disposition mismatch: {record.get('note_id')}")
    table_kind = str(record["table_kind"])
    if table_kind == "counter_matrix":
        rows: dict[int, dict[int, str]] = defaultdict(dict)
        audio_by_cell: dict[tuple[int, int], str] = {}
        for cell in accepted:
            match = _COUNTER_CELL.fullmatch(str(cell["row_id"]))
            if match is None:
                raise DeckBuildError(f"invalid counter cell: {cell['cell_id']}")
            position = (int(match.group("row")), int(match.group("column")))
            rows[position[0]][position[1]] = str(cell["normalized_text"])
            audio_by_cell[position] = str(cell.get("audio_filename", ""))
        table_html = _counter_reference_html(rows, audio_by_cell)
    elif table_kind == "calendar_grid":
        groups: dict[int, dict[int, dict[int, str]]] = defaultdict(lambda: defaultdict(dict))
        audio_by_position: dict[tuple[int, int, int], str] = {}
        for cell in accepted:
            match = _CALENDAR_CELL.fullmatch(str(cell["row_id"]))
            if match is None:
                raise DeckBuildError(f"invalid calendar cell: {cell['cell_id']}")
            position = (
                int(match.group("table")),
                int(match.group("row")),
                int(match.group("column")),
            )
            groups[position[0]][position[1]][position[2]] = str(
                cell["normalized_text"]
            )
            audio_by_position[position] = str(cell.get("audio_filename", ""))
        if set(groups) != {0, 1}:
            raise DeckBuildError("calendar reference groups are incomplete")
        month_values = [
            (
                groups[0][row][column],
                audio_by_position.get((0, row, column), ""),
            )
            for row in sorted(groups[0])
            for column in sorted(groups[0][row])
        ]
        weekday_values = [
            (
                groups[1][0][column],
                audio_by_position.get((1, 0, column), ""),
            )
            for column in sorted(groups[1][0])
        ]
        date_values = [
            (
                groups[1][row][column],
                audio_by_position.get((1, row, column), ""),
            )
            for row in sorted(groups[1])
            if row != 0
            for column in sorted(groups[1][row])
        ]
        if (
            len(month_values) != 12
            or len(weekday_values) != 7
            or len(date_values) != 31
        ):
            raise DeckBuildError("calendar reference cells are incomplete")
        table_html = "".join(
            (
                _calendar_reference_group("월", month_values),
                _calendar_reference_group("요일", weekday_values),
                _calendar_reference_group("날짜", date_values),
            )
        )
    else:
        raise DeckBuildError(f"unknown reference table kind: {table_kind}")
    return {
        "ReferenceID": html.escape(str(record["reference_id"])),
        "Title": html.escape(str(record["title"])),
        "PartLabel": html.escape(str(record.get("part_label", ""))),
        "JLPT": html.escape(str(record["jlpt_level"])),
        "TableKind": html.escape(table_kind),
        "TableHTML": table_html,
        "Source": html.escape(_source_display_name(str(record["source_id"]))),
        "SourcePage": html.escape(str(record["source_page"])),
    }


def _kanji_sort_key(record: Mapping[str, Any]) -> str:
    note_id = str(record.get("note_id", ""))
    sequence = record.get("sequence")
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or not 1 <= sequence <= 999_999
    ):
        raise DeckBuildError(
            f"invalid kanji sequence for sort key: {note_id}: {sequence!r}"
        )
    return f"K{sequence:06d}"


def _kanji_field_values(record: Mapping[str, Any]) -> dict[str, str]:
    note_id = str(record.get("note_id", ""))
    provenance = record.get("source_provenance")
    if not isinstance(provenance, Mapping):
        raise DeckBuildError(f"kanji provenance is missing: {note_id}")
    try:
        return {
            "GlyphHTML": kanji_display_html(
                str(record.get("glyph_text", "")),
                str(record.get("glyph_media_filename", "")),
            ),
            "KanjiID": html.escape(note_id),
            "KanjiReference": kanji_reference_html(
                record.get("kanji_reference", {})
            ),
            "LinkedVocabulary": linked_vocabulary_html(
                record.get("linked_vocabulary", [])
            ),
            "Meaning": html.escape(str(record.get("meaning", ""))),
            "SourceFingerprint": html.escape(
                str(provenance.get("source_fingerprint", ""))
            ),
            "SortKey": _kanji_sort_key(record),
            "Theme": html.escape(str(record.get("theme", ""))),
            "Unit": html.escape(str(record.get("unit", ""))),
            "Volume": html.escape(str(record.get("volume", ""))),
        }
    except (TypeError, ValueError) as exc:
        raise DeckBuildError(f"invalid kanji rendering: {note_id}: {exc}") from exc


def create_decks(
    collection: Collection, layout: Mapping[str, Any]
) -> dict[str, DeckId]:
    _validate_deck_layout(layout)
    config_ids = create_deck_configs(collection)
    result: dict[str, DeckId] = {}
    for item in layout["decks"]:
        key = str(item["key"])
        deck = collection.decks.new_deck_legacy(False)
        deck["id"] = DECK_IDS[key]
        deck["name"] = str(item["name"])
        deck["conf"] = config_ids[_deck_config_policy(key)]
        deck["collapsed"] = bool(item["collapsed"])
        deck["browserCollapsed"] = bool(item["browser_collapsed"])
        collection.decks.update(deck)
        result[key] = DECK_IDS[key]
    return result


def _deck_config_policy(deck_key: str) -> str:
    if deck_key == "audio" or deck_key.startswith("audio:"):
        return "audio"
    if deck_key == "practice" or deck_key.startswith("practice:"):
        return "practice"
    if (
        deck_key == "reference_table"
        or deck_key == "kanji"
        or deck_key.startswith("kanji:")
    ):
        return "reference"
    return "vocabulary"


def _apply_deck_config_defaults(config: dict[str, Any], policy: str) -> None:
    if policy not in DECK_CONFIG_IDS:
        raise DeckBuildError(f"unknown deck config policy: {policy}")
    config["id"] = DECK_CONFIG_IDS[policy]
    config["name"] = DECK_CONFIG_NAMES[policy]
    config["autoplay"] = DECK_CONFIG_AUTOPLAY[policy]
    config["replayq"] = False
    config["desiredRetention"] = 0.9
    config["fsrsParams5"] = []
    config["fsrsParams6"] = []
    config["fsrsWeights"] = []
    config["new"]["delays"] = [10.0]
    config["new"]["perDay"] = 20
    config["new"]["order"] = 1
    config["new"]["bury"] = True
    config["newGatherPriority"] = 0
    config["newSortOrder"] = 1
    config["newMix"] = 1
    config["lapse"]["delays"] = [10.0]
    config["lapse"]["leechFails"] = 8
    config["lapse"]["leechAction"] = 1
    config["rev"]["bury"] = True
    config["rev"]["perDay"] = 9999
    config["rev"]["maxIvl"] = 36500
    config["buryInterdayLearning"] = True


def _deck_config_matches_defaults(config: Mapping[str, Any], policy: str) -> bool:
    try:
        return bool(
            config.get("name") == DECK_CONFIG_NAMES[policy]
            and config.get("autoplay") is DECK_CONFIG_AUTOPLAY[policy]
            and config.get("replayq") is False
            and config.get("desiredRetention") == 0.9
            and config.get("fsrsParams5") == []
            and config.get("fsrsParams6") == []
            and config.get("fsrsWeights") == []
            and config["new"]["delays"] == [10.0]
            and config["new"]["perDay"] == 20
            and config["new"]["order"] == 1
            and config["new"]["bury"] is True
            and config.get("newGatherPriority") == 0
            and config.get("newSortOrder") == 1
            and config.get("newMix") == 1
            and config["lapse"]["delays"] == [10.0]
            and config["lapse"]["leechFails"] == 8
            and config["lapse"]["leechAction"] == 1
            and config["rev"]["bury"] is True
            and config["rev"]["perDay"] == 9999
            and config["rev"]["maxIvl"] == 36500
            and config.get("buryInterdayLearning") is True
        )
    except (KeyError, TypeError):
        return False


def create_deck_configs(collection: Collection) -> dict[str, DeckConfigId]:
    """Install stable FSRS-ready presets without changing global FSRS state."""
    default = collection.decks.get_config(DEFAULT_DECK_CONF_ID)
    if default is None:
        raise DeckBuildError("default Anki deck config is missing")
    result: dict[str, DeckConfigId] = {}
    for policy in DECK_CONFIG_IDS:
        config = copy.deepcopy(default)
        _apply_deck_config_defaults(config, policy)
        collection.decks.update_config(config)
        saved = collection.decks.get_config(DECK_CONFIG_IDS[policy])
        if saved is None or not _deck_config_matches_defaults(saved, policy):
            raise DeckBuildError(f"failed to install deck config: {policy}")
        result[policy] = DECK_CONFIG_IDS[policy]
    return result


def create_notetype(collection: Collection, spec: NotetypeSpec) -> NotetypeDict:
    notetype = collection.models.new(spec.name)
    for name in spec.fields:
        field = collection.models.new_field(name)
        field["id"] = FIELD_IDS[spec.kind][name]
        collection.models.add_field(notetype, field)
    notetype["sortf"] = spec.fields.index(spec.sort_field)
    for template_name, question, answer in spec.templates:
        template = collection.models.new_template(template_name)
        template["id"] = TEMPLATE_IDS[template_name]
        template["qfmt"] = question
        template["afmt"] = answer
        collection.models.add_template(notetype, template)
    notetype["css"] = spec.css
    temporary_id = NotetypeId(collection.models.add(notetype).id)
    saved = collection.models.get(temporary_id)
    if saved is None:
        raise DeckBuildError(f"failed to create note type: {spec.name}")
    collection.models.remove(temporary_id)
    saved["id"] = NOTETYPE_IDS[spec.kind]
    saved["name"] = spec.name
    for field in saved["flds"]:
        field["id"] = FIELD_IDS[spec.kind][field["name"]]
    for template in saved["tmpls"]:
        template["id"] = TEMPLATE_IDS[template["name"]]
    collection.models.update(saved)
    canonical = collection.models.get(NOTETYPE_IDS[spec.kind])
    if canonical is None:
        raise DeckBuildError(f"failed to install canonical note type: {spec.name}")
    return canonical


def assert_collection_identity(
    collection: Collection,
    layout: Mapping[str, Any],
    *,
    require_deck_ids: bool = True,
    require_display_state: bool = True,
) -> None:
    for kind, spec in NOTETYPE_SPECS.items():
        notetype = collection.models.by_name(spec.name)
        if notetype is None or int(notetype["id"]) != NOTETYPE_IDS[kind]:
            raise DeckBuildError(f"canonical note type ID changed: {spec.name}")
        actual_fields = {field["name"]: int(field["id"]) for field in notetype["flds"]}
        actual_templates = {
            template["name"]: int(template["id"])
            for template in notetype["tmpls"]
        }
        if actual_fields != FIELD_IDS[kind]:
            raise DeckBuildError(f"canonical field IDs changed: {spec.name}")
        if actual_templates != {
            name: TEMPLATE_IDS[name] for name, _, _ in spec.templates
        }:
            raise DeckBuildError(f"canonical template IDs changed: {spec.name}")
    expected_names = {
        str(item["key"]): str(item["name"]) for item in layout["decks"]
    }
    actual = {
        key: int(collection.decks.id_for_name(name) or 0)
        for key, name in expected_names.items()
    }
    if require_deck_ids and actual != DECK_IDS:
        raise DeckBuildError("canonical deck IDs changed")
    for policy, config_id in DECK_CONFIG_IDS.items():
        config = collection.decks.get_config(config_id)
        if config is None or not _deck_config_matches_defaults(config, policy):
            raise DeckBuildError(f"canonical deck config changed: {policy}")
    for key, name in expected_names.items():
        deck_id = collection.decks.id_for_name(name)
        if deck_id is None:
            raise DeckBuildError(f"canonical deck is missing: {key}")
        deck = collection.decks.get(deck_id, default=False)
        item = next(
            layout_item
            for layout_item in layout["decks"]
            if layout_item["key"] == key
        )
        if deck is None:
            raise DeckBuildError(f"canonical deck is missing: {key}")
        if int(deck.get("conf", 0)) != DECK_CONFIG_IDS[_deck_config_policy(key)]:
            raise DeckBuildError(f"deck config assignment changed: {key}")
        if require_display_state and (
            bool(deck.get("collapsed", False)) is not bool(item["collapsed"])
            or bool(deck.get("browserCollapsed", False))
            is not bool(item["browser_collapsed"])
        ):
            raise DeckBuildError(f"deck display state changed: {key}")


def deck_display_state_differences(
    collection: Collection,
    layout: Mapping[str, Any],
) -> list[str]:
    """Return layout deck keys whose profile-local collapse state differs."""
    differences: list[str] = []
    for item in layout["decks"]:
        deck = collection.decks.by_name(str(item["name"]))
        if deck is None or (
            bool(deck.get("collapsed", False)) is not bool(item["collapsed"])
            or bool(deck.get("browserCollapsed", False))
            is not bool(item["browser_collapsed"])
        ):
            differences.append(str(item["key"]))
    return differences


def apply_deck_display_state(
    collection: Collection,
    layout: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply the manifest's profile-local deck collapse state after import."""
    _validate_deck_layout(layout)
    for item in layout["decks"]:
        key = str(item["key"])
        deck = collection.decks.by_name(str(item["name"]))
        if deck is None:
            raise DeckBuildError(f"canonical deck is missing: {key}")
        deck["collapsed"] = bool(item["collapsed"])
        deck["browserCollapsed"] = bool(item["browser_collapsed"])
        collection.decks.update(deck)
    assert_collection_identity(
        collection,
        layout,
        require_deck_ids=False,
        require_display_state=True,
    )
    return {
        "applied": True,
        "deck_count": len(layout["decks"]),
        "remaining_differences": deck_display_state_differences(
            collection, layout
        ),
    }


def _assign_values(
    note: Any, fields: Sequence[str], values: Mapping[str, str]
) -> None:
    if set(fields) != set(values):
        raise DeckBuildError("note field values do not match note type schema")
    for field in fields:
        note[field] = values[field]


def _add_note_to_decks(
    collection: Collection,
    *,
    notetype: NotetypeDict,
    guid: str,
    fields: Sequence[str],
    values: Mapping[str, str],
    tags: Sequence[str],
    deck_by_template: Mapping[str, DeckId],
) -> None:
    note = collection.new_note(notetype)
    note.guid = guid
    _assign_values(note, fields, values)
    note.tags = list(tags)
    first_deck = next(iter(deck_by_template.values()))
    collection.add_note(note, first_deck)
    for card in note.cards():
        template_name = str(notetype["tmpls"][card.ord]["name"])
        target_deck = deck_by_template.get(template_name)
        if target_deck is None:
            raise DeckBuildError(f"no deck declared for template: {template_name}")
        if int(card.did) != target_deck:
            card.did = target_deck
            collection.update_card(card)


def populate_collection(
    collection: Collection,
    *,
    layout: Mapping[str, Any],
    vocabulary_notes: Sequence[Mapping[str, Any]],
    practice_question_notes: Sequence[Mapping[str, Any]],
    reference_table_notes: Sequence[Mapping[str, Any]],
    kanji_notes: Sequence[Mapping[str, Any]],
) -> None:
    deck_ids = create_decks(collection, layout)
    notetypes = {
        kind: create_notetype(collection, spec)
        for kind, spec in NOTETYPE_SPECS.items()
    }
    assert_collection_identity(collection, layout)
    for record in vocabulary_notes:
        values = _vocabulary_field_values(record)
        routes = _vocabulary_card_routes(record, values)
        deck_by_template = {
            template: deck_ids[key] for template, key in routes.items()
        }
        _add_note_to_decks(
            collection,
            notetype=notetypes[VOCABULARY_KIND],
            guid=str(record["note_id"]),
            fields=VOCABULARY_FIELDS,
            values=values,
            tags=[str(tag) for tag in record.get("tags", [])],
            deck_by_template=deck_by_template,
        )
    for record in practice_question_notes:
        level = str(record["jlpt_level"])
        expected_key = practice_deck_key(str(record["question_type"]), level)
        if record.get("deck_key") != expected_key:
            raise DeckBuildError(
                f"practice-question deck key changed: {record.get('note_id')}"
            )
        _add_note_to_decks(
            collection,
            notetype=notetypes[PRACTICE_QUESTION_KIND],
            guid=str(record["note_id"]),
            fields=PRACTICE_QUESTION_FIELDS,
            values=_practice_question_field_values(record),
            tags=[str(tag) for tag in record.get("tags", [])],
            deck_by_template={PRACTICE_QUESTION_TEMPLATE: deck_ids[expected_key]},
        )
    for record in reference_table_notes:
        if record.get("deck_key") != "reference_table":
            raise DeckBuildError(f"reference-table deck key changed: {record.get('note_id')}")
        _add_note_to_decks(
            collection,
            notetype=notetypes[REFERENCE_TABLE_KIND],
            guid=str(record["note_id"]),
            fields=REFERENCE_TABLE_FIELDS,
            values=_reference_table_field_values(record),
            tags=[str(tag) for tag in record.get("tags", [])],
            deck_by_template={REFERENCE_TABLE_TEMPLATE: deck_ids["reference_table"]},
        )
    for record in kanji_notes:
        volume_code = str(record.get("volume_code", ""))
        expected_key = f"kanji:{volume_code}"
        if record.get("deck_keys") != [expected_key]:
            raise DeckBuildError(
                f"kanji deck key changed: {record.get('note_id')}"
            )
        _add_note_to_decks(
            collection,
            notetype=notetypes[KANJI_KIND],
            guid=str(record["note_id"]),
            fields=KANJI_FIELDS,
            values=_kanji_field_values(record),
            tags=[str(tag) for tag in record.get("tags", [])],
            deck_by_template={KANJI_TEMPLATE: deck_ids[expected_key]},
        )
def _link_media(source: Path, destination: Path, names: Sequence[str]) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    for name in sorted(names):
        source_path = source / name
        destination_path = destination / name
        try:
            os.link(source_path, destination_path)
        except OSError:
            shutil.copy2(source_path, destination_path)
    return len(names)


def _export_package(collection: Collection, output: Path) -> int:
    exporter = AnkiPackageExporter(collection)
    exporter.did = DECK_IDS["root"]
    # Anki only writes referenced deck-option presets into an APKG when
    # includeSched is enabled.  The importer still receives scheduling=False,
    # so existing card progress is preserved while the audio presets remain
    # available and assigned after import.
    exporter.includeSched = True
    exporter.includeMedia = True
    exporter.exportInto(str(output))
    return exporter.count


def _package_media_hashes(package: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    with zipfile.ZipFile(package) as archive:
        try:
            mapping = json.loads(archive.read("media"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise DeckBuildError(f"package media map cannot be read: {exc}") from exc
        if not isinstance(mapping, dict):
            raise DeckBuildError("package media map must be an object")
        for archive_name, filename in sorted(mapping.items(), key=lambda item: str(item[1])):
            if not isinstance(filename, str) or filename in hashes:
                raise DeckBuildError(f"invalid package media mapping: {filename}")
            digest = hashlib.sha256()
            with archive.open(str(archive_name)) as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
            hashes[filename] = digest.hexdigest()
    return hashes


def _expected_notes(inputs: ClosedDeckInputs) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    for record in inputs.vocabulary_notes:
        fields = _vocabulary_field_values(record)
        routes = _vocabulary_card_routes(record, fields)
        cards = {
            template: next(
                str(item["name"])
                for item in inputs.deck_layout["decks"]
                if item["key"] == key
            )
            for template, key in routes.items()
        }
        expected[str(record["note_id"])] = {
            "kind": VOCABULARY_KIND,
            "fields": fields,
            "tags": sorted(str(tag) for tag in record.get("tags", [])),
            "cards": cards,
        }
    for record in inputs.practice_question_notes:
        level = str(record["jlpt_level"])
        expected[str(record["note_id"])] = {
            "kind": PRACTICE_QUESTION_KIND,
            "fields": _practice_question_field_values(record),
            "tags": sorted(str(tag) for tag in record.get("tags", [])),
            "cards": {
                PRACTICE_QUESTION_TEMPLATE: practice_deck_name(
                    str(record["question_type"]), level
                )
            },
        }
    for record in inputs.reference_table_notes:
        expected[str(record["note_id"])] = {
            "kind": REFERENCE_TABLE_KIND,
            "fields": _reference_table_field_values(record),
            "tags": sorted(str(tag) for tag in record.get("tags", [])),
            "cards": {REFERENCE_TABLE_TEMPLATE: f"{PRODUCT_NAME}::참조표"},
        }
    for record in inputs.kanji_notes:
        volume = str(record["volume"])
        expected[str(record["note_id"])] = {
            "kind": KANJI_KIND,
            "fields": _kanji_field_values(record),
            "tags": sorted(str(tag) for tag in record.get("tags", [])),
            "cards": {
                KANJI_TEMPLATE: f"{PRODUCT_NAME}::일상무따::{volume}"
            },
        }
    return expected


def _collection_snapshot(collection: Collection) -> dict[str, Any]:
    deck_names_by_id = {
        int(item.id): item.name for item in collection.decks.all_names_and_ids()
    }
    deck_state_records = [
        {
            "browser_collapsed": bool(deck.get("browserCollapsed", False)),
            "collapsed": bool(deck.get("collapsed", False)),
            "name": deck_names_by_id[int(deck["id"])],
        }
        for deck in collection.decks.all()
        if int(deck["id"]) in deck_names_by_id
        and deck_names_by_id[int(deck["id"])].startswith(PRODUCT_NAME)
    ]
    deck_config_records = []
    for policy, config_id in DECK_CONFIG_IDS.items():
        config = collection.decks.get_config(config_id)
        if config is None:
            raise DeckBuildError(f"imported deck config missing: {policy}")
        deck_config_records.append(
            {
                "policy": policy,
                "id": int(config_id),
                "name": str(config["name"]),
                "autoplay": bool(config["autoplay"]),
                "replay_question_audio": bool(config["replayq"]),
                "new_card_order": {
                    "legacy_order": int(config["new"]["order"]),
                    "gather_priority": int(config["newGatherPriority"]),
                    "sort_order": int(config["newSortOrder"]),
                },
                "decks": sorted(
                    deck_names_by_id[int(deck["id"])]
                    for deck in collection.decks.all()
                    if int(deck.get("conf", 0)) == int(config_id)
                    and int(deck["id"]) in deck_names_by_id
                    and deck_names_by_id[int(deck["id"])].startswith(PRODUCT_NAME)
                ),
            }
        )
    notetype_by_id: dict[int, tuple[str, dict[str, Any]]] = {}
    notetype_records: list[dict[str, Any]] = []
    for kind, spec in NOTETYPE_SPECS.items():
        notetype = collection.models.by_name(spec.name)
        if notetype is None:
            raise DeckBuildError(f"imported note type missing: {spec.name}")
        notetype_by_id[int(notetype["id"])] = (kind, notetype)
        notetype_records.append(
            {
                "kind": kind,
                "name": spec.name,
                "id": int(notetype["id"]),
                "fields": [
                    {"name": field["name"], "id": int(field["id"])}
                    for field in notetype["flds"]
                ],
                "templates": [
                    {
                        "name": template["name"],
                        "id": int(template["id"]),
                        "question_hash": hashlib.sha256(
                            str(template["qfmt"]).encode()
                        ).hexdigest(),
                        "answer_hash": hashlib.sha256(
                            str(template["afmt"]).encode()
                        ).hexdigest(),
                    }
                    for template in notetype["tmpls"]
                ],
                "css_hash": hashlib.sha256(str(notetype["css"]).encode()).hexdigest(),
            }
        )
    notes: list[dict[str, Any]] = []
    guid_by_note_id: dict[int, str] = {}
    for note_id in collection.find_notes(""):
        note = collection.get_note(note_id)
        kind, notetype = notetype_by_id[int(note.mid)]
        fields = {
            field["name"]: note[field["name"]]
            for field in notetype["flds"]
        }
        guid_by_note_id[int(note_id)] = note.guid
        notes.append(
            {
                "guid": note.guid,
                "kind": kind,
                "fields": fields,
                "tags": sorted(note.tags),
            }
        )
    cards: list[dict[str, Any]] = []
    for card_id in collection.find_cards(""):
        card = collection.get_card(card_id)
        _, notetype = notetype_by_id[int(card.note_type()["id"])]
        cards.append(
            {
                "note_guid": guid_by_note_id[int(card.nid)],
                "template": notetype["tmpls"][card.ord]["name"],
                "deck": deck_names_by_id[int(card.did)],
            }
        )
    return {
        "schema_version": LOGICAL_MANIFEST_SCHEMA_VERSION,
        "product": PRODUCT_NAME,
        "notetypes": sorted(notetype_records, key=lambda value: value["kind"]),
        "deck_configs": sorted(
            deck_config_records, key=lambda value: value["policy"]
        ),
        "decks": sorted(
            deck_state_records,
            key=lambda value: value["name"],
        ),
        "notes": sorted(notes, key=lambda value: value["guid"]),
        "cards": sorted(
            cards,
            key=lambda value: (
                value["note_guid"],
                value["template"],
                value["deck"],
            ),
        ),
    }


def _identity_maps(
    collection: Collection,
) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    note_ids: dict[str, int] = {}
    guid_by_note_id: dict[int, str] = {}
    for note_id in collection.find_notes(""):
        note = collection.get_note(note_id)
        note_ids[note.guid] = int(note_id)
        guid_by_note_id[int(note_id)] = note.guid
    card_ids: dict[tuple[str, str], int] = {}
    for card_id in collection.find_cards(""):
        card = collection.get_card(card_id)
        notetype = card.note_type()
        template = str(notetype["tmpls"][card.ord]["name"])
        card_ids[(guid_by_note_id[int(card.nid)], template)] = int(card_id)
    return note_ids, card_ids


def _verify_collection(
    collection: Collection,
    *,
    inputs: ClosedDeckInputs,
    expected: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    assert_collection_identity(
        collection,
        inputs.deck_layout,
        require_deck_ids=False,
        require_display_state=False,
    )
    note_ids = collection.find_notes("")
    card_ids = collection.find_cards("")
    if len(note_ids) != inputs.summary["total_note_count"]:
        raise DeckBuildError(f"imported note count differs: {len(note_ids)}")
    if len(card_ids) != inputs.summary["total_card_count"]:
        raise DeckBuildError(f"imported card count differs: {len(card_ids)}")
    deck_names = {
        int(item.id): item.name for item in collection.decks.all_names_and_ids()
    }
    expected_deck_names = sorted(str(item["name"]) for item in inputs.deck_layout["decks"])
    actual_deck_names = sorted(
        name for name in deck_names.values() if name.startswith(PRODUCT_NAME)
    )
    if actual_deck_names != expected_deck_names:
        raise DeckBuildError("imported deck names differ from the content manifest")

    guid_by_note_id: dict[int, str] = {}
    note_kind_counts: Counter[str] = Counter()
    sound_names: list[str] = []
    static_names: list[str] = []
    for note_id in note_ids:
        note = collection.get_note(note_id)
        guid = note.guid
        guid_by_note_id[int(note_id)] = guid
        wanted = expected.get(guid)
        if wanted is None:
            raise DeckBuildError(f"unexpected imported note GUID: {guid}")
        spec = NOTETYPE_SPECS[str(wanted["kind"])]
        notetype = collection.models.by_name(spec.name)
        if notetype is None or int(note.mid) != int(notetype["id"]):
            raise DeckBuildError(f"note type mismatch for GUID: {guid}")
        actual_fields = {field: note[field] for field in spec.fields}
        if actual_fields != wanted["fields"]:
            mismatched_fields = [
                field
                for field in spec.fields
                if actual_fields[field] != wanted["fields"][field]
            ]
            field = mismatched_fields[0]
            raise DeckBuildError(
                "field mismatch after import: "
                f"{guid}/{field}: expected={wanted['fields'][field]!r}, "
                f"actual={actual_fields[field]!r}"
            )
        if sorted(note.tags) != wanted["tags"]:
            raise DeckBuildError(f"tag mismatch after import: {guid}")
        note_kind_counts[spec.kind] += 1
        field_html = "\n".join(actual_fields.values())
        sound_names.extend(re.findall(r"\[sound:([^\]]+)\]", field_html))
        for media_name in re.findall(r'(?:src|data)="([^"]+)"', field_html):
            if media_name.endswith(AUDIO_SUFFIXES):
                sound_names.append(media_name)
            else:
                static_names.append(media_name)
    if set(guid_by_note_id.values()) != set(expected):
        raise DeckBuildError("expected note GUIDs are missing after import")

    cards_by_deck: Counter[str] = Counter()
    cards_by_template: Counter[str] = Counter()
    templates_by_guid: dict[str, set[str]] = defaultdict(set)
    for card_id in card_ids:
        card = collection.get_card(card_id)
        guid = guid_by_note_id[int(card.nid)]
        notetype = card.note_type()
        template = str(notetype["tmpls"][card.ord]["name"])
        deck_name = deck_names[int(card.did)]
        wanted_deck = expected[guid]["cards"].get(template)
        if wanted_deck != deck_name:
            raise DeckBuildError(
                f"card deck mismatch: {guid}/{template} -> {deck_name}"
            )
        templates_by_guid[guid].add(template)
        cards_by_deck[deck_name] += 1
        cards_by_template[template] += 1
    for guid, wanted in expected.items():
        if templates_by_guid[guid] != set(wanted["cards"]):
            raise DeckBuildError(f"card template mismatch for GUID: {guid}")
    expected_audio = {
        str(job["filename"])
        for job in inputs.media_jobs
        if job.get("kind") != "kanji_static"
    }
    expected_static = {
        str(job["filename"])
        for job in inputs.media_jobs
        if job.get("kind") == "kanji_static"
    }
    if set(sound_names) != expected_audio:
        raise DeckBuildError("note sound fields do not reconcile with audio jobs")
    if set(static_names) != expected_static:
        raise DeckBuildError("note HTML does not reconcile with static media jobs")
    expected_card_counts = {
        next(
            str(item["name"])
            for item in inputs.deck_layout["decks"]
            if item["key"] == key
        ): count
        for key, count in inputs.deck_layout["card_counts_by_deck"].items()
    }
    if dict(cards_by_deck) != expected_card_counts:
        raise DeckBuildError(
            "card counts by deck differ from the content manifest: "
            f"expected={expected_card_counts!r}, actual={dict(cards_by_deck)!r}"
        )
    return {
        "notes": len(note_ids),
        "cards": len(card_ids),
        "note_counts_by_kind": dict(sorted(note_kind_counts.items())),
        "cards_by_template": dict(sorted(cards_by_template.items())),
        "cards_by_deck": dict(sorted(cards_by_deck.items())),
        "sound_reference_count": len(sound_names),
        "unique_sound_reference_count": len(set(sound_names)),
        "static_reference_count": len(static_names),
        "unique_static_reference_count": len(set(static_names)),
        "deck_count": len(actual_deck_names),
        "notetype_count": len(NOTETYPE_SPECS),
        "template_count": sum(len(spec.templates) for spec in NOTETYPE_SPECS.values()),
    }


def _full_render_html(css: str, body: str) -> str:
    return (
        "<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<style>{css}</style></head><body class=\"card\">{body}</body></html>\n"
    )


_WINDOWS_DEVICE_NAMES = frozenset(
    {
        "aux",
        "con",
        "nul",
        "prn",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
)
_RENDERED_SAMPLE_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _portable_rendered_sample_stem(
    label: str,
    *,
    force_hash_suffix: bool = False,
) -> str:
    """Project a sample label to one portable Windows/macOS filename component."""
    if not label:
        raise DeckBuildError("render sample label must be non-empty")
    normalized = unicodedata.normalize("NFC", label)
    stem = _RENDERED_SAMPLE_UNSAFE.sub("-", normalized).strip(" .")
    if not stem:
        stem = "sample"
    if stem.split(".", 1)[0].casefold() in _WINDOWS_DEVICE_NAMES:
        stem = f"sample-{stem}"
    changed = stem != normalized or len(stem) > RENDERED_SAMPLE_STEM_MAX_LENGTH
    if changed or force_hash_suffix:
        suffix = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
        maximum_base = RENDERED_SAMPLE_STEM_MAX_LENGTH - len(suffix) - 1
        stem = stem[:maximum_base].rstrip(" .") or "sample"
        stem = f"{stem}-{suffix}"
    if (
        len(stem) > RENDERED_SAMPLE_STEM_MAX_LENGTH
        or _RENDERED_SAMPLE_UNSAFE.search(stem)
        or stem.endswith((" ", "."))
        or stem.split(".", 1)[0].casefold() in _WINDOWS_DEVICE_NAMES
    ):
        raise DeckBuildError(f"render sample label has no portable filename: {label}")
    return stem


def _rendered_sample_filename_stems(labels: Sequence[str]) -> dict[str, str]:
    """Return deterministic, case-insensitively unique portable sample stems."""
    provisional = {label: _portable_rendered_sample_stem(label) for label in labels}
    counts = Counter(stem.casefold() for stem in provisional.values())
    stems = {
        label: _portable_rendered_sample_stem(
            label,
            force_hash_suffix=counts[stem.casefold()] > 1,
        )
        for label, stem in provisional.items()
    }
    if len({stem.casefold() for stem in stems.values()}) != len(stems):
        raise DeckBuildError("render sample filenames collide case-insensitively")
    return stems


def _is_kakudan_inflection_regression_note(note: Any) -> bool:
    """Identify the historical 格段に case even if public display form differs."""
    return any(
        any(
            marker in str(note[f"Example{index}JP"])
            for marker in (
                "格段に",
                "<ruby><rb>格段</rb><rt>かくだん</rt></ruby>に",
            )
        )
        for index in range(1, 5)
    )


def _rendered_sample_candidates(
    collection: Collection,
    *,
    public_source_materialized: bool = False,
) -> dict[str, Any]:
    notes: dict[str, Any] = {}
    cards: dict[tuple[str, str], Any] = {}
    for note_id in collection.find_notes(""):
        note = collection.get_note(note_id)
        notes[note.guid] = note
    for card_id in collection.find_cards(""):
        card = collection.get_card(card_id)
        note = collection.get_note(card.nid)
        notetype = card.note_type()
        cards[(note.guid, str(notetype["tmpls"][card.ord]["name"]))] = card

    selected: dict[str, Any] = {}

    def choose(
        label: str,
        predicate: Any,
        template: str,
        *,
        required: bool = True,
    ) -> bool:
        guid = next((guid for guid in sorted(notes) if predicate(notes[guid])), None)
        if guid is None:
            if not required:
                return False
            raise DeckBuildError(f"render sample cannot be selected: {label}")
        if (guid, template) not in cards:
            raise DeckBuildError(f"render sample card is missing: {label}")
        selected[label] = cards[(guid, template)]
        return True

    for level in LEVELS:
        choose(
            f"vocabulary-{level}",
            lambda note, level=level: note.note_type()["name"] == VOCABULARY_NOTETYPE
            and note["JLPT"] == level,
            VOCABULARY_TEMPLATE,
        )
        choose(
            f"audio-{level}",
            lambda note, level=level: note.note_type()["name"] == VOCABULARY_NOTETYPE
            and note["JLPT"] == level,
            AUDIO_TEMPLATE,
        )
        choose(
            f"practice-question-{level}",
            lambda note, level=level: note.note_type()["name"]
            == PRACTICE_QUESTION_NOTETYPE
            and note["JLPT"] == level,
            PRACTICE_QUESTION_TEMPLATE,
        )
    if any(
        note.note_type()["name"] == VOCABULARY_NOTETYPE
        and bool(note["HiraganaWord"])
        for note in notes.values()
    ):
        choose(
            "hiragana-form-vocabulary",
            lambda note: note.note_type()["name"] == VOCABULARY_NOTETYPE
            and bool(note["HiraganaWord"]),
            HIRAGANA_FORM_TEMPLATE,
        )
    choose(
        "vocabulary-one-example",
        lambda note: note.note_type()["name"] == VOCABULARY_NOTETYPE
        and bool(note["Example1JP"])
        and not note["Example2JP"],
        VOCABULARY_TEMPLATE,
    )
    if not choose(
        "vocabulary-four-examples",
        lambda note: note.note_type()["name"] == VOCABULARY_NOTETYPE
        and bool(note["Example4JP"]),
        VOCABULARY_TEMPLATE,
        required=not public_source_materialized,
    ):
        choose(
            "vocabulary-three-examples",
            lambda note: note.note_type()["name"] == VOCABULARY_NOTETYPE
            and bool(note["Example3JP"])
            and not note["Example4JP"],
            VOCABULARY_TEMPLATE,
        )
    choose(
        "vocabulary-kanji-details",
        lambda note: note.note_type()["name"] == VOCABULARY_NOTETYPE
        and bool(note["KanjiDetails"]),
        VOCABULARY_TEMPLATE,
    )
    choose(
        "vocabulary-no-kanji-details",
        lambda note: note.note_type()["name"] == VOCABULARY_NOTETYPE
        and not note["KanjiDetails"],
        VOCABULARY_TEMPLATE,
    )
    choose(
        "vocabulary-conjugation-register",
        lambda note: note.note_type()["name"] == VOCABULARY_NOTETYPE
        and bool(note["ConjugationDetails"])
        and bool(note["UsageRegister"]),
        VOCABULARY_TEMPLATE,
    )
    for label, field in (
        ("vocabulary-study-usage", "UsageDetails"),
        ("vocabulary-study-formation", "WordFormationDetails"),
        ("vocabulary-study-related", "RelatedWords"),
    ):
        choose(
            label,
            lambda note, field=field: note.note_type()["name"]
            == VOCABULARY_NOTETYPE
            and bool(note[field]),
            VOCABULARY_TEMPLATE,
        )
    for question_type in _RENDER_SAMPLE_PRACTICE_TYPES:
        choose(
            f"practice-question-{question_type}",
            lambda note, question_type=question_type: note.note_type()["name"]
            == PRACTICE_QUESTION_NOTETYPE
            and note["QuestionType"] == question_type,
            PRACTICE_QUESTION_TEMPLATE,
        )
    for guid, note in sorted(notes.items()):
        if note.note_type()["name"] == REFERENCE_TABLE_NOTETYPE:
            selected[f"reference-table-{note['ReferenceID']}"] = cards[
                (guid, REFERENCE_TABLE_TEMPLATE)
            ]
    choose(
        "kanji-text-linked",
        lambda note: note.note_type()["name"] == KANJI_NOTETYPE
        and "kanji-card-glyph" in note["GlyphHTML"]
        and "kanji-glyph-image" not in note["GlyphHTML"]
        and bool(note["LinkedVocabulary"]),
        KANJI_TEMPLATE,
    )
    choose(
        "kanji-image-glyph",
        lambda note: note.note_type()["name"] == KANJI_NOTETYPE
        and "kanji-glyph-image" in note["GlyphHTML"],
        KANJI_TEMPLATE,
    )
    choose(
        "kanji-no-reference",
        lambda note: note.note_type()["name"] == KANJI_NOTETYPE
        and not note["KanjiReference"],
        KANJI_TEMPLATE,
    )
    choose(
        "regression-hyoumei-ruby",
        lambda note: note.note_type()["name"] == VOCABULARY_NOTETYPE
        and any(
            "<ruby><rb>表明</rb><rt>ひょうめい</rt></ruby>" in note[f"Example{index}JP"]
            for index in range(1, 5)
        ),
        VOCABULARY_TEMPLATE,
    )
    choose(
        "regression-kakudan-ni",
        lambda note: note.note_type()["name"] == VOCABULARY_NOTETYPE
        and _is_kakudan_inflection_regression_note(note),
        VOCABULARY_TEMPLATE,
    )
    return selected


def write_rendered_samples(
    collection: Collection,
    output_root: Path,
    *,
    public_source_materialized: bool = False,
) -> list[dict[str, Any]]:
    sample_root = output_root / "rendered-samples"
    sample_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    candidates = _rendered_sample_candidates(
        collection,
        public_source_materialized=public_source_materialized,
    )
    filename_stems = _rendered_sample_filename_stems(tuple(sorted(candidates)))
    for label, card in sorted(candidates.items()):
        note = collection.get_note(card.nid)
        notetype = card.note_type()
        template = str(notetype["tmpls"][card.ord]["name"])
        question = card.question()
        answer = card.answer()
        if not question or not answer or "{{" in question or "{{" in answer:
            raise DeckBuildError(f"card did not render cleanly: {label}")
        if label == "regression-hyoumei-ruby" and (
            "<ruby><rb>表明</rb><rt>ひょうめい</rt></ruby>" not in answer
        ):
            raise DeckBuildError("表明 ruby regression is absent from rendered answer")
        conjugation_markup = '<details class="conjugation-panel">'
        register_markup = '<span class="usage-register-badge '
        if label == "regression-kakudan-ni" and conjugation_markup in answer:
            raise DeckBuildError("inflected 格段に received a conjugation panel")
        if label == "vocabulary-conjugation-register" and (
            conjugation_markup not in answer
            or register_markup not in answer
            or conjugation_markup in question
            or register_markup in question
        ):
            raise DeckBuildError(
                "vocabulary features did not stay on the rendered answer"
            )
        study_markup = {
            "vocabulary-study-usage": '<details class="study-panel usage-details">',
            "vocabulary-study-formation": '<details class="study-panel word-formation-details">',
            "vocabulary-study-related": '<details class="study-panel related-words-details">',
        }.get(label)
        if study_markup and (
            study_markup not in answer or study_markup in question
        ):
            raise DeckBuildError("study feature leaked to the card question")
        if label.startswith("kanji-") and (
            'class="kanji-meaning"' not in answer
            or 'class="kanji-meaning"' in question
        ):
            raise DeckBuildError("kanji answer content leaked to the question")
        vocabulary_markup = '<section class="kanji-panel kanji-vocabulary">'
        click_audio_markup = '<audio class="click-audio-player"'
        glyph_image_markup = '<img class="kanji-glyph-image"'
        if label == "kanji-text-linked" and (
            vocabulary_markup not in answer
            or click_audio_markup not in answer
            or vocabulary_markup in question
            or click_audio_markup in question
        ):
            raise DeckBuildError("kanji enrichment rendering changed")
        if label == "kanji-image-glyph" and glyph_image_markup not in question:
            raise DeckBuildError("source glyph image is absent from the kanji front")
        question_has_audio = bool(
            re.search(r"\[(?:sound:[^\]]+|anki:play:q:\d+)\]", question)
        )
        answer_has_audio = bool(
            re.search(r"\[(?:sound:[^\]]+|anki:play:[qa]:\d+)\]", answer)
        )
        question_autoplay_scope_count = len(
            HTML_AUTOPLAY_WORD_SCOPE_RE.findall(question)
        )
        answer_autoplay_scope_count = len(
            HTML_AUTOPLAY_WORD_SCOPE_RE.findall(answer)
        )
        expected_answer_autoplay_scope_count = int(
            template in {VOCABULARY_TEMPLATE, HIRAGANA_FORM_TEMPLATE}
        )
        if (
            (question_has_audio and click_audio_markup in question)
            or (answer_has_audio and click_audio_markup in answer)
        ):
            raise DeckBuildError("native and HTML audio share one card face")
        if (
            question_autoplay_scope_count
            or answer_autoplay_scope_count
            != expected_answer_autoplay_scope_count
            or (
                answer_autoplay_scope_count
                and click_audio_markup not in answer
            )
        ):
            raise DeckBuildError("HTML audio autoplay scope contract changed")
        if template in {VOCABULARY_TEMPLATE, HIRAGANA_FORM_TEMPLATE} and (
            question_has_audio
            or answer_has_audio
            or answer.count("[anki:play:") != 0
            or click_audio_markup not in answer
            or answer_autoplay_scope_count != 1
        ):
            raise DeckBuildError("vocabulary answer audio contract changed")
        if template == AUDIO_TEMPLATE and (
            not question_has_audio
            or question.count("[anki:play:") != 1
            or answer_has_audio
            or click_audio_markup not in answer
            or answer_autoplay_scope_count
        ):
            raise DeckBuildError("audio-card playback contract changed")
        if template == HIRAGANA_FORM_TEMPLATE and (
            note["HiraganaWord"] not in question
            or note["Meaning"] in question
            or "【" in question
            or "】" in question
        ):
            raise DeckBuildError("hiragana-form vocabulary front changed")
        if template == PRACTICE_QUESTION_TEMPLATE and (
            question_has_audio
            or click_audio_markup in question
            or not answer_has_audio
            or 'aria-label="문제 음성 재생"' in answer
            or 'aria-label="정답 음성 재생"' not in answer
            or click_audio_markup in answer
            or answer.count("[anki:play:") != 1
            or answer_autoplay_scope_count
        ):
            raise DeckBuildError("practice answer-only audio contract changed")
        if label in {
            "practice-question-kanji_reading",
            "practice-question-orthography",
            "practice-question-word_formation",
        }:
            _validate_lexical_practice_render(note, question, answer)
        if label.startswith("reference-table-"):
            reference_group_count = answer.count(
                '<section class="reference-group">'
            )
            expected_group_count = 3 if note["TableKind"] == "calendar_grid" else None
            if (
                click_audio_markup not in answer
                or answer_has_audio
                or question_has_audio
                or "<details" in answer
                or "<summary" in answer
                or (
                    expected_group_count is not None
                    and reference_group_count != expected_group_count
                )
                or (
                    expected_group_count is None
                    and not 1 <= reference_group_count <= 2
                )
            ):
                raise DeckBuildError(
                    "reference-table static click-audio contract changed"
                )
        for side, body in (("question", question), ("answer", answer)):
            relative = f"rendered-samples/{filename_stems[label]}-{side}.html"
            path = output_root / relative
            path.write_text(_full_render_html(str(notetype["css"]), body), encoding="utf-8")
            records.append(
                {
                    "label": label,
                    "side": side,
                    "note_guid": note.guid,
                    "notetype": notetype["name"],
                    "template": template,
                    "path": relative,
                    "sha256": sha256_file(path),
                }
            )
    _write_json(output_root / RENDERED_SAMPLE_INDEX, {"samples": records, "schema_version": 1})
    return records


def _validate_lexical_practice_render(
    note: _NoteFields, question: str, answer: str
) -> None:
    """Reject lexical answer markup without mistaking notetype CSS for DOM."""
    correct_option_markup = 'class="question-option is-correct"'
    translation_markup = 'class="question-option-translation"'
    leaked_fields = (
        str(note["ExplanationRubyHTML"]),
        str(note["AnswerAudio"]),
    )
    if (
        any(value and value in question for value in leaked_fields)
        or correct_option_markup in question
        or translation_markup in question
        or "<ruby" in question
        or answer.count(correct_option_markup) != 1
        or answer.count('class="question-explanation"') != 1
        or translation_markup in answer
        or not str(note["AnswerRuby"])
        or str(note["AnswerRuby"]) not in answer
        or not str(note["AnswerKORuby"])
        or str(note["AnswerKORuby"]) not in answer
    ):
        raise DeckBuildError(
            "lexical practice rendering leaked answer-only content"
        )


def verify_repeated_import(
    package: Path,
    *,
    work_root: Path,
    output_root: Path,
    inputs: ClosedDeckInputs,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    work_root.mkdir(parents=True, exist_ok=False)
    collection = Collection(str(work_root / "isolated.anki2"))
    try:
        options = collection._backend.get_import_anki_package_presets()
        options.merge_notetypes = True
        options.with_scheduling = False
        options.with_deck_configs = True
        request = ImportAnkiPackageRequest(package_path=str(package), options=options)
        first_result = collection.import_anki_package(request)
        expected = _expected_notes(inputs)
        first_verification = _verify_collection(
            collection, inputs=inputs, expected=expected
        )
        first_import_display_differences = deck_display_state_differences(
            collection, inputs.deck_layout
        )
        first_profile_display_application = apply_deck_display_state(
            collection, inputs.deck_layout
        )
        first_note_ids, first_card_ids = _identity_maps(collection)
        logical_snapshot = _collection_snapshot(collection)
        rendered_samples = write_rendered_samples(
            collection,
            output_root,
            public_source_materialized=(
                inputs.summary.get("content_variant")
                == "public_source_materialized"
            ),
        )

        scheduled_key = next(
            key for key in sorted(first_card_ids) if key[1] == VOCABULARY_TEMPLATE
        )
        scheduled_card = collection.get_card(CardId(first_card_ids[scheduled_key]))
        scheduled_card.ivl = 42
        scheduled_card.due = 4242
        scheduled_card.queue = CardQueue(2)
        scheduled_card.type = CardType(2)
        collection.update_card(scheduled_card)
        preserved_schedule = (
            scheduled_card.ivl,
            scheduled_card.due,
            scheduled_card.queue,
            scheduled_card.type,
        )

        second_result = collection.import_anki_package(request)
        second_verification = _verify_collection(
            collection, inputs=inputs, expected=expected
        )
        second_import_display_differences = deck_display_state_differences(
            collection, inputs.deck_layout
        )
        second_profile_display_application = apply_deck_display_state(
            collection, inputs.deck_layout
        )
        second_note_ids, second_card_ids = _identity_maps(collection)
        reloaded = collection.get_card(CardId(first_card_ids[scheduled_key]))
        actual_schedule = (reloaded.ivl, reloaded.due, reloaded.queue, reloaded.type)
        if len(first_result.log.new) != inputs.summary["total_note_count"]:
            raise DeckBuildError("empty-profile import did not add every expected note")
        if len(first_result.log.updated) != 0:
            raise DeckBuildError("empty-profile import unexpectedly updated notes")
        if len(second_result.log.new) != 0:
            raise DeckBuildError("repeated import created duplicate notes")
        if first_note_ids != second_note_ids or first_card_ids != second_card_ids:
            raise DeckBuildError("repeated import changed note or card IDs")
        if actual_schedule != preserved_schedule:
            raise DeckBuildError("repeated import changed existing scheduling")
        if _collection_snapshot(collection) != logical_snapshot:
            raise DeckBuildError("repeated import changed logical package content")
        return (
            {
                "first_import": {
                    "new": len(first_result.log.new),
                    "updated": len(first_result.log.updated),
                },
                "second_import": {
                    "new": len(second_result.log.new),
                    "updated": len(second_result.log.updated),
                },
                "note_ids_preserved": True,
                "card_ids_preserved": True,
                "scheduling_preserved": True,
                "verification_import_with_scheduling": False,
                "verification_import_preserves_display_state": not (
                    first_import_display_differences
                    or second_import_display_differences
                ),
                "profile_display_state_application_required": bool(
                    first_import_display_differences
                    or second_import_display_differences
                ),
                "first_import_display_state_differences": (
                    first_import_display_differences
                ),
                "second_import_display_state_differences": (
                    second_import_display_differences
                ),
                "first_profile_display_application": (
                    first_profile_display_application
                ),
                "second_profile_display_application": (
                    second_profile_display_application
                ),
                "scheduled_card": {
                    "note_guid": scheduled_key[0],
                    "template": scheduled_key[1],
                    "ivl": actual_schedule[0],
                    "due": actual_schedule[1],
                    "queue": actual_schedule[2],
                    "type": actual_schedule[3],
                },
                "first_verification": first_verification,
                "second_verification": second_verification,
            },
            logical_snapshot,
            rendered_samples,
        )
    finally:
        collection.close()


def _run_candidate_package_verifications(
    candidate: Path,
    *,
    work_root: Path,
    output_root: Path,
    inputs: ClosedDeckInputs,
    expected_media_hashes: Mapping[str, str],
) -> tuple[
    dict[str, str],
    tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]],
]:
    """Read package media and verify isolated imports with bounded overlap."""

    def verify_package_media() -> dict[str, str]:
        package_media_hashes = _package_media_hashes(candidate)
        if package_media_hashes != expected_media_hashes:
            raise DeckBuildError(
                "packaged media hashes differ from the closed inventory"
            )
        return package_media_hashes

    with ThreadPoolExecutor(
        max_workers=2,
        thread_name_prefix="apkg-verify",
    ) as executor:
        package_media_future = executor.submit(verify_package_media)
        repeated_import_future = executor.submit(
            verify_repeated_import,
            candidate,
            work_root=work_root,
            output_root=output_root,
            inputs=inputs,
        )
        return package_media_future.result(), repeated_import_future.result()


def build_public_apkg(
    *,
    content_root: Path,
    media_root: Path,
    output_root: Path,
    package_name: str = PACKAGE_NAME,
) -> dict[str, Any]:
    """Build and twice-import a public APKG from materialized inputs."""
    inputs = load_closed_inputs(content_root, media_root)
    _ensure_empty(output_root, "output root")
    package = output_root / package_name
    candidate = output_root / f".{Path(package_name).stem}.candidate.apkg"
    work_root = output_root / ".work"
    verify_root = output_root / ".verify"
    collection_path = work_root / "build.anki2"
    work_root.mkdir()
    collection: Collection | None = None
    try:
        active_collection: Collection = Collection(str(collection_path))
        collection = active_collection
        populate_collection(
            active_collection,
            layout=inputs.deck_layout,
            vocabulary_notes=inputs.vocabulary_notes,
            practice_question_notes=inputs.practice_question_notes,
            reference_table_notes=inputs.reference_table_notes,
            kanji_notes=inputs.kanji_notes,
        )
        linked_media = _link_media(
            media_root / MEDIA_DIR,
            Path(active_collection.media.dir()),
            [str(job["filename"]) for job in inputs.media_jobs],
        )
        exported_cards = _export_package(active_collection, candidate)
        active_collection.close()
        collection = None
        if exported_cards != inputs.summary["total_card_count"]:
            raise DeckBuildError(f"exported card count differs: {exported_cards}")
        if linked_media != inputs.summary["media_job_count"]:
            raise DeckBuildError(f"linked media count differs: {linked_media}")

        expected_media_hashes = {
            str(item["filename"]): str(item["sha256"])
            for item in inputs.media_inventory
        }
        package_media_hashes, repeated_import_verification = (
            _run_candidate_package_verifications(
                candidate,
                work_root=verify_root,
                output_root=output_root,
                inputs=inputs,
                expected_media_hashes=expected_media_hashes,
            )
        )

        import_report, collection_snapshot, rendered_samples = (
            repeated_import_verification
        )
        logical_manifest = {
            **collection_snapshot,
            "media": [
                {"filename": name, "sha256": digest}
                for name, digest in sorted(package_media_hashes.items())
            ],
        }
        logical_hash = sha256_json(logical_manifest)
        _write_json(output_root / LOGICAL_MANIFEST, logical_manifest)
        if candidate != package:
            candidate.replace(package)

        report = {
            "schema_version": 1,
            "status": "passed",
            "unresolved": 0,
            "policy_version": APKG_POLICY_VERSION,
            "product": PRODUCT_NAME,
            "product_version": PRODUCT_VERSION,
            "package": package.name,
            "package_bytes": package.stat().st_size,
            "package_sha256": sha256_file(package),
            "logical_apkg_hash": logical_hash,
            "content_manifest_sha256": sha256_file(
                content_root / CONTENT_STAGE_MANIFEST
            ),
            "media_manifest_sha256": sha256_file(media_root / MEDIA_STAGE_MANIFEST),
            "notes": inputs.summary["total_note_count"],
            "cards": exported_cards,
            "decks": inputs.deck_layout["total_deck_count"],
            "leaf_decks": inputs.deck_layout["leaf_deck_count"],
            "card_bearing_decks": inputs.deck_layout[
                "card_bearing_deck_count"
            ],
            "notetypes": len(NOTETYPE_SPECS),
            "templates": sum(len(spec.templates) for spec in NOTETYPE_SPECS.values()),
            "media_files": len(package_media_hashes),
            "rendered_sample_files": len(rendered_samples),
            "grammar_notes": 0,
            "anki_version": ANKI_VERSION,
            "python": platform.python_version(),
            "import_verification": import_report,
        }
        _write_json(output_root / BUILD_REPORT, report)

        write_release_artifacts(
            output_root=output_root,
            notes=[
                *inputs.vocabulary_notes,
                *inputs.practice_question_notes,
                *inputs.reference_table_notes,
                *inputs.kanji_notes,
            ],
            logical_apkg_hash=logical_hash,
            packaged_artifacts={package.name: report["package_sha256"]},
            previous_records=None,
            product_version=PRODUCT_VERSION,
        )

        code_hashes = {name: sha256_file(ROOT / name) for name in CODE_PATHS}
        input_hashes = {
            "code": sha256_json(code_hashes),
            "content_manifest": report["content_manifest_sha256"],
            "content_output_bundle": inputs.content_manifest["output_bundle_hash"],
            "media_manifest": report["media_manifest_sha256"],
            "media_output_bundle": inputs.media_manifest["output_bundle_hash"],
        }
        output_names = [
            package.name,
            BUILD_REPORT,
            LOGICAL_MANIFEST,
            RENDERED_SAMPLE_INDEX,
            RELEASE_MANIFEST,
            RELEASE_NOTES,
            UPDATE_REPORT_JSON,
            UPDATE_REPORT_TEXT,
            *(record["path"] for record in rendered_samples),
        ]
        output_artifacts = {
            name: sha256_file(output_root / name) for name in sorted(output_names)
        }
        manifest = {
            "schema_version": 1,
            "stage_id": STAGE_ID,
            "stage_order": 9,
            "substage": "closed-apkg",
            "status": "passed",
            "unresolved": 0,
            "policy_version": APKG_POLICY_VERSION,
            "upstream_stage_ids": [CONTENT_STAGE_ID, MEDIA_STAGE_ID],
            "code_hashes": code_hashes,
            "input_hashes": input_hashes,
            "input_bundle_hash": sha256_json(input_hashes),
            "output_artifacts": output_artifacts,
            "output_bundle_hash": sha256_json(output_artifacts),
            "counts": {
                "notes": report["notes"],
                "cards": report["cards"],
                "decks": report["decks"],
                "leaf_decks": report["leaf_decks"],
                "notetypes": report["notetypes"],
                "templates": report["templates"],
                "media_files": report["media_files"],
                "rendered_sample_files": report["rendered_sample_files"],
                "grammar_notes": 0,
            },
            "runtime": {
                "anki": ANKI_VERSION,
                "python": platform.python_version(),
                "python_implementation": platform.python_implementation(),
            },
        }
        _write_json(output_root / STAGE_MANIFEST, manifest)
        if work_root.exists():
            shutil.rmtree(work_root)
        shutil.rmtree(verify_root)
        return manifest
    finally:
        if collection is not None:
            collection.close()
