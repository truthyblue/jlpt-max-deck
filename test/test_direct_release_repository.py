from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import public_release as subject  # noqa: E402
import build_kanji_addon as builder_subject  # noqa: E402

from direct_release_contract import (  # noqa: E402
    EXPECTED_KANJI_NOTES,
    EXPECTED_KANJI_STATIC_MEDIA,
    EXPECTED_KANJI_VECTOR_GLYPHS,
    KANJI_BUILDER_FILES,
    KANJI_DECK_ROOT,
    KANJI_FIELDS,
    KANJI_NOTETYPE_NAME,
    KANJI_REQUIRED_STATIC_MEDIA,
    PRIVATE_KANJI_NOTETYPE_NAMES,
    POLICY_VERSION,
    SCHEMA_VERSION,
    kanji_builder_archive_path,
    release_filenames,
    sha256_file,
    sha256_json,
)
from public_release import (  # noqa: E402
    PublicReleaseError,
    _canonicalize_kanji_root,
    _private_kanji_note_ids,
    _package_kanji_builder,
    _reuse_kanji_builder,
    _zip_write,
    prepare_direct_release,
)
from build_kanji_addon import _kanji_note_families  # noqa: E402


TEST_LIFECYCLE = {
    "test_contracts": {
        "DirectReleaseRepositoryTest.test_current_kanji_fields_close_skeleton_semantics": {
            "protected_contract": (
                "the public builder accepts the approved 11-field kanji models and binds facts and stroke-order content into the skeleton proof"
            ),
            "not_subsumed_by": (
                "family-count tests can pass while an older field list rejects the accepted private APKG before public artifacts are prepared"
            ),
        },
        "DirectReleaseRepositoryTest.test_kanji_addon_requires_template_attribution_media": {
            "protected_contract": (
                "the generated reading and writing addon contains the exact AnimCJK license file referenced by both card templates"
            ),
            "not_subsumed_by": (
                "stroke-image closure and note counts do not prove that the separately licensed template asset is present with its approved bytes"
            ),
        },
        "DirectReleaseRepositoryTest.test_kanji_addon_packages_every_referenced_stroke_image": {
            "protected_contract": (
                "the final addon contains every stroke-order SVG referenced by both kanji card families"
            ),
            "not_subsumed_by": (
                "the skeleton media count can pass while an exported addon drops a referenced image and shows Anki's missing-image warning"
            ),
        },
        "DirectReleaseRepositoryTest.test_builder_hotfix_reuses_exact_core_bytes": {
            "protected_contract": (
                "a builder-only hotfix preserves the already published core APKG bytes while producing a newly bound release receipt"
            ),
            "not_subsumed_by": (
                "logical core counts can pass after a nondeterministic re-export changes the published core artifact bytes"
            ),
        },
        "DirectReleaseRepositoryTest.test_release_pin_matches_current_logical_counts": {
            "protected_contract": (
                "a self-bound public pin keeps stable deck counts while allowing the exact media inventory to change with a new release"
            ),
            "not_subsumed_by": (
                "artifact filename and builder tests do not detect a verifier that freezes the previous release's media count"
            ),
        },
        "DirectReleaseRepositoryTest.test_v130_private_kanji_families_leave_core_vocabulary_only": {
            "protected_contract": (
                "a private vocabulary plus reading and writing package produces a vocabulary-only public core and a two-family personal addon"
            ),
            "not_subsumed_by": (
                "builder archive and cache tests do not inspect the learner-visible note and card families in either output"
            ),
        },
    }
}


class _SyntheticDeck:
    def __init__(self, deck_id: int, name: str) -> None:
        self.id = deck_id
        self.name = name

    def __getitem__(self, key: str) -> int:
        if key != "id":
            raise KeyError(key)
        return self.id


class _SyntheticDecks:
    def __init__(self, names: tuple[str, ...]) -> None:
        self._decks = [
            _SyntheticDeck(index, name)
            for index, name in enumerate(names, start=1)
        ]

    def all_names_and_ids(self) -> tuple[_SyntheticDeck, ...]:
        return tuple(self._decks)

    def by_name(self, name: str) -> _SyntheticDeck | None:
        return next((deck for deck in self._decks if deck.name == name), None)

    def remove(self, deck_ids: list[int]) -> None:
        self._decks = [deck for deck in self._decks if deck.id not in deck_ids]

    def rename(self, deck_id: int, new_name: str) -> None:
        source = next(deck for deck in self._decks if deck.id == deck_id).name
        for deck in self._decks:
            if deck.name == source or deck.name.startswith(f"{source}::"):
                suffix = deck.name[len(source) :]
                deck.name = f"{new_name}{suffix}"


class _SyntheticModels:
    def __init__(self, names: tuple[str, ...]) -> None:
        self._models = {
            name: {"id": index, "name": name}
            for index, name in enumerate(names, start=1)
        }

    def by_name(self, name: str) -> dict[str, Any] | None:
        return self._models.get(name)

    def remove(self, model_id: int) -> None:
        self._models = {
            name: model
            for name, model in self._models.items()
            if model["id"] != model_id
        }

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._models))


