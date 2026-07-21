from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from public_hashing import sha256_json  # noqa: E402
from public_source_proof import (  # noqa: E402
    MatchedPdf,
    PublicSourceProofError,
    _text_layer_receipt,
    _validated_catalog,
    build_source_proof,
    match_public_pdfs,
)


def _write_pdf(path: Path, pages: int) -> tuple[int, str]:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        writer.write(output)
    payload = path.read_bytes()
    return len(payload), hashlib.sha256(payload).hexdigest()


def _write_text_pdf(path: Path, text: str = "fixture") -> tuple[int, str]:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_reference}
            )
        }
    )
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        writer.write(output)
    payload = path.read_bytes()
    return len(payload), hashlib.sha256(payload).hexdigest()


def _write_catalog(path: Path, records: list[dict[str, Any]]) -> None:
    normalized_records = [
        {
            "document_role": "wordbook",
            "publisher": "hackers",
            **record,
        }
        for record in records
    ]
    value = {
        "expected_pdf_count": len(normalized_records),
        "expected_total_bytes": sum(
            int(record["expected_bytes"]) for record in normalized_records
        ),
        "expected_total_pages": sum(
            int(record["expected_page_count"]) for record in normalized_records
        ),
        "pdfs": normalized_records,
        "policy_version": "fixture",
        "schema_version": 1,
        "status": "passed",
        "unresolved": 0,
    }
    path.write_text(json.dumps(value), encoding="utf-8")


class PublicSourceProofTest(unittest.TestCase):
    def test_matches_arbitrary_nested_filenames_by_hash_and_catalog_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "downloads" / "아무이름.pdf"
            second = root / "other.pdf"
            first_bytes, first_hash = _write_pdf(first, 1)
            second_bytes, second_hash = _write_pdf(second, 2)
            catalog = root / "catalog.json"
            _write_catalog(
                catalog,
                [
                    {
                        "expected_bytes": second_bytes,
                        "expected_page_count": 2,
                        "pdf_sha256": second_hash,
                        "proof_mode": "text_layer",
                        "source_id": "second",
                    },
                    {
                        "expected_bytes": first_bytes,
                        "expected_page_count": 1,
                        "pdf_sha256": first_hash,
                        "proof_mode": "text_layer",
                        "source_id": "first",
                    },
                ],
            )

            _catalog, matches = match_public_pdfs(root, catalog)

        self.assertEqual(
            [match.record["source_id"] for match in matches], ["second", "first"]
        )
        self.assertEqual([match.path.name for match in matches], ["other.pdf", "아무이름.pdf"])

    def test_rejects_unknown_duplicate_and_missing_pdfs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            supported = root / "supported.pdf"
            byte_count, digest = _write_pdf(supported, 1)
            catalog = root / "catalog.json"
            _write_catalog(
                catalog,
                [
                    {
                        "expected_bytes": byte_count,
                        "expected_page_count": 1,
                        "pdf_sha256": digest,
                        "proof_mode": "text_layer",
                        "source_id": "supported",
                    }
                ],
            )

            duplicate = root / "duplicate.pdf"
            duplicate.write_bytes(supported.read_bytes())
            with self.assertRaisesRegex(PublicSourceProofError, "duplicate supported"):
                match_public_pdfs(root, catalog)
            duplicate.unlink()

            unknown = root / "unknown.pdf"
            _write_pdf(unknown, 2)
            with self.assertRaisesRegex(PublicSourceProofError, "unsupported PDF"):
                match_public_pdfs(root, catalog)
            unknown.unlink()

            supported.unlink()
            with self.assertRaisesRegex(PublicSourceProofError, "no PDFs"):
                match_public_pdfs(root, catalog)

    def test_repository_catalog_closes_declared_totals(self) -> None:
        catalog = _validated_catalog(ROOT / "config" / "public-sources.json")
        self.assertEqual(catalog["expected_pdf_count"], 17)
        self.assertEqual(catalog["expected_total_pages"], 785)
        self.assertEqual(catalog["expected_total_bytes"], 61555395)
        self.assertEqual(
            {
                publisher: sum(
                    record["publisher"] == publisher for record in catalog["pdfs"]
                )
                for publisher in ("dongyang", "gilbut", "hackers")
            },
            {"dongyang": 5, "gilbut": 2, "hackers": 10},
        )
        self.assertEqual(
            {record["proof_mode"] for record in catalog["pdfs"]},
            {"text_layer"},
        )
        self.assertNotIn(
            "darakwon", {record["publisher"] for record in catalog["pdfs"]}
        )

    def test_catalog_rejects_ocr_and_darakwon_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "catalog.json"
            for rejected in (
                {"proof_mode": "rapidocr_cells"},
                {"publisher": "darakwon"},
            ):
                with self.subTest(rejected=rejected):
                    _write_catalog(
                        path,
                        [
                            {
                                "expected_bytes": 1,
                                "expected_page_count": 1,
                                "pdf_sha256": "a" * 64,
                                "proof_mode": "text_layer",
                                "source_id": "unsupported",
                                **rejected,
                            }
                        ],
                    )
                    with self.assertRaisesRegex(
                        PublicSourceProofError, "catalog PDF 0 is invalid"
                    ):
                        _validated_catalog(path)

    def test_text_layer_receipt_rejects_an_empty_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.pdf"
            _write_pdf(path, 1)
            match = MatchedPdf(
                {
                    "document_role": "wordbook",
                    "expected_page_count": 1,
                    "proof_mode": "text_layer",
                    "publisher": "hackers",
                    "source_id": "empty",
                },
                path,
            )
            with self.assertRaisesRegex(PublicSourceProofError, "text layer is empty"):
                _text_layer_receipt([match])

    def test_source_proof_records_text_observation_without_ocr_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "renamed.pdf"
            byte_count, digest = _write_text_pdf(pdf)
            catalog = root / "catalog.json"
            _write_catalog(
                catalog,
                [
                    {
                        "expected_bytes": byte_count,
                        "expected_page_count": 1,
                        "pdf_sha256": digest,
                        "proof_mode": "text_layer",
                        "source_id": "hackers-fixture",
                    }
                ],
            )
            output = root / "proof.json"

            proof = build_source_proof(
                pdf_root=root,
                catalog_path=catalog,
                output_path=output,
            )

        payload = {key: value for key, value in proof.items() if key != "payload_hash"}
        self.assertEqual(proof["payload_hash"], sha256_json(payload))
        self.assertNotIn("rapidocr", proof)
        self.assertNotIn("ocr_models", proof)
        self.assertNotIn("ocr_config_sha256", proof)
        self.assertEqual(proof["text_layers"]["document_count"], 1)
        self.assertEqual(proof["text_layers"]["publisher_counts"], {"hackers": 1})
        document = proof["text_layers"]["documents"][0]
        self.assertEqual(document["source_id"], "hackers-fixture")
        self.assertEqual(document["document_role"], "wordbook")
        self.assertEqual(document["publisher"], "hackers")
        self.assertEqual(document["nonempty_page_count"], 1)
        self.assertGreater(document["character_count"], 0)
        self.assertRegex(document["text_observation_sha256"], r"^[0-9a-f]{64}$")
