"""Typed source-cell contract for public PDF layout parsers."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence


CELL_ROLES = frozenset(
    {
        "calendar_lexeme",
        "counter_example",
        "counter_header",
        "grammar_pattern",
        "ignored_decoration",
        "instruction",
        "lexeme_reading",
        "lexeme_surface",
        "meaning",
        "pos",
        "query_row_header",
        "reference_text",
    }
)
CELL_STATUSES = frozenset({"accepted", "excluded", "pending_review"})
EXTRACTION_METHODS = frozenset({"cell_ocr", "none", "text_geometry"})
LEXEME_ROLES = ("lexeme_surface", "lexeme_reading", "pos", "meaning")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class CellContractError(ValueError):
    """Raised when a typed cell or page reconciliation violates the contract."""


def normalize_cell_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split())


def _validated_bbox(value: Sequence[object], label: str) -> list[float]:
    if len(value) != 4:
        raise CellContractError(f"{label} must contain four numeric coordinates")
    bbox: list[float] = []
    for number in value:
        if not isinstance(number, (int, float)):
            raise CellContractError(f"{label} must contain four numeric coordinates")
        bbox.append(round(float(number), 8))
    x0, y0, x1, y1 = bbox
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        raise CellContractError(f"{label} is outside normalized page bounds")
    return bbox


def _bbox_contains(outer: Sequence[float], inner: Sequence[float]) -> bool:
    tolerance = 1e-7
    return (
        outer[0] - tolerance <= inner[0]
        and outer[1] - tolerance <= inner[1]
        and outer[2] + tolerance >= inner[2]
        and outer[3] + tolerance >= inner[3]
    )


def make_cell(
    *,
    source_id: str,
    pdf_sha256: str,
    page: int,
    layout_id: str,
    row_id: str,
    role: str,
    bbox: Sequence[object],
    raw_fragments: Sequence[Mapping[str, Any]],
    extraction_method: str,
    confidence: float,
    status: str,
    status_reason: str | None = None,
    extraction_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and serialize one page-bound source cell."""
    if not source_id or not layout_id or not row_id:
        raise CellContractError("cell identity fields must be nonempty")
    if not isinstance(page, int) or page < 1:
        raise CellContractError("cell page must be a positive integer")
    if SHA256_RE.fullmatch(pdf_sha256) is None:
        raise CellContractError("cell PDF hash must be lowercase SHA-256")
    if role not in CELL_ROLES:
        raise CellContractError(f"invalid cell role: {role}")
    if status not in CELL_STATUSES:
        raise CellContractError(f"invalid cell status: {status}")
    if extraction_method not in EXTRACTION_METHODS:
        raise CellContractError(
            f"invalid cell extraction method: {extraction_method}"
        )
    if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        raise CellContractError("cell confidence must be between zero and one")
    if status == "accepted" and status_reason is not None:
        raise CellContractError("accepted cell may not carry a status reason")
    if status != "accepted" and (
        not isinstance(status_reason, str) or not status_reason.strip()
    ):
        raise CellContractError("non-accepted cell requires a status reason")
    cell_bbox = _validated_bbox(bbox, "cell bbox")
    if not raw_fragments:
        raise CellContractError("cell must retain at least one raw fragment")

    fragments: list[dict[str, Any]] = []
    raw_parts: list[str] = []
    for index, fragment in enumerate(raw_fragments):
        text = fragment.get("text")
        if not isinstance(text, str):
            raise CellContractError(f"raw fragment {index} lacks text")
        fragment_bbox_value = fragment.get("bbox")
        if not isinstance(fragment_bbox_value, (list, tuple)):
            raise CellContractError(f"raw fragment {index} lacks bbox")
        fragment_bbox = _validated_bbox(
            fragment_bbox_value, f"raw fragment {index} bbox"
        )
        if not _bbox_contains(cell_bbox, fragment_bbox):
            raise CellContractError(f"fragment bbox escapes cell bbox: {index}")
        font_name = fragment.get("font_name")
        font_size = fragment.get("font_size")
        if font_name is not None and not isinstance(font_name, str):
            raise CellContractError(f"raw fragment {index} has invalid font name")
        if font_size is not None and not isinstance(font_size, (int, float)):
            raise CellContractError(f"raw fragment {index} has invalid font size")
        fragments.append(
            {
                "text": text,
                "bbox": fragment_bbox,
                "font_name": font_name,
                "font_size": None if font_size is None else round(float(font_size), 6),
            }
        )
        raw_parts.append(text)

    raw_text = "".join(raw_parts)
    if extraction_provenance is None:
        serialized_provenance = None
    else:
        try:
            serialized_provenance = json.loads(
                json.dumps(
                    extraction_provenance,
                    allow_nan=False,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        except (TypeError, ValueError) as exc:
            raise CellContractError(
                "cell extraction provenance must be JSON-safe"
            ) from exc
        if not isinstance(serialized_provenance, dict):
            raise CellContractError("cell extraction provenance must be an object")
    cell = {
        "schema_version": 1,
        "source_id": source_id,
        "pdf_sha256": pdf_sha256,
        "page": page,
        "layout_id": layout_id,
        "cell_id": f"{source_id}:p{page:04d}:{row_id}:{role}",
        "row_id": row_id,
        "role": role,
        "bbox": cell_bbox,
        "bbox_space": "normalized_top_left",
        "raw_fragments": fragments,
        "raw_text": raw_text,
        "normalized_text": normalize_cell_text(raw_text),
        "extraction_method": extraction_method,
        "confidence": round(float(confidence), 6),
        "status": status,
        "status_reason": status_reason,
    }
    if serialized_provenance is not None:
        cell["extraction_provenance"] = serialized_provenance
    return cell


def build_lexeme_candidates(cells: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Link accepted lexical roles; structural roles are never promoted."""
    grouped: dict[tuple[str, str, int, str, str], dict[str, Mapping[str, Any]]] = (
        defaultdict(dict)
    )
    for cell in cells:
        role = cell.get("role")
        if role not in LEXEME_ROLES or cell.get("status") != "accepted":
            continue
        key = (
            str(cell["source_id"]),
            str(cell["pdf_sha256"]),
            int(cell["page"]),
            str(cell["layout_id"]),
            str(cell["row_id"]),
        )
        if role in grouped[key]:
            raise CellContractError(f"duplicate accepted row role: {key}:{role}")
        grouped[key][str(role)] = cell

    candidates: list[dict[str, Any]] = []
    for key in sorted(grouped):
        row_cells = grouped[key]
        surface = row_cells.get("lexeme_surface")
        if surface is None:
            continue
        source_id, pdf_sha256, page, layout_id, row_id = key
        linked_roles = [role for role in LEXEME_ROLES if role in row_cells]
        source_cell_ids = {
            role: str(row_cells[role]["cell_id"]) for role in linked_roles
        }
        candidates.append(
            {
                "schema_version": 1,
                "candidate_id": f"{source_id}:p{page:04d}:{row_id}",
                "source_id": source_id,
                "pdf_sha256": pdf_sha256,
                "page": page,
                "layout_id": layout_id,
                "row_id": row_id,
                "surface": str(surface["normalized_text"]),
                "reading": str(
                    row_cells.get("lexeme_reading", {}).get("normalized_text", "")
                ),
                "pos": str(row_cells.get("pos", {}).get("normalized_text", "")),
                "meaning": str(
                    row_cells.get("meaning", {}).get("normalized_text", "")
                ),
                "confidence": min(
                    float(row_cells[role]["confidence"]) for role in linked_roles
                ),
                "source_cell_ids": source_cell_ids,
            }
        )
    return candidates


def reconcile_page_cells(
    cells: Sequence[Mapping[str, Any]],
    *,
    declared_role_counts: Mapping[str, int],
) -> dict[str, Any]:
    """Prove that every declared page cell has exactly one terminal status."""
    if not cells and any(declared_role_counts.values()):
        raise CellContractError("declared page cells are missing")
    cell_ids = [str(cell.get("cell_id", "")) for cell in cells]
    duplicate_ids = sorted(
        cell_id for cell_id, count in Counter(cell_ids).items() if count > 1
    )
    if duplicate_ids:
        raise CellContractError(f"duplicate cell_id: {duplicate_ids}")
    actual_role_counts = Counter(str(cell.get("role", "")) for cell in cells)
    for role, declared in declared_role_counts.items():
        if role not in CELL_ROLES or not isinstance(declared, int) or declared < 0:
            raise CellContractError(f"invalid declared role count: {role}={declared}")
        actual = actual_role_counts.get(role, 0)
        if actual != declared:
            raise CellContractError(
                f"declared role count mismatch: {role} declared={declared} actual={actual}"
            )
    undeclared_roles = sorted(set(actual_role_counts) - set(declared_role_counts))
    if undeclared_roles:
        raise CellContractError(f"page has undeclared roles: {undeclared_roles}")
    status_counts = Counter(str(cell.get("status", "")) for cell in cells)
    invalid_statuses = sorted(set(status_counts) - CELL_STATUSES)
    if invalid_statuses:
        raise CellContractError(f"page has invalid cell statuses: {invalid_statuses}")
    return {
        "status": "passed",
        "declared_cells": sum(declared_role_counts.values()),
        "observed_cells": len(cells),
        "declared_role_counts": dict(sorted(declared_role_counts.items())),
        "status_counts": {
            status: status_counts.get(status, 0)
            for status in ("accepted", "excluded", "pending_review")
        },
    }
