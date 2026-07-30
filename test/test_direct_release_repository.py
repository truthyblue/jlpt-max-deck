from __future__ import annotations

import json
import io
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from direct_release_contract import (  # noqa: E402
    KANJI_BUILDER_FILES,
    sha256_file,
    sha256_json,
)
from public_release import _zip_write  # noqa: E402


class DirectReleaseRepositoryTest(unittest.TestCase):
    def test_release_zip_preserves_shell_launcher_execute_bit(self) -> None:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            _zip_write(
                archive,
                "JLPT-MAX-kanji-builder/scripts/build-kanji-addon.sh",
                b"#!/usr/bin/env bash\n",
                mode=0o755,
            )
        with zipfile.ZipFile(payload) as archive:
            info = archive.getinfo(
                "JLPT-MAX-kanji-builder/scripts/build-kanji-addon.sh"
            )
        self.assertEqual((info.external_attr >> 16) & 0o777, 0o755)

    def test_release_pin_is_self_bound(self) -> None:
        pin = json.loads(
            (ROOT / "config" / "public-release.json").read_text(encoding="utf-8")
        )
        payload = {key: value for key, value in pin.items() if key != "payload_hash"}
        self.assertEqual(pin["payload_hash"], sha256_json(payload))

    def test_runtime_is_only_the_optional_kanji_builder(self) -> None:
        self.assertEqual(
            KANJI_BUILDER_FILES,
            (
                "LICENSE",
                "NOTICE",
                "docs/kanji-builder.md",
                "pyproject.toml",
                "scripts/build-kanji-addon.ps1",
                "scripts/build-kanji-addon.sh",
                "src/build_kanji_addon.py",
                "src/direct_release_contract.py",
                "src/public_kanji.py",
                "uv.lock",
            ),
        )
        self.assertFalse((ROOT / "config" / "public-runtime-files.txt").exists())
        self.assertFalse((ROOT / "src" / "artifact_hashing.py").exists())

    def test_release_pin_binds_current_kanji_builder_sources(self) -> None:
        pin = json.loads(
            (ROOT / "config" / "public-release.json").read_text(encoding="utf-8")
        )
        source_hashes = {
            (
                "README.md"
                if relative == "docs/kanji-builder.md"
                else relative
            ): sha256_file(ROOT / relative)
            for relative in KANJI_BUILDER_FILES
        }
        self.assertEqual(
            pin["kanji_builder"]["source_hash"],
            sha256_json(dict(sorted(source_hashes.items()))),
        )

    def test_repository_has_no_companion_autoplay_addon(self) -> None:
        self.assertFalse((ROOT / "src" / "autoplay_addon.py").exists())
        self.assertFalse((ROOT / "addons" / "jlpt_max_deck_autoplay").exists())
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertNotIn("companion autoplay add-on", notice)
        for relative in (
            "docs-src/README.md.j2",
            "docs-src/site/getting-started.html.j2",
        ):
            content = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn(".ankiaddon", content)

    def test_kanji_builder_removes_anki_work_files(self) -> None:
        source = (ROOT / "src" / "build_kanji_addon.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('(staged / "build.media.db2").unlink', source)
        self.assertNotIn('staged / "collection.media"', source)

    def test_readme_leads_with_direct_basic_deck_download(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("JLPT-MAX-Deck-1.0.0.apkg", readme)
        self.assertNotIn("JLPT-MAX-core", readme)
        self.assertIn(
            "기본 덱은 완성된 APKG 파일입니다",
            readme,
        )
        self.assertIn("웹 시작 가이드", readme)
        self.assertNotIn("코어 APKG", readme)
        self.assertNotIn("Python이나 출판사 PDF는 필요하지 않습니다", readme)
        self.assertNotIn("저장소를 복제하거나 빌드할 필요가 없습니다", readme)

    def test_learner_support_files_use_current_product_names(self) -> None:
        builder_guide = (ROOT / "docs" / "kanji-builder.md").read_text(
            encoding="utf-8"
        )
        issue_template = (
            ROOT / ".github" / "ISSUE_TEMPLATE" / "bug.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("# 일상무따 한자 확장 만들기", builder_guide)
        self.assertIn("기본 덱 다운로드·가져오기", issue_template)
        for stale in ("코어 덱", "코어 APKG", "코어 배포"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, builder_guide)
                self.assertNotIn(stale, issue_template)


if __name__ == "__main__":
    unittest.main()
