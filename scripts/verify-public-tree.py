#!/usr/bin/env python3
"""Fail closed when the public source tree crosses its publication boundary."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = PurePosixPath("config/public-source-files.txt")
RELEASE_PIN = PurePosixPath("config/public-release.json")
RUNTIME_ALLOWLIST = PurePosixPath("config/public-runtime-files.txt")
SOURCE_CATALOG = PurePosixPath("config/public-sources.json")
LAYOUT_REGISTRY = PurePosixPath("config/public-layouts.json")

LOCAL_ONLY_DIRECTORY_NAMES = frozenset(
    {
        ".idea",
        ".jlpt-max-public-venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".vscode",
        "__pycache__",
        "htmlcov",
    }
)
LOCAL_ONLY_FILE_NAMES = frozenset({".coverage", ".DS_Store", "Thumbs.db"})
LOCAL_ONLY_FILE_SUFFIXES = frozenset({".pyc", ".pyo"})

FORBIDDEN_DIRECTORY_NAMES = frozenset(
    {
        ".agents",
        ".codex",
        ".omx",
        "build",
        "data",
        "prompts",
        "tmp",
        "tools",
    }
)
FORBIDDEN_SUFFIXES = frozenset(
    {".apkg", ".mp3", ".pdf", ".sqlite", ".sqlite3", ".wav", ".zip"}
)
PUBLIC_AUDIO_DEMO_PATHS = frozenset(
    {
        "site/assets/demo-dasu-example-2.mp3",
        "site/assets/demo-dasu-example-3.mp3",
        "site/assets/demo-dasu-example.mp3",
        "site/assets/demo-dasu-word.mp3",
    }
)
SCAN_ROOTS = frozenset(
    {".github", "config", "docs", "scripts", "site", "src", "test"}
)
ROOT_SCAN_FILES = frozenset(
    {
        ".gitattributes",
        ".gitignore",
        "CONTRIBUTING.md",
        "LICENSE",
        "NOTICE",
        "README.md",
        "SECURITY.md",
        "pyproject.toml",
        "uv.lock",
    }
)
SCANNED_SUFFIXES = frozenset(
    {
        ".css",
        ".html",
        ".json",
        ".jsonl",
        ".md",
        ".ps1",
        ".py",
        ".sh",
        ".svg",
        ".toml",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)
ABSOLUTE_USER_PATH_PATTERNS = (
    re.compile("/" + "Users/"),
    re.compile(r"[A-Za-z]:[\\/]" + r"Users[\\/]", re.IGNORECASE),
    re.compile(r"/" + r"home/[^/\s]+/"),
)
PUBLIC_PATH_EXAMPLES = (r"C:" + r"\Users\me\Documents\jlpt-pdfs",)
PUBLIC_PATH_EXAMPLE_ROOTS = frozenset({"README.md", "docs", "site"})
# These are assembled so the verifier can scan its own source without carrying
# the private identifiers as contiguous publication candidates.
FORBIDDEN_TEXT_FRAGMENTS = (
    "data/sources/" + "personal",
    "data/" + "overrides",
    "ocr_" + "darakwon",
    "vision_" + "ocr",
    "run_" + "codex_exec",
    "llm_" + "example_provider",
    "private " + "authoring",
    "authoring-" + "only",
)

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
RELEASE_PIN_KEYS = frozenset(
    {
        "archive_bytes",
        "archive_sha256",
        "bundle_manifest_sha256",
        "payload_hash",
        "policy_version",
        "public_builder_source_hash",
        "schema_version",
        "status",
        "unresolved",
    }
)
SOURCE_CATALOG_KEYS = frozenset(
    {
        "expected_pdf_count",
        "expected_total_bytes",
        "expected_total_pages",
        "pdfs",
        "policy_version",
        "schema_version",
        "source_set_id",
        "status",
        "unresolved",
    }
)
SOURCE_RECORD_KEYS = frozenset(
    {
        "document_role",
        "expected_bytes",
        "expected_page_count",
        "level",
        "pdf_sha256",
        "proof_mode",
        "publisher",
        "source_id",
    }
)
LAYOUT_REGISTRY_KEYS = frozenset(
    {"documents", "layout_families", "policy_version", "schema_version"}
)
LAYOUT_DOCUMENT_KEYS = frozenset(
    {"expected_page_count", "page_rules", "pdf_sha256", "source_id"}
)
LAYOUT_SPEC_KEYS = frozenset(
    {
        "content_class",
        "creates_canonical_candidates",
        "extraction_method",
        "inspection_bbox",
        "transition_group",
    }
)
PAGE_RULE_REQUIRED_KEYS = frozenset({"end_page", "layout_id", "start_page"})
SUPPORTED_LAYOUTS = frozenset(
    {
        "dongyang_synonym_reference",
        "dongyang_vocab_two_column",
        "hackers_calendar_grid",
        "hackers_counter_matrix",
        "hackers_latest_vocabulary",
        "hackers_usage_lexemes",
        "hackers_usage_lexemes_to_phrases",
        "hackers_usage_lexemes_to_vocab",
        "hackers_usage_phrases",
        "hackers_usage_phrases_to_vocab",
        "hackers_vocab_example_column",
        "hackers_vocab_to_usage_lexemes",
        "hackers_vocab_two_column",
    }
)
NON_CANDIDATE_LAYOUTS = frozenset(
    {"hackers_calendar_grid", "hackers_counter_matrix"}
)
EXPECTED_PUBLIC_SOURCE_IDS = frozenset(
    [f"dongyang-n{level}-vocabulary" for level in range(1, 6)]
    + [
        f"hackers-n{level}-{role}"
        for level in range(1, 6)
        for role in ("latest", "wordbook")
    ]
    + ["ilsang-muutta-lower", "ilsang-muutta-upper"]
)


class PublicTreeError(RuntimeError):
    """Raised when the repository is not an exact, public-safe source tree."""


def _relative_text(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _read_path_list(
    root: Path,
    relative: PurePosixPath,
    *,
    lists_itself: bool,
) -> tuple[str, ...]:
    path = root / relative
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PublicTreeError(f"cannot read {relative}: {exc}") from exc
    entries = tuple(
        line.strip()
        for line in raw_lines
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not entries:
        raise PublicTreeError(f"{relative} is empty")
    if len(entries) != len(set(entries)):
        raise PublicTreeError(f"{relative} contains duplicate paths")
    if entries != tuple(sorted(entries)):
        raise PublicTreeError(f"{relative} must be sorted")
    for entry in entries:
        candidate = PurePosixPath(entry)
        if (
            entry != candidate.as_posix()
            or candidate.is_absolute()
            or ".." in candidate.parts
            or "\\" in entry
        ):
            raise PublicTreeError(f"unsafe allowlist path: {entry!r}")
    if lists_itself and relative.as_posix() not in entries:
        raise PublicTreeError(f"{relative} must list itself")
    return entries


def read_allowlist(root: Path) -> tuple[str, ...]:
    return _read_path_list(root, ALLOWLIST, lists_itself=True)


def read_runtime_allowlist(root: Path) -> tuple[str, ...]:
    return _read_path_list(root, RUNTIME_ALLOWLIST, lists_itself=False)


def _git_root(root: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    resolved = Path(result.stdout.strip()).resolve()
    return resolved if resolved == root.resolve() else None


def git_inventory(root: Path) -> tuple[str, ...] | None:
    if _git_root(root) is None:
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise PublicTreeError(f"cannot inventory tracked files: {exc}") from exc
    return tuple(
        sorted(
            item.decode("utf-8")
            for item in result.stdout.split(b"\0")
            if item
        )
    )


def _is_local_only_file(name: str) -> bool:
    return (
        name in LOCAL_ONLY_FILE_NAMES
        or Path(name).suffix.casefold() in LOCAL_ONLY_FILE_SUFFIXES
        or name.startswith(".coverage.")
    )


def _walkable_directory_names(dir_names: Iterable[str]) -> list[str]:
    return sorted(
        name
        for name in dir_names
        if name != ".git" and name not in LOCAL_ONLY_DIRECTORY_NAMES
    )


def _raise_walk_error(error: OSError) -> None:
    raise PublicTreeError(f"cannot inspect public tree: {error}") from error


def filesystem_inventory(root: Path) -> tuple[str, ...]:
    files: list[str] = []
    for current, dir_names, file_names in os.walk(
        root, onerror=_raise_walk_error, followlinks=False
    ):
        current_path = Path(current)
        dir_names[:] = _walkable_directory_names(dir_names)
        for name in dir_names:
            path = current_path / name
            if path.is_symlink():
                files.append(_relative_text(path, root))
        for name in sorted(file_names):
            if _is_local_only_file(name):
                continue
            path = current_path / name
            if _relative_text(path, root) == ".git":
                continue
            files.append(_relative_text(path, root))
    return tuple(sorted(files))


def public_inventory(root: Path) -> tuple[tuple[str, ...], str]:
    files = filesystem_inventory(root)
    source = "git index + filesystem" if git_inventory(root) is not None else "filesystem"
    return files, source


def verify_public_inventories(
    root: Path, allowlisted: Iterable[str]
) -> tuple[tuple[str, ...], str]:
    expected = tuple(allowlisted)
    files = filesystem_inventory(root)
    verify_exact_inventory(expected, files, source="filesystem")
    tracked = git_inventory(root)
    if tracked is None:
        return files, "filesystem"
    verify_exact_inventory(expected, tracked, source="git index")
    return files, "git index + filesystem"


def verify_directory_tree(root: Path) -> None:
    for current, dir_names, unused_file_names in os.walk(
        root, onerror=_raise_walk_error, followlinks=False
    ):
        current_path = Path(current)
        dir_names[:] = _walkable_directory_names(dir_names)
        for name in dir_names:
            path = current_path / name
            relative = _relative_text(path, root)
            if path.is_symlink():
                raise PublicTreeError(f"symlinks are forbidden: {relative}")
            if name in FORBIDDEN_DIRECTORY_NAMES:
                raise PublicTreeError(f"forbidden directory in public tree: {relative}")


def verify_exact_inventory(
    allowlisted: Iterable[str], actual: Iterable[str], *, source: str
) -> None:
    expected_set = set(allowlisted)
    actual_set = set(actual)
    missing = sorted(expected_set - actual_set)
    unexpected = sorted(actual_set - expected_set)
    if missing or unexpected:
        details: list[str] = [f"public tree differs from allowlist ({source})"]
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unexpected:
            details.append("unexpected: " + ", ".join(unexpected))
        raise PublicTreeError("; ".join(details))


def verify_paths(root: Path, relative_paths: Iterable[str]) -> None:
    for relative in relative_paths:
        pure = PurePosixPath(relative)
        if any(part in FORBIDDEN_DIRECTORY_NAMES for part in pure.parts[:-1]):
            raise PublicTreeError(f"forbidden directory in public tree: {relative}")
        suffix = pure.suffix.lower()
        if suffix in FORBIDDEN_SUFFIXES and not (
            suffix == ".mp3" and relative in PUBLIC_AUDIO_DEMO_PATHS
        ):
            raise PublicTreeError(f"forbidden artifact in public tree: {relative}")
        path = root / pure
        if path.is_symlink():
            raise PublicTreeError(f"symlinks are forbidden: {relative}")
        if not path.is_file():
            raise PublicTreeError(f"tracked path is not a regular file: {relative}")


def _scan_candidate(relative: str) -> bool:
    pure = PurePosixPath(relative)
    return (
        relative in ROOT_SCAN_FILES
        or (
            bool(pure.parts)
            and pure.parts[0] in SCAN_ROOTS
            and pure.suffix.lower() in SCANNED_SUFFIXES
        )
    )


def scan_private_tokens(root: Path, relative_paths: Iterable[str]) -> None:
    for relative in relative_paths:
        if not _scan_candidate(relative):
            continue
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise PublicTreeError(f"cannot scan text file {relative}: {exc}") from exc
        scanned_text = text
        relative_parts = PurePosixPath(relative).parts
        if relative_parts and relative_parts[0] in PUBLIC_PATH_EXAMPLE_ROOTS:
            for example in PUBLIC_PATH_EXAMPLES:
                scanned_text = scanned_text.replace(example, "<documented-public-path>")
        lowered = scanned_text.casefold()
        for fragment in FORBIDDEN_TEXT_FRAGMENTS:
            if fragment.casefold() in lowered:
                raise PublicTreeError(
                    f"non-public identifier found in {relative}"
                )
        if any(
            pattern.search(scanned_text) for pattern in ABSOLUTE_USER_PATH_PATTERNS
        ):
            raise PublicTreeError(f"absolute user path found in {relative}")


def _read_json_object(
    root: Path, relative: PurePosixPath, *, label: str
) -> dict[str, object]:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicTreeError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PublicTreeError(f"{label} must contain a JSON object")
    return value


def _sha256_json(value: object) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _is_exact_int(value: object, expected: int) -> bool:
    return type(value) is int and value == expected


def validate_release_pin_document(root: Path) -> dict[str, object]:
    pin = _read_json_object(root, RELEASE_PIN, label="public release pin")
    payload = {key: value for key, value in pin.items() if key != "payload_hash"}
    digests = (
        pin.get("archive_sha256"),
        pin.get("bundle_manifest_sha256"),
        pin.get("public_builder_source_hash"),
        pin.get("payload_hash"),
    )
    if (
        set(pin) != RELEASE_PIN_KEYS
        or not _is_exact_int(pin.get("schema_version"), 1)
        or pin.get("policy_version") != "public-release-pin-v1"
        or pin.get("status") != "passed"
        or not _is_exact_int(pin.get("unresolved"), 0)
        or not _is_positive_int(pin.get("archive_bytes"))
        or any(
            not isinstance(digest, str)
            or SHA256_PATTERN.fullmatch(digest) is None
            for digest in digests
        )
        or pin.get("payload_hash") != _sha256_json(payload)
    ):
        raise PublicTreeError("public release pin is not passed and closed")
    return pin


def _source_identity(
    source_id: str,
) -> tuple[str, str, str | None] | None:
    dongyang = re.fullmatch(r"dongyang-n([1-5])-vocabulary", source_id)
    if dongyang is not None:
        return "dongyang", "vocabulary", f"N{dongyang.group(1)}"
    hackers = re.fullmatch(r"hackers-n([1-5])-(latest|wordbook)", source_id)
    if hackers is not None:
        role = "latest_vocabulary" if hackers.group(2) == "latest" else "wordbook"
        return "hackers", role, f"N{hackers.group(1)}"
    if source_id in {"ilsang-muutta-lower", "ilsang-muutta-upper"}:
        return "gilbut", "kanji_reference", None
    return None


def validate_public_source_catalog(root: Path) -> dict[str, object]:
    catalog = _read_json_object(root, SOURCE_CATALOG, label="public source catalog")
    records = catalog.get("pdfs")
    if (
        set(catalog) != SOURCE_CATALOG_KEYS
        or not _is_exact_int(catalog.get("schema_version"), 1)
        or catalog.get("policy_version") != "public-text-source-possession-v2"
        or catalog.get("source_set_id") != "public-user-pdfs-v2"
        or catalog.get("status") != "passed"
        or not _is_exact_int(catalog.get("unresolved"), 0)
        or not _is_positive_int(catalog.get("expected_pdf_count"))
        or not _is_positive_int(catalog.get("expected_total_bytes"))
        or not _is_positive_int(catalog.get("expected_total_pages"))
        or not isinstance(records, list)
        or len(records) != catalog.get("expected_pdf_count")
    ):
        raise PublicTreeError("public source catalog is not passed and closed")

    source_ids: set[str] = set()
    hashes: set[str] = set()
    total_bytes = 0
    total_pages = 0
    for index, raw in enumerate(records):
        if not isinstance(raw, dict) or set(raw) != SOURCE_RECORD_KEYS:
            raise PublicTreeError(f"public source catalog PDF {index} schema changed")
        source_id = raw.get("source_id")
        digest = raw.get("pdf_sha256")
        expected_bytes = raw.get("expected_bytes")
        expected_pages = raw.get("expected_page_count")
        identity = _source_identity(source_id) if isinstance(source_id, str) else None
        if (
            identity is None
            or source_id in source_ids
            or not isinstance(digest, str)
            or SHA256_PATTERN.fullmatch(digest) is None
            or digest in hashes
            or not _is_positive_int(expected_bytes)
            or not _is_positive_int(expected_pages)
            or raw.get("proof_mode") != "text_layer"
            or (raw.get("publisher"), raw.get("document_role"), raw.get("level"))
            != identity
        ):
            raise PublicTreeError(f"public source catalog PDF {index} is invalid")
        assert isinstance(source_id, str)
        assert isinstance(digest, str)
        assert type(expected_bytes) is int
        assert type(expected_pages) is int
        source_ids.add(source_id)
        hashes.add(digest)
        total_bytes += expected_bytes
        total_pages += expected_pages
    if (
        source_ids != EXPECTED_PUBLIC_SOURCE_IDS
        or total_bytes != catalog.get("expected_total_bytes")
        or total_pages != catalog.get("expected_total_pages")
    ):
        raise PublicTreeError("public source catalog totals or source set changed")
    return catalog


def _expanded_pages(rule: dict[str, object]) -> list[int]:
    start_page = rule.get("start_page")
    end_page = rule.get("end_page")
    parity = rule.get("parity")
    if (
        type(start_page) is not int
        or type(end_page) is not int
        or start_page < 1
        or end_page < start_page
        or parity not in {None, "odd", "even"}
    ):
        raise PublicTreeError(f"invalid public page rule: {rule}")
    pages = list(range(start_page, end_page + 1))
    if parity == "odd":
        return [page for page in pages if page % 2 == 1]
    if parity == "even":
        return [page for page in pages if page % 2 == 0]
    return pages


def validate_public_layout_registry(
    root: Path, catalog: dict[str, object]
) -> dict[str, object]:
    registry = _read_json_object(root, LAYOUT_REGISTRY, label="public layout registry")
    documents = registry.get("documents")
    layout_families = registry.get("layout_families")
    if (
        set(registry) != LAYOUT_REGISTRY_KEYS
        or not _is_exact_int(registry.get("schema_version"), 1)
        or registry.get("policy_version") != "public-hd-text-layouts-v1"
        or not isinstance(documents, list)
        or not documents
        or not isinstance(layout_families, dict)
        or not layout_families
    ):
        raise PublicTreeError("public layout registry is invalid")

    family_ids = set(layout_families)
    if not family_ids <= SUPPORTED_LAYOUTS:
        raise PublicTreeError(
            f"unsupported public layouts: {sorted(family_ids - SUPPORTED_LAYOUTS)}"
        )
    for layout_id, raw_spec in layout_families.items():
        if not isinstance(layout_id, str) or not isinstance(raw_spec, dict):
            raise PublicTreeError(f"public layout spec is invalid: {layout_id}")
        bbox = raw_spec.get("inspection_bbox")
        expected_candidates = layout_id not in NON_CANDIDATE_LAYOUTS
        if (
            set(raw_spec) != LAYOUT_SPEC_KEYS
            or raw_spec.get("extraction_method") != "text_geometry"
            or raw_spec.get("content_class")
            not in {"vocabulary", "structured_reference"}
            or raw_spec.get("creates_canonical_candidates") is not expected_candidates
            or not isinstance(raw_spec.get("transition_group"), str)
            or not str(raw_spec.get("transition_group")).strip()
            or not isinstance(bbox, list)
            or len(bbox) != 4
            or any(type(value) not in {int, float} for value in bbox)
            or not (
                0.0 <= float(bbox[0]) < float(bbox[2]) <= 1.0
                and 0.0 <= float(bbox[1]) < float(bbox[3]) <= 1.0
            )
        ):
            raise PublicTreeError(f"public layout spec is invalid: {layout_id}")

    raw_catalog_records = catalog.get("pdfs")
    if not isinstance(raw_catalog_records, list):
        raise PublicTreeError("public source catalog records are unavailable")
    catalog_records = {
        str(record["source_id"]): record
        for record in raw_catalog_records
        if isinstance(record, dict) and record.get("publisher") != "gilbut"
    }
    source_ids: set[str] = set()
    hashes: set[str] = set()
    referenced_layouts: set[str] = set()
    for index, raw_document in enumerate(documents):
        if not isinstance(raw_document, dict) or set(raw_document) != LAYOUT_DOCUMENT_KEYS:
            raise PublicTreeError(f"public layout document {index} schema changed")
        source_id = raw_document.get("source_id")
        digest = raw_document.get("pdf_sha256")
        expected_pages = raw_document.get("expected_page_count")
        page_rules = raw_document.get("page_rules")
        source_record = catalog_records.get(str(source_id))
        if (
            not isinstance(source_id, str)
            or source_record is None
            or source_id in source_ids
            or not isinstance(digest, str)
            or SHA256_PATTERN.fullmatch(digest) is None
            or digest in hashes
            or digest != source_record.get("pdf_sha256")
            or not _is_positive_int(expected_pages)
            or expected_pages != source_record.get("expected_page_count")
            or not isinstance(page_rules, list)
            or not page_rules
        ):
            raise PublicTreeError(f"public layout document is invalid: {source_id or index}")
        assert isinstance(source_id, str)
        assert isinstance(digest, str)
        assert type(expected_pages) is int
        assert isinstance(page_rules, list)
        assigned_pages: set[int] = set()
        for raw_rule in page_rules:
            if not isinstance(raw_rule, dict) or frozenset(raw_rule) not in {
                PAGE_RULE_REQUIRED_KEYS,
                PAGE_RULE_REQUIRED_KEYS | {"parity"},
            }:
                raise PublicTreeError(f"public page rule schema changed: {source_id}")
            layout_id = raw_rule.get("layout_id")
            if not isinstance(layout_id, str) or layout_id not in layout_families:
                raise PublicTreeError(
                    f"public page rule uses unknown layout: {source_id}:{layout_id}"
                )
            pages = _expanded_pages(raw_rule)
            if not pages or pages[-1] > expected_pages:
                raise PublicTreeError(
                    f"public page rule escapes PDF bounds: {source_id}:{layout_id}"
                )
            overlap = assigned_pages.intersection(pages)
            if overlap:
                raise PublicTreeError(
                    f"public page rules overlap: {source_id}:{sorted(overlap)}"
                )
            assigned_pages.update(pages)
            referenced_layouts.add(layout_id)
        source_ids.add(source_id)
        hashes.add(digest)
    if source_ids != set(catalog_records):
        raise PublicTreeError("public layout documents differ from the source catalog")
    if family_ids != referenced_layouts:
        raise PublicTreeError("public layout registry contains unused layout families")
    return registry


def validate_public_contract_files(root: Path) -> None:
    catalog = validate_public_source_catalog(root)
    validate_public_layout_registry(root, catalog)


def _compute_public_build_source_hash(root: Path) -> str:
    source_root = root / "src"
    sys.path.insert(0, str(source_root))
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.import_module("public_build_contract")
        compute = getattr(module, "public_build_source_hash", None)
        if not callable(compute):
            raise PublicTreeError("public build hash function is unavailable")
        value = compute(root)
    except PublicTreeError:
        raise
    except Exception as exc:
        raise PublicTreeError(f"cannot compute public build source hash: {exc}") from exc
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        sys.path.pop(0)
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise PublicTreeError("public build source hash is invalid")
    return value


def verify_runtime_allowlist(root: Path) -> tuple[str, ...]:
    """Bind the exportable runtime manifest to the executable source contract."""
    entries = read_runtime_allowlist(root)
    source_root = root / "src"
    sys.path.insert(0, str(source_root))
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.import_module("public_build_contract")
        declared = getattr(module, "PUBLIC_BUILD_FILES", None)
    except Exception as exc:
        raise PublicTreeError(f"cannot load public runtime contract: {exc}") from exc
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        sys.path.pop(0)
    if not isinstance(declared, tuple) or entries != declared:
        raise PublicTreeError(
            "config/public-runtime-files.txt differs from PUBLIC_BUILD_FILES"
        )
    verify_paths(root, entries)
    return entries


def verify_release_pin(
    root: Path,
    *,
    compute_source_hash: Callable[[Path], str] = _compute_public_build_source_hash,
    allow_source_hash_drift: bool = False,
) -> str:
    """Validate the release pin and bind it to the current builder by default.

    Contributor checks may allow only the final builder-source hash comparison
    to drift. The pin document itself is always validated first.
    """
    pin = validate_release_pin_document(root)
    expected = pin.get("public_builder_source_hash")
    if not isinstance(expected, str):
        raise PublicTreeError(f"{RELEASE_PIN} lacks a valid public builder source hash")
    actual = compute_source_hash(root)
    if actual != expected and not allow_source_hash_drift:
        raise PublicTreeError(
            "public build source hash differs from config/public-release.json"
        )
    return actual


def verify(
    root: Path, *, allow_release_pin_drift: bool = False
) -> tuple[int, str, str]:
    root = root.resolve()
    allowlisted = read_allowlist(root)
    verify_directory_tree(root)
    actual, source = verify_public_inventories(root, allowlisted)
    verify_paths(root, actual)
    scan_private_tokens(root, actual)
    validate_public_contract_files(root)
    verify_runtime_allowlist(root)
    source_hash = verify_release_pin(
        root, allow_source_hash_drift=allow_release_pin_drift
    )
    return len(actual), source, source_hash


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the exact public source allowlist and publication boundary."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="public repository root (defaults to this script's repository)",
    )
    parser.add_argument(
        "--allow-release-pin-drift",
        action="store_true",
        help=(
            "allow only the current builder source hash to differ from the "
            "valid release pin (for contributor checks)"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        count, source, source_hash = verify(
            args.root,
            allow_release_pin_drift=args.allow_release_pin_drift,
        )
    except PublicTreeError as exc:
        print(f"public tree verification failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"public tree verified: {count} files from {source}; "
        f"builder source {source_hash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
