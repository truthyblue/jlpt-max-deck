"""Render compact study-feature HTML for public vocabulary cards."""

from __future__ import annotations

import html
import re
from collections.abc import Mapping, Sequence
from typing import Any

from public_ruby import render_kanji_ruby


MAX_USAGE_DETAILS = 2
MAX_WORD_FORMATION_DETAILS = 2
MAX_RELATED_WORDS = 3

PRIORITY_LABELS = {
    "01_essential": ("필수", "is-essential"),
    "02_standard": ("표준", "is-standard"),
    "03_extended": ("확장", "is-extended"),
}
FORMATION_LABELS = {
    "prefix": "접두",
    "suffix": "접미",
    "suru_derivation": "する 파생",
}
COMPONENT_LABELS = {
    "base": "어근",
    "prefix": "접두",
    "suffix": "접미",
}
RELATION_LABELS = {
    "antonym": "반의어",
    "near_synonym": "유의어",
    "same_reading": "동음어",
    "similar_form": "동형어",
    "transitive_pair": "자동사·타동사",
}
SAFE_AUDIO_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

VOCABULARY_STUDY_SECTIONS = """
  {{#UsageDetails}}{{UsageDetails}}{{/UsageDetails}}
  {{#WordFormationDetails}}{{WordFormationDetails}}{{/WordFormationDetails}}
  {{#RelatedWords}}{{RelatedWords}}{{/RelatedWords}}
"""

STUDY_FEATURE_CSS = """
.study-priority {
  display: inline-flex;
  align-items: center;
  min-height: 23px;
  padding: 3px 8px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 800;
  line-height: 1.3;
}
.study-priority.is-essential {
  border-color: var(--accent);
  background: var(--surface-muted);
  color: var(--accent);
}
.study-priority.is-standard { background: var(--surface); }
.study-priority.is-extended { border-style: dashed; }
.study-panel {
  margin-top: 8px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  overflow: hidden;
}
.study-panel > summary {
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
.study-panel > summary::-webkit-details-marker { display: none; }
.study-panel > summary::after { content: "▾"; color: var(--ink-soft); }
.study-panel[open] > summary::after { content: "▴"; }
.study-panel-body { display: grid; gap: 8px; padding: 0 13px 12px; }
.study-subheading {
  margin-bottom: 5px;
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .04em;
}
.study-relation-label, .formation-role {
  display: inline-flex;
  width: max-content;
  padding: 2px 6px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--ink-soft);
  font-size: 9px;
  font-weight: 800;
  line-height: 1.35;
}
.study-audio { min-width: 0; }
.usage-copy, .usage-contrast-copy, .formation-copy, .related-copy {
  min-width: 0;
  border-radius: 6px;
  outline: none;
}
.usage-copy:focus-visible, .usage-contrast-copy:focus-visible,
.formation-copy:focus-visible, .related-copy:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.usage-copy:active, .usage-contrast-copy:active,
.formation-copy:active, .related-copy:active { opacity: .72; }
.usage-detail + .usage-detail { padding-top: 8px; border-top: 1px solid var(--line); }
.usage-pattern { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.usage-pattern-jp {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 17px;
  font-weight: 750;
}
.usage-reading, .usage-contrast-reading, .formation-reading, .related-reading {
  color: var(--ink-soft);
  font-size: 11px;
}
.usage-meaning, .formation-meaning, .related-meaning {
  margin-top: 3px;
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.5;
}
.usage-contrasts { margin-top: 8px; padding-top: 7px; border-top: 1px dashed var(--line); }
.usage-contrast-list { display: grid; gap: 5px; margin: 0; padding: 0; list-style: none; }
.usage-contrast-item { display: flex; align-items: baseline; gap: 7px; flex-wrap: wrap; }
.usage-contrast-copy-main { display: flex; align-items: baseline; gap: 7px; flex-wrap: wrap; }
.usage-contrast-jp {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 14px;
  font-weight: 700;
}
.usage-contrast-meaning { color: var(--ink-soft); font-size: 11px; }
.formation-row { display: grid; gap: 7px; }
.formation-components { display: flex; align-items: center; gap: 7px; min-width: 0; }
.formation-component {
  display: grid;
  flex: 1 1 0;
  min-width: 0;
  gap: 3px;
  padding: 7px 8px;
  border-radius: 8px;
  background: var(--surface-muted);
}
.formation-word { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.formation-word-jp, .related-word {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 17px;
  font-weight: 750;
}
.formation-plus { flex: 0 0 auto; color: var(--ink-soft); font-size: 13px; }
.related-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 5px 9px;
  padding: 7px 8px;
  border-radius: 8px;
  background: var(--surface-muted);
}
.related-row .related-meaning { grid-column: 2; margin-top: 0; }
.related-copy-main { display: flex; align-items: baseline; gap: 7px; flex-wrap: wrap; }
@media (max-width: 360px) {
  .study-panel-body { padding-right: 10px; padding-left: 10px; }
  .formation-components { gap: 5px; }
  .formation-component { padding-right: 6px; padding-left: 6px; }
  .formation-plus { font-size: 11px; }
}
"""


