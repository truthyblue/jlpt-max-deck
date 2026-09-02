# pyright: reportMissingImports=false
"""Prepare direct core-APKG release assets from one verified full public APKG."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from anki.collection import Collection
from anki.exporting import AnkiPackageExporter
from anki.import_export_pb2 import ImportAnkiPackageRequest

from direct_release_contract import (
    EXPECTED_KANJI_ADDON_CARDS,
    EXPECTED_KANJI_ADDON_NOTES,
    EXPECTED_KANJI_NOTES,
    EXPECTED_KANJI_STATIC_MEDIA,
    EXPECTED_KANJI_STROKE_MEDIA,
    EXPECTED_KANJI_VECTOR_GLYPHS,
    KANJI_BUILDER_FILES,
    KANJI_DECK_ROOT,
    KANJI_FIELDS,
    KANJI_NOTETYPE_NAME,
    KANJI_REQUIRED_STATIC_MEDIA,
    KANJI_STROKE_MEDIA_RE,
    KANJI_WRITING_NOTETYPE_NAME,
    PRIVATE_KANJI_DECK_ROOTS,
    PRIVATE_KANJI_NOTETYPE_NAMES,
    POLICY_VERSION,
    ROOT_DECK_NAME,
    SCHEMA_VERSION,
    checksum_lines,
    kanji_builder_archive_path,
    kanji_builder_file_mode,
    release_filenames,
    sha256_file,
    sha256_json,
    skeleton_note_record,
    validate_kanji_static_media,
    validate_skeleton_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
BUILDER_ARCHIVE_ROOT = "JLPT-MAX-kanji-builder"
PUBLIC_RELEASE_CODE_PATHS = (
    "src/direct_release_contract.py",
    "src/public_release.py",
    "src/public_kanji.py",
)
_VECTOR_GLYPH_RE = re.compile(
    r'<img\b[^>]*\bsrc="(jlpt-v2-kanji-[0-9a-f]{24}\.png)"[^>]*>'
)


class PublicReleaseError(RuntimeError):
    """Raised when a direct-release candidate cannot be closed safely."""


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _default_artifact_cache_root() -> Path:
    completed = subprocess.run(
        ("git", "rev-parse", "--path-format=absolute", "--git-common-dir"),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise PublicReleaseError("cannot resolve the shared public release cache")
    return Path(completed.stdout.strip()) / "jlpt-public-release-cache"


def _public_release_input_fingerprint(
    *,
    full_apkg: Path,
    product_version: str,
    reuse_core_apkg: Path | None,
    reuse_kanji_builder: Path | None,
) -> dict[str, Any]:
    names = release_filenames(product_version)
    if not full_apkg.is_file() or full_apkg.is_symlink():
        raise PublicReleaseError(f"APKG is missing or unsafe: {full_apkg}")
    code = {
        relative: sha256_file(ROOT / relative)
        for relative in PUBLIC_RELEASE_CODE_PATHS
    }
    builder_sources = {
        relative: sha256_file(ROOT / relative)
        for relative in KANJI_BUILDER_FILES
    }
    reusable_core: dict[str, Any] | None = None
    if reuse_core_apkg is not None:
        reusable_core_path = reuse_core_apkg.resolve()
        if (
            not reusable_core_path.is_file()
            or reusable_core_path.is_symlink()
            or reusable_core_path.name != names["core_apkg"]
        ):
            raise PublicReleaseError("reusable core APKG identity changed")
        reusable_core = {
            "name": reusable_core_path.name,
            "sha256": sha256_file(reusable_core_path),
        }
    reusable: dict[str, Any] | None = None
    if reuse_kanji_builder is not None:
        reusable_path = reuse_kanji_builder.resolve()
        if (
            not reusable_path.is_file()
            or reusable_path.is_symlink()
            or reusable_path.name != names["kanji_builder"]
        ):
            raise PublicReleaseError("reusable kanji builder identity changed")
        reusable = {
            "name": reusable_path.name,
            "sha256": sha256_file(reusable_path),
        }
    return {
        "contract": "public-release-artifact-cache-v1",
        "full_apkg_sha256": sha256_file(full_apkg),
        "product_version": product_version,
        "reuse_core_apkg": reusable_core,
        "reuse_kanji_builder": reusable,
        "release_code": code,
        "builder_sources": builder_sources,
    }


def _validate_release_output(
    *, output_root: Path, input_fingerprint_sha256: str
) -> dict[str, Any]:
    pins = list(output_root.glob("public-release.json"))
    if len(pins) != 1 or pins[0].is_symlink():
        raise PublicReleaseError("cached public release pin is missing or unsafe")
    try:
        pin = json.loads(pins[0].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicReleaseError("cached public release pin is invalid") from exc
    if not isinstance(pin, dict):
        raise PublicReleaseError("cached public release pin is invalid")
    payload = {key: value for key, value in pin.items() if key != "payload_hash"}
    artifacts = pin.get("artifacts")
    if (
        pin.get("status") != "passed"
        or pin.get("unresolved") != 0
        or pin.get("build_input_fingerprint_sha256")
        != input_fingerprint_sha256
        or pin.get("payload_hash") != sha256_json(payload)
        or not isinstance(artifacts, Mapping)
        or not artifacts
    ):
        raise PublicReleaseError("cached public release pin is not closed")
    expected_names = {"public-release.json", *artifacts.keys()}
    actual_names = {
        path.name
        for path in output_root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if actual_names != expected_names or any(
        path.is_dir() or path.is_symlink() for path in output_root.iterdir()
    ):
        raise PublicReleaseError("cached public release file inventory changed")
    for name, record in artifacts.items():
        if not isinstance(name, str) or not isinstance(record, Mapping):
            raise PublicReleaseError("cached public release artifact record is invalid")
        path = output_root / name
        if (
            not path.is_file()
            or path.stat().st_size != record.get("bytes")
            or sha256_file(path) != record.get("sha256")
        ):
            raise PublicReleaseError(f"cached public release artifact changed: {name}")
    return pin


def _validate_declared_release_output(
    output_root: Path,
) -> tuple[str, dict[str, Any]]:
    """Validate one closed output against the fingerprint recorded in its pin."""
    pin_path = output_root / "public-release.json"
    try:
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicReleaseError("cached public release pin is invalid") from exc
    fingerprint = (
        pin.get("build_input_fingerprint_sha256")
        if isinstance(pin, dict)
        else None
    )
    if (
        not isinstance(fingerprint, str)
        or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None
    ):
        raise PublicReleaseError("cached public release pin is invalid")
    return fingerprint, _validate_release_output(
        output_root=output_root,
        input_fingerprint_sha256=fingerprint,
    )


def _replace_release_output(*, staged: Path, output_root: Path) -> None:
    """Atomically install a staged tree while keeping the old tree recoverable."""
    output_root.parent.mkdir(parents=True, exist_ok=True)
    previous: Path | None = None
    if output_root.exists():
        if not output_root.is_dir() or output_root.is_symlink():
            raise PublicReleaseError(f"output root must be a directory: {output_root}")
        previous = Path(
            tempfile.mkdtemp(
                prefix=f".{output_root.name}.previous-",
                dir=output_root.parent,
            )
        )
        previous.rmdir()
        os.replace(output_root, previous)
    try:
        os.replace(staged, output_root)
    except BaseException:
        if previous is not None and previous.exists() and not output_root.exists():
            os.replace(previous, output_root)
        raise
    if previous is not None and previous.exists():
        shutil.rmtree(previous)


def _install_cached_release(
    *, cache_tree: Path, output_root: Path, input_fingerprint_sha256: str
) -> dict[str, Any]:
    pin = _validate_release_output(
        output_root=cache_tree,
        input_fingerprint_sha256=input_fingerprint_sha256,
    )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.cache-", dir=output_root.parent)
    )
    try:
        shutil.copytree(cache_tree, staged, dirs_exist_ok=True, copy_function=shutil.copy2)
        _validate_release_output(
            output_root=staged,
            input_fingerprint_sha256=input_fingerprint_sha256,
        )
        _replace_release_output(staged=staged, output_root=output_root)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return pin


def _archive_release_output(
    *, output_root: Path, cache_entry: Path, input_fingerprint_sha256: str
) -> None:
    _validate_release_output(
        output_root=output_root,
        input_fingerprint_sha256=input_fingerprint_sha256,
    )
    if cache_entry.exists():
        _validate_release_output(
            output_root=cache_entry / "tree",
            input_fingerprint_sha256=input_fingerprint_sha256,
        )
        return
    cache_entry.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(prefix=f".{cache_entry.name}.", dir=cache_entry.parent)
    )
    try:
        tree = staged / "tree"
        shutil.copytree(output_root, tree, copy_function=shutil.copy2)
        _write_json(
            staged / "cache-receipt.json",
            {
                "schema_version": 1,
                "status": "passed",
                "input_fingerprint_sha256": input_fingerprint_sha256,
            },
        )
        os.replace(staged, cache_entry)
    finally:
        if staged.exists():
            shutil.rmtree(staged)


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


def _private_kanji_note_ids(
    collection: Collection,
) -> tuple[list[int], list[int]]:
    """Return reading IDs and all private kanji IDs for the v1.3.0 source shape."""
    ids_by_name = {
        name: _note_ids_for_notetype(collection, name)
        for name in PRIVATE_KANJI_NOTETYPE_NAMES
    }
    reading_ids = ids_by_name[KANJI_NOTETYPE_NAME]
    writing_ids = ids_by_name[KANJI_WRITING_NOTETYPE_NAME]
    for name, ids in ids_by_name.items():
        if len(ids) != EXPECTED_KANJI_NOTES:
            raise PublicReleaseError(
                f"full APKG {name} count changed: {len(ids)}"
            )
    private_ids = [*reading_ids, *writing_ids]
    if len(set(private_ids)) != len(private_ids):
        raise PublicReleaseError("private kanji note IDs overlap")
    return reading_ids, sorted(private_ids)


def _is_private_kanji_deck(name: str) -> bool:
    return any(
        name == root or name.startswith(f"{root}::")
        for root in PRIVATE_KANJI_DECK_ROOTS
    )


def _remove_private_kanji_content(
    collection: Collection,
    private_note_ids: Iterable[int],
) -> None:
    """Remove both private kanji note/deck families from a public core."""
    collection.remove_notes(list(private_note_ids))
    _remove_matching_decks(collection, keep_kanji=False)
    for name in PRIVATE_KANJI_NOTETYPE_NAMES:
        model = collection.models.by_name(name)
        if model is not None:
            collection.models.remove(int(model["id"]))


def _canonicalize_kanji_root(collection: Collection) -> None:
    """Rename the private v1.3.0 kanji root to the builder's public root."""
    target = collection.decks.by_name(KANJI_DECK_ROOT)
    private_roots = []
    for root in PRIVATE_KANJI_DECK_ROOTS:
        if root == KANJI_DECK_ROOT:
            continue
        private_root = collection.decks.by_name(root)
        if private_root is not None:
            private_roots.append(private_root)
    if len(private_roots) > 1 or (target is not None and private_roots):
        raise PublicReleaseError("private kanji deck roots are ambiguous")
    if target is None:
        if not private_roots:
            raise PublicReleaseError("private kanji deck root is missing")
        collection.decks.rename(int(private_roots[0]["id"]), KANJI_DECK_ROOT)
    if collection.decks.by_name(KANJI_DECK_ROOT) is None:
        raise PublicReleaseError("builder kanji deck root is missing")


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


