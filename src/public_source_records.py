#!/usr/bin/env python3
"""Extract public lexical source records from user-owned text-layer PDFs."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pdfplumber

from public_hashing import sha256_file, sha256_json
from public_source_proof import MatchedPdf
from public_text_layouts import (
    HACKERS_USAGE_LAYOUTS,
    TextLayoutError,
    parse_dongyang_synonym_page,
    parse_dongyang_vocab_page,
    parse_hackers_latest_vocabulary_page,
    parse_hackers_structured_page,
    parse_hackers_usage_page,
    parse_hackers_vocab_page,
)


PUBLIC_SOURCE_RECORD_POLICY_VERSION = "public-hd-source-records-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LEVEL_RE = re.compile(r"-(?:n|N)([1-5])(?:-|$)")
_SUPPORTED_PUBLISHERS = frozenset({"dongyang", "hackers"})
_IGNORED_PUBLISHERS = frozenset({"gilbut"})
_VOCAB_LAYOUTS = frozenset(
    {
        "dongyang_vocab_two_column",
        "dongyang_synonym_reference",
        "hackers_latest_vocabulary",
        "hackers_vocab_example_column",
        "hackers_vocab_two_column",
    }
)
HACKERS_STRUCTURED_LAYOUTS = frozenset(
    {"hackers_calendar_grid", "hackers_counter_matrix"}
)
_SUPPORTED_LAYOUTS = _VOCAB_LAYOUTS | HACKERS_USAGE_LAYOUTS | HACKERS_STRUCTURED_LAYOUTS


class PublicSourceRecordError(RuntimeError):
    """Raised when the public source-record extraction cannot close."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicSourceRecordError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PublicSourceRecordError(f"{label} must be a JSON object")
    return value


def _expanded_pages(rule: Mapping[str, Any]) -> list[int]:
    """Expand one validated inclusive page rule in source order."""
    start_page = rule.get("start_page")
    end_page = rule.get("end_page")
    parity = rule.get("parity")
    if (
        not isinstance(start_page, int)
        or not isinstance(end_page, int)
        or start_page < 1
        or end_page < start_page
        or parity not in {None, "odd", "even"}
    ):
        raise PublicSourceRecordError(f"invalid public page rule: {dict(rule)}")
    pages = list(range(start_page, end_page + 1))
    if parity == "odd":
        return [page for page in pages if page % 2 == 1]
    if parity == "even":
        return [page for page in pages if page % 2 == 0]
    return pages


def _validated_layout_registry(path: Path) -> dict[str, Any]:
    registry = _read_json(path, "public layout registry")
    documents = registry.get("documents")
    layout_families = registry.get("layout_families")
    if (
        registry.get("schema_version") != 1
        or not isinstance(registry.get("policy_version"), str)
        or not registry.get("policy_version")
        or not isinstance(documents, list)
        or not documents
        or not isinstance(layout_families, dict)
        or not layout_families
    ):
        raise PublicSourceRecordError("public layout registry is invalid")

    family_ids = set(layout_families)
    if not family_ids <= _SUPPORTED_LAYOUTS:
        unsupported = sorted(family_ids - _SUPPORTED_LAYOUTS)
        raise PublicSourceRecordError(f"unsupported public layouts: {unsupported}")
    for layout_id, raw_spec in layout_families.items():
        if not isinstance(raw_spec, dict):
            raise PublicSourceRecordError(f"layout spec is not an object: {layout_id}")
        bbox = raw_spec.get("inspection_bbox")
        if (
            raw_spec.get("extraction_method") != "text_geometry"
            or raw_spec.get("content_class")
            not in {"vocabulary", "structured_reference"}
            or not isinstance(raw_spec.get("creates_canonical_candidates"), bool)
            or not isinstance(bbox, list)
            or len(bbox) != 4
            or any(not isinstance(value, (int, float)) for value in bbox)
            or not (
                0.0 <= float(bbox[0]) < float(bbox[2]) <= 1.0
                and 0.0 <= float(bbox[1]) < float(bbox[3]) <= 1.0
            )
        ):
            raise PublicSourceRecordError(f"invalid public layout spec: {layout_id}")
        expected_candidates = layout_id not in HACKERS_STRUCTURED_LAYOUTS
        if raw_spec["creates_canonical_candidates"] is not expected_candidates:
            raise PublicSourceRecordError(
                f"candidate policy changed for public layout: {layout_id}"
            )

    source_ids: set[str] = set()
    hashes: set[str] = set()
    referenced_layouts: set[str] = set()
    for index, raw_document in enumerate(documents):
        if not isinstance(raw_document, dict):
            raise PublicSourceRecordError(
                f"public layout document {index} is not an object"
            )
        source_id = raw_document.get("source_id")
        digest = raw_document.get("pdf_sha256")
        expected_pages = raw_document.get("expected_page_count")
        page_rules = raw_document.get("page_rules")
        if (
            not isinstance(source_id, str)
            or not source_id.startswith(("dongyang-", "hackers-"))
            or _LEVEL_RE.search(source_id) is None
            or source_id in source_ids
            or not isinstance(digest, str)
            or _SHA256_RE.fullmatch(digest) is None
            or digest in hashes
            or not isinstance(expected_pages, int)
            or expected_pages < 1
            or not isinstance(page_rules, list)
            or not page_rules
        ):
            raise PublicSourceRecordError(
                f"invalid public layout document: {source_id or index}"
            )
        assigned_pages: set[int] = set()
        for raw_rule in page_rules:
            if not isinstance(raw_rule, dict):
                raise PublicSourceRecordError(
                    f"page rule is not an object: {source_id}"
                )
            layout_id = raw_rule.get("layout_id")
            if not isinstance(layout_id, str) or layout_id not in layout_families:
                raise PublicSourceRecordError(
                    f"page rule uses unknown public layout: {source_id}:{layout_id}"
                )
            pages = _expanded_pages(raw_rule)
            if not pages or pages[-1] > expected_pages:
                raise PublicSourceRecordError(
                    f"page rule escapes PDF bounds: {source_id}:{layout_id}"
                )
            overlap = assigned_pages.intersection(pages)
            if overlap:
                raise PublicSourceRecordError(
                    f"public page rules overlap: {source_id}:{sorted(overlap)}"
                )
            assigned_pages.update(pages)
            referenced_layouts.add(layout_id)
        source_ids.add(source_id)
        hashes.add(digest)
    if family_ids != referenced_layouts:
        raise PublicSourceRecordError(
            "public layout registry contains unused layout families"
        )
    return registry


