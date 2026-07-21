"""Stable user-facing metadata for a locally built public deck."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


PRODUCT_VERSION = "1.0.0"
NOTE_SCHEMA_VERSION = 3
RELEASE_POLICY_VERSION = "jlpt-max-deck-release-v1"
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
IDENTITY_FIELDS = frozenset({"note_id", "note_kind"})
RELEASE_MANIFEST = "release-manifest.json"
RELEASE_NOTES = "release-notes.jsonl"
UPDATE_REPORT_JSON = "update-report.json"
UPDATE_REPORT_TEXT = "update-report.txt"


def validate_product_version(version: str) -> tuple[int, int, int]:
    """Validate the stable product version independently from pipeline v2."""
    match = SEMVER_RE.fullmatch(version)
    if match is None:
        raise ValueError(f"invalid semantic version: {version}")
    parsed = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    if parsed[0] != 1:
        raise ValueError("the stable product release must remain on SemVer 1.x")
    return parsed


def release_tag(version: str) -> str:
    validate_product_version(version)
    return f"release::{version.replace('.', '_')}"


def package_name(version: str) -> str:
    validate_product_version(version)
    return f"JLPT-MAX덱-{version}.apkg"


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_release_records(
    notes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Hash every managed note field so future updates get exact diffs."""
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in notes:
        note_id = raw.get("note_id")
        note_kind = raw.get("note_kind")
        if (
            not isinstance(note_id, str)
            or not note_id
            or note_id in seen
            or not isinstance(note_kind, str)
            or not note_kind
        ):
            raise ValueError(f"invalid or duplicate release note: {note_id}")
        seen.add(note_id)
        field_hashes = {
            key: _sha256_json(raw[key])
            for key in sorted(raw)
            if key not in IDENTITY_FIELDS
        }
        records.append(
            {
                "content_hash": _sha256_json(field_hashes),
                "field_hashes": field_hashes,
                "note_id": note_id,
                "note_kind": note_kind,
                "release_policy_version": RELEASE_POLICY_VERSION,
                "schema_version": NOTE_SCHEMA_VERSION,
            }
        )
    return sorted(records, key=lambda value: str(value["note_id"]))


