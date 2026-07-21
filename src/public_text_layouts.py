"""Public layout-family parsers for text-layer publisher PDF pages."""

from __future__ import annotations

import logging
import re
import statistics
import unicodedata
from typing import Any, Mapping, Sequence

from public_dongyang_reference import parse_synonym_page
from public_text_geometry import (
    DONGYANG_CONFIG,
    HACKERS_SURFACE_ANCHORS,
    JAPANESE_CHAR_RE,
    chars_text,
    cluster_chars,
    compose_surface_reading,
    dongyang_reading,
    hackers_meaning_chars,
    hackers_reading,
    hackers_row_vertical_bounds,
    hackers_surface_rows,
    meaning_text,
    split_horizontal_groups,
)
from public_layout_cells import (
    build_lexeme_candidates,
    make_cell,
    reconcile_page_cells,
)
from public_text_geometry import contains_japanese


class TextLayoutError(ValueError):
    """Raised when detected PDF geometry does not match its declared layout."""


HANGUL_OR_POS_KANA_RE = re.compile(r"[가-힣]|[いな]")
HACKERS_POS_VALUES = frozenset({"명", "동", "い형", "な형", "부", "접", "형"})
JAPANESE_TEXT_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff々〆ヶ～〜]")
KANJI_TEXT_RE = re.compile(r"[\u3400-\u9fff々〆ヶ]")
HACKERS_VOCAB_LAYOUTS = frozenset(
    {"hackers_vocab_two_column", "hackers_vocab_example_column"}
)
HACKERS_LATEST_VOCAB_LAYOUTS = frozenset({"hackers_latest_vocabulary"})
HACKERS_USAGE_LAYOUTS = frozenset(
    {
        "hackers_usage_lexemes",
        "hackers_usage_lexemes_to_phrases",
        "hackers_usage_lexemes_to_vocab",
        "hackers_usage_phrases",
        "hackers_usage_phrases_to_vocab",
        "hackers_vocab_to_usage_lexemes",
    }
)
HACKERS_ROW_LAYOUTS = HACKERS_VOCAB_LAYOUTS | HACKERS_USAGE_LAYOUTS
HACKERS_RELATION_PREFIXES = frozenset({"≒"})


def _normalized_bbox(
    bbox: Sequence[float], page_width: float, page_height: float
) -> list[float]:
    x0, top, x1, bottom = bbox
    return [
        round(x0 / page_width, 8),
        round(top / page_height, 8),
        round(x1 / page_width, 8),
        round(bottom / page_height, 8),
    ]


def _bbox_within(outer: Sequence[float], inner: Sequence[float]) -> bool:
    tolerance = 0.005
    return (
        outer[0] - tolerance <= inner[0]
        and outer[1] - tolerance <= inner[1]
        and outer[2] + tolerance >= inner[2]
        and outer[3] + tolerance >= inner[3]
    )


def _point_bbox(
    characters: Sequence[Mapping[str, Any]],
    fallback: Sequence[float],
) -> tuple[float, float, float, float]:
    if not characters:
        return tuple(float(value) for value in fallback)  # type: ignore[return-value]
    return (
        min(float(char["x0"]) for char in characters),
        min(float(char["top"]) for char in characters),
        max(float(char["x1"]) for char in characters),
        max(float(char["bottom"]) for char in characters),
    )