def _level_from_source_id(source_id: str) -> int:
    match = _LEVEL_RE.search(source_id)
    if match is None:
        raise PublicSourceRecordError(f"source ID lacks JLPT level: {source_id}")
    return int(match.group(1))


def _parse_page(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    layout_spec: Mapping[str, Any],
    level: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    kwargs = {
        "source_id": source_id,
        "pdf_sha256": pdf_sha256,
        "page_number": page_number,
        "layout_id": layout_id,
        "layout_spec": layout_spec,
    }
    if layout_id in {"hackers_vocab_example_column", "hackers_vocab_two_column"}:
        return parse_hackers_vocab_page(page, level=level, **kwargs)
    if layout_id == "hackers_latest_vocabulary":
        return parse_hackers_latest_vocabulary_page(page, level=level, **kwargs)
    if layout_id == "dongyang_vocab_two_column":
        return parse_dongyang_vocab_page(page, level=level, **kwargs)
    if layout_id == "dongyang_synonym_reference":
        return parse_dongyang_synonym_page(page, level=level, **kwargs)
    if layout_id in HACKERS_USAGE_LAYOUTS:
        return parse_hackers_usage_page(page, level=level, **kwargs)
    if layout_id in HACKERS_STRUCTURED_LAYOUTS:
        cells, reconciliation = parse_hackers_structured_page(page, **kwargs)
        return cells, [], reconciliation
    raise PublicSourceRecordError(f"no public parser for layout: {layout_id}")


def _validated_matches(
    matches: Sequence[MatchedPdf], registry: Mapping[str, Any]
) -> dict[str, MatchedPdf]:
    by_source_id: dict[str, MatchedPdf] = {}
    for match in matches:
        source_id = match.record.get("source_id")
        publisher = match.record.get("publisher")
        if (
            not isinstance(source_id, str)
            or not source_id
            or not isinstance(publisher, str)
        ):
            raise PublicSourceRecordError("matched PDF has invalid source metadata")
        if publisher in _IGNORED_PUBLISHERS:
            continue
        if publisher not in _SUPPORTED_PUBLISHERS:
            raise PublicSourceRecordError(
                f"matched PDF has unsupported publisher: {source_id}:{publisher}"
            )
        if source_id in by_source_id:
            raise PublicSourceRecordError(f"duplicate matched source: {source_id}")
        by_source_id[source_id] = match

    documents = registry["documents"]
    expected_ids = {str(document["source_id"]) for document in documents}
    if set(by_source_id) != expected_ids:
        missing = sorted(expected_ids - set(by_source_id))
        unexpected = sorted(set(by_source_id) - expected_ids)
        raise PublicSourceRecordError(
            f"public layout source set changed: missing={missing} unexpected={unexpected}"
        )
    return by_source_id


def _validated_page_output(
    *,
    source_id: str,
    publisher: str,
    document_role: str,
    level: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    creates_candidates: bool,
    cells: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    reconciliation: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if reconciliation.get("status") != "passed":
        raise PublicSourceRecordError(
            f"page reconciliation failed: {source_id}:p{page_number:04d}"
        )
    if reconciliation.get("observed_cells") != len(cells):
        raise PublicSourceRecordError(
            f"page cell count changed: {source_id}:p{page_number:04d}"
        )
    if not creates_candidates and candidates:
        raise PublicSourceRecordError(
            f"structured layout promoted candidates: {source_id}:p{page_number:04d}"
        )

    page_cells: list[dict[str, Any]] = []
    cell_ids: set[str] = set()
    for raw_cell in cells:
        cell = dict(raw_cell)
        cell_id = cell.get("cell_id")
        if (
            not isinstance(cell_id, str)
            or not cell_id
            or cell_id in cell_ids
            or cell.get("source_id") != source_id
            or cell.get("pdf_sha256") != pdf_sha256
            or cell.get("page") != page_number
            or cell.get("layout_id") != layout_id
        ):
            raise PublicSourceRecordError(
                f"invalid page cell: {source_id}:p{page_number:04d}:{cell_id}"
            )
        cell_ids.add(cell_id)
        page_cells.append(cell)

    page_records: list[dict[str, Any]] = []
    source_record_ids: set[str] = set()
    for raw_candidate in candidates:
        candidate = dict(raw_candidate)
        candidate_id = candidate.get("candidate_id")
        source_cell_ids = candidate.get("source_cell_ids")
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or candidate_id in source_record_ids
            or candidate.get("source_id") != source_id
            or candidate.get("pdf_sha256") != pdf_sha256
            or candidate.get("page") != page_number
            or candidate.get("layout_id") != layout_id
            or not isinstance(source_cell_ids, dict)
            or not source_cell_ids
            or any(
                not isinstance(cell_id, str) or cell_id not in cell_ids
                for cell_id in source_cell_ids.values()
            )
        ):
            raise PublicSourceRecordError(
                f"invalid source record: {source_id}:p{page_number:04d}:{candidate_id}"
            )
        source_record_ids.add(candidate_id)
        candidate["document_role"] = document_role
        candidate["level"] = level
        candidate["publisher"] = publisher
        candidate["source_record_id"] = candidate_id
        page_records.append(candidate)
    return page_cells, page_records


def extract_public_source_records(
    matches: Sequence[MatchedPdf],
    layout_registry_path: Path,
) -> dict[str, Any]:
    """Return deterministic source-record and cell maps for Dongyang/Hackers.

    ``matches`` is intended to be the closed result of ``match_public_pdfs``.
    Gilbut reference PDFs are ignored here and handled by the public kanji
    extractor; any other publisher or any missing Dongyang/Hackers PDF fails
    closed.
    """
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    registry = _validated_layout_registry(layout_registry_path)
    matches_by_source_id = _validated_matches(matches, registry)

    source_records_by_id: dict[str, dict[str, Any]] = {}
    cells_by_id: dict[str, dict[str, Any]] = {}
    page_receipts: list[dict[str, Any]] = []
    document_receipts: list[dict[str, Any]] = []
    for raw_document in registry["documents"]:
        document = dict(raw_document)
        source_id = str(document["source_id"])
        expected_digest = str(document["pdf_sha256"])
        expected_page_count = int(document["expected_page_count"])
        match = matches_by_source_id[source_id]
        publisher = match.record.get("publisher")
        document_role = match.record.get("document_role")
        if (
            match.record.get("pdf_sha256") != expected_digest
            or match.record.get("expected_page_count") != expected_page_count
            or publisher not in _SUPPORTED_PUBLISHERS
            or not isinstance(document_role, str)
            or not document_role
        ):
            raise PublicSourceRecordError(
                f"public layout binding changed: {source_id}"
            )

        assignments: list[tuple[int, str]] = []
        for raw_rule in document["page_rules"]:
            rule = dict(raw_rule)
            assignments.extend(
                (page_number, str(rule["layout_id"]))
                for page_number in _expanded_pages(rule)
            )
        assignments.sort()
        level = _level_from_source_id(source_id)
        document_cell_count = 0
        document_record_count = 0
        try:
            with pdfplumber.open(match.path) as pdf:
                if len(pdf.pages) != expected_page_count:
                    raise PublicSourceRecordError(
                        f"PDF page count changed during extraction: {source_id}"
                    )
                for page_number, layout_id in assignments:
                    layout_spec = registry["layout_families"][layout_id]
                    try:
                        cells, candidates, reconciliation = _parse_page(
                            pdf.pages[page_number - 1],
                            source_id=source_id,
                            pdf_sha256=expected_digest,
                            page_number=page_number,
                            layout_id=layout_id,
                            layout_spec=layout_spec,
                            level=level,
                        )
                    except TextLayoutError as exc:
                        raise PublicSourceRecordError(
                            f"public text layout failed: {source_id}:"
                            f"p{page_number:04d}:{layout_id}: {exc}"
                        ) from exc
                    page_cells, page_records = _validated_page_output(
                        source_id=source_id,
                        publisher=str(publisher),
                        document_role=document_role,
                        level=f"N{level}",
                        pdf_sha256=expected_digest,
                        page_number=page_number,
                        layout_id=layout_id,
                        creates_candidates=bool(
                            layout_spec["creates_canonical_candidates"]
                        ),
                        cells=cells,
                        candidates=candidates,
                        reconciliation=reconciliation,
                    )
                    for cell in page_cells:
                        cell_id = str(cell["cell_id"])
                        if cell_id in cells_by_id:
                            raise PublicSourceRecordError(
                                f"duplicate public cell ID: {cell_id}"
                            )
                        cells_by_id[cell_id] = cell
                    for source_record in page_records:
                        source_record_id = str(source_record["source_record_id"])
                        if source_record_id in source_records_by_id:
                            raise PublicSourceRecordError(
                                f"duplicate public source record ID: {source_record_id}"
                            )
                        source_records_by_id[source_record_id] = source_record
                    content_class = str(layout_spec["content_class"])
                    reference_cell_count = sum(
                        cell.get("role") == "reference_text" for cell in page_cells
                    )
                    structured_cell_count = (
                        len(page_cells)
                        if content_class == "structured_reference"
                        else 0
                    )
                    page_receipts.append(
                        {
                            "cell_count": len(page_cells),
                            "content_class": content_class,
                            "layout_id": layout_id,
                            "ordered_cell_ids_hash": sha256_json(
                                [str(cell["cell_id"]) for cell in page_cells]
                            ),
                            "ordered_source_record_ids_hash": sha256_json(
                                [
                                    str(record["source_record_id"])
                                    for record in page_records
                                ]
                            ),
                            "page": page_number,
                            "reconciliation": dict(reconciliation),
                            "reference_cell_count": reference_cell_count,
                            "source_id": source_id,
                            "source_record_count": len(page_records),
                            "structured_cell_count": structured_cell_count,
                        }
                    )
                    document_cell_count += len(page_cells)
                    document_record_count += len(page_records)
        except OSError as exc:
            raise PublicSourceRecordError(
                f"cannot open matched PDF: {source_id}: {exc}"
            ) from exc
        document_receipts.append(
            {
                "cell_count": document_cell_count,
                "page_count": len(assignments),
                "pdf_sha256": expected_digest,
                "source_id": source_id,
                "source_record_count": document_record_count,
            }
        )

    sorted_records = dict(sorted(source_records_by_id.items()))
    sorted_cells = dict(sorted(cells_by_id.items()))
    summary = {
        "cell_count": len(sorted_cells),
        "cells_hash": sha256_json(sorted_cells),
        "document_count": len(document_receipts),
        "page_count": len(page_receipts),
        "pages_hash": sha256_json(page_receipts),
        "reference_cell_count": sum(
            cell.get("role") == "reference_text" for cell in sorted_cells.values()
        ),
        "source_record_count": len(sorted_records),
        "source_records_hash": sha256_json(sorted_records),
        "structured_cell_count": sum(
            receipt["structured_cell_count"] for receipt in page_receipts
        ),
    }
    payload: dict[str, Any] = {
        "cells_by_id": sorted_cells,
        "documents": document_receipts,
        "layout_registry_sha256": sha256_file(layout_registry_path),
        "pages": page_receipts,
        "policy_version": PUBLIC_SOURCE_RECORD_POLICY_VERSION,
        "schema_version": 1,
        "source_records_by_id": sorted_records,
        "status": "passed",
        "summary": summary,
        "unresolved": 0,
    }
    payload["payload_hash"] = sha256_json(payload)
    return payload
