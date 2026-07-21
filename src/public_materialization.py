"""Hydrate a public bundle into the closed inputs consumed by the APKG builder."""

from __future__ import annotations

import json
import platform
import shutil
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from public_hashing import sha256_file, sha256_json, sha256_text
from public_input_contract import (
    CONTENT_STAGE_ID,
    CONTENT_STAGE_MANIFEST,
    CONTENT_SUMMARY,
    DECK_LAYOUT,
    KANJI_NOTES,
    MEDIA_DIR,
    MEDIA_INVENTORY,
    MEDIA_JOBS,
    MEDIA_STAGE_ID,
    MEDIA_STAGE_MANIFEST,
    MEDIA_SUMMARY,
    PRACTICE_QUESTION_NOTES,
    REFERENCE_TABLE_NOTES,
    VOCABULARY_NOTES,
)
from public_build_contract import (
    BUNDLE_MEDIA_DIR,
    BUNDLE_RECIPES_DIR,
    BUNDLE_TEMPLATES_DIR,
    KANJIDIC2_SNAPSHOT,
    PUBLIC_KANJI_GLOSS_LEDGER,
    PUBLIC_LAYOUT_REGISTRY,
)
from public_content import (
    materialize_practice_notes,
    materialize_reference_notes,
    materialize_vocabulary_notes,
)
from public_kanji import (
    GILBUT_GLYPH_EQUIVALENTS,
    PublicKanjiMaterializer,
    extract_all_gilbut_kanji_slots,
    gilbut_vector_glyph_svg,
    kanji_characters,
    load_kanjidic2,
    load_reviewed_kanji_glosses,
    materialize_gilbut_kanji_meanings,
    public_supplemental_kanji_gap,
)
from public_source_proof import MatchedPdf
from public_source_records import extract_public_source_records


TEMPLATE_CONTENT_SUMMARY = f"{BUNDLE_TEMPLATES_DIR}/{CONTENT_SUMMARY}"
TEMPLATE_DECK_LAYOUT = f"{BUNDLE_TEMPLATES_DIR}/{DECK_LAYOUT}"
TEMPLATE_KANJI_NOTES = f"{BUNDLE_TEMPLATES_DIR}/{KANJI_NOTES}"
TEMPLATE_MEDIA_JOBS = f"{BUNDLE_TEMPLATES_DIR}/{MEDIA_JOBS}"
TEMPLATE_MEDIA_SUMMARY = f"{BUNDLE_TEMPLATES_DIR}/{MEDIA_SUMMARY}"
TEMPLATE_PRACTICE_NOTES = f"{BUNDLE_TEMPLATES_DIR}/{PRACTICE_QUESTION_NOTES}"
TEMPLATE_REFERENCE_NOTES = f"{BUNDLE_TEMPLATES_DIR}/{REFERENCE_TABLE_NOTES}"
TEMPLATE_VOCABULARY_NOTES = f"{BUNDLE_TEMPLATES_DIR}/{VOCABULARY_NOTES}"
RECIPE_PRACTICE = f"{BUNDLE_RECIPES_DIR}/practice-meanings.jsonl"
RECIPE_REFERENCE = f"{BUNDLE_RECIPES_DIR}/reference-cells.jsonl"
RECIPE_VOCABULARY = f"{BUNDLE_RECIPES_DIR}/vocabulary-meanings.jsonl"
BUNDLE_AUDIO_INVENTORY = f"{BUNDLE_MEDIA_DIR}/audio-inventory.jsonl"
PUBLIC_MATERIALIZATION_POLICY_VERSION = "public-source-materialization-v1"

CONTENT_ARTIFACTS = (
    DECK_LAYOUT,
    KANJI_NOTES,
    MEDIA_JOBS,
    PRACTICE_QUESTION_NOTES,
    REFERENCE_TABLE_NOTES,
    CONTENT_SUMMARY,
    VOCABULARY_NOTES,
)


