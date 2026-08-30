# pyright: reportMissingImports=false
"""Extract the supported Gilbut kanji booklets for the optional local addon."""

from __future__ import annotations

import html
import re
import statistics
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pdfplumber
from PIL import Image

from direct_release_contract import sha256_file, sha256_json


GILBUT_EXTRACTION_POLICY_VERSION = "public-gilbut-kanji-geometry-v2"
GILBUT_GLYPH_POLICY_VERSION = "public-gilbut-vector-glyph-png-v2"
GILBUT_GLYPH_PNG_RESOLUTION = 576
GILBUT_GLYPH_PNG_PADDING_PIXELS = 16
GILBUT_MEANING_WORD_GAP_POINTS = 0.5
EXPECTED_GILBUT_SLOT_COUNT = 2_337
GILBUT_GLYPH_EQUIVALENTS = MappingProxyType({"戶": ("戸",)})
_NUMBERED_SLOT_RE = re.compile(r"[0-9]{4}")


class PublicKanjiError(ValueError):
    """Raised when public kanji inputs cannot close deterministically."""


@dataclass(frozen=True)
class GilbutPdfSpec:
    source_id: str
    volume_code: str
    first_sequence: int
    first_number: int
    last_number: int
    expected_slot_count: int
    expected_page_count: int
    expected_sha256: str | None
    additional_labels: tuple[str, ...] = ()


GILBUT_UPPER_SPEC = GilbutPdfSpec(
    source_id="ilsang-muutta-upper",
    volume_code="upper",
    first_sequence=1,
    first_number=1,
    last_number=1214,
    expected_slot_count=1223,
    expected_page_count=52,
    expected_sha256="5ccd96a8594c5e869e8f069771cce86b3a72601b591aa861f1264c26fbb0556c",
    additional_labels=tuple(f"추가자{number}" for number in range(1, 10)),
)
GILBUT_LOWER_SPEC = GilbutPdfSpec(
    source_id="ilsang-muutta-lower",
    volume_code="lower",
    first_sequence=1224,
    first_number=1215,
    last_number=2328,
    expected_slot_count=1114,
    expected_page_count=45,
    expected_sha256="0980a68ea9c6055b9c44559c81ed20a5ecf0d59e42d38a3b426a3ea8bf9cb789",
)


@dataclass(frozen=True)
class GilbutKanjiSlot:
    sequence: int
    source_id: str
    source_sha256: str
    volume_code: str
    page: int
    row: int
    column: int
    source_label: str
    glyph_kind: str
    glyph_text: str
    glyph_bbox: tuple[float, float, float, float]
    meaning: str

@dataclass(frozen=True)
class _GilbutHeader:
    label: str
    top: float
    bottom: float
    x0: float
    x1: float

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2


def _word_float(word: Mapping[str, Any], key: str) -> float:
    value = word.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PublicKanjiError(f"Gilbut PDF word lacks numeric {key}")
    return float(value)


def _gilbut_headers(
    words: Sequence[Mapping[str, Any]],
    *,
    page_width: float,
    page_height: float,
    spec: GilbutPdfSpec,
) -> list[_GilbutHeader]:
    headers: list[_GilbutHeader] = []
    for word in words:
        text = str(word.get("text", ""))
        x0 = _word_float(word, "x0")
        x1 = _word_float(word, "x1")
        top = _word_float(word, "top")
        bottom = _word_float(word, "bottom")
        center_x = (x0 + x1) / 2
        if not (
            page_width * 0.08 < center_x < page_width * 0.92
            and page_height * 0.10 < top < page_height * 0.90
        ):
            continue
        if _NUMBERED_SLOT_RE.fullmatch(text) is not None:
            number = int(text)
            if spec.first_number <= number <= spec.last_number:
                headers.append(_GilbutHeader(text, top, bottom, x0, x1))
            continue
        if text != "추가자":
            continue
        number_words = [
            candidate
            for candidate in words
            if str(candidate.get("text", "")).isdigit()
            and len(str(candidate.get("text", ""))) == 1
            and abs(_word_float(candidate, "top") - top) < 1
            and 0 < _word_float(candidate, "x0") - x1 < 8
        ]
        if len(number_words) != 1:
            raise PublicKanjiError(
                f"Gilbut additional-kanji header is ambiguous: {spec.source_id}"
            )
        number_word = number_words[0]
        label = f"추가자{number_word['text']}"
        headers.append(
            _GilbutHeader(
                label=label,
                top=top,
                bottom=max(bottom, _word_float(number_word, "bottom")),
                x0=x0,
                x1=_word_float(number_word, "x1"),
            )
        )
    return headers


