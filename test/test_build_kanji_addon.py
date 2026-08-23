from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from build_kanji_addon import (  # noqa: E402
    KanjiAddonBuildError,
    _align_pdf_slots,
    _fill_note,
    _glyph_matches,
    _unit_matches,
)
from public_kanji import (  # noqa: E402
    GilbutKanjiSlot,
    gilbut_vector_glyph_png,
)


TEST_LIFECYCLE = {
    "test_contracts": {
        "KanjiAddonTest.test_vector_slot_writes_png_media": {
            "protected_contract": (
                "the optional kanji builder writes the 14 PDF outline glyphs as transparent PNG media instead of SVG"
            ),
            "not_subsumed_by": (
                "note counts and transparent CSS classes can pass while the builder still packages hole-filling SVG media"
            ),
        },
        "KanjiAddonTest.test_vector_pdf_hole_remains_transparent_in_png": {
            "protected_contract": (
                "a white counter inside a PDF vector glyph remains transparent in the generated PNG"
            ),
            "not_subsumed_by": (
                "checking the PNG filename and outer alpha cannot detect a black-filled inner counter"
            ),
        },
    }
}


class FakeNote(dict[str, str]):
    pass


def _write_vector_hole_pdf(path: Path) -> None:
    stream = b"0 0 0 rg\n20 20 60 60 re\n30 30 40 40 re\nf*\n"
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] "
            b"/Resources << >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream
        + b"endstream",
    )
    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode("ascii"))
        payload.extend(body)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(payload)


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

    def test_vector_slot_writes_png_media(self) -> None:
        note = FakeNote(
            SortKey="K000432",
            Volume="상권",
            Unit="0432",
            Meaning="",
            GlyphHTML="",
        )
        slot = GilbutKanjiSlot(
            sequence=432,
            source_id="ilsang-muutta-upper",
            source_sha256="0" * 64,
            volume_code="upper",
            page=1,
            row=1,
            column=1,
            source_label="0432",
            glyph_kind="vector",
            glyph_text="",
            glyph_bbox=(0.0, 0.0, 1.0, 1.0),
            meaning="크게 보일 관",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "upper.pdf"
            source.write_bytes(b"fixture")
            with patch(
                "build_kanji_addon.gilbut_vector_glyph_png",
                return_value=b"\x89PNG\r\n\x1a\nfixture",
            ):
                media_record = _fill_note(
                    note,
                    slot,
                    source_paths={"ilsang-muutta-upper": source},
                    media_root=root,
                )
        self.assertIsNotNone(media_record)
        assert media_record is not None
        self.assertTrue(media_record[0].endswith(".png"))
        self.assertFalse(media_record[0].endswith(".svg"))
        self.assertIn(
            'class="kanji-glyph-image kanji-glyph-transparent"',
            note["GlyphHTML"],
        )
        self.assertTrue(note["GlyphHTML"].endswith('alt="원본 한자 자형">'))
        self.assertEqual(note["Meaning"], "크게 보일 관")

    def test_vector_pdf_hole_remains_transparent_in_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "vector-hole.pdf"
            _write_vector_hole_pdf(source)
            slot = GilbutKanjiSlot(
                sequence=1,
                source_id="fixture",
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                volume_code="upper",
                page=1,
                row=1,
                column=1,
                source_label="0001",
                glyph_kind="vector",
                glyph_text="",
                glyph_bbox=(20.0, 20.0, 80.0, 80.0),
                meaning="fixture",
            )
            payload = gilbut_vector_glyph_png(source, slot)

        with Image.open(BytesIO(payload)) as image:
            image.load()
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.mode, "RGBA")
            alpha = image.getchannel("A")
            self.assertEqual(alpha.getpixel((0, 0)), 0)
            self.assertEqual(
                alpha.getpixel((image.width // 2, image.height // 2)),
                0,
            )
            self.assertEqual(alpha.getextrema()[1], 255)
            self.assertEqual(set(alpha.get_flattened_data()), {0, 255})

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
