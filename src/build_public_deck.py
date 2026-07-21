#!/usr/bin/env python3
"""Materialize a public bundle from exact user PDFs and build a personal APKG."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from public_hashing import sha256_file, sha256_json
from public_apkg_builder import (
    APKG_POLICY_VERSION,
    BUILD_REPORT,
    LOGICAL_MANIFEST,
    RENDERED_SAMPLE_INDEX,
    STAGE_ID,
    STAGE_MANIFEST,
    build_public_apkg,
)
from public_build_contract import (
    BUNDLE_MANIFEST,
    KANJIDIC2_LICENSE,
    KANJIDIC2_SNAPSHOT,
    PUBLIC_BUNDLE_POLICY_VERSION,
    PUBLIC_KANJI_GLOSS_LEDGER,
    PUBLIC_LAYOUT_REGISTRY,
    PUBLIC_SOURCE_CATALOG,
    PublicBuildContractError,
    bundle_payload_file_hashes,
    deck_semantic_hash,
    public_build_file_hashes,
)
from public_materialization import (
    PUBLIC_MATERIALIZATION_POLICY_VERSION,
    materialize_public_inputs,
)
from public_kanji import PublicKanjiError, load_kanjidic2
from public_source_proof import (
    SOURCE_PROOF_POLICY_VERSION,
    build_source_proof,
    match_public_pdfs,
)
from public_release import (
    RELEASE_MANIFEST,
    RELEASE_NOTES,
    UPDATE_REPORT_JSON,
    UPDATE_REPORT_TEXT,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE_ROOT = ROOT
RELEASE_PIN_NAME = "public-release.json"
DEFAULT_RELEASE_PIN = ROOT / "config" / RELEASE_PIN_NAME
PUBLIC_BUILD_REPORT = "public-build-report.json"
MATERIALIZATION_REPORT = "public-materialization-report.json"
SOURCE_PROOF = "source-proof.json"
PUBLIC_BUILD_POLICY_VERSION = "source-materialized-public-build-v1"
PUBLIC_RELEASE_PIN_POLICY_VERSION = "public-release-pin-v1"


def _default_output_root(root: Path) -> Path:
    """Keep maintainer output in-repo and extracted-bundle output beside the bundle."""
    if (root / BUNDLE_MANIFEST).is_file():
        return root.parent / "public-release"
    return root / "build" / "public-release"


DEFAULT_OUTPUT_ROOT = _default_output_root(ROOT)


class PublicBuildError(RuntimeError):
    """Raised when a bundle, local reconstruction, or APKG differs from its pin."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicBuildError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PublicBuildError(f"{label} must be a JSON object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validated_bundle_manifest(path: Path) -> dict[str, Any]:
    manifest = _read_json(path, "public bundle manifest")
    payload_hash = manifest.get("payload_hash")
    payload = {key: value for key, value in manifest.items() if key != "payload_hash"}
    if (
        manifest.get("schema_version") != 1
        or manifest.get("policy_version") != PUBLIC_BUNDLE_POLICY_VERSION
        or manifest.get("status") != "passed"
        or manifest.get("unresolved") != 0
        or not isinstance(payload_hash, str)
        or payload_hash != sha256_json(payload)
    ):
        raise PublicBuildError("public bundle manifest is not passed and closed")
    return manifest


def _validated_release_pin(path: Path) -> dict[str, Any]:
    pin = _read_json(path, "public release pin")
    payload = {key: value for key, value in pin.items() if key != "payload_hash"}
    digests = (
        pin.get("archive_sha256"),
        pin.get("bundle_manifest_sha256"),
        pin.get("public_builder_source_hash"),
    )
    if (
        pin.get("schema_version") != 1
        or pin.get("policy_version") != PUBLIC_RELEASE_PIN_POLICY_VERSION
        or pin.get("status") != "passed"
        or pin.get("unresolved") != 0
        or not isinstance(pin.get("archive_bytes"), int)
        or pin.get("archive_bytes", 0) < 1
        or any(
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for digest in digests
        )
        or pin.get("payload_hash") != sha256_json(payload)
    ):
        raise PublicBuildError("public release pin is not passed and closed")
    return pin