def _group_gilbut_rows(
    headers: Sequence[_GilbutHeader],
) -> list[list[_GilbutHeader]]:
    rows: list[list[_GilbutHeader]] = []
    for header in sorted(headers, key=lambda value: (value.top, value.center_x)):
        if not rows or header.top - rows[-1][0].top > 2:
            rows.append([header])
        else:
            rows[-1].append(header)
    for row in rows:
        row.sort(key=lambda value: value.center_x)
        centers = [header.center_x for header in row]
        if len(centers) != len(set(centers)):
            raise PublicKanjiError("Gilbut PDF row has duplicate slot columns")
    return rows


def _group_items_by_line(
    items: Sequence[Mapping[str, Any]],
) -> list[list[Mapping[str, Any]]]:
    lines: list[list[Mapping[str, Any]]] = []
    for item in sorted(
        items,
        key=lambda value: (_word_float(value, "top"), _word_float(value, "x0")),
    ):
        if (
            not lines
            or _word_float(item, "top") - _word_float(lines[-1][0], "top") > 1.5
        ):
            lines.append([item])
        else:
            lines[-1].append(item)
    for line in lines:
        line.sort(key=lambda value: _word_float(value, "x0"))
    return lines


def _normalized_gilbut_meaning(
    characters: Sequence[Mapping[str, Any]],
) -> str:
    lines = _group_items_by_line(characters)
    rendered_lines: list[tuple[str, bool]] = []
    for line in lines:
        visible = [word for word in line if str(word.get("text", "")).strip()]
        if not visible:
            continue
        fragments: list[str] = []
        previous: Mapping[str, Any] | None = None
        for word in visible:
            if (
                previous is not None
                and _word_float(word, "x0") - _word_float(previous, "x1")
                > GILBUT_MEANING_WORD_GAP_POINTS
            ):
                fragments.append(" ")
            fragments.append(str(word.get("text", "")))
            previous = word
        last_visible_x0 = max(_word_float(word, "x0") for word in visible)
        trailing_space = any(
            not str(word.get("text", "")).strip()
            and _word_float(word, "x0") > last_visible_x0
            for word in line
        )
        rendered_lines.append(("".join(fragments), trailing_space))
    value = "".join(
        text + (" " if trailing_space and index + 1 < len(rendered_lines) else "")
        for index, (text, trailing_space) in enumerate(rendered_lines)
    )
    value = unicodedata.normalize("NFC", re.sub(r"\s+", " ", value).strip())
    value = re.sub(r"([^\s(（])([①-⑳])", r"\1 \2", value)
    return re.sub(r"\s*([·•])\s*", r"\1", value)


def _rounded_bbox(values: Sequence[Mapping[str, Any]]) -> tuple[float, float, float, float]:
    if not values:
        raise PublicKanjiError("Gilbut glyph has no geometry")
    return (
        round(min(_word_float(item, "x0") for item in values), 3),
        round(min(_word_float(item, "top") for item in values), 3),
        round(max(_word_float(item, "x1") for item in values), 3),
        round(max(_word_float(item, "bottom") for item in values), 3),
    )


