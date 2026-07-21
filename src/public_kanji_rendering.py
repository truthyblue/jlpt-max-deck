"""Render compact HTML fragments for public kanji cards."""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


MAX_LINKED_VOCABULARY = 3
SAFE_MEDIA_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PRIORITY_LABELS = {
    "01_essential": "필수",
    "02_standard": "표준",
    "03_extended": "확장",
}

KANJI_CARD_CSS = """
.kanji-card { min-height: 45vh; }
.kanji-card-header {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  white-space: nowrap;
}
.kanji-volume { flex: 0 0 auto; }
.kanji-context {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--ink-soft);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.3;
}
.kanji-hero {
  display: grid;
  place-items: center;
  min-height: 150px;
  margin-top: 14px;
}
.kanji-card-glyph {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: clamp(70px, 22vw, 108px);
  font-weight: 650;
  line-height: 1.05;
  overflow-wrap: anywhere;
}
.kanji-glyph-image {
  display: block;
  width: min(108px, 32vw);
  max-height: 124px;
  object-fit: contain;
}
.kanji-meaning {
  margin-top: 14px;
  color: var(--ink);
  font-size: clamp(23px, 6vw, 32px);
  font-weight: 800;
  line-height: 1.45;
  text-align: center;
}
.kanji-panel {
  margin-top: 8px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  overflow: hidden;
}
.kanji-panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 34px;
  margin: 0;
  padding: 7px 11px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .05em;
}
.kanji-panel-count { margin-left: auto; color: var(--ink-soft); font-size: 10px; }
.kanji-reference-grid {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  align-items: center;
  gap: 4px 10px;
  margin: 0;
  padding: 2px 12px 12px;
}
.kanji-reference-grid dt, .kanji-reference-grid dd {
  display: flex;
  align-items: center;
  min-height: 28px;
  margin: 0;
  padding: 4px 0;
  line-height: 1.45;
}
.kanji-reference-grid dt { color: var(--ink-soft); font-size: 10px; font-weight: 800; }
.kanji-reference-grid dd {
  min-width: 0;
  border-bottom: 1px solid var(--line);
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 14px;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.kanji-vocabulary-list { display: grid; gap: 1px; padding: 0 13px 12px; }
.kanji-vocabulary-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 5px 9px;
  padding: 8px;
  border-radius: 8px;
  background: var(--surface-muted);
}
.kanji-vocabulary-copy { min-width: 0; outline: none; }
.kanji-vocabulary-copy:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.kanji-vocabulary-main { display: flex; align-items: baseline; gap: 7px; flex-wrap: wrap; }
.kanji-vocabulary-word {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 17px;
  font-weight: 800;
}
.kanji-vocabulary-reading { color: var(--ink-soft); font-size: 11px; }
.kanji-vocabulary-meaning { grid-column: 1; color: var(--ink-soft); font-size: 11px; line-height: 1.45; }
.kanji-vocabulary-meta {
  grid-column: 2;
  grid-row: 1 / span 2;
  color: var(--ink-soft);
  font-size: 9px;
  font-weight: 800;
  white-space: nowrap;
}
@media (max-width: 360px) {
  .kanji-hero { min-height: 138px; }
  .kanji-panel-heading, .kanji-vocabulary-list { padding-right: 10px; padding-left: 10px; }
  .kanji-reference-grid { padding-right: 10px; padding-left: 10px; }
}
"""


def _text(value: Any) -> str:
    return html.escape(unicodedata.normalize("NFC", str(value)), quote=True)


def _canonical_radical(value: Any) -> str:
    parts: list[str] = []
    for raw_part in str(value).split("・"):
        part = unicodedata.normalize("NFC", raw_part)
        if part and part not in parts:
            parts.append(part)
    return "・".join(parts)


def _safe_media_filename(value: Any) -> str:
    if not isinstance(value, str) or SAFE_MEDIA_FILENAME_RE.fullmatch(value) is None:
        raise ValueError(f"unsafe media filename: {value}")
    return value