def _make_aggregate_text_cell(
    *,
    page: Any,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    row_id: str,
    role: str,
    raw_text: str,
    characters: Sequence[Mapping[str, Any]],
    fallback_bbox: Sequence[float],
    inspection_bbox: Sequence[float],
    status: str = "accepted",
    status_reason: str | None = None,
    confidence: float = 1.0,
    extraction_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    points_bbox = _point_bbox(characters, fallback_bbox)
    normalized_bbox = _normalized_bbox(
        points_bbox, float(page.width), float(page.height)
    )
    if not _bbox_within(inspection_bbox, normalized_bbox):
        raise TextLayoutError(
            f"{layout_id} cell escapes declared inspection bbox: {row_id}:{role}"
        )
    font_names = {
        str(char.get("fontname", "")) for char in characters if char.get("fontname")
    }
    font_sizes = {
        round(float(char["size"]), 6) for char in characters if char.get("size")
    }
    fragment = {
        "text": raw_text,
        "bbox": normalized_bbox,
        "font_name": next(iter(font_names)) if len(font_names) == 1 else None,
        "font_size": next(iter(font_sizes)) if len(font_sizes) == 1 else None,
    }
    return make_cell(
        source_id=source_id,
        pdf_sha256=pdf_sha256,
        page=page_number,
        layout_id=layout_id,
        row_id=row_id,
        role=role,
        bbox=normalized_bbox,
        raw_fragments=(fragment,),
        extraction_method="text_geometry",
        confidence=confidence,
        status=status,
        status_reason=status_reason,
        extraction_provenance=extraction_provenance,
    )


def _ordinary_page_result(
    cells: list[dict[str, Any]], row_count: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    reconciliation = reconcile_page_cells(
        cells,
        declared_role_counts={
            "lexeme_surface": row_count,
            "lexeme_reading": row_count,
            "pos": row_count,
            "meaning": row_count,
        },
    )
    candidates = build_lexeme_candidates(cells)
    if len(candidates) != row_count:
        raise TextLayoutError(
            f"ordinary vocabulary candidate reconciliation failed: "
            f"rows={row_count} candidates={len(candidates)}"
        )
    return cells, candidates, reconciliation


def _hackers_meaning_evidence(
    page: Any,
    rows: list[dict[str, Any]],
    row: dict[str, Any],
) -> tuple[float, float, list[dict[str, Any]], str]:
    start, end = hackers_row_vertical_bounds(rows, row)
    half_width = float(page.width) / 2.0
    half_lo, half_hi = (
        (0.0, half_width)
        if int(row["half"]) == 0
        else (half_width, float(page.width))
    )
    meaning_candidates = [
        char
        for char in page.chars
        if half_lo <= float(char["x0"]) < half_hi
        and float(char["x0"]) >= float(row["surface_x"]) + 55.0
        and start <= float(char["top"]) < end
        and "YoonGothicPro745" in str(char.get("fontname", ""))
        and float(char["size"]) >= 6.4
    ]
    meaning_chars = hackers_meaning_chars(
        meaning_candidates, float(row["top"])
    )
    return start, end, meaning_chars, meaning_text(meaning_chars)


def _hackers_row_has_checkbox(page: Any, row: Mapping[str, Any]) -> bool:
    surface_x = float(row["surface_x"])
    row_top = float(row["top"])
    return any(
        4.0 <= float(rect.get("width", 0.0)) <= 10.0
        and 4.0 <= float(rect.get("height", 0.0)) <= 10.0
        and surface_x - 25.0 <= float(rect["x0"]) <= surface_x - 5.0
        and abs(float(rect["top"]) - row_top) <= 18.0
        for rect in page.rects
    )


def _merge_hackers_unboxed_continuations(
    page: Any, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for half in (0, 1):
        half_rows = sorted(
            (dict(row) for row in rows if int(row["half"]) == half),
            key=lambda row: float(row["top"]),
        )
        half_merged: list[dict[str, Any]] = []
        for row in half_rows:
            _start, _end, meaning_chars, meaning = _hackers_meaning_evidence(
                page, rows, row
            )
            previous = half_merged[-1] if half_merged else None
            vertical_gap = (
                float(row["top"])
                - float(previous.get("bottom_top", previous["top"]))
                if previous is not None
                else float("inf")
            )
            previous_surface = str(previous["surface"]) if previous else ""
            has_unclosed_quote = previous_surface.count("「") > previous_surface.count(
                "」"
            )
            meaning_leads_surface = bool(meaning_chars) and (
                float(row["top"])
                - min(float(char["top"]) for char in meaning_chars)
                >= 5.5
            )
            is_unboxed_continuation = not int(row.get("row_anchor_count", 0)) and (
                meaning_leads_surface
                or (not meaning and not _hackers_row_has_checkbox(page, row))
            )
            if (
                previous is not None
                and 0.0 < vertical_gap <= 30.0
                and (has_unclosed_quote or is_unboxed_continuation)
            ):
                previous["surface"] = str(previous["surface"]) + str(row["surface"])
                previous["surface_groups"] = [
                    *previous.get("surface_groups", []),
                    *row.get("surface_groups", []),
                ]
                previous["bottom_top"] = row.get("bottom_top", row["top"])
                previous["row_anchor_count"] = int(
                    previous.get("row_anchor_count", 0)
                ) + int(row.get("row_anchor_count", 0))
                continue
            half_merged.append(row)
        merged.extend(half_merged)

    merged.sort(key=lambda row: (float(row["top"]), int(row["half"])))
    for row_index, row in enumerate(merged, start=1):
        row["row"] = f"c{int(row['half']) + 1}-r{row_index}"
    return merged


def _recover_hackers_relation_prefixed_rows(
    page: Any,
    rows: list[dict[str, Any]],
    *,
    level: int,
) -> list[dict[str, Any]]:
    """Recover a surface fused to the N2 relation marker without renumbering rows.

    The comparison marker normally forms its own PDF text group. On N2 page 33,
    the long `トレーニング` surface is close enough to be emitted as one
    `≒トレーニング` group. The ordinary surface detector correctly rejects the
    marker's x-position, but the actual surface must still become an independent
    comparison row. Recovered rows use a suffix anchored to the next existing row
    so unrelated downstream row IDs remain stable.
    """
    surface_chars = [
        char
        for char in page.chars
        if "KozGoPro-Medium" in str(char.get("fontname", ""))
    ]
    raw_groups = split_horizontal_groups(
        cluster_chars(surface_chars), gap=12.0
    )
    recovered: list[dict[str, Any]] = []
    for raw_group in raw_groups:
        ordered_group = sorted(raw_group, key=lambda char: float(char["x0"]))
        prefix_length = 0
        while (
            prefix_length < len(ordered_group)
            and str(ordered_group[prefix_length].get("text", ""))
            in HACKERS_RELATION_PREFIXES
        ):
            prefix_length += 1
        if prefix_length == 0 or prefix_length == len(ordered_group):
            continue
        surface_group = ordered_group[prefix_length:]
        surface = chars_text(surface_group)
        if not contains_japanese(surface):
            continue
        surface_x = min(float(char["x0"]) for char in surface_group)
        anchor_distances = [
            abs(surface_x - float(anchor))
            for anchor in HACKERS_SURFACE_ANCHORS[level]
        ]
        if min(anchor_distances) > 15.0:
            raise TextLayoutError(
                "Hackers relation-prefixed surface has no column anchor: "
                f"surface={surface!r} x={surface_x:.3f}"
            )
        half = anchor_distances.index(min(anchor_distances))
        top = sum(float(char["top"]) for char in surface_group) / len(
            surface_group
        )
        if any(
            int(row["half"]) == half
            and abs(float(row["top"]) - top) <= 1.0
            and str(row["surface"]) == surface
            for row in rows
        ):
            continue
        recovered.append(
            {
                "half": half,
                "surface": surface,
                "surface_x": surface_x,
                "top": top,
                "bottom_top": top,
                "surface_groups": [surface_group],
                "row_anchor_count": 0,
            }
        )

    suffix_counts: dict[str, int] = {}
    for row in sorted(
        recovered, key=lambda item: (float(item["top"]), int(item["half"]))
    ):
        same_half_rows = [
            existing
            for existing in rows
            if int(existing["half"]) == int(row["half"])
        ]
        following = [
            existing
            for existing in same_half_rows
            if float(existing["top"]) > float(row["top"])
        ]
        if following:
            anchor_row = min(following, key=lambda item: float(item["top"]))
        elif same_half_rows:
            anchor_row = max(same_half_rows, key=lambda item: float(item["top"]))
        else:
            raise TextLayoutError(
                "Hackers relation-prefixed surface has no neighboring row"
            )
        anchor_id = str(anchor_row["row"])
        suffix_counts[anchor_id] = suffix_counts.get(anchor_id, 0) + 1
        row["row"] = f"{anchor_id}-s{suffix_counts[anchor_id]:02d}"
        rows.append(row)

    rows.sort(key=lambda row: (float(row["top"]), int(row["half"])))
    return rows


def _parse_hackers_row_cells(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    layout_spec: Mapping[str, Any],
    level: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract the shared Hackers row geometry before disposition by layout."""
    if layout_id not in HACKERS_ROW_LAYOUTS:
        raise TextLayoutError(f"unsupported Hackers row layout: {layout_id}")
    inspection_bbox = layout_spec.get("inspection_bbox")
    if not isinstance(inspection_bbox, list) or len(inspection_bbox) != 4:
        raise TextLayoutError(f"layout lacks inspection bbox: {layout_id}")
    rows = hackers_surface_rows(page, level, page_number)
    if layout_id == "hackers_vocab_example_column":
        rows = [dict(row) for row in rows if int(row["half"]) == 0]
        for row_index, row in enumerate(rows, start=1):
            row["row"] = f"c1-r{row_index}"
    rows = _merge_hackers_unboxed_continuations(page, rows)
    if layout_id in HACKERS_USAGE_LAYOUTS:
        rows = _recover_hackers_relation_prefixed_rows(
            page, rows, level=level
        )
    if not rows:
        raise TextLayoutError(f"Hackers page has no vocabulary rows: {page_number}")
    multi_anchor_rows = [
        str(row["row"])
        for row in rows
        if int(row.get("row_anchor_count", 0)) > 1
    ]
    if multi_anchor_rows:
        raise TextLayoutError(
            "Hackers candidate spans multiple independent row anchors: "
            f"page={page_number} rows={multi_anchor_rows[:5]}"
        )
    cells: list[dict[str, Any]] = []
    for row in rows:
        start, end, meaning_chars, meaning = _hackers_meaning_evidence(
            page, rows, row
        )
        half_width = float(page.width) / 2.0
        half_lo, half_hi = (
            (0.0, half_width)
            if int(row["half"]) == 0
            else (half_width, float(page.width))
        )
        surface_chars = [
            char
            for group in row.get("surface_groups", [])
            for char in group
        ]
        surface_bbox = _point_bbox(
            surface_chars,
            (float(row["surface_x"]), float(row["top"]), float(row["surface_x"]) + 1.0, float(row["top"]) + 1.0),
        )
        reading = hackers_reading(page, row, level)
        reading_chars = [
            char
            for char in page.chars
            if half_lo <= float(char["x0"]) < half_hi
            and start <= float(char["top"]) < end
            and "KozGoPro-Regular" in str(char.get("fontname", ""))
            and JAPANESE_CHAR_RE.search(str(char.get("text", "")))
        ]
        if layout_id == "hackers_vocab_example_column":
            if not KANJI_TEXT_RE.search(str(row["surface"])):
                reading_chars = surface_chars
            else:
                surface_left = min(float(char["x0"]) for char in surface_chars) - 4.0
                surface_right = max(float(char["x1"]) for char in surface_chars) + 4.0
                reading_chars = [
                    char
                    for char in reading_chars
                    if surface_left <= float(char["x0"]) <= surface_right
                    and 2.0
                    <= float(row["top"]) - float(char["top"])
                    <= 10.0
                ]
        meaning_start = min(
            (float(char["x0"]) for char in meaning_chars),
            default=float(row["surface_x"]) + 90.0,
        )
        pos_chars = [
            char
            for char in page.chars
            if half_lo <= float(char["x0"]) < half_hi
            and float(row["surface_x"]) + 50.0 <= float(char["x0"]) < meaning_start
            and start <= float(char["top"]) < end
            and abs(float(char["top"]) - float(row["top"])) <= 10.0
            and float(char["size"]) <= 6.5
            and HANGUL_OR_POS_KANA_RE.search(str(char.get("text", "")))
        ]
        if not any(
            "YoonGothicPro745" in str(char.get("fontname", ""))
            for char in pos_chars
        ):
            # A kana ruby can fall inside the narrow POS x-range on phrase
            # rows.  Real POS labels always contain at least one character
            # from the publisher's Korean label font (including the 형 in
            # い형/な형), so do not promote a lone ruby as POS evidence.
            pos_chars = []
        pos_chars.sort(key=lambda char: (float(char["top"]), float(char["x0"])))
        pos = chars_text(pos_chars)
        if pos and pos not in HACKERS_POS_VALUES:
            raise TextLayoutError(
                f"Hackers row has invalid POS extraction: "
                f"page={page_number} row={row['row']} pos={pos!r}"
            )
        row_id = str(row["row"])
        field_fallback = (
            max(half_lo, float(row["surface_x"])),
            max(0.0, start),
            min(half_hi, max(float(row["surface_x"]) + 1.0, meaning_start)),
            min(float(page.height), max(start + 1.0, end)),
        )
        cells.extend(
            (
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=row_id,
                    role="lexeme_surface",
                    raw_text=str(row["surface"]),
                    characters=surface_chars,
                    fallback_bbox=surface_bbox,
                    inspection_bbox=inspection_bbox,
                ),
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=row_id,
                    role="lexeme_reading",
                    raw_text=reading,
                    characters=reading_chars if reading else (),
                    fallback_bbox=surface_bbox,
                    inspection_bbox=inspection_bbox,
                    status="accepted" if reading else "excluded",
                    status_reason=None if reading else "source_has_no_explicit_reading",
                    confidence=0.99 if reading else 1.0,
                ),
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=row_id,
                    role="pos",
                    raw_text=pos,
                    characters=pos_chars,
                    fallback_bbox=field_fallback,
                    inspection_bbox=inspection_bbox,
                    status="accepted" if pos else "excluded",
                    status_reason=None if pos else "source_has_no_explicit_pos",
                ),
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=row_id,
                    role="meaning",
                    raw_text=meaning,
                    characters=meaning_chars,
                    fallback_bbox=field_fallback,
                    inspection_bbox=inspection_bbox,
                    status="accepted" if meaning else "pending_review",
                    status_reason=None if meaning else "meaning_not_detected",
                    confidence=1.0 if meaning else 0.0,
                ),
            )
        )
    return cells, rows


def parse_hackers_vocab_page(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    layout_spec: Mapping[str, Any],
    level: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Parse one ordinary Hackers page into typed lexical row cells."""
    if layout_id not in HACKERS_VOCAB_LAYOUTS:
        raise TextLayoutError(f"unsupported Hackers vocabulary layout: {layout_id}")
    cells, rows = _parse_hackers_row_cells(
        page,
        source_id=source_id,
        pdf_sha256=pdf_sha256,
        page_number=page_number,
        layout_id=layout_id,
        layout_spec=layout_spec,
        level=level,
    )
    return _ordinary_page_result(cells, len(rows))


_HACKERS_LATEST_SURFACE_ANCHORS = (63.8, 241.4, 419.1)
_HACKERS_LATEST_COLUMN_BOUNDS = (
    (35.0, 213.0),
    (213.0, 391.0),
    (391.0, 568.0),
)
_HACKERS_LATEST_YEAR_RE = re.compile(r"(?P<year>20\d{2})년")


def _normalize_hackers_latest_surface_chars(
    page: Any, surface_chars: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Disambiguate a ruby-annotated kanji two encoded as katakana ni.

    The Hackers N5 latest PDF encodes the counter entry ``二ひき`` with a
    ``ニ`` base glyph and an overlapping ``に`` ruby glyph.  Restrict this
    normalization to latest-supplement surface rows and require the ruby
    geometry, so ordinary katakana ``ニ`` remains untouched.
    """
    normalized: list[dict[str, Any]] = []
    for raw_char in surface_chars:
        char = dict(raw_char)
        if str(char.get("text", "")) == "ニ":
            base_top = float(char["top"])
            base_x0 = float(char["x0"])
            base_x1 = float(char["x1"])
            has_ni_ruby = any(
                str(ruby.get("text", "")) == "に"
                and "KozGoPro-Regular" in str(ruby.get("fontname", ""))
                and abs(float(ruby.get("size", 0.0)) - 5.0) < 0.25
                and 2.0 <= base_top - float(ruby["top"]) <= 10.0
                and float(ruby["x1"]) >= base_x0
                and float(ruby["x0"]) <= base_x1
                for ruby in page.chars
            )
            if has_ni_ruby:
                char["text"] = "二"
        normalized.append(char)
    return normalized


def _hackers_latest_line_has_row_anchor(
    page: Any, *, surface_x: float, top: float
) -> bool:
    return any(
        4.0 <= float(rect.get("width", 0.0)) <= 10.0
        and 4.0 <= float(rect.get("height", 0.0)) <= 10.0
        and surface_x - 25.0 <= float(rect["x0"]) <= surface_x - 5.0
        and abs(float(rect["top"]) - top) <= 5.5
        for rect in page.rects
    )


def _hackers_latest_rows(page: Any) -> list[dict[str, Any]]:
    surface_chars = [
        char
        for char in page.chars
        if "KozGoPro-Medium" in str(char.get("fontname", ""))
        and 155.0 <= float(char["top"]) <= 770.0
    ]
    groups = split_horizontal_groups(
        cluster_chars(surface_chars, tolerance=0.8), gap=12.0
    )
    rows: list[dict[str, Any]] = []
    for raw_group in groups:
        group = _normalize_hackers_latest_surface_chars(page, raw_group)
        surface = chars_text(group)
        if not contains_japanese(surface):
            continue
        surface_x = min(float(char["x0"]) for char in group)
        distances = [
            abs(surface_x - anchor) for anchor in _HACKERS_LATEST_SURFACE_ANCHORS
        ]
        if min(distances) > 8.0:
            continue
        column = distances.index(min(distances))
        rows.append(
            {
                "column": column,
                "surface": surface,
                "surface_chars": sorted(group, key=lambda char: float(char["x0"])),
                "surface_groups": [
                    sorted(group, key=lambda char: float(char["x0"]))
                ],
                "surface_x": surface_x,
                "top": sum(float(char["top"]) for char in group) / len(group),
                "bottom_top": sum(float(char["top"]) for char in group) / len(group),
                "row_anchor_count": int(
                    _hackers_latest_line_has_row_anchor(
                        page,
                        surface_x=surface_x,
                        top=sum(float(char["top"]) for char in group) / len(group),
                    )
                ),
            }
        )
    merged: list[dict[str, Any]] = []
    for column in range(3):
        column_lines = sorted(
            (row for row in rows if int(row["column"]) == column),
            key=lambda row: float(row["top"]),
        )
        column_rows: list[dict[str, Any]] = []
        for line in column_lines:
            if int(line["row_anchor_count"]) == 1:
                column_rows.append(dict(line))
                continue
            if not column_rows:
                raise TextLayoutError(
                    "Hackers latest continuation lacks an anchored row: "
                    f"column={column + 1} surface={line['surface']!r}"
                )
            previous = column_rows[-1]
            previous["surface"] = str(previous["surface"]) + str(line["surface"])
            previous["surface_chars"] = [
                *previous["surface_chars"],
                *line["surface_chars"],
            ]
            previous["surface_groups"] = [
                *previous["surface_groups"],
                *line["surface_groups"],
            ]
            previous["bottom_top"] = line["bottom_top"]
        for row_index, row in enumerate(column_rows, start=1):
            row["row"] = f"c{column + 1}-r{row_index}"
        merged.extend(column_rows)
    merged.sort(key=lambda row: (float(row["top"]), int(row["column"])))
    return merged


def _hackers_latest_reading(page: Any, row: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    reading_parts: list[str] = []
    all_reading_chars: list[dict[str, Any]] = []
    for raw_group in row["surface_groups"]:
        surface_chars = list(raw_group)
        surface = chars_text(surface_chars)
        if not KANJI_TEXT_RE.search(surface) and not any(
            char.isdigit() for char in surface
        ):
            reading_parts.append(surface)
            all_reading_chars.extend(surface_chars)
            continue
        surface_top = sum(float(char["top"]) for char in surface_chars) / len(
            surface_chars
        )
        surface_left = min(float(char["x0"]) for char in surface_chars) - 4.0
        surface_right = max(float(char["x1"]) for char in surface_chars) + 4.0
        reading_chars = [
            char
            for char in page.chars
            if surface_left <= float(char["x0"]) <= surface_right
            and 2.0 <= surface_top - float(char["top"]) <= 10.0
            and abs(float(char.get("size", 0.0)) - 5.0) < 0.25
            and "KozGoPro-Regular" in str(char.get("fontname", ""))
            and JAPANESE_CHAR_RE.search(str(char.get("text", "")))
        ]
        reading_groups = split_horizontal_groups(
            cluster_chars(reading_chars, tolerance=0.9), gap=10.0
        )
        if not reading_groups:
            return "", []
        reading_parts.append(
            compose_surface_reading(surface_chars, reading_groups)
        )
        all_reading_chars.extend(reading_chars)
    return "".join(reading_parts), all_reading_chars


def parse_hackers_latest_vocabulary_page(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    layout_spec: Mapping[str, Any],
    level: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Parse one odd-numbered Hackers latest vocabulary page.

    The latest supplements use three compact columns and intentionally exclude
    their later practice-test pages from the canonical vocabulary boundary.
    """
    if layout_id not in HACKERS_LATEST_VOCAB_LAYOUTS:
        raise TextLayoutError(
            f"unsupported Hackers latest vocabulary layout: {layout_id}"
        )
    if level not in {1, 2, 3, 4, 5}:
        raise TextLayoutError(f"invalid Hackers latest level: {level}")
    page_text = unicodedata.normalize("NFKC", page.extract_text() or "")
    if "기출 어휘" not in page_text or "연습문제" in page_text:
        raise TextLayoutError(
            f"Hackers latest page is not a vocabulary page: {page_number}"
        )
    year_match = _HACKERS_LATEST_YEAR_RE.search(page_text)
    if year_match is None:
        raise TextLayoutError(
            f"Hackers latest vocabulary page lacks a year: {page_number}"
        )
    inspection_bbox = layout_spec.get("inspection_bbox")
    if not isinstance(inspection_bbox, list) or len(inspection_bbox) != 4:
        raise TextLayoutError(f"layout lacks inspection bbox: {layout_id}")
    rows = _hackers_latest_rows(page)
    if not rows:
        raise TextLayoutError(
            f"Hackers latest page has no vocabulary rows: {page_number}"
        )

    cells: list[dict[str, Any]] = []
    for row in rows:
        column = int(row["column"])
        column_rows = sorted(
            (item for item in rows if int(item["column"]) == column),
            key=lambda item: float(item["top"]),
        )
        row_index = next(
            index
            for index, item in enumerate(column_rows)
            if item["row"] == row["row"]
        )
        previous = column_rows[row_index - 1] if row_index else None
        following = (
            column_rows[row_index + 1]
            if row_index + 1 < len(column_rows)
            else None
        )
        start = (
            (float(previous["bottom_top"]) + float(row["top"])) / 2.0
            if previous is not None
            else float(row["top"]) - 16.0
        )
        end = (
            (float(row["bottom_top"]) + float(following["top"])) / 2.0
            if following is not None
            else float(row["bottom_top"]) + 16.0
        )
        column_lo, column_hi = _HACKERS_LATEST_COLUMN_BOUNDS[column]
        meaning_chars = [
            char
            for char in page.chars
            if column_lo <= float(char["x0"]) < column_hi
            and float(row["surface_x"]) + 50.0 <= float(char["x0"])
            and start <= float(char["top"]) < end
            and "NanumGothic" in str(char.get("fontname", ""))
            and abs(float(char.get("size", 0.0)) - 8.0) < 0.35
        ]
        meaning_chars = hackers_meaning_chars(meaning_chars, float(row["top"]))
        meaning = meaning_text(meaning_chars)
        if not meaning:
            raise TextLayoutError(
                "Hackers latest meaning was not detected: "
                f"page={page_number} row={row['row']} surface={row['surface']!r}"
            )
        reading, reading_chars = _hackers_latest_reading(page, row)
        if KANJI_TEXT_RE.search(str(row["surface"])) and not reading:
            raise TextLayoutError(
                "Hackers latest reading was not detected: "
                f"page={page_number} row={row['row']} surface={row['surface']!r}"
            )
        surface_chars = list(row["surface_chars"])
        surface_bbox = _point_bbox(
            surface_chars,
            (
                float(row["surface_x"]),
                float(row["top"]),
                float(row["surface_x"]) + 1.0,
                float(row["top"]) + 1.0,
            ),
        )
        fallback_bbox = (
            max(column_lo, float(row["surface_x"])),
            max(0.0, start),
            min(column_hi, float(row["surface_x"]) + 65.0),
            min(float(page.height), max(start + 1.0, end)),
        )
        provenance = {
            "source_section": "latest_vocabulary",
            "source_year": int(year_match.group("year")),
        }
        cells.extend(
            (
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=str(row["row"]),
                    role="lexeme_surface",
                    raw_text=str(row["surface"]),
                    characters=surface_chars,
                    fallback_bbox=surface_bbox,
                    inspection_bbox=inspection_bbox,
                    extraction_provenance=provenance,
                ),
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=str(row["row"]),
                    role="lexeme_reading",
                    raw_text=reading,
                    characters=reading_chars,
                    fallback_bbox=surface_bbox,
                    inspection_bbox=inspection_bbox,
                    status="accepted" if reading else "excluded",
                    status_reason=None if reading else "source_has_no_explicit_reading",
                    confidence=0.99 if reading else 1.0,
                    extraction_provenance=provenance,
                ),
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=str(row["row"]),
                    role="pos",
                    raw_text="",
                    characters=(),
                    fallback_bbox=fallback_bbox,
                    inspection_bbox=inspection_bbox,
                    status="excluded",
                    status_reason="source_has_no_explicit_pos",
                    extraction_provenance=provenance,
                ),
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=str(row["row"]),
                    role="meaning",
                    raw_text=meaning,
                    characters=meaning_chars,
                    fallback_bbox=fallback_bbox,
                    inspection_bbox=inspection_bbox,
                    extraction_provenance=provenance,
                ),
            )
        )
    return _ordinary_page_result(cells, len(rows))


def _hackers_row_reading_key(row: Mapping[str, Any]) -> tuple[int, float, float]:
    return (
        int(row["half"]),
        float(row["top"]),
        float(row["surface_x"]),
    )


def _hackers_usage_marker(page: Any, marker_kind: str) -> tuple[int, float]:
    markers: list[tuple[int, float, str]] = []
    half_width = float(page.width) / 2.0
    for half, (left, right) in enumerate(
        ((0.0, half_width), (half_width, float(page.width)))
    ):
        characters = [
            char
            for char in page.chars
            if left <= float(char["x0"]) < right
        ]
        for line in _cluster_character_lines(characters):
            text = "".join(str(char.get("text", "")) for char in line)
            compact = re.sub(
                r"\s+", "", unicodedata.normalize("NFKC", text)
            )
            is_marker = (
                (marker_kind == "usage" and compact == "유의표현")
                or (marker_kind == "vocabulary" and compact == "용법")
                or (
                    marker_kind == "phrase"
                    and (
                        compact == "출제예상구"
                        or ("구" in compact and "유의표현" in compact)
                    )
                )
            )
            if is_marker:
                markers.append(
                    (half, min(float(char["top"]) for char in line), compact)
                )
    if len(markers) != 1:
        raise TextLayoutError(
            f"Hackers {marker_kind} transition requires one marker: {markers}"
        )
    return markers[0][0], markers[0][1]


def _split_hackers_rows_at_marker(
    rows: Sequence[Mapping[str, Any]], marker: tuple[int, float]
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    before: list[Mapping[str, Any]] = []
    after: list[Mapping[str, Any]] = []
    for row in rows:
        row_position = (int(row["half"]), float(row["top"]))
        if row_position < marker:
            before.append(row)
        elif row_position > marker:
            after.append(row)
        else:
            raise TextLayoutError(
                f"Hackers row overlaps a section marker: {row['row']}"
            )
    if not before or not after:
        raise TextLayoutError(
            f"Hackers transition did not split rows on both sides: {marker}"
        )
    return before, after


def _hackers_usage_regions(
    page: Any,
    rows: Sequence[Mapping[str, Any]],
    layout_id: str,
) -> dict[str, list[Mapping[str, Any]]]:
    if layout_id == "hackers_usage_lexemes":
        return {"lexeme": list(rows)}
    if layout_id == "hackers_usage_phrases":
        return {"phrase": list(rows)}
    if layout_id == "hackers_vocab_to_usage_lexemes":
        ordinary, lexemes = _split_hackers_rows_at_marker(
            rows, _hackers_usage_marker(page, "usage")
        )
        return {"ordinary": ordinary, "lexeme": lexemes}
    if layout_id == "hackers_usage_lexemes_to_phrases":
        lexemes, phrases = _split_hackers_rows_at_marker(
            rows, _hackers_usage_marker(page, "phrase")
        )
        return {"lexeme": lexemes, "phrase": phrases}
    if layout_id == "hackers_usage_lexemes_to_vocab":
        lexemes, ordinary = _split_hackers_rows_at_marker(
            rows, _hackers_usage_marker(page, "vocabulary")
        )
        return {"lexeme": lexemes, "ordinary": ordinary}
    if layout_id == "hackers_usage_phrases_to_vocab":
        phrases, ordinary = _split_hackers_rows_at_marker(
            rows, _hackers_usage_marker(page, "vocabulary")
        )
        return {"phrase": phrases, "ordinary": ordinary}
    raise TextLayoutError(f"unsupported Hackers usage layout: {layout_id}")


def _hackers_usage_row_groups(
    page: Any,
    rows: Sequence[Mapping[str, Any]],
    *,
    level: int,
) -> list[tuple[int, list[Mapping[str, Any]]]]:
    """Group usage rows from the publisher's physical table geometry."""
    if not rows:
        return []
    invalid_halves = sorted(
        {int(row["half"]) for row in rows} - {0, 1}
    )
    if invalid_halves:
        raise TextLayoutError(f"Hackers rows use invalid halves: {invalid_halves}")

    if level == 2:
        target_rows = sorted(
            (row for row in rows if int(row["half"]) == 0),
            key=_hackers_row_reading_key,
        )
        if not target_rows:
            raise TextLayoutError("Hackers N2 usage region has no target column")
        parents = list(range(len(target_rows)))

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(first: int, second: int) -> None:
            first_root = find(first)
            second_root = find(second)
            if first_root != second_root:
                parents[second_root] = first_root

        comparison_matches: list[
            tuple[Mapping[str, Any], list[int]]
        ] = []
        for row in sorted(
            (item for item in rows if int(item["half"]) == 1),
            key=_hackers_row_reading_key,
        ):
            matching_targets = [
                index
                for index, target in enumerate(target_rows)
                if abs(float(target["top"]) - float(row["top"])) <= 20.0
            ]
            if not matching_targets:
                raise TextLayoutError(
                    "Hackers N2 comparison row has no horizontal target: "
                    f"{row['row']}"
                )
            if len(matching_targets) > 2:
                raise TextLayoutError(
                    "Hackers N2 comparison row spans too many targets: "
                    f"{row['row']} targets={matching_targets}"
                )
            for target_index in matching_targets[1:]:
                union(matching_targets[0], target_index)
            comparison_matches.append((row, matching_targets))

        component_targets: dict[int, list[tuple[int, Mapping[str, Any]]]] = {}
        for target_index, target in enumerate(target_rows):
            component_targets.setdefault(find(target_index), []).append(
                (target_index, target)
            )
        component_comparisons: dict[int, list[Mapping[str, Any]]] = {}
        for comparison, matching_targets in comparison_matches:
            component_comparisons.setdefault(
                find(matching_targets[0]), []
            ).append(comparison)

        n2_grouped_rows: list[tuple[int, list[Mapping[str, Any]]]] = []
        for component, indexed_targets in component_targets.items():
            comparisons = component_comparisons.get(component, [])
            if not comparisons:
                raise TextLayoutError(
                    "Hackers N2 target row has no comparison: "
                    f"targets={[row['row'] for _index, row in indexed_targets]}"
                )
            stable_group_number = min(
                target_index for target_index, _row in indexed_targets
            ) + 1
            n2_grouped_rows.append(
                (
                    stable_group_number,
                    [
                        *(
                            row
                            for _index, row in sorted(
                                indexed_targets, key=lambda item: item[0]
                            )
                        ),
                        *sorted(comparisons, key=_hackers_row_reading_key),
                    ],
                )
            )
        n2_grouped_rows.sort(key=lambda item: item[0])
        return n2_grouped_rows

    divider_grouped_rows: list[list[Mapping[str, Any]]] = []
    for half in (0, 1):
        half_rows = sorted(
            (row for row in rows if int(row["half"]) == half),
            key=_hackers_row_reading_key,
        )
        if not half_rows:
            continue
        surface_x = float(
            statistics.median(float(row["surface_x"]) for row in half_rows)
        )
        row_top = min(float(row["top"]) for row in half_rows)
        row_bottom = max(
            float(row.get("bottom_top", row["top"])) for row in half_rows
        )
        horizontal_boundaries = _cluster_geometry_positions(
            [
                (float(line["top"]) + float(line["bottom"])) / 2.0
                for line in page.lines
                if abs(float(line["top"]) - float(line["bottom"])) <= 1.0
                and float(line["x1"]) - float(line["x0"]) >= 30.0
                and float(line["x0"]) - 1.0
                <= surface_x
                <= float(line["x1"]) + 1.0
                and row_top - 40.0
                <= (float(line["top"]) + float(line["bottom"])) / 2.0
                <= row_bottom + 40.0
            ],
            tolerance=0.6,
        )
        if not horizontal_boundaries:
            raise TextLayoutError(
                f"Hackers usage region has no horizontal dividers in half {half}"
            )
        half_groups_by_interval: dict[int, list[Mapping[str, Any]]] = {}
        for row in half_rows:
            interval_index = sum(
                boundary < float(row["top"])
                for boundary in horizontal_boundaries
            )
            half_groups_by_interval.setdefault(interval_index, []).append(row)
        for interval_index, group in sorted(half_groups_by_interval.items()):
            interval_top = (
                horizontal_boundaries[interval_index - 1]
                if interval_index > 0
                else float("-inf")
            )
            interval_bottom = (
                horizontal_boundaries[interval_index]
                if interval_index < len(horizontal_boundaries)
                else float("inf")
            )
            checkbox_anchors = {
                (round(float(rect["top"]), 3), round(float(rect["x0"]), 3))
                for rect in page.rects
                if 4.0 <= float(rect.get("width", 0.0)) <= 10.0
                and 4.0 <= float(rect.get("height", 0.0)) <= 10.0
                and surface_x - 25.0
                <= float(rect["x0"])
                <= surface_x - 5.0
                and interval_top < float(rect["top"]) < interval_bottom
            }
            if len(checkbox_anchors) != 1:
                raise TextLayoutError(
                    "Hackers usage divider interval requires one checkbox: "
                    f"half={half} interval={interval_index} "
                    f"rows={[row['row'] for row in group]} "
                    f"checkboxes={sorted(checkbox_anchors)}"
                )
            divider_grouped_rows.append(
                sorted(group, key=_hackers_row_reading_key)
            )
    return list(enumerate(divider_grouped_rows, start=1))


def _hackers_usage_dispositions(
    page: Any,
    rows: Sequence[Mapping[str, Any]],
    *,
    source_id: str,
    page_number: int,
    layout_id: str,
    level: int,
) -> dict[str, tuple[str, str | None]]:
    regions = _hackers_usage_regions(page, rows, layout_id)
    dispositions: dict[str, tuple[str, str | None]] = {}

    for row in regions.get("ordinary", []):
        dispositions[str(row["row"])] = ("ordinary", None)

    for region_name in ("lexeme", "phrase"):
        region_rows = regions.get(region_name, [])
        groups = _hackers_usage_row_groups(page, region_rows, level=level)
        for group_index, group in groups:
            group_id = (
                f"{source_id}:p{page_number:04d}:"
                f"{region_name}-g{group_index:02d}"
            )
            for row_index, row in enumerate(group):
                row_id = str(row["row"])
                if row_id in dispositions:
                    raise TextLayoutError(
                        f"Hackers usage row has multiple dispositions: {row_id}"
                    )
                if region_name == "phrase":
                    usage_role = "phrase"
                elif level == 2:
                    usage_role = (
                        "target" if int(row["half"]) == 0 else "comparison"
                    )
                else:
                    usage_role = "target" if row_index == 0 else "comparison"
                dispositions[row_id] = (usage_role, group_id)

    expected_rows = {str(row["row"]) for row in rows}
    if set(dispositions) != expected_rows:
        missing = sorted(expected_rows - set(dispositions))
        extra = sorted(set(dispositions) - expected_rows)
        raise TextLayoutError(
            f"Hackers usage disposition mismatch: missing={missing} extra={extra}"
        )
    return dispositions


def _reference_cell_from_hackers_row(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    row_id: str,
    row_cells: Sequence[Mapping[str, Any]],
    inspection_bbox: Sequence[float],
    usage_role: str,
    usage_group_id: str,
) -> dict[str, Any]:
    bboxes = [[float(value) for value in cell["bbox"]] for cell in row_cells]
    normalized = (
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    )
    point_bbox = (
        normalized[0] * float(page.width),
        normalized[1] * float(page.height),
        normalized[2] * float(page.width),
        normalized[3] * float(page.height),
    )
    fields = {
        str(cell["role"]): {
            "bbox": cell["bbox"],
            "normalized_text": cell["normalized_text"],
            "status": cell["status"],
        }
        for cell in row_cells
    }
    return _make_geometry_cell(
        page=page,
        source_id=source_id,
        pdf_sha256=pdf_sha256,
        page_number=page_number,
        layout_id=layout_id,
        row_id=row_id,
        role="reference_text",
        bbox=point_bbox,
        inspection_bbox=inspection_bbox,
        extraction_provenance={
            "reference_kind": "hackers_usage_contrast",
            "source_fields": fields,
            "usage_group_id": usage_group_id,
            "usage_role": usage_role,
        },
    )


def parse_hackers_usage_page(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    layout_spec: Mapping[str, Any],
    level: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Promote every source expression while preserving each synonym relation."""
    if layout_id not in HACKERS_USAGE_LAYOUTS:
        raise TextLayoutError(f"unsupported Hackers usage layout: {layout_id}")
    inspection_bbox = layout_spec.get("inspection_bbox")
    if not isinstance(inspection_bbox, list) or len(inspection_bbox) != 4:
        raise TextLayoutError(f"layout lacks inspection bbox: {layout_id}")
    row_cells, rows = _parse_hackers_row_cells(
        page,
        source_id=source_id,
        pdf_sha256=pdf_sha256,
        page_number=page_number,
        layout_id=layout_id,
        layout_spec=layout_spec,
        level=level,
    )
    cells_by_row: dict[str, list[dict[str, Any]]] = {}
    for cell in row_cells:
        cells_by_row.setdefault(str(cell["row_id"]), []).append(cell)
    dispositions = _hackers_usage_dispositions(
        page,
        rows,
        source_id=source_id,
        page_number=page_number,
        layout_id=layout_id,
        level=level,
    )
    lexical_rows = set(dispositions)

    cells: list[dict[str, Any]] = []
    reference_count = 0
    for row in rows:
        row_id = str(row["row"])
        physical_cells = cells_by_row.get(row_id)
        if physical_cells is None or len(physical_cells) != 4:
            raise TextLayoutError(f"Hackers usage row is incomplete: {row_id}")
        usage_role, usage_group_id = dispositions[row_id]
        cells.extend(physical_cells)
        if usage_role == "ordinary":
            continue
        if usage_group_id is None:
            raise TextLayoutError(
                f"Hackers reference row lacks a usage group: {row_id}"
            )
        cells.append(
            _reference_cell_from_hackers_row(
                page,
                source_id=source_id,
                pdf_sha256=pdf_sha256,
                page_number=page_number,
                layout_id=layout_id,
                row_id=row_id,
                row_cells=physical_cells,
                inspection_bbox=inspection_bbox,
                usage_role=usage_role,
                usage_group_id=usage_group_id,
            )
        )
        reference_count += 1

    declared_role_counts = {
        "reference_text": reference_count,
        "lexeme_surface": len(lexical_rows),
        "lexeme_reading": len(lexical_rows),
        "pos": len(lexical_rows),
        "meaning": len(lexical_rows),
    }
    reconciliation = reconcile_page_cells(
        cells, declared_role_counts=declared_role_counts
    )
    candidates = build_lexeme_candidates(cells)
    if len(candidates) != len(lexical_rows):
        raise TextLayoutError(
            "Hackers usage lexical rows did not reconcile: "
            f"rows={len(lexical_rows)} candidates={len(candidates)}"
        )
    return cells, candidates, reconciliation


def _dongyang_rows_with_groups(page: Any, level: int) -> list[dict[str, Any]]:
    _start, _stop, surface_size, _reading_size = DONGYANG_CONFIG[level]
    rows: list[dict[str, Any]] = []
    halves = ((0.0, float(page.width) / 2.0), (float(page.width) / 2.0, float(page.width)))
    for half, (lo, hi) in enumerate(halves):
        surface_chars = [
            char
            for char in page.chars
            if lo < float(char["x0"]) < hi
            and abs(float(char["size"]) - surface_size) < 0.25
        ]
        surface_groups = [
            group
            for group in cluster_chars(surface_chars, tolerance=0.7)
            if contains_japanese(chars_text(group).replace("□", ""))
        ]
        checkbox_tops = sorted(
            float(rect["top"])
            for rect in page.rects
            if 4.0 <= float(rect.get("width", 0.0)) <= 10.0
            and 4.0 <= float(rect.get("height", 0.0)) <= 10.0
            and lo + 5.0 <= float(rect["x0"]) <= lo + 40.0
        )
        grouped: dict[tuple[str, int], list[list[dict[str, Any]]]] = {}
        for line_index, group in enumerate(surface_groups):
            group_top = sum(float(char["top"]) for char in group) / len(group)
            if checkbox_tops:
                checkbox_index = min(
                    range(len(checkbox_tops)),
                    key=lambda index: abs(checkbox_tops[index] - group_top),
                )
                if abs(checkbox_tops[checkbox_index] - group_top) <= 25.0:
                    key = ("checkbox", checkbox_index)
                else:
                    key = ("line", line_index)
            else:
                key = ("line", line_index)
            grouped.setdefault(key, []).append(group)

        logical_groups = sorted(
            grouped.values(),
            key=lambda groups: min(float(char["top"]) for group in groups for char in group),
        )
        for row_index, groups in enumerate(logical_groups, start=1):
            groups.sort(
                key=lambda group: sum(float(char["top"]) for char in group)
                / len(group)
            )
            surface = "".join(
                chars_text(line).replace("□", "") for line in groups
            )
            group = [char for line in groups for char in line]
            rows.append(
                {
                    "row": f"c{half + 1}-r{row_index}",
                    "half": half,
                    "surface": surface,
                    "top": min(
                        sum(float(char["top"]) for char in line) / len(line)
                        for line in groups
                    ),
                    "surface_group": group,
                    "surface_groups": groups,
                }
            )
    return rows


def parse_dongyang_vocab_page(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    layout_spec: Mapping[str, Any],
    level: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Parse one Dongyang two-column vocabulary page into typed cells."""
    if layout_id != "dongyang_vocab_two_column":
        raise TextLayoutError(f"unsupported Dongyang vocabulary layout: {layout_id}")
    inspection_bbox = layout_spec.get("inspection_bbox")
    if not isinstance(inspection_bbox, list) or len(inspection_bbox) != 4:
        raise TextLayoutError(f"layout lacks inspection bbox: {layout_id}")
    _start, _stop, _surface_size, reading_size = DONGYANG_CONFIG[level]
    rows = _dongyang_rows_with_groups(page, level)
    if not rows:
        raise TextLayoutError(f"Dongyang page has no vocabulary rows: {page_number}")
    cells: list[dict[str, Any]] = []
    for row in rows:
        same_half_tops = sorted(
            float(item["top"])
            for item in rows
            if item["half"] == row["half"] and float(item["top"]) > float(row["top"])
        )
        end = (
            same_half_tops[0] - 1.0
            if same_half_tops
            else float(inspection_bbox[3]) * float(page.height)
        )
        half_width = float(page.width) / 2.0
        lo, hi = (
            (0.0, half_width)
            if int(row["half"]) == 0
            else (half_width, float(page.width))
        )
        surface_chars = list(row["surface_group"])
        surface_bbox = _point_bbox(
            surface_chars,
            (lo + 1.0, float(row["top"]), lo + 2.0, float(row["top"]) + 1.0),
        )
        reading = "".join(
            dongyang_reading(
                page, int(row["half"]), list(group), reading_size
            )
            for group in row.get("surface_groups", [surface_chars])
        )
        reading_chars = [
            char
            for char in page.chars
            if lo <= float(char["x0"]) < hi
            and float(row["top"]) - 8.0 <= float(char["top"]) < end
            and "Mincho" in str(char.get("fontname", ""))
            and JAPANESE_CHAR_RE.search(str(char.get("text", "")))
        ]
        meaning_chars = [
            char
            for char in page.chars
            if lo <= float(char["x0"]) < hi
            and float(row["top"]) - 1.0 <= float(char["top"]) < end
            and "YDVYGOStd11" in str(char.get("fontname", ""))
            and float(char["size"]) >= 7.2
        ]
        meaning = meaning_text(meaning_chars)
        if not meaning and int(row["half"]) == 0 and not same_half_tops:
            first_right_top = min(
                (
                    float(item["top"])
                    for item in rows
                    if int(item["half"]) == 1
                ),
                default=float(inspection_bbox[3]) * float(page.height),
            )
            overflow_chars = [
                char
                for char in page.chars
                if half_width <= float(char["x0"]) < float(page.width)
                and float(inspection_bbox[1]) * float(page.height)
                <= float(char["top"])
                < first_right_top
                and "YDVYGOStd11" in str(char.get("fontname", ""))
                and float(char["size"]) >= 7.2
            ]
            overflow_meaning = meaning_text(overflow_chars)
            if overflow_meaning:
                meaning_chars = overflow_chars
                meaning = overflow_meaning
        row_id = str(row["row"])
        inspection_points = (
            float(inspection_bbox[0]) * float(page.width),
            float(inspection_bbox[1]) * float(page.height),
            float(inspection_bbox[2]) * float(page.width),
            float(inspection_bbox[3]) * float(page.height),
        )
        fallback = (
            max(lo, inspection_points[0]),
            max(float(row["top"]) - 8.0, inspection_points[1]),
            min(hi, inspection_points[2]),
            min(end, inspection_points[3]),
        )
        cells.extend(
            (
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=row_id,
                    role="lexeme_surface",
                    raw_text=str(row["surface"]),
                    characters=surface_chars,
                    fallback_bbox=surface_bbox,
                    inspection_bbox=inspection_bbox,
                ),
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=row_id,
                    role="lexeme_reading",
                    raw_text=reading,
                    characters=reading_chars if reading else (),
                    fallback_bbox=surface_bbox,
                    inspection_bbox=inspection_bbox,
                    status="accepted" if reading else "excluded",
                    status_reason=None if reading else "source_has_no_explicit_reading",
                    confidence=0.99 if reading else 1.0,
                ),
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=row_id,
                    role="pos",
                    raw_text="",
                    characters=(),
                    fallback_bbox=fallback,
                    inspection_bbox=inspection_bbox,
                    status="excluded",
                    status_reason="source_has_no_explicit_pos",
                ),
                _make_aggregate_text_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=row_id,
                    role="meaning",
                    raw_text=meaning,
                    characters=meaning_chars,
                    fallback_bbox=fallback,
                    inspection_bbox=inspection_bbox,
                    status="accepted" if meaning else "pending_review",
                    status_reason=None if meaning else "meaning_not_detected",
                    confidence=1.0 if meaning else 0.0,
                ),
            )
        )
    return _ordinary_page_result(cells, len(rows))