def extract_gilbut_kanji_slots(
    path: Path,
    spec: GilbutPdfSpec,
) -> list[GilbutKanjiSlot]:
    """Extract one pinned Gilbut booklet in page, row, then column order."""
    if not path.is_file():
        raise PublicKanjiError(f"Gilbut kanji PDF is missing: {path}")
    digest = sha256_file(path)
    if spec.expected_sha256 is not None and digest != spec.expected_sha256:
        raise PublicKanjiError(f"Gilbut kanji PDF hash changed: {spec.source_id}")

    extracted: list[GilbutKanjiSlot] = []
    numeric_labels: list[int] = []
    additional_labels: list[str] = []
    try:
        document = pdfplumber.open(path)
    except Exception as exc:
        raise PublicKanjiError(f"cannot open Gilbut kanji PDF: {exc}") from exc
    with document:
        if len(document.pages) != spec.expected_page_count:
            raise PublicKanjiError(
                f"Gilbut kanji PDF page count changed: {spec.source_id}"
            )
        for page_number, page in enumerate(document.pages[1:], start=2):
            raw_words = page.extract_words(
                x_tolerance=1,
                y_tolerance=2,
                keep_blank_chars=False,
                extra_attrs=["size"],
            )
            words = [dict(value) for value in raw_words]
            headers = _gilbut_headers(
                words,
                page_width=float(page.width),
                page_height=float(page.height),
                spec=spec,
            )
            rows = _group_gilbut_rows(headers)
            if not rows:
                raise PublicKanjiError(
                    f"Gilbut kanji page has no slots: {spec.source_id}:{page_number}"
                )
            row_differences = [
                rows[index + 1][0].top - rows[index][0].top
                for index in range(len(rows) - 1)
            ]
            fallback_row_height = (
                statistics.median(row_differences) if row_differences else 59.5
            )
            for row_index, row in enumerate(rows, start=1):
                row_top = row[0].top
                row_bottom = (
                    rows[row_index][0].top
                    if row_index < len(rows)
                    else min(float(page.height) * 0.90, row_top + fallback_row_height)
                )
                centers = [header.center_x for header in row]
                column_steps = [
                    centers[index + 1] - centers[index]
                    for index in range(len(centers) - 1)
                ]
                fallback_column_width = (
                    statistics.median(column_steps)
                    if column_steps
                    else float(page.width) / 5
                )
                for column_index, header in enumerate(row, start=1):
                    center_index = column_index - 1
                    left = (
                        (centers[center_index - 1] + centers[center_index]) / 2
                        if center_index
                        else centers[center_index] - fallback_column_width / 2
                    )
                    right = (
                        (centers[center_index] + centers[center_index + 1]) / 2
                        if center_index + 1 < len(centers)
                        else centers[center_index] + fallback_column_width / 2
                    )
                    cell_words = [
                        word
                        for word in words
                        if left
                        <= (_word_float(word, "x0") + _word_float(word, "x1")) / 2
                        < right
                        and row_top + 10 < _word_float(word, "top") < row_bottom
                    ]
                    glyph_words = [
                        word
                        for word in cell_words
                        if _word_float(word, "size") >= 12
                        and _word_float(word, "top") < min(row_bottom, row_top + 50)
                    ]
                    meaning_characters = [
                        character
                        for character in page.chars
                        if left
                        <= (
                            _word_float(character, "x0")
                            + _word_float(character, "x1")
                        )
                        / 2
                        < right
                        and row_top + 10
                        < _word_float(character, "top")
                        < row_bottom
                        and _word_float(character, "size") <= 7.1
                        and _word_float(character, "top") >= row_top + 20
                    ]
                    glyph_curves = [
                        curve
                        for curve in page.curves
                        if left <= (float(curve["x0"]) + float(curve["x1"])) / 2 < right
                        and bool(curve.get("fill"))
                        and float(curve["width"]) > 2
                        and float(curve["height"]) > 2
                        and row_top + 8 <= float(curve["top"])
                        and float(curve["bottom"]) <= min(row_bottom, row_top + 50)
                    ]
                    if bool(glyph_words) == bool(glyph_curves):
                        raise PublicKanjiError(
                            "Gilbut slot must have exactly one text or vector glyph: "
                            f"{spec.source_id}:{page_number}:{row_index}:{column_index}"
                        )
                    if glyph_words:
                        glyph_kind = "text"
                        glyph_text = "".join(
                            str(word.get("text", ""))
                            for word in sorted(
                                glyph_words,
                                key=lambda value: _word_float(value, "x0"),
                            )
                        ).replace(" ", "")
                        glyph_bbox = _rounded_bbox(glyph_words)
                    else:
                        glyph_kind = "vector"
                        glyph_text = ""
                        glyph_bbox = _rounded_bbox(glyph_curves)
                    meaning = _normalized_gilbut_meaning(meaning_characters)
                    if not meaning:
                        raise PublicKanjiError(
                            "Gilbut slot has no Korean meaning: "
                            f"{spec.source_id}:{page_number}:{row_index}:{column_index}"
                        )
                    label = header.label
                    if label.isdigit():
                        numeric_labels.append(int(label))
                    else:
                        additional_labels.append(label)
                    extracted.append(
                        GilbutKanjiSlot(
                            sequence=spec.first_sequence + len(extracted),
                            source_id=spec.source_id,
                            source_sha256=digest,
                            volume_code=spec.volume_code,
                            page=page_number,
                            row=row_index,
                            column=column_index,
                            source_label=label,
                            glyph_kind=glyph_kind,
                            glyph_text=glyph_text,
                            glyph_bbox=glyph_bbox,
                            meaning=meaning,
                        )
                    )
    if len(extracted) != spec.expected_slot_count:
        raise PublicKanjiError(
            f"Gilbut kanji slot count changed: {spec.source_id} "
            f"expected={spec.expected_slot_count} actual={len(extracted)}"
        )
    if numeric_labels != list(range(spec.first_number, spec.last_number + 1)):
        raise PublicKanjiError(f"Gilbut numbered slot sequence changed: {spec.source_id}")
    if tuple(additional_labels) != spec.additional_labels:
        raise PublicKanjiError(f"Gilbut additional slot sequence changed: {spec.source_id}")
    return extracted


