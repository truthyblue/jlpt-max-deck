from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from public_content import (  # noqa: E402
    PublicContentError,
    materialize_practice_notes,
    materialize_reference_notes,
    materialize_vocabulary_notes,
    source_union_meaning,
)
from public_hashing import sha256_json  # noqa: E402


def _source(source_id: str, meaning: str) -> dict[str, object]:
    return {
        "meaning": meaning,
        "page": 7,
        "pdf_sha256": "a" * 64,
        "publisher": source_id.split("-", 1)[0],
        "row_id": "c1-r1",
    }


class PublicContentTest(unittest.TestCase):
    def test_source_union_normalizes_and_deduplicates_meaning_atoms(self) -> None:
        records = {
            "dongyang-n5:p0001:c1-r1": _source(
                "dongyang-n5", "생선, 물고기"
            ),
            "hackers-n5:p0001:c1-r1": _source(
                "hackers-n5", "물고기"
            ),
        }

        self.assertEqual(
            source_union_meaning(list(records), records),
            "생선,물고기",
        )

    def test_materializes_vocabulary_meaning_from_hash_bound_source(self) -> None:
        source_id = "hackers-n5-wordbook:p0001:c1-r1"
        records = {source_id: _source("hackers-n5-wordbook", "생선, 물고기")}
        expected_meaning = "생선,물고기"
        templates = [
            {
                "canonical_record_hash": "",
                "examples": [
                    {"meaning_sense_id": "sense-fish", "sense": ""}
                ],
                "forms": [
                    {
                        "publishers": ["hackers"],
                        "reading": "さかな",
                        "source_levels": {"hackers": ["N5"]},
                        "source_record_ids": [source_id],
                        "surface": "魚",
                    }
                ],
                "meaning": "",
                "meaning_senses": [
                    {
                        "meaning": "",
                        "meaning_sense_id": "sense-fish",
                        "source_provenance": [],
                    }
                ],
                "note_id": "ci-fish",
                "reading": "さかな",
                "related_words": [],
                "study_priority": {
                    "rank_within_level": 1,
                    "tier": "02_standard",
                },
                "tags": [],
                "usage_details": [],
                "word_formation": [],
            }
        ]
        recipes = [
            {
                "expected_meaning_hash": sha256_json(expected_meaning),
                "note_id": "ci-fish",
                "senses": [
                    {
                        "expected_meaning_hash": sha256_json(expected_meaning),
                        "meaning_sense_id": "sense-fish",
                        "source_record_ids": [source_id],
                    }
                ],
                "usage_details": [],
            }
        ]

        materialized = materialize_vocabulary_notes(
            templates,
            recipes,
            records,
            kanji_details_by_note={"ci-fish": [{"study_hint": "물고기 어"}]},
        )

        note = materialized[0]
        self.assertEqual(note["meaning"], expected_meaning)
        self.assertEqual(note["examples"][0]["sense"], expected_meaning)
        self.assertEqual(note["vocabulary_front"], "魚")
        self.assertNotIn("front_hint", note)
        self.assertEqual(note["kanji_details"], [{"study_hint": "물고기 어"}])

        changed_records = {
            source_id: _source("hackers-n5-wordbook", "다른 뜻")
        }
        with self.assertRaisesRegex(PublicContentError, "hash changed"):
            materialize_vocabulary_notes(templates, recipes, changed_records)

    def test_materializes_reference_cell_and_rejects_changed_text(self) -> None:
        cell_id = "hackers:p0001:r1:meaning"
        templates = [
            {
                "note_id": "rt:fixture",
                "cells": [{"cell_id": cell_id, "normalized_text": ""}],
            }
        ]
        recipes = [
            {
                "note_id": "rt:fixture",
                "cells": [
                    {
                        "cell_id": cell_id,
                        "expected_text_hash": sha256_json("한 개"),
                    }
                ],
            }
        ]

        hydrated = materialize_reference_notes(
            templates,
            recipes,
            {cell_id: {"normalized_text": "한 개"}},
        )

        self.assertEqual(hydrated[0]["cells"][0]["normalized_text"], "한 개")
        with self.assertRaisesRegex(PublicContentError, "changed"):
            materialize_reference_notes(
                templates,
                recipes,
                {cell_id: {"normalized_text": "두 개"}},
            )

    def test_materializes_practice_duplicates_from_public_inputs(self) -> None:
        candidate_id = "hackers-n1-wordbook:p0001:c1-r1"
        source_records = {
            candidate_id: _source("hackers-n1-wordbook", "업무, 일")
        }
        canonical_meaning = "업무,일"
        templates = [
            {
                "covered_targets": [
                    {
                        "candidate_id": candidate_id,
                        "canonical_id": "ci-work",
                        "canonical_meaning": "",
                        "meaning": "",
                        "reading": "しごと",
                        "surface": "仕事",
                        "target_hash": "",
                    }
                ],
                "question_id": "pq:fixture",
                "resolution_input_hash": "",
                "review_provenance": {
                    "effective_items": [
                    {
                        "meaning": "",
                        "reading": "しごと",
                        "surface": "仕事",
                    }
                    ],
                    "input_hash": "",
                },
            }
        ]
        recipes = [
            {
                "effective_items": [
                    {
                        "candidate_id": candidate_id,
                        "expected_source_meaning_hash": sha256_json("업무, 일"),
                        "index": 0,
                    }
                ],
                "question_id": "pq:fixture",
                "targets": [
                    {
                        "candidate_id": candidate_id,
                        "canonical_id": "ci-work",
                        "canonical_source_record_ids": [],
                        "expected_canonical_meaning_hash": sha256_json(
                            canonical_meaning
                        ),
                        "expected_source_meaning_hash": sha256_json("업무, 일"),
                        "index": 0,
                    }
                ],
            }
        ]

        hydrated = materialize_practice_notes(
            templates,
            recipes,
            source_records,
            {"ci-work": canonical_meaning},
        )

        target = hydrated[0]["covered_targets"][0]
        self.assertEqual(target["meaning"], "업무, 일")
        self.assertEqual(target["canonical_meaning"], canonical_meaning)
        self.assertEqual(
            hydrated[0]["review_provenance"]["effective_items"][0]["meaning"],
            "업무, 일",
        )


if __name__ == "__main__":
    unittest.main()