def _points_bbox(
    normalized_bbox: Sequence[float], page: Any
) -> tuple[float, float, float, float]:
    return (
        float(normalized_bbox[0]) * float(page.width),
        float(normalized_bbox[1]) * float(page.height),
        float(normalized_bbox[2]) * float(page.width),
        float(normalized_bbox[3]) * float(page.height),
    )


def _chars_in_bbox(
    page: Any,
    bbox: Sequence[float],
    *,
    font_names: Sequence[str],
    minimum_size: float,
) -> list[dict[str, Any]]:
    x0, top, x1, bottom = bbox
    selected = [
        char
        for char in page.chars
        if x0
        <= (float(char["x0"]) + float(char["x1"])) / 2.0
        <= x1
        and top
        <= (float(char["top"]) + float(char["bottom"])) / 2.0
        <= bottom
        and any(name in str(char.get("fontname", "")) for name in font_names)
        and float(char.get("size", 0.0)) >= minimum_size
    ]
    selected.sort(key=lambda char: (float(char["top"]), float(char["x0"])))
    return selected


def parse_dongyang_synonym_page(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    layout_spec: Mapping[str, Any],
    level: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Promote both sides of each explicit Dongyang synonym pair."""
    if layout_id != "dongyang_synonym_reference":
        raise TextLayoutError(
            f"unsupported Dongyang synonym layout: {layout_id}"
        )
    inspection_bbox = layout_spec.get("inspection_bbox")
    if not isinstance(inspection_bbox, list) or len(inspection_bbox) != 4:
        raise TextLayoutError(f"layout lacks inspection bbox: {layout_id}")
    if level not in DONGYANG_CONFIG:
        raise TextLayoutError(f"invalid Dongyang level: {level}")
    _start, _stop, _surface_size, reading_size = DONGYANG_CONFIG[level]
    references = parse_synonym_page(
        page,
        source_id=source_id,
        pdf_sha256=pdf_sha256,
        jlpt_level=f"N{level}",
        page_number=page_number,
    )
    cells: list[dict[str, Any]] = []
    for reference_index, reference in enumerate(references, start=1):
        reference_id = str(reference["reference_id"])
        field_provenance = reference.get("field_provenance")
        if not isinstance(field_provenance, Mapping):
            raise TextLayoutError(
                f"Dongyang synonym lacks field provenance: {reference_id}"
            )
        reference_bbox = _points_bbox(reference["bbox"], page)
        cells.append(
            _make_geometry_cell(
                page=page,
                source_id=source_id,
                pdf_sha256=pdf_sha256,
                page_number=page_number,
                layout_id=layout_id,
                row_id=f"synonym-{reference_index:02d}",
                role="reference_text",
                bbox=reference_bbox,
                inspection_bbox=inspection_bbox,
                extraction_provenance={
                    "reference_id": reference_id,
                    "reference_kind": "dongyang_synonym_pair",
                    "source_section": "paraphrase",
                },
            )
        )
        for side in ("primary", "comparison"):
            japanese_field = field_provenance.get(f"{side}_japanese")
            korean_field = field_provenance.get(f"{side}_korean")
            item = reference.get(side)
            if (
                not isinstance(japanese_field, Mapping)
                or not isinstance(korean_field, Mapping)
                or not isinstance(item, Mapping)
            ):
                raise TextLayoutError(
                    f"Dongyang synonym side is incomplete: {reference_id}/{side}"
                )
            japanese_bbox = _points_bbox(japanese_field["bbox"], page)
            korean_bbox = _points_bbox(korean_field["bbox"], page)
            surface_chars = _chars_in_bbox(
                page,
                japanese_bbox,
                font_names=("DFHSGothic", "DFHSMincho-W5"),
                minimum_size=10.0,
            )
            meaning_chars = _chars_in_bbox(
                page,
                korean_bbox,
                font_names=("YDVYGOStd11",),
                minimum_size=7.0,
            )
            surface = str(item.get("japanese", "")).strip()
            meaning = str(item.get("korean", "")).strip()
            if not surface_chars or not surface or not meaning:
                raise TextLayoutError(
                    f"Dongyang synonym lexical side is empty: {reference_id}/{side}"
                )
            half = 0 if japanese_bbox[0] < float(page.width) / 2.0 else 1
            reading = dongyang_reading(
                page, half, surface_chars, reading_size
            )
            if not reading:
                raise TextLayoutError(
                    f"Dongyang synonym reading is empty: {reference_id}/{side}"
                )
            reading_chars = [
                char
                for char in page.chars
                if japanese_bbox[0] - 2.0 <= float(char["x0"])
                and float(char["x1"]) <= japanese_bbox[2] + 2.0
                and japanese_bbox[1] - 10.0 <= float(char["top"])
                and float(char["bottom"]) <= japanese_bbox[3]
                and "Mincho" in str(char.get("fontname", ""))
                and JAPANESE_CHAR_RE.search(str(char.get("text", "")))
            ]
            row_id = f"synonym-{reference_index:02d}-{side}"
            lexical_provenance = {
                "reference_id": reference_id,
                "reference_kind": "dongyang_synonym_pair",
                "relation_role": side,
                "source_section": "paraphrase",
            }
            cells.extend(
                (
                    _make_aggregate_text_cell(
                        page=page,
                        source_id=source_id,
                        pdf_sha256=pdf_sha256,
                        page_number=page_number,
                        layout_id=layout_id,
                        row_id=row_id,
                        role="lexeme_surface",
                        raw_text=surface,
                        characters=surface_chars,
                        fallback_bbox=japanese_bbox,
                        inspection_bbox=inspection_bbox,
                        extraction_provenance=lexical_provenance,
                    ),
                    _make_aggregate_text_cell(
                        page=page,
                        source_id=source_id,
                        pdf_sha256=pdf_sha256,
                        page_number=page_number,
                        layout_id=layout_id,
                        row_id=row_id,
                        role="lexeme_reading",
                        raw_text=reading,
                        characters=reading_chars or surface_chars,
                        fallback_bbox=japanese_bbox,
                        inspection_bbox=inspection_bbox,
                        confidence=0.99,
                        extraction_provenance=lexical_provenance,
                    ),
                    _make_aggregate_text_cell(
                        page=page,
                        source_id=source_id,
                        pdf_sha256=pdf_sha256,
                        page_number=page_number,
                        layout_id=layout_id,
                        row_id=row_id,
                        role="pos",
                        raw_text="",
                        characters=(),
                        fallback_bbox=japanese_bbox,
                        inspection_bbox=inspection_bbox,
                        status="excluded",
                        status_reason="source_has_no_explicit_pos",
                        extraction_provenance=lexical_provenance,
                    ),
                    _make_aggregate_text_cell(
                        page=page,
                        source_id=source_id,
                        pdf_sha256=pdf_sha256,
                        page_number=page_number,
                        layout_id=layout_id,
                        row_id=row_id,
                        role="meaning",
                        raw_text=meaning,
                        characters=meaning_chars,
                        fallback_bbox=korean_bbox,
                        inspection_bbox=inspection_bbox,
                        extraction_provenance=lexical_provenance,
                    ),
                )
            )
    declared_role_counts = {
        "reference_text": len(references),
        "lexeme_surface": len(references) * 2,
        "lexeme_reading": len(references) * 2,
        "pos": len(references) * 2,
        "meaning": len(references) * 2,
    }
    reconciliation = reconcile_page_cells(
        cells, declared_role_counts=declared_role_counts
    )
    candidates = build_lexeme_candidates(cells)
    if len(candidates) != len(references) * 2:
        raise TextLayoutError(
            "Dongyang synonym candidates did not reconcile: "
            f"references={len(references)} candidates={len(candidates)}"
        )
    return cells, candidates, reconciliation


def _table_grid_bboxes(
    table: Any, *, expected_rows: int, expected_columns: int, label: str
) -> list[list[tuple[float, float, float, float]]]:
    rows = list(table.rows)
    if len(rows) != expected_rows:
        raise TextLayoutError(
            f"{label} table shape mismatch: rows={len(rows)} expected={expected_rows}"
        )
    header_cells = list(rows[0].cells)
    if len(header_cells) != expected_columns or any(
        cell is None for cell in header_cells
    ):
        raise TextLayoutError(
            f"{label} table shape mismatch: header columns={len(header_cells)}"
        )
    column_bounds = [
        (float(cell[0]), float(cell[2]))
        for cell in header_cells
        if cell is not None
    ]
    grid: list[list[tuple[float, float, float, float]]] = []
    for row_index, row in enumerate(rows):
        row_cells = [cell for cell in row.cells if cell is not None]
        if not row_cells:
            raise TextLayoutError(f"{label} row {row_index} has no geometry")
        top = min(float(cell[1]) for cell in row_cells)
        bottom = max(float(cell[3]) for cell in row_cells)
        grid.append(
            [(x0, top, x1, bottom) for x0, x1 in column_bounds]
        )
    return grid


def _cluster_geometry_positions(
    values: Sequence[float], *, tolerance: float = 1.0
) -> list[float]:
    if not values:
        return []
    clusters: list[list[float]] = []
    for value in sorted(values):
        if not clusters or value - clusters[-1][-1] > tolerance:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [float(statistics.median(cluster)) for cluster in clusters]


def _full_width_table_grid_bboxes(
    page: Any,
    table: Any,
    *,
    expected_rows: int,
    expected_columns: int,
    label: str,
) -> list[list[tuple[float, float, float, float]]]:
    """Recover borderless outer columns from the table's full-width rules.

    pdfplumber's table finder anchors only columns bounded by vertical rules.
    The calendar page intentionally omits the two outer vertical borders, so
    its detected tables lose the first and last columns even though the top and
    bottom horizontal rules preserve every column boundary as segment ends.
    """
    rows = list(table.rows)
    if len(rows) != expected_rows:
        raise TextLayoutError(
            f"{label} table shape mismatch: rows={len(rows)} expected={expected_rows}"
        )
    row_bounds: list[tuple[float, float]] = []
    for row_index, row in enumerate(rows):
        row_cells = [cell for cell in row.cells if cell is not None]
        if not row_cells:
            raise TextLayoutError(f"{label} row {row_index} has no geometry")
        row_bounds.append(
            (
                min(float(cell[1]) for cell in row_cells),
                max(float(cell[3]) for cell in row_cells),
            )
        )
    table_top = row_bounds[0][0]
    table_bottom = row_bounds[-1][1]
    endpoints: list[float] = []
    for line in page.lines:
        x0 = float(line["x0"])
        x1 = float(line["x1"])
        top = float(line["top"])
        bottom = float(line["bottom"])
        if x1 - x0 <= 1.0 or abs(bottom - top) > 1.0:
            continue
        line_y = (top + bottom) / 2.0
        if min(abs(line_y - table_top), abs(line_y - table_bottom)) > 1.0:
            continue
        endpoints.extend((x0, x1))
    column_boundaries = _cluster_geometry_positions(endpoints)
    if len(column_boundaries) != expected_columns + 1:
        raise TextLayoutError(
            f"{label} full-width rule mismatch: boundaries="
            f"{len(column_boundaries)} expected={expected_columns + 1}"
        )
    if any(
        right - left <= 1.0
        for left, right in zip(column_boundaries, column_boundaries[1:])
    ):
        raise TextLayoutError(f"{label} contains a collapsed column")
    return [
        [
            (left, top, right, bottom)
            for left, right in zip(column_boundaries, column_boundaries[1:])
        ]
        for top, bottom in row_bounds
    ]


def _cell_fragments(page: Any, bbox: Sequence[float]) -> list[dict[str, Any]]:
    x0, top, x1, bottom = bbox
    characters = [
        char
        for char in page.chars
        if x0 <= (float(char["x0"]) + float(char["x1"])) / 2.0 < x1
        and top <= (float(char["top"]) + float(char["bottom"])) / 2.0 < bottom
    ]
    characters.sort(key=lambda char: (round(float(char["top"]), 3), float(char["x0"])))
    cell_bbox = _normalized_bbox(bbox, float(page.width), float(page.height))
    fragments: list[dict[str, Any]] = []
    for char in characters:
        char_bbox = _normalized_bbox(
            (
                max(x0, float(char["x0"])),
                max(top, float(char["top"])),
                min(x1, float(char["x1"])),
                min(bottom, float(char["bottom"])),
            ),
            float(page.width),
            float(page.height),
        )
        if char_bbox[0] >= char_bbox[2] or char_bbox[1] >= char_bbox[3]:
            continue
        fragments.append(
            {
                "text": str(char["text"]),
                "bbox": char_bbox,
                "font_name": str(char.get("fontname", "")) or None,
                "font_size": float(char["size"]),
            }
        )
    if not fragments:
        fragments.append(
            {
                "text": "",
                "bbox": cell_bbox,
                "font_name": None,
                "font_size": None,
            }
        )
    return fragments


def _make_geometry_cell(
    *,
    page: Any,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    row_id: str,
    role: str,
    bbox: Sequence[float],
    inspection_bbox: Sequence[float],
    exclude_empty: bool = False,
    extraction_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_bbox = _normalized_bbox(
        bbox, float(page.width), float(page.height)
    )
    if not _bbox_within(inspection_bbox, normalized_bbox):
        raise TextLayoutError(
            f"{layout_id} cell escapes declared inspection bbox: {row_id}"
        )
    fragments = _cell_fragments(page, bbox)
    raw_text = "".join(str(fragment["text"]) for fragment in fragments)
    excluded = exclude_empty and not raw_text.strip()
    return make_cell(
        source_id=source_id,
        pdf_sha256=pdf_sha256,
        page=page_number,
        layout_id=layout_id,
        row_id=row_id,
        role=role,
        bbox=normalized_bbox,
        raw_fragments=fragments,
        extraction_method="text_geometry",
        confidence=1.0,
        status="excluded" if excluded else "accepted",
        status_reason="empty_physical_grid_cell" if excluded else None,
        extraction_provenance=extraction_provenance,
    )


def _counter_matrix_cells(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    inspection_bbox: Sequence[float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tables = page.find_tables()
    if len(tables) != 1:
        raise TextLayoutError(
            f"counter matrix table shape mismatch: tables={len(tables)} expected=1"
        )
    grid = _table_grid_bboxes(
        tables[0], expected_rows=12, expected_columns=6, label="counter matrix"
    )
    cells: list[dict[str, Any]] = []
    for row_index, row in enumerate(grid):
        for column_index, bbox in enumerate(row):
            if row_index == 0 and column_index == 0:
                role = "ignored_decoration"
            elif row_index == 0:
                role = "counter_header"
            elif row_index == 11 and column_index == 0:
                role = "query_row_header"
            else:
                role = "counter_example"
            cells.append(
                _make_geometry_cell(
                    page=page,
                    source_id=source_id,
                    pdf_sha256=pdf_sha256,
                    page_number=page_number,
                    layout_id=layout_id,
                    row_id=f"matrix-r{row_index:02d}-c{column_index:02d}",
                    role=role,
                    bbox=bbox,
                    inspection_bbox=inspection_bbox,
                    exclude_empty=role == "ignored_decoration",
                )
            )
    reconciliation = reconcile_page_cells(
        cells,
        declared_role_counts={
            "counter_example": 65,
            "counter_header": 5,
            "ignored_decoration": 1,
            "query_row_header": 1,
        },
    )
    return cells, reconciliation


def _calendar_grid_cells(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    inspection_bbox: Sequence[float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tables = sorted(page.find_tables(), key=lambda table: float(table.bbox[1]))
    if len(tables) != 2:
        raise TextLayoutError(
            f"calendar grid table shape mismatch: tables={len(tables)} expected=2"
        )
    expected_shapes = ((2, 6), (6, 7))
    cells: list[dict[str, Any]] = []
    for table_index, (table, (row_count, column_count)) in enumerate(
        zip(tables, expected_shapes)
    ):
        grid = _full_width_table_grid_bboxes(
            page,
            table,
            expected_rows=row_count,
            expected_columns=column_count,
            label=f"calendar grid {table_index}",
        )
        for row_index, row in enumerate(grid):
            for column_index, bbox in enumerate(row):
                cells.append(
                    _make_geometry_cell(
                        page=page,
                        source_id=source_id,
                        pdf_sha256=pdf_sha256,
                        page_number=page_number,
                        layout_id=layout_id,
                        row_id=(
                            f"calendar-t{table_index:02d}-r{row_index:02d}-"
                            f"c{column_index:02d}"
                        ),
                        role="calendar_lexeme",
                        bbox=bbox,
                        inspection_bbox=inspection_bbox,
                        exclude_empty=True,
                        extraction_provenance={
                            "grid_geometry_source": "full_width_horizontal_rules",
                            "table_index": table_index,
                        },
                    )
                )
    reconciliation = reconcile_page_cells(
        cells, declared_role_counts={"calendar_lexeme": 54}
    )
    return cells, reconciliation


def parse_hackers_structured_page(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    layout_spec: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse counter/calendar grids without promoting them to lexeme rows."""
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    inspection_bbox = layout_spec.get("inspection_bbox")
    if not isinstance(inspection_bbox, list) or len(inspection_bbox) != 4:
        raise TextLayoutError(f"layout lacks inspection bbox: {layout_id}")
    if layout_id == "hackers_counter_matrix":
        return _counter_matrix_cells(
            page,
            source_id=source_id,
            pdf_sha256=pdf_sha256,
            page_number=page_number,
            layout_id=layout_id,
            inspection_bbox=inspection_bbox,
        )
    if layout_id == "hackers_calendar_grid":
        return _calendar_grid_cells(
            page,
            source_id=source_id,
            pdf_sha256=pdf_sha256,
            page_number=page_number,
            layout_id=layout_id,
            inspection_bbox=inspection_bbox,
        )
    raise TextLayoutError(f"unsupported structured layout: {layout_id}")


def _cluster_character_lines(
    characters: Sequence[Mapping[str, Any]], *, tolerance: float = 1.5
) -> list[list[Mapping[str, Any]]]:
    lines: list[list[Mapping[str, Any]]] = []
    anchors: list[float] = []
    for char in sorted(
        characters, key=lambda item: (float(item["top"]), float(item["x0"]))
    ):
        top = float(char["top"])
        match = next(
            (
                index
                for index, anchor in enumerate(anchors)
                if abs(top - anchor) <= tolerance
            ),
            None,
        )
        if match is None:
            anchors.append(top)
            lines.append([char])
        else:
            lines[match].append(char)
            anchors[match] = sum(float(item["top"]) for item in lines[match]) / len(
                lines[match]
            )
    for line in lines:
        line.sort(key=lambda item: float(item["x0"]))
    return lines


def _line_bbox(line: Sequence[Mapping[str, Any]]) -> tuple[float, float, float, float]:
    return (
        min(float(char["x0"]) for char in line),
        min(float(char["top"]) for char in line),
        max(float(char["x1"]) for char in line),
        max(float(char["bottom"]) for char in line),
    )


def _inside_normalized_bbox(
    char: Mapping[str, Any], page: Any, bbox: Sequence[float]
) -> bool:
    center_x = (float(char["x0"]) + float(char["x1"])) / 2.0
    center_y = (float(char["top"]) + float(char["bottom"])) / 2.0
    return (
        float(bbox[0]) * float(page.width)
        <= center_x
        <= float(bbox[2]) * float(page.width)
        and float(bbox[1]) * float(page.height)
        <= center_y
        <= float(bbox[3]) * float(page.height)
    )


def parse_nonlexical_text_page(
    page: Any,
    *,
    source_id: str,
    pdf_sha256: str,
    page_number: int,
    layout_id: str,
    layout_spec: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse explicit grammar/reference layouts without creating lexemes."""
    inspection_bbox = layout_spec.get("inspection_bbox")
    if not isinstance(inspection_bbox, list) or len(inspection_bbox) != 4:
        raise TextLayoutError(f"layout lacks inspection bbox: {layout_id}")
    content_top = float(inspection_bbox[1]) * float(page.height)
    chars = [
        char
        for char in page.chars
        if _inside_normalized_bbox(char, page, inspection_bbox)
        and float(char["top"]) >= content_top
    ]
    if layout_id == "hackers_grammar_patterns":
        selected = [
            char
            for char in chars
            if "KozGoPro-Bold" in str(char.get("fontname", ""))
            and float(char.get("size", 0.0)) >= 8.5
            and float(char["x0"]) < float(page.width) * 0.42
        ]
        role = "grammar_pattern"
    elif layout_id == "dongyang_grammar_checklist":
        selected = [
            char
            for char in chars
            if "DFHSGothic" in str(char.get("fontname", ""))
            and float(char.get("size", 0.0)) >= 9.0
        ]
        role = "grammar_pattern"
    elif layout_id == "dongyang_synonym_reference":
        selected = chars
        role = "reference_text"
    else:
        raise TextLayoutError(f"unsupported nonlexical text layout: {layout_id}")

    lines = [
        line
        for line in _cluster_character_lines(selected)
        if JAPANESE_TEXT_RE.search(
            "".join(str(char.get("text", "")) for char in line)
        )
        or role == "reference_text"
    ]
    if not lines:
        raise TextLayoutError(f"{layout_id} page has no declared text cells")
    cells = [
        _make_geometry_cell(
            page=page,
            source_id=source_id,
            pdf_sha256=pdf_sha256,
            page_number=page_number,
            layout_id=layout_id,
            row_id=f"line-{index:03d}",
            role=role,
            bbox=_line_bbox(line),
            inspection_bbox=inspection_bbox,
        )
        for index, line in enumerate(lines, start=1)
    ]
    reconciliation = reconcile_page_cells(
        cells, declared_role_counts={role: len(cells)}
    )
    if build_lexeme_candidates(cells):
        raise TextLayoutError(f"{layout_id} structural text created lexemes")
    return cells, reconciliation