def _text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _usage_ruby_html(pattern: Any, reading: Any) -> str:
    surface = re.sub(r"\s+", "", str(pattern))
    pronunciation = re.sub(r"\s+", "", str(reading))
    if not surface or not pronunciation:
        raise ValueError("usage pattern and reading must be non-empty")
    return render_kanji_ruby(surface, pronunciation)


def _audio_tag(filename: Any) -> str:
    if filename in {None, ""}:
        return ""
    normalized = str(filename)
    if SAFE_AUDIO_FILENAME_RE.fullmatch(normalized) is None:
        raise ValueError(f"unsafe audio filename: {normalized}")
    return (
        '<audio class="click-audio-player" preload="none" '
        f'src="{_text(normalized)}"></audio>'
    )


def _audio_filename(
    value: Mapping[str, Any], audio_by_note_id: Mapping[str, str]
) -> str:
    embedded = value.get("audio_filename")
    if embedded:
        return str(embedded)
    note_id = value.get("note_id", value.get("target_id"))
    if not isinstance(note_id, str) or not note_id:
        return ""
    return str(audio_by_note_id.get(note_id, ""))


def _audio_enabled_copy(
    *,
    content_html: str,
    filename: str,
    aria_label: str,
    css_class: str,
) -> str:
    audio = _audio_tag(filename)
    if not audio:
        return content_html
    return (
        '<div class="study-audio audio-scope">'
        f'<div class="{css_class} audio-trigger" role="button" tabindex="0" '
        f'aria-label="{_text(aria_label)}">{content_html}</div>'
        f"{audio}"
        "</div>"
    )


def study_priority_html(priority: Mapping[str, Any]) -> str:
    """Render the public priority tier without leaking internal rank/score data."""
    tier = str(priority.get("tier", ""))
    try:
        label, css_class = PRIORITY_LABELS[tier]
    except KeyError as error:
        raise ValueError(f"unknown study priority tier: {tier}") from error
    return (
        f'<span class="study-priority {css_class}" aria-label="학습 우선순위: {label}">'
        f"{label}</span>"
    )


def usage_details_html(details: Sequence[Mapping[str, Any]]) -> str:
    """Render source-grounded key usage and its contrast expressions."""
    if len(details) > MAX_USAGE_DETAILS:
        raise ValueError("usage details exceed the display limit")
    if not details:
        return ""
    rows: list[str] = []
    for detail in details:
        pattern = _usage_ruby_html(
            detail.get("pattern_jp", ""), detail.get("reading", "")
        )
        meaning = _text(detail.get("meaning_ko", ""))
        main_copy = (
            '<div class="usage-pattern" lang="ja">'
            f'<span class="usage-pattern-jp">{pattern}</span>'
            + "</div>"
        )
        main_copy = _audio_enabled_copy(
            content_html=main_copy,
            filename=_audio_filename(detail, {}),
            aria_label="핵심 용법 음성 재생",
            css_class="usage-copy",
        )
        contrasts: list[str] = []
        raw_contrasts = detail.get("contrast_items", [])
        if not isinstance(raw_contrasts, Sequence) or isinstance(
            raw_contrasts, (str, bytes)
        ):
            raise ValueError("contrast_items must be a sequence")
        for contrast in raw_contrasts:
            if not isinstance(contrast, Mapping):
                raise ValueError("contrast item must be an object")
            raw_contrast_pattern = str(contrast.get("pattern_jp", ""))
            contrast_pattern = _usage_ruby_html(
                raw_contrast_pattern, contrast.get("reading", "")
            )
            contrast_meaning = _text(contrast.get("meaning_ko", ""))
            contrast_copy = (
                '<span class="usage-contrast-copy-main">'
                f'<span class="usage-contrast-jp" lang="ja">{contrast_pattern}</span>'
                + "</span>"
            )
            contrast_copy = _audio_enabled_copy(
                content_html=contrast_copy,
                filename=_audio_filename(contrast, {}),
                aria_label=f"{raw_contrast_pattern} 음성 재생",
                css_class="usage-contrast-copy",
            )
            contrasts.append(
                '<li class="usage-contrast-item">'
                + contrast_copy
                + (
                    f'<span class="usage-contrast-meaning">{contrast_meaning}</span>'
                    if contrast_meaning
                    else ""
                )
                + "</li>"
            )
        contrast_html = ""
        if contrasts:
            contrast_html = (
                '<div class="usage-contrasts">'
                '<div class="study-subheading">비슷한 표현</div>'
                '<ul class="usage-contrast-list">'
                + "".join(contrasts)
                + "</ul></div>"
            )
        rows.append(
            '<section class="usage-detail">'
            + main_copy
            + (f'<div class="usage-meaning">{meaning}</div>' if meaning else "")
            + contrast_html
            + "</section>"
        )
    return (
        '<details class="study-panel usage-details">'
        "<summary>핵심 용법</summary>"
        '<div class="study-panel-body">'
        + "".join(rows)
        + "</div></details>"
    )


