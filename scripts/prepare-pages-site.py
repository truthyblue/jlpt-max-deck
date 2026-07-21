#!/usr/bin/env python3
"""Create a deployable Pages artifact with absolute links and asset hashes."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
REPOSITORY_URL_PLACEHOLDER = "https://github.com/OWNER/REPOSITORY"
SITE_URL_PLACEHOLDER = "https://OWNER.github.io/REPOSITORY"
ANCHOR_PATTERN = re.compile(r"<a\b[^>]*>", re.IGNORECASE)
HREF_PATTERN = re.compile(r'\bhref="([^"]*)"', re.IGNORECASE)
REPOSITORY_PATH_PATTERN = re.compile(
    r'\bdata-repository-path="([^"]*)"', re.IGNORECASE
)
LOCAL_ASSET_URL_PATTERN = re.compile(
    r'(?P<prefix>\b(?:href|src)=")'
    r'(?P<path>assets/[^"?#]+)'
    r'(?:\?[^"#]*)?'
    r'(?P<fragment>#[^"]*)?"',
    re.IGNORECASE,
)
SITE_ASSET_URL_PATTERN = re.compile(
    rf'(?P<prefix>\bcontent="{re.escape(SITE_URL_PLACEHOLDER)}/)'
    r'(?P<path>assets/[^"?#]+)'
    r'(?:\?[^"#]*)?'
    r'(?P<fragment>#[^"]*)?"',
    re.IGNORECASE,
)


class SitePreparationError(RuntimeError):
    """Raised when a Pages artifact cannot be prepared safely."""


def _repository_url(repository: str) -> str:
    parts = repository.split("/")
    if (
        REPOSITORY_PATTERN.fullmatch(repository) is None
        or any(part in {".", ".."} for part in parts)
    ):
        raise SitePreparationError(f"invalid GitHub repository: {repository!r}")
    return f"https://github.com/{repository}"


def _default_site_url(repository: str) -> str:
    _repository_url(repository)
    owner, name = repository.split("/", 1)
    if name.casefold() == f"{owner}.github.io".casefold():
        return f"https://{owner}.github.io"
    return f"https://{owner}.github.io/{name}"


def _validated_site_url(site_url: str) -> str:
    normalized = site_url.strip().rstrip("/")
    parsed = urlsplit(normalized)
    path_parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(part in {".", ".."} for part in path_parts)
    ):
        raise SitePreparationError(f"invalid site URL: {site_url!r}")
    return normalized


def _resolved_link(base_url: str, repository_path: str) -> str:
    parts = repository_path.split("/") if repository_path else []
    if (
        repository_path.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise SitePreparationError(
            f"invalid repository link path: {repository_path!r}"
        )
    return base_url if not repository_path else f"{base_url}/{repository_path}"


def render_index(
    index_html: str,
    repository: str,
    site_url: str | None = None,
) -> str:
    """Resolve repository links, commands and public site URLs."""
    base_url = _repository_url(repository)
    public_site_url = _validated_site_url(
        site_url if site_url is not None else _default_site_url(repository)
    )
    rewritten = 0

    def replace_anchor(match: re.Match[str]) -> str:
        nonlocal rewritten
        anchor = match.group(0)
        repository_path_match = REPOSITORY_PATH_PATTERN.search(anchor)
        if repository_path_match is None:
            return anchor
        href_match = HREF_PATTERN.search(anchor)
        if href_match is None:
            raise SitePreparationError("repository-linked anchor has no href")
        href = _resolved_link(base_url, repository_path_match.group(1))
        rewritten += 1
        return (
            anchor[: href_match.start(1)]
            + href
            + anchor[href_match.end(1) :]
        )

    rendered = ANCHOR_PATTERN.sub(replace_anchor, index_html)
    if rewritten == 0:
        raise SitePreparationError("site has no repository-linked anchors")
    return rendered.replace(REPOSITORY_URL_PLACEHOLDER, base_url).replace(
        SITE_URL_PLACEHOLDER, public_site_url
    )


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
    return SITE_ASSET_URL_PATTERN.sub(replace_url, fingerprinted)


def prepare_site(
    source: Path,
    output: Path,
    repository: str,
    site_url: str | None = None,
) -> Path:
    """Copy the site and resolve repository, canonical and asset URLs."""
    source = source.resolve()
    output = output.resolve()
    public_site_url = _validated_site_url(
        site_url if site_url is not None else _default_site_url(repository)
    )
    if not source.is_dir() or not (source / "index.html").is_file():
        raise SitePreparationError(f"site source is invalid: {source}")
    if output.exists():
        raise SitePreparationError(f"site output already exists: {output}")
    if output == source or source in output.parents:
        raise SitePreparationError("site output must be outside the source tree")

    rendered_pages: dict[str, str] = {}
    for page in sorted(source.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        if (
            REPOSITORY_URL_PLACEHOLDER not in html
            and REPOSITORY_PATH_PATTERN.search(html) is None
        ):
            continue
        rendered_pages[page.name] = render_index(
            _fingerprint_local_assets(html, source), repository, public_site_url
        )
    if not rendered_pages:
        raise SitePreparationError("site has no repository-linked HTML pages")

    rendered_text: dict[str, str] = {}
    for name in ("robots.txt", "sitemap.xml"):
        path = source / name
        if path.is_file():
            rendered_text[name] = path.read_text(encoding="utf-8").replace(
                SITE_URL_PLACEHOLDER, public_site_url
            )

    shutil.copytree(source, output)
    for page_name, rendered in rendered_pages.items():
        (output / page_name).write_text(rendered, encoding="utf-8")
    for name, rendered in rendered_text.items():
        (output / name).write_text(rendered, encoding="utf-8")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "site")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument(
        "--site-url",
        help="deployed HTTPS base URL (defaults to the repository Pages URL)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prepare_site(args.source, args.output, args.repository, args.site_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
