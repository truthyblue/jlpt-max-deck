from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from direct_release_contract import (  # noqa: E402
    EXPECTED_KANJI_ADDON_CARDS,
    EXPECTED_KANJI_ADDON_NOTES,
    DirectReleaseContractError,
    EXPECTED_KANJI_NOTES,
    EXPECTED_KANJI_VECTOR_GLYPHS,
    KANJI_BUILDER_EXECUTABLES,
    KANJI_FIELDS,
    PRIVATE_KANJI_DECK_ROOTS,
    PRIVATE_KANJI_NOTETYPE_NAMES,
    POLICY_VERSION,
    SCHEMA_VERSION,
    kanji_builder_archive_path,
    kanji_builder_file_mode,
    release_filenames,
    skeleton_note_record,
    validate_skeleton_manifest,
)


TEST_LIFECYCLE = {
    "test_contracts": {
        "DirectReleaseContractTest.test_v130_private_families_and_personal_addon_counts_are_explicit": {
            "protected_contract": (
                "the public core excludes both private kanji families while the personal builder closes all 4,674 reading and writing cards"
            ),
            "not_subsumed_by": (
                "release-name and skeleton-manifest tests cover one reading family and cannot detect writing cards leaking into the public core"
            ),
        },
    }
}


class DirectReleaseContractTest(unittest.TestCase):
    def test_v130_private_families_and_personal_addon_counts_are_explicit(self) -> None:
        self.assertEqual(
            PRIVATE_KANJI_NOTETYPE_NAMES,
            (
                "JLPT MAX덱 일상무따",
                "JLPT MAX덱 일상무따 쓰기",
            ),
        )
        self.assertEqual(
            PRIVATE_KANJI_DECK_ROOTS,
            (
                "JLPT MAX덱::일상무따",
                "JLPT MAX덱::한자",
            ),
        )
        self.assertEqual(EXPECTED_KANJI_ADDON_NOTES, 4_674)
        self.assertEqual(EXPECTED_KANJI_ADDON_CARDS, 4_674)
        self.assertEqual(
            KANJI_FIELDS,
            (
                "KanjiID",
                "Volume",
                "Unit",
                "Theme",
                "GlyphHTML",
                "Meaning",
                "KanjiFacts",
                "KanjiReference",
                "LinkedVocabulary",
                "StrokeOrder",
                "SortKey",
            ),
        )

    def test_release_names_separate_core_and_optional_kanji(self) -> None:
        names = release_filenames("1.0.1")
        self.assertEqual(names["core_apkg"], "JLPT-MAX-Deck-1.0.1.apkg")
        self.assertEqual(
            names["kanji_builder"], "JLPT-MAX-kanji-builder-1.0.1.zip"
        )
        self.assertEqual(
            names["kanji_addon"], "JLPT-MAX-kanji-addon-1.0.1.apkg"
        )
        self.assertEqual(
            names["kanji_skeleton"], "JLPT-MAX-kanji-skeleton-1.0.1.asset"
        )
        self.assertFalse(names["kanji_skeleton"].endswith(".apkg"))
        self.assertNotIn("autoplay_addon", names)

    def test_beginner_launchers_are_prominent_in_the_builder_archive(self) -> None:
        self.assertEqual(
            kanji_builder_archive_path("scripts/start-kanji-addon.cmd"),
            "Windows에서 한자 확장 만들기.cmd",
        )
        self.assertEqual(
            kanji_builder_archive_path("scripts/start-kanji-addon.command"),
            "Mac에서 한자 확장 만들기.command",
        )
        self.assertEqual(
            kanji_builder_archive_path("docs/kanji-builder-assets.txt"),
            "assets/README.txt",
        )
        self.assertEqual(
            kanji_builder_archive_path("docs/kanji-builder.md"),
            "README.md",
        )

    def test_only_shell_launchers_receive_execute_permissions(self) -> None:
        self.assertEqual(
            KANJI_BUILDER_EXECUTABLES,
            (
                "scripts/build-kanji-addon.sh",
                "scripts/start-kanji-addon.command",
                "scripts/start-kanji-addon.sh",
            ),
        )
        for relative in KANJI_BUILDER_EXECUTABLES:
            with self.subTest(relative=relative):
                self.assertEqual(kanji_builder_file_mode(relative), 0o755)
        self.assertEqual(
            kanji_builder_file_mode("scripts/start-kanji-addon.cmd"),
            0o644,
        )

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
            "product_version": "1.0.1",
            "schema_version": SCHEMA_VERSION,
            "skeleton_apkg": "JLPT-MAX-kanji-skeleton-1.0.1.asset",
            "skeleton_apkg_sha256": "0" * 64,
            "vector_glyph_count": EXPECTED_KANJI_VECTOR_GLYPHS,
        }
        self.assertEqual(len(validate_skeleton_manifest(manifest)), 2_337)


if __name__ == "__main__":
    unittest.main()
