#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""Render tracked documentation and site pages from canonical Jinja templates."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = PurePosixPath("docs-src")
PRODUCT_DATA = PurePosixPath("docs-src/data/product.json")
RELEASE_HISTORY = PurePosixPath("docs-src/data/release-history.json")
RELEASE_PIN = PurePosixPath("config/public-release.json")

# Publication is intentionally explicit. Adding a template never creates a public
# output until its source/output pair is reviewed here.
TEMPLATE_OUTPUTS: tuple[tuple[PurePosixPath, PurePosixPath], ...] = (
    (PurePosixPath("README.md.j2"), PurePosixPath("README.md")),
    (PurePosixPath("docs/anki.md.j2"), PurePosixPath("docs/anki.md")),
    (PurePosixPath("docs/build.md.j2"), PurePosixPath("docs/build.md")),
    (
        PurePosixPath("docs/privacy-and-licensing.md.j2"),
        PurePosixPath("docs/privacy-and-licensing.md"),
    ),
    (
        PurePosixPath("docs/releases/v1.0.1.md.j2"),
        PurePosixPath("docs/releases/v1.0.1.md"),
    ),
    (
        PurePosixPath("docs/releases/v1.0.2.md.j2"),
        PurePosixPath("docs/releases/v1.0.2.md"),
    ),
    (
        PurePosixPath("docs/releases/v1.0.3.md.j2"),
        PurePosixPath("docs/releases/v1.0.3.md"),
    ),
    (
        PurePosixPath("docs/releases/v1.1.0.md.j2"),
        PurePosixPath("docs/releases/v1.1.0.md"),
    ),
    (
        PurePosixPath("docs/releases/v1.1.1.md.j2"),
        PurePosixPath("docs/releases/v1.1.1.md"),
    ),
    (
        PurePosixPath("docs/releases/v1.2.0.md.j2"),
        PurePosixPath("docs/releases/v1.2.0.md"),
    ),
    (
        PurePosixPath("docs/releases/v1.2.1.md.j2"),
        PurePosixPath("docs/releases/v1.2.1.md"),
    ),
    (
        PurePosixPath("docs/releases/v1.3.0.md.j2"),
        PurePosixPath("docs/releases/v1.3.0.md"),
    ),
    (
        PurePosixPath("docs/releases/v2.0.0.md.j2"),
        PurePosixPath("docs/releases/v2.0.0.md"),
    ),
    (
        PurePosixPath("docs/releases/v2.0.1.md.j2"),
        PurePosixPath("docs/releases/v2.0.1.md"),
    ),
    (
        PurePosixPath("docs/releases/v2.0.2.md.j2"),
        PurePosixPath("docs/releases/v2.0.2.md"),
    ),
    (
        PurePosixPath("docs/troubleshooting.md.j2"),
        PurePosixPath("docs/troubleshooting.md"),
    ),
    (PurePosixPath("site/404.html.j2"), PurePosixPath("site/404.html")),
    (
        PurePosixPath("site/getting-started.html.j2"),
        PurePosixPath("site/getting-started.html"),
    ),
    (PurePosixPath("site/index.html.j2"), PurePosixPath("site/index.html")),
    (
        PurePosixPath("site/install-anki.html.j2"),
        PurePosixPath("site/install-anki.html"),
    ),
    (
        PurePosixPath("site/study-guide.html.j2"),
        PurePosixPath("site/study-guide.html"),
    ),
    (PurePosixPath("site/update.html.j2"), PurePosixPath("site/update.html")),
    (PurePosixPath("site/kanji.html.j2"), PurePosixPath("site/kanji.html")),
    (
        PurePosixPath("site/latest-release.json.j2"),
        PurePosixPath("site/latest-release.json"),
    ),
    (PurePosixPath("site/support.html.j2"), PurePosixPath("site/support.html")),
)


class DocumentationRenderError(RuntimeError):
    """Raised when canonical documentation data cannot be rendered safely."""


