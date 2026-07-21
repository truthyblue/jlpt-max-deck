from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from public_layout_cells import (  # noqa: E402
    CellContractError,
    build_lexeme_candidates,
    make_cell,
    reconcile_page_cells,
)


PDF_HASH = "a" * 64


def _cell(
    *,
    role: str,
    text: str,
    row_id: str = "c1-r1",
    status: str = "accepted",
    extraction_provenance: dict[str, object] | None = None,
) -> dict[str, object]:
    return make_cell(
        source_id="publisher-n5-wordbook",
        pdf_sha256=PDF_HASH,
        page=17,
        layout_id="hackers_vocab_two_column",
        row_id=row_id,
        role=role,
        bbox=(0.1, 0.2, 0.3, 0.25),
        raw_fragments=(
            {
                "text": text,
                "bbox": [0.1, 0.2, 0.3, 0.25],
                "font_name": "FixtureFont",
                "font_size": 8.5,
            },
        ),
        extraction_method="text_geometry",
        confidence=0.99,
        status=status,
        status_reason=None if status == "accepted" else f"fixture_{status}",
        extraction_provenance=extraction_provenance,
    )


class PublicLayoutCellContractTest(unittest.TestCase):
    def test_cell_preserves_complete_provenance_and_normalizes_text(self) -> None:
        cell = make_cell(
            source_id="publisher-n5-wordbook",
            pdf_sha256=PDF_HASH,
            page=3,
            layout_id="hackers_vocab_two_column",
            row_id="c1-r1",
            role="lexeme_surface",
            bbox=(0.1, 0.2, 0.3, 0.25),
            raw_fragments=(
                {
                    "text": " 語\u3000句 ",
                    "bbox": [0.1, 0.2, 0.3, 0.25],
                    "font_name": "FixtureFont",
                    "font_size": 8.5,
                },
            ),
            extraction_method="text_geometry",
            confidence=0.99,
            status="accepted",
        )

        self.assertEqual(cell["cell_id"], "publisher-n5-wordbook:p0003:c1-r1:lexeme_surface")
        self.assertEqual(cell["bbox_space"], "normalized_top_left")
        self.assertEqual(cell["raw_text"], " 語\u3000句 ")
        self.assertEqual(cell["normalized_text"], "語 句")
        self.assertEqual(cell["pdf_sha256"], PDF_HASH)
        self.assertEqual(cell["layout_id"], "hackers_vocab_two_column")
        self.assertEqual(cell["extraction_method"], "text_geometry")
        self.assertEqual(cell["confidence"], 0.99)

    def test_cell_keeps_json_safe_extraction_provenance(self) -> None:
        cell = _cell(
            role="lexeme_surface",
            text="愛想",
            extraction_provenance={
                "crop_sha256": "a" * 64,
                "observations": [{"text": "愛想", "confidence": 1.0}],
            },
        )

        provenance = cell["extraction_provenance"]
        self.assertIsInstance(provenance, dict)
        assert isinstance(provenance, dict)
        self.assertEqual(provenance["observations"][0]["text"], "愛想")

    def test_cell_rejects_non_json_extraction_provenance(self) -> None:
        with self.assertRaisesRegex(CellContractError, "JSON-safe"):
            _cell(
                role="lexeme_surface",
                text="愛想",
                extraction_provenance={"invalid": {1, 2}},
            )

    def test_rejects_invalid_bbox_role_status_hash_and_fragment_escape(self) -> None:
        cases = (
            ({"role": "lexeme", "bbox": (0.1, 0.2, 0.3, 0.25)}, "cell role"),
            ({"role": "lexeme_surface", "bbox": (0.3, 0.2, 0.1, 0.25)}, "bbox"),
            (
                {
                    "role": "lexeme_surface",
                    "bbox": (0.1, 0.2, 0.3, 0.25),
                    "status": "unknown",
                },
                "status",
            ),
            (
                {
                    "role": "lexeme_surface",
                    "bbox": (0.1, 0.2, 0.3, 0.25),
                    "pdf_sha256": "bad",
                },
                "PDF hash",
            ),
        )
        for changed, message in cases:
            arguments = {
                "source_id": "publisher-n5-wordbook",
                "pdf_sha256": PDF_HASH,
                "page": 3,
                "layout_id": "hackers_vocab_two_column",
                "row_id": "c1-r1",
                "role": "lexeme_surface",
                "bbox": (0.1, 0.2, 0.3, 0.25),
                "raw_fragments": (
                    {
                        "text": "語句",
                        "bbox": [0.1, 0.2, 0.3, 0.25],
                        "font_name": "FixtureFont",
                        "font_size": 8.5,
                    },
                ),
                "extraction_method": "text_geometry",
                "confidence": 0.99,
                "status": "accepted",
                "status_reason": None,
            }
            arguments.update(changed)
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(CellContractError, message):
                    make_cell(**arguments)

        with self.assertRaisesRegex(CellContractError, "fragment bbox escapes"):
            make_cell(
                source_id="publisher-n5-wordbook",
                pdf_sha256=PDF_HASH,
                page=3,
                layout_id="hackers_vocab_two_column",
                row_id="c1-r1",
                role="lexeme_surface",
                bbox=(0.1, 0.2, 0.3, 0.25),
                raw_fragments=(
                    {
                        "text": "語句",
                        "bbox": [0.05, 0.2, 0.3, 0.25],
                        "font_name": "FixtureFont",
                        "font_size": 8.5,
                    },
                ),
                extraction_method="text_geometry",
                confidence=0.99,
                status="accepted",
                status_reason=None,
            )

    def test_structural_cells_never_become_ordinary_lexeme_candidates(self) -> None:
        cells = [
            _cell(role="query_row_header", text="なに・なん(何)"),
            _cell(role="counter_header", text="～こ(個)", row_id="header-1"),
            _cell(role="counter_example", text="いっこ", row_id="r1-c1"),
            _cell(role="calendar_lexeme", text="ついたち", row_id="calendar-r1-c1"),
        ]

        self.assertEqual(build_lexeme_candidates(cells), [])

    def test_candidate_links_typed_cells_instead_of_reparsing_text(self) -> None:
        cells = [
            _cell(role="lexeme_surface", text="語句"),
            _cell(role="lexeme_reading", text="ごく"),
            _cell(role="pos", text="명"),
            _cell(role="meaning", text="어구"),
        ]

        candidates = build_lexeme_candidates(cells)

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["surface"], "語句")
        self.assertEqual(candidate["reading"], "ごく")
        self.assertEqual(candidate["pos"], "명")
        self.assertEqual(candidate["meaning"], "어구")
        self.assertEqual(
            candidate["source_cell_ids"],
            {
                "lexeme_surface": "publisher-n5-wordbook:p0017:c1-r1:lexeme_surface",
                "lexeme_reading": "publisher-n5-wordbook:p0017:c1-r1:lexeme_reading",
                "pos": "publisher-n5-wordbook:p0017:c1-r1:pos",
                "meaning": "publisher-n5-wordbook:p0017:c1-r1:meaning",
            },
        )

    def test_page_reconciliation_counts_every_declared_role_and_status(self) -> None:
        cells = [
            _cell(role="lexeme_surface", text="語句", row_id="r1"),
            _cell(
                role="lexeme_surface",
                text="",
                row_id="r2",
                status="pending_review",
            ),
            _cell(role="meaning", text="어구", row_id="r1"),
            _cell(role="meaning", text="", row_id="r2", status="excluded"),
        ]

        report = reconcile_page_cells(
            cells,
            declared_role_counts={"lexeme_surface": 2, "meaning": 2},
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["declared_cells"], 4)
        self.assertEqual(report["observed_cells"], 4)
        self.assertEqual(
            report["status_counts"],
            {"accepted": 2, "excluded": 1, "pending_review": 1},
        )

        with self.assertRaisesRegex(CellContractError, "declared role count mismatch"):
            reconcile_page_cells(
                cells,
                declared_role_counts={"lexeme_surface": 3, "meaning": 2},
            )

        with self.assertRaisesRegex(CellContractError, "duplicate cell_id"):
            reconcile_page_cells(
                [cells[0], cells[0]],
                declared_role_counts={"lexeme_surface": 2},
            )


if __name__ == "__main__":
    unittest.main()
