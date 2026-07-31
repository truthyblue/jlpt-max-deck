# pyright: reportMissingImports=false
from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from jinja2 import StrictUndefined, UndefinedError


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "render_docs", ROOT / "scripts" / "render-docs.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load documentation renderer")
RENDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDER)


class DocumentationRenderTest(unittest.TestCase):
    EXPECTED_MAPPING = {
        PurePosixPath("README.md.j2"): PurePosixPath("README.md"),
        PurePosixPath("docs/anki.md.j2"): PurePosixPath("docs/anki.md"),
        PurePosixPath("docs/build.md.j2"): PurePosixPath("docs/build.md"),
        PurePosixPath("docs/privacy-and-licensing.md.j2"): PurePosixPath(
            "docs/privacy-and-licensing.md"
        ),
        PurePosixPath("docs/releases/v1.0.1.md.j2"): PurePosixPath(
            "docs/releases/v1.0.1.md"
        ),
        PurePosixPath("docs/releases/v1.0.2.md.j2"): PurePosixPath(
            "docs/releases/v1.0.2.md"
        ),
        PurePosixPath("docs/troubleshooting.md.j2"): PurePosixPath(
            "docs/troubleshooting.md"
        ),
        PurePosixPath("site/404.html.j2"): PurePosixPath("site/404.html"),
        PurePosixPath("site/getting-started.html.j2"): PurePosixPath(
            "site/getting-started.html"
        ),
        PurePosixPath("site/index.html.j2"): PurePosixPath("site/index.html"),
        PurePosixPath("site/install-anki.html.j2"): PurePosixPath(
            "site/install-anki.html"
        ),
        PurePosixPath("site/kanji.html.j2"): PurePosixPath("site/kanji.html"),
        PurePosixPath("site/latest-release.json.j2"): PurePosixPath(
            "site/latest-release.json"
        ),
        PurePosixPath("site/support.html.j2"): PurePosixPath(
            "site/support.html"
        ),
    }

    def test_mapping_is_explicit_complete_and_unique(self) -> None:
        mapping = dict(RENDER.TEMPLATE_OUTPUTS)
        self.assertEqual(mapping, self.EXPECTED_MAPPING)
        self.assertEqual(len(mapping.values()), len(set(mapping.values())))

    def test_environment_is_strict_and_release_data_matches_pin(self) -> None:
        environment = RENDER.create_environment(ROOT)
        self.assertIs(environment.undefined, StrictUndefined)
        with self.assertRaises(UndefinedError):
            environment.from_string("{{ missing_value }}").render()

        context = RENDER.load_context(ROOT)
        release_history = context["release_history"]
        self.assertEqual(
            release_history[0]["version"],
            context["release"]["version"],
        )
        self.assertTrue(release_history[0]["current"])
        self.assertEqual(release_history[0]["label"], "최신")
        self.assertIsNone(release_history[1]["label"])
        self.assertEqual(
            1,
            sum(bool(item["current"]) for item in release_history),
        )
        asset_versions = context["asset_versions"]
        self.assertEqual(
            asset_versions["showcase_css"],
            RENDER._sha256_file(ROOT / "site" / "assets" / "showcase.css")[:12],
        )
        self.assertEqual(
            asset_versions["site_css"],
            RENDER._sha256_file(ROOT / "site" / "assets" / "site.css")[:12],
        )
        release_artifacts = context["release"]["artifacts"]
        pin_artifacts = context["release_pin"]["artifacts"]
        for record in release_artifacts.values():
            filename = record["filename"]
            self.assertEqual(
                pin_artifacts[filename],
                {"bytes": record["bytes"], "sha256": record["sha256"]},
            )

    def test_staged_release_history_activates_with_matching_pin(self) -> None:
        release_history = RENDER._load_release_history(
            ROOT,
            current_version="1.0.2",
        )

        self.assertEqual(release_history[0]["version"], "1.0.2")
        self.assertTrue(release_history[0]["current"])
        self.assertEqual(release_history[0]["label"], "최신")
        self.assertEqual(release_history[1]["version"], "1.0.1")
        self.assertFalse(release_history[1]["current"])
        self.assertIsNone(release_history[1]["label"])

    def test_tracked_outputs_match_rendered_sources(self) -> None:
        rendered = dict(RENDER.render_documents(ROOT))
        self.assertEqual(set(rendered), set(self.EXPECTED_MAPPING.values()))
        self.assertEqual(RENDER.check_documents(ROOT), ())
        for relative, content in rendered.items():
            with self.subTest(output=relative.as_posix()):
                self.assertEqual(
                    (ROOT / relative).read_text(encoding="utf-8"),
                    content,
                )
                self.assertTrue(content.endswith("\n"))
                self.assertFalse(content.endswith("\n\n"))

    def test_rendered_markdown_relative_links_resolve(self) -> None:
        link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
        for relative in self.EXPECTED_MAPPING.values():
            if relative.suffix != ".md":
                continue
            content = (ROOT / relative).read_text(encoding="utf-8")
            for target in link_pattern.findall(content):
                parsed = urlsplit(target)
                if parsed.scheme or target.startswith("//") or not parsed.path:
                    continue
                resolved = (ROOT / relative).parent / unquote(parsed.path)
                with self.subTest(source=relative.as_posix(), target=target):
                    self.assertTrue(resolved.is_file(), f"missing link: {resolved}")

    def test_final_newline_normalization_is_deterministic(self) -> None:
        for source in ("value", "value\n", "value\n\n", "value\r\n"):
            with self.subTest(source=repr(source)):
                self.assertEqual(RENDER.normalize_final_newline(source), "value\n")

    def test_public_site_pages_share_layout_and_design_system(self) -> None:
        layout = (ROOT / "docs-src/_layouts/site.html.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn('{% include "_components/nav.html.j2" %}', layout)
        self.assertIn('{% include "_components/footer.html.j2" -%}', layout)
        self.assertIn("assets/site.css", layout)
        self.assertIn("assets/site.js", layout)
        for source in self.EXPECTED_MAPPING:
            if source.parts[:1] != ("site",):
                continue
            template = (ROOT / "docs-src" / source).read_text(encoding="utf-8")
            with self.subTest(template=source.as_posix()):
                if source.name.endswith(".json.j2"):
                    self.assertNotIn(
                        '{% extends "_layouts/site.html.j2" %}',
                        template,
                    )
                    continue
                if source == PurePosixPath("site/index.html.j2"):
                    self.assertNotIn(
                        '{% extends "_layouts/site.html.j2" %}',
                        template,
                    )
                    self.assertIn(
                        '{% include "_components/nav.html.j2" %}',
                        template,
                    )
                    self.assertIn("assets/showcase.css", template)
                    self.assertIn("data-audio=", template)
                    self.assertIn("data-carousel", template)
                else:
                    self.assertIn(
                        '{% extends "_layouts/site.html.j2" %}',
                        template,
                    )
                    self.assertNotIn("assets/site.css", template)

    def test_current_release_facts_are_data_driven(self) -> None:
        sources = "\n".join(
            (ROOT / "docs-src" / relative).read_text(encoding="utf-8")
            for relative in self.EXPECTED_MAPPING
        )
        self.assertNotIn("release.artifacts.autoplay_addon", sources)
        self.assertNotIn(".ankiaddon", sources)
        for stale in (
            "코어를 받거나 공부하는 데 출판사 PDF가 필요하지 않습니다",
            "코어 APKG를 PDF 없이 직접 배포합니다",
            "코어 학습에는 출판사 PDF가 필요하지 않습니다",
            "코어 APKG",
            "코어 덱",
            "기본 덱을 설치하는 데 Python",
            "기본 덱만 사용할 때는 한자 빌더",
            "만들지 않아도 나머지 기능",
            "저장소를 복제하거나 빌드할 필요",
            "무료로 내려받",
            "구매 인증 없이",
            "macOS / Linux",
            "build-kanji-addon.ps1",
            "build-kanji-addon.sh",
            "PowerShell을 열고",
            "Python {{ product.requirements.python }}과",
        ):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, sources)
        for reference in (
            "product.deck.vocabulary_notes",
            "product.deck.core_notes",
            "product.deck.core_cards",
            "product.deck.core_media",
            "product.deck.total_notes",
            "release.artifacts.core.sha256",
        ):
            with self.subTest(reference=reference):
                self.assertIn(reference, sources)
        privacy = (
            ROOT / "docs-src/docs/privacy-and-licensing.md.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("덱 카드의 최신 버전 확인", privacy)
        self.assertIn("PDF·카드 내용·학습", privacy)
        self.assertIn("접속 IP와 브라우저", privacy)


if __name__ == "__main__":
    unittest.main()
