"""Text geometry helpers for supported public-builder PDFs.

This module intentionally contains only deterministic text-layer parsing
primitives and no authoring entry points.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from pdfplumber.utils.text import extract_text



HACKERS_READING_SIZE = {1: 5.0, 2: 8.0, 3: 5.0, 4: 5.0, 5: 5.0}
HACKERS_SURFACE_ANCHORS = {
    1: (83.0, 294.0),
    2: (53.0, 252.0),
    3: (83.0, 281.0),
    4: (84.0, 264.0),
    5: (84.0, 264.0),
}
HACKERS_WRAP_GAP = {1: 13.5, 2: 15.5, 3: 13.5, 4: 13.5, 5: 18.5}
DONGYANG_CONFIG = {
    1: (4, 29, 9.5, 5.0),
    2: (4, 32, 9.5, 4.5),
    3: (4, 20, 9.5, 4.5),
    4: (4, 13, 12.0, 5.5),
    5: (4, 13, 12.0, 5.5),
}
JAPANESE_CHAR_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff々〆ヶ～〜]")
KANJI_CHAR_RE = re.compile(r"[\u3400-\u9fff々〆ヶ]")
HACKERS_CONTINUATION_LINE_GAP = 16.0
_FORM_SPACE_RE = re.compile(r"\s+")


def normalize_form(value: str) -> str:
    """Normalize source typography while preserving bound-form markers."""
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.replace("〜", "～").replace("~", "～")
    return _FORM_SPACE_RE.sub("", normalized).strip()


def contains_japanese(value: str) -> bool:
    return JAPANESE_CHAR_RE.search(value) is not None


def cluster_chars(
    chars: Iterable[dict[str, Any]], tolerance: float = 1.5
) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for char in sorted(chars, key=lambda item: (item["top"], item["x0"])):
        if groups:
            group_top = sum(item["top"] for item in groups[-1]) / len(groups[-1])
            if abs(group_top - char["top"]) < tolerance:
                groups[-1].append(char)
                continue
        groups.append([char])
    return groups


def chars_text(chars: Iterable[dict[str, Any]]) -> str:
    ordered = sorted(chars, key=lambda item: item["x0"])
    return "".join(char["text"] for char in ordered).replace(" ", "").strip()


def meaning_text(chars: list[dict[str, Any]]) -> str:
    if not chars:
        return ""
    value = extract_text(chars, x_tolerance=1.5, y_tolerance=2.5).replace("\n", " ")
    return re.sub(r"\s+", " ", value).strip()


def hackers_meaning_chars(
    chars: list[dict[str, Any]], surface_top: float
) -> list[dict[str, Any]]:
    """Keep the meaning line anchored to the surface plus continuations."""
    lines = cluster_chars(chars, tolerance=1.0)
    if not lines:
        return []
    line_tops = [
        sum(char["top"] for char in line) / len(line) for line in lines
    ]
    anchored = [
        index
        for index, line_top in enumerate(line_tops)
        if abs(line_top - surface_top) <= 10.0
    ]
    primary_index = (
        anchored[0]
        if anchored
        else min(
            range(len(lines)),
            key=lambda index: abs(line_tops[index] - surface_top),
        )
    )
    selected = [*lines[primary_index]]
    previous_top = line_tops[primary_index]
    for line in lines[primary_index + 1 :]:
        line_top = sum(char["top"] for char in line) / len(line)
        if line_top - previous_top > HACKERS_CONTINUATION_LINE_GAP:
            break
        selected.extend(line)
        previous_top = line_top
    return selected


def hackers_row_vertical_bounds(
    rows: list[dict[str, Any]], row: dict[str, Any]
) -> tuple[float, float]:
    half_rows = sorted(
        (item for item in rows if item["half"] == row["half"]),
        key=lambda item: item["top"],
    )
    row_index = next(
        index
        for index, item in enumerate(half_rows)
        if item["row"] == row["row"]
    )
    previous = half_rows[row_index - 1] if row_index else None
    following = (
        half_rows[row_index + 1]
        if row_index + 1 < len(half_rows)
        else None
    )
    start = (
        (previous.get("bottom_top", previous["top"]) + row["top"]) / 2.0
        if previous
        else row["top"] - 18.0
    )
    end = (
        (row.get("bottom_top", row["top"]) + following["top"]) / 2.0
        if following
        else row.get("bottom_top", row["top"]) + 18.0
    )
    return start, end


def split_horizontal_groups(
    groups: Iterable[list[dict[str, Any]]], gap: float = 12.0
) -> list[list[dict[str, Any]]]:
    result: list[list[dict[str, Any]]] = []
    for group in groups:
        chunks: list[list[dict[str, Any]]] = []
        for char in sorted(group, key=lambda item: item["x0"]):
            if chunks and char["x0"] - chunks[-1][-1]["x1"] < gap:
                chunks[-1].append(char)
            else:
                chunks.append([char])
        result.extend(chunks)
    return result


def _nearest_reading(
    page: Any,
    *,
    half: int,
    surface_top: float,
    reading_size: float,
    same_line: bool,
    surface_x: float,
) -> str:
    half_width = page.width / 2
    lo, hi = (0, half_width) if half == 0 else (half_width, page.width)
    candidates = [
        char
        for char in page.chars
        if lo < char["x0"] < hi
        and abs(char["size"] - reading_size) < 0.25
        and "KozGoPro-Regular" in char["fontname"]
        and JAPANESE_CHAR_RE.search(char["text"])
    ]
    groups = split_horizontal_groups(cluster_chars(candidates, tolerance=0.9), gap=10.0)
    if same_line:
        target_x = surface_x + 55.0
        groups = [
            group
            for group in groups
            if abs(group[0]["top"] - surface_top) <= 10.0
            and abs(min(char["x0"] for char in group) - target_x) <= 15.0
        ]
        return normalize_form(
            "".join(
                chars_text(group)
                for group in sorted(groups, key=lambda item: item[0]["top"])
            )
        )
    groups = [
        group for group in groups if 2.0 <= surface_top - group[0]["top"] <= 10.0
    ]
    if not groups:
        return ""
    closest = min(
        groups,
        key=lambda group: (
            abs(group[0]["top"] - surface_top),
            abs(min(char["x0"] for char in group) - surface_x),
        ),
    )
    return chars_text(closest)


def _merge_hackers_surface_lines(
    lines: list[dict[str, Any]], max_gap: float
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for half in (0, 1):
        half_lines = sorted(
            (line for line in lines if line["half"] == half),
            key=lambda line: line["top"],
        )
        half_rows: list[dict[str, Any]] = []
        for line in half_lines:
            previous_anchor_count = (
                int(half_rows[-1].get("row_anchor_count", 0)) if half_rows else 0
            )
            current_anchor_count = int(line.get("row_anchor_count", 0))
            if (
                half_rows
                and line["top"] - half_rows[-1]["last_top"] <= max_gap
                and not (previous_anchor_count and current_anchor_count)
            ):
                half_rows[-1]["surface"] += line["surface"]
                half_rows[-1]["surface_groups"].extend(
                    line.get("surface_groups", [])
                )
                half_rows[-1]["last_top"] = line["top"]
                half_rows[-1]["row_anchor_count"] = (
                    previous_anchor_count + current_anchor_count
                )
                continue
            half_rows.append(
                {
                    **line,
                    "surface_groups": list(line.get("surface_groups", [])),
                    "last_top": line["top"],
                }
            )
        merged.extend(half_rows)
    merged.sort(key=lambda row: (row["top"], row["half"]))
    for index, row in enumerate(merged, start=1):
        row["row"] = f"c{row['half'] + 1}-r{index}"
        row["bottom_top"] = row.pop("last_top")
    return merged


def _hackers_line_has_row_anchor(
    page: Any, *, surface_x: float, top: float
) -> bool:
    return any(
        4.0 <= float(rect.get("width", 0.0)) <= 10.0
        and 4.0 <= float(rect.get("height", 0.0)) <= 10.0
        and surface_x - 25.0 <= float(rect["x0"]) <= surface_x - 5.0
        and abs(float(rect["top"]) - top) <= 4.0
        for rect in page.rects
    )


def hackers_surface_rows(
    page: Any, level: int, page_number: int | None = None
) -> list[dict[str, Any]]:
    surface_chars = [
        char for char in page.chars if "KozGoPro-Medium" in char["fontname"]
    ]
    table_layout = level == 5 and page_number is not None and 17 <= page_number <= 20
    groups = split_horizontal_groups(
        cluster_chars(surface_chars), gap=6.0 if table_layout else 12.0
    )
    lines: list[dict[str, Any]] = []
    for group in groups:
        surface_x = min(char["x0"] for char in group)
        anchor_distances = [
            abs(surface_x - anchor) for anchor in HACKERS_SURFACE_ANCHORS[level]
        ]
        if min(anchor_distances) > 15.0:
            continue
        surface = chars_text(group)
        if not contains_japanese(surface):
            continue
        top = sum(char["top"] for char in group) / len(group)
        lines.append(
            {
                "half": anchor_distances.index(min(anchor_distances)),
                "surface": surface,
                "surface_x": surface_x,
                "top": top,
                "surface_groups": [group],
                "row_anchor_count": int(
                    _hackers_line_has_row_anchor(
                        page,
                        surface_x=surface_x,
                        top=top,
                    )
                ),
            }
        )
    return _merge_hackers_surface_lines(lines, HACKERS_WRAP_GAP[level])


def compose_surface_reading(
    surface_chars: list[dict[str, Any]],
    reading_groups: list[list[dict[str, Any]]],
) -> str:
    chars = sorted(
        (char for char in surface_chars if char["text"] != "□"),
        key=lambda char: char["x0"],
    )
    base_runs: list[tuple[int, int, float]] = []
    start: int | None = None
    base_kind: str | None = None
    for index, char in enumerate(chars):
        text = str(char["text"])
        current_kind = (
            "kanji"
            if KANJI_CHAR_RE.fullmatch(text)
            else "digit"
            if text.isdigit()
            else None
        )
        if current_kind is not None:
            if start is None:
                start = index
                base_kind = current_kind
            elif current_kind != base_kind:
                run = chars[start:index]
                base_runs.append(
                    (start, index, (run[0]["x0"] + run[-1]["x1"]) / 2)
                )
                start = index
                base_kind = current_kind
        elif start is not None:
            run = chars[start:index]
            base_runs.append((start, index, (run[0]["x0"] + run[-1]["x1"]) / 2))
            start = None
            base_kind = None
    if start is not None:
        run = chars[start:]
        base_runs.append((start, len(chars), (run[0]["x0"] + run[-1]["x1"]) / 2))
    if not base_runs:
        return chars_text(chars)

    run_boundaries = [
        (
            chars[base_runs[index][1] - 1]["x1"]
            + chars[base_runs[index + 1][0]]["x0"]
        )
        / 2
        for index in range(len(base_runs) - 1)
    ]
    structurally_split_groups: list[list[dict[str, Any]]] = []
    for group in reading_groups:
        chunks: list[list[dict[str, Any]]] = []
        for char in sorted(group, key=lambda item: item["x0"]):
            if chunks and any(
                chunks[-1][-1]["x1"] <= boundary <= char["x0"]
                for boundary in run_boundaries
            ):
                chunks.append([])
            if not chunks:
                chunks.append([])
            chunks[-1].append(char)
        structurally_split_groups.extend(chunk for chunk in chunks if chunk)

    assigned: dict[int, str] = {}
    remaining = set(range(len(base_runs)))
    for group in sorted(
        structurally_split_groups,
        key=lambda item: min(char["x0"] for char in item),
    ):
        if not remaining:
            break
        center = (
            min(char["x0"] for char in group)
            + max(char["x1"] for char in group)
        ) / 2
        target = min(remaining, key=lambda index: abs(base_runs[index][2] - center))
        assigned[target] = chars_text(group)
        remaining.remove(target)

    parts: list[str] = []
    run_by_start = {
        run_start: (index, run_end)
        for index, (run_start, run_end, _center) in enumerate(base_runs)
    }
    index = 0
    while index < len(chars):
        if index in run_by_start:
            run_index, run_end = run_by_start[index]
            parts.append(assigned.get(run_index, chars_text(chars[index:run_end])))
            index = run_end
            continue
        parts.append(chars[index]["text"])
        index += 1
    return normalize_form("".join(parts))


def hackers_reading(page: Any, row: dict[str, Any], level: int) -> str:
    reading_size = 5.0 if level == 2 else HACKERS_READING_SIZE[level]
    half_width = page.width / 2
    lo, hi = (0, half_width) if row["half"] == 0 else (half_width, page.width)

    def compose_group(
        surface_group: list[dict[str, Any]],
    ) -> tuple[str, bool]:
        surface_top = sum(char["top"] for char in surface_group) / len(surface_group)
        surface_lo = min(char["x0"] for char in surface_group) - 4.0
        surface_hi = max(char["x1"] for char in surface_group) + 4.0
        candidates = [
            char
            for char in page.chars
            if lo < char["x0"] < hi
            and surface_lo <= char["x0"] <= surface_hi
            and abs(char["size"] - reading_size) < 0.25
            and "KozGoPro-Regular" in char["fontname"]
            and JAPANESE_CHAR_RE.search(char["text"])
            and 2.0 <= surface_top - char["top"] <= 10.0
        ]
        groups = split_horizontal_groups(
            cluster_chars(candidates, tolerance=0.9), gap=10.0
        )
        return compose_surface_reading(surface_group, groups), bool(groups)

    if level == 2:
        same_line_reading = _nearest_reading(
            page,
            half=row["half"],
            surface_top=row["top"],
            reading_size=HACKERS_READING_SIZE[level],
            same_line=True,
            surface_x=row["surface_x"],
        )
        if same_line_reading:
            reading = normalize_form(same_line_reading)
            for surface_group in row["surface_groups"]:
                surface_top = sum(char["top"] for char in surface_group) / len(
                    surface_group
                )
                surface_x = min(char["x0"] for char in surface_group)
                composed = _nearest_reading(
                    page,
                    half=row["half"],
                    surface_top=surface_top,
                    reading_size=HACKERS_READING_SIZE[level],
                    same_line=True,
                    surface_x=surface_x,
                )
                if not composed and KANJI_CHAR_RE.search(chars_text(surface_group)):
                    composed, has_ruby = compose_group(surface_group)
                    if not has_ruby:
                        continue
                if not composed:
                    continue
                overlap = max(
                    (
                        length
                        for length in range(len(composed) + 1)
                        if reading.endswith(composed[:length])
                    ),
                    default=0,
                )
                reading += composed[overlap:]
            return normalize_form(reading)
    readings = [compose_group(group)[0] for group in row["surface_groups"]]
    return normalize_form("".join(readings))


def dongyang_reading(
    page: Any,
    half: int,
    surface_group: list[dict[str, Any]],
    reading_size: float,
) -> str:
    half_width = page.width / 2
    lo, hi = (0, half_width) if half == 0 else (half_width, page.width)
    surface_top = sum(char["top"] for char in surface_group) / len(surface_group)
    surface_lo = min(char["x0"] for char in surface_group) - 4.0
    surface_hi = max(char["x1"] for char in surface_group) + 4.0
    candidates = [
        char
        for char in page.chars
        if lo < char["x0"] < hi
        and surface_lo <= char["x0"] <= surface_hi
        and (
            abs(char["size"] - reading_size) < 0.25
            or (reading_size == 5.0 and abs(char["size"] - 4.5) < 0.25)
        )
        and "Mincho" in char["fontname"]
        and JAPANESE_CHAR_RE.search(char["text"])
    ]
    line_groups = [
        group
        for group in cluster_chars(candidates, tolerance=0.7)
        if 2.0 <= surface_top - group[0]["top"] <= 8.0
    ]
    if not line_groups:
        return compose_surface_reading(surface_group, [])
    reading_line = min(
        line_groups, key=lambda group: abs(group[0]["top"] - surface_top)
    )
    reading_groups = split_horizontal_groups([reading_line], gap=10.0)
    return compose_surface_reading(surface_group, reading_groups)
