#!/usr/bin/env python3
"""Create a deployable Pages artifact with fingerprinted local assets."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ASSET_URL_PATTERN = re.compile(
    r'(?P<prefix>\b(?:href|src)=")'
    r'(?P<path>assets/[^"?#]+)'
    r'(?:\?[^"#]*)?'
    r'(?P<fragment>#[^"]*)?"',
    re.IGNORECASE,
)
ABSOLUTE_SITE_ASSET_URL_PATTERN = re.compile(
    r'(?P<prefix>\b(?:href|src|content)="https://truthyblue\.github\.io/'
    r'jlpt-max-deck/)'
    r'(?P<path>assets/[^"?#]+)'
    r'(?:\?[^"#]*)?'
    r'(?P<fragment>#[^"]*)?"',
    re.IGNORECASE,
)


class SitePreparationError(RuntimeError):
    """Raised when a Pages artifact cannot be prepared safely."""


def _fingerprint_local_assets(html: str, source: Path) -> str:
    """Replace local asset query strings with their current SHA-256 prefix."""

    def replace_url(match: re.Match[str]) -> str:
        relative_path = match.group("path")
        path_parts = Path(relative_path).parts
        if any(part in {"", ".", ".."} for part in path_parts):
            raise SitePreparationError(
                f"invalid local asset path: {relative_path!r}"
            )
        asset = (source / relative_path).resolve()
        if source not in asset.parents or not asset.is_file():
            raise SitePreparationError(f"local asset is missing: {relative_path}")
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
        fragment = match.group("fragment") or ""
        return (
            f'{match.group("prefix")}{relative_path}?v={digest}'
            f'{fragment}"'
        )

    fingerprinted = LOCAL_ASSET_URL_PATTERN.sub(replace_url, html)
    return ABSOLUTE_SITE_ASSET_URL_PATTERN.sub(replace_url, fingerprinted)


def prepare_site(
    source: Path,
    output: Path,
) -> Path:
    """Copy the static site and fingerprint its local asset URLs."""
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir() or not (source / "index.html").is_file():
        raise SitePreparationError(f"site source is invalid: {source}")
    if output.exists():
        raise SitePreparationError(f"site output already exists: {output}")
    if output == source or source in output.parents:
        raise SitePreparationError("site output must be outside the source tree")

    rendered_pages: dict[str, str] = {}
    for page in sorted(source.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        rendered_pages[page.name] = _fingerprint_local_assets(html, source)
    if not rendered_pages:
        raise SitePreparationError("site has no HTML pages")

    shutil.copytree(source, output)
    for page_name, rendered in rendered_pages.items():
        (output / page_name).write_text(rendered, encoding="utf-8")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "site")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prepare_site(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
