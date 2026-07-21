"""Materialize source-bound public deck records from user-owned PDFs.

The public bundle may retain generated Japanese/Korean study content, stable
identities, and source coordinates.  Publisher Korean meanings are different:
templates carry empty fields and recipes carry only source record identifiers,
ordering, and hashes.  The user's exact PDFs provide the strings at build time.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from public_hashing import sha256_json


PUBLIC_PUBLISHERS = frozenset({"dongyang", "hackers"})
PUBLIC_READING_OVERRIDES = {
    "ci-6e3dab8ff525d7dc91d2": ("まいつき",),
    "ci-3d5f4860a4bc469680ce": ("まぬかれる",),
}

_MEANING_SEPARATOR_RE = re.compile(r"\s*[,;/／；]+\s*")
_LEADING_NUMBER_RE = re.compile(r"^(?:[①-⑳]|\(?\d+\)?[.)]?)[\s　]*")
_SPACE_RE = re.compile(r"[\s　]+")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_KANA_ONLY_RE = re.compile(r"^[\u3040-\u30ffー・･～〜~()（）]+$")
_LEVELS = ("N5", "N4", "N3", "N2", "N1")
_LEVEL_RANK = {level: index for index, level in enumerate(_LEVELS)}
_PRIORITY_TIERS = ("01_essential", "02_standard", "03_extended")
_LEVEL_FORM_CARD_POLICY_VERSION = "learner-level-form-card-v1"
_LONG_VOWEL_BY_HIRAGANA = {
    **{character: "あ" for character in "ぁあかがさざただなはばぱまゃやらゎわ"},
    **{character: "い" for character in "ぃいきぎしじちぢにひびぴみりゐ"},
    **{character: "う" for character in "ぅうくぐすずつづぬふぶぷむゅゆるゔ"},
    **{character: "え" for character in "ぇえけげせぜてでねへべぺめれゑ"},
    **{character: "お" for character in "ぉおこごそぞとどのほぼぽもょよろを"},
}


class PublicContentError(ValueError):
    """Raised when public content cannot be reconstructed exactly."""


def _normalize_form(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.replace("〜", "～").replace("~", "～")
    return _SPACE_RE.sub("", normalized).strip()


def _is_kana_only(value: str) -> bool:
    return bool(_KANA_ONLY_RE.fullmatch(_normalize_form(value)))


def _has_kanji(value: str) -> bool:
    return any(
        "\u3400" <= character <= "\u4dbf"
        or "\u4e00" <= character <= "\u9fff"
        or character in "々〆ヶ"
        for character in _normalize_form(value)
    )


def _reading_equivalence_key(value: str) -> str:
    normalized = _normalize_form(value)
    hiragana = "".join(
        chr(ord(character) - 0x60)
        if "ァ" <= character <= "ヶ"
        else character
        for character in normalized
    )
    expanded: list[str] = []
    for character in hiragana:
        if character == "ー" and expanded:
            expanded.append(_LONG_VOWEL_BY_HIRAGANA.get(expanded[-1], character))
        else:
            expanded.append(character)
    return "".join(expanded)


def _form_levels(form: Mapping[str, Any]) -> set[str]:
    levels = {
        str(level)
        for values in form.get("source_levels", {}).values()
        for level in values
        if str(level) in _LEVEL_RANK
    }
    if not levels:
        raise PublicContentError(
            f"public form lacks attested JLPT levels: {form.get('surface')}"
        )
    return levels


def _source_level(source_record_id: str) -> str | None:
    lowered = source_record_id.lower()
    for level in _LEVELS:
        if f"-{level.lower()}-" in lowered:
            return level
    return None


def _easiest_level(values: Sequence[str] | set[str]) -> str:
    levels = {str(value) for value in values}
    if not levels or not levels <= set(_LEVELS):
        raise PublicContentError(f"public form has invalid JLPT levels: {levels}")
    return min(levels, key=_LEVEL_RANK.__getitem__)


def _public_display_form(forms: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    placement_level = _easiest_level(
        {level for form in forms for level in _form_levels(form)}
    )
    support: dict[str, dict[str, Any]] = {}
    for form in forms:
        if placement_level not in _form_levels(form):
            continue
        surface = str(form.get("surface", ""))
        reading = str(form.get("reading", ""))
        value = support.setdefault(
            surface,
            {"publishers": set(), "reading": reading, "source_record_ids": set()},
        )
        value["publishers"].update(
            str(publisher)
            for publisher, levels in form.get("source_levels", {}).items()
            if placement_level in levels
        )
        value["source_record_ids"].update(
            str(source_id)
            for source_id in form.get("source_record_ids", [])
            if _source_level(str(source_id)) == placement_level
        )
    if not support:
        raise PublicContentError("public forms do not support their easiest level")
    surface = min(
        support,
        key=lambda value: (
            -len(support[value]["publishers"]),
            -len(support[value]["source_record_ids"]),
            _is_kana_only(value.strip("～")),
            value,
        ),
    )
    return {
        "display_form": surface,
        "display_reading": str(support[surface]["reading"]),
        "placement_level": placement_level,
    }


def _public_level_form_card(
    forms: Sequence[Mapping[str, Any]],
    *,
    display_form: str,
    reading: str,
) -> dict[str, Any] | None:
    if not _is_kana_only(display_form.strip("～")):
        return None
    placement_level = _public_display_form(forms)["placement_level"]
    levels_by_surface: dict[str, set[str]] = {}
    for form in forms:
        surface = str(form.get("surface", ""))
        if not _has_kanji(surface):
            continue
        form_reading = str(form.get("reading", reading))
        if _reading_equivalence_key(form_reading) != _reading_equivalence_key(reading):
            continue
        levels_by_surface.setdefault(surface, set()).update(_form_levels(form))
    advanced_levels_by_surface: dict[str, str] = {}
    for surface, levels in levels_by_surface.items():
        first_level = _easiest_level(levels)
        if _LEVEL_RANK[first_level] <= _LEVEL_RANK[placement_level]:
            continue
        advanced_levels_by_surface[surface] = first_level
    if not advanced_levels_by_surface:
        return None
    target_level = _easiest_level(
        set(advanced_levels_by_surface.values())
    )
    support: dict[str, dict[str, Any]] = {}
    for form in forms:
        surface = str(form.get("surface", ""))
        if (
            advanced_levels_by_surface.get(surface) != target_level
            or target_level not in _form_levels(form)
            or _reading_equivalence_key(str(form.get("reading", reading)))
            != _reading_equivalence_key(reading)
        ):
            continue
        value = support.setdefault(
            surface,
            {"publishers": set(), "source_record_ids": set()},
        )
        value["publishers"].update(
            str(publisher)
            for publisher, levels in form.get("source_levels", {}).items()
            if target_level in levels
        )
        value["source_record_ids"].update(
            str(source_id)
            for source_id in form.get("source_record_ids", [])
            if _source_level(str(source_id)) == target_level
        )
    if not support:
        raise PublicContentError(
            f"public level-form card lacks target-level support: {display_form}"
        )

    def strength_key(surface: str) -> tuple[int, int, bool, str]:
        return (
            -len(support[surface]["publishers"]),
            -len(support[surface]["source_record_ids"]),
            _is_kana_only(surface.strip("～")),
            surface,
        )

    ranked_surfaces = sorted(support, key=strength_key)
    front_word = ranked_surfaces[0]
    return {
        "alternate_forms": ranked_surfaces[1:],
        "front_context": "",
        "front_word": front_word,
        "policy_version": _LEVEL_FORM_CARD_POLICY_VERSION,
        "reading": reading,
        "source_record_ids": sorted(support[front_word]["source_record_ids"]),
        "target_jlpt_level": target_level,
    }


def _reproject_public_learner_form(
    raw_note: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute learner display/card fields from public forms and meaning."""
    note = copy.deepcopy(dict(raw_note))
    forms = note.get("forms")
    if not isinstance(forms, list) or not forms:
        raise PublicContentError(
            f"public learner note lacks forms: {note.get('note_id')}"
        )
    display = _public_display_form(forms)
    level = display["placement_level"]
    reading = display["display_reading"] or str(note.get("reading", ""))
    priority = note.get("study_priority")
    tier = priority.get("tier") if isinstance(priority, Mapping) else None
    if not reading or tier not in _PRIORITY_TIERS:
        raise PublicContentError(
            f"public learner note lacks display metadata: {note.get('note_id')}"
        )
    note["word"] = display["display_form"]
    note["vocabulary_front"] = note["word"]
    note["reading"] = reading
    note["jlpt_level"] = level
    note["card_templates"] = ["어휘", "음성"]
    note["deck_keys"] = [f"vocabulary:{level}", f"audio:{level}"]
    note.pop("front_hint", None)
    note.pop("vocabulary_context", None)
    note.pop("simple_orthography", None)
    note.pop("level_form_card", None)
    level_form_card = _public_level_form_card(
        forms,
        display_form=note["word"],
        reading=reading,
    )
    if level_form_card is not None:
        note["level_form_card"] = level_form_card
        note["card_templates"].append("어휘(상위급수)")
        note["deck_keys"].append(
            f"vocabulary:{level_form_card['target_jlpt_level']}"
        )
    note["tags"] = sorted(
        {
            *(
                str(tag)
                for tag in note.get("tags", [])
                if not str(tag).startswith(("jlpt::", "priority::"))
            ),
            f"jlpt::{level}",
            f"priority::{tier}",
        }
    )
    note_id = str(note.get("note_id", ""))
    reading_override = PUBLIC_READING_OVERRIDES.get(note_id)
    if reading_override is None:
        return note
    reading = "・".join(reading_override)
    note["reading_variants"] = list(reading_override)
    note["reading"] = reading
    level_form_card = note.get("level_form_card")
    if isinstance(level_form_card, dict):
        level_form_card["reading"] = reading
    return note