def _orphan_migration_note_guids(collection: Collection) -> tuple[str, ...]:
    """Return package-only migration notes that need an export carrier card."""

    if getattr(collection, "db", None) is None:
        return ()
    note_ids = collection.db.list(
        "select n.id from notes n left join cards c on c.nid = n.id "
        "where c.id is null order by n.id"
    )
    guids: list[str] = []
    for note_id in note_ids:
        note = collection.get_note(note_id)
        if (
            "RetiredKanaAuxiliaryCard" not in note.keys()
            or not note["RetiredKanaAuxiliaryCard"]
        ):
            raise PublicReleaseError(
                f"public core contains an unknown orphan note: {note.guid}"
            )
        guids.append(note.guid)
    return tuple(sorted(guids))


def _restore_migration_carrier_cards(
    collection: Collection, *, guids: Iterable[str]
) -> None:
    migration_guids = tuple(guids)
    if not migration_guids:
        return
    note_ids_by_guid = {
        collection.get_note(note_id).guid: note_id
        for note_id in collection.find_notes("")
    }
    root_deck = collection.decks.by_name(ROOT_DECK_NAME)
    if root_deck is None:
        raise PublicReleaseError(f"root deck is missing: {ROOT_DECK_NAME}")
    for guid in migration_guids:
        note_id = note_ids_by_guid.get(guid)
        if note_id is None or collection.find_cards(f"nid:{note_id}"):
            raise PublicReleaseError(f"migration note carrier differs: {guid}")
        collection.after_note_updates(
            [note_id],
            mark_modified=False,
            generate_cards=True,
        )
        card_ids = collection.find_cards(f"nid:{note_id}")
        if len(card_ids) != 1:
            raise PublicReleaseError(
                f"migration note carrier was not restored: {guid}"
            )
        collection.set_deck(card_ids, int(root_deck["id"]))