def compare_release_records(
    previous: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return an exact EntryID/note-ID diff for update reports."""
    previous_by_id = {str(record["note_id"]): record for record in previous}
    current_by_id = {str(record["note_id"]): record for record in current}
    if len(previous_by_id) != len(previous) or len(current_by_id) != len(current):
        raise ValueError("release records contain duplicate note IDs")
    previous_ids = set(previous_by_id)
    current_ids = set(current_by_id)
    shared_ids = previous_ids & current_ids
    for note_id in shared_ids:
        if previous_by_id[note_id].get("note_kind") != current_by_id[note_id].get(
            "note_kind"
        ):
            raise ValueError(f"release note kind changed for stable ID: {note_id}")
    changed_ids = sorted(
        note_id
        for note_id in shared_ids
        if previous_by_id[note_id].get("content_hash")
        != current_by_id[note_id].get("content_hash")
    )
    changed_fields: Counter[str] = Counter()
    for note_id in changed_ids:
        old_fields = previous_by_id[note_id].get("field_hashes", {})
        new_fields = current_by_id[note_id].get("field_hashes", {})
        if not isinstance(old_fields, Mapping) or not isinstance(new_fields, Mapping):
            raise ValueError(f"release record lacks field hashes: {note_id}")
        for field in set(old_fields) | set(new_fields):
            if old_fields.get(field) != new_fields.get(field):
                changed_fields[str(field)] += 1
    return {
        "added_note_ids": sorted(current_ids - previous_ids),
        "changed_fields": dict(sorted(changed_fields.items())),
        "changed_note_ids": changed_ids,
        "current_note_count": len(current_ids),
        "previous_note_count": len(previous_ids),
        "release_policy_version": RELEASE_POLICY_VERSION,
        "removed_note_ids": sorted(previous_ids - current_ids),
        "schema_version": 1,
    }


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _release_notes_bytes(records: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    ).encode("utf-8")


def _report_text(version: str, report: Mapping[str, Any]) -> str:
    changed_fields = report.get("changed_fields", {})
    field_lines = (
        [
            "변경 필드:",
            *[
                f"- {field}: {count}"
                for field, count in sorted(changed_fields.items())
            ],
        ]
        if isinstance(changed_fields, Mapping) and changed_fields
        else ["변경 필드: 없음"]
    )
    return "\n".join(
        [
            f"JLPT MAX덱 {version}",
            "",
            f"추가된 노트: {len(report['added_note_ids'])}",
            f"변경된 노트: {len(report['changed_note_ids'])}",
            f"제외된 노트: {len(report['removed_note_ids'])}",
            *field_lines,
            "",
        ]
    )


def write_release_artifacts(
    *,
    output_root: Path,
    notes: Sequence[Mapping[str, Any]],
    logical_apkg_hash: str,
    packaged_artifacts: Mapping[str, str],
    previous_records: Sequence[Mapping[str, Any]] | None = None,
    product_version: str = PRODUCT_VERSION,
) -> dict[str, Any]:
    """Write deterministic user-facing release metadata beside the APKG."""
    validate_product_version(product_version)
    if not re.fullmatch(r"[0-9a-f]{64}", logical_apkg_hash):
        raise ValueError("logical APKG hash must be SHA-256")
    if any(
        not isinstance(name, str)
        or not name
        or Path(name).name != name
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        for name, digest in packaged_artifacts.items()
    ):
        raise ValueError("packaged artifact hashes must be named SHA-256 values")
    expected_package = package_name(product_version)
    if expected_package not in packaged_artifacts:
        raise ValueError(f"packaged artifacts lack release APKG: {expected_package}")
    if output_root.exists() and not output_root.is_dir():
        raise ValueError(f"release output root must be a directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    for name, expected_hash in packaged_artifacts.items():
        artifact = output_root / name
        if not artifact.is_file() or _sha256_file(artifact) != expected_hash:
            raise ValueError(f"packaged artifact is missing or changed: {name}")
    release_paths = (
        RELEASE_MANIFEST,
        RELEASE_NOTES,
        UPDATE_REPORT_JSON,
        UPDATE_REPORT_TEXT,
    )
    if any((output_root / name).exists() for name in release_paths):
        raise ValueError(f"release metadata already exists: {output_root}")

    records = build_release_records(notes)
    report = compare_release_records(previous_records or [], records)
    report = {
        **report,
        "initial_release": previous_records is None,
        "product_version": product_version,
    }
    notes_payload = _release_notes_bytes(records)
    report_payload = _json_bytes(report)
    text_payload = _report_text(product_version, report).encode("utf-8")
    payloads = {
        RELEASE_NOTES: notes_payload,
        UPDATE_REPORT_JSON: report_payload,
        UPDATE_REPORT_TEXT: text_payload,
    }
    for name, payload in payloads.items():
        (output_root / name).write_bytes(payload)
    note_kind_counts = Counter(str(note["note_kind"]) for note in notes)
    metadata_hashes = {
        name: _sha256_bytes(payload) for name, payload in sorted(payloads.items())
    }
    manifest = {
        "initial_release": previous_records is None,
        "logical_apkg_hash": logical_apkg_hash,
        "metadata_artifacts": metadata_hashes,
        "note_count": len(records),
        "note_counts_by_kind": dict(sorted(note_kind_counts.items())),
        "note_schema_version": NOTE_SCHEMA_VERSION,
        "package_name": expected_package,
        "packaged_artifacts": dict(sorted(packaged_artifacts.items())),
        "policy_version": RELEASE_POLICY_VERSION,
        "product": "JLPT MAX덱",
        "product_version": product_version,
        "release_tag": release_tag(product_version),
        "schema_version": 1,
    }
    (output_root / RELEASE_MANIFEST).write_bytes(_json_bytes(manifest))
    return manifest


validate_product_version(PRODUCT_VERSION)
