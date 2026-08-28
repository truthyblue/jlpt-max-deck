# pyright: reportMissingImports=false
from __future__ import annotations

import hashlib
import importlib.util
import json
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


TEST_LIFECYCLE = {
    "test_contracts": {
        "DocumentationRenderTest.test_current_kanji_counts_are_semantically_separate": {
            "protected_contract": (
                "current public copy distinguishes 2,337 source characters from the 4,674 reading and writing addon notes and cards in the v1.3.0 physical release"
            ),
            "not_subsumed_by": (
                "package count tests can pass while learner documentation labels character count as note or card count"
            ),
        },
        "DocumentationRenderTest.test_v130_copy_separates_new_writing_cards_from_manual_reading_move": {
            "protected_contract": (
                "every v1.3.0 publication copy says writing cards are added while existing reading cards remain in the old everyday deck until the learner moves them"
            ),
            "not_subsumed_by": (
                "general update-guide checks can pass while the release announcement incorrectly implies that the old reading deck moves automatically"
            ),
        },
        "DocumentationRenderTest.test_v130_copy_names_ios_default_change_and_example_edge_fix": {
            "protected_contract": (
                "v1.3.0 publication copy identifies the changed iPhone and iPad default, distinguishes the repaired example edge case from the v1.2.1 feature, and keeps package instructions in the update steps"
            ),
            "not_subsumed_by": (
                "screenshot and asset-reference tests can pass while the surrounding learner explanation describes the wrong release history or repeats a confusing package section"
            ),
        },
        "DocumentationRenderTest.test_v130_gallery_puts_required_learner_actions_first": {
            "protected_contract": (
                "the v1.3.0 gallery announcement puts every required existing-user action in one ordered section and keeps internal release evidence out of learner-facing copy"
            ),
            "not_subsumed_by": (
                "individual wording checks can pass while the learner must hunt through feature sections for the kana cleanup, kanji deck move, and final sync steps"
            ),
        },
        "DocumentationRenderTest.test_historical_v12_release_outputs_are_byte_identical": {
            "protected_contract": (
                "rendering current documentation data cannot rewrite the published v1.2.0 or v1.2.1 release evidence"
            ),
            "not_subsumed_by": (
                "spot checks for old filenames and counts do not detect unrelated byte changes or a current release hash leaking into historical notes"
            ),
        },
        "DocumentationRenderTest.test_historical_v13_release_output_is_byte_identical": {
            "protected_contract": (
                "rendering a later release cannot rewrite the published v1.3.0 filenames, counts, or artifact hashes"
            ),
            "not_subsumed_by": (
                "current-release documentation tests can pass while global template data silently leaks into the historical v1.3.0 release note"
            ),
        },
        "DocumentationRenderTest.test_historical_v200_release_output_is_byte_identical": {
            "protected_contract": (
                "rendering a hotfix cannot rewrite the published v2.0.0 filenames, sizes, or artifact hashes"
            ),
            "not_subsumed_by": (
                "current-release documentation tests can pass while global artifact data silently leaks into the historical v2.0.0 release note"
            ),
        },
    }
}


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
        PurePosixPath("docs/releases/v1.0.3.md.j2"): PurePosixPath(
            "docs/releases/v1.0.3.md"
        ),
        PurePosixPath("docs/releases/v1.1.0.md.j2"): PurePosixPath(
            "docs/releases/v1.1.0.md"
        ),
        PurePosixPath("docs/releases/v1.1.1.md.j2"): PurePosixPath(
            "docs/releases/v1.1.1.md"
        ),
        PurePosixPath("docs/releases/v1.2.0.md.j2"): PurePosixPath(
            "docs/releases/v1.2.0.md"
        ),
        PurePosixPath("docs/releases/v1.2.1.md.j2"): PurePosixPath(
            "docs/releases/v1.2.1.md"
        ),
        PurePosixPath("docs/releases/v1.3.0.md.j2"): PurePosixPath(
            "docs/releases/v1.3.0.md"
        ),
        PurePosixPath("docs/releases/v2.0.0.md.j2"): PurePosixPath(
            "docs/releases/v2.0.0.md"
        ),
        PurePosixPath("docs/releases/v2.0.1.md.j2"): PurePosixPath(
            "docs/releases/v2.0.1.md"
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
        PurePosixPath("site/study-guide.html.j2"): PurePosixPath(
            "site/study-guide.html"
        ),
        PurePosixPath("site/update.html.j2"): PurePosixPath(
            "site/update.html"
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

    def test_release_notes_use_publication_safe_absolute_links(self) -> None:
        link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
        for path in sorted((ROOT / "docs" / "releases").glob("v*.md")):
            content = path.read_text(encoding="utf-8")
            for target in link_pattern.findall(content):
                parsed = urlsplit(target)
                with self.subTest(source=path.name, target=target):
                    self.assertIn(parsed.scheme, {"http", "https"})
                    self.assertTrue(parsed.netloc)

    def test_historical_v103_release_evidence_is_immutable(self) -> None:
        content = (ROOT / "docs" / "releases" / "v1.0.3.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("JLPT-MAX-Deck-1.0.3.apkg", content)
        self.assertIn(
            "08846d902f2bec4bb7afad5e7526273864bb6ef5e9a15379e00e253004e7f7ea",
            content,
        )
        self.assertIn("| 기본 덱 | 13,903 | 20,065 | 18,051 |", content)
        self.assertIn("| 두 APKG 합산 | 16,240 | 22,402 | 18,065 |", content)
        self.assertNotIn("18,153", content)
        self.assertNotIn("JLPT-MAX-Deck-1.1.0.apkg", content)

    def test_historical_v11x_release_evidence_is_immutable(self) -> None:
        v110 = (ROOT / "docs" / "releases" / "v1.1.0.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("JLPT-MAX-Deck-1.1.0.apkg", v110)
        self.assertIn(
            "1a6f17b0141fc53766f01ccfd7a712ec766d3e5b81c94625de3d1fb960e31911",
            v110,
        )
        self.assertNotIn("JLPT-MAX-Deck-1.1.1.apkg", v110)

        v111 = (ROOT / "docs" / "releases" / "v1.1.1.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("JLPT-MAX-Deck-1.1.1.apkg", v111)
        self.assertIn(
            "0c6abfc969792e9129d67ccef30c2ca78d114a4cf7e06b187e0e4d05f8b5198f",
            v111,
        )
        self.assertIn("| 기본 덱 | 13,903 | 20,065 | 18,253 |", v111)
        self.assertNotIn("JLPT-MAX-Deck-1.2.0.apkg", v111)

        v120 = (ROOT / "docs" / "releases" / "v1.2.0.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("JLPT-MAX-Deck-1.2.0.apkg", v120)
        self.assertIn(
            "18694172b1e4a45bebda096069ef7102221abeb2aeabec185c5de051d4ec1dcc",
            v120,
        )
        self.assertNotIn("JLPT-MAX-Deck-1.2.1.apkg", v120)

    def test_historical_v12_release_outputs_are_byte_identical(self) -> None:
        environment = RENDER.create_environment(ROOT)
        context = RENDER.load_context(ROOT)
        expected = {
            "docs/releases/v1.2.0.md.j2": (
                ROOT / "docs/releases/v1.2.0.md",
                "410ab3d987059bdd97422b474b91b76ea6e3d04b46e54b08820f524978d53e92",
            ),
            "docs/releases/v1.2.1.md.j2": (
                ROOT / "docs/releases/v1.2.1.md",
                "5b3070e28ba23f10d9e34f9221637da4c7c5affbb7c8eb70423456151de54f36",
            ),
        }
        for template, (output, expected_sha256) in expected.items():
            rendered = RENDER.normalize_final_newline(
                environment.get_template(template).render(**context)
            )
            with self.subTest(template=template):
                self.assertEqual(rendered, output.read_text(encoding="utf-8"))
                self.assertEqual(
                    hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
                    expected_sha256,
                )

    def test_historical_v13_release_output_is_byte_identical(self) -> None:
        environment = RENDER.create_environment(ROOT)
        context = RENDER.load_context(ROOT)
        rendered = RENDER.normalize_final_newline(
            environment.get_template("docs/releases/v1.3.0.md.j2").render(
                **context
            )
        )
        output = ROOT / "docs/releases/v1.3.0.md"
        self.assertEqual(rendered, output.read_text(encoding="utf-8"))
        self.assertEqual(
            hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            "432947c1e9239db3b9024d564a2bab6429c7f73ec1c7cb2e3bd97159cc265809",
        )

    def test_historical_v200_release_output_is_byte_identical(self) -> None:
        environment = RENDER.create_environment(ROOT)
        context = RENDER.load_context(ROOT)
        rendered = RENDER.normalize_final_newline(
            environment.get_template("docs/releases/v2.0.0.md.j2").render(
                **context
            )
        )
        output = ROOT / "docs/releases/v2.0.0.md"
        self.assertEqual(rendered, output.read_text(encoding="utf-8"))
        self.assertEqual(
            hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            "825880a67f7ae1a8f15502ba5165e5efed7ae0b93eb1002488562216266429dc",
        )

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
            "product.deck.kanji_characters",
            "product.deck.kanji_addon_notes",
            "product.deck.kanji_addon_cards",
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

    def test_current_kanji_counts_are_semantically_separate(self) -> None:
        product = json.loads(
            (ROOT / "docs-src/data/product.json").read_text(encoding="utf-8")
        )
        deck = product["deck"]
        self.assertNotIn("kanji_notes", deck)
        self.assertEqual(deck["kanji_characters"], 2_337)
        self.assertEqual(deck["kanji_addon_notes"], 4_674)
        self.assertEqual(deck["kanji_addon_cards"], 4_674)
        self.assertEqual(
            deck["total_notes"],
            deck["core_notes"] + deck["kanji_addon_notes"],
        )
        self.assertEqual(
            deck["total_cards"],
            deck["core_cards"] + deck["kanji_addon_cards"],
        )
        self.assertEqual(
            deck["total_media"],
            deck["core_media"] + deck["static_media"],
        )

        current_templates = (
            "README.md.j2",
            "docs/anki.md.j2",
            "docs/build.md.j2",
            "site/index.html.j2",
            "site/kanji.html.j2",
            "site/study-guide.html.j2",
            "site/update.html.j2",
        )
        current_sources = "\n".join(
            (ROOT / "docs-src" / template).read_text(encoding="utf-8")
            for template in current_templates
        )
        self.assertNotIn("product.deck.kanji_notes", current_sources)
        for reference in (
            "product.deck.kanji_characters",
            "product.deck.kanji_addon_notes",
            "product.deck.kanji_addon_cards",
        ):
            with self.subTest(reference=reference):
                self.assertIn(reference, current_sources)

    def test_v130_copy_separates_new_writing_cards_from_manual_reading_move(
        self,
    ) -> None:
        paths = (
            ROOT / "docs-src/docs/releases/v1.3.0.md.j2",
            ROOT / "docs/jlpt-gallery-updates/v1.3.0.html",
            ROOT / "docs/release-details/v1.3.0.md",
            ROOT / "docs/release-drafts/v1.3.0-github-release.md",
        )
        for path in paths:
            copy = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertIn("새 쓰기 카드 2,337장이 추가", copy)
                self.assertIn("일상무따::상권·하권", copy)
                self.assertIn("한자::읽기::상권·하권", copy)
                self.assertIn("직접 옮", copy)
                self.assertNotIn("새 카드가 자동으로 생김", copy)

    def test_v130_copy_names_ios_default_change_and_example_edge_fix(
        self,
    ) -> None:
        paths = (
            ROOT / "docs-src/docs/releases/v1.3.0.md.j2",
            ROOT / "docs/jlpt-gallery-updates/v1.3.0.html",
            ROOT / "docs/release-details/v1.3.0.md",
            ROOT / "docs/release-drafts/v1.3.0-github-release.md",
        )
        for path in paths:
            copy = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertIn("무음 모드 재생을 기본값으로 변경", copy)
                self.assertIn("v1.3.0부터", copy)
                self.assertIn("다른 앱 음악과 함께 재생", copy)
                self.assertIn("예문을 뜻 묶음별 흰 영역으로 나누는 기능은 v1.2.1", copy)
                self.assertIn("뜻 묶음이 하나뿐", copy)
                self.assertNotIn("고저 악센트와 예문 묶음 화면 개선", copy)

        gallery = paths[1].read_text(encoding="utf-8")
        self.assertIn("한자 APKG도 다시 만들어 가져와야 함", gallery)
        self.assertNotIn("기본 덱과 한자 확장을 따로 배포", gallery)

    def test_v130_gallery_puts_required_learner_actions_first(self) -> None:
        gallery = (
            ROOT / "docs/jlpt-gallery-updates/v1.3.0.html"
        ).read_text(encoding="utf-8")

        action_heading = gallery.index("기존 사용자 필수 작업")
        feature_heading = gallery.index("한자 쓰기 카드 2,337장 추가", action_heading)
        self.assertLess(action_heading, feature_heading)

        for required_copy in (
            "업데이트할 때 이 4단계를 직접 해주세요",
            "기존 노트 업데이트: 항상",
            "JLPT MAX덱::일상무따::상권",
            "카드 → 덱 변경",
            "JLPT MAX덱::한자::읽기::상권",
            "JLPT MAX덱 어휘 / 어휘(가나 보조)",
            "빈 카드 도구의 삭제",
            "카드 탐색기의 ‘노트 삭제’는 누르면 안 됨",
            "모든 기기에서 전체 동기화하기",
        ):
            with self.subTest(required_copy=required_copy):
                self.assertIn(required_copy, gallery[action_heading:feature_heading])

        for required_link in (
            "업데이트 방법 자세히 보기",
            "v1.3.0 다운로드 · GitHub Release",
            "v1.3.0 상세 변경 내역 보기",
        ):
            with self.subTest(required_link=required_link):
                self.assertIn(required_link, gallery)

        for internal_copy in (
            "실제로 업데이트해 보니",
            "물리적으로 남",
            "byte 단위",
            "TTS 합성",
            "실제 배포 후보 검증",
            "빈 profile",
            "해시로 묶",
        ):
            with self.subTest(internal_copy=internal_copy):
                self.assertNotIn(internal_copy, gallery)

    def test_current_entry_guides_do_not_repeat_retired_update_or_filter_flows(
        self,
    ) -> None:
        readme = (ROOT / "docs-src/README.md.j2").read_text(encoding="utf-8")
        anki_guide = (ROOT / "docs-src/docs/anki.md.j2").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("## 1.0.0에서 업데이트한다면", readme)
        self.assertNotIn("JLPT MAX덱::종합 실전`만 삭제", readme)
        self.assertNotIn("오늘의 어휘 복습", anki_guide)
        self.assertNotIn('deck:"JLPT MAX덱::어휘" is:due', anki_guide)
        self.assertIn("필터 덱은 선택 기능입니다", anki_guide)
        self.assertIn("study-guide.html#filtered", anki_guide)

    def test_update_guides_publish_one_import_policy_for_all_updates(
        self,
    ) -> None:
        current_sources = (
            ROOT / "docs-src/docs/anki.md.j2",
            ROOT / "docs-src/site/update.html.j2",
        )
        for path in current_sources:
            content = path.read_text(encoding="utf-8")
            with self.subTest(source=path.relative_to(ROOT).as_posix()):
                self.assertIn("항상", content)
                self.assertIn("전체 동기화", content)

        anki_guide = current_sources[0].read_text(encoding="utf-8")
        update_page = current_sources[1].read_text(encoding="utf-8")
        self.assertIn("기존 노트 업데이트: 항상", anki_guide)
        self.assertIn("모든 JLPT MAX 덱 업데이트", anki_guide)
        self.assertNotIn("지금 사용하는 버전", anki_guide)
        self.assertNotIn(">새 버전일 때</strong>", update_page)
        self.assertIn("언제나 <code>항상</code>", update_page)
        self.assertNotIn("지금 사용하는 버전", update_page)
        self.assertIn("기존 한자 확장은 {{ release.tag }} 빌더로 다시 만듭니다", update_page)
        self.assertIn("완전히 미학습 상태인 급수", update_page)
        self.assertIn("五万", update_page)
        self.assertIn("～キロ", update_page)
        self.assertIn("기존 한자 읽기 카드는 현재 덱에 그대로 남습니다", update_page)
        self.assertIn("한자::읽기::상권·하권", anki_guide)

        historical_minor_release = (
            ROOT / "docs-src/docs/releases/v1.2.0.md.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("이번 버전은 어느 기존 버전에서 오더라도 **항상**", historical_minor_release)

        historical_patch_release = (
            ROOT / "docs-src/docs/releases/v1.1.1.md.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("1.1.0 → 1.1.1", historical_patch_release)
        self.assertIn("새 버전일 때", historical_patch_release)

        older_minor_release = (
            ROOT / "docs-src/docs/releases/v1.1.0.md.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("1.0.3", older_minor_release)
        self.assertIn("**기존 노트 업데이트**는 반드시", older_minor_release)
        self.assertIn("**항상**", historical_minor_release)
        self.assertNotIn("새 버전일 때", historical_minor_release)
        self.assertIn("직접 편집한 공식 노트 필드", historical_minor_release)


if __name__ == "__main__":
    unittest.main()
