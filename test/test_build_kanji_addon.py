from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from build_kanji_addon import (  # noqa: E402
    KanjiAddonBuildError,
    _align_pdf_slots,
    _fill_note,
    _glyph_matches,
    _unit_matches,
)
from public_kanji import GilbutKanjiSlot  # noqa: E402


class FakeNote(dict[str, str]):
    pass


class KanjiAddonTest(unittest.TestCase):
    @staticmethod
    def _slot(sequence: int, label: str) -> GilbutKanjiSlot:
        return GilbutKanjiSlot(
            sequence=sequence,
            source_id="ilsang-muutta-upper",
            source_sha256="0" * 64,
            volume_code="upper",
            page=1,
            row=1,
            column=1,
            source_label=label,
            glyph_kind="text",
            glyph_text="一",
            glyph_bbox=(0.0, 0.0, 1.0, 1.0),
            meaning="하나 일",
        )

    def test_pdf_slots_align_by_unit_when_printed_order_differs(self) -> None:
        notes = [
            FakeNote(SortKey="K000257", Volume="상권", Unit="252"),
            FakeNote(
                SortKey="K000258",
                Volume="상권",
                Unit="252.5 추가자 6",
            ),
        ]
        slots = [self._slot(257, "추가자6"), self._slot(258, "0252")]
        aligned = _align_pdf_slots(notes, slots)
        self.assertEqual(
            [slot.source_label for slot in aligned],
            ["0252", "추가자6"],
        )

    def test_glyph_equivalence_accepts_printed_traditional_form(self) -> None:
        self.assertTrue(_glyph_matches("戶", "戸"))
        self.assertFalse(_glyph_matches("戶", "口"))

    def test_additional_unit_spacing_is_normalized(self) -> None:
        self.assertTrue(_unit_matches("추가자 6", "추가자6"))
        self.assertFalse(_unit_matches("추가자 6", "추가자7"))

    def test_numeric_unit_ignores_pdf_zero_padding(self) -> None:
        self.assertTrue(_unit_matches("1", "0001"))
        self.assertFalse(_unit_matches("1", "0002"))

    def test_text_slot_fills_only_meaning(self) -> None:
        note = FakeNote(
            SortKey="K000001",
            Volume="상권",
            Unit="0001",
            Meaning="",
            GlyphHTML='<span class="kanji-card-glyph" lang="ja">一</span>',
        )
        slot = GilbutKanjiSlot(
            sequence=1,
            source_id="ilsang-muutta-upper",
            source_sha256="0" * 64,
            volume_code="upper",
            page=1,
            row=1,
            column=1,
            source_label="0001",
            glyph_kind="text",
            glyph_text="一",
            glyph_bbox=(0.0, 0.0, 1.0, 1.0),
            meaning="하나 일",
        )
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(
                _fill_note(
                    note,
                    slot,
                    source_paths={},
                    media_root=Path(directory),
                )
            )
        self.assertEqual(note["Meaning"], "하나 일")

    def test_prepopulated_meaning_is_rejected(self) -> None:
        note = FakeNote(
            SortKey="K000001",
            Volume="상권",
            Unit="0001",
            Meaning="출판사 뜻",
            GlyphHTML='<span class="kanji-card-glyph" lang="ja">一</span>',
        )
        slot = GilbutKanjiSlot(
            sequence=1,
            source_id="ilsang-muutta-upper",
            source_sha256="0" * 64,
            volume_code="upper",
            page=1,
            row=1,
            column=1,
            source_label="0001",
            glyph_kind="text",
            glyph_text="一",
            glyph_bbox=(0.0, 0.0, 1.0, 1.0),
            meaning="하나 일",
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KanjiAddonBuildError):
                _fill_note(
                    note,
                    slot,
                    source_paths={},
                    media_root=Path(directory),
                )


if __name__ == "__main__":
    unittest.main()