class _SyntheticPrivateCollection:
    def __init__(
        self,
        *,
        notes_per_kanji_model: int,
        include_legacy_kanji_root: bool = True,
    ) -> None:
        names = (
            KANJI_NOTETYPE_NAME,
            PRIVATE_KANJI_NOTETYPE_NAMES[1],
            "JLPT MAX덱 어휘",
        )
        self.models = _SyntheticModels(names)
        deck_names = [
            "JLPT MAX덱",
            "JLPT MAX덱::한자",
            "JLPT MAX덱::한자::읽기",
            "JLPT MAX덱::한자::쓰기",
            "JLPT MAX덱::종합 실전::어휘::N1::한자 읽기",
            "JLPT MAX덱::어휘::N5",
        ]
        if include_legacy_kanji_root:
            deck_names.extend(
                (
                    "JLPT MAX덱::일상무따",
                    "JLPT MAX덱::일상무따::legacy",
                )
            )
        self.decks = _SyntheticDecks(tuple(deck_names))
        self.notes: dict[int, int] = {}
        self.note_payloads: dict[int, dict[str, str]] = {}
        next_id = 1
        for model_id in (1, 2):
            for sequence in range(1, notes_per_kanji_model + 1):
                self.notes[next_id] = model_id
                note: dict[str, str] = dict.fromkeys(KANJI_FIELDS, "")
                note.update(
                    {
                        "KanjiID": f"kanji-{sequence}",
                        "Volume": "상권" if sequence == 1 else "하권",
                        "Unit": str(sequence),
                        "KanjiFacts": f"fact-{sequence}",
                        "StrokeOrder": f"stroke-{sequence}",
                        "SortKey": f"K{sequence:06d}",
                    }
                )
                self.note_payloads[next_id] = note
                next_id += 1
        self.vocabulary_note_id = next_id
        self.notes[self.vocabulary_note_id] = 3

    def find_notes(self, query: str) -> list[int]:
        if query == "":
            return sorted(self.notes)
        model_id = int(query.removeprefix("mid:"))
        return sorted(
            note_id for note_id, current_model_id in self.notes.items()
            if current_model_id == model_id
        )

    def remove_notes(self, note_ids: list[int]) -> None:
        for note_id in note_ids:
            self.notes.pop(note_id, None)

    def get_note(self, note_id: int) -> dict[str, str]:
        return self.note_payloads[note_id]

    def card_count(self) -> int:
        return len(self.notes)

    def note_count(self) -> int:
        return len(self.notes)

    def close(self, *, downgrade: bool) -> None:
        del downgrade


