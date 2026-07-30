# pyright: reportMissingImports=false
"""Prepare direct core-APKG release assets from one verified full public APKG."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from anki.collection import Collection
from anki.exporting import AnkiPackageExporter
from anki.import_export_pb2 import ImportAnkiPackageRequest

from direct_release_contract import (
    EXPECTED_KANJI_NOTES,
    EXPECTED_KANJI_VECTOR_GLYPHS,
    KANJI_BUILDER_FILES,
    KANJI_DECK_ROOT,
    KANJI_FIELDS,
    KANJI_NOTETYPE_NAME,
    POLICY_VERSION,
    ROOT_DECK_NAME,
    SCHEMA_VERSION,
    checksum_lines,
    release_filenames,
    sha256_file,
    sha256_json,
    skeleton_note_record,
    validate_skeleton_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
BUILDER_ARCHIVE_ROOT = "JLPT-MAX-kanji-builder"
_VECTOR_GLYPH_RE = re.compile(
    r'<img class="kanji-glyph-image" src="([^"]+)"[^>]*>'
)


class PublicReleaseError(RuntimeError):
    """Raised when a direct-release candidate cannot be closed safely."""


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ensure_empty_or_absent(path: Path) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise PublicReleaseError(f"output root must be absent or empty: {path}")


def _import_package(path: Path, collection_path: Path) -> Collection:
    if not path.is_file():
        raise PublicReleaseError(f"APKG is missing: {path}")
    collection = Collection(str(collection_path))
    try:
        options = collection._backend.get_import_anki_package_presets()
        options.merge_notetypes = True
        options.with_scheduling = False
        options.with_deck_configs = True
        collection.import_anki_package(
            ImportAnkiPackageRequest(package_path=str(path), options=options)
        )
    except BaseException:
        collection.close(downgrade=False)
        raise
    return collection


def _notetype(collection: Collection, name: str) -> dict[str, Any]:
    model = collection.models.by_name(name)
    if model is None:
        raise PublicReleaseError(f"notetype is missing: {name}")
    return model


def _note_ids_for_notetype(collection: Collection, name: str) -> list[int]:
    model = _notetype(collection, name)
    return [int(value) for value in collection.find_notes(f"mid:{int(model['id'])}")]


def _export_root(collection: Collection, output: Path) -> int:
    deck = collection.decks.by_name(ROOT_DECK_NAME)
    if deck is None:
        raise PublicReleaseError(f"root deck is missing: {ROOT_DECK_NAME}")
    exporter = AnkiPackageExporter(collection)
    exporter.did = int(deck["id"])
    exporter.includeSched = True
    exporter.includeMedia = True
    exporter.exportInto(str(output))
    return int(exporter.count)


def _remove_decks(collection: Collection, names: Iterable[str]) -> None:
    remove_ids = [
        int(deck.id)
        for deck in collection.decks.all_names_and_ids()
        if deck.name in set(names)
    ]
    if remove_ids:
        collection.decks.remove(remove_ids)


def _remove_matching_decks(collection: Collection, *, keep_kanji: bool) -> None:
    names = [deck.name for deck in collection.decks.all_names_and_ids()]
    if keep_kanji:
        remove = [
            name
            for name in names
            if name != ROOT_DECK_NAME
            and name != KANJI_DECK_ROOT
            and not name.startswith(f"{KANJI_DECK_ROOT}::")
        ]
    else:
        remove = [
            name
            for name in names
            if name == KANJI_DECK_ROOT or name.startswith(f"{KANJI_DECK_ROOT}::")
        ]
    _remove_decks(collection, sorted(remove, key=lambda value: value.count("::"), reverse=True))


def _clear_collection_media(collection: Collection) -> None:
    media_root = Path(collection.media.dir())
    for path in media_root.iterdir():
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            raise PublicReleaseError(f"unexpected directory in Anki media: {path.name}")


def _package_media(path: Path) -> dict[str, str]:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise PublicReleaseError(f"cannot read APKG media: {path}: {exc}") from exc
    with archive:
        try:
            mapping = json.loads(archive.read("media"))
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PublicReleaseError(f"APKG media map is invalid: {path}") from exc
        if not isinstance(mapping, dict):
            raise PublicReleaseError(f"APKG media map is not an object: {path}")
        hashes: dict[str, str] = {}
        for member, raw_name in mapping.items():
            if not isinstance(raw_name, str) or Path(raw_name).name != raw_name:
                raise PublicReleaseError(f"unsafe APKG media filename: {raw_name!r}")
            payload = archive.read(str(member))
            digest = hashlib.sha256(payload).hexdigest()
            if raw_name in hashes:
                raise PublicReleaseError(f"duplicate APKG media filename: {raw_name}")
            hashes[raw_name] = digest
        return hashes


def _package_snapshot(path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="jlpt-release-verify-") as directory:
        collection = _import_package(path, Path(directory) / "verify.anki2")
        try:
            custom_models = {
                str(model["name"]): len(
                    collection.find_notes(f"mid:{int(model['id'])}")
                )
                for model in collection.models.all()
                if str(model["name"]).startswith("JLPT MAX덱")
            }
            deck_names = sorted(
                deck.name
                for deck in collection.decks.all_names_and_ids()
                if deck.name.startswith(ROOT_DECK_NAME)
            )
            snapshot = {
                "cards": collection.card_count(),
                "custom_notetype_note_counts": dict(sorted(custom_models.items())),
                "deck_names": deck_names,
                "notes": collection.note_count(),
            }
        finally:
            collection.close(downgrade=False)
    media = _package_media(path)
    return {
        **snapshot,
        "media_files": len(media),
        "media_hash": sha256_json(
            [{"filename": name, "sha256": digest} for name, digest in sorted(media.items())]
        ),
    }


def _build_core(full_apkg: Path, output: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="jlpt-core-release-") as directory:
        collection = _import_package(full_apkg, Path(directory) / "core.anki2")
        try:
            full_snapshot = {
                "cards": collection.card_count(),
                "notes": collection.note_count(),
            }
            kanji_ids = _note_ids_for_notetype(collection, KANJI_NOTETYPE_NAME)
            if len(kanji_ids) != EXPECTED_KANJI_NOTES:
                raise PublicReleaseError(
                    f"full APKG kanji count changed: {len(kanji_ids)}"
                )
            collection.remove_notes(kanji_ids)
            _remove_matching_decks(collection, keep_kanji=False)
            kanji_model = collection.models.by_name(KANJI_NOTETYPE_NAME)
            if kanji_model is not None:
                collection.models.remove(int(kanji_model["id"]))
            exported = _export_root(collection, output)
            expected_cards = full_snapshot["cards"] - EXPECTED_KANJI_NOTES
            expected_notes = full_snapshot["notes"] - EXPECTED_KANJI_NOTES
            if exported != expected_cards:
                raise PublicReleaseError(
                    f"core export card count changed: {exported} != {expected_cards}"
                )
        finally:
            collection.close(downgrade=False)
    snapshot = _package_snapshot(output)
    if (
        snapshot["notes"] != expected_notes
        or snapshot["cards"] != expected_cards
        or KANJI_NOTETYPE_NAME in snapshot["custom_notetype_note_counts"]
        or any(name.startswith(KANJI_DECK_ROOT) for name in snapshot["deck_names"])
        or any(name.startswith("jlpt-public-kanji-") for name in _package_media(output))
    ):
        raise PublicReleaseError("core APKG still contains the optional kanji deck")
    return full_snapshot, snapshot


def _build_skeleton(
    full_apkg: Path,
    output: Path,
    *,
    product_version: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="jlpt-kanji-skeleton-") as directory:
        collection = _import_package(full_apkg, Path(directory) / "skeleton.anki2")
        try:
            kanji_ids = set(_note_ids_for_notetype(collection, KANJI_NOTETYPE_NAME))
            if len(kanji_ids) != EXPECTED_KANJI_NOTES:
                raise PublicReleaseError(
                    f"full APKG kanji count changed: {len(kanji_ids)}"
                )
            all_ids = {int(value) for value in collection.find_notes("")}
            other_ids = sorted(all_ids - kanji_ids)
            if other_ids:
                collection.remove_notes(other_ids)
            _remove_matching_decks(collection, keep_kanji=True)
            records: list[dict[str, Any]] = []
            for note_id in kanji_ids:
                note = collection.get_note(note_id)
                if tuple(note.keys()) != KANJI_FIELDS:
                    raise PublicReleaseError("kanji notetype fields changed")
                note["Meaning"] = ""
                if _VECTOR_GLYPH_RE.fullmatch(note["GlyphHTML"]):
                    note["GlyphHTML"] = ""
                collection.update_note(note)
                records.append(
                    skeleton_note_record({field: note[field] for field in KANJI_FIELDS})
                )
            records.sort(key=lambda value: int(value["sequence"]))
            if [record["sequence"] for record in records] != list(
                range(1, EXPECTED_KANJI_NOTES + 1)
            ):
                raise PublicReleaseError("kanji skeleton sequence changed")
            if sum(bool(record["vector_glyph"]) for record in records) != (
                EXPECTED_KANJI_VECTOR_GLYPHS
            ):
                raise PublicReleaseError("kanji skeleton vector count changed")
            _clear_collection_media(collection)
            exported = _export_root(collection, output)
            if exported != EXPECTED_KANJI_NOTES:
                raise PublicReleaseError(
                    f"kanji skeleton card count changed: {exported}"
                )
        finally:
            collection.close(downgrade=False)
    snapshot = _package_snapshot(output)
    if (
        snapshot["notes"] != EXPECTED_KANJI_NOTES
        or snapshot["cards"] != EXPECTED_KANJI_NOTES
        or snapshot["custom_notetype_note_counts"] != {
            KANJI_NOTETYPE_NAME: EXPECTED_KANJI_NOTES
        }
        or snapshot["media_files"] != 0
    ):
        raise PublicReleaseError("kanji skeleton package is not closed")
    manifest = {
        "kanji_note_count": EXPECTED_KANJI_NOTES,
        "notes": records,
        "policy_version": POLICY_VERSION,
        "product_version": product_version,
        "schema_version": SCHEMA_VERSION,
        "skeleton_apkg": output.name,
        "skeleton_apkg_sha256": sha256_file(output),
        "vector_glyph_count": EXPECTED_KANJI_VECTOR_GLYPHS,
    }
    validate_skeleton_manifest(manifest)
    return manifest


def _zip_write(
    archive: zipfile.ZipFile,
    name: str,
    payload: bytes,
    *,
    mode: int = 0o644,
) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100000 | mode) << 16
    archive.writestr(info, payload)


def _package_kanji_builder(
    *,
    output: Path,
    skeleton_apkg: Path,
    skeleton_manifest: Path,
) -> dict[str, str]:
    source_hashes: dict[str, str] = {}
    with zipfile.ZipFile(output, "w") as archive:
        for relative in KANJI_BUILDER_FILES:
            source = ROOT / relative
            if not source.is_file() or source.is_symlink():
                raise PublicReleaseError(f"kanji builder source is missing: {relative}")
            target = "README.md" if relative == "docs/kanji-builder.md" else relative
            payload = source.read_bytes()
            _zip_write(
                archive,
                f"{BUILDER_ARCHIVE_ROOT}/{target}",
                payload,
                mode=0o755 if relative == "scripts/build-kanji-addon.sh" else 0o644,
            )
            source_hashes[target] = sha256_file(source)
        for source in (skeleton_apkg, skeleton_manifest):
            _zip_write(
                archive,
                f"{BUILDER_ARCHIVE_ROOT}/assets/{source.name}",
                source.read_bytes(),
            )
    return dict(sorted(source_hashes.items()))


def prepare_direct_release(
    *,
    full_apkg: Path,
    output_root: Path,
    product_version: str,
) -> dict[str, Any]:
    """Create a direct core APKG and a small optional kanji builder bundle."""
    _ensure_empty_or_absent(output_root)
    names = release_filenames(product_version)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.tmp-",
            dir=output_root.parent,
        )
    )
    try:
        core_apkg = staged / names["core_apkg"]
        skeleton_apkg = staged / names["kanji_skeleton"]
        skeleton_manifest_path = staged / names["skeleton_manifest"]
        full_snapshot, core_snapshot = _build_core(full_apkg, core_apkg)
        skeleton_manifest = _build_skeleton(
            full_apkg,
            skeleton_apkg,
            product_version=product_version,
        )
        _write_json(skeleton_manifest_path, skeleton_manifest)
        builder_archive = staged / names["kanji_builder"]
        builder_source_hashes = _package_kanji_builder(
            output=builder_archive,
            skeleton_apkg=skeleton_apkg,
            skeleton_manifest=skeleton_manifest_path,
        )
        skeleton_apkg.unlink()
        skeleton_manifest_path.unlink()

        distributed = [core_apkg, builder_archive]
        checksums = staged / names["checksums"]
        checksums.write_text(checksum_lines(distributed), encoding="utf-8")
        payload = {
            "artifacts": {
                path.name: {
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
                for path in sorted([*distributed, checksums], key=lambda item: item.name)
            },
            "core": {
                "cards": core_snapshot["cards"],
                "custom_notetype_note_counts": core_snapshot[
                    "custom_notetype_note_counts"
                ],
                "deck_names": [
                    ROOT_DECK_NAME,
                    f"{ROOT_DECK_NAME}::어휘",
                    f"{ROOT_DECK_NAME}::음성",
                    f"{ROOT_DECK_NAME}::종합 실전",
                    f"{ROOT_DECK_NAME}::참조표",
                ],
                "media_files": core_snapshot["media_files"],
                "media_hash": core_snapshot["media_hash"],
                "notes": core_snapshot["notes"],
            },
            "full_source": {
                **full_snapshot,
                "sha256": sha256_file(full_apkg),
            },
            "kanji_builder": {
                "expected_kanji_notes": EXPECTED_KANJI_NOTES,
                "expected_pdf_count": 2,
                "expected_vector_glyphs": EXPECTED_KANJI_VECTOR_GLYPHS,
                "output_apkg": names["kanji_addon"],
                "source_hash": sha256_json(builder_source_hashes),
            },
            "policy_version": POLICY_VERSION,
            "product_version": product_version,
            "schema_version": SCHEMA_VERSION,
            "status": "passed",
            "unresolved": 0,
        }
        pin = {**payload, "payload_hash": sha256_json(payload)}
        _write_json(staged / names["release_pin"], pin)
        if output_root.exists():
            output_root.rmdir()
        os.replace(staged, output_root)
        return pin
    finally:
        if staged.exists():
            shutil.rmtree(staged)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-apkg", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--product-version", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = prepare_direct_release(
        full_apkg=args.full_apkg.resolve(),
        output_root=args.output_root.resolve(),
        product_version=args.product_version,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