def _public_lexeme_sequences(note: Mapping[str, Any]) -> set[str]:
    return {
        str(sense["jmdict_sequence"])
        for sense in note.get("meaning_senses", [])
        if isinstance(sense, Mapping) and sense.get("jmdict_sequence")
    }


def _public_reading_keys(note: Mapping[str, Any]) -> set[str]:
    return {
        _reading_equivalence_key(value)
        for value in str(note.get("reading", "")).split("・")
        if _normalize_form(value)
    }


def _public_sense_ids(note: Mapping[str, Any], sequence: str) -> set[str]:
    return {
        str(sense_id)
        for sense in note.get("meaning_senses", [])
        if isinstance(sense, Mapping)
        and str(sense.get("jmdict_sequence", "")) == sequence
        for sense_id in sense.get("jmdict_sense_ids", [])
    }


def _public_collision_requires_merge(
    cards: Sequence[Mapping[str, Any]],
) -> bool:
    sequence_sets = [
        _public_lexeme_sequences(card["note"]) for card in cards
    ]
    if any(not values for values in sequence_sets):
        return True
    for index, left_card in enumerate(cards):
        left_note = left_card["note"]
        for right_card in cards[index + 1 :]:
            right_note = right_card["note"]
            shared_sequences = (
                _public_lexeme_sequences(left_note)
                & _public_lexeme_sequences(right_note)
            )
            if not shared_sequences:
                continue
            if _public_reading_keys(left_note) & _public_reading_keys(
                right_note
            ):
                return True
            for sequence in shared_sequences:
                left_senses = _public_sense_ids(left_note, sequence)
                right_senses = _public_sense_ids(right_note, sequence)
                if (
                    not left_senses
                    or not right_senses
                    or bool(left_senses & right_senses)
                ):
                    return True
    return False


