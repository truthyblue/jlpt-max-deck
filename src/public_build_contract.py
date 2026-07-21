"""Platform-neutral integrity contract shared by public export and build."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from public_hashing import sha256_file, sha256_json


BUNDLE_MANIFEST = "public-bundle-manifest.json"
BUNDLE_TEMPLATES_DIR = "templates"
BUNDLE_RECIPES_DIR = "recipes"
BUNDLE_OPEN_DATA_DIR = "open-data"
BUNDLE_MEDIA_DIR = "media"
PUBLIC_SOURCE_CATALOG = "public-sources.json"
PUBLIC_LAYOUT_REGISTRY = "public-layouts.json"
PUBLIC_KANJI_GLOSS_LEDGER = "recipes/public-kanji-gloss-reviewed.jsonl"
KANJIDIC2_SNAPSHOT = "open-data/kanjidic2.xml.gz"
KANJIDIC2_LICENSE = "open-data/EDRDG-LICENSE.html"
PUBLIC_BUNDLE_POLICY_VERSION = "source-materialized-public-bundle-v2"
PUBLIC_BUILD_FILES = (
    ".gitattributes",
    "pyproject.toml",
    "scripts/build-public.ps1",
    "scripts/build-public.sh",
    "src/build_public_deck.py",
    "src/public_apkg_builder.py",
    "src/public_build_contract.py",
    "src/public_content.py",
    "src/public_dongyang_reference.py",
    "src/public_hashing.py",
    "src/public_input_contract.py",
    "src/public_kanji.py",
    "src/public_kanji_rendering.py",
    "src/public_layout_cells.py",
    "src/public_lexical_validation.py",
    "src/public_materialization.py",
    "src/public_media.py",
    "src/public_practice_contract.py",
    "src/public_release.py",
    "src/public_ruby.py",
    "src/public_source_proof.py",
    "src/public_source_records.py",
    "src/public_study_rendering.py",
    "src/public_text_geometry.py",
    "src/public_text_layouts.py",
    "src/public_vocabulary_rendering.py",
    "uv.lock",
)
_AUDIO_FILENAME_RE = re.compile(
    r"(?<![a-zA-Z0-9._-])([a-zA-Z0-9][a-zA-Z0-9._-]*\.(?:wav|mp3))"
)


class PublicBuildContractError(RuntimeError):
    """Raised when a logical deck cannot be projected to semantic form."""


def public_build_file_hashes(root: Path) -> dict[str, str]:
    """Hash every source file that can affect an external public build."""
    hashes: dict[str, str] = {}
    for relative in PUBLIC_BUILD_FILES:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise PublicBuildContractError(
                f"public build source file is missing or unsafe: {relative}"
            )
        hashes[relative] = sha256_file(path)
    return hashes


def public_build_source_hash(root: Path) -> str:
    return sha256_json(public_build_file_hashes(root))


def bundle_payload_file_hashes(bundle_root: Path) -> dict[str, str]:
    """Hash the exact regular-file tree covered by the bundle manifest."""
    if bundle_root.is_symlink() or not bundle_root.is_dir():
        raise PublicBuildContractError("public bundle root is missing or unsafe")
    hashes: dict[str, str] = {}
    for path in bundle_root.rglob("*"):
        if path.is_symlink():
            raise PublicBuildContractError(
                f"public bundle contains a symlink: {path.relative_to(bundle_root)}"
            )
        if path.is_dir():
            continue
        if not path.is_file():
            raise PublicBuildContractError(
                f"public bundle contains a non-regular entry: {path}"
            )
        relative = path.relative_to(bundle_root).as_posix()
        if relative == BUNDLE_MANIFEST:
            continue
        if relative in hashes:
            raise PublicBuildContractError(
                f"public bundle path is duplicated: {relative}"
            )
        hashes[relative] = sha256_file(path)
    return {relative: hashes[relative] for relative in sorted(hashes)}


def _semantic_value(value: Any, audio_names: Mapping[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _semantic_value(item, audio_names) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_semantic_value(item, audio_names) for item in value]
    if isinstance(value, str):
        return _AUDIO_FILENAME_RE.sub(
            lambda match: audio_names.get(match.group(1), match.group(1)), value
        )
    return value


def deck_semantic_hash(logical_manifest: Mapping[str, Any]) -> str:
    """Hash deck behavior while treating WAV/MP3 encoding as transport."""
    source_media = logical_manifest.get("media")
    if not isinstance(source_media, list):
        raise PublicBuildContractError("logical manifest lacks media")
    audio_names: dict[str, str] = {}
    normalized_audio_names: set[str] = set()
    for record in source_media:
        if not isinstance(record, dict):
            raise PublicBuildContractError("logical media record must be an object")
        filename = str(record.get("filename", ""))
        suffix = Path(filename).suffix
        if suffix not in {".wav", ".mp3"}:
            continue
        if Path(filename).name != filename or filename in audio_names:
            raise PublicBuildContractError("logical audio filename is unsafe")
        normalized = f"{filename[:-len(suffix)]}.audio"
        if normalized in normalized_audio_names:
            raise PublicBuildContractError("logical audio transport names collide")
        audio_names[filename] = normalized
        normalized_audio_names.add(normalized)
    projected = _semantic_value(copy.deepcopy(dict(logical_manifest)), audio_names)
    media = projected.get("media")
    if not isinstance(media, list):
        raise PublicBuildContractError("logical manifest lacks media")
    normalized_media: list[dict[str, Any]] = []
    for record in media:
        if not isinstance(record, dict):
            raise PublicBuildContractError("logical media record must be an object")
        filename = str(record.get("filename", ""))
        if filename in normalized_audio_names:
            normalized_media.append({"filename": filename})
        else:
            normalized_media.append(dict(record))
    projected["media"] = normalized_media
    return sha256_json(projected)
