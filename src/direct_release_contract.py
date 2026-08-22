"""Contracts for direct core-APKG distribution and the optional kanji builder."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 3
POLICY_VERSION = "direct-core-plus-kanji-addon-v1"
KANJI_NOTETYPE_NAME = "JLPT MAX덱 일상무따"
ROOT_DECK_NAME = "JLPT MAX덱"
KANJI_DECK_ROOT = f"{ROOT_DECK_NAME}::일상무따"
KANJI_WRITING_NOTETYPE_NAME = f"{KANJI_NOTETYPE_NAME} 쓰기"
# The v1.3.0 private package has separate reading and writing kanji models
# under the ``::한자`` deck family.  Older private packages used the builder
# contract root directly, so both roots are excluded from the public core.
PRIVATE_KANJI_NOTETYPE_NAMES = (
    KANJI_NOTETYPE_NAME,
    KANJI_WRITING_NOTETYPE_NAME,
)
PRIVATE_KANJI_DECK_ROOTS = (
    KANJI_DECK_ROOT,
    f"{ROOT_DECK_NAME}::한자",
)
EXPECTED_KANJI_NOTES = 2_337
EXPECTED_KANJI_ADDON_NOTES = EXPECTED_KANJI_NOTES * len(
    PRIVATE_KANJI_NOTETYPE_NAMES
)
EXPECTED_KANJI_ADDON_CARDS = EXPECTED_KANJI_ADDON_NOTES
EXPECTED_KANJI_VECTOR_GLYPHS = 14
EXPECTED_KANJI_STROKE_MEDIA = 2_298
KANJI_REQUIRED_STATIC_MEDIA = {
    "_jlpt_max_animcjk_arphic_public_license.txt": (
        "3a5e90c0957524a89e48203febcd4492ca4393678abaa7e5b4d70f3ff32b386d"
    ),
}
EXPECTED_KANJI_STATIC_MEDIA = (
    EXPECTED_KANJI_STROKE_MEDIA + len(KANJI_REQUIRED_STATIC_MEDIA)
)
KANJI_FIELDS = (
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
)
KANJI_BUILDER_FILES = (
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
)
KANJI_BUILDER_EXECUTABLES = (
    "scripts/build-kanji-addon.sh",
    "scripts/start-kanji-addon.command",
    "scripts/start-kanji-addon.sh",
)
KANJI_BUILDER_ARCHIVE_PATHS = {
    "docs/kanji-builder-assets.txt": "assets/README.txt",
    "docs/kanji-builder.md": "README.md",
    "scripts/start-kanji-addon.cmd": "Windows에서 한자 확장 만들기.cmd",
    "scripts/start-kanji-addon.command": "Mac에서 한자 확장 만들기.command",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
KANJI_STROKE_MEDIA_RE = re.compile(r"jlpt-v2-stroke-[0-9a-f]{24}\.svg")


class DirectReleaseContractError(ValueError):
    """Raised when one direct-release artifact crosses its closed contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def kanji_builder_archive_path(relative: str) -> str:
    if relative not in KANJI_BUILDER_FILES:
        raise DirectReleaseContractError(
            f"unknown kanji builder source: {relative}"
        )
    return KANJI_BUILDER_ARCHIVE_PATHS.get(relative, relative)


def kanji_builder_file_mode(relative: str) -> int:
    if relative not in KANJI_BUILDER_FILES:
        raise DirectReleaseContractError(
            f"unknown kanji builder source: {relative}"
        )
    return 0o755 if relative in KANJI_BUILDER_EXECUTABLES else 0o644


def release_filenames(version: str) -> dict[str, str]:
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise DirectReleaseContractError(f"invalid product version: {version!r}")
    return {
        "core_apkg": f"JLPT-MAX-Deck-{version}.apkg",
        "kanji_builder": f"JLPT-MAX-kanji-builder-{version}.zip",
        "kanji_skeleton": f"JLPT-MAX-kanji-skeleton-{version}.asset",
        "kanji_addon": f"JLPT-MAX-kanji-addon-{version}.apkg",
        "kanji_build_report": "kanji-addon-build-report.json",
        "release_pin": "public-release.json",
        "checksums": "SHA256SUMS",
        "skeleton_manifest": "kanji-skeleton-manifest.json",
    }


def note_projection(note: Mapping[str, str]) -> dict[str, str]:
    keys = tuple(note)
    if keys != KANJI_FIELDS:
        raise DirectReleaseContractError(
            f"kanji fields changed: expected={KANJI_FIELDS!r} actual={keys!r}"
        )
    return {field: str(note[field]) for field in KANJI_FIELDS}


def skeleton_note_record(note: Mapping[str, str]) -> dict[str, Any]:
    projected = note_projection(note)
    if projected["Meaning"]:
        raise DirectReleaseContractError("kanji skeleton contains a Korean meaning")
    sort_key = projected["SortKey"]
    if re.fullmatch(r"K[0-9]{6}", sort_key) is None:
        raise DirectReleaseContractError(f"invalid kanji sort key: {sort_key!r}")
    sequence = int(sort_key[1:])
    glyph_html = projected["GlyphHTML"]
    vector = not glyph_html
    return {
        "guid": projected["KanjiID"],
        "note_hash": sha256_json(projected),
        "sequence": sequence,
        "sort_key": sort_key,
        "unit": projected["Unit"],
        "vector_glyph": vector,
        "volume": projected["Volume"],
    }