def _strip_migration_carrier_cards(
    package: Path, *, guids: Iterable[str]
) -> None:
    migration_guids = tuple(guids)
    if not migration_guids:
        return
    with zipfile.ZipFile(package) as archive:
        if "collection.anki21" not in archive.namelist():
            raise PublicReleaseError("public APKG collection is missing")
        collection_bytes = archive.read("collection.anki21")
    with tempfile.TemporaryDirectory(
        prefix=".public-migration-notes-", dir=package.parent
    ) as temporary:
        temporary_root = Path(temporary)
        collection_path = temporary_root / "collection.anki21"
        collection_path.write_bytes(collection_bytes)
        collection = Collection(str(collection_path))
        try:
            notes_by_guid = {
                collection.get_note(note_id).guid: note_id
                for note_id in collection.find_notes("")
            }
            if collection.db is None:
                raise PublicReleaseError("public APKG collection is unavailable")
            for guid in migration_guids:
                note_id = notes_by_guid.get(guid)
                card_ids = (
                    collection.find_cards(f"nid:{note_id}")
                    if note_id is not None
                    else []
                )
                if len(card_ids) != 1:
                    raise PublicReleaseError(
                        f"migration note carrier differs in public APKG: {guid}"
                    )
                collection.db.execute(
                    "delete from cards where id = ?", int(card_ids[0])
                )
        finally:
            collection.close(downgrade=False)
        patched_collection = collection_path.read_bytes()
        temporary_package = temporary_root / package.name
        with zipfile.ZipFile(package) as source, zipfile.ZipFile(
            temporary_package, mode="w"
        ) as destination:
            for info in source.infolist():
                if info.filename == "collection.anki21":
                    destination.writestr(info, patched_collection)
                    continue
                with source.open(info) as input_stream, destination.open(
                    info, mode="w", force_zip64=True
                ) as output_stream:
                    shutil.copyfileobj(input_stream, output_stream)
        os.replace(temporary_package, package)


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
            and not _is_private_kanji_deck(name)
        ]
    else:
        remove = [name for name in names if _is_private_kanji_deck(name)]
    _remove_decks(collection, sorted(remove, key=lambda value: value.count("::"), reverse=True))


