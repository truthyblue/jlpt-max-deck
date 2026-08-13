#!/usr/bin/env python3
"""Render a gallery announcement with local release images for review."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
PAGES_ASSET_RE = re.compile(
    r'(?P<prefix>\bsrc=["\'])'
    r'https://truthyblue\.github\.io/jlpt-max-deck/assets/'
    r'(?P<asset>[^"\']+)'
    r'(?P<suffix>["\'])'
)


class GalleryPreviewError(RuntimeError):
    """Raised when a preview cannot preserve the publication contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_asset_path(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise GalleryPreviewError(f"unsafe gallery asset path: {raw}")
    return path


def render_gallery_preview(
    *, source: Path, output: Path, repo_root: Path = ROOT
) -> dict[str, Any]:
    """Rewrite published Pages image URLs to local, hash-checked assets."""
    if not source.is_file():
        raise GalleryPreviewError(f"gallery announcement does not exist: {source}")
    html = source.read_text(encoding="utf-8")
    matches = list(PAGES_ASSET_RE.finditer(html))
    if not matches:
        raise GalleryPreviewError("gallery announcement has no Pages-hosted images")

    assets_by_path: dict[str, dict[str, Any]] = {}

    def replace(match: re.Match[str]) -> str:
        relative = _safe_asset_path(match.group("asset"))
        public_path = PurePosixPath("site/assets") / relative
        local_path = repo_root.joinpath(*public_path.parts)
        if not local_path.is_file():
            raise GalleryPreviewError(
                f"gallery preview asset does not exist: {public_path.as_posix()}"
            )
        preview_src = os.path.relpath(local_path, output.parent).replace(os.sep, "/")
        assets_by_path.setdefault(
            public_path.as_posix(),
            {
                "public_path": public_path.as_posix(),
                "preview_src": preview_src,
                "bytes": local_path.stat().st_size,
                "sha256": _sha256(local_path),
            },
        )
        return f'{match.group("prefix")}{preview_src}{match.group("suffix")}'

    preview = PAGES_ASSET_RE.sub(replace, html)
    if PAGES_ASSET_RE.search(preview):
        raise GalleryPreviewError("gallery preview still contains a remote image URL")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(preview, encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "status": "passed",
        "source": source.relative_to(repo_root).as_posix(),
        "source_sha256": _sha256(source),
        "preview": output.relative_to(repo_root).as_posix(),
        "preview_sha256": _sha256(output),
        "image_count": len(matches),
        "assets": list(assets_by_path.values()),
    }
    output.with_suffix(".receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release version, for example 1.2.0")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not VERSION_RE.fullmatch(args.version):
        raise GalleryPreviewError(f"invalid release version: {args.version}")
    source = ROOT / "docs/jlpt-gallery-updates" / f"v{args.version}.html"
    output = args.output or ROOT / "build/gallery-preview" / f"v{args.version}.html"
    receipt = render_gallery_preview(source=source, output=output)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