def validate_kanji_static_media(
    media: Mapping[str, str],
    *,
    expected_sha256: str | None = None,
) -> dict[str, str]:
    normalized = dict(sorted(media.items()))
    if any(
        Path(filename).name != filename or _SHA256_RE.fullmatch(digest) is None
        for filename, digest in normalized.items()
    ):
        raise DirectReleaseContractError("kanji static media inventory is invalid")
    if any(
        normalized.get(filename) != digest
        for filename, digest in KANJI_REQUIRED_STATIC_MEDIA.items()
    ):
        raise DirectReleaseContractError("kanji attribution media changed")
    stroke_media = {
        filename: digest
        for filename, digest in normalized.items()
        if KANJI_STROKE_MEDIA_RE.fullmatch(filename)
    }
    if (
        len(normalized) != EXPECTED_KANJI_STATIC_MEDIA
        or len(stroke_media) != EXPECTED_KANJI_STROKE_MEDIA
        or set(normalized) != set(stroke_media) | set(KANJI_REQUIRED_STATIC_MEDIA)
    ):
        raise DirectReleaseContractError("kanji stroke media inventory changed")
    if expected_sha256 is not None and sha256_json(normalized) != expected_sha256:
        raise DirectReleaseContractError("kanji static media hash changed")
    return normalized


def validate_skeleton_manifest(value: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    expected_keys = {
        "kanji_note_count",
        "notes",
        "policy_version",
        "product_version",
        "schema_version",
        "skeleton_apkg",
        "skeleton_apkg_sha256",
        "static_media_count",
        "static_media_sha256",
        "vector_glyph_count",
    }
    if set(value) != expected_keys:
        raise DirectReleaseContractError("kanji skeleton manifest keys changed")
    notes = value.get("notes")
    skeleton_name = value.get("skeleton_apkg")
    skeleton_digest = value.get("skeleton_apkg_sha256")
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("policy_version") != POLICY_VERSION
        or not isinstance(value.get("product_version"), str)
        or not isinstance(skeleton_name, str)
        or Path(skeleton_name).name != skeleton_name
        or not isinstance(skeleton_digest, str)
        or _SHA256_RE.fullmatch(skeleton_digest) is None
        or value.get("static_media_count") != EXPECTED_KANJI_STATIC_MEDIA
        or _SHA256_RE.fullmatch(str(value.get("static_media_sha256"))) is None
        or not isinstance(notes, list)
        or value.get("kanji_note_count") != EXPECTED_KANJI_NOTES
        or len(notes) != EXPECTED_KANJI_NOTES
        or value.get("vector_glyph_count") != EXPECTED_KANJI_VECTOR_GLYPHS
    ):
        raise DirectReleaseContractError("kanji skeleton manifest is invalid")
    if skeleton_name != release_filenames(
        str(value["product_version"])
    )["kanji_skeleton"]:
        raise DirectReleaseContractError("kanji skeleton asset name changed")
    records: list[dict[str, Any]] = []
    for sequence, raw in enumerate(notes, start=1):
        if not isinstance(raw, dict) or set(raw) != {
            "guid",
            "note_hash",
            "sequence",
            "sort_key",
            "unit",
            "vector_glyph",
            "volume",
        }:
            raise DirectReleaseContractError("kanji skeleton note record is invalid")
        if (
            raw.get("sequence") != sequence
            or raw.get("sort_key") != f"K{sequence:06d}"
            or not isinstance(raw.get("guid"), str)
            or not raw.get("guid")
            or not isinstance(raw.get("note_hash"), str)
            or _SHA256_RE.fullmatch(str(raw["note_hash"])) is None
            or raw.get("volume") not in {"상권", "하권"}
            or not isinstance(raw.get("unit"), str)
            or not raw.get("unit")
            or not isinstance(raw.get("vector_glyph"), bool)
        ):
            raise DirectReleaseContractError(
                f"kanji skeleton sequence changed: {sequence}"
            )
        records.append(dict(raw))
    if len({str(record["guid"]) for record in records}) != len(records):
        raise DirectReleaseContractError("kanji skeleton GUIDs are duplicated")
    if sum(bool(record["vector_glyph"]) for record in records) != (
        EXPECTED_KANJI_VECTOR_GLYPHS
    ):
        raise DirectReleaseContractError("kanji vector glyph count changed")
    return tuple(records)


def checksum_lines(paths: Sequence[Path]) -> str:
    names = [path.name for path in paths]
    if len(names) != len(set(names)):
        raise DirectReleaseContractError("checksum filenames are duplicated")
    return "".join(f"{sha256_file(path)}  {path.name}\n" for path in sorted(paths))
