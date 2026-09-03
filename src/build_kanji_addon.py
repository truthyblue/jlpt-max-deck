# pyright: reportMissingImports=false
"""Build the optional JLPT MAX kanji addon from its skeleton and two Gilbut PDFs."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import tempfile
import unicodedata
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from anki.collection import Collection
from anki.decks import DeckId
from anki.exporting import AnkiPackageExporter
from anki.import_export_pb2 import ImportAnkiPackageRequest
from anki.notes import NoteId

from direct_release_contract import (
    EXPECTED_KANJI_ADDON_CARDS,
    EXPECTED_KANJI_ADDON_NOTES,
    EXPECTED_KANJI_NOTES,
    EXPECTED_KANJI_STATIC_MEDIA,
    EXPECTED_KANJI_STROKE_MEDIA,
    EXPECTED_KANJI_VECTOR_GLYPHS,
    KANJI_DECK_ROOT,
    KANJI_FIELDS,
    KANJI_NOTETYPE_NAME,
    KANJI_REQUIRED_STATIC_MEDIA,
    KANJI_STROKE_MEDIA_RE,
    KANJI_WRITING_NOTETYPE_NAME,
    PRIVATE_KANJI_NOTETYPE_NAMES,
    POLICY_VERSION,
    ROOT_DECK_NAME,
    SCHEMA_VERSION,
    release_filenames,
    sha256_file,
    sha256_json,
    skeleton_note_record,
    validate_kanji_static_media,
    validate_skeleton_manifest,
)
from public_kanji import (
    GILBUT_GLYPH_EQUIVALENTS,
    GilbutKanjiSlot,
    extract_all_gilbut_kanji_slots,
    gilbut_glyph_media_filename,
    gilbut_vector_glyph_png,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_ROOT = ROOT / "assets"
_TEXT_GLYPH_RE = re.compile(
    r'<span(?: class="[^"]*")? lang="ja">([^<]+)</span>'
)
_ADDITIONAL_SLOT_RE = re.compile(r"추가자\s*([0-9]+)")


class KanjiAddonBuildError(RuntimeError):
    """Raised when the optional kanji addon cannot be reproduced exactly."""


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KanjiAddonBuildError(f"cannot read skeleton manifest: {path}") from exc
    if not isinstance(value, dict):
        raise KanjiAddonBuildError("skeleton manifest is not an object")
    validate_skeleton_manifest(value)
    return value


def _import_package(path: Path, collection_path: Path) -> Collection:
    if not path.is_file():
        raise KanjiAddonBuildError(f"kanji builder asset is missing: {path}")
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


def _kanji_note_families(collection: Collection) -> dict[str, list[Any]]:
    families: dict[str, list[Any]] = {}
    for name in PRIVATE_KANJI_NOTETYPE_NAMES:
        model = collection.models.by_name(name)
        if model is None:
            raise KanjiAddonBuildError(f"kanji skeleton notetype is missing: {name}")
        notes = [
            collection.get_note(NoteId(int(note_id)))
            for note_id in collection.find_notes(f"mid:{int(model['id'])}")
        ]
        notes.sort(key=lambda note: note["SortKey"])
        if len(notes) != EXPECTED_KANJI_NOTES:
            raise KanjiAddonBuildError(
                f"kanji skeleton {name} note count changed: {len(notes)}"
            )
        families[name] = notes
    return families


def _kanji_notes(collection: Collection) -> list[Any]:
    """Return the reading family used to align the PDF and manifest."""
    return _kanji_note_families(collection)[KANJI_NOTETYPE_NAME]


def _kanji_stroke_references(
    families: Mapping[str, Sequence[Mapping[str, str]]],
) -> set[str]:
    return {
        filename
        for notes in families.values()
        for note in notes
        for filename in KANJI_STROKE_MEDIA_RE.findall(note["StrokeOrder"])
    }


def _export_root(collection: Collection, output: Path) -> int:
    root = collection.decks.by_name(ROOT_DECK_NAME)
    if root is None:
        raise KanjiAddonBuildError("kanji skeleton root deck is missing")
    exporter = AnkiPackageExporter(collection)
    exporter.did = DeckId(int(root["id"]))
    exporter.includeSched = True
    exporter.includeMedia = True
    exporter.exportInto(str(output))
    return int(exporter.count)


def _package_media(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        mapping = json.loads(archive.read("media"))
        if not isinstance(mapping, dict):
            raise KanjiAddonBuildError("kanji addon media map is invalid")
        result: dict[str, str] = {}
        for member, raw_name in mapping.items():
            if not isinstance(raw_name, str) or Path(raw_name).name != raw_name:
                raise KanjiAddonBuildError("kanji addon media filename is unsafe")
            result[raw_name] = hashlib.sha256(archive.read(str(member))).hexdigest()
        return result


def _normalized_glyph(value: str) -> str:
    return unicodedata.normalize("NFKC", re.sub(r"\s+", "", value))


def _glyph_matches(expected: str, actual: str) -> bool:
    expected_key = _normalized_glyph(expected)
    actual_key = _normalized_glyph(actual)
    if expected_key == actual_key:
        return True
    equivalents = GILBUT_GLYPH_EQUIVALENTS.get(expected_key, ())
    reverse = {
        alternate: canonical
        for canonical, alternates in GILBUT_GLYPH_EQUIVALENTS.items()
        for alternate in alternates
    }
    return actual_key in equivalents or reverse.get(expected_key) == actual_key


def _unit_matches(unit: str, label: str) -> bool:
    if unit == label:
        return True
    if unit.isdecimal() and label.isdecimal():
        return int(unit) == int(label)
    match = _ADDITIONAL_SLOT_RE.search(unit)
    return match is not None and f"추가자{match.group(1)}" == label


def _align_pdf_slots(
    notes: Sequence[Mapping[str, str]],
    slots: Sequence[GilbutKanjiSlot],
) -> list[GilbutKanjiSlot]:
    """Match every skeleton note to its unique PDF slot by volume and unit."""
    unused = set(range(len(slots)))
    aligned: list[GilbutKanjiSlot] = []
    for note in notes:
        matches = [
            index
            for index in unused
            if slots[index].volume_code == _volume_code(note["Volume"])
            and _unit_matches(note["Unit"], slots[index].source_label)
        ]
        if len(matches) != 1:
            raise KanjiAddonBuildError(
                "kanji skeleton/PDF unit alignment is not unique: "
                f"{note['SortKey']}:{note['Volume']}:{note['Unit']}"
            )
        matched = matches[0]
        unused.remove(matched)
        aligned.append(slots[matched])
    if unused:
        raise KanjiAddonBuildError(
            f"kanji PDF contains unmatched slots: {len(unused)}"
        )
    return aligned


def _volume_code(volume: str) -> str:
    try:
        return {"상권": "upper", "하권": "lower"}[volume]
    except KeyError as exc:
        raise KanjiAddonBuildError(f"unknown kanji volume: {volume!r}") from exc


def _verify_skeleton(
    notes: list[Any],
    manifest_records: tuple[dict[str, Any], ...],
) -> None:
    if len(notes) != len(manifest_records):
        raise KanjiAddonBuildError("kanji skeleton manifest coverage changed")
    for note, record in zip(notes, manifest_records, strict=True):
        projected = {field: note[field] for field in KANJI_FIELDS}
        observed = skeleton_note_record(projected)
        if observed != record:
            raise KanjiAddonBuildError(
                f"kanji skeleton note changed: {record['sort_key']}"
            )


def _fill_note(
    note: Any,
    slot: GilbutKanjiSlot,
    *,
    source_paths: Mapping[str, Path],
    media_root: Path,
) -> tuple[str, str] | None:
    expected_sort_key = note["SortKey"]
    if (
        _volume_code(note["Volume"]) != slot.volume_code
        or not _unit_matches(note["Unit"], slot.source_label)
        or note["Meaning"]
    ):
        raise KanjiAddonBuildError(
            f"kanji skeleton/PDF alignment changed: {expected_sort_key}"
        )
    if slot.glyph_kind == "text":
        # The manifest already binds the markup; CSS aliases are not glyph identity.
        match = _TEXT_GLYPH_RE.fullmatch(note["GlyphHTML"])
        if match is None or not _glyph_matches(html.unescape(match.group(1)), slot.glyph_text):
            raise KanjiAddonBuildError(
                f"kanji text glyph changed: {expected_sort_key}"
            )
        media_record = None
    else:
        if note["GlyphHTML"]:
            raise KanjiAddonBuildError(
                f"kanji vector skeleton is not empty: {expected_sort_key}"
            )
        source = source_paths.get(slot.source_id)
        if source is None:
            raise KanjiAddonBuildError(
                f"kanji vector source is missing: {slot.source_id}"
            )
        filename = gilbut_glyph_media_filename(slot)
        payload = gilbut_vector_glyph_png(source, slot)
        target = media_root / filename
        target.write_bytes(payload)
        note["GlyphHTML"] = (
            f'<img class="kanji-glyph-image kanji-glyph-transparent" '
            f'src="{filename}" '
            'alt="원본 한자 자형">'
        )
        media_record = filename, hashlib.sha256(payload).hexdigest()
    note["Meaning"] = slot.meaning
    return media_record


def _verify_addon(path: Path, expected_media: Mapping[str, str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="jlpt-kanji-addon-verify-") as directory:
        collection = _import_package(path, Path(directory) / "verify.anki2")
        try:
            families = _kanji_note_families(collection)
            stroke_references = _kanji_stroke_references(families)
            if (
                collection.note_count() != EXPECTED_KANJI_ADDON_NOTES
                or collection.card_count() != EXPECTED_KANJI_ADDON_CARDS
                or any(
                    not note["Meaning"]
                    for family in families.values()
                    for note in family
                )
                or any(
                    deck.name.startswith(ROOT_DECK_NAME)
                    and deck.name != ROOT_DECK_NAME
                    and not deck.name.startswith(KANJI_DECK_ROOT)
                    for deck in collection.decks.all_names_and_ids()
                )
            ):
                raise KanjiAddonBuildError("kanji addon import verification failed")
        finally:
            collection.close(downgrade=False)
    packaged_media = _package_media(path)
    if any(
        packaged_media.get(filename) != digest
        for filename, digest in KANJI_REQUIRED_STATIC_MEDIA.items()
    ):
        raise KanjiAddonBuildError(
            "kanji addon required attribution media changed"
        )
    packaged_strokes = {
        filename
        for filename in packaged_media
        if KANJI_STROKE_MEDIA_RE.fullmatch(filename)
    }
    if stroke_references != packaged_strokes:
        raise KanjiAddonBuildError("kanji addon stroke media is incomplete")
    if packaged_media != dict(expected_media):
        raise KanjiAddonBuildError("kanji addon media changed")
    return {
        "cards": EXPECTED_KANJI_ADDON_CARDS,
        "media_files": len(packaged_media),
        "notes": EXPECTED_KANJI_ADDON_NOTES,
    }


def build_kanji_addon(
    *,
    upper_pdf: Path,
    lower_pdf: Path,
    asset_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    manifest_path = asset_root / "kanji-skeleton-manifest.json"
    manifest = _read_manifest(manifest_path)
    product_version = str(manifest["product_version"])
    names = release_filenames(product_version)
    skeleton = asset_root / str(manifest["skeleton_apkg"])
    if sha256_file(skeleton) != manifest["skeleton_apkg_sha256"]:
        raise KanjiAddonBuildError("kanji builder asset hash changed")
    skeleton_media = _package_media(skeleton)
    try:
        validate_kanji_static_media(
            skeleton_media,
            expected_sha256=str(manifest["static_media_sha256"]),
        )
    except ValueError as exc:
        raise KanjiAddonBuildError(str(exc)) from exc
    if output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir())):
        raise KanjiAddonBuildError(
            f"output root must be absent or empty: {output_root}"
        )
    slots = extract_all_gilbut_kanji_slots(
        upper_pdf=upper_pdf,
        lower_pdf=lower_pdf,
    )
    manifest_records = validate_skeleton_manifest(manifest)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.tmp-", dir=output_root.parent)
    )
    collection: Collection | None = None
    try:
        collection = _import_package(skeleton, staged / "build.anki2")
        assert collection is not None
        families = _kanji_note_families(collection)
        notes = families[KANJI_NOTETYPE_NAME]
        _verify_skeleton(notes, manifest_records)
        _verify_skeleton(families[KANJI_WRITING_NOTETYPE_NAME], manifest_records)
        aligned_slots = _align_pdf_slots(notes, slots)
        media_root = Path(collection.media.dir())
        source_paths = {
            "ilsang-muutta-upper": upper_pdf,
            "ilsang-muutta-lower": lower_pdf,
        }
        expected_media = dict(skeleton_media)
        writing_by_sort_key = {
            note["SortKey"]: note
            for note in families[KANJI_WRITING_NOTETYPE_NAME]
        }
        for note, slot in zip(notes, aligned_slots, strict=True):
            writing_note = writing_by_sort_key.get(note["SortKey"])
            if writing_note is None:
                raise KanjiAddonBuildError(
                    f"kanji writing family is missing: {note['SortKey']}"
                )
            for family_note in (note, writing_note):
                record = _fill_note(
                    family_note,
                    slot,
                    source_paths=source_paths,
                    media_root=media_root,
                )
                collection.update_note(family_note)
                if record is not None:
                    filename, digest = record
                    expected_media[filename] = digest
        if len(expected_media) != (
            EXPECTED_KANJI_VECTOR_GLYPHS + EXPECTED_KANJI_STATIC_MEDIA
        ):
            raise KanjiAddonBuildError("kanji vector glyph count changed")
        if len(_kanji_stroke_references(families)) != EXPECTED_KANJI_STROKE_MEDIA:
            raise KanjiAddonBuildError("kanji stroke media reference count changed")
        package = staged / names["kanji_addon"]
        exported = _export_root(collection, package)
        collection.close(downgrade=False)
        collection = None
        if exported != EXPECTED_KANJI_ADDON_CARDS:
            raise KanjiAddonBuildError(f"kanji addon card count changed: {exported}")
        verification = _verify_addon(package, expected_media)
        report_payload = {
            "apkg": package.name,
            "apkg_bytes": package.stat().st_size,
            "apkg_sha256": sha256_file(package),
            "input_pdfs": {
                "lower_sha256": sha256_file(lower_pdf),
                "upper_sha256": sha256_file(upper_pdf),
            },
            "policy_version": POLICY_VERSION,
            "product_version": product_version,
            "schema_version": SCHEMA_VERSION,
            "skeleton_apkg_sha256": sha256_file(skeleton),
            "status": "passed",
            "unresolved": 0,
            "verification": verification,
        }
        report = {**report_payload, "payload_hash": sha256_json(report_payload)}
        _write_json(staged / names["kanji_build_report"], report)
        (staged / "build.anki2").unlink(missing_ok=True)
        if media_root.exists():
            shutil.rmtree(media_root)
        (staged / "build.media.db2").unlink(missing_ok=True)
        if output_root.exists():
            output_root.rmdir()
        os.replace(staged, output_root)
        return report
    finally:
        if collection is not None:
            collection.close(downgrade=False)
        if staged.exists():
            shutil.rmtree(staged)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upper-pdf", type=Path, required=True)
    parser.add_argument("--lower-pdf", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSET_ROOT)
    parser.add_argument("--output-root", type=Path, default=ROOT / "build" / "kanji-addon")
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = build_kanji_addon(
        upper_pdf=args.upper_pdf.resolve(),
        lower_pdf=args.lower_pdf.resolve(),
        asset_root=args.asset_root.resolve(),
        output_root=args.output_root.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