def _validate_kanjidic2_snapshot(
    bundle_root: Path,
    manifest: Mapping[str, Any],
) -> None:
    expected_sha256 = manifest.get("kanjidic2_sha256")
    if not isinstance(expected_sha256, str):
        raise PublicBuildError("public bundle KANJIDIC2 snapshot changed")
    try:
        snapshot = load_kanjidic2(
            bundle_root / KANJIDIC2_SNAPSHOT,
            expected_sha256=expected_sha256,
        )
    except PublicKanjiError as exc:
        raise PublicBuildError(
            f"public bundle KANJIDIC2 snapshot changed: {exc}"
        ) from exc
    metadata = {
        "kanjidic2_database_version": snapshot.database_version,
        "kanjidic2_date_of_creation": snapshot.date_of_creation,
        "kanjidic2_file_version": snapshot.file_version,
    }
    if any(manifest.get(key) != value for key, value in metadata.items()):
        raise PublicBuildError("public bundle KANJIDIC2 metadata changed")


def validate_public_bundle(
    bundle_root: Path,
    *,
    release_pin: Path | None = None,
) -> dict[str, Any]:
    """Validate the complete source-empty tree before reading any templates."""
    manifest_path = bundle_root / BUNDLE_MANIFEST
    manifest = _validated_bundle_manifest(manifest_path)
    builder_files = public_build_file_hashes(ROOT)
    if (
        manifest.get("public_builder_files") != builder_files
        or manifest.get("public_builder_source_hash") != sha256_json(builder_files)
    ):
        raise PublicBuildError("public bundle and builder source release differ")
    if release_pin is not None:
        pin = _validated_release_pin(release_pin)
        if (
            pin.get("bundle_manifest_sha256") != sha256_file(manifest_path)
            or pin.get("public_builder_source_hash")
            != manifest.get("public_builder_source_hash")
        ):
            raise PublicBuildError("public bundle differs from the pinned release")
    try:
        actual_files = bundle_payload_file_hashes(bundle_root)
    except PublicBuildContractError as exc:
        raise PublicBuildError(f"public bundle file tree is unsafe: {exc}") from exc
    declared_files = manifest.get("bundle_files")
    if (
        not isinstance(declared_files, dict)
        or declared_files != actual_files
        or manifest.get("bundle_files_hash") != sha256_json(declared_files)
    ):
        raise PublicBuildError("public bundle file tree changed")
    required_hashes = (
        (
            bundle_root / PUBLIC_SOURCE_CATALOG,
            manifest.get("source_catalog_sha256"),
            "source catalog",
        ),
        (
            bundle_root / PUBLIC_LAYOUT_REGISTRY,
            manifest.get("layout_registry_sha256"),
            "layout registry",
        ),
    )
    for path, expected, label in required_hashes:
        if not isinstance(expected, str) or not path.is_file() or sha256_file(path) != expected:
            raise PublicBuildError(f"public bundle {label} changed")
    _validate_kanjidic2_snapshot(bundle_root, manifest)
    for relative, label in (
        (KANJIDIC2_LICENSE, "KANJIDIC2 license"),
        (PUBLIC_KANJI_GLOSS_LEDGER, "kanji gloss ledger"),
    ):
        if not (bundle_root / relative).is_file():
            raise PublicBuildError(f"public bundle lacks {label}")
    protected = manifest.get("protected_fields")
    if not isinstance(protected, dict) or protected.get("leak_count") != 0:
        raise PublicBuildError("public bundle protected fields are not closed")
    return manifest


def _ensure_publish_target(output_root: Path) -> None:
    if output_root.is_symlink() or (output_root.exists() and not output_root.is_dir()):
        raise PublicBuildError(f"output root must be a regular directory: {output_root}")
    if output_root.is_dir() and any(output_root.iterdir()):
        _validated_existing_public_output(output_root)