def _public_front_context(
    note: Mapping[str, Any], front_surface: str
) -> str | None:
    candidates: list[tuple[int, str, str]] = []
    for example in note.get("examples", []):
        if not isinstance(example, Mapping):
            continue
        japanese = str(example.get("japanese", "")).strip()
        target_id = str(example.get("target_id", ""))
        if (
            not japanese
            or not target_id
            or japanese.count(front_surface) != 1
            or any(
                character in japanese
                for character in "<>()（）[]［］【】\r\n"
            )
            or _HANGUL_RE.search(japanese)
        ):
            continue
        candidates.append((len(japanese), japanese, target_id))
    return min(candidates)[1] if candidates else None


def _refresh_public_vocabulary_fronts(
    notes: Sequence[dict[str, Any]],
) -> None:
    for note in notes:
        note.pop("front_hint", None)
        note.pop("vocabulary_context", None)
        note["vocabulary_front"] = str(note["word"])
        level_form_card = note.get("level_form_card")
        if isinstance(level_form_card, dict):
            level_form_card["front_context"] = ""
    cards_by_front: dict[
        tuple[str, str, str], list[dict[str, Any]]
    ] = {}
    for note in notes:
        level = str(note["jlpt_level"])
        word = str(note["word"])
        cards_by_front.setdefault(
            ("visual", level, word), []
        ).append(
            {
                "card_kind": "vocabulary",
                "context_surface": word,
                "note": note,
            }
        )
        level_form_card = note.get("level_form_card")
        if isinstance(level_form_card, dict):
            cards_by_front.setdefault(
                (
                    "visual",
                    str(level_form_card["target_jlpt_level"]),
                    str(level_form_card["front_word"]),
                ),
                [],
            ).append(
                {
                    "card_kind": "level_form",
                    "context_surface": str(level_form_card["front_word"]),
                    "note": note,
                }
            )

    collision_groups: list[tuple[list[dict[str, Any]], bool]] = []
    blocked_note_ids: set[str] = set()
    for _key, cards in sorted(cards_by_front.items()):
        if len(cards) < 2:
            continue
        cards.sort(
            key=lambda card: (
                str(card["card_kind"]),
                str(card["note"].get("note_id", "")),
            )
        )
        requires_merge = _public_collision_requires_merge(cards)
        if requires_merge:
            blocked_note_ids.update(
                str(card["note"].get("note_id", "")) for card in cards
            )
        collision_groups.append((cards, requires_merge))

    for cards, requires_merge in collision_groups:
        note_ids = {
            str(card["note"].get("note_id", "")) for card in cards
        }
        if requires_merge or note_ids & blocked_note_ids:
            continue
        for card in cards:
            note = card["note"]
            context = _public_front_context(
                note, str(card["context_surface"])
            )
            if context is None:
                continue
            if card["card_kind"] == "vocabulary":
                previous_context = note.get("vocabulary_context")
                if previous_context not in {None, context}:
                    raise PublicContentError(
                        "public visual collisions selected different context"
                    )
                note["vocabulary_context"] = context
            else:
                level_form_card = note.get("level_form_card")
                if not isinstance(level_form_card, dict):
                    raise PublicContentError("public level-form context lost payload")
                level_form_card["front_context"] = context