class PublicMaterializationError(RuntimeError):
    """Raised when source-bound templates cannot become closed inputs."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicMaterializationError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PublicMaterializationError(f"{label} must be a JSON object")
    return value


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PublicMaterializationError(f"cannot read {label}: {exc}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PublicMaterializationError(
                f"cannot parse {label}:{line_number}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise PublicMaterializationError(
                f"{label}:{line_number} must be an object"
            )
        records.append(value)
    return records


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )


def _require_empty_directory(path: Path, label: str) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise PublicMaterializationError(f"{label} is unsafe: {path}")
    if path.is_dir() and any(path.iterdir()):
        raise PublicMaterializationError(f"{label} must be empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _match_path(matches: Sequence[MatchedPdf], source_id: str) -> Path:
    paths = [match.path for match in matches if match.record.get("source_id") == source_id]
    if len(paths) != 1:
        raise PublicMaterializationError(
            f"matched public source is missing or duplicated: {source_id}"
        )
    return paths[0]


def _standalone_kanji_character(note: Mapping[str, Any]) -> str:
    """Return only the canonical single character accepted by the card schema."""
    canonical = str(note.get("canonical_character", "")).strip()
    characters = kanji_characters(canonical)
    return characters[0] if len(characters) == 1 and canonical == characters[0] else ""


def _gilbut_study_characters(note: Mapping[str, Any]) -> tuple[str, ...]:
    canonical = _standalone_kanji_character(note)
    characters = (
        (canonical,)
        if canonical
        else kanji_characters(str(note.get("glyph_text", "")))
    )
    expanded: list[str] = []
    for character in characters:
        expanded.append(character)
        expanded.extend(GILBUT_GLYPH_EQUIVALENTS.get(character, ()))
    return tuple(dict.fromkeys(expanded))


def _standalone_kanji_reference(
    note: Mapping[str, Any],
    materializer: PublicKanjiMaterializer,
) -> dict[str, str]:
    character = _standalone_kanji_character(note)
    if not character or character not in materializer.snapshot.entries:
        return {}
    return materializer.kanji_reference(character)


def _gilbut_hint_map(
    notes: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    hints_by_character: dict[str, list[str]] = {}
    for note in notes:
        hint = str(note.get("meaning", "")).strip()
        if not hint:
            raise PublicMaterializationError("Gilbut kanji meaning is empty")
        for character in _gilbut_study_characters(note):
            values = hints_by_character.setdefault(character, [])
            if hint not in values:
                values.append(hint)
    return {
        character: " / ".join(values)
        for character, values in hints_by_character.items()
    }


def _materialize_kanji(
    *,
    bundle_root: Path,
    matches: Sequence[MatchedPdf],
    templates: Sequence[Mapping[str, Any]],
    vocabulary_templates: Sequence[Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    dict[str, list[dict[str, str]]],
    list[Any],
    dict[str, Path],
]:
    upper_pdf = _match_path(matches, "ilsang-muutta-upper")
    lower_pdf = _match_path(matches, "ilsang-muutta-lower")
    slots = extract_all_gilbut_kanji_slots(
        upper_pdf=upper_pdf,
        lower_pdf=lower_pdf,
    )
    snapshot = load_kanjidic2(bundle_root / KANJIDIC2_SNAPSHOT)
    public_words = [str(note.get("word", "")) for note in vocabulary_templates]
    gap = public_supplemental_kanji_gap(public_words, slots)
    glosses = load_reviewed_kanji_glosses(
        bundle_root / PUBLIC_KANJI_GLOSS_LEDGER,
        snapshot,
        expected_characters=gap,
    )
    materializer = PublicKanjiMaterializer(snapshot, glosses)
    materializer.validate_supplemental_coverage(gap)

    notes = materialize_gilbut_kanji_meanings(templates, slots)
    gilbut_hints = _gilbut_hint_map(notes)
    for note in notes:
        # Composite, compatibility, vector-only, and non-KANJIDIC2 Gilbut
        # cells have no row in the existing four-field reference schema. Their
        # PDF meaning and glyph remain intact; textual variants still supply
        # the vocabulary mini-dictionary study hint above.
        note["kanji_reference"] = _standalone_kanji_reference(note, materializer)

    details_by_note: dict[str, list[dict[str, str]]] = {}
    for note in vocabulary_templates:
        note_id = str(note.get("note_id", ""))
        details_by_note[note_id] = materializer.vocabulary_details(
            str(note.get("word", "")),
            gilbut_study_hints=gilbut_hints,
        )
    return (
        notes,
        details_by_note,
        slots,
        {
            "ilsang-muutta-upper": upper_pdf,
            "ilsang-muutta-lower": lower_pdf,
        },
    )


def _fill_linked_vocabulary(
    kanji_notes: Sequence[dict[str, Any]],
    vocabulary_notes: Sequence[Mapping[str, Any]],
) -> None:
    meaning_by_id = {
        str(note.get("note_id", "")): str(note.get("meaning", ""))
        for note in vocabulary_notes
    }
    for note in kanji_notes:
        linked = note.get("linked_vocabulary")
        if not isinstance(linked, list):
            raise PublicMaterializationError("kanji linked vocabulary is invalid")
        for item in linked:
            if not isinstance(item, dict):
                raise PublicMaterializationError("kanji linked item is invalid")
            note_id = str(item.get("note_id", ""))
            meaning = meaning_by_id.get(note_id)
            if meaning is None:
                raise PublicMaterializationError(
                    f"kanji links a non-public vocabulary note: {note_id}"
                )
            item["meaning"] = meaning


def _write_content_manifest(content_root: Path) -> dict[str, Any]:
    output_artifacts = {
        name: sha256_file(content_root / name) for name in CONTENT_ARTIFACTS
    }
    payload = {
        "code_hashes": {},
        "counts": _read_json(content_root / CONTENT_SUMMARY, "content summary"),
        "input_bundle_hash": sha256_json(output_artifacts),
        "input_hashes": {"public_templates": sha256_json(output_artifacts)},
        "output_artifacts": output_artifacts,
        "output_bundle_hash": sha256_json(output_artifacts),
        "policy_version": PUBLIC_MATERIALIZATION_POLICY_VERSION,
        "runtime": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
        },
        "schema_version": 1,
        "stage_id": CONTENT_STAGE_ID,
        "stage_order": 9,
        "status": "passed",
        "substage": "public-source-materialized-content",
        "unresolved": 0,
        "upstream_stage_ids": [],
    }
    _write_json(content_root / CONTENT_STAGE_MANIFEST, payload)
    return payload


def _materialize_media(
    *,
    bundle_root: Path,
    content_root: Path,
    content_manifest: Mapping[str, Any],
    media_root: Path,
    jobs: Sequence[Mapping[str, Any]],
    slots: Sequence[Any],
    slot_source_paths: Mapping[str, Path],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    inventory = _read_jsonl(
        bundle_root / BUNDLE_AUDIO_INVENTORY,
        "public audio inventory",
    )
    audio_inventory = {
        str(record.get("filename", "")): record for record in inventory
    }
    if len(audio_inventory) != len(inventory):
        raise PublicMaterializationError("public audio inventory has duplicate names")

    jobs_by_name = {str(job.get("filename", "")): dict(job) for job in jobs}
    if len(jobs_by_name) != len(jobs) or "" in jobs_by_name:
        raise PublicMaterializationError("public media jobs have invalid names")
    audio_jobs = {
        name: job for name, job in jobs_by_name.items() if job.get("kind") != "kanji_static"
    }
    static_jobs = {
        name: job for name, job in jobs_by_name.items() if job.get("kind") == "kanji_static"
    }
    if set(audio_jobs) != set(audio_inventory):
        raise PublicMaterializationError("public audio jobs and inventory differ")

    media_dir = media_root / MEDIA_DIR
    media_dir.mkdir(parents=True, exist_ok=True)
    final_inventory: list[dict[str, Any]] = []
    for filename, job in sorted(audio_jobs.items()):
        source = bundle_root / BUNDLE_MEDIA_DIR / filename
        target = media_dir / filename
        record = dict(audio_inventory[filename])
        if (
            source.is_symlink()
            or not source.is_file()
            or record.get("content_input_hash") != job.get("input_hash")
            or source.stat().st_size != record.get("bytes")
            or sha256_file(source) != record.get("sha256")
        ):
            raise PublicMaterializationError(
                f"public bundled audio changed: {filename}"
            )
        shutil.copyfile(source, target)
        final_inventory.append(record)

    vector_slots = [slot for slot in slots if slot.glyph_kind == "vector"]
    if len(vector_slots) != len(static_jobs):
        raise PublicMaterializationError("public vector glyph job count changed")
    for slot in vector_slots:
        source_path = slot_source_paths.get(slot.source_id)
        if source_path is None:
            raise PublicMaterializationError(
                f"public vector glyph source is missing: {slot.source_id}"
            )
        filename = next(
            (
                name
                for name, job in static_jobs.items()
                if job.get("source_record_hash") == slot.source_record_hash
            ),
            "",
        )
        job = static_jobs.get(filename)
        if job is None:
            raise PublicMaterializationError(
                f"public vector glyph job is missing: {slot.sequence}"
            )
        payload = gilbut_vector_glyph_svg(source_path, slot)
        digest = sha256_text(payload.decode("utf-8"))
        if (
            len(payload) != job.get("bytes")
            or digest != job.get("source_sha256")
        ):
            raise PublicMaterializationError(
                f"public vector glyph changed: {slot.sequence}"
            )
        target = media_dir / filename
        target.write_bytes(payload)
        final_inventory.append(
            {
                "bytes": len(payload),
                "content_input_hash": job.get("input_hash"),
                "filename": filename,
                "kind": "kanji_static",
                "schema_version": 1,
                "sha256": digest,
                "synthesis_mode": "copy",
            }
        )

    final_inventory.sort(key=lambda record: str(record["filename"]))
    actual_names = {path.name for path in media_dir.iterdir() if path.is_file()}
    if actual_names != set(jobs_by_name):
        raise PublicMaterializationError("public materialized media set differs")
    _write_jsonl(media_root / MEDIA_INVENTORY, final_inventory)
    media_summary = _read_json(
        bundle_root / TEMPLATE_MEDIA_SUMMARY,
        "public media summary template",
    )
    kind_counts = Counter(str(job.get("kind", "")) for job in jobs)
    if media_summary.get("kind_counts") != dict(sorted(kind_counts.items())):
        raise PublicMaterializationError("public media summary kind counts changed")
    _write_json(media_root / MEDIA_SUMMARY, media_summary)
    output_artifacts = {
        MEDIA_INVENTORY: sha256_file(media_root / MEDIA_INVENTORY),
        MEDIA_SUMMARY: sha256_file(media_root / MEDIA_SUMMARY),
    }
    input_hashes = {
        "content_manifest": sha256_file(content_root / CONTENT_STAGE_MANIFEST),
        "content_output_bundle": str(content_manifest["output_bundle_hash"]),
        "media_jobs": sha256_file(content_root / MEDIA_JOBS),
    }
    manifest = {
        "code_hashes": {},
        "counts": media_summary,
        "input_bundle_hash": sha256_json(input_hashes),
        "input_hashes": input_hashes,
        "output_artifacts": output_artifacts,
        "output_bundle_hash": sha256_json(output_artifacts),
        "policy_version": PUBLIC_MATERIALIZATION_POLICY_VERSION,
        "runtime": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
        },
        "schema_version": 1,
        "stage_id": MEDIA_STAGE_ID,
        "stage_order": 9,
        "status": "passed",
        "substage": "public-source-materialized-media",
        "unresolved": 0,
        "upstream_stage_ids": [CONTENT_STAGE_ID],
    }
    _write_json(media_root / MEDIA_STAGE_MANIFEST, manifest)
    return manifest, final_inventory


def materialize_public_inputs(
    *,
    bundle_root: Path,
    matches: Sequence[MatchedPdf],
    content_root: Path,
    media_root: Path,
    extracted_sources: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create closed content/media roots from templates and exact local PDFs."""
    _require_empty_directory(content_root, "public content output")
    _require_empty_directory(media_root, "public media output")
    extracted = (
        dict(extracted_sources)
        if extracted_sources is not None
        else extract_public_source_records(
            matches,
            bundle_root / PUBLIC_LAYOUT_REGISTRY,
        )
    )
    source_records = extracted.get("source_records_by_id")
    source_cells = extracted.get("cells_by_id")
    if not isinstance(source_records, dict) or not isinstance(source_cells, dict):
        raise PublicMaterializationError("public source extraction is incomplete")

    vocabulary_templates = _read_jsonl(
        bundle_root / TEMPLATE_VOCABULARY_NOTES,
        "public vocabulary templates",
    )
    kanji_templates = _read_jsonl(
        bundle_root / TEMPLATE_KANJI_NOTES,
        "public kanji templates",
    )
    kanji_notes, kanji_details_by_note, slots, slot_source_paths = _materialize_kanji(
        bundle_root=bundle_root,
        matches=matches,
        templates=kanji_templates,
        vocabulary_templates=vocabulary_templates,
    )
    vocabulary_notes = materialize_vocabulary_notes(
        vocabulary_templates,
        _read_jsonl(bundle_root / RECIPE_VOCABULARY, "vocabulary recipes"),
        source_records,
        kanji_details_by_note=kanji_details_by_note,
    )
    public_meanings = {
        str(note["note_id"]): str(note["meaning"]) for note in vocabulary_notes
    }
    _fill_linked_vocabulary(kanji_notes, vocabulary_notes)
    reference_notes = materialize_reference_notes(
        _read_jsonl(
            bundle_root / TEMPLATE_REFERENCE_NOTES,
            "public reference templates",
        ),
        _read_jsonl(bundle_root / RECIPE_REFERENCE, "reference recipes"),
        source_cells,
    )
    practice_notes = materialize_practice_notes(
        _read_jsonl(
            bundle_root / TEMPLATE_PRACTICE_NOTES,
            "public practice templates",
        ),
        _read_jsonl(bundle_root / RECIPE_PRACTICE, "practice recipes"),
        source_records,
        public_meanings,
        source_cells,
    )
    jobs = _read_jsonl(bundle_root / TEMPLATE_MEDIA_JOBS, "public media jobs")

    shutil.copyfile(bundle_root / TEMPLATE_DECK_LAYOUT, content_root / DECK_LAYOUT)
    shutil.copyfile(
        bundle_root / TEMPLATE_CONTENT_SUMMARY,
        content_root / CONTENT_SUMMARY,
    )
    _write_jsonl(content_root / VOCABULARY_NOTES, vocabulary_notes)
    _write_jsonl(content_root / KANJI_NOTES, kanji_notes)
    _write_jsonl(content_root / REFERENCE_TABLE_NOTES, reference_notes)
    _write_jsonl(content_root / PRACTICE_QUESTION_NOTES, practice_notes)
    _write_jsonl(content_root / MEDIA_JOBS, jobs)
    content_manifest = _write_content_manifest(content_root)
    media_manifest, inventory = _materialize_media(
        bundle_root=bundle_root,
        content_root=content_root,
        content_manifest=content_manifest,
        media_root=media_root,
        jobs=jobs,
        slots=slots,
        slot_source_paths=slot_source_paths,
    )
    payload = {
        "content_output_bundle": content_manifest["output_bundle_hash"],
        "kanji_note_count": len(kanji_notes),
        "media_file_count": len(inventory),
        "media_output_bundle": media_manifest["output_bundle_hash"],
        "policy_version": PUBLIC_MATERIALIZATION_POLICY_VERSION,
        "practice_note_count": len(practice_notes),
        "reference_note_count": len(reference_notes),
        "schema_version": 1,
        "source_records_hash": extracted.get("summary", {}).get(
            "source_records_hash"
        ),
        "status": "passed",
        "unresolved": 0,
        "vocabulary_note_count": len(vocabulary_notes),
    }
    return {**payload, "payload_hash": sha256_json(payload)}