def extract_all_gilbut_kanji_slots(
    *,
    upper_pdf: Path,
    lower_pdf: Path,
) -> list[GilbutKanjiSlot]:
    slots = [
        *extract_gilbut_kanji_slots(upper_pdf, GILBUT_UPPER_SPEC),
        *extract_gilbut_kanji_slots(lower_pdf, GILBUT_LOWER_SPEC),
    ]
    if len(slots) != EXPECTED_GILBUT_SLOT_COUNT or [
        slot.sequence for slot in slots
    ] != list(range(1, EXPECTED_GILBUT_SLOT_COUNT + 1)):
        raise PublicKanjiError("combined Gilbut kanji sequence changed")
    return slots


def gilbut_glyph_media_filename(slot: GilbutKanjiSlot) -> str:
    if slot.glyph_kind != "vector":
        raise PublicKanjiError("only vector Gilbut glyphs need static media")
    identity = {
        "glyph_bbox": list(slot.glyph_bbox),
        "page": slot.page,
        "policy_version": GILBUT_GLYPH_POLICY_VERSION,
        "source_id": slot.source_id,
        "source_sha256": slot.source_sha256,
    }
    return f"jlpt-public-kanji-{sha256_json(identity)[:24]}.png"


def gilbut_vector_glyph_png(
    path: Path,
    slot: GilbutKanjiSlot,
) -> bytes:
    """Render one outline-only PDF glyph as transparent black-ink PNG."""
    if slot.glyph_kind != "vector":
        raise PublicKanjiError("Gilbut slot is not a vector glyph")
    if sha256_file(path) != slot.source_sha256:
        raise PublicKanjiError("Gilbut vector glyph source hash changed")
    left, top, right, bottom = slot.glyph_bbox
    try:
        document = pdfplumber.open(path)
    except Exception as exc:
        raise PublicKanjiError(f"cannot open Gilbut vector glyph PDF: {exc}") from exc
    with document:
        if not 1 <= slot.page <= len(document.pages):
            raise PublicKanjiError("Gilbut vector glyph page is invalid")
        page = document.pages[slot.page - 1]
        page_left, page_top, page_right, page_bottom = map(float, page.bbox)
        padding_points = 1.5
        crop_box = (
            max(page_left, left - padding_points),
            max(page_top, top - padding_points),
            min(page_right, right + padding_points),
            min(page_bottom, bottom + padding_points),
        )
        try:
            rendered = page.crop(crop_box).to_image(
                resolution=GILBUT_GLYPH_PNG_RESOLUTION,
                antialias=True,
            ).original.convert("L")
        except Exception as exc:
            raise PublicKanjiError(
                f"cannot render Gilbut vector glyph PDF: {exc}"
            ) from exc

    alpha = rendered.point(
        [255 if value < 192 else 0 for value in range(256)],
        mode="L",
    )
    ink_box = alpha.getbbox()
    if ink_box is None:
        raise PublicKanjiError("Gilbut vector glyph pixels are missing")
    alpha = alpha.crop(ink_box)
    canvas = Image.new(
        "RGBA",
        (
            alpha.width + GILBUT_GLYPH_PNG_PADDING_PIXELS * 2,
            alpha.height + GILBUT_GLYPH_PNG_PADDING_PIXELS * 2,
        ),
        (17, 17, 17, 0),
    )
    ink = Image.new("RGBA", alpha.size, (17, 17, 17, 255))
    ink.putalpha(alpha)
    canvas.alpha_composite(
        ink,
        (GILBUT_GLYPH_PNG_PADDING_PIXELS, GILBUT_GLYPH_PNG_PADDING_PIXELS),
    )
    output = BytesIO()
    canvas.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()
