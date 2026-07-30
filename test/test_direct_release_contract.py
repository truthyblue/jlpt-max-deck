from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from direct_release_contract import (  # noqa: E402
    DirectReleaseContractError,
    EXPECTED_KANJI_NOTES,
    EXPECTED_KANJI_VECTOR_GLYPHS,
    KANJI_FIELDS,
    POLICY_VERSION,
    SCHEMA_VERSION,
    release_filenames,
    skeleton_note_record,
    validate_skeleton_manifest,
)


class DirectReleaseContractTest(unittest.TestCase):
    def test_release_names_separate_core_and_optional_kanji(self) -> None:
        names = release_filenames("1.0.0")
        self.assertEqual(names["core_apkg"], "JLPT-MAX-Deck-1.0.0.apkg")
        self.assertEqual(
            names["kanji_builder"], "JLPT-MAX-kanji-builder-1.0.0.zip"
        )
        self.assertEqual(
            names["kanji_addon"], "JLPT-MAX-kanji-addon-1.0.0.apkg"
        )
        self.assertNotIn("autoplay_addon", names)

    def test_release_version_must_be_semver_triplet(self) -> None:
        with self.assertRaises(DirectReleaseContractError):
            release_filenames("1.0")

    def test_skeleton_manifest_closes_every_note(self) -> None:
        records = []
        for sequence in range(1, EXPECTED_KANJI_NOTES + 1):
            note: dict[str, str] = dict.fromkeys(KANJI_FIELDS, "")
            note.update(
                {
                    "KanjiID": f"kanji-{sequence}",
                    "Volume": "상권" if sequence <= 1_223 else "하권",
                    "Unit": str(sequence),
                    "GlyphHTML": (
                        "" if sequence <= EXPECTED_KANJI_VECTOR_GLYPHS else
                        '<span class="kanji-card-glyph" lang="ja">一</span>'
                    ),
                    "SortKey": f"K{sequence:06d}",
                }
            )
            records.append(skeleton_note_record(note))
        manifest = {
            "kanji_note_count": EXPECTED_KANJI_NOTES,
            "notes": records,
            "policy_version": POLICY_VERSION,
            "product_version": "1.0.0",
            "schema_version": SCHEMA_VERSION,
            "skeleton_apkg": "JLPT-MAX-kanji-skeleton-1.0.0.apkg",
            "skeleton_apkg_sha256": "0" * 64,
            "vector_glyph_count": EXPECTED_KANJI_VECTOR_GLYPHS,
        }
        self.assertEqual(len(validate_skeleton_manifest(manifest)), 2_337)


if __name__ == "__main__":
    unittest.main()