def _read_json_object(root: Path, relative: PurePosixPath) -> dict[str, Any]:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DocumentationRenderError(f"cannot read {relative}: {exc}") from exc
    if not isinstance(value, dict):
        raise DocumentationRenderError(f"{relative} must contain a JSON object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_release_history(
    root: Path,
    *,
    current_version: str,
) -> tuple[dict[str, Any], ...]:
    raw_releases = _read_json_object(root, RELEASE_HISTORY).get("releases")
    if not isinstance(raw_releases, list) or not raw_releases:
        raise DocumentationRenderError(
            f"{RELEASE_HISTORY} must contain a non-empty releases list"
        )
    expected_keys = {
        "changes",
        "date",
        "label",
        "migration",
        "summary",
        "version",
    }
    releases: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_releases):
        label = raw.get("label") if isinstance(raw, dict) else None
        label_is_valid = label is None or (
            isinstance(label, str) and bool(label.strip())
        )
        if (
            not isinstance(raw, dict)
            or set(raw) != expected_keys
            or not isinstance(raw.get("changes"), list)
            or not raw["changes"]
            or not all(
                isinstance(change, str) and change.strip()
                for change in raw["changes"]
            )
            or not isinstance(raw.get("date"), str)
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw["date"])
            is None
            or not label_is_valid
            or not isinstance(raw.get("migration"), str)
            or not raw["migration"].strip()
            or not isinstance(raw.get("summary"), str)
            or not raw["summary"].strip()
            or not isinstance(raw.get("version"), str)
            or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", raw["version"])
            is None
        ):
            raise DocumentationRenderError(
                f"{RELEASE_HISTORY} release record is invalid: index={index}"
            )
        releases.append(dict(raw))
    versions = [str(release["version"]) for release in releases]
    parsed_versions = [
        tuple(int(part) for part in version.split("."))
        for version in versions
    ]
    if (
        len(versions) != len(set(versions))
        or parsed_versions != sorted(parsed_versions, reverse=True)
        or current_version not in versions
    ):
        raise DocumentationRenderError(
            f"{RELEASE_HISTORY} current release does not match {RELEASE_PIN}"
        )
    published = releases[versions.index(current_version) :]
    for index, release in enumerate(published):
        release["current"] = index == 0
        release["label"] = "최신" if index == 0 else release["label"]
    return tuple(published)


def load_context(root: Path = ROOT) -> dict[str, Any]:
    product = _read_json_object(root, PRODUCT_DATA)
    release_pin = _read_json_object(root, RELEASE_PIN)
    pin_artifacts = release_pin.get("artifacts")
    version = release_pin.get("product_version")
    if not isinstance(version, str) or not isinstance(pin_artifacts, dict):
        raise DocumentationRenderError("release artifact metadata is missing")

    def release_artifact(filename: str) -> dict[str, Any]:
        record = pin_artifacts.get(filename)
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("bytes"), int)
            or not isinstance(record.get("sha256"), str)
        ):
            raise DocumentationRenderError(
                f"{RELEASE_PIN} artifact metadata is invalid: {filename}"
            )
        return {"filename": filename, **record}

    release = {
        "version": version,
        "tag": f"v{version}",
        "artifacts": {
            "core": release_artifact(f"JLPT-MAX-Deck-{version}.apkg"),
            "kanji_builder": release_artifact(
                f"JLPT-MAX-kanji-builder-{version}.zip"
            ),
            "checksums": release_artifact("SHA256SUMS"),
        },
    }
    release_history = _load_release_history(
        root,
        current_version=version,
    )
    return {
        "asset_versions": {
            "showcase_css": _sha256_file(
                root / "site" / "assets" / "showcase.css"
            )[:12],
            "site_css": _sha256_file(root / "site" / "assets" / "site.css")[:12],
        },
        "product": product,
        "release": release,
        "release_history": release_history,
        "release_pin": release_pin,
    }


def create_environment(root: Path = ROOT) -> Environment:
    environment = Environment(
        loader=FileSystemLoader(root / TEMPLATE_ROOT),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        newline_sequence="\n",
    )
    environment.filters["number"] = lambda value: f"{value:,}"
    return environment


def normalize_final_newline(value: str) -> str:
    """Return UTF-8 source text with LF endings and exactly one final newline."""
    return value.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"


def render_documents(root: Path = ROOT) -> Iterator[tuple[PurePosixPath, str]]:
    environment = create_environment(root)
    context = load_context(root)
    for template_name, output_name in TEMPLATE_OUTPUTS:
        template = environment.get_template(template_name.as_posix())
        yield output_name, normalize_final_newline(template.render(**context))


def write_documents(root: Path = ROOT) -> tuple[PurePosixPath, ...]:
    written: list[PurePosixPath] = []
    for relative, rendered in render_documents(root):
        output = root / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        written.append(relative)
    return tuple(written)


def check_documents(root: Path = ROOT) -> tuple[PurePosixPath, ...]:
    stale: list[PurePosixPath] = []
    for relative, rendered in render_documents(root):
        output = root / relative
        try:
            current = output.read_text(encoding="utf-8")
        except OSError:
            current = ""
        if current == rendered:
            continue
        stale.append(relative)
        diff = difflib.unified_diff(
            current.splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=relative.as_posix(),
            tofile=f"rendered/{relative.as_posix()}",
        )
        sys.stderr.writelines(diff)
    return tuple(stale)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render or verify tracked documentation generated from docs-src."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="render tracked outputs")
    mode.add_argument("--check", action="store_true", help="fail if outputs are stale")
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root (defaults to this script's repository)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.write:
            written = write_documents(args.root.resolve())
            print(f"rendered {len(written)} documentation files")
            return 0
        stale = check_documents(args.root.resolve())
    except DocumentationRenderError as exc:
        print(f"documentation render failed: {exc}", file=sys.stderr)
        return 1
    if stale:
        print(
            "documentation render check failed; run scripts/render-docs.py --write",
            file=sys.stderr,
        )
        return 1
    print(f"documentation render check passed: {len(TEMPLATE_OUTPUTS)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