def word_formation_html(
    details: Sequence[Mapping[str, Any]],
    audio_by_note_id: Mapping[str, str],
) -> str:
    """Render exact canonical decompositions and reuse component word audio."""
    if len(details) > MAX_WORD_FORMATION_DETAILS:
        raise ValueError("word formation details exceed the display limit")
    if not details:
        return ""
    rows: list[str] = []
    for detail in details:
        relation_type = str(detail.get("relation_type", ""))
        if relation_type not in FORMATION_LABELS:
            raise ValueError(f"unknown word formation relation: {relation_type}")
        raw_components = detail.get("components", [])
        if not isinstance(raw_components, Sequence) or isinstance(
            raw_components, (str, bytes)
        ):
            raise ValueError("word formation components must be a sequence")
        components: list[str] = []
        for component in raw_components:
            if not isinstance(component, Mapping):
                raise ValueError("word formation component must be an object")
            role = str(component.get("role", ""))
            if role not in COMPONENT_LABELS:
                raise ValueError(f"unknown word formation role: {role}")
            raw_word = str(component.get("word", ""))
            word = _text(raw_word)
            reading = _text(component.get("reading", ""))
            meaning = _text(component.get("meaning", ""))
            copy = (
                '<span class="formation-word" lang="ja">'
                f'<span class="formation-word-jp">{word}</span>'
                + (f'<span class="formation-reading">{reading}</span>' if reading else "")
                + "</span>"
            )
            copy = _audio_enabled_copy(
                content_html=copy,
                filename=_audio_filename(component, audio_by_note_id),
                aria_label=f"{raw_word} 음성 재생",
                css_class="formation-copy",
            )
            components.append(
                '<div class="formation-component">'
                f'<span class="formation-role">{COMPONENT_LABELS[role]}</span>'
                + copy
                + (f'<span class="formation-meaning">{meaning}</span>' if meaning else "")
                + "</div>"
            )
        joined = '<span class="formation-plus" aria-hidden="true">＋</span>'.join(
            components
        )
        rows.append(
            '<div class="formation-row">'
            f'<span class="study-relation-label">{FORMATION_LABELS[relation_type]}</span>'
            f'<div class="formation-components">{joined}</div>'
            "</div>"
        )
    return (
        '<details class="study-panel word-formation-details">'
        "<summary>단어 구성</summary>"
        '<div class="study-panel-body">'
        + "".join(rows)
        + "</div></details>"
    )


def related_words_html(
    related_words: Sequence[Mapping[str, Any]],
    audio_by_note_id: Mapping[str, str],
) -> str:
    """Render a bounded related-word list without exposing provenance internals."""
    if len(related_words) > MAX_RELATED_WORDS:
        raise ValueError("related words exceed the display limit")
    if not related_words:
        return ""
    rows: list[str] = []
    for related in related_words:
        relation_type = str(related.get("relation_type", ""))
        if relation_type not in RELATION_LABELS:
            raise ValueError(f"unknown related-word relation: {relation_type}")
        raw_word = str(related.get("word", ""))
        word = _text(raw_word)
        reading = _text(related.get("reading", ""))
        meaning = _text(related.get("meaning", ""))
        copy = (
            '<span class="related-copy-main" lang="ja">'
            f'<span class="related-word">{word}</span>'
            + (f'<span class="related-reading">{reading}</span>' if reading else "")
            + "</span>"
        )
        copy = _audio_enabled_copy(
            content_html=copy,
            filename=_audio_filename(related, audio_by_note_id),
            aria_label=f"{raw_word} 음성 재생",
            css_class="related-copy",
        )
        rows.append(
            '<div class="related-row">'
            f'<span class="study-relation-label">{RELATION_LABELS[relation_type]}</span>'
            + copy
            + (f'<span class="related-meaning">{meaning}</span>' if meaning else "")
            + "</div>"
        )
    return (
        '<details class="study-panel related-words-details">'
        "<summary>헷갈리는 단어</summary>"
        '<div class="study-panel-body">'
        + "".join(rows)
        + "</div></details>"
    )
