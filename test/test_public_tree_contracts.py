from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_public_tree_contracts", ROOT / "scripts" / "verify-public-tree.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load public tree verifier")
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class PublicTreeContractTest(unittest.TestCase):
    def _copy_configs(self, directory: str) -> Path:
        root = Path(directory)
        target = root / "config"
        target.mkdir()
        for name in ("public-layouts.json", "public-release.json", "public-sources.json"):
            shutil.copyfile(ROOT / "config" / name, target / name)
        return root

    @staticmethod
    def _read(path: Path) -> dict[str, object]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise AssertionError("fixture must contain an object")
        return value

    @staticmethod
    def _write(path: Path, value: dict[str, object]) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_repository_contract_files_are_fully_valid(self) -> None:
        VERIFY.validate_public_contract_files(ROOT)
        pin = VERIFY.validate_release_pin_document(ROOT)
        self.assertEqual(pin["status"], "passed")

    def test_release_pin_rejects_closed_payload_with_failed_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_configs(tmp)
            path = root / "config" / "public-release.json"
            pin = self._read(path)
            pin["status"] = "failed"
            payload = {key: value for key, value in pin.items() if key != "payload_hash"}
            pin["payload_hash"] = VERIFY._sha256_json(payload)
            self._write(path, pin)

            with self.assertRaisesRegex(VERIFY.PublicTreeError, "not passed and closed"):
                VERIFY.validate_release_pin_document(root)

    def test_release_pin_rejects_payload_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_configs(tmp)
            path = root / "config" / "public-release.json"
            pin = self._read(path)
            pin["archive_sha256"] = "0" * 64
            self._write(path, pin)

            with self.assertRaisesRegex(VERIFY.PublicTreeError, "not passed and closed"):
                VERIFY.validate_release_pin_document(root)

    def test_release_pin_rejects_boolean_integer_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_configs(tmp)
            path = root / "config" / "public-release.json"
            pin = self._read(path)
            pin["schema_version"] = True
            pin["unresolved"] = False
            payload = {key: value for key, value in pin.items() if key != "payload_hash"}
            pin["payload_hash"] = VERIFY._sha256_json(payload)
            self._write(path, pin)

            with self.assertRaisesRegex(VERIFY.PublicTreeError, "not passed and closed"):
                VERIFY.validate_release_pin_document(root)

    def test_source_catalog_rejects_record_schema_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_configs(tmp)
            path = root / "config" / "public-sources.json"
            catalog = self._read(path)
            records = catalog["pdfs"]
            if not isinstance(records, list) or not isinstance(records[0], dict):
                raise AssertionError("catalog fixture is invalid")
            records[0]["private_field"] = "must not ship"
            self._write(path, catalog)

            with self.assertRaisesRegex(VERIFY.PublicTreeError, "schema changed"):
                VERIFY.validate_public_source_catalog(root)

    def test_layout_registry_rejects_schema_and_source_binding_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_configs(tmp)
            path = root / "config" / "public-layouts.json"
            registry = self._read(path)
            registry["schema_version"] = 999
            self._write(path, registry)
            catalog = VERIFY.validate_public_source_catalog(root)
            with self.assertRaisesRegex(VERIFY.PublicTreeError, "registry is invalid"):
                VERIFY.validate_public_layout_registry(root, catalog)

            registry = self._read(ROOT / "config" / "public-layouts.json")
            documents = registry["documents"]
            if not isinstance(documents, list) or not isinstance(documents[0], dict):
                raise AssertionError("layout fixture is invalid")
            documents[0]["pdf_sha256"] = "0" * 64
            self._write(path, registry)
            with self.assertRaisesRegex(VERIFY.PublicTreeError, "document is invalid"):
                VERIFY.validate_public_layout_registry(root, catalog)


if __name__ == "__main__":
    unittest.main()