def kanji_display_html(glyph_text: str, glyph_media_filename: str) -> str:
    """Render exactly one source glyph as text or a packaged image."""
    if bool(glyph_text) == bool(glyph_media_filename):
        raise ValueError("kanji display needs exactly one text or media glyph")
    if glyph_media_filename:
        filename = _safe_media_filename(glyph_media_filename)
        return (
            f'<img class="kanji-glyph-image" src="{filename}" '
            'alt="원본 한자 자형">'
        )
    return f'<span class="kanji-card-glyph" lang="ja">{_text(glyph_text)}</span>'


def kanji_reference_html(reference: Mapping[str, Any]) -> str:
    """Render optional source-grounded reading, radical, and stroke metadata."""
    radical = reference.get("radical")
    rows = [
        ("음독", reference.get("on_reading")),
        ("훈독", reference.get("kun_reading")),
        ("부수", _canonical_radical(radical) if radical not in {None, ""} else radical),
        ("획수", reference.get("strokes")),
    ]
    rendered = [
        f"<dt>{label}</dt><dd>{_text(value)}</dd>"
        for label, value in rows
        if value not in {None, ""}
    ]
    if not rendered:
        return ""
    return (
        '<section class="kanji-panel kanji-reference">'
        '<h2 class="kanji-panel-heading">읽기·구성</h2>'
        '<dl class="kanji-reference-grid">'
        + "".join(rendered)
        + "</dl></section>"
    )


def linked_vocabulary_html(links: Sequence[Mapping[str, Any]]) -> str:
    """Render up to three canonical vocabulary links with reused word audio."""
    if len(links) > MAX_LINKED_VOCABULARY:
        raise ValueError("linked vocabulary exceeds the display limit")
    if not links:
        return ""
    rows: list[str] = []
    seen_ids: set[str] = set()
    for link in links:
        note_id = link.get("note_id")
        word = link.get("word")
        reading = link.get("reading")
        meaning = link.get("meaning")
        level = link.get("jlpt_level")
        tier = link.get("priority_tier")
        audio_filename = link.get("audio_filename")
        if (
            not isinstance(note_id, str)
            or not note_id
            or note_id in seen_ids
            or not isinstance(word, str)
            or not word
            or not isinstance(reading, str)
            or not reading
            or not isinstance(meaning, str)
            or not meaning
            or level not in {"N5", "N4", "N3", "N2", "N1"}
            or tier not in PRIORITY_LABELS
            or not isinstance(audio_filename, str)
            or not audio_filename.endswith((".wav", ".mp3"))
        ):
            raise ValueError(f"invalid linked vocabulary: {note_id}")
        seen_ids.add(note_id)
        filename = _safe_media_filename(audio_filename)
        rows.append(
            '<div class="kanji-vocabulary-row audio-scope">'
            '<div class="kanji-vocabulary-copy audio-trigger" role="button" '
            f'tabindex="0" aria-label="{_text(word)} 음성 재생">'
            '<div class="kanji-vocabulary-main" lang="ja">'
            f'<span class="kanji-vocabulary-word">{_text(word)}</span>'
            f'<span class="kanji-vocabulary-reading">{_text(reading)}</span>'
            "</div></div>"
            f'<audio class="click-audio-player" preload="none" '
            f'src="{filename}"></audio>'
            f'<div class="kanji-vocabulary-meaning">{_text(meaning)}</div>'
            f'<div class="kanji-vocabulary-meta">{level} · {PRIORITY_LABELS[str(tier)]}</div>'
            "</div>"
        )
    return (
        '<section class="kanji-panel kanji-vocabulary">'
        '<h2 class="kanji-panel-heading">어휘·음성'
        f'<span class="kanji-panel-count">{len(rows)}</span></h2>'
        '<div class="kanji-vocabulary-list">'
        + "".join(rows)
        + "</div></section>"
    )