def _validated_output_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PublicBuildError(f"{label} is not a safe relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PublicBuildError(f"{label} is not a safe relative path")
    return value


def _validated_closed_report(
    path: Path,
    label: str,
    *,
    policy_version: str,
) -> dict[str, Any]:
    report = _read_json(path, label)
    payload = {key: value for key, value in report.items() if key != "payload_hash"}
    if (
        report.get("schema_version") != 1
        or report.get("policy_version") != policy_version
        or report.get("status") != "passed"
        or report.get("unresolved") != 0
        or report.get("payload_hash") != sha256_json(payload)
    ):
        raise PublicBuildError(f"{label} is not passed and closed")
    return report


def _output_tree_inventory(output_root: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()

    def raise_walk_error(error: OSError) -> None:
        raise error

    for current, dir_names, file_names in os.walk(
        output_root,
        topdown=True,
        onerror=raise_walk_error,
        followlinks=False,
    ):
        current_path = Path(current)
        dir_names[:] = sorted(dir_names)
        for name in dir_names:
            path = current_path / name
            relative = path.relative_to(output_root).as_posix()
            if path.is_symlink() or not path.is_dir():
                raise PublicBuildError(f"public output directory is unsafe: {relative}")
            directories.add(relative)
        for name in sorted(file_names):
            path = current_path / name
            relative = path.relative_to(output_root).as_posix()
            if path.is_symlink() or not path.is_file():
                raise PublicBuildError(f"public output file is unsafe: {relative}")
            files.add(relative)
    return files, directories


def _managed_parent_directories(relative_paths: set[str]) -> set[str]:
    directories: set[str] = set()
    for relative in relative_paths:
        parent = PurePosixPath(relative).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _validated_rendered_sample_paths(
    output_root: Path,
    *,
    rendered_sample_files: Any,
) -> tuple[dict[str, Any], set[str]]:
    index = _read_json(
        output_root / RENDERED_SAMPLE_INDEX,
        "existing rendered sample index",
    )
    samples = index.get("samples")
    if index.get("schema_version") != 1 or not isinstance(samples, list):
        raise PublicBuildError("existing rendered sample index is invalid")
    paths: set[str] = set()
    identities: set[tuple[str, str]] = set()
    for position, raw in enumerate(samples):
        if not isinstance(raw, dict):
            raise PublicBuildError("existing rendered sample record is invalid")
        label = raw.get("label")
        side = raw.get("side")
        relative = _validated_output_path(
            raw.get("path"),
            f"rendered sample path {position}",
        )
        digest = raw.get("sha256")
        pure = PurePosixPath(relative)
        identity = (str(label), str(side))
        if (
            not isinstance(label, str)
            or not label
            or side not in {"question", "answer"}
            or len(pure.parts) != 2
            or pure.parts[0] != "rendered-samples"
            or pure.suffix != ".html"
            or relative == RENDERED_SAMPLE_INDEX
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or relative in paths
            or identity in identities
        ):
            raise PublicBuildError("existing rendered sample record is invalid")
        paths.add(relative)
        identities.add(identity)
    if (
        type(rendered_sample_files) is not int
        or rendered_sample_files != len(samples)
    ):
        raise PublicBuildError("existing rendered sample count differs")
    return index, paths


def _validate_managed_public_output(output_root: Path) -> dict[str, Any]:
    if output_root.is_symlink() or not output_root.is_dir():
        raise PublicBuildError("existing public output root is unsafe")
    report = _validated_closed_report(
        output_root / PUBLIC_BUILD_REPORT,
        "existing public build report",
        policy_version=PUBLIC_BUILD_POLICY_VERSION,
    )
    build_report = _read_json(output_root / BUILD_REPORT, "existing build report")
    package = _validated_output_path(build_report.get("package"), "existing package")
    if (
        PurePosixPath(package).name != package
        or build_report.get("schema_version") != 1
        or build_report.get("policy_version") != APKG_POLICY_VERSION
        or build_report.get("status") != "passed"
        or build_report.get("unresolved") != 0
    ):
        raise PublicBuildError("existing build report is invalid")
    sample_index, sample_paths = _validated_rendered_sample_paths(
        output_root,
        rendered_sample_files=build_report.get("rendered_sample_files"),
    )

    stage = _read_json(
        output_root / STAGE_MANIFEST,
        "existing APKG stage manifest",
    )
    raw_artifacts = stage.get("output_artifacts")
    if (
        stage.get("schema_version") != 1
        or stage.get("stage_id") != STAGE_ID
        or stage.get("policy_version") != APKG_POLICY_VERSION
        or stage.get("status") != "passed"
        or stage.get("unresolved") != 0
        or not isinstance(raw_artifacts, dict)
    ):
        raise PublicBuildError("existing APKG stage manifest is invalid")
    artifacts: dict[str, str] = {}
    for raw_name, raw_digest in raw_artifacts.items():
        name = _validated_output_path(raw_name, "existing APKG artifact")
        if (
            not isinstance(raw_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", raw_digest) is None
        ):
            raise PublicBuildError("existing APKG artifact hash is invalid")
        artifacts[name] = raw_digest
    expected_artifacts = {
        package,
        BUILD_REPORT,
        LOGICAL_MANIFEST,
        RENDERED_SAMPLE_INDEX,
        RELEASE_MANIFEST,
        RELEASE_NOTES,
        UPDATE_REPORT_JSON,
        UPDATE_REPORT_TEXT,
        *sample_paths,
    }
    if (
        set(artifacts) != expected_artifacts
        or stage.get("output_bundle_hash") != sha256_json(artifacts)
    ):
        raise PublicBuildError("existing APKG artifact inventory differs")

    source_proof = _validated_closed_report(
        output_root / SOURCE_PROOF,
        "existing source proof",
        policy_version=SOURCE_PROOF_POLICY_VERSION,
    )
    materialization = _validated_closed_report(
        output_root / MATERIALIZATION_REPORT,
        "existing materialization report",
        policy_version=PUBLIC_MATERIALIZATION_POLICY_VERSION,
    )
    expected_files = {
        *expected_artifacts,
        STAGE_MANIFEST,
        PUBLIC_BUILD_REPORT,
        MATERIALIZATION_REPORT,
        SOURCE_PROOF,
    }
    actual_files, actual_directories = _output_tree_inventory(output_root)
    if actual_files != expected_files:
        raise PublicBuildError("existing public output file inventory differs")
    if actual_directories != _managed_parent_directories(expected_files):
        raise PublicBuildError("existing public output directory inventory differs")

    actual_hashes = {
        name: sha256_file(output_root.joinpath(*PurePosixPath(name).parts))
        for name in sorted(expected_artifacts)
    }
    if actual_hashes != artifacts:
        raise PublicBuildError("existing public output artifact content changed")
    for raw in sample_index["samples"]:
        if actual_hashes[str(raw["path"])] != raw["sha256"]:
            raise PublicBuildError("existing rendered sample content changed")

    logical = _read_json(
        output_root / LOGICAL_MANIFEST,
        "existing logical APKG manifest",
    )
    package_digest = artifacts[package]
    if (
        report.get("apkg") != package
        or report.get("apkg_sha256") != package_digest
        or build_report.get("package_sha256") != package_digest
        or build_report.get("package_bytes")
        != (output_root / package).stat().st_size
        or report.get("expected_logical_apkg_hash") != sha256_json(logical)
        or build_report.get("logical_apkg_hash")
        != report.get("expected_logical_apkg_hash")
        or report.get("source_proof_payload_hash")
        != source_proof.get("payload_hash")
        or report.get("materialization_payload_hash")
        != materialization.get("payload_hash")
        or not isinstance(report.get("bundle_manifest_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", report["bundle_manifest_sha256"])
        is None
    ):
        raise PublicBuildError("existing public build output does not reconcile")
    return report


def _validated_existing_public_output(output_root: Path) -> dict[str, Any]:
    try:
        return _validate_managed_public_output(output_root)
    except (OSError, PublicBuildError) as exc:
        raise PublicBuildError(
            f"refusing to replace an unmanaged output root: {output_root}"
        ) from exc


def _backup_path(output_root: Path) -> Path:
    return output_root.parent / f".{output_root.name}.backup"


def _recover_interrupted_publish(output_root: Path) -> None:
    backup = _backup_path(output_root)
    if not backup.exists():
        return
    if backup.is_symlink() or not backup.is_dir():
        raise PublicBuildError(f"public output backup is unsafe: {backup}")
    _validated_existing_public_output(backup)
    if output_root.exists():
        if output_root.is_dir() and not any(output_root.iterdir()):
            output_root.rmdir()
            os.replace(backup, output_root)
        else:
            _validated_existing_public_output(output_root)
            shutil.rmtree(backup)
    else:
        os.replace(backup, output_root)


def _publish_release(release_root: Path, output_root: Path) -> None:
    _validated_existing_public_output(release_root)
    backup = _backup_path(output_root)
    if backup.exists():
        raise PublicBuildError(f"public output backup already exists: {backup}")
    had_previous = output_root.exists() and any(output_root.iterdir())
    if output_root.exists() and not had_previous:
        output_root.rmdir()
    elif had_previous:
        _validated_existing_public_output(output_root)
        os.replace(output_root, backup)
    try:
        os.replace(release_root, output_root)
    except BaseException:
        if had_previous and backup.exists() and not output_root.exists():
            os.replace(backup, output_root)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def build_public_deck(
    *,
    pdf_root: Path,
    bundle_root: Path = DEFAULT_BUNDLE_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    release_pin: Path | None = None,
) -> dict[str, Any]:
    """Hydrate source fields, build once, and publish only the pinned logic."""
    bundle = validate_public_bundle(bundle_root, release_pin=release_pin)
    _recover_interrupted_publish(output_root)
    _ensure_publish_target(output_root)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.tmp-", dir=output_root.parent)
    )
    try:
        source_proof_path = temporary / SOURCE_PROOF
        source_proof = build_source_proof(
            pdf_root=pdf_root,
            catalog_path=bundle_root / PUBLIC_SOURCE_CATALOG,
            output_path=source_proof_path,
        )
        _catalog, matches = match_public_pdfs(
            pdf_root,
            bundle_root / PUBLIC_SOURCE_CATALOG,
        )
        content_root = temporary / "content"
        media_root = temporary / "media"
        materialization = materialize_public_inputs(
            bundle_root=bundle_root,
            matches=matches,
            content_root=content_root,
            media_root=media_root,
        )
        build_root = temporary / "release"
        build_public_apkg(
            content_root=content_root,
            media_root=media_root,
            output_root=build_root,
        )
        logical = _read_json(build_root / LOGICAL_MANIFEST, "public logical manifest")
        build_report = _read_json(build_root / BUILD_REPORT, "public build report")
        logical_hash = sha256_json(logical)
        if (
            logical_hash != bundle.get("expected_logical_apkg_hash")
            or deck_semantic_hash(logical) != bundle.get("deck_semantic_hash")
            or build_report.get("notes") != bundle.get("expected_notes")
            or build_report.get("cards") != bundle.get("expected_cards")
            or build_report.get("media_files") != bundle.get("expected_media_files")
        ):
            raise PublicBuildError("materialized public deck differs from reference")
        shutil.copyfile(source_proof_path, build_root / SOURCE_PROOF)
        _write_json(build_root / MATERIALIZATION_REPORT, materialization)
        package_name = build_report.get("package")
        if not isinstance(package_name, str) or Path(package_name).name != package_name:
            raise PublicBuildError("public build package name is invalid")
        package_path = build_root / package_name
        payload = {
            "apkg": package_name,
            "apkg_sha256": sha256_file(package_path),
            "bundle_manifest_sha256": sha256_file(bundle_root / BUNDLE_MANIFEST),
            "expected_logical_apkg_hash": bundle["expected_logical_apkg_hash"],
            "materialization_payload_hash": materialization["payload_hash"],
            "policy_version": PUBLIC_BUILD_POLICY_VERSION,
            "schema_version": 1,
            "source_proof_payload_hash": source_proof["payload_hash"],
            "status": "passed",
            "unresolved": 0,
        }
        report = {**payload, "payload_hash": sha256_json(payload)}
        _write_json(build_root / PUBLIC_BUILD_REPORT, report)
        _publish_release(build_root, output_root)
        return report
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-root", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, default=DEFAULT_BUNDLE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--release-pin", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = build_public_deck(
        pdf_root=args.pdf_root,
        bundle_root=args.bundle_root,
        output_root=args.output_root,
        release_pin=args.release_pin,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
