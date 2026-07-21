from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from public_kanji_rendering import (  # noqa: E402
    KANJI_CARD_CSS,
    kanji_display_html,
    kanji_reference_html,
    linked_vocabulary_html,
)


class PublicKanjiRenderingTest(unittest.TestCase):
    def test_plain_and_media_glyphs_are_safe(self) -> None:
        plain = kanji_display_html("<一>", "")
        self.assertIn("&lt;一&gt;", plain)
        self.assertIn('class="kanji-card-glyph"', plain)
        self.assertNotIn('class="kanji-glyph"', plain)
        rendered = kanji_display_html("", "jlpt-v2-kanji-deadbeef.jpg")
        self.assertIn('src="jlpt-v2-kanji-deadbeef.jpg"', rendered)
        with self.assertRaisesRegex(ValueError, "unsafe media"):
            kanji_display_html("", "../glyph.jpg")

    def test_reference_panel_is_compact_and_omits_empty_rows(self) -> None:
        rendered = kanji_reference_html(
            {
                "kun_reading": "ひと",
                "on_reading": "イチ",
                "radical": "一",
                "strokes": "1",
            }
        )
        self.assertIn("음독", rendered)
        self.assertIn("イチ", rendered)
        self.assertIn("훈독", rendered)
        self.assertIn('<section class="kanji-panel kanji-reference">', rendered)
        self.assertIn('<h2 class="kanji-panel-heading">읽기·구성</h2>', rendered)
        self.assertNotIn("<details", rendered)
        self.assertNotIn("<summary", rendered)
        self.assertEqual(kanji_reference_html({}), "")

    def test_reference_panel_normalizes_compatibility_radicals(self) -> None:
        rendered = kanji_reference_html({"radical": "羽・羽", "strokes": "６"})
        self.assertIn("<dd>羽</dd>", rendered)
        self.assertNotIn("羽・羽", rendered)

    def test_linked_vocabulary_reuses_clickable_word_audio(self) -> None:
        rendered = linked_vocabulary_html(
            [
                {
                    "audio_filename": "word-1.wav",
                    "jlpt_level": "N5",
                    "meaning": "하나",
                    "note_id": "v1",
                    "priority_tier": "01_essential",
                    "reading": "ひとつ",
                    "word": "一つ",
                },
                {
                    "audio_filename": "word-2.wav",
                    "jlpt_level": "N4",
                    "meaning": "함께",
                    "note_id": "v2",
                    "priority_tier": "02_standard",
                    "reading": "いっしょ",
                    "word": "一緒",
                },
            ]
        )
        self.assertIn("어휘·음성", rendered)
        self.assertNotIn("JLPT MAX 어휘·음성", rendered)
        self.assertIn(
            '<audio class="click-audio-player" preload="none" src="word-1.wav">',
            rendered,
        )
        self.assertNotIn("[sound:", rendered)
        self.assertIn("필수", rendered)
        self.assertIn("표준", rendered)
        self.assertIn('role="button"', rendered)
        self.assertIn('<section class="kanji-panel kanji-vocabulary">', rendered)
        self.assertNotIn("<details", rendered)
        self.assertNotIn("<summary", rendered)
        self.assertEqual(linked_vocabulary_html([]), "")
        with self.assertRaisesRegex(ValueError, "invalid linked vocabulary"):
            linked_vocabulary_html(
                [
                    {
                        "audio_filename": None,
                        "jlpt_level": "N5",
                        "meaning": "하나",
                        "note_id": "broken",
                        "priority_tier": "01_essential",
                        "reading": "ひとつ",
                        "word": "一つ",
                    }
                ]
            )

    def test_linked_vocabulary_accepts_public_mp3_transport(self) -> None:
        rendered = linked_vocabulary_html(
            [
                {
                    "audio_filename": "word-1.mp3",
                    "jlpt_level": "N5",
                    "meaning": "하나",
                    "note_id": "v1",
                    "priority_tier": "01_essential",
                    "reading": "ひとつ",
                    "word": "一つ",
                }
            ]
        )
        self.assertIn('src="word-1.mp3"', rendered)

    def test_rendering_contract_includes_mobile_and_night_mode_support(self) -> None:
        self.assertIn("@media (max-width: 360px)", KANJI_CARD_CSS)
        self.assertIn(
            "grid-template-columns: max-content minmax(0, 1fr)",
            KANJI_CARD_CSS,
        )
        self.assertIn("align-items: center", KANJI_CARD_CSS)
        self.assertIn("gap: 4px 10px", KANJI_CARD_CSS)
        self.assertIn("min-height: 28px", KANJI_CARD_CSS)
        self.assertIn("font-size: clamp(70px, 22vw, 108px)", KANJI_CARD_CSS)
        self.assertIn(".kanji-card-header", KANJI_CARD_CSS)
        self.assertIn("white-space: nowrap", KANJI_CARD_CSS)
        self.assertIn("text-overflow: ellipsis", KANJI_CARD_CSS)
        self.assertNotIn(".kanji-unit", KANJI_CARD_CSS)
        self.assertNotIn(".kanji-theme", KANJI_CARD_CSS)
        self.assertNotIn("kanji-stroke", KANJI_CARD_CSS)
        self.assertNotIn("overflow-x", KANJI_CARD_CSS)
        self.assertNotIn("kanji-panel summary", KANJI_CARD_CSS)


if __name__ == "__main__":
    unittest.main()
