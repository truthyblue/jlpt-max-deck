#!/usr/bin/env python3
"""Verify the direct core-release and optional-kanji public boundary."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from direct_release_contract import (  # noqa: E402
    KANJI_BUILDER_FILES,
    POLICY_VERSION,
    SCHEMA_VERSION,
    kanji_builder_archive_path,
    release_filenames,
    sha256_file,
    sha256_json,
)

PIN = ROOT / "config" / "public-release.json"
ALLOWED_MP3_FILES = {
    "site/assets/demo-dasu-example-2.mp3",
    "site/assets/demo-dasu-example-3.mp3",
    "site/assets/demo-dasu-example.mp3",
    "site/assets/demo-dasu-word.mp3",
}
FORBIDDEN_TOP_LEVEL = {
    ".tools",
    ".venv",
    "build",
    "data",
    "prompts",
    "public-release",
    "tmp",
    "tools",
}
FORBIDDEN_FILENAMES = {
    "kanji-builder.log",
}
FORBIDDEN_SUFFIXES = {
    ".anki2",
    ".apkg",
    ".pdf",
    ".sqlite",
    ".sqlite3",
    ".wav",
    ".zip",
}
SHA256 = re.compile(r"[0-9a-f]{64}")


def _payload_hash(value: object) -> str:
    import hashlib

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fail(message: str) -> NoReturn:
    raise RuntimeError(message)


def _verify_pin(pin: dict[str, object]) -> None:
    payload = {key: value for key, value in pin.items() if key != "payload_hash"}
    version = pin.get("product_version")
    if (
        pin.get("schema_version") != SCHEMA_VERSION
        or pin.get("policy_version") != POLICY_VERSION
        or not isinstance(version, str)
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None
        or pin.get("status") != "passed"
        or pin.get("unresolved") != 0
        or pin.get("payload_hash") != _payload_hash(payload)
    ):
        _fail("public release pin is not closed")
    names = release_filenames(version)
    expected_artifacts = {
        names["core_apkg"],
        names["kanji_builder"],
        names["checksums"],
    }
    artifacts = pin.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != expected_artifacts:
        _fail("public release artifact inventory changed")
    for name, record in artifacts.items():
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("bytes"), int)
            or record["bytes"] <= 0
            or SHA256.fullmatch(str(record.get("sha256"))) is None
        ):
            _fail(f"invalid release artifact record: {name}")
    core = pin.get("core")
    kanji = pin.get("kanji_builder")
    if not isinstance(core, dict) or not isinstance(kanji, dict):
        _fail("direct-release logical metadata is missing")
    if (
        core.get("notes") != 13_903
        or core.get("cards") != 20_065
        or core.get("media_files") != 18_153
        or kanji.get("expected_pdf_count") != 2
        or kanji.get("expected_kanji_notes") != 2_337
        or kanji.get("expected_vector_glyphs") != 14
        or kanji.get("output_apkg") != names["kanji_addon"]
    ):
        _fail("direct-release logical counts changed")


def _tracked_files() -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return tuple(
        raw.decode("utf-8")
        for raw in result.stdout.split(b"\0")
        if raw
    )


def _verify_builder_sources(pin: dict[str, object], tracked: set[str]) -> None:
    if (
        KANJI_BUILDER_FILES != tuple(sorted(KANJI_BUILDER_FILES))
        or len(KANJI_BUILDER_FILES) != len(set(KANJI_BUILDER_FILES))
    ):
        _fail("kanji builder source inventory must be sorted and unique")
    source_hashes: dict[str, str] = {}
    for relative in KANJI_BUILDER_FILES:
        source = ROOT / relative
        if relative not in tracked or source.is_symlink() or not source.is_file():
            _fail(f"kanji builder source is missing or unsafe: {relative}")
        target = kanji_builder_archive_path(relative)
        source_hashes[target] = sha256_file(source)
    kanji_builder = pin.get("kanji_builder")
    if (
        not isinstance(kanji_builder, dict)
        or kanji_builder.get("source_hash")
        != sha256_json(dict(sorted(source_hashes.items())))
    ):
        _fail("kanji builder source differs from the release pin")


def _verify_tracked_boundary(tracked: tuple[str, ...]) -> None:
    for relative in tracked:
        path = Path(relative)
        suffix = path.suffix.lower()
        top_level = path.parts[0]
        if top_level in FORBIDDEN_TOP_LEVEL:
            _fail(f"tracked private or generated directory: {relative}")
        if path.name in FORBIDDEN_FILENAMES:
            _fail(f"tracked local builder log: {relative}")
        if suffix in FORBIDDEN_SUFFIXES:
            _fail(f"tracked release or private input payload: {relative}")
        if suffix == ".mp3" and relative not in ALLOWED_MP3_FILES:
            _fail(f"unapproved tracked MP3: {relative}")


def main() -> int:
    try:
        pin = json.loads(PIN.read_text(encoding="utf-8"))
        tracked = _tracked_files()
        _verify_pin(pin)
        _verify_builder_sources(pin, set(tracked))
        _verify_tracked_boundary(tracked)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"direct release tree verification failed: {exc}", file=sys.stderr)
        return 1
    print("direct release tree verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
