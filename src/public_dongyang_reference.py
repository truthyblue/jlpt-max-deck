"""Parse public Dongyang synonym-reference pages into comparison pairs.

This module uses the PDF's embedded font, size, color, and
geometry evidence to recover the four semantic fields shown in each entry.  It
does not perform OCR and it never treats ruby or the repeated page heading as
content.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


LAYOUT_ID = "dongyang_synonym_reference"
REFERENCE_KIND = "dongyang_synonym_pair"
PARSER_POLICY_VERSION = "dongyang-synonym-semantic-v1"
CONTENT_TOP_POINTS = 35.0
CONTENT_BOTTOM_POINTS = 395.0

_JAPANESE_BASE_FONTS = ("DFHSGothic", "DFHSMincho-W5")
_KOREAN_FONT = "YDVYGOStd11"
_JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_KOREAN_RE = re.compile(r"[\uac00-\ud7a3]")
_FIELDS = (
    "primary_japanese",
    "primary_korean",
    "comparison_japanese",
    "comparison_korean",
)


class DongyangSynonymParseError(RuntimeError):
    """Raised when a synonym page cannot be parsed without ambiguity."""


def _black_component(value: object) -> float | None:
    if isinstance(value, (tuple, list)) and len(value) >= 4:
        component = value[3]
        if isinstance(component, (int, float)):
            return float(component)
    return None


def classify_word(word: Mapping[str, Any]) -> str | None:
    """Classify a PDF word as primary Japanese, comparison, Korean, or noise."""
    font = str(word.get("fontname", ""))
    size_value = word.get("size")
    size = float(size_value) if isinstance(size_value, (int, float)) else 0.0
    text = str(word.get("text", "")).strip()
    if _KOREAN_FONT in font and 7.0 <= size <= 9.0:
        return "korean"
    if any(name in font for name in _JAPANESE_BASE_FONTS) and size >= 10.0:
        black = _black_component(word.get("non_stroking_color"))
        if text == "≒" or (black is not None and black < 0.9):
            return "comparison_japanese"
        return "primary_japanese"
    return None


def _normalized_bbox(
    word: Mapping[str, Any], *, width: float, height: float
) -> list[float]:
    return [
        round(float(word["x0"]) / width, 8),
        round(float(word["top"]) / height, 8),
        round(float(word["x1"]) / width, 8),
        round(float(word["bottom"]) / height, 8),
    ]


def _fragment(
    word: Mapping[str, Any], *, width: float, height: float
) -> dict[str, Any]:
    color = word.get("non_stroking_color")
    return {
        "bbox": _normalized_bbox(word, width=width, height=height),
        "font_name": str(word.get("fontname", "")),
        "font_size": round(float(word.get("size", 0.0)), 4),
        "non_stroking_color": list(color)
        if isinstance(color, (tuple, list))
        else color,
        "text": str(word.get("text", "")),
    }


def _bbox_union(fragments: Sequence[Mapping[str, Any]]) -> list[float]:
    boxes = [fragment["bbox"] for fragment in fragments]
    if not boxes:
        raise DongyangSynonymParseError("cannot compute an empty field bbox")
    return [
        round(min(float(box[0]) for box in boxes), 8),
        round(min(float(box[1]) for box in boxes), 8),
        round(max(float(box[2]) for box in boxes), 8),
        round(max(float(box[3]) for box in boxes), 8),
    ]


def _new_record() -> dict[str, Any]:
    return {
        "text": {field: "" for field in _FIELDS},
        "fragments": {field: [] for field in _FIELDS},
        "comparison_markers": [],
    }


def _complete(record: Mapping[str, Any]) -> bool:
    text = record["text"]
    return all(str(text[field]).strip() for field in _FIELDS)


def _append_token(
    record: dict[str, Any],
    field: str,
    text: str,
    fragment: Mapping[str, Any],
) -> None:
    if field.endswith("_korean") and record["text"][field]:
        record["text"][field] += " "
    record["text"][field] += text
    record["fragments"][field].append(dict(fragment))


def _validate_record(
    record: Mapping[str, Any], *, source_id: str, page_number: int, index: int
) -> None:
    reference = f"{source_id}:p{page_number:04d}:synonym-{index:02d}"
    if not _complete(record):
        missing = [
            field for field in _FIELDS if not str(record["text"][field]).strip()
        ]
        raise DongyangSynonymParseError(
            f"{reference} is missing semantic fields: {missing}"
        )
    if len(record["comparison_markers"]) != 1:
        raise DongyangSynonymParseError(
            f"{reference} has {len(record['comparison_markers'])} comparison markers"
        )
    text = record["text"]
    if not _JAPANESE_RE.search(str(text["primary_japanese"])):
        raise DongyangSynonymParseError(
            f"{reference} primary Japanese lacks Japanese script"
        )
    if not _JAPANESE_RE.search(str(text["comparison_japanese"])):
        raise DongyangSynonymParseError(
            f"{reference} comparison Japanese lacks Japanese script"
        )
    if not _KOREAN_RE.search(str(text["primary_korean"])):
        raise DongyangSynonymParseError(
            f"{reference} primary Korean lacks Hangul"
        )
    if not _KOREAN_RE.search(str(text["comparison_korean"])):
        raise DongyangSynonymParseError(
            f"{reference} comparison Korean lacks Hangul"
        )


def parse_synonym_page(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    jlpt_level: str,
    page_number: int,
) -> list[dict[str, Any]]:
    """Parse one declared synonym-reference page with strict field reconciliation."""
    width = float(page.width)
    height = float(page.height)
    if width <= 0.0 or height <= 0.0:
        raise DongyangSynonymParseError(
            f"invalid page dimensions: {source_id} p{page_number}"
        )
    words = page.extract_words(
        extra_attrs=["fontname", "size", "non_stroking_color"],
        use_text_flow=False,
        keep_blank_chars=False,
    )
    tokens: list[dict[str, Any]] = []
    for word in words:
        top = float(word["top"])
        if not CONTENT_TOP_POINTS <= top <= CONTENT_BOTTOM_POINTS:
            continue
        kind = classify_word(word)
        if kind is None:
            continue
        text = str(word.get("text", "")).strip()
        if not text:
            continue
        tokens.append(
            {
                "kind": kind,
                "text": text,
                "top": top,
                "x0": float(word["x0"]),
                "fragment": _fragment(word, width=width, height=height),
            }
        )
    tokens.sort(key=lambda token: (token["top"], token["x0"]))
    if not tokens:
        raise DongyangSynonymParseError(
            f"no semantic tokens found: {source_id} p{page_number}"
        )

    raw_records: list[dict[str, Any]] = []
    record: dict[str, Any] | None = None
    phase = "primary"
    for token in tokens:
        kind = str(token["kind"])
        text = str(token["text"])
        fragment = token["fragment"]
        if kind == "primary_japanese":
            if record is not None and _complete(record):
                raw_records.append(record)
                record = None
            if record is None:
                record = _new_record()
            phase = "primary"
            _append_token(record, "primary_japanese", text, fragment)
            continue
        if record is None:
            raise DongyangSynonymParseError(
                f"{kind} appeared before a primary entry: {source_id} p{page_number}"
            )
        if kind == "comparison_japanese":
            phase = "comparison"
            if text == "≒":
                record["comparison_markers"].append(dict(fragment))
            else:
                _append_token(record, "comparison_japanese", text, fragment)
            continue
        target = "comparison_korean" if phase == "comparison" else "primary_korean"
        _append_token(record, target, text, fragment)
    if record is not None:
        raw_records.append(record)

    references: list[dict[str, Any]] = []
    for index, item in enumerate(raw_records, start=1):
        _validate_record(
            item,
            source_id=source_id,
            page_number=page_number,
            index=index,
        )
        field_provenance = {
            field: {
                "bbox": _bbox_union(item["fragments"][field]),
                "raw_fragments": item["fragments"][field],
            }
            for field in _FIELDS
        }
        all_fragments = [
            fragment
            for field in _FIELDS
            for fragment in item["fragments"][field]
        ] + list(item["comparison_markers"])
        references.append(
            {
                "schema_version": 1,
                "reference_id": (
                    f"{source_id}:p{page_number:04d}:synonym-{index:02d}"
                ),
                "reference_kind": REFERENCE_KIND,
                "layout_id": LAYOUT_ID,
                "source_id": source_id,
                "publisher": "dongyang",
                "jlpt_level": jlpt_level,
                "pdf_sha256": pdf_sha256,
                "page": page_number,
                "bbox": _bbox_union(all_fragments),
                "primary": {
                    "japanese": item["text"]["primary_japanese"],
                    "korean": item["text"]["primary_korean"],
                },
                "comparison": {
                    "japanese": item["text"]["comparison_japanese"],
                    "korean": item["text"]["comparison_korean"],
                },
                "field_provenance": field_provenance,
                "comparison_marker_provenance": {
                    "bbox": _bbox_union(item["comparison_markers"]),
                    "raw_fragments": item["comparison_markers"],
                },
                "extraction_provenance": {
                    "method": "embedded_text_geometry",
                    "ocr_used": False,
                    "parser_policy_version": PARSER_POLICY_VERSION,
                    "page_dimensions_points": [round(width, 6), round(height, 6)],
                },
            }
        )
    return references
