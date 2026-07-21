#!/usr/bin/env python3
"""Validate user-owned source PDFs and produce a portable text-layer receipt."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium

from public_hashing import sha256_file, sha256_json
SOURCE_PROOF_POLICY_VERSION = "local-pdf-text-source-proof-v3"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PublicSourceProofError(RuntimeError):
    """Raised when the user's local source set cannot close."""


@dataclass(frozen=True)
class MatchedPdf:
    record: dict[str, Any]
    path: Path


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicSourceProofError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PublicSourceProofError(f"{label} must be a JSON object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validated_catalog(path: Path) -> dict[str, Any]:
    catalog = _read_json(path, "public source catalog")
    records = catalog.get("pdfs")
    if (
        catalog.get("schema_version") != 1
        or catalog.get("status") != "passed"
        or catalog.get("unresolved") != 0
        or not isinstance(records, list)
        or len(records) != catalog.get("expected_pdf_count")
    ):
        raise PublicSourceProofError("public source catalog is not passed and closed")
    source_ids: set[str] = set()
    hashes: set[str] = set()
    total_bytes = 0
    total_pages = 0
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            raise PublicSourceProofError(f"catalog PDF {index} is not an object")
        source_id = raw.get("source_id")
        digest = raw.get("pdf_sha256")
        expected_bytes = raw.get("expected_bytes")
        expected_pages = raw.get("expected_page_count")
        if (
            not isinstance(source_id, str)
            or not source_id
            or source_id in source_ids
            or not isinstance(digest, str)
            or _SHA256_RE.fullmatch(digest) is None
            or digest in hashes
            or not isinstance(expected_bytes, int)
            or expected_bytes < 1
            or not isinstance(expected_pages, int)
            or expected_pages < 1
            or raw.get("proof_mode") != "text_layer"
            or raw.get("publisher") not in {"dongyang", "gilbut", "hackers"}
            or not isinstance(raw.get("document_role"), str)
            or not raw.get("document_role")
        ):
            raise PublicSourceProofError(f"catalog PDF {index} is invalid")
        source_ids.add(source_id)
        hashes.add(digest)
        total_bytes += expected_bytes
        total_pages += expected_pages
    if (
        total_bytes != catalog.get("expected_total_bytes")
        or total_pages != catalog.get("expected_total_pages")
    ):
        raise PublicSourceProofError("public source catalog totals changed")
    return catalog


def match_public_pdfs(
    pdf_root: Path, catalog_path: Path
) -> tuple[dict[str, Any], list[MatchedPdf]]:
    """Map arbitrary local PDF filenames to the closed catalog by SHA-256."""
    catalog = _validated_catalog(catalog_path)
    if not pdf_root.is_dir():
        raise PublicSourceProofError(f"PDF root is missing: {pdf_root}")
    records = catalog["pdfs"]
    by_hash = {str(record["pdf_sha256"]): record for record in records}
    matched_by_hash: dict[str, MatchedPdf] = {}
    candidates = sorted(
        (path for path in pdf_root.rglob("*") if path.suffix.casefold() == ".pdf"),
        key=lambda path: path.relative_to(pdf_root).as_posix(),
    )
    if not candidates:
        raise PublicSourceProofError(f"PDF root contains no PDFs: {pdf_root}")
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            raise PublicSourceProofError(f"PDF must be a regular file: {path}")
        digest = sha256_file(path)
        record = by_hash.get(digest)
        if record is None:
            raise PublicSourceProofError(f"unsupported PDF hash: {path.name}: {digest}")
        if digest in matched_by_hash:
            raise PublicSourceProofError(
                f"duplicate supported PDF: {record['source_id']}"
            )
        if path.stat().st_size != record["expected_bytes"]:
            raise PublicSourceProofError(
                f"PDF byte count changed: {record['source_id']}"
            )
        document = pdfium.PdfDocument(path)
        try:
            page_count = len(document)
        finally:
            document.close()
        if page_count != record["expected_page_count"]:
            raise PublicSourceProofError(
                f"PDF page count changed: {record['source_id']}"
            )
        matched_by_hash[digest] = MatchedPdf(dict(record), path)
    missing = [
        str(record["source_id"])
        for record in records
        if str(record["pdf_sha256"]) not in matched_by_hash
    ]
    if missing:
        raise PublicSourceProofError(f"required PDFs are missing: {missing}")
    return catalog, [
        matched_by_hash[str(record["pdf_sha256"])] for record in records
    ]


def _text_layer_receipt(matches: Sequence[MatchedPdf]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for match in matches:
        if match.record["proof_mode"] != "text_layer":
            continue
        document = pdfium.PdfDocument(match.path)
        nonempty_pages = 0
        character_count = 0
        digest = hashlib.sha256()
        try:
            for page_index in range(len(document)):
                page = document[page_index]
                text_page = page.get_textpage()
                try:
                    text = text_page.get_text_range()
                finally:
                    text_page.close()
                    page.close()
                normalized = "".join(text.split())
                if normalized:
                    nonempty_pages += 1
                    character_count += len(normalized)
                digest.update(
                    json.dumps(
                        [page_index + 1, normalized],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                digest.update(b"\n")
        finally:
            document.close()
        if nonempty_pages == 0 or character_count == 0:
            raise PublicSourceProofError(
                f"PDF text layer is empty: {match.record['source_id']}"
            )
        records.append(
            {
                "character_count": character_count,
                "document_role": match.record["document_role"],
                "nonempty_page_count": nonempty_pages,
                "page_count": match.record["expected_page_count"],
                "publisher": match.record["publisher"],
                "source_id": match.record["source_id"],
                "text_observation_sha256": digest.hexdigest(),
            }
        )
    publisher_counts = Counter(str(record["publisher"]) for record in records)
    return {
        "document_count": len(records),
        "documents": records,
        "publisher_counts": dict(sorted(publisher_counts.items())),
        "status": "passed",
    }


def build_source_proof(
    *,
    pdf_root: Path,
    catalog_path: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    catalog, matches = match_public_pdfs(pdf_root, catalog_path)
    text_receipt = _text_layer_receipt(matches)
    inventory = [
        {
            "bytes": match.record["expected_bytes"],
            "page_count": match.record["expected_page_count"],
            "pdf_sha256": match.record["pdf_sha256"],
            "source_id": match.record["source_id"],
        }
        for match in matches
    ]
    payload = {
        "catalog_sha256": sha256_file(catalog_path),
        "expected_pdf_count": catalog["expected_pdf_count"],
        "inventory": inventory,
        "policy_version": SOURCE_PROOF_POLICY_VERSION,
        "schema_version": 1,
        "status": "passed",
        "text_layers": text_receipt,
        "unresolved": 0,
    }
    result = {**payload, "payload_hash": sha256_json(payload)}
    if output_path is not None:
        _write_json(output_path, result)
    return result
