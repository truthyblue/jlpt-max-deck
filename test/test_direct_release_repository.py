from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from direct_release_contract import (  # noqa: E402
    KANJI_BUILDER_FILES,
    kanji_builder_archive_path,
    release_filenames,
    sha256_file,
    sha256_json,
)
from public_release import _package_kanji_builder, _zip_write  # noqa: E402


def load_repository_verifier() -> Any:
    path = ROOT / "scripts" / "verify-direct-release-tree.py"
    spec = importlib.util.spec_from_file_location(
        "verify_direct_release_tree",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    def test_packaged_builder_exposes_only_beginner_entries_at_top_level(
        self,
    ) -> None:
        names = release_filenames("1.0.1")
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            skeleton = tmp / names["kanji_skeleton"]
            manifest = tmp / names["skeleton_manifest"]
            output = tmp / names["kanji_builder"]
            skeleton.write_bytes(b"internal builder asset")
            manifest.write_text("{}\n", encoding="utf-8")

            _package_kanji_builder(
                output=output,
                skeleton_apkg=skeleton,
                skeleton_manifest=manifest,
            )

            archive_root = "JLPT-MAX-kanji-builder"
            with zipfile.ZipFile(output) as archive:
                members = set(archive.namelist())
                windows_entry = archive.getinfo(
                    f"{archive_root}/Windows에서 한자 확장 만들기.cmd"
                )
                windows_launcher = archive.read(
                    f"{archive_root}/Windows에서 한자 확장 만들기.cmd"
                )
                mac_entry = archive.getinfo(
                    f"{archive_root}/Mac에서 한자 확장 만들기.command"
                )
                windows_helper = archive.read(
                    f"{archive_root}/scripts/start-kanji-addon.ps1"
                )

        self.assertIn(
            f"{archive_root}/assets/{names['kanji_skeleton']}",
            members,
        )
        self.assertNotIn(
            f"{archive_root}/assets/"
            "JLPT-MAX-kanji-skeleton-1.0.1.apkg",
            members,
        )
        self.assertIn(f"{archive_root}/assets/README.txt", members)
        self.assertEqual((windows_entry.external_attr >> 16) & 0o777, 0o644)
        self.assertEqual((mac_entry.external_attr >> 16) & 0o777, 0o755)
        self.assertTrue(windows_launcher.startswith(b"@echo off\r\n"))
        self.assertNotIn(b"\n", windows_launcher.replace(b"\r\n", b""))
        windows_launcher.decode("ascii")
        self.assertTrue(windows_helper.startswith(b"\xef\xbb\xbf#requires"))

    def test_release_pin_is_self_bound(self) -> None:
        pin = json.loads(
            (ROOT / "config" / "public-release.json").read_text(encoding="utf-8")
        )
        payload = {key: value for key, value in pin.items() if key != "payload_hash"}
        self.assertEqual(pin["payload_hash"], sha256_json(payload))

    def test_release_pin_matches_current_logical_counts(self) -> None:
        pin = json.loads(
            (ROOT / "config" / "public-release.json").read_text(encoding="utf-8")
        )
        verifier = load_repository_verifier()

        verifier._verify_pin(pin)
        self.assertEqual(pin["core"]["media_files"], 18_253)

    def test_runtime_is_only_the_optional_kanji_builder(self) -> None:
        self.assertEqual(
            KANJI_BUILDER_FILES,
            (
                "LICENSE",
                "NOTICE",
                "docs/kanji-builder-assets.txt",
                "docs/kanji-builder.md",
                "pyproject.toml",
                "scripts/build-kanji-addon.ps1",
                "scripts/build-kanji-addon.sh",
                "scripts/start-kanji-addon.cmd",
                "scripts/start-kanji-addon.command",
                "scripts/start-kanji-addon.ps1",
                "scripts/start-kanji-addon.sh",
                "src/build_kanji_addon.py",
                "src/direct_release_contract.py",
                "src/public_kanji.py",
                "uv.lock",
            ),
        )
        self.assertFalse((ROOT / "config" / "public-runtime-files.txt").exists())
        self.assertFalse((ROOT / "src" / "artifact_hashing.py").exists())

    def test_beginner_launchers_avoid_manual_terminal_setup(self) -> None:
        windows_entry_bytes = (
            ROOT / "scripts" / "start-kanji-addon.cmd"
        ).read_bytes()
        self.assertTrue(windows_entry_bytes.startswith(b"@echo off\r\n"))
        self.assertNotIn(b"\n", windows_entry_bytes.replace(b"\r\n", b""))
        windows_entry = windows_entry_bytes.decode("ascii")
        windows_flow = (ROOT / "scripts" / "start-kanji-addon.ps1").read_text(
            encoding="utf-8"
        )
        mac_entry = (
            ROOT / "scripts" / "start-kanji-addon.command"
        ).read_text(encoding="utf-8")
        mac_flow = (ROOT / "scripts" / "start-kanji-addon.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("start-kanji-addon.ps1", windows_entry)
        self.assertIn("OpenFileDialog", windows_flow)
        self.assertIn("UV_UNMANAGED_INSTALL", windows_flow)
        self.assertIn("Start-Process", windows_flow)
        self.assertIn("start-kanji-addon.sh", mac_entry)
        self.assertIn("choose file with prompt", mac_flow)
        self.assertIn("UV_UNMANAGED_INSTALL", mac_flow)
        self.assertIn('open "$OUTPUT_ROOT"', mac_flow)
        for source in (windows_flow, mac_flow):
            with self.subTest(source=source[:20]):
                self.assertIn("0.11.32", source)
                self.assertIn("build/kanji-addon", source)
                self.assertIn("kanji-addon-build-report.json", source)
                self.assertNotIn(
                    "JLPT-MAX-kanji-addon-1.0.1.apkg",
                    source,
                )
        self.assertIn("ConvertFrom-Json", windows_flow)
        self.assertIn('report.get("apkg")', mac_flow)

    def test_builder_assets_warn_against_direct_install(self) -> None:
        warning = (
            ROOT / "docs" / "kanji-builder-assets.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("직접 설치하는 파일이 아닙니다", warning)
        self.assertIn("더블클릭 실행 파일", warning)

    def test_local_builder_runtime_files_cannot_enter_public_source(self) -> None:
        ignored = set(
            (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        )
        verifier = load_repository_verifier()

        self.assertIn("/.tools/", ignored)
        self.assertIn("/kanji-builder.log", ignored)
        for relative in (
            ".tools/uv/uv",
            "kanji-builder.log",
            "nested/kanji-builder.log",
        ):
            with self.subTest(relative=relative):
                with self.assertRaises(RuntimeError):
                    verifier._verify_tracked_boundary((relative,))

    def test_release_pin_binds_current_kanji_builder_sources(self) -> None:
        pin = json.loads(
            (ROOT / "config" / "public-release.json").read_text(encoding="utf-8")
        )
        source_hashes = {
            kanji_builder_archive_path(relative): sha256_file(ROOT / relative)
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
        release = json.loads(
            (ROOT / "config" / "public-release.json").read_text(
                encoding="utf-8"
            )
        )
        names = release_filenames(release["product_version"])
        self.assertIn(
            '<img src="site/assets/brand-lockup.svg" '
            'alt="JLPT MAX Deck" width="560">',
            readme,
        )
        self.assertTrue((ROOT / "site" / "assets" / "brand-lockup.svg").is_file())
        self.assertIn(names["core_apkg"], readme)
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
        self.assertIn("더블클릭", builder_guide)
        self.assertIn("1권 공식 자료", builder_guide)
        self.assertIn("2권 공식 자료", builder_guide)
        self.assertIn("한글이나 띄어쓰기", builder_guide)
        self.assertIn("kanji-builder.log", builder_guide)
        self.assertNotIn("Python 3.13", builder_guide)
        self.assertNotIn("./scripts/build-kanji-addon.sh", builder_guide)
        self.assertIn("기본 덱 다운로드·가져오기", issue_template)
        self.assertIn("한자 확장 ZIP 풀기 또는 실행 파일", issue_template)
        for stale in ("코어 덱", "코어 APKG", "코어 배포"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, builder_guide)
                self.assertNotIn(stale, issue_template)


if __name__ == "__main__":
    unittest.main()