def _source_korean_suffix(value: str) -> str:
    match = _HANGUL_RE.search(value)
    if match is None:
        raise PublicContentError("source cell has no Korean suffix")
    return value[value.rfind(" ", 0, match.start()) + 1 :].strip()

def _normalized_meaning_atoms(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value)
    atoms: list[str] = []
    for raw in _MEANING_SEPARATOR_RE.split(normalized):
        atom = _SPACE_RE.sub(" ", raw).strip(" .·ㆍ")
        atom = _LEADING_NUMBER_RE.sub("", atom).strip()
        if atom and atom not in atoms:
            atoms.append(atom)
    return atoms


def source_union_meaning(
    source_record_ids: Sequence[str],
    source_records: Mapping[str, Mapping[str, Any]],
) -> str:
    """Join unique publisher variants inside one reviewed sense."""
    atoms: list[str] = []
    for source_record_id in source_record_ids:
        record = source_records.get(source_record_id)
        if record is None:
            raise PublicContentError(
                f"public source record is missing: {source_record_id}"
            )
        publisher = str(record.get("publisher", ""))
        meaning = record.get("meaning")
        if publisher not in PUBLIC_PUBLISHERS or not isinstance(meaning, str):
            raise PublicContentError(
                f"public source meaning is invalid: {source_record_id}"
            )
        for atom in _normalized_meaning_atoms(meaning):
            if atom not in atoms:
                atoms.append(atom)
    if not atoms:
        raise PublicContentError("public sense has no source meaning")
    result = ",".join(atoms)
    if ";" in result:
        raise PublicContentError("public sense contains a semicolon")
    return result