def _clear_collection_media(
    collection: Collection,
    *,
    keep: Mapping[str, str] | None = None,
) -> None:
    media_root = Path(collection.media.dir())
    required = dict(keep or {})
    for filename, digest in required.items():
        path = media_root / filename
        if path.is_symlink() or not path.is_file() or sha256_file(path) != digest:
            raise PublicReleaseError(
                f"required kanji media is missing or changed: {filename}"
            )
    for path in media_root.iterdir():
        if path.name in required:
            continue
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


def _kanji_skeleton_records(
    collection: Collection, kanji_ids: Iterable[int]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for note_id in kanji_ids:
        note = collection.get_note(note_id)
        if tuple(note.keys()) != KANJI_FIELDS:
            raise PublicReleaseError("kanji notetype fields changed")
        projected = {field: note[field] for field in KANJI_FIELDS}
        projected["Meaning"] = ""
        projected["Volume"] = _kanji_volume(collection, note_id)
        if _VECTOR_GLYPH_RE.fullmatch(projected["GlyphHTML"]):
            projected["GlyphHTML"] = ""
        records.append(skeleton_note_record(projected))
    records.sort(key=lambda value: int(value["sequence"]))
    if [record["sequence"] for record in records] != list(
        range(1, EXPECTED_KANJI_NOTES + 1)
    ):
        raise PublicReleaseError("kanji skeleton sequence changed")
    if sum(bool(record["vector_glyph"]) for record in records) != (
        EXPECTED_KANJI_VECTOR_GLYPHS
    ):
        raise PublicReleaseError("kanji skeleton vector count changed")
    return records


def _kanji_volume(collection: Collection, note_id: int) -> str:
    note = collection.get_note(note_id)
    stored = note["Volume"]
    if stored in {"상권", "하권"}:
        return stored
    card_ids = collection.find_cards(f"nid:{note_id}")
    if len(card_ids) != 1:
        raise PublicReleaseError("kanji volume route is ambiguous")
    deck_name = collection.decks.name(collection.get_card(card_ids[0]).did)
    for volume in ("상권", "하권"):
        if deck_name == volume or deck_name.endswith(f"::{volume}"):
            return volume
    raise PublicReleaseError(f"kanji volume route changed: {deck_name}")


def _kanji_skeleton_static_media(
    collection: Collection,
    kanji_ids: Iterable[int],
) -> dict[str, str]:
    filenames: set[str] = set()
    for note_id in kanji_ids:
        note = collection.get_note(note_id)
        filenames.update(KANJI_STROKE_MEDIA_RE.findall(note["StrokeOrder"]))
    if len(filenames) != EXPECTED_KANJI_STROKE_MEDIA:
        raise PublicReleaseError(
            f"kanji stroke media references changed: {len(filenames)}"
        )
    media_root = Path(collection.media.dir())
    required = dict(KANJI_REQUIRED_STATIC_MEDIA)
    for filename in sorted(filenames):
        path = media_root / filename
        if path.is_symlink() or not path.is_file():
            raise PublicReleaseError(f"kanji stroke media is missing: {filename}")
        required[filename] = sha256_file(path)
    try:
        return validate_kanji_static_media(required)
    except ValueError as exc:
        raise PublicReleaseError(str(exc)) from exc


def _build_core(
    full_apkg: Path,
    output: Path,
    *,
    reuse_core_apkg: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    with tempfile.TemporaryDirectory(prefix="jlpt-core-release-") as directory:
        collection = _import_package(full_apkg, Path(directory) / "core.anki2")
        try:
            full_snapshot = {
                "cards": collection.card_count(),
                "notes": collection.note_count(),
            }
            kanji_ids, private_kanji_ids = _private_kanji_note_ids(collection)
            kanji_records = _kanji_skeleton_records(collection, kanji_ids)
            migration_guids = _orphan_migration_note_guids(collection)
            expected_cards = full_snapshot["cards"] - len(private_kanji_ids)
            expected_notes = full_snapshot["notes"] - len(private_kanji_ids)
            if reuse_core_apkg is None:
                _remove_private_kanji_content(collection, private_kanji_ids)
                _restore_migration_carrier_cards(
                    collection, guids=migration_guids
                )
                exported = _export_root(collection, output)
                if exported != expected_cards + len(migration_guids):
                    raise PublicReleaseError(
                        "core export card count changed: "
                        f"{exported} != {expected_cards + len(migration_guids)}"
                    )
        finally:
            collection.close(downgrade=False)
    if reuse_core_apkg is not None:
        shutil.copy2(reuse_core_apkg, output)
    else:
        _strip_migration_carrier_cards(output, guids=migration_guids)
    snapshot = _package_snapshot(output)
    if (
        snapshot["notes"] != expected_notes
        or snapshot["cards"] != expected_cards
        or any(
            name in snapshot["custom_notetype_note_counts"]
            for name in PRIVATE_KANJI_NOTETYPE_NAMES
        )
        or any(_is_private_kanji_deck(name) for name in snapshot["deck_names"])
        or any(
            name.startswith("jlpt-public-kanji-")
            or KANJI_STROKE_MEDIA_RE.fullmatch(name)
            for name in _package_media(output)
        )
    ):
        raise PublicReleaseError("core APKG still contains the optional kanji deck")
    return full_snapshot, snapshot, kanji_records


def _build_skeleton(
    full_apkg: Path,
    output: Path,
    *,
    product_version: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="jlpt-kanji-skeleton-") as directory:
        collection = _import_package(full_apkg, Path(directory) / "skeleton.anki2")
        try:
            reading_ids, private_kanji_ids = _private_kanji_note_ids(collection)
            kanji_ids = set(private_kanji_ids)
            all_ids = {int(value) for value in collection.find_notes("")}
            other_ids = sorted(all_ids - kanji_ids)
            if other_ids:
                collection.remove_notes(other_ids)
            _remove_matching_decks(collection, keep_kanji=True)
            _canonicalize_kanji_root(collection)
            records = _kanji_skeleton_records(collection, reading_ids)
            static_media = _kanji_skeleton_static_media(
                collection,
                private_kanji_ids,
            )
            for note_id in private_kanji_ids:
                note = collection.get_note(note_id)
                note["Meaning"] = ""
                note["Volume"] = _kanji_volume(collection, note_id)
                if _VECTOR_GLYPH_RE.fullmatch(note["GlyphHTML"]):
                    note["GlyphHTML"] = ""
                collection.update_note(note)
            _clear_collection_media(
                collection,
                keep=static_media,
            )
            export_output = output.with_suffix(".apkg")
            exported = _export_root(collection, export_output)
            if exported != EXPECTED_KANJI_ADDON_CARDS:
                raise PublicReleaseError(
                    f"kanji skeleton card count changed: {exported}"
                )
            export_output.replace(output)
        finally:
            collection.close(downgrade=False)
    snapshot = _package_snapshot(output)
    if (
        snapshot["notes"] != EXPECTED_KANJI_ADDON_NOTES
        or snapshot["cards"] != EXPECTED_KANJI_ADDON_CARDS
        or snapshot["custom_notetype_note_counts"] != {
            name: EXPECTED_KANJI_NOTES
            for name in PRIVATE_KANJI_NOTETYPE_NAMES
        }
        or any(
            name != KANJI_DECK_ROOT
            and not name.startswith(f"{KANJI_DECK_ROOT}::")
            for name in snapshot["deck_names"]
            if _is_private_kanji_deck(name)
        )
        or _package_media(output) != static_media
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
        "static_media_count": EXPECTED_KANJI_STATIC_MEDIA,
        "static_media_sha256": sha256_json(static_media),
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
            target = kanji_builder_archive_path(relative)
            payload = source.read_bytes()
            _zip_write(
                archive,
                f"{BUILDER_ARCHIVE_ROOT}/{target}",
                payload,
                mode=kanji_builder_file_mode(relative),
            )
            source_hashes[target] = sha256_file(source)
        for source in (skeleton_apkg, skeleton_manifest):
            _zip_write(
                archive,
                f"{BUILDER_ARCHIVE_ROOT}/assets/{source.name}",
                source.read_bytes(),
            )
    return dict(sorted(source_hashes.items()))


def _reuse_kanji_builder(
    *,
    source: Path,
    output: Path,
    product_version: str,
    current_records: list[dict[str, Any]],
) -> dict[str, str]:
    """Reuse builder bytes only when its skeleton and source files are exact."""

    names = release_filenames(product_version)
    if source.name != names["kanji_builder"] or source.is_symlink():
        raise PublicReleaseError("reusable kanji builder identity changed")
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise PublicReleaseError("reusable kanji builder is invalid") from exc
    prefix = f"{BUILDER_ARCHIVE_ROOT}/"
    manifest_name = f"{prefix}assets/{names['skeleton_manifest']}"
    with archive:
        try:
            manifest = json.loads(archive.read(manifest_name))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PublicReleaseError(
                "reusable kanji builder lacks its skeleton manifest"
            ) from exc
        if not isinstance(manifest, dict):
            raise PublicReleaseError("reusable kanji skeleton manifest is invalid")
        try:
            validated_records = list(validate_skeleton_manifest(manifest))
        except ValueError as exc:
            raise PublicReleaseError(str(exc)) from exc
        if validated_records != current_records:
            raise PublicReleaseError(
                "kanji notes changed; the existing builder cannot be reused"
            )
        skeleton_name = str(manifest["skeleton_apkg"])
        try:
            skeleton = archive.read(f"{prefix}assets/{skeleton_name}")
        except KeyError as exc:
            raise PublicReleaseError(
                "reusable kanji builder lacks its skeleton asset"
            ) from exc
        if hashlib.sha256(skeleton).hexdigest() != manifest["skeleton_apkg_sha256"]:
            raise PublicReleaseError("reusable kanji skeleton asset changed")
        source_hashes: dict[str, str] = {}
        for relative in KANJI_BUILDER_FILES:
            local = ROOT / relative
            target = kanji_builder_archive_path(relative)
            try:
                packaged = archive.read(f"{prefix}{target}")
            except KeyError as exc:
                raise PublicReleaseError(
                    f"reusable kanji builder source is missing: {target}"
                ) from exc
            if local.is_symlink() or not local.is_file() or packaged != local.read_bytes():
                raise PublicReleaseError(
                    f"reusable kanji builder source changed: {relative}"
                )
            source_hashes[target] = sha256_file(local)
    shutil.copy2(source, output)
    return dict(sorted(source_hashes.items()))


def prepare_direct_release(
    *,
    full_apkg: Path,
    output_root: Path,
    product_version: str,
    reuse_core_apkg: Path | None = None,
    reuse_kanji_builder: Path | None = None,
    artifact_cache_root: Path | None = None,
) -> dict[str, Any]:
    """Create a direct core APKG and a small optional kanji builder bundle."""
    input_fingerprint = _public_release_input_fingerprint(
        full_apkg=full_apkg,
        product_version=product_version,
        reuse_core_apkg=reuse_core_apkg,
        reuse_kanji_builder=reuse_kanji_builder,
    )
    input_fingerprint_sha256 = sha256_json(input_fingerprint)
    cache_root = (
        artifact_cache_root.resolve()
        if artifact_cache_root is not None
        else _default_artifact_cache_root()
    )
    cache_entry = cache_root / input_fingerprint_sha256
    if output_root.exists() and (
        not output_root.is_dir() or output_root.is_symlink()
    ):
        raise PublicReleaseError(f"output root must be a directory: {output_root}")
    replaced_artifact_cache_key: str | None = None
    if output_root.exists() and any(output_root.iterdir()):
        existing_fingerprint, pin = _validate_declared_release_output(output_root)
        if existing_fingerprint != input_fingerprint_sha256:
            _archive_release_output(
                output_root=output_root,
                cache_entry=cache_root / existing_fingerprint,
                input_fingerprint_sha256=existing_fingerprint,
            )
            replaced_artifact_cache_key = existing_fingerprint
        else:
            _archive_release_output(
                output_root=output_root,
                cache_entry=cache_entry,
                input_fingerprint_sha256=input_fingerprint_sha256,
            )
            return {
                **pin,
                "artifact_cache_key": input_fingerprint_sha256,
                "builds_run": 0,
                "reused": True,
            }
    cache_tree = cache_entry / "tree"
    if cache_tree.is_dir() and not cache_tree.is_symlink():
        pin = _install_cached_release(
            cache_tree=cache_tree,
            output_root=output_root,
            input_fingerprint_sha256=input_fingerprint_sha256,
        )
        return {
            **pin,
            "artifact_cache_key": input_fingerprint_sha256,
            "builds_run": 0,
            "replaced_artifact_cache_key": replaced_artifact_cache_key,
            "reused": True,
        }
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
        full_snapshot, core_snapshot, kanji_records = _build_core(
            full_apkg,
            core_apkg,
            reuse_core_apkg=(
                reuse_core_apkg.resolve()
                if reuse_core_apkg is not None
                else None
            ),
        )
        builder_archive = staged / names["kanji_builder"]
        if reuse_kanji_builder is None:
            skeleton_manifest = _build_skeleton(
                full_apkg,
                skeleton_apkg,
                product_version=product_version,
            )
            _write_json(skeleton_manifest_path, skeleton_manifest)
            builder_source_hashes = _package_kanji_builder(
                output=builder_archive,
                skeleton_apkg=skeleton_apkg,
                skeleton_manifest=skeleton_manifest_path,
            )
            skeleton_apkg.unlink()
            skeleton_manifest_path.unlink()
        else:
            builder_source_hashes = _reuse_kanji_builder(
                source=reuse_kanji_builder.resolve(),
                output=builder_archive,
                product_version=product_version,
                current_records=kanji_records,
            )

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
                "reused": reuse_core_apkg is not None,
            },
            "full_source": {
                **full_snapshot,
                "sha256": sha256_file(full_apkg),
            },
            "kanji_builder": {
                "expected_kanji_addon_cards": EXPECTED_KANJI_ADDON_CARDS,
                "expected_kanji_addon_notes": EXPECTED_KANJI_ADDON_NOTES,
                "expected_kanji_notes": EXPECTED_KANJI_NOTES,
                "expected_pdf_count": 2,
                "expected_static_media": EXPECTED_KANJI_STATIC_MEDIA,
                "expected_stroke_media": EXPECTED_KANJI_STROKE_MEDIA,
                "expected_vector_glyphs": EXPECTED_KANJI_VECTOR_GLYPHS,
                "output_apkg": names["kanji_addon"],
                "reused": reuse_kanji_builder is not None,
                "source_hash": sha256_json(builder_source_hashes),
            },
            "policy_version": POLICY_VERSION,
            "product_version": product_version,
            "build_input_fingerprint_sha256": input_fingerprint_sha256,
            "schema_version": SCHEMA_VERSION,
            "status": "passed",
            "unresolved": 0,
        }
        pin = {**payload, "payload_hash": sha256_json(payload)}
        _write_json(staged / names["release_pin"], pin)
        _replace_release_output(staged=staged, output_root=output_root)
        _archive_release_output(
            output_root=output_root,
            cache_entry=cache_entry,
            input_fingerprint_sha256=input_fingerprint_sha256,
        )
        return {
            **pin,
            "artifact_cache_key": input_fingerprint_sha256,
            "builds_run": 1,
            "replaced_artifact_cache_key": replaced_artifact_cache_key,
            "reused": False,
        }
    finally:
        if staged.exists():
            shutil.rmtree(staged)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-apkg", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--product-version", required=True)
    parser.add_argument("--reuse-core-apkg", type=Path)
    parser.add_argument("--reuse-kanji-builder", type=Path)
    parser.add_argument("--artifact-cache-root", type=Path)
    parser.add_argument("--result-json", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = prepare_direct_release(
        full_apkg=args.full_apkg.resolve(),
        output_root=args.output_root.resolve(),
        product_version=args.product_version,
        reuse_core_apkg=args.reuse_core_apkg,
        reuse_kanji_builder=args.reuse_kanji_builder,
        artifact_cache_root=args.artifact_cache_root,
    )
    if args.result_json is None:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        _write_json(args.result_json.resolve(), result)


if __name__ == "__main__":
    main()