def load_repository_verifier() -> Any:
    path = ROOT / "scripts" / "verify-direct-release-tree.py"
    spec = importlib.util.spec_from_file_location(
        "verify_direct_release_tree",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DirectReleaseRepositoryTest(unittest.TestCase):
    def test_current_kanji_fields_close_skeleton_semantics(self) -> None:
        note = dict.fromkeys(KANJI_FIELDS, "")
        note.update(
            {
                "KanjiID": "kanji-1",
                "Volume": "상권",
                "Unit": "1",
                "Meaning": "private meaning",
                "KanjiFacts": "public-safe fact projection",
                "StrokeOrder": "deterministic stroke projection",
                "SortKey": "K000001",
            }
        )
        collection = Mock()
        collection.get_note.return_value = note
        with patch.object(subject, "EXPECTED_KANJI_NOTES", 1), patch.object(
            subject, "EXPECTED_KANJI_VECTOR_GLYPHS", 1
        ):
            records = subject._kanji_skeleton_records(collection, [1])

        expected_projection = dict(note)
        expected_projection["Meaning"] = ""
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["note_hash"], sha256_json(expected_projection))
        self.assertEqual(note["Meaning"], "private meaning")

    def test_v130_private_kanji_families_leave_core_vocabulary_only(self) -> None:
        with patch.object(subject, "EXPECTED_KANJI_NOTES", 2), patch.object(
            builder_subject, "EXPECTED_KANJI_NOTES", 2
        ), patch.object(builder_subject, "EXPECTED_KANJI_ADDON_NOTES", 4), patch.object(
            builder_subject, "EXPECTED_KANJI_ADDON_CARDS", 4
        ):
            full = _SyntheticPrivateCollection(notes_per_kanji_model=2)
            reading_ids, private_ids = _private_kanji_note_ids(full)  # type: ignore[arg-type]

            self.assertEqual(len(reading_ids), 2)
            self.assertEqual(len(private_ids), 4)
            with tempfile.TemporaryDirectory() as raw_tmp:
                output = Path(raw_tmp) / "core.apkg"

                def export_core(
                    collection: _SyntheticPrivateCollection,
                    target: Path,
                ) -> int:
                    target.write_bytes(b"synthetic vocabulary-only core")
                    return collection.card_count()

                def snapshot_core(_target: Path) -> dict[str, Any]:
                    self.assertEqual(
                        full.notes,
                        {full.vocabulary_note_id: 3},
                    )
                    self.assertEqual(full.models.names(), ("JLPT MAX덱 어휘",))
                    deck_names = {
                        deck.name for deck in full.decks.all_names_and_ids()
                    }
                    self.assertNotIn("JLPT MAX덱::한자", deck_names)
                    self.assertNotIn("JLPT MAX덱::한자::읽기", deck_names)
                    self.assertNotIn("JLPT MAX덱::한자::쓰기", deck_names)
                    self.assertNotIn("JLPT MAX덱::일상무따", deck_names)
                    self.assertIn(
                        "JLPT MAX덱::종합 실전::어휘::N1::한자 읽기",
                        deck_names,
                    )
                    return {
                        "cards": 1,
                        "custom_notetype_note_counts": {
                            "JLPT MAX덱 어휘": 1,
                        },
                        "deck_names": sorted(deck_names),
                        "media_files": 0,
                        "media_hash": "0" * 64,
                        "notes": 1,
                    }

                with patch.object(
                    subject,
                    "_import_package",
                    return_value=full,
                ), patch.object(
                    subject,
                    "_kanji_skeleton_records",
                    return_value=[],
                ), patch.object(
                    subject,
                    "_export_root",
                    side_effect=export_core,
                ), patch.object(
                    subject,
                    "_package_snapshot",
                    side_effect=snapshot_core,
                ), patch.object(subject, "_package_media", return_value={}):
                    full_snapshot, core_snapshot, records = subject._build_core(
                        Path("synthetic-full.apkg"), output
                    )

            self.assertEqual(full_snapshot, {"cards": 5, "notes": 5})
            self.assertEqual(core_snapshot["notes"], 1)
            self.assertEqual(core_snapshot["cards"], 1)
            self.assertEqual(records, [])

            skeleton = _SyntheticPrivateCollection(
                notes_per_kanji_model=2,
                include_legacy_kanji_root=False,
            )
            families = _kanji_note_families(skeleton)  # type: ignore[arg-type]
            self.assertEqual(
                tuple(families),
                PRIVATE_KANJI_NOTETYPE_NAMES,
            )
            self.assertEqual(
                sum(len(notes) for notes in families.values()),
                2 * len(PRIVATE_KANJI_NOTETYPE_NAMES),
            )
            _canonicalize_kanji_root(skeleton)  # type: ignore[arg-type]
            skeleton_deck_names = {
                deck.name for deck in skeleton.decks.all_names_and_ids()
            }
            self.assertIn(KANJI_DECK_ROOT, skeleton_deck_names)
            self.assertIn(
                f"{KANJI_DECK_ROOT}::읽기",
                skeleton_deck_names,
            )
            self.assertNotIn("JLPT MAX덱::한자", skeleton_deck_names)

            addon = _SyntheticPrivateCollection(
                notes_per_kanji_model=2,
                include_legacy_kanji_root=False,
            )
            addon.remove_notes([addon.vocabulary_note_id])
            for note_id in addon.notes:
                addon.note_payloads[note_id]["Meaning"] = "합성 뜻"
            _canonicalize_kanji_root(addon)  # type: ignore[arg-type]
            addon.decks.remove(
                [
                    deck.id
                    for deck in addon.decks.all_names_and_ids()
                    if deck.name != KANJI_DECK_ROOT
                    and not deck.name.startswith(f"{KANJI_DECK_ROOT}::")
                ]
            )
            with tempfile.TemporaryDirectory() as raw_tmp:
                package = Path(raw_tmp) / "synthetic-addon.apkg"
                package.write_bytes(b"synthetic addon")
                with patch.object(
                    builder_subject, "_import_package", return_value=addon
                ), patch.object(
                    builder_subject,
                    "_package_media",
                    return_value=KANJI_REQUIRED_STATIC_MEDIA,
                ):
                    verification = builder_subject._verify_addon(
                        package,
                        KANJI_REQUIRED_STATIC_MEDIA,
                    )
            self.assertEqual(
                verification,
                {"cards": 4, "media_files": 1, "notes": 4},
            )

    def test_kanji_addon_requires_template_attribution_media(self) -> None:
        with tempfile.TemporaryDirectory() as raw_media:
            media_root = Path(raw_media)
            required_name = next(iter(KANJI_REQUIRED_STATIC_MEDIA))
            required_path = media_root / required_name
            required_path.write_bytes(b"exact attribution fixture")
            extra_path = media_root / "unused-media.bin"
            extra_path.write_bytes(b"unused")
            required_media = {
                required_name: hashlib.sha256(required_path.read_bytes()).hexdigest()
            }
            collection = Mock()
            collection.media.dir.return_value = str(media_root)
            subject._clear_collection_media(collection, keep=required_media)
            self.assertTrue(required_path.is_file())
            self.assertFalse(extra_path.exists())

        addon = _SyntheticPrivateCollection(
            notes_per_kanji_model=1,
            include_legacy_kanji_root=False,
        )
        addon.remove_notes([addon.vocabulary_note_id])
        for note_id in addon.notes:
            addon.note_payloads[note_id]["Meaning"] = "합성 뜻"
        _canonicalize_kanji_root(addon)  # type: ignore[arg-type]
        addon.decks.remove(
            [
                deck.id
                for deck in addon.decks.all_names_and_ids()
                if deck.name != KANJI_DECK_ROOT
                and not deck.name.startswith(f"{KANJI_DECK_ROOT}::")
            ]
        )
        with tempfile.TemporaryDirectory() as raw_tmp:
            package = Path(raw_tmp) / "synthetic-addon.apkg"
            package.write_bytes(b"synthetic addon")
            expected_media = dict(KANJI_REQUIRED_STATIC_MEDIA)
            with patch.object(
                builder_subject, "EXPECTED_KANJI_NOTES", 1
            ), patch.object(
                builder_subject, "EXPECTED_KANJI_ADDON_NOTES", 2
            ), patch.object(
                builder_subject, "EXPECTED_KANJI_ADDON_CARDS", 2
            ), patch.object(
                builder_subject, "_import_package", return_value=addon
            ), patch.object(
                builder_subject, "_package_media", return_value=expected_media
            ):
                self.assertEqual(
                    builder_subject._verify_addon(package, expected_media),
                    {"cards": 2, "media_files": 1, "notes": 2},
                )

            with patch.object(
                builder_subject, "EXPECTED_KANJI_NOTES", 1
            ), patch.object(
                builder_subject, "EXPECTED_KANJI_ADDON_NOTES", 2
            ), patch.object(
                builder_subject, "EXPECTED_KANJI_ADDON_CARDS", 2
            ), patch.object(
                builder_subject, "_import_package", return_value=addon
            ), patch.object(
                builder_subject, "_package_media", return_value={}
            ):
                with self.assertRaisesRegex(
                    builder_subject.KanjiAddonBuildError,
                    "required attribution media changed",
                ):
                    builder_subject._verify_addon(package, {})

    def test_kanji_addon_packages_every_referenced_stroke_image(self) -> None:
        stroke_filename = "jlpt-v2-stroke-0123456789abcdef01234567.svg"
        addon = _SyntheticPrivateCollection(
            notes_per_kanji_model=1,
            include_legacy_kanji_root=False,
        )
        addon.remove_notes([addon.vocabulary_note_id])
        for note_id in addon.notes:
            addon.note_payloads[note_id]["Meaning"] = "합성 뜻"
            addon.note_payloads[note_id]["StrokeOrder"] = (
                f'<img src="{stroke_filename}">'
            )
        _canonicalize_kanji_root(addon)  # type: ignore[arg-type]
        addon.decks.remove(
            [
                deck.id
                for deck in addon.decks.all_names_and_ids()
                if deck.name != KANJI_DECK_ROOT
                and not deck.name.startswith(f"{KANJI_DECK_ROOT}::")
            ]
        )
        complete_media = {
            **KANJI_REQUIRED_STATIC_MEDIA,
            stroke_filename: "1" * 64,
        }
        with tempfile.TemporaryDirectory() as raw_tmp:
            package = Path(raw_tmp) / "synthetic-addon.apkg"
            package.write_bytes(b"synthetic addon")
            common_patches = (
                patch.object(builder_subject, "EXPECTED_KANJI_NOTES", 1),
                patch.object(builder_subject, "EXPECTED_KANJI_ADDON_NOTES", 2),
                patch.object(builder_subject, "EXPECTED_KANJI_ADDON_CARDS", 2),
                patch.object(builder_subject, "_import_package", return_value=addon),
            )
            with common_patches[0], common_patches[1], common_patches[2], common_patches[3], patch.object(
                builder_subject,
                "_package_media",
                return_value=complete_media,
            ):
                self.assertEqual(
                    builder_subject._verify_addon(package, complete_media),
                    {"cards": 2, "media_files": 2, "notes": 2},
                )
            with common_patches[0], common_patches[1], common_patches[2], common_patches[3], patch.object(
                builder_subject,
                "_package_media",
                return_value=KANJI_REQUIRED_STATIC_MEDIA,
            ):
                with self.assertRaisesRegex(
                    builder_subject.KanjiAddonBuildError,
                    "stroke media is incomplete",
                ):
                    builder_subject._verify_addon(
                        package,
                        KANJI_REQUIRED_STATIC_MEDIA,
                    )

    def test_public_outputs_are_cached_reused_and_safely_replaced_by_fingerprint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            full = tmp / "full.apkg"
            full.write_bytes(b"stable full package")
            cache = tmp / "cache"
            output_one = tmp / "one"
            output_two = tmp / "two"
            build_core = Mock()

            def fake_core(
                _full: Path,
                output: Path,
                *,
                reuse_core_apkg: Path | None = None,
            ) -> tuple[dict[str, int], dict[str, Any], list[dict[str, Any]]]:
                build_core()
                self.assertIsNone(reuse_core_apkg)
                output.write_bytes(b"one nondeterministic build captured once")
                return (
                    {"cards": 2, "notes": 2},
                    {
                        "cards": 1,
                        "custom_notetype_note_counts": {},
                        "deck_names": [],
                        "media_files": 0,
                        "media_hash": "0" * 64,
                        "notes": 1,
                    },
                    [],
                )

            def fake_skeleton(
                _full: Path, output: Path, *, product_version: str
            ) -> dict[str, Any]:
                output.write_bytes(b"skeleton")
                return {"product_version": product_version}

            def fake_builder(**kwargs: Any) -> dict[str, str]:
                Path(kwargs["output"]).write_bytes(b"builder")
                return {"source": "1" * 64}

            with patch("public_release._build_core", side_effect=fake_core), patch(
                "public_release._build_skeleton", side_effect=fake_skeleton
            ), patch(
                "public_release._package_kanji_builder", side_effect=fake_builder
            ):
                first = prepare_direct_release(
                    full_apkg=full,
                    output_root=output_one,
                    product_version="1.2.0",
                    artifact_cache_root=cache,
                )
                second = prepare_direct_release(
                    full_apkg=full,
                    output_root=output_two,
                    product_version="1.2.0",
                    artifact_cache_root=cache,
                )

                self.assertEqual(first["builds_run"], 1)
                self.assertEqual(second["builds_run"], 0)
                self.assertTrue(second["reused"])
                self.assertEqual(build_core.call_count, 1)
                self.assertEqual(
                    {
                        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in output_one.iterdir()
                    },
                    {
                        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in output_two.iterdir()
                    },
                )

                changed_full = tmp / "changed-full.apkg"
                changed_full.write_bytes(b"new accepted full package")
                replaced = prepare_direct_release(
                    full_apkg=changed_full,
                    output_root=output_two,
                    product_version="1.2.0",
                    artifact_cache_root=cache,
                )
                self.assertEqual(replaced["builds_run"], 1)
                self.assertEqual(
                    replaced["replaced_artifact_cache_key"],
                    first["artifact_cache_key"],
                )
                self.assertEqual(build_core.call_count, 2)

                restored = tmp / "restored-first"
                restored_first = prepare_direct_release(
                    full_apkg=full,
                    output_root=restored,
                    product_version="1.2.0",
                    artifact_cache_root=cache,
                )
                self.assertEqual(restored_first["builds_run"], 0)
                self.assertEqual(
                    {
                        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in output_one.iterdir()
                    },
                    {
                        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in restored.iterdir()
                    },
                )

                (output_one / release_filenames("1.2.0")["core_apkg"]).write_bytes(
                    b"tampered"
                )
                with self.assertRaisesRegex(
                    PublicReleaseError, "cached public release artifact changed"
                ):
                    prepare_direct_release(
                        full_apkg=full,
                        output_root=output_one,
                        product_version="1.2.0",
                        artifact_cache_root=cache,
                    )
                self.assertEqual(build_core.call_count, 2)

    def test_builder_hotfix_reuses_exact_core_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            full = tmp / "full.apkg"
            full.write_bytes(b"accepted full source")
            names = release_filenames("1.3.0")
            reusable_core = tmp / names["core_apkg"]
            reusable_core.write_bytes(b"exact published core bytes")
            output = tmp / "output"

            def fake_core(
                _full: Path,
                target: Path,
                *,
                reuse_core_apkg: Path | None = None,
            ) -> tuple[dict[str, int], dict[str, Any], list[dict[str, Any]]]:
                self.assertEqual(reuse_core_apkg, reusable_core.resolve())
                target.write_bytes(reusable_core.read_bytes())
                return (
                    {"cards": 2, "notes": 2},
                    {
                        "cards": 1,
                        "custom_notetype_note_counts": {},
                        "deck_names": [],
                        "media_files": 0,
                        "media_hash": "0" * 64,
                        "notes": 1,
                    },
                    [],
                )

            def fake_skeleton(
                _full: Path, target: Path, *, product_version: str
            ) -> dict[str, Any]:
                target.write_bytes(b"skeleton")
                return {"product_version": product_version}

            def fake_builder(**kwargs: Any) -> dict[str, str]:
                Path(kwargs["output"]).write_bytes(b"corrected builder")
                return {"source": "1" * 64}

            with patch("public_release._build_core", side_effect=fake_core), patch(
                "public_release._build_skeleton", side_effect=fake_skeleton
            ), patch(
                "public_release._package_kanji_builder", side_effect=fake_builder
            ):
                result = prepare_direct_release(
                    full_apkg=full,
                    output_root=output,
                    product_version="1.3.0",
                    reuse_core_apkg=reusable_core,
                    artifact_cache_root=tmp / "cache",
                )

            self.assertEqual(
                (output / names["core_apkg"]).read_bytes(),
                reusable_core.read_bytes(),
            )
            self.assertTrue(result["core"]["reused"])
            self.assertEqual(
                result["artifacts"][names["core_apkg"]]["sha256"],
                sha256_file(reusable_core),
            )

    def test_cli_writes_machine_result_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            result_path = tmp / "result.json"
            with patch.object(
                subject,
                "prepare_direct_release",
                return_value={"status": "passed", "builds_run": 0},
            ), patch.object(
                sys,
                "argv",
                [
                    "public_release.py",
                    "--full-apkg",
                    str(tmp / "full.apkg"),
                    "--output-root",
                    str(tmp / "output"),
                    "--product-version",
                    "1.2.0",
                    "--result-json",
                    str(result_path),
                ],
            ):
                subject.main()

            self.assertEqual(
                json.loads(result_path.read_text(encoding="utf-8")),
                {"status": "passed", "builds_run": 0},
            )

    def test_current_kanji_builder_is_reused_only_for_exact_note_projection(
        self,
    ) -> None:
        pin = json.loads(
            (ROOT / "config/public-release.json").read_text(encoding="utf-8")
        )
        version = str(pin["product_version"])
        names = release_filenames(version)
        records = [
            {
                "guid": f"synthetic-kanji-{sequence:04d}",
                "note_hash": f"{sequence:064x}",
                "sequence": sequence,
                "sort_key": f"K{sequence:06d}",
                "unit": str(((sequence - 1) // 100) + 1),
                "vector_glyph": sequence <= EXPECTED_KANJI_VECTOR_GLYPHS,
                "volume": "상권" if sequence <= 1_200 else "하권",
            }
            for sequence in range(1, EXPECTED_KANJI_NOTES + 1)
        ]
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            skeleton_payload = b"synthetic kanji skeleton"
            skeleton = tmp / names["kanji_skeleton"]
            skeleton.write_bytes(skeleton_payload)
            manifest = tmp / names["skeleton_manifest"]
            manifest.write_text(
                json.dumps(
                    {
                        "kanji_note_count": EXPECTED_KANJI_NOTES,
                        "notes": records,
                        "policy_version": POLICY_VERSION,
                        "product_version": version,
                        "schema_version": SCHEMA_VERSION,
                        "skeleton_apkg": names["kanji_skeleton"],
                        "skeleton_apkg_sha256": hashlib.sha256(
                            skeleton_payload
                        ).hexdigest(),
                        "static_media_count": EXPECTED_KANJI_STATIC_MEDIA,
                        "static_media_sha256": "1" * 64,
                        "vector_glyph_count": EXPECTED_KANJI_VECTOR_GLYPHS,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            builder = tmp / names["kanji_builder"]
            _package_kanji_builder(
                output=builder,
                skeleton_apkg=skeleton,
                skeleton_manifest=manifest,
            )
            copied = tmp / "copied"
            copied.mkdir()
            output = copied / names["kanji_builder"]
            _reuse_kanji_builder(
                source=builder,
                output=output,
                product_version=version,
                current_records=records,
            )
            self.assertEqual(sha256_file(output), sha256_file(builder))
            changed = [dict(record) for record in records]
            changed[0]["note_hash"] = "0" * 64
            with self.assertRaisesRegex(PublicReleaseError, "kanji notes changed"):
                _reuse_kanji_builder(
                    source=builder,
                    output=output,
                    product_version=version,
                    current_records=changed,
                )

    def test_release_zip_preserves_shell_launcher_execute_bit(self) -> None:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            _zip_write(
                archive,
                "JLPT-MAX-kanji-builder/scripts/build-kanji-addon.sh",
                b"#!/usr/bin/env bash\n",
                mode=0o755,
            )
        with zipfile.ZipFile(payload) as archive:
            info = archive.getinfo(
                "JLPT-MAX-kanji-builder/scripts/build-kanji-addon.sh"
            )
        self.assertEqual((info.external_attr >> 16) & 0o777, 0o755)

    def test_packaged_builder_exposes_only_beginner_entries_at_top_level(
        self,
    ) -> None:
        names = release_filenames("1.0.1")
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            skeleton = tmp / names["kanji_skeleton"]
            manifest = tmp / names["skeleton_manifest"]
            output = tmp / names["kanji_builder"]
            skeleton.write_bytes(b"internal builder asset")
            manifest.write_text("{}\n", encoding="utf-8")

            _package_kanji_builder(
                output=output,
                skeleton_apkg=skeleton,
                skeleton_manifest=manifest,
            )

            archive_root = "JLPT-MAX-kanji-builder"
            with zipfile.ZipFile(output) as archive:
                members = set(archive.namelist())
                windows_entry = archive.getinfo(
                    f"{archive_root}/Windows에서 한자 확장 만들기.cmd"
                )
                windows_launcher = archive.read(
                    f"{archive_root}/Windows에서 한자 확장 만들기.cmd"
                )
                mac_entry = archive.getinfo(
                    f"{archive_root}/Mac에서 한자 확장 만들기.command"
                )
                windows_helper = archive.read(
                    f"{archive_root}/scripts/start-kanji-addon.ps1"
                )

        self.assertIn(
            f"{archive_root}/assets/{names['kanji_skeleton']}",
            members,
        )
        self.assertNotIn(
            f"{archive_root}/assets/"
            "JLPT-MAX-kanji-skeleton-1.0.1.apkg",
            members,
        )
        self.assertIn(f"{archive_root}/assets/README.txt", members)
        self.assertEqual((windows_entry.external_attr >> 16) & 0o777, 0o644)
        self.assertEqual((mac_entry.external_attr >> 16) & 0o777, 0o755)
        self.assertTrue(windows_launcher.startswith(b"@echo off\r\n"))
        self.assertNotIn(b"\n", windows_launcher.replace(b"\r\n", b""))
        windows_launcher.decode("ascii")
        self.assertTrue(windows_helper.startswith(b"\xef\xbb\xbf#requires"))

    def test_release_pin_is_self_bound(self) -> None:
        pin = json.loads(
            (ROOT / "config" / "public-release.json").read_text(encoding="utf-8")
        )
        payload = {key: value for key, value in pin.items() if key != "payload_hash"}
        self.assertEqual(pin["payload_hash"], sha256_json(payload))

    def test_release_pin_matches_current_logical_counts(self) -> None:
        pin = json.loads(
            (ROOT / "config" / "public-release.json").read_text(encoding="utf-8")
        )
        verifier = load_repository_verifier()

        verifier._verify_pin(pin)
        changed_media = json.loads(json.dumps(pin))
        changed_media["core"]["media_files"] -= 1
        changed_payload = {
            key: value
            for key, value in changed_media.items()
            if key != "payload_hash"
        }
        changed_media["payload_hash"] = sha256_json(changed_payload)
        verifier._verify_pin(changed_media)

    def test_runtime_is_only_the_optional_kanji_builder(self) -> None:
        self.assertEqual(
            KANJI_BUILDER_FILES,
            (
                "LICENSE",
                "NOTICE",
                "docs/kanji-builder-assets.txt",
                "docs/kanji-builder.md",
                "pyproject.toml",
                "scripts/build-kanji-addon.ps1",
                "scripts/build-kanji-addon.sh",
                "scripts/start-kanji-addon.cmd",
                "scripts/start-kanji-addon.command",
                "scripts/start-kanji-addon.ps1",
                "scripts/start-kanji-addon.sh",
                "src/build_kanji_addon.py",
                "src/direct_release_contract.py",
                "src/public_kanji.py",
                "uv.lock",
            ),
        )
        self.assertFalse((ROOT / "config" / "public-runtime-files.txt").exists())
        self.assertFalse((ROOT / "src" / "artifact_hashing.py").exists())

    def test_beginner_launchers_avoid_manual_terminal_setup(self) -> None:
        windows_entry_bytes = (
            ROOT / "scripts" / "start-kanji-addon.cmd"
        ).read_bytes()
        self.assertTrue(windows_entry_bytes.startswith(b"@echo off\r\n"))
        self.assertNotIn(b"\n", windows_entry_bytes.replace(b"\r\n", b""))
        windows_entry = windows_entry_bytes.decode("ascii")
        windows_flow = (ROOT / "scripts" / "start-kanji-addon.ps1").read_text(
            encoding="utf-8"
        )
        mac_entry = (
            ROOT / "scripts" / "start-kanji-addon.command"
        ).read_text(encoding="utf-8")
        mac_flow = (ROOT / "scripts" / "start-kanji-addon.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("start-kanji-addon.ps1", windows_entry)
        self.assertIn("OpenFileDialog", windows_flow)
        self.assertIn("UV_UNMANAGED_INSTALL", windows_flow)
        self.assertIn("Start-Process", windows_flow)
        self.assertIn("start-kanji-addon.sh", mac_entry)
        self.assertIn("choose file with prompt", mac_flow)
        self.assertIn("UV_UNMANAGED_INSTALL", mac_flow)
        self.assertIn('open "$OUTPUT_ROOT"', mac_flow)
        for source in (windows_flow, mac_flow):
            with self.subTest(source=source[:20]):
                self.assertIn("0.11.32", source)
                self.assertIn("build/kanji-addon", source)
                self.assertIn("kanji-addon-build-report.json", source)
                self.assertIn("읽기·쓰기 카드 4,674개", source)
                self.assertNotIn(
                    "JLPT-MAX-kanji-addon-1.0.1.apkg",
                    source,
                )
        self.assertIn("ConvertFrom-Json", windows_flow)
        self.assertIn('report.get("apkg")', mac_flow)

    def test_builder_assets_warn_against_direct_install(self) -> None:
        warning = (
            ROOT / "docs" / "kanji-builder-assets.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("직접 설치하는 파일이 아닙니다", warning)
        self.assertIn("더블클릭 실행 파일", warning)

    def test_local_builder_runtime_files_cannot_enter_public_source(self) -> None:
        ignored = set(
            (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        )
        verifier = load_repository_verifier()

        self.assertIn("/.tools/", ignored)
        self.assertIn("/kanji-builder.log", ignored)
        for relative in (
            ".tools/uv/uv",
            "kanji-builder.log",
            "nested/kanji-builder.log",
        ):
            with self.subTest(relative=relative):
                with self.assertRaises(RuntimeError):
                    verifier._verify_tracked_boundary((relative,))

    def test_release_pin_binds_current_kanji_builder_sources(self) -> None:
        pin = json.loads(
            (ROOT / "config" / "public-release.json").read_text(encoding="utf-8")
        )
        if tuple(int(part) for part in str(pin["product_version"]).split(".")) < (
            1,
            3,
            0,
        ):
            self.skipTest(
                "the checked-in v1.2.x pin predates the v1.3.0 two-family builder contract"
            )
        source_hashes = {
            kanji_builder_archive_path(relative): sha256_file(ROOT / relative)
            for relative in KANJI_BUILDER_FILES
        }
        self.assertEqual(
            pin["kanji_builder"]["source_hash"],
            sha256_json(dict(sorted(source_hashes.items()))),
        )

    def test_release_draft_matches_current_artifact_pin(self) -> None:
        pin = json.loads(
            (ROOT / "config" / "public-release.json").read_text(encoding="utf-8")
        )
        version = str(pin["product_version"])
        draft = (
            ROOT / "docs" / "release-drafts" / f"v{version}-github-release.md"
        ).read_text(encoding="utf-8")
        for name, artifact in pin["artifacts"].items():
            with self.subTest(name=name):
                self.assertIn(
                    f"`{name}` — {artifact['bytes']:,} bytes — "
                    f"`{artifact['sha256']}`",
                    draft,
                )
        self.assertNotIn("user-attachments/assets", draft)
        self.assertNotIn("/main/site/assets/releases/", draft)
        self.assertIn(
            f"raw.githubusercontent.com/truthyblue/jlpt-max-deck/v{version}/"
            f"site/assets/releases/v{version}/",
            draft,
        )

    def test_repository_has_no_companion_autoplay_addon(self) -> None:
        self.assertFalse((ROOT / "src" / "autoplay_addon.py").exists())
        self.assertFalse((ROOT / "addons" / "jlpt_max_deck_autoplay").exists())
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertNotIn("companion autoplay add-on", notice)
        for relative in (
            "docs-src/README.md.j2",
            "docs-src/site/getting-started.html.j2",
        ):
            content = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn(".ankiaddon", content)

    def test_kanji_builder_removes_anki_work_files(self) -> None:
        source = (ROOT / "src" / "build_kanji_addon.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('(staged / "build.media.db2").unlink', source)
        self.assertNotIn('staged / "collection.media"', source)

    def test_readme_leads_with_direct_basic_deck_download(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        release = json.loads(
            (ROOT / "config" / "public-release.json").read_text(
                encoding="utf-8"
            )
        )
        names = release_filenames(release["product_version"])
        self.assertIn(
            '<img src="site/assets/brand-lockup.svg" '
            'alt="JLPT MAX Deck" width="560">',
            readme,
        )
        self.assertTrue((ROOT / "site" / "assets" / "brand-lockup.svg").is_file())
        self.assertIn(names["core_apkg"], readme)
        self.assertNotIn("JLPT-MAX-core", readme)
        self.assertIn(
            "기본 덱은 완성된 APKG 파일입니다",
            readme,
        )
        self.assertIn("웹 시작 가이드", readme)
        self.assertNotIn("코어 APKG", readme)
        self.assertNotIn("Python이나 출판사 PDF는 필요하지 않습니다", readme)
        self.assertNotIn("저장소를 복제하거나 빌드할 필요가 없습니다", readme)

    def test_learner_support_files_use_current_product_names(self) -> None:
        builder_guide = (ROOT / "docs" / "kanji-builder.md").read_text(
            encoding="utf-8"
        )
        issue_template = (
            ROOT / ".github" / "ISSUE_TEMPLATE" / "bug.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("# 일상무따 한자 확장 만들기", builder_guide)
        self.assertIn("더블클릭", builder_guide)
        self.assertIn("1권 공식 자료", builder_guide)
        self.assertIn("2권 공식 자료", builder_guide)
        self.assertIn("한글이나 띄어쓰기", builder_guide)
        self.assertIn("kanji-builder.log", builder_guide)
        self.assertNotIn("Python 3.13", builder_guide)
        self.assertNotIn("./scripts/build-kanji-addon.sh", builder_guide)
        self.assertIn("기본 덱 다운로드·가져오기", issue_template)
        self.assertIn("한자 확장 ZIP 풀기 또는 실행 파일", issue_template)
        for stale in ("코어 덱", "코어 APKG", "코어 배포"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, builder_guide)
                self.assertNotIn(stale, issue_template)


if __name__ == "__main__":
    unittest.main()
