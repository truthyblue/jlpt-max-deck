#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PAGES = (
    "index.html",
    "getting-started.html",
    "install-anki.html",
    "kanji.html",
    "support.html",
    "404.html",
)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.references: list[tuple[str, str]] = []
        self.images_without_alt: list[str] = []
        self.unsafe_blank_links: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.append(element_id)
        for name in ("href", "src"):
            value = attributes.get(name)
            if value:
                self.references.append((name, value))
        if tag == "img" and not (attributes.get("alt") or "").strip():
            self.images_without_alt.append(
                attributes.get("src") or "<missing src>"
            )
        if tag == "a" and attributes.get("target") == "_blank":
            rel = set((attributes.get("rel") or "").split())
            if not {"noopener", "noreferrer"}.issubset(rel):
                self.unsafe_blank_links.append(
                    attributes.get("href") or "<missing href>"
                )


def parse_page(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def load_prepare_module():
    path = ROOT / "scripts" / "prepare-pages-site.py"
    spec = importlib.util.spec_from_file_location("prepare_pages_site", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parsers = {name: parse_page(SITE / name) for name in PAGES}

    def test_all_public_pages_use_canonical_design_assets(self) -> None:
        for name in PAGES:
            html = (SITE / name).read_text(encoding="utf-8")
            with self.subTest(page=name):
                self.assertIn('class="site-header"', html)
                self.assertIn(
                    'class="nav-group nav-primary-links"',
                    html,
                )
                self.assertNotIn('class="nav-group nav-section-links"', html)
                self.assertNotIn('class="nav-group nav-guide-links"', html)
                self.assertIn('aria-label="지원"', html)
                self.assertIn(
                    '<span class="nav-label-full">지원</span>',
                    html,
                )
                self.assertIn('aria-label="한자 확장"', html)
                self.assertIn(
                    '<span class="nav-label-full">한자 확장</span>',
                    html,
                )
                self.assertIn(
                    '<span class="nav-label-compact">한자</span>',
                    html,
                )
                if name == "support.html":
                    self.assertIn(
                        'href="support.html" aria-current="page" '
                        'aria-label="지원"',
                        html,
                    )
                if name == "kanji.html":
                    self.assertIn(
                        'href="kanji.html" aria-current="page" '
                        'aria-label="한자 확장"',
                        html,
                    )
                self.assertIn('id="repo-link"', html)
                self.assertIn(
                    '<span class="nav-action-label">GitHub에서 Star</span>',
                    html,
                )
                self.assertNotIn('class="v2-header"', html)
                if name == "index.html":
                    self.assertIn("assets/showcase.css", html)
                    self.assertNotIn("assets/site.css", html)
                    self.assertNotIn("assets/site.js", html)
                else:
                    self.assertIn("assets/site.css", html)
                    self.assertIn("assets/site.js", html)

    def test_home_and_guide_navigation_use_the_same_typography(self) -> None:
        nav_font_values: list[str] = []
        for asset in ("site.css", "showcase.css"):
            css = (SITE / "assets" / asset).read_text(encoding="utf-8")
            font = re.search(r"--font-sans:\s*([^;]+);", css)
            if font is None:
                self.fail(f"{asset} has no shared navigation font")
            nav_font_values.append(font.group(1))
            header = re.search(r"\.site-header\s*\{([^}]+)\}", css)
            if header is None:
                self.fail(f"{asset} has no site header styles")
            self.assertIn("font-family: var(--font-sans);", header.group(1))
            self.assertIn("letter-spacing: normal;", header.group(1))
        self.assertEqual(nav_font_values[0], nav_font_values[1])

    def test_local_references_and_fragments_resolve(self) -> None:
        for page_name, parser in self.parsers.items():
            self.assertEqual(len(parser.ids), len(set(parser.ids)), page_name)
            for attribute, reference in parser.references:
                parsed = urlsplit(reference)
                if parsed.scheme or reference.startswith("//"):
                    continue
                if parsed.path:
                    target = SITE / parsed.path
                else:
                    target = SITE / page_name
                with self.subTest(page=page_name, attribute=attribute, ref=reference):
                    self.assertTrue(target.is_file(), f"missing local target: {target}")
                    if parsed.fragment and target.suffix == ".html":
                        self.assertIn(parsed.fragment, parse_page(target).ids)

    def test_accessibility_basics_are_present(self) -> None:
        for page_name, parser in self.parsers.items():
            with self.subTest(page=page_name):
                self.assertEqual([], parser.images_without_alt)
                self.assertEqual([], parser.unsafe_blank_links)
        css = (SITE / "assets" / "site.css").read_text(encoding="utf-8")
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("@media (max-width: 680px)", css)
        showcase_css = (SITE / "assets" / "showcase.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(":focus-visible", showcase_css)
        self.assertIn("prefers-reduced-motion", showcase_css)
        self.assertIn("@media (max-width: 560px)", showcase_css)
        self.assertIn(".autoplay-feature-callout", showcase_css)
        self.assertIn(".support-focus-register::after", showcase_css)
        self.assertIn(".quality-summary", showcase_css)
        self.assertIn(".pipeline-step", showcase_css)
        self.assertIn(".meaning-focus", showcase_css)
        self.assertIn(".closing-actions", showcase_css)
        self.assertIn(
            "grid-template-columns: repeat(3, minmax(0, 1fr));",
            showcase_css,
        )
        self.assertNotIn(
            "grid-template-columns: minmax(0, 1fr) minmax(520px, 640px);",
            showcase_css,
        )
        self.assertNotIn(".hero-card-sample::before", showcase_css)

    def test_card_audio_hotspots_match_example_boxes(self) -> None:
        css = (SITE / "assets" / "showcase.css").read_text(encoding="utf-8")
        expected_tops = {
            "example-1-audio-hotspot": "18.445897%",
            "example-2-audio-hotspot": "27.087872%",
            "example-3-audio-hotspot": "35.729847%",
        }
        for selector, expected_top in expected_tops.items():
            rule = re.search(rf"\.{selector}\s*\{{([^}}]+)\}}", css)
            if rule is None:
                self.fail(f"missing hotspot rule: {selector}")
            with self.subTest(selector=selector):
                self.assertIn(f"top: {expected_top};", rule.group(1))

        shared_rule = re.search(r"\.example-audio-hotspot\s*\{([^}]+)\}", css)
        if shared_rule is None:
            self.fail("missing shared example hotspot rule")
        self.assertIn("height: 8.061002%;", shared_rule.group(1))

    def test_home_explains_direct_core_and_optional_kanji(self) -> None:
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn("JLPT-MAX-Deck-1.0.1.apkg", html)
        self.assertNotIn("JLPT-MAX-core", html)
        self.assertIn("JLPT-MAX-kanji-builder-1.0.1.zip", html)
        self.assertIn('id="kanji-builder-download-link"', html)
        self.assertNotIn('id="materials-doc-link"', html)
        self.assertIn('id="kanji-guide-link"', html)
        self.assertIn("한자 확장 만들기", html)
        self.assertIn("명령어 없이 만드는 순서", html)
        self.assertIn("실행 파일 더블클릭", html)
        self.assertIn("13,903", html)
        self.assertIn("20,065", html)
        self.assertIn("17,899", html)
        self.assertNotIn("<strong>1.0.0 사용자:</strong>", html)
        self.assertIn('id="cards"', html)
        self.assertIn('id="kanji"', html)
        self.assertIn('id="practice"', html)
        self.assertIn('id="reference"', html)
        self.assertIn('id="curation"', html)
        self.assertIn('id="start"', html)
        self.assertIn('id="meaning-focus"', html)
        self.assertIn('id="github-star-link"', html)
        self.assertIn("외울 뜻이", html)
        self.assertIn("엄마, 어머니", html)
        self.assertIn("겹치는 표현은 하나로", html)
        self.assertIn("다의어는 뜻별로 분리", html)
        self.assertIn("뜻 1", html)
        self.assertIn("예문 1", html)
        self.assertIn("뜻 2", html)
        self.assertIn("예문 2", html)
        self.assertIn("대표 예문 하나를 생성해 연결했습니다.", html)
        self.assertIn("GPT‑5.6 Sol", html)
        self.assertIn("이중 검토", html)
        self.assertIn("GitHub에서 Star", html)
        self.assertEqual(4, html.count("data-audio="))
        self.assertEqual(6, html.count('class="practice-flip-card"'))
        self.assertEqual(6, html.count('class="practice-slide"'))
        self.assertIn("data-carousel", html)
        self.assertIn("data-carousel-prev", html)
        self.assertIn("data-carousel-next", html)
        self.assertIn("autoplay-feature-callout", html)
        self.assertIn("<strong>자동재생 설정</strong>", html)
        self.assertNotIn("단어·첫 예문·모든 예문 선택</small>", html)
        self.assertIn("음성과 자동재생", html)
        self.assertIn("뜻마다 대표 예문", html)
        self.assertIn("한자 정보를 바로", html)
        self.assertNotIn('class="deck-support-features reveal"', html)
        self.assertNotIn("BEYOND THIS CARD", html)
        self.assertIn("덱 안내와 업데이트", html)
        self.assertIn("가나·부분 한자 표기 105개는 별도 보조 카드로", html)
        self.assertIn("card-hannichi-formation.webp", html)
        self.assertIn("구어(일부 뜻)", html)
        self.assertIn("‘괜찮다’에만", html)
        self.assertIn("기본 덱은 바로 받을 수 있습니다.", html)
        self.assertIn("한국어권 학습자용 Anki 덱입니다.", html)
        self.assertIn("저급수 표기 카드", html)
        self.assertIn("GPT‑5.6 Sol로 작성하고", html)
        self.assertIn("이중 검토했습니다.", html)
        self.assertIn("GPT‑5.6 Sol을 사용했습니다.", html)
        self.assertIn("생성 결과를 그대로 넣지 않고", html)
        self.assertIn('class="quality-summary-facts reveal"', html)
        self.assertIn("1차 검토", html)
        self.assertIn("2차 검토", html)
        self.assertNotIn("생성된 내용을 곧바로 카드에 넣은 건 아닙니다.", html)
        self.assertNotIn("GPT‑5.6 Sol이 작성한 항목", html)
        self.assertIn("한 단어가", html)
        self.assertIn("카드에 들어가기까지.", html)
        self.assertIn("문제가 발견되면 원인을 반영해 다시 작성하거나 교체한 뒤", html)
        self.assertIn("같은 검증을 다시 거칩니다.", html)
        self.assertIn("재작성·교체 후 재검증", html)
        self.assertIn(">검증 완료</i>", html)
        self.assertNotIn("통과한 결과만 반영", html)
        self.assertNotIn("실패 항목 자동 수록 차단", html)
        self.assertIn("표기·읽기·뜻 근거를 준비합니다", html)
        self.assertIn("GPT‑5.6 Sol이 뜻·예문·문제를 작성합니다", html)
        self.assertIn("작성 결과를 별도로 검증합니다", html)
        self.assertIn("검증을 마친 최종본으로 덱을 만듭니다", html)
        self.assertIn("재검증을 마친 결과를 확정한 뒤", html)
        self.assertIn("<span>확정 데이터</span>", html)
        self.assertNotIn("승인", html)
        self.assertNotIn("LLM OFF", html)
        self.assertIn("입력 근거", html)
        self.assertIn("작성 결과 · 出す", html)
        self.assertIn("품질 검증", html)
        self.assertIn("덱 생성", html)
        self.assertNotIn("STRUCTURED INPUT", html)
        self.assertNotIn("DETERMINISTIC RELEASE", html)
        self.assertNotIn("논리 APKG 해시", html)
        self.assertNotIn('href="#curation" aria-label="덱 제작 과정"', html)
        self.assertIn('href="#start" aria-label="받기"', html)
        self.assertEqual(4, html.count('class="pipeline-step reveal"'))
        self.assertLess(html.index('id="meaning-focus"'), html.index('id="cards"'))
        self.assertLess(html.index('id="cards"'), html.index('id="practice"'))
        self.assertLess(html.index('id="practice"'), html.index('id="reference"'))
        self.assertLess(
            html.index('id="reference"'),
            html.index('id="quality-summary-title"'),
        )
        self.assertLess(
            html.index('id="quality-summary-title"'),
            html.index('id="curation"'),
        )
        self.assertLess(html.index('id="curation"'), html.index('id="kanji"'))
        self.assertLess(html.index('id="reference"'), html.index('id="kanji"'))
        self.assertLess(html.index('id="kanji"'), html.index('id="start"'))
        public_core_story = html[: html.index('id="kanji"')]
        self.assertNotIn("PDF", public_core_story)
        self.assertNotIn("출판사", public_core_story)
        self.assertNotIn("길벗", public_core_story)
        self.assertNotIn('id="inside"', html)
        self.assertNotIn('id="how"', html)
        self.assertNotIn('id="materials"', html)
        self.assertNotIn('id="boundary"', html)
        self.assertNotIn("Anki를 한 번도 써 본 적이 없어요.", html)
        self.assertNotIn("여러 기기의 학습 상태를 이어갈 수 있나요?", html)
        self.assertNotIn("생성 결과를 바로 싣지 않고,", html)
        self.assertNotIn("01 · PREPARE", html)
        self.assertNotIn("02 · REVIEW", html)
        self.assertNotIn("학습 내용은 새로,", html)
        self.assertNotIn("검증은 따로.", html)
        self.assertNotIn("N5–N1 어휘 범위", html)
        self.assertNotIn("전체 어휘를 기본 덱 하나에", html)
        self.assertNotIn("다락원·동양북스·해커스", html)
        self.assertIn(
            "저작권 있는 출판사 내용입니다",
            html,
        )
        self.assertIn("공개 기본 덱에 포함해 재배포하지 않기 위해", html)
        self.assertIn("PDF와 생성 APKG는 외부로 전송되지 않습니다.", html)
        self.assertNotIn("예문과 문제는 받을 때 LLM이 즉석에서 만드나요?", html)
        self.assertNotIn("한자 확장 노트</dt>", html)
        self.assertIn("별도 선택 확장", html)
        self.assertIn("optional-addon-row", html)
        self.assertIn("JMdict·KANJIDIC2 EDRDG", html)
        self.assertIn("처음에는", html)
        self.assertIn("필수 단어부터", html)
        self.assertIn("필수 → 표준 → 확장", html)
        self.assertIn("공개 일본어 사전인 JMdict의 우선순위 정보를 참고해", html)
        self.assertIn("자주 쓰이는 단어부터 새 카드가 나오도록", html)
        self.assertNotIn("priority::", html)
        self.assertNotIn("jlpt::", html)
        self.assertIn('class="essential"', html)
        self.assertIn('class="standard"', html)
        self.assertIn('class="extended"', html)
        self.assertIn('<i class="legend-essential"></i>필수</dt><dd>2,006', html)
        self.assertIn('<i class="legend-standard"></i>표준</dt><dd>1,124', html)
        self.assertIn('<i class="legend-extended"></i>확장</dt><dd>2,888', html)
        release_cta = re.search(r'<a [^>]*id="release-cta"[^>]*>.*?</a>', html)
        if release_cta is None:
            self.fail("release CTA is missing")
        self.assertIn('class="button button-primary"', release_cta.group(0))
        self.assertIn("기본 덱 다운로드", release_cta.group(0))
        self.assertIn('class="button-download-icon"', release_cta.group(0))
        self.assertNotIn("↓", release_cta.group(0))
        self.assertEqual(3, html.count('class="button-download-icon"'))
        self.assertRegex(
            html,
            r'<a class="button button-primary" id="release-cta"[^>]*>.*?</a>\s*'
            r'<a class="button button-quiet" id="hero-beginner-guide-link" '
            r'href="getting-started\.html">시작 가이드 보기',
        )
        self.assertIn(
            'class="button button-secondary" id="beginner-guide-link"',
            html,
        )
        self.assertIn(
            "border: 1px solid rgba(47, 89, 59, .18);",
            (SITE / "assets" / "showcase.css").read_text(encoding="utf-8"),
        )
        self.assertNotIn(
            "border: 1px dashed rgba(47, 89, 59, .27);",
            (SITE / "assets" / "showcase.css").read_text(encoding="utf-8"),
        )
        for image in (
            "practice-kanji-reading-answer.webp",
            "practice-orthography-answer.webp",
            "practice-word-formation-answer.webp",
            "practice-context-defined-answer.webp",
            "practice-paraphrase-answer.webp",
            "practice-usage-answer.webp",
        ):
            self.assertIn(f"assets/{image}", html)
        self.assertIn("assets/demo-dasu-word.mp3", html)

    def test_start_guide_contains_complete_import_contract(self) -> None:
        html = (SITE / "getting-started.html").read_text(encoding="utf-8")
        parser = self.parsers["getting-started.html"]
        for section_id in (
            "deck",
            "import",
            "import-options",
            "settings",
            "verify",
            "kanji",
            "sync",
        ):
            self.assertIn(section_id, parser.ids)
        for token in (
            'href="kanji.html"',
            "Android는 AnkiDroid를 설치하세요",
            "최상위 항목 <code>JLPT MAX덱</code>을 확인합니다",
            "켜기 · 권장",
            "동기화는 여러 기기에서 이어볼 때만 합니다",
        ):
            self.assertIn(token, html)
        self.assertNotIn("kanji-command-macos", html)
        self.assertNotIn("kanji-command-windows", html)
        self.assertNotIn("PowerShell", html)
        self.assertNotIn("./scripts/build-kanji-addon.sh", html)
        self.assertNotIn("Python 3.13", html)
        self.assertNotIn("자동재생 애드온", html)
        self.assertNotIn(".ankiaddon", html)
        self.assertNotIn("<code>JLPT MAX덱</code> 덱", html)
        self.assertNotIn('id="autoplay"', html)
        self.assertNotIn("별도 선택 · 한자 확장", html)
        self.assertNotIn("Mac에서 한자 확장 만들기.command", html)
        self.assertNotIn("Windows에서 한자 확장 만들기.cmd", html)
        self.assertNotIn("초심자용 전체 가이드", html)
        self.assertIn("기본 덱만 가져온 경우", html)
        self.assertIn("한자 확장까지 추가한 경우", html)
        self.assertIn('href="#kanji">한자 확장', html)
        self.assertIn("필요하다면 한자 확장을 추가합니다.", html)
        self.assertIn(
            '<a class="v2-button v2-button-dark" href="kanji.html">'
            '한자 확장 가이드 보기',
            html,
        )
        self.assertNotIn("한자 덱도 필요하신가요?", html)
        self.assertNotIn("내가 선택한 구성", html)
        self.assertLess(html.index('id="verify"'), html.index('id="kanji"'))
        self.assertLess(html.index('id="kanji"'), html.index('id="sync"'))
        self.assertIn("약 0.85GB", html)
        self.assertNotIn("QUICK START", html)
        css = (SITE / "assets" / "site.css").read_text(encoding="utf-8")
        self.assertNotIn(".v2-optional-section", css)
        self.assertNotIn(".v2-guide-toc-subtitle", css)

    def test_kanji_guide_is_beginner_complete_and_private_by_default(self) -> None:
        html = (SITE / "kanji.html").read_text(encoding="utf-8")
        parser = self.parsers["kanji.html"]
        for section_id in (
            "why",
            "prepare",
            "pdfs",
            "builder",
            "run",
            "finish",
            "trouble",
            "privacy",
        ):
            self.assertIn(section_id, parser.ids)
        for token in (
            "PDF 두 개를 고르면",
            "한글 뜻이 든 완성본을 배포하지 않습니다",
            "1권 공식 자료 페이지",
            "2권 공식 자료 페이지",
            "모두 압축 풀기",
            "ZIP 안에서 바로 실행하지 마세요",
            "Mac에서 한자 확장 만들기.command",
            "Windows에서 한자 확장 만들기.cmd",
            "첫 번째 창에서 1권 PDF",
            "두 번째 창에서 2권 PDF",
            "한글이나 띄어쓰기가 있는 폴더",
            "JLPT-MAX-kanji-addon-1.0.1.apkg",
            "kanji-builder.log",
            "PDF와 완성 APKG는 사용자 컴퓨터 안에서만",
        ):
            self.assertIn(token, html)
        self.assertIn('role="tab"', html)
        self.assertIn('aria-controls="kanji-run-panel-macos"', html)
        self.assertIn('aria-controls="kanji-run-panel-windows"', html)
        self.assertIn("JLPT-MAX-kanji-builder-1.0.1.zip", html)
        self.assertNotIn("./scripts/build-kanji-addon.sh", html)
        self.assertNotIn("build-kanji-addon.ps1", html)
        self.assertNotIn("Python 3.13", html)
        self.assertNotIn("상권.pdf", html)
        self.assertLess(html.index('id="pdfs"'), html.index('id="builder"'))
        self.assertLess(html.index('id="builder"'), html.index('id="run"'))
        self.assertLess(html.index('id="run"'), html.index('id="finish"'))
        css = (SITE / "assets" / "site.css").read_text(encoding="utf-8")
        faq_summary = re.search(r"\.v2-faq summary\s*\{([^}]+)\}", css)
        if faq_summary is None:
            self.fail("missing FAQ summary styles")
        self.assertIn("display: block;", faq_summary.group(1))
        self.assertIn("padding: 25px 48px 25px 4px;", faq_summary.group(1))
        self.assertNotIn("grid-template-columns", faq_summary.group(1))
        self.assertIn(
            "grid-template-columns: repeat(5, minmax(0, 1fr));",
            css,
        )

    def test_install_page_links_only_to_official_anki_apps(self) -> None:
        html = (SITE / "install-anki.html").read_text(encoding="utf-8")
        self.assertIn("https://apps.ankiweb.net/", html)
        self.assertIn("id373493387", html)
        self.assertIn("id=com.ichi2.anki", html)
        self.assertIn("공식 iOS 앱", html)
        self.assertIn("유료 구매", html)
        self.assertIn('id="apps"', html)
        self.assertIn("공부할 기기의 Anki를 설치합니다.", html)
        self.assertIn("data-tabs data-platform-tabs", html)
        self.assertEqual(5, html.count('class="v2-tab"'))
        self.assertEqual(5, html.count('class="v2-tab-panel v2-device-card"'))
        for platform in ("macos", "windows", "linux", "ios", "android"):
            with self.subTest(platform=platform):
                self.assertIn(f'data-platform="{platform}"', html)
        self.assertNotIn('id="desktop"', html)
        self.assertNotIn('id="mobile"', html)
        self.assertNotIn('href="#desktop"', html)
        self.assertNotIn('href="#mobile"', html)
        self.assertNotIn('id="capabilities"', html)
        self.assertNotIn("WHAT WORKS WHERE", html)
        self.assertNotIn("일상무따 한자 확장 빌드</th>", html)
        self.assertNotIn("일상무따 한자 확장은 빌드 후 가져옵니다.", html)
        self.assertNotIn("현재 Release에서 검증한 macOS", html)
        for redundant_badge in (
            "macOS·Windows·Linux 무료",
            "iPhone·iPad 공식 앱 유료",
            "Android AnkiDroid 무료",
        ):
            with self.subTest(redundant_badge=redundant_badge):
                self.assertNotIn(redundant_badge, html)
        self.assertIn(
            'href="install-anki.html" aria-current="page" aria-label="Anki 설치"',
            html,
        )
        for desktop_first in (
            "처음 설치한다면 컴퓨터에서 시작한 뒤",
            "컴퓨터에서 처음 설정합니다",
            "컴퓨터가 가장 편합니다",
            "<span class=\"v2-step-label\">RECOMMENDED</span>",
            "가능 · 권장",
        ):
            with self.subTest(desktop_first=desktop_first):
                self.assertNotIn(desktop_first, html)
        self.assertNotIn("AnkiApp", html)

    def test_support_page_publishes_safe_diagnostic_boundary(self) -> None:
        html = (SITE / "support.html").read_text(encoding="utf-8")
        release = json.loads(
            (ROOT / "config" / "public-release.json").read_text(
                encoding="utf-8"
            )
        )
        version = release["product_version"]
        core = release["artifacts"][f"JLPT-MAX-Deck-{version}.apkg"]
        self.assertIn(core["sha256"], html)
        self.assertIn(
            '기본 덱 다시 받기 <svg class="button-download-icon"',
            html,
        )
        self.assertIn('class="brand v2-footer-brand"', html)
        self.assertNotIn("v2-brand-badge", html)
        self.assertIn("issues/new?template=bug.yml", html)
        self.assertIn("출판사 PDF", html)
        self.assertIn("개인 Anki 컬렉션", html)
        self.assertIn('id="history"', html)
        self.assertIn('class="v2-release-history"', html)
        self.assertIn("v1.0.1 GitHub Release", html)
        self.assertIn("v1.0.0 GitHub Release", html)
        self.assertIn("현재 · 교정판", html)
        self.assertIn("최초 공개", html)
        self.assertIn("종합 실전 학습 기록만 초기화됩니다.", html)
        self.assertIn("미사용 미디어를 삭제해 저장 공간을 확보합니다.", html)
        self.assertIn("도구 → 미디어 검사", html)
        self.assertIn("휴지통을 비워야 실제 여유 공간이 생깁니다.", html)
        self.assertIn("<h2>한자 확장을 만들 수 없어요.</h2>", html)
        self.assertIn("한자 확장 만들기 전체 가이드", html)
        for build_error in (
            "더블클릭할 실행 파일이 보이지 않아요.",
            "필요한 프로그램을 받지 못했다고 나와요.",
            "<code>PDF hash</code> 또는 <code>page count</code> 오류가 나요.",
            "<code>alignment</code> 오류가 나요.",
            "PDF 선택창을 취소했어요.",
            "완성 파일을 다시 만들고 싶어요.",
        ):
            self.assertIn(build_error, html)
        self.assertIn("kanji-builder.log", html)
        self.assertNotIn("Python 3.13", html)
        self.assertNotIn("PowerShell", html)
        self.assertNotIn("output root must be absent or empty", html)
        self.assertNotIn("한자 확장 문제는 PDF와 빌더 버전을 맞춥니다.", html)
        self.assertIn("<h2>자주 묻는 질문</h2>", html)
        self.assertIn("<h2>오류를 제보하고 싶어요.</h2>", html)
        self.assertIn("<h2>Anki 가져오기가 멈춰요.</h2>", html)
        self.assertIn("<h2>새 버전으로 업데이트하고 싶어요.</h2>", html)
        self.assertNotIn('id="update"', html)
        self.assertNotIn("짧게 답합니다.", html)
        self.assertNotIn("민감한 원본 없이 재현 정보를 보냅니다.", html)

    def test_social_card_matches_current_direct_release(self) -> None:
        source = (SITE / "assets" / "social-card.svg").read_text(encoding="utf-8")
        for current in (
            "단어는 더 깊이,",
            "실전 문제까지.",
            "어휘·음성·실전 문제를 담은 한국어권 JLPT Anki 덱",
            "6,018",
            "7,876",
            "20,065",
        ):
            self.assertIn(current, source)
        for stale in (
            "공개 Anki 덱 빌더",
            "PDF 없이 시작하는",
            "5,800",
            "7,850",
            "21,897",
        ):
            self.assertNotIn(stale, source)

    def test_stale_transition_copy_is_not_published(self) -> None:
        sources = "\n".join(
            (SITE / name).read_text(encoding="utf-8")
            for name in PAGES
        )
        sources += (SITE / "assets" / "social-card.svg").read_text(
            encoding="utf-8"
        )
        for stale in (
            "3분 시작 가이드",
            "예상 3–10분",
            "PDF 불필요",
            "처음에는 PDF도 빌더도 필요 없습니다",
            "Python이나 출판사 PDF는 필요하지 않습니다",
            "기본 덱만 사용할 때는 한자 빌더",
            "기본 덱은 바로,",
            "한자는 확장.",
            "소스 PDF나 Python 환경",
            "자동재생은 기본 덱에 포함되어 있습니다",
            "별도 애드온이나 추가 설치가 필요하지 않습니다",
            "PDF나 빌드 과정은 필요 없습니다",
            "기본 덱은 빌더 ZIP 안에 있지 않습니다",
            "기본 덱을 받는 데 PDF가 필요한가요?",
            "기본 덱은 어디서나, 빌드는 컴퓨터에서.",
            "CORE · FILE",
            "CORE · ANKI",
            "빌드할 때 LLM이 즉석에서 만드나요?",
            "학습자가 기본 덱을 가져오거나 한자 확장을 만들 때 LLM",
            "자동재생에 별도 설치가 필요한가요?",
            "다락원·동양북스·해커스",
            "동양북스·해커스의 N1~N5 어휘",
            "출판사 뜻을 그대로 옮기지 않고",
            "출판사 교재가 지정한 유형과 뜻",
            "원문과 JMdict의 의미·품사·표기 근거",
            "출판사 공통 수록 범위",
            "무료로 내려받",
            "구매 인증 없이",
            "macOS / Linux",
            "처음부터 LLM으로",
            "네이버, 해커스, 동양북스",
        ):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, sources)

    def test_interactions_cover_menu_tabs_and_copy(self) -> None:
        script = (SITE / "assets" / "site.js").read_text(encoding="utf-8")
        for token in (
            "Escape",
            "ArrowLeft",
            "ArrowRight",
            "Home",
            "End",
            "data-copy-target",
            "navigator.maxTouchPoints",
            "return 'linux'",
            "tabList.scrollTo",
        ):
            self.assertIn(token, script)
        homepage = (SITE / "index.html").read_text(encoding="utf-8")
        for token in (
            "HTMLAudioElement",
            "data-flip-card",
            "data-carousel-next",
            "ArrowLeft",
            "ArrowRight",
        ):
            self.assertIn(token, homepage)

    def test_css_has_balanced_blocks(self) -> None:
        for filename in ("site.css", "showcase.css"):
            css = (SITE / "assets" / filename).read_text(encoding="utf-8")
            css_without_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
            with self.subTest(filename=filename):
                self.assertEqual(
                    css_without_comments.count("{"),
                    css_without_comments.count("}"),
                )

    def test_pages_artifact_fingerprints_site_assets(self) -> None:
        module = load_prepare_module()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "pages"
            module.prepare_site(SITE, output)
            for name in PAGES:
                html = (output / name).read_text(encoding="utf-8")
                with self.subTest(page=name):
                    if name == "index.html":
                        self.assertRegex(
                            html,
                            r"assets/showcase\.css\?v=[0-9a-f]{12}",
                        )
                    else:
                        self.assertRegex(
                            html,
                            r"assets/site\.css\?v=[0-9a-f]{12}",
                        )
                        self.assertRegex(
                            html,
                            r"assets/site\.js\?v=[0-9a-f]{12}",
                        )


if __name__ == "__main__":
    unittest.main()
