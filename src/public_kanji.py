# pyright: reportMissingImports=false
"""Build public kanji metadata from the bundled open-data snapshot and PDFs.

KANJIDIC2 supplies Japanese readings, Korean readings, the classical radical,
and stroke count.  Korean study glosses are deliberately separate: characters
not covered by the user's Gilbut PDFs must have an independently reviewed
record in a small, hash-bound ledger.
"""

from __future__ import annotations

import gzip
import html
import json
import re
import statistics
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pdfplumber

from public_hashing import sha256_file, sha256_json


KANJIDIC2_SOURCE_ID = "edrdg-kanjidic2"
GLOSS_POLICY_VERSION = "public-kanji-gloss-review-v1"
GLOSS_REVIEW_BASIS = "kanjidic2-english-meanings-and-public-usage"
GILBUT_EXTRACTION_POLICY_VERSION = "public-gilbut-kanji-geometry-v1"
GILBUT_GLYPH_POLICY_VERSION = "public-gilbut-vector-glyph-v1"
EXPECTED_GILBUT_SLOT_COUNT = 2_337
# enumerate their own alternatives and need no table entry.
GILBUT_GLYPH_EQUIVALENTS = MappingProxyType({"戶": ("戸",)})
SUPPLEMENTAL_KANJI_CHARACTERS = tuple(
    "些儚凌叩叶吠呟咎咳喧噛堵塵墟奢婉嬉尖庇弛怯惹拮捧揃揉斡溜溢"
    "煌爬狡痒眩禄稀耽脆蓮蘇詫賑贅辿逞遽醤頷馴"
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_REVIEW_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_KOREAN_TEXT_RE = re.compile(r"[\uac00-\ud7a3]")
_NUMBERED_SLOT_RE = re.compile(r"[0-9]{4}")
_ADDITIONAL_SLOT_RE = re.compile(r"추가자\s*([0-9]+)")
_LEDGER_KEYS = frozenset(
    {
        "character",
        "kanjidic2_entry_hash",
        "korean_gloss",
        "korean_readings",
        "policy_version",
        "review_basis",
        "reviewed_at",
        "reviewer",
        "schema_version",
    }
)


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

    @property
    def source_record_hash(self) -> str:
        return sha256_json(
            {
                "column": self.column,
                "glyph_bbox": list(self.glyph_bbox),
                "glyph_kind": self.glyph_kind,
                "glyph_text": self.glyph_text,
                "meaning": self.meaning,
                "page": self.page,
                "policy_version": GILBUT_EXTRACTION_POLICY_VERSION,
                "row": self.row,
                "sequence": self.sequence,
                "source_id": self.source_id,
                "source_label": self.source_label,
                "source_sha256": self.source_sha256,
                "volume_code": self.volume_code,
            }
        )

    def provenance(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "glyph_bbox": list(self.glyph_bbox),
            "page": self.page,
            "policy_version": GILBUT_EXTRACTION_POLICY_VERSION,
            "row": self.row,
            "source_id": self.source_id,
            "source_record_hash": self.source_record_hash,
            "source_sha256": self.source_sha256,
        }


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


def _is_kanji(value: str) -> bool:
    if len(value) != 1:
        return False
    name = unicodedata.name(value, "")
    return name.startswith(
        ("CJK UNIFIED IDEOGRAPH-", "CJK COMPATIBILITY IDEOGRAPH-")
    )


def _unique_text(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        value = unicodedata.normalize("NFC", raw.strip())
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _classical_radical_character(number: int) -> str:
    if not 1 <= number <= 214:
        raise PublicKanjiError(f"KANJIDIC2 classical radical is invalid: {number}")
    # Unicode encodes the Kangxi radicals consecutively.  NFKC maps the
    # compatibility radical symbol to the ordinary CJK character shown in UI.
    return unicodedata.normalize("NFKC", chr(0x2F00 + number - 1))


@dataclass(frozen=True)
class Kanjidic2Entry:
    character: str
    classical_radical_number: int
    radical: str
    strokes: int
    on_readings: tuple[str, ...]
    kun_readings: tuple[str, ...]
    korean_readings: tuple[str, ...]
    english_meanings: tuple[str, ...]

    @property
    def review_input_hash(self) -> str:
        """Bind a Korean review to the exact open-data entry it reviewed."""
        return sha256_json(
            {
                "character": self.character,
                "english_meanings": list(self.english_meanings),
                "korean_readings": list(self.korean_readings),
                "source_id": KANJIDIC2_SOURCE_ID,
            }
        )

    def structural_fields(self) -> dict[str, str]:
        return {
            "kun_reading": "・".join(self.kun_readings),
            "on_reading": "・".join(self.on_readings),
            "radical": self.radical,
            "strokes": str(self.strokes),
        }


@dataclass(frozen=True)
class Kanjidic2Snapshot:
    entries: Mapping[str, Kanjidic2Entry]
    file_version: str
    database_version: str
    date_of_creation: str
    sha256: str


@dataclass(frozen=True)
class ReviewedKanjiGloss:
    character: str
    korean_gloss: str
    korean_readings: tuple[str, ...]
    reviewed_at: str
    reviewer: str

    @property
    def study_hint(self) -> str:
        return f"{self.korean_gloss} {'·'.join(self.korean_readings)}"


def _entry_from_element(element: ET.Element) -> Kanjidic2Entry:
    # Compatibility ideographs are distinct KANJIDIC2 keys even when Unicode
    # normalization would fold them into a unified ideograph.
    character = str(element.findtext("literal", ""))
    if not _is_kanji(character):
        raise PublicKanjiError(f"KANJIDIC2 literal is invalid: {character!r}")

    classical_values = [
        str(value.text or "").strip()
        for value in element.findall("radical/rad_value")
        if value.attrib.get("rad_type") == "classical"
    ]
    if len(classical_values) != 1 or not classical_values[0].isdigit():
        raise PublicKanjiError(
            f"KANJIDIC2 entry lacks one classical radical: {character}"
        )
    radical_number = int(classical_values[0])

    stroke_values = [
        str(value.text or "").strip()
        for value in element.findall("misc/stroke_count")
    ]
    if not stroke_values or not stroke_values[0].isdigit() or int(stroke_values[0]) < 1:
        raise PublicKanjiError(f"KANJIDIC2 entry lacks a stroke count: {character}")

    on_readings: list[str] = []
    kun_readings: list[str] = []
    korean_readings: list[str] = []
    english_meanings: list[str] = []
    for group in element.findall("reading_meaning/rmgroup"):
        for reading in group.findall("reading"):
            value = str(reading.text or "")
            reading_type = reading.attrib.get("r_type", "ja_on")
            if reading_type == "ja_on":
                on_readings.append(value)
            elif reading_type == "ja_kun":
                kun_readings.append(value)
            elif reading_type == "korean_h":
                korean_readings.append(value)
        for meaning in group.findall("meaning"):
            if "m_lang" not in meaning.attrib:
                english_meanings.append(str(meaning.text or ""))

    return Kanjidic2Entry(
        character=character,
        classical_radical_number=radical_number,
        radical=_classical_radical_character(radical_number),
        strokes=int(stroke_values[0]),
        on_readings=_unique_text(on_readings),
        kun_readings=_unique_text(kun_readings),
        korean_readings=_unique_text(korean_readings),
        english_meanings=_unique_text(english_meanings),
    )


def load_kanjidic2(
    path: Path, *, expected_sha256: str | None = None
) -> Kanjidic2Snapshot:
    """Load one hash-pinned KANJIDIC2 gzip snapshot."""
    if not path.is_file():
        raise PublicKanjiError(f"KANJIDIC2 snapshot is missing: {path}")
    digest = sha256_file(path)
    if expected_sha256 is not None and (
        _SHA256_RE.fullmatch(expected_sha256) is None or digest != expected_sha256
    ):
        raise PublicKanjiError("KANJIDIC2 snapshot hash changed")

    try:
        with gzip.open(path, "rb") as source:
            root = ET.parse(source).getroot()
    except (OSError, ET.ParseError) as exc:
        raise PublicKanjiError(f"cannot parse KANJIDIC2 snapshot: {exc}") from exc
    if root.tag != "kanjidic2":
        raise PublicKanjiError("KANJIDIC2 root element changed")

    header = root.find("header")
    if header is None:
        raise PublicKanjiError("KANJIDIC2 header is missing")
    file_version = str(header.findtext("file_version", "")).strip()
    database_version = str(header.findtext("database_version", "")).strip()
    date_of_creation = str(header.findtext("date_of_creation", "")).strip()
    if (
        not file_version
        or not database_version
        or _REVIEW_DATE_RE.fullmatch(date_of_creation) is None
    ):
        raise PublicKanjiError("KANJIDIC2 header is invalid")

    entries: dict[str, Kanjidic2Entry] = {}
    for element in root.findall("character"):
        entry = _entry_from_element(element)
        if entry.character in entries:
            raise PublicKanjiError(
                f"KANJIDIC2 character is duplicated: {entry.character}"
            )
        entries[entry.character] = entry
    if not entries:
        raise PublicKanjiError("KANJIDIC2 has no character entries")
    return Kanjidic2Snapshot(
        entries=MappingProxyType(entries),
        file_version=file_version,
        database_version=database_version,
        date_of_creation=date_of_creation,
        sha256=digest,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PublicKanjiError(f"cannot read public kanji gloss ledger: {exc}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PublicKanjiError(
                f"cannot parse public kanji gloss ledger:{line_number}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise PublicKanjiError(
                f"public kanji gloss ledger:{line_number} must be an object"
            )
        records.append(value)
    return records


def load_reviewed_kanji_glosses(
    path: Path,
    snapshot: Kanjidic2Snapshot,
    *,
    expected_characters: Sequence[str] = SUPPLEMENTAL_KANJI_CHARACTERS,
) -> Mapping[str, ReviewedKanjiGloss]:
    """Validate the complete reviewed fallback ledger against KANJIDIC2."""
    expected = tuple(expected_characters)
    if len(expected) != len(set(expected)) or any(
        not _is_kanji(character) for character in expected
    ):
        raise PublicKanjiError("expected supplemental kanji set is invalid")

    glosses: dict[str, ReviewedKanjiGloss] = {}
    for record in _read_jsonl(path):
        if set(record) != _LEDGER_KEYS:
            raise PublicKanjiError("public kanji gloss ledger schema changed")
        character = record.get("character")
        entry = snapshot.entries.get(str(character))
        korean_gloss = record.get("korean_gloss")
        korean_readings = record.get("korean_readings")
        reviewer = record.get("reviewer")
        reviewed_at = record.get("reviewed_at")
        if (
            not isinstance(character, str)
            or entry is None
            or character in glosses
            or record.get("schema_version") != 1
            or record.get("policy_version") != GLOSS_POLICY_VERSION
            or record.get("review_basis") != GLOSS_REVIEW_BASIS
            or record.get("kanjidic2_entry_hash") != entry.review_input_hash
            or not isinstance(korean_gloss, str)
            or korean_gloss != korean_gloss.strip()
            or not korean_gloss
            or len(korean_gloss) > 80
            or _KOREAN_TEXT_RE.search(korean_gloss) is None
            or any(separator in korean_gloss for separator in (";", ",", "/", "\n"))
            or not isinstance(korean_readings, list)
            or any(not isinstance(value, str) for value in korean_readings)
            or _unique_text(korean_readings) != entry.korean_readings
            or not entry.korean_readings
            or not isinstance(reviewer, str)
            or not reviewer.strip()
            or not isinstance(reviewed_at, str)
            or _REVIEW_DATE_RE.fullmatch(reviewed_at) is None
        ):
            raise PublicKanjiError(
                f"public kanji gloss review is invalid: {character!r}"
            )
        glosses[character] = ReviewedKanjiGloss(
            character=character,
            korean_gloss=korean_gloss,
            korean_readings=entry.korean_readings,
            reviewed_at=reviewed_at,
            reviewer=reviewer.strip(),
        )

    actual = set(glosses)
    wanted = set(expected)
    if actual != wanted:
        missing = "".join(sorted(wanted - actual))
        unexpected = "".join(sorted(actual - wanted))
        raise PublicKanjiError(
            "public kanji gloss coverage differs: "
            f"missing={missing or '-'} unexpected={unexpected or '-'}"
        )
    return MappingProxyType(glosses)


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


def _group_words_by_line(
    words: Sequence[Mapping[str, Any]],
) -> list[list[Mapping[str, Any]]]:
    lines: list[list[Mapping[str, Any]]] = []
    for word in sorted(
        words,
        key=lambda value: (_word_float(value, "top"), _word_float(value, "x0")),
    ):
        if not lines or _word_float(word, "top") - _word_float(lines[-1][0], "top") > 1.5:
            lines.append([word])
        else:
            lines[-1].append(word)
    for line in lines:
        line.sort(key=lambda value: _word_float(value, "x0"))
    return lines


def _normalized_gilbut_meaning(words: Sequence[Mapping[str, Any]]) -> str:
    lines = _group_words_by_line(words)
    value = " ".join(
        " ".join(str(word.get("text", "")) for word in line) for line in lines
    )
    value = unicodedata.normalize("NFC", re.sub(r"\s+", " ", value).strip())
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
                    meaning_words = [
                        word
                        for word in cell_words
                        if _word_float(word, "size") <= 7.1
                        and _word_float(word, "top") >= row_top + 20
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
                    meaning = _normalized_gilbut_meaning(meaning_words)
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


def _svg_number(value: float) -> str:
    rendered = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _svg_point(
    point: Sequence[Any], *, x0: float, top: float, padding: float
) -> tuple[float, float]:
    if len(point) != 2:
        raise PublicKanjiError("Gilbut vector glyph path point is invalid")
    x, y = point
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise PublicKanjiError("Gilbut vector glyph path point is invalid")
    return float(x) - x0 + padding, float(y) - top + padding


def _svg_path_data(
    raw_path: Sequence[Any],
    *,
    x0: float,
    top: float,
    padding: float,
) -> str:
    commands: list[str] = []
    current: tuple[float, float] | None = None
    start: tuple[float, float] | None = None
    for raw in raw_path:
        if not isinstance(raw, (tuple, list)) or not raw:
            raise PublicKanjiError("Gilbut vector glyph path command is invalid")
        operator = raw[0]
        points = [
            _svg_point(point, x0=x0, top=top, padding=padding)
            for point in raw[1:]
        ]
        if operator == "m" and len(points) == 1:
            current = start = points[0]
            commands.append(f"M{_svg_number(current[0])} {_svg_number(current[1])}")
        elif operator == "l" and len(points) == 1:
            current = points[0]
            commands.append(f"L{_svg_number(current[0])} {_svg_number(current[1])}")
        elif operator == "c" and len(points) == 3:
            current = points[2]
            commands.append(
                "C"
                + " ".join(
                    f"{_svg_number(point[0])} {_svg_number(point[1])}"
                    for point in points
                )
            )
        elif operator == "v" and len(points) == 2 and current is not None:
            first_control = current
            second_control, endpoint = points
            commands.append(
                f"C{_svg_number(first_control[0])} {_svg_number(first_control[1])} "
                f"{_svg_number(second_control[0])} {_svg_number(second_control[1])} "
                f"{_svg_number(endpoint[0])} {_svg_number(endpoint[1])}"
            )
            current = endpoint
        elif operator == "y" and len(points) == 2:
            control, endpoint = points
            current = endpoint
            commands.append(
                f"C{_svg_number(control[0])} {_svg_number(control[1])} "
                f"{_svg_number(endpoint[0])} {_svg_number(endpoint[1])} "
                f"{_svg_number(endpoint[0])} {_svg_number(endpoint[1])}"
            )
        elif operator == "h" and not points:
            commands.append("Z")
            current = start
        else:
            raise PublicKanjiError(
                f"unsupported Gilbut vector glyph path command: {operator!r}"
            )
    return "".join(commands)


def _curve_path_payload(curve: Mapping[str, Any]) -> Any:
    raw_path = curve.get("path")
    if not isinstance(raw_path, list) or not raw_path:
        raise PublicKanjiError("Gilbut vector glyph curve has no path")
    return raw_path


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
    return f"jlpt-public-kanji-{sha256_json(identity)[:24]}.svg"


def gilbut_vector_glyph_svg(
    path: Path,
    slot: GilbutKanjiSlot,
) -> bytes:
    """Serialize one outline-only PDF glyph as deterministic standalone SVG."""
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
        curves = [
            curve
            for curve in page.curves
            if bool(curve.get("fill"))
            and left - 0.002 <= float(curve["x0"])
            and float(curve["x1"]) <= right + 0.002
            and top - 0.002 <= float(curve["top"])
            and float(curve["bottom"]) <= bottom + 0.002
        ]
    if not curves:
        raise PublicKanjiError("Gilbut vector glyph paths are missing")

    unique: dict[str, Mapping[str, Any]] = {}
    for curve in curves:
        payload = _curve_path_payload(curve)
        unique.setdefault(sha256_json(payload), curve)
    ordered = sorted(
        unique.values(),
        key=lambda value: (
            float(value["top"]),
            float(value["x0"]),
            float(value["bottom"]),
            float(value["x1"]),
            sha256_json(_curve_path_payload(value)),
        ),
    )
    padding = 1.5
    width = right - left + padding * 2
    height = bottom - top + padding * 2
    paths: list[str] = []
    for curve in ordered:
        data = _svg_path_data(
            _curve_path_payload(curve),
            x0=left,
            top=top,
            padding=padding,
        )
        fill_rule = "evenodd" if bool(curve.get("evenodd")) else "nonzero"
        paths.append(
            f'<path d="{data}" fill="#111111" fill-rule="{fill_rule}"/>'
        )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {_svg_number(width)} {_svg_number(height)}">'
        + "".join(paths)
        + "</svg>\n"
    )
    return svg.encode("utf-8")


def _normalized_glyph_identity(value: Any) -> str:
    return unicodedata.normalize("NFKC", re.sub(r"\s+", "", str(value)))


def _template_label_matches(unit: Any, label: str) -> bool:
    unit_text = str(unit).strip()
    if label.isdigit():
        return unit_text.isdigit() and int(unit_text) == int(label)
    match = _ADDITIONAL_SLOT_RE.search(unit_text)
    return match is not None and f"추가자{match.group(1)}" == label


def audit_gilbut_kanji_template(
    templates: Sequence[Mapping[str, Any]],
    slots: Sequence[GilbutKanjiSlot],
) -> dict[str, Any]:
    """Report every sequence, label, and glyph mismatch without repairing it."""
    mismatches: list[dict[str, Any]] = []
    if len(templates) != len(slots):
        mismatches.append(
            {
                "actual": len(slots),
                "expected": len(templates),
                "kind": "slot_count",
            }
        )
    for index, (template, slot) in enumerate(zip(templates, slots, strict=False), 1):
        location = {
            "column": slot.column,
            "page": slot.page,
            "row": slot.row,
            "sequence": index,
            "source_id": slot.source_id,
        }
        if template.get("sequence") != index or slot.sequence != index:
            mismatches.append(
                {
                    **location,
                    "actual": {
                        "slot_sequence": slot.sequence,
                        "template_sequence": template.get("sequence"),
                    },
                    "expected": index,
                    "kind": "sequence",
                }
            )
        if str(template.get("volume_code", "")) != slot.volume_code:
            mismatches.append(
                {
                    **location,
                    "actual": slot.volume_code,
                    "expected": template.get("volume_code"),
                    "kind": "volume",
                }
            )
        if not _template_label_matches(template.get("unit"), slot.source_label):
            mismatches.append(
                {
                    **location,
                    "actual": slot.source_label,
                    "expected": template.get("unit"),
                    "kind": "source_label",
                }
            )

        expected_glyph = str(template.get("canonical_character", "")) or str(
            template.get("glyph_text", "")
        )
        expects_vector = bool(template.get("glyph_media_filename")) or (
            template.get("glyph_kind") == "vector"
        )
        if slot.glyph_kind == "text":
            if not expected_glyph or (
                _normalized_glyph_identity(expected_glyph)
                != _normalized_glyph_identity(slot.glyph_text)
            ):
                mismatches.append(
                    {
                        **location,
                        "actual": slot.glyph_text,
                        "expected": expected_glyph,
                        "kind": "glyph",
                    }
                )
        elif expected_glyph or not expects_vector:
            mismatches.append(
                {
                    **location,
                    "actual": "vector",
                    "expected": expected_glyph or "vector marker",
                    "kind": "glyph",
                }
            )
    return {
        "matched": len(templates) == len(slots) and not mismatches,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "policy_version": GILBUT_EXTRACTION_POLICY_VERSION,
        "schema_version": 1,
        "slot_count": len(slots),
        "template_count": len(templates),
    }




def materialize_gilbut_kanji_meanings(
    templates: Sequence[Mapping[str, Any]],
    slots: Sequence[GilbutKanjiSlot],
) -> list[dict[str, Any]]:
    """Fill public kanji meanings and glyphs only after exact alignment."""
    audit = audit_gilbut_kanji_template(templates, slots)
    if not audit["matched"]:
        examples = ", ".join(
            f"{value.get('sequence', '-')}/{value['kind']}"
            for value in audit["mismatches"][:5]
        )
        raise PublicKanjiError(
            "Gilbut kanji template differs from page-row-column slots: "
            f"{audit['mismatch_count']} mismatch(es): {examples}"
        )
    materialized: list[dict[str, Any]] = []
    for template, slot in zip(templates, slots, strict=True):
        vector = slot.glyph_kind == "vector"
        materialized.append(
            {
                **dict(template),
                "glyph_kind": slot.glyph_kind,
                "glyph_media_filename": gilbut_glyph_media_filename(slot)
                if vector
                else "",
                "glyph_text": "" if vector else slot.glyph_text,
                "meaning": slot.meaning,
                "source_provenance": slot.provenance(),
            }
        )
    return materialized




def kanji_characters(value: str) -> tuple[str, ...]:
    """Return distinct CJK kanji in display order."""
    return tuple(dict.fromkeys(character for character in value if _is_kanji(character)))


def gilbut_covered_kanji_characters(
    slots: Sequence[GilbutKanjiSlot],
) -> tuple[str, ...]:
    """Return every Unicode kanji explicitly represented by Gilbut glyph cells."""
    covered: set[str] = set()
    for slot in slots:
        covered.update(kanji_characters(slot.glyph_text))
    for source, equivalents in GILBUT_GLYPH_EQUIVALENTS.items():
        if source in covered:
            covered.update(equivalents)
    return tuple(sorted(covered))


def public_supplemental_kanji_gap(
    vocabulary_words: Sequence[str],
    slots: Sequence[GilbutKanjiSlot],
) -> tuple[str, ...]:
    """Measure public vocabulary kanji not represented in the Gilbut PDFs."""
    required = {
        character
        for word in vocabulary_words
        for character in kanji_characters(word)
    }
    return tuple(sorted(required - set(gilbut_covered_kanji_characters(slots))))


@dataclass(frozen=True)
class PublicKanjiMaterializer:
    snapshot: Kanjidic2Snapshot
    supplemental_glosses: Mapping[str, ReviewedKanjiGloss]

    def _entry(self, character: str) -> Kanjidic2Entry:
        entry = self.snapshot.entries.get(character)
        if entry is None:
            raise PublicKanjiError(
                f"public kanji is absent from KANJIDIC2: {character}"
            )
        return entry

    def kanji_reference(self, character: str) -> dict[str, str]:
        """Materialize the existing four-field standalone-kanji schema."""
        return self._entry(character).structural_fields()

    def vocabulary_details(
        self,
        word: str,
        *,
        gilbut_study_hints: Mapping[str, str],
    ) -> list[dict[str, str]]:
        """Materialize mini-dictionary rows from Gilbut plus reviewed fallbacks."""
        details: list[dict[str, str]] = []
        for character in kanji_characters(word):
            entry = self._entry(character)
            hint = gilbut_study_hints.get(character, "").strip()
            if not hint:
                reviewed = self.supplemental_glosses.get(character)
                if reviewed is None:
                    raise PublicKanjiError(
                        f"public kanji lacks a Korean study hint: {character}"
                    )
                hint = reviewed.study_hint
            details.append(
                {
                    "character": character,
                    "study_hint": hint,
                    **entry.structural_fields(),
                }
            )
        return details

    def validate_supplemental_coverage(
        self,
        required_characters: Sequence[str],
    ) -> None:
        """Require the reviewed ledger to be exactly the actual Gilbut gap."""
        required = set(required_characters)
        actual = set(self.supplemental_glosses)
        if required != actual:
            missing = "".join(sorted(required - actual))
            unexpected = "".join(sorted(actual - required))
            raise PublicKanjiError(
                "public supplemental kanji set differs: "
                f"missing={missing or '-'} unexpected={unexpected or '-'}"
            )


if len(SUPPLEMENTAL_KANJI_CHARACTERS) != 49 or tuple(
    sorted(SUPPLEMENTAL_KANJI_CHARACTERS)
) != SUPPLEMENTAL_KANJI_CHARACTERS:
    raise RuntimeError("public supplemental kanji contract must be 49 sorted characters")