def _materialized_provenance(
    source_record_ids: Sequence[str],
    source_records: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source_record_id in source_record_ids:
        record = source_records[source_record_id]
        result.append(
            {
                "page": record.get("page"),
                "pdf_sha256": record.get("pdf_sha256"),
                "publisher": record.get("publisher"),
                "row_id": record.get("row_id"),
                "source_record_id": source_record_id,
                "verified_meaning": str(record.get("meaning", "")),
            }
        )
    return result


def materialize_vocabulary_notes(
    templates: Sequence[Mapping[str, Any]],
    recipes: Sequence[Mapping[str, Any]],
    source_records: Mapping[str, Mapping[str, Any]],
    *,
    kanji_details_by_note: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Fill public meaning duplicates from exact locally extracted records."""
    recipe_by_id = {str(recipe.get("note_id")): recipe for recipe in recipes}
    if len(recipe_by_id) != len(recipes):
        raise PublicContentError("public vocabulary recipes have duplicate IDs")
    materialized: list[dict[str, Any]] = []
    for raw in templates:
        note = copy.deepcopy(dict(raw))
        note_id = str(note.get("note_id", ""))
        recipe = recipe_by_id.get(note_id)
        if recipe is None:
            raise PublicContentError(f"public vocabulary recipe is missing: {note_id}")
        raw_sense_recipes = recipe.get("senses")
        senses = note.get("meaning_senses")
        if not isinstance(raw_sense_recipes, list) or not isinstance(senses, list):
            raise PublicContentError(f"public sense recipe is invalid: {note_id}")
        if len(raw_sense_recipes) != len(senses):
            raise PublicContentError(f"public sense count changed: {note_id}")
        meanings: list[str] = []
        meaning_by_sense: dict[str, str] = {}
        for sense, sense_recipe in zip(senses, raw_sense_recipes, strict=True):
            if not isinstance(sense, dict) or not isinstance(sense_recipe, dict):
                raise PublicContentError("public sense materialization is invalid")
            source_record_ids = sense_recipe.get("source_record_ids")
            if not isinstance(source_record_ids, list) or any(
                not isinstance(value, str) for value in source_record_ids
            ):
                raise PublicContentError("public sense sources are invalid")
            meaning = source_union_meaning(source_record_ids, source_records)
            if sha256_json(meaning) != sense_recipe.get("expected_meaning_hash"):
                raise PublicContentError(
                    f"public sense meaning hash changed: {note_id}"
                )
            sense["meaning"] = meaning
            sense["source_provenance"] = _materialized_provenance(
                source_record_ids, source_records
            )
            meanings.append(meaning)
            meaning_by_sense[str(sense.get("meaning_sense_id"))] = meaning
        note_meaning = " / ".join(meanings)
        if sha256_json(note_meaning) != recipe.get("expected_meaning_hash"):
            raise PublicContentError(f"public note meaning hash changed: {note_id}")
        note["meaning"] = note_meaning
        note = _reproject_public_learner_form(note)
        for example in note.get("examples", []):
            if isinstance(example, dict):
                sense_id = str(example.get("meaning_sense_id", ""))
                if sense_id not in meaning_by_sense:
                    raise PublicContentError(
                        f"public example references a removed sense: {note_id}"
                    )
                example["sense"] = meaning_by_sense[sense_id]
        if kanji_details_by_note is not None:
            note["kanji_details"] = copy.deepcopy(
                list(kanji_details_by_note.get(note_id, ()))
            )
        materialized.append(note)

    _refresh_public_vocabulary_fronts(materialized)

    meaning_by_note = {
        str(note["note_id"]): str(note["meaning"]) for note in materialized
    }
    public_ids = set(meaning_by_note)
    for note in materialized:
        recipe = recipe_by_id[str(note["note_id"])]
        note["related_words"] = [
            related
            for related in note.get("related_words", [])
            if isinstance(related, dict) and related.get("target_id") in public_ids
        ]
        for related in note["related_words"]:
            related["meaning"] = meaning_by_note[str(related["target_id"])]
        relations: list[dict[str, Any]] = []
        for relation in note.get("word_formation", []):
            if not isinstance(relation, dict):
                continue
            components = relation.get("components")
            if not isinstance(components, list) or any(
                not isinstance(component, dict)
                or component.get("note_id") not in public_ids
                for component in components
            ):
                continue
            for component in components:
                component["meaning"] = meaning_by_note[str(component["note_id"])]
            relations.append(relation)
        note["word_formation"] = relations
        raw_usage_recipes = recipe.get("usage_details")
        usage_details = note.get("usage_details")
        if not isinstance(raw_usage_recipes, list) or not isinstance(
            usage_details, list
        ) or len(raw_usage_recipes) != len(usage_details):
            raise PublicContentError(
                f"public usage recipe changed: {note['note_id']}"
            )
        for usage, usage_recipe in zip(
            usage_details, raw_usage_recipes, strict=True
        ):
            if not isinstance(usage, dict) or not isinstance(usage_recipe, dict):
                raise PublicContentError("public usage materialization is invalid")
            items = [usage, *usage.get("contrast_items", [])]
            item_recipes = usage_recipe.get("items")
            if not isinstance(item_recipes, list) or len(item_recipes) != len(items):
                raise PublicContentError("public usage item count changed")
            for item, item_recipe in zip(items, item_recipes, strict=True):
                if not isinstance(item, dict) or not isinstance(item_recipe, dict):
                    raise PublicContentError("public usage item recipe is invalid")
                source_record_id = str(item_recipe.get("source_record_id", ""))
                meaning = str(
                    source_records.get(source_record_id, {}).get("meaning", "")
                )
                if sha256_json(meaning) != item_recipe.get(
                    "expected_meaning_hash"
                ):
                    raise PublicContentError(
                        f"public usage meaning changed: {source_record_id}"
                    )
                item["meaning_ko"] = meaning
        note["canonical_record_hash"] = sha256_json(
            {
                key: value
                for key, value in note.items()
                if key != "canonical_record_hash"
            }
        )
    return materialized




def materialize_reference_notes(
    templates: Sequence[Mapping[str, Any]],
    recipes: Sequence[Mapping[str, Any]],
    source_cells: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    recipe_by_id = {str(recipe.get("note_id")): recipe for recipe in recipes}
    result: list[dict[str, Any]] = []
    for raw in templates:
        note = copy.deepcopy(dict(raw))
        note_id = str(note.get("note_id", ""))
        recipe = recipe_by_id.get(note_id)
        if recipe is None:
            raise PublicContentError(f"public reference recipe is missing: {note_id}")
        cell_recipe_by_id = {
            str(item.get("cell_id")): item for item in recipe.get("cells", [])
        }
        for cell in note.get("cells", []):
            cell_id = str(cell.get("cell_id", ""))
            source = source_cells.get(cell_id)
            cell_recipe = cell_recipe_by_id.get(cell_id)
            if source is None or cell_recipe is None:
                raise PublicContentError(f"public reference cell is missing: {cell_id}")
            value = str(source.get("normalized_text", ""))
            if sha256_json(value) != cell_recipe.get("expected_text_hash"):
                raise PublicContentError(f"public reference cell changed: {cell_id}")
            cell["normalized_text"] = value
        result.append(note)
    return result




def materialize_practice_notes(
    templates: Sequence[Mapping[str, Any]],
    recipes: Sequence[Mapping[str, Any]],
    source_records: Mapping[str, Mapping[str, Any]],
    public_meanings: Mapping[str, str],
    source_cells: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    recipe_by_id = {str(recipe.get("question_id")): recipe for recipe in recipes}
    if len(recipe_by_id) != len(recipes):
        raise PublicContentError("public practice recipes have duplicate IDs")
    result: list[dict[str, Any]] = []
    for raw in templates:
        note = copy.deepcopy(dict(raw))
        question_id = str(note.get("question_id", ""))
        recipe = recipe_by_id.get(question_id)
        if recipe is None:
            raise PublicContentError(f"public practice recipe is missing: {question_id}")
        reference_recipe = recipe.get("reference")
        if isinstance(reference_recipe, dict):
            if source_cells is None:
                raise PublicContentError(
                    f"public reference practice cells are missing: {question_id}"
                )
            answer_cell_id = str(reference_recipe.get("answer_cell_id", ""))
            answer_source_text = str(
                source_cells.get(answer_cell_id, {}).get("normalized_text", "")
            )
            answer_ko = _source_korean_suffix(answer_source_text)
            if (
                sha256_json(answer_source_text)
                != reference_recipe.get("expected_answer_source_text_hash")
                or sha256_json(answer_ko)
                != reference_recipe.get("expected_answer_ko_hash")
            ):
                raise PublicContentError(
                    f"public reference practice answer changed: {question_id}"
                )
            note["answer_ko"] = answer_ko
            header_cell_id = reference_recipe.get("header_cell_id")
            if header_cell_id is not None:
                header_text = str(
                    source_cells.get(str(header_cell_id), {}).get(
                        "normalized_text", ""
                    )
                )
                if sha256_json(header_text) != reference_recipe.get(
                    "expected_table_group_hash"
                ):
                    raise PublicContentError(
                        f"public counter practice header changed: {question_id}"
                    )
                note["table_group"] = header_text
            result.append(note)
            continue
        targets = note.get("covered_targets")
        target_recipes = recipe.get("targets")
        if not isinstance(targets, list) or not isinstance(target_recipes, list):
            raise PublicContentError(f"public practice targets changed: {question_id}")
        if len(targets) != len(target_recipes):
            raise PublicContentError(f"public practice target count changed: {question_id}")
        for target, target_recipe in zip(targets, target_recipes, strict=True):
            if not isinstance(target, dict) or not isinstance(target_recipe, dict):
                raise PublicContentError("public practice target is invalid")
            candidate_id = str(target_recipe.get("candidate_id", ""))
            canonical_id = str(target_recipe.get("canonical_id", ""))
            source_meaning = str(source_records.get(candidate_id, {}).get("meaning", ""))
            canonical_meaning = public_meanings.get(canonical_id)
            if canonical_meaning is None:
                canonical_source_record_ids = target_recipe.get(
                    "canonical_source_record_ids"
                )
                if not isinstance(canonical_source_record_ids, list) or any(
                    not isinstance(value, str)
                    for value in canonical_source_record_ids
                ):
                    raise PublicContentError(
                        f"public practice canonical recipe changed: {question_id}"
                    )
                canonical_meaning = source_union_meaning(
                    canonical_source_record_ids, source_records
                )
            if (
                sha256_json(source_meaning)
                != target_recipe.get("expected_source_meaning_hash")
                or canonical_meaning is None
                or sha256_json(canonical_meaning)
                != target_recipe.get("expected_canonical_meaning_hash")
            ):
                raise PublicContentError(
                    f"public practice meaning hash changed: {question_id}:{candidate_id}"
                )
            target["meaning"] = source_meaning
            target["canonical_meaning"] = canonical_meaning
            target["target_hash"] = sha256_json(
                {key: value for key, value in target.items() if key != "target_hash"}
            )

        effective_recipes = recipe.get("effective_items")
        review = note.get("review_provenance")
        if effective_recipes:
            if not isinstance(effective_recipes, list) or not isinstance(review, dict):
                raise PublicContentError(
                    f"public practice review recipe is invalid: {question_id}"
                )
            effective_items = review.get("effective_items")
            if not isinstance(effective_items, list) or len(effective_items) != len(
                effective_recipes
            ):
                raise PublicContentError(
                    f"public practice effective items changed: {question_id}"
                )
            for item, item_recipe in zip(
                effective_items, effective_recipes, strict=True
            ):
                if not isinstance(item, dict) or not isinstance(item_recipe, dict):
                    raise PublicContentError("public practice effective item is invalid")
                candidate_id = str(item_recipe.get("candidate_id", ""))
                source_meaning = str(
                    source_records.get(candidate_id, {}).get("meaning", "")
                )
                if sha256_json(source_meaning) != item_recipe.get(
                    "expected_source_meaning_hash"
                ):
                    raise PublicContentError(
                        f"public practice effective meaning changed: {question_id}"
                    )
                item["meaning"] = source_meaning
            for key in ("evidence_hash", "input_hash", "review_hash"):
                if key in review:
                    review[key] = sha256_json(
                        {name: value for name, value in review.items() if name != key}
                    )
        if "resolution_input_hash" in note:
            note["resolution_input_hash"] = sha256_json(
                {
                    key: value
                    for key, value in note.items()
                    if key != "resolution_input_hash"
                }
            )
        result.append(note)
    return result
