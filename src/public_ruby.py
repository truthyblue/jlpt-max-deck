"""Ruby and plain-text helpers used by public card rendering."""

from __future__ import annotations

import html
import re
import unicodedata
from html.parser import HTMLParser


TTS_RE = re.compile(r"\[anki:tts[^]]*].*?\[/anki:tts]", re.DOTALL)
SOUND_RE = re.compile(r"\[sound:[^]]+]", re.DOTALL)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
KANJI_CHAR_RE = re.compile(
    r"[\u3007\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff々〆ヶ]"
)
KANA_READING_EQUIVALENTS = {
    "は": frozenset(("は", "わ")),
    "へ": frozenset(("へ", "え")),
    "を": frozenset(("を", "お")),
}

class _PlainJapaneseParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "rt":
            self.ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "rt" and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)


class _RubyHTMLSanitizer(HTMLParser):
    ALLOWED_TAGS = {"ruby", "rb", "rt", "rp"}
    BLOCKED_TAGS = {"script", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.BLOCKED_TAGS:
            self.blocked_depth += 1
        elif not self.blocked_depth and tag in self.ALLOWED_TAGS:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.BLOCKED_TAGS and self.blocked_depth:
            self.blocked_depth -= 1
        elif not self.blocked_depth and tag in self.ALLOWED_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            self.parts.append(html.escape(data, quote=False))


def _kana_match_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(
        chr(ord(character) - 0x60)
        if 0x30A1 <= ord(character) <= 0x30F6
        else character
        for character in normalized
    )


def _kanji_runs(value: str) -> list[tuple[bool, str]]:
    runs: list[tuple[bool, str]] = []
    for character in value:
        is_kanji = KANJI_CHAR_RE.fullmatch(character) is not None
        if runs and runs[-1][0] == is_kanji:
            previous_kind, previous_text = runs[-1]
            runs[-1] = (previous_kind, previous_text + character)
        else:
            runs.append((is_kanji, character))
    return runs


def _kana_anchor_matches(text_key: str, reading_key: str, start: int) -> bool:
    candidate = reading_key[start : start + len(text_key)]
    if len(candidate) != len(text_key):
        return False
    return all(
        reading_character
        in KANA_READING_EQUIVALENTS.get(
            text_character, frozenset((text_character,))
        )
        for text_character, reading_character in zip(text_key, candidate)
    )


def _find_kana_anchor(
    text_key: str, reading_key: str, start: int
) -> int | None:
    for index in range(start, len(reading_key) - len(text_key) + 1):
        if _kana_anchor_matches(text_key, reading_key, index):
            return index
    return None


def _align_kanji_readings(
    runs: list[tuple[bool, str]], reading: str
) -> dict[int, str] | None:
    reading_key = _kana_match_key(reading)
    if len(reading_key) != len(reading):
        return None

    def align(run_index: int, reading_index: int) -> dict[int, str] | None:
        if run_index == len(runs):
            return {} if reading_index == len(reading_key) else None
        is_kanji, text = runs[run_index]
        if not is_kanji:
            text_key = _kana_match_key(text)
            if len(text_key) != len(text) or not _kana_anchor_matches(
                text_key, reading_key, reading_index
            ):
                return None
            return align(run_index + 1, reading_index + len(text_key))

        if run_index + 1 == len(runs):
            if reading_index >= len(reading_key):
                return None
            return {run_index: reading[reading_index:]}

        anchor_key = _kana_match_key(runs[run_index + 1][1])
        anchor_index = _find_kana_anchor(
            anchor_key, reading_key, reading_index + 1
        )
        while anchor_index is not None:
            remainder = align(run_index + 1, anchor_index)
            if remainder is not None:
                return {
                    run_index: reading[reading_index:anchor_index],
                    **remainder,
                }
            anchor_index = _find_kana_anchor(
                anchor_key, reading_key, anchor_index + 1
            )
        return None

    return align(0, 0)


def render_kanji_ruby(text: str, reading: str) -> str:
    """Render ruby on kanji runs only, using kana text as alignment anchors."""
    if not text:
        raise ValueError("ruby base text is empty")
    if not reading:
        raise ValueError("ruby reading is empty")
    runs = _kanji_runs(text)
    if not any(is_kanji for is_kanji, _text in runs):
        return html.escape(text, quote=False)
    aligned = _align_kanji_readings(runs, reading)
    if aligned is None:
        raise ValueError(f"cannot align ruby base {text!r} with reading {reading!r}")

    rendered: list[str] = []
    for index, (is_kanji, run_text) in enumerate(runs):
        escaped_text = html.escape(run_text, quote=False)
        if not is_kanji:
            rendered.append(escaped_text)
            continue
        run_reading = aligned[index]
        rendered.append(
            f"<ruby><rb>{escaped_text}</rb>"
            f"<rt>{html.escape(run_reading, quote=False)}</rt></ruby>"
        )
    return "".join(rendered)


class _KanjiOnlyRubyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.base_parts: list[str] = []
        self.reading_parts: list[str] = []
        self.in_ruby = False
        self.in_rt = False
        self.in_rp = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "ruby" and not self.in_ruby:
            self.in_ruby = True
            self.base_parts = []
            self.reading_parts = []
        elif self.in_ruby and tag == "rt":
            self.in_rt = True
        elif self.in_ruby and tag == "rp":
            self.in_rp = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.in_ruby and tag == "rt":
            self.in_rt = False
        elif self.in_ruby and tag == "rp":
            self.in_rp = False
        elif self.in_ruby and tag == "ruby":
            self._flush_ruby()

    def handle_data(self, data: str) -> None:
        if not self.in_ruby:
            self.parts.append(html.escape(data, quote=False))
        elif self.in_rp:
            return
        elif self.in_rt:
            self.reading_parts.append(data)
        else:
            self.base_parts.append(data)

    def close(self) -> None:
        super().close()
        if self.in_ruby:
            self._flush_ruby()

    def _flush_ruby(self) -> None:
        base = "".join(self.base_parts)
        reading = "".join(self.reading_parts)
        try:
            rendered = render_kanji_ruby(base, reading)
        except ValueError:
            rendered = html.escape(base, quote=False)
        self.parts.append(rendered)
        self.base_parts = []
        self.reading_parts = []
        self.in_ruby = False
        self.in_rt = False
        self.in_rp = False


def clean_example_html(value: str) -> str:
    value = COMMENT_RE.sub("", value)
    value = SOUND_RE.sub("", value)
    value = TTS_RE.sub("", value)
    return re.sub(r"\s+", " ", value).strip()


def safe_ruby_html(value: str) -> str:
    """Keep only static ruby markup and escaped text for display in Anki fields."""
    parser = _RubyHTMLSanitizer()
    parser.feed(clean_example_html(value))
    parser.close()
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def kanji_only_ruby_html(value: str) -> str:
    """Normalize static ruby so only kanji runs remain ruby bases."""
    parser = _KanjiOnlyRubyParser()
    parser.feed(safe_ruby_html(value))
    parser.close()
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def plain_japanese(value: str) -> str:
    parser = _PlainJapaneseParser()
    parser.feed(clean_example_html(value))
    return re.sub(r"\s+", " ", html.unescape("".join(parser.parts))).strip()
