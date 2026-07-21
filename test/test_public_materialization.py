from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from public_materialization import (
    _gilbut_hint_map,
    _gilbut_study_characters,
    _standalone_kanji_character,
    _standalone_kanji_reference,
)
from public_kanji import Kanjidic2Snapshot, PublicKanjiMaterializer


class PublicMaterializationTests(unittest.TestCase):
    def test_uses_only_single_canonical_character_for_card_reference(self) -> None:
        self.assertEqual(
            _standalone_kanji_character(
                {"canonical_character": "休", "glyph_text": "休"}
            ),
            "休",
        )
        self.assertEqual(
            _standalone_kanji_character(
                {"canonical_character": "", "glyph_text": "遡/溯"}
            ),
            "",
        )
        self.assertEqual(
            _standalone_kanji_character(
                {"canonical_character": "", "glyph_text": "艹/䒑"}
            ),
            "",
        )

    def test_composite_glyphs_still_supply_vocabulary_study_hints(self) -> None:
        self.assertEqual(
            _gilbut_study_characters(
                {"canonical_character": "", "glyph_text": "遡/溯"}
            ),
            ("遡", "溯"),
        )
        self.assertEqual(
            _gilbut_study_characters(
                {"canonical_character": "", "glyph_text": ""}
            ),
            (),
        )
        self.assertEqual(
            _gilbut_study_characters(
                {"canonical_character": "戶", "glyph_text": "戶"}
            ),
            ("戶", "戸"),
        )

    def test_non_kanjidic2_standalone_glyph_keeps_empty_reference(self) -> None:
        snapshot = Kanjidic2Snapshot(
            entries={},
            file_version="4",
            database_version="test",
            date_of_creation="2026-07-20",
            sha256="0" * 64,
        )
        materializer = PublicKanjiMaterializer(snapshot, {})
        self.assertEqual(
            _standalone_kanji_reference(
                {"canonical_character": "㐄", "glyph_text": "㐄"},
                materializer,
            ),
            {},
        )

    def test_repeated_gilbut_character_keeps_distinct_hints_in_slot_order(self) -> None:
        self.assertEqual(
            _gilbut_hint_map(
                [
                    {
                        "canonical_character": "敢",
                        "glyph_text": "敢",
                        "meaning": "용감 감",
                    },
                    {
                        "canonical_character": "敢",
                        "glyph_text": "敢",
                        "meaning": "감히 감·과감할 감",
                    },
                    {
                        "canonical_character": "敢",
                        "glyph_text": "敢",
                        "meaning": "용감 감",
                    },
                ]
            ),
            {"敢": "용감 감 / 감히 감·과감할 감"},
        )


if __name__ == "__main__":
    unittest.main()
