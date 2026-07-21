from __future__ import annotations

import gzip
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from public_hashing import sha256_file  # noqa: E402
from public_kanji import PublicKanjiError, load_kanjidic2  # noqa: E402


class PublicKanjiContractTest(unittest.TestCase):
    def _snapshot(self, root: Path) -> Path:
        source = ROOT / "test/fixtures/kanjidic2-public-mini.xml"
        target = root / "kanjidic2.xml.gz"
        with source.open("rb") as input_file, gzip.open(target, "wb") as output_file:
            shutil.copyfileobj(input_file, output_file)
        return target

    def test_snapshot_exposes_hash_bound_header_and_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._snapshot(Path(directory))
            snapshot = load_kanjidic2(
                path,
                expected_sha256=sha256_file(path),
            )

        self.assertEqual(snapshot.file_version, "4")
        self.assertEqual(snapshot.database_version, "fixture-1")
        self.assertEqual(snapshot.date_of_creation, "2026-07-20")
        self.assertEqual(set(snapshot.entries), {"些", "休"})
        self.assertEqual(snapshot.entries["些"].korean_readings, ("사",))
        self.assertEqual(snapshot.entries["些"].english_meanings, ("a little bit",))

    def test_snapshot_rejects_a_mismatched_pin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._snapshot(Path(directory))
            with self.assertRaisesRegex(PublicKanjiError, "hash changed"):
                load_kanjidic2(path, expected_sha256="0" * 64)


if __name__ == "__main__":
    unittest.main()
