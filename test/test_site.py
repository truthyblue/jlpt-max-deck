from __future__ import annotations

import html as html_lib
import hashlib
import importlib.util
import json
import re
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = ROOT / "site"
REPOSITORY_URL = "https://github.com/truthyblue/jlpt-max-deck"
SITE_URL = "https://truthyblue.github.io/jlpt-max-deck"
INDEXABLE_PAGE_URLS = {
    "index.html": f"{SITE_URL}/",
    "getting-started.html": f"{SITE_URL}/getting-started.html",
    "install-anki.html": f"{SITE_URL}/install-anki.html",
}
SPEC = importlib.util.spec_from_file_location(
    "prepare_pages_site", ROOT / "scripts" / "prepare-pages-site.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load Pages site preparer")
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


class _SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.elements.append(
            (tag, {key: value or "" for key, value in attrs})
        )


def _parse(index: Path) -> _SiteParser:
    parser = _SiteParser()
    parser.feed(index.read_text(encoding="utf-8"))
    return parser


def _webp_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise AssertionError(f"not a RIFF WebP file: {path}")

    declared_size = struct.unpack_from("<I", data, 4)[0] + 8
    if declared_size != len(data):
        raise AssertionError(
            f"WebP RIFF size mismatch: {path} "
            f"(declared {declared_size}, actual {len(data)})"
        )

    offset = 12
    while offset < len(data):
        if offset + 8 > len(data):
            raise AssertionError(f"truncated WebP chunk header: {path}")
        chunk_type = data[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        payload_start = offset + 8
        payload_end = payload_start + chunk_size
        if payload_end > len(data):
            raise AssertionError(f"truncated WebP chunk payload: {path}")
        payload = data[payload_start:payload_end]

        if chunk_type == b"VP8L":
            if len(payload) < 5 or payload[0] != 0x2F:
                raise AssertionError(f"invalid VP8L header: {path}")
            dimensions = int.from_bytes(payload[1:5], "little")
            if dimensions >> 29:
                raise AssertionError(f"unsupported VP8L version: {path}")
            return (
                (dimensions & 0x3FFF) + 1,
                ((dimensions >> 14) & 0x3FFF) + 1,
            )

        if chunk_type == b"VP8X":
            if len(payload) < 10:
                raise AssertionError(f"truncated VP8X header: {path}")
            return (
                int.from_bytes(payload[4:7], "little") + 1,
                int.from_bytes(payload[7:10], "little") + 1,
            )

        if chunk_type == b"VP8 ":
            if len(payload) < 10 or payload[3:6] != b"\x9d\x01\x2a":
                raise AssertionError(f"invalid VP8 key-frame header: {path}")
            return (
                struct.unpack_from("<H", payload, 6)[0] & 0x3FFF,
                struct.unpack_from("<H", payload, 8)[0] & 0x3FFF,
            )

        offset = payload_end + (chunk_size & 1)

    raise AssertionError(f"WebP image chunk not found: {path}")


def _jpeg_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise AssertionError(f"not a JPEG file: {path}")

    start_of_frame_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    offset = 2
    while offset < len(data):
        if data[offset] != 0xFF:
            raise AssertionError(f"invalid JPEG marker: {path}")
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in {0x01, *range(0xD0, 0xDA)}:
            continue
        if offset + 2 > len(data):
            raise AssertionError(f"truncated JPEG segment: {path}")
        segment_size = struct.unpack_from(">H", data, offset)[0]
        if segment_size < 2 or offset + segment_size > len(data):
            raise AssertionError(f"invalid JPEG segment size: {path}")
        if marker in start_of_frame_markers:
            if segment_size < 7:
                raise AssertionError(f"truncated JPEG frame header: {path}")
            height = struct.unpack_from(">H", data, offset + 3)[0]
            width = struct.unpack_from(">H", data, offset + 5)[0]
            return width, height
        offset += segment_size

    raise AssertionError(f"JPEG frame header not found: {path}")


def _json_ld_documents(path: Path) -> list[object]:
    html = path.read_text(encoding="utf-8")
    documents = re.findall(
        r'<script\s+type="application/ld\+json">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    return [json.loads(document) for document in documents]


def _json_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _json_strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _json_strings(child)]
    return []


def _css_block(css: str, prelude: str, occurrence: int = 0) -> str:
    marker = f"{prelude} {{"
    start = -1
    for _ in range(occurrence + 1):
        start = css.index(marker, start + 1)
    opening = start + len(marker) - 1
    depth = 0
    for index in range(opening, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return css[start : index + 1]
    raise AssertionError(f"unclosed CSS block: {prelude}")


def _css_declarations(
    css: str, selector: str, occurrence: int = 0
) -> dict[str, str]:
    block = _css_block(css, selector, occurrence)
    body = block[block.index("{") + 1 : -1]
    declarations: dict[str, str] = {}
    for declaration in body.split(";"):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        declarations[name.strip()] = value.strip()
    return declarations


class SiteContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.index = SITE_ROOT / "index.html"
        self.html = self.index.read_text(encoding="utf-8")
        self.parser = _parse(self.index)

    def test_ids_fragments_controls_and_local_files_are_closed(self) -> None:
        ids = [attrs["id"] for _, attrs in self.parser.elements if "id" in attrs]
        self.assertEqual(len(ids), len(set(ids)))

        for tag, attrs in self.parser.elements:
            href = attrs.get("href", "")
            if tag == "a" and href.startswith("#"):
                self.assertIn(href[1:], ids)
            controls = attrs.get("aria-controls")
            if controls:
                self.assertIn(controls, ids)

            local_reference = ""
            if tag in {"img", "audio", "script"}:
                local_reference = attrs.get("src", "")
            elif tag == "link":
                local_reference = href
            elif tag == "a" and href and not href.startswith(("#", "http")):
                local_reference = href
            if local_reference:
                parsed_reference = urlsplit(local_reference)
                if parsed_reference.scheme or parsed_reference.netloc:
                    continue
                target = (SITE_ROOT / parsed_reference.path).resolve()
                self.assertTrue(target.is_file(), local_reference)

    def test_images_and_external_links_have_accessibility_contracts(self) -> None:
        images = [attrs for tag, attrs in self.parser.elements if tag == "img"]
        self.assertEqual(len(images), 18)
        for index, attrs in enumerate(images):
            self.assertTrue(attrs.get("alt"))
            self.assertGreater(int(attrs.get("width", "0")), 0)
            self.assertGreater(int(attrs.get("height", "0")), 0)
            self.assertEqual(attrs.get("decoding"), "async")
            if index == 0:
                self.assertEqual(attrs.get("fetchpriority"), "high")
            else:
                self.assertEqual(attrs.get("loading"), "lazy")

        for tag, attrs in self.parser.elements:
            if tag != "a" or attrs.get("target") != "_blank":
                continue
            rel = set(attrs.get("rel", "").split())
            self.assertTrue({"noopener", "noreferrer"}.issubset(rel))
            self.assertIn("새 탭", attrs.get("aria-label", ""))

    def test_primary_card_showcase_surfaces_expanded_kanji_details(self) -> None:
        asset = SITE_ROOT / "assets" / "card-dasu-answer.webp"
        showcases = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "img" and attrs.get("src") == "assets/card-dasu-answer.webp"
        ]
        self.assertEqual(len(showcases), 2)
        for attrs in showcases:
            self.assertEqual(attrs.get("data-showcase-state"), "kanji-expanded")
            self.assertEqual(
                (int(attrs["width"]), int(attrs["height"])), (640, 1352)
            )
            self.assertIn("버튼 아래에 펼쳐진 出 한자 정보", attrs.get("alt", ""))
            self.assertIn("부수·5획", attrs.get("alt", ""))

        self.assertEqual(_webp_dimensions(asset), (640, 1352))
        folded_asset_webp_hash = (
            "dc361c33c5cb4bc45f04571e24febc5eabccb71cba629f7e50115d2a1fb87329"
        )
        self.assertNotEqual(
            hashlib.sha256(asset.read_bytes()).hexdigest(),
            folded_asset_webp_hash,
        )
        css = (SITE_ROOT / "assets" / "site.css").read_text(encoding="utf-8")
        self.assertEqual(
            _css_declarations(css, ".kanji-feature-callout").get("top"),
            "81%",
        )
        self.assertEqual(
            _css_declarations(css, ".kanji-feature-callout .card-feature-label").get(
                "top"
            ),
            "7%",
        )

    def test_dedicated_kanji_showcase_uses_a_real_linked_card(self) -> None:
        asset = SITE_ROOT / "assets" / "card-kanji-ima-answer.webp"
        image = next(
            attrs
            for tag, attrs in self.parser.elements
            if tag == "img"
            and attrs.get("src") == "assets/card-kanji-ima-answer.webp"
        )
        self.assertEqual(
            (int(image["width"]), int(image["height"])), (640, 744)
        )
        self.assertEqual(_webp_dimensions(asset), (640, 744))
        self.assertIn("今月·今度·今週 연결 어휘", image.get("alt", ""))
        for snippet in (
            'class="section kanji-section" id="kanji"',
            "한 글자에서,<br>연결된 단어까지.",
            "2,337</strong><span>상·하권 한자 노트",
            "한국어 뜻과 일본어 읽기",
            "부수와 획수까지 한 번에",
            "아는 한자를 실제 단어로 연결",
        ):
            self.assertIn(snippet, self.html)

    def test_practice_carousel_covers_all_six_official_types(self) -> None:
        expected_types = [
            "kanji_reading",
            "orthography",
            "word_formation",
            "context_defined",
            "paraphrase",
            "usage",
        ]
        slides = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "article"
            and "practice-slide" in attrs.get("class", "").split()
        ]
        self.assertEqual(
            [attrs.get("data-question-type") for attrs in slides],
            expected_types,
        )

        expected_assets = {
            "assets/practice-kanji-reading.webp",
            "assets/practice-orthography.webp",
            "assets/practice-word-formation.webp",
            "assets/practice-context-defined.webp",
            "assets/practice-paraphrase.webp",
            "assets/practice-usage.webp",
        }
        practice_images = {
            attrs["src"]: attrs
            for tag, attrs in self.parser.elements
            if tag == "img" and attrs.get("src") in expected_assets
        }
        self.assertEqual(set(practice_images), expected_assets)
        for path, attrs in practice_images.items():
            self.assertEqual(
                (int(attrs["width"]), int(attrs["height"])), (640, 540)
            )
            self.assertEqual(_webp_dimensions(SITE_ROOT / path), (640, 540))

        expected_answers = {
            "assets/practice-kanji-reading-answer.webp": (640, 781),
            "assets/practice-orthography-answer.webp": (640, 804),
            "assets/practice-word-formation-answer.webp": (640, 868),
            "assets/practice-context-defined-answer.webp": (640, 952),
            "assets/practice-paraphrase-answer.webp": (640, 947),
            "assets/practice-usage-answer.webp": (640, 910),
        }
        answer_images = {
            attrs["src"]: attrs
            for tag, attrs in self.parser.elements
            if tag == "img" and attrs.get("src") in expected_answers
        }
        self.assertEqual(set(answer_images), set(expected_answers))
        for path, dimensions in expected_answers.items():
            attrs = answer_images[path]
            self.assertEqual(
                (int(attrs["width"]), int(attrs["height"])), dimensions
            )
            self.assertEqual(_webp_dimensions(SITE_ROOT / path), dimensions)

        flip_buttons = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "button" and "data-flip-card" in attrs
        ]
        self.assertEqual(len(flip_buttons), 6)
        self.assertEqual(
            len({attrs.get("aria-describedby") for attrs in flip_buttons}), 6
        )
        self.assertEqual(
            len({attrs.get("aria-controls") for attrs in flip_buttons}), 6
        )
        for attrs in flip_buttons:
            self.assertEqual(attrs.get("aria-expanded"), "false")
            self.assertNotIn("aria-pressed", attrs)
            self.assertEqual(
                attrs.get("aria-label"), attrs.get("data-show-answer-label")
            )
            self.assertTrue(attrs.get("data-show-question-label"))
            self.assertTrue(attrs.get("aria-controls"))

        flip_inners = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "div"
            and "practice-card-inner" in attrs.get("class", "").split()
        ]
        front_faces = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "section"
            and "practice-card-front" in attrs.get("class", "").split()
        ]
        back_faces = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "section"
            and "practice-card-back" in attrs.get("class", "").split()
        ]
        announcements = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "span"
            and "practice-flip-announcement" in attrs.get("class", "").split()
        ]
        self.assertEqual(len(flip_inners), 6)
        self.assertEqual(len(front_faces), 6)
        self.assertEqual(len(back_faces), 6)
        self.assertEqual(len(announcements), 6)
        self.assertTrue(
            all(attrs.get("aria-live") == "polite" for attrs in announcements)
        )
        self.assertTrue(
            all(attrs.get("aria-hidden") == "false" for attrs in front_faces)
        )
        self.assertTrue(
            all(attrs.get("aria-hidden") == "true" for attrs in back_faces)
        )

        hidden_backs = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "section"
            and "practice-card-back" in attrs.get("class", "").split()
            and "hidden" in attrs
        ]
        hidden_answer_links = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "a"
            and "practice-answer-link" in attrs.get("class", "").split()
            and "hidden" in attrs
        ]
        self.assertEqual(len(hidden_backs), 6)
        self.assertEqual(len(hidden_answer_links), 6)
        self.assertEqual(self.html.count('class="practice-transcript sr-only"'), 12)
        self.assertEqual(
            len(
                re.findall(
                    r'<section class="practice-card-face practice-card-(?:front|back)"[^>]*>\s*<header>',
                    self.html,
                )
            ),
            12,
        )
        self.assertEqual(self.html.count("문제로 돌아가기</small>"), 6)
        practice_card_images = {
            **practice_images,
            **answer_images,
        }
        for attrs in practice_card_images.values():
            self.assertEqual(
                attrs.get("alt"),
                "시각적 카드 예시. 같은 내용은 이어지는 구조화된 텍스트로 제공됩니다.",
            )
            self.assertEqual(attrs.get("aria-hidden"), "true")
            self.assertNotRegex(attrs.get("alt", ""), r"정답\s*\d|번이 정답")

        slide_html_blocks = re.findall(
            r'<article class="practice-slide".*?</article>',
            self.html,
            flags=re.DOTALL,
        )
        self.assertEqual(len(slide_html_blocks), 6)
        for slide_html in slide_html_blocks:
            self.assertLess(
                slide_html.index('practice-card-front'),
                slide_html.index('class="practice-flip-card"'),
            )
            self.assertLess(
                slide_html.index('class="practice-transcript sr-only"'),
                slide_html.index('class="practice-flip-card"'),
            )

        carousel = next(
            attrs
            for tag, attrs in self.parser.elements
            if tag == "div" and attrs.get("id") == "practice-carousel"
        )
        self.assertIn("data-carousel", carousel)
        self.assertEqual(carousel.get("tabindex"), "0")
        self.assertEqual(carousel.get("role"), "group")
        self.assertEqual(carousel.get("aria-roledescription"), "캐러셀")
        self.assertEqual(
            carousel.get("aria-describedby"), "practice-carousel-hint"
        )
        expected_slide_labels = [
            "1 / 6 · 한자 읽기",
            "2 / 6 · 표기",
            "3 / 6 · 단어 형성",
            "4 / 6 · 문맥 규정",
            "5 / 6 · 바꿔쓰기",
            "6 / 6 · 용법",
        ]
        self.assertEqual(
            [attrs.get("aria-roledescription") for attrs in slides],
            ["슬라이드"] * 6,
        )
        self.assertEqual(
            [attrs.get("aria-label") for attrs in slides], expected_slide_labels
        )
        self.assertEqual(
            [attrs.get("aria-current") for attrs in slides],
            ["true", None, None, None, None, None],
        )
        carousel_status = next(
            attrs
            for tag, attrs in self.parser.elements
            if tag == "span" and attrs.get("id") == "practice-carousel-status"
        )
        self.assertEqual(carousel_status.get("role"), "status")
        self.assertEqual(carousel_status.get("aria-live"), "polite")
        self.assertEqual(carousel_status.get("aria-atomic"), "true")
        self.assertIn(
            '>현재 1 / 6 · 한자 읽기</span>',
            self.html,
        )
        controls = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "button"
            and "carousel-control" in attrs.get("class", "").split()
        ]
        self.assertEqual(len(controls), 2)
        self.assertTrue(
            all(attrs.get("aria-controls") == "practice-carousel" for attrs in controls)
        )

        stylesheet = next(
            attrs
            for tag, attrs in self.parser.elements
            if tag == "link" and attrs.get("rel") == "stylesheet"
        )
        stylesheet_url = urlsplit(stylesheet["href"])
        self.assertEqual(stylesheet_url.path, "assets/site.css")
        expected_css_version = hashlib.sha256(
            (SITE_ROOT / "assets" / "site.css").read_bytes()
        ).hexdigest()[:12]
        self.assertEqual(
            parse_qs(stylesheet_url.query), {"v": [expected_css_version]}
        )

        css = (SITE_ROOT / "assets" / "site.css").read_text(encoding="utf-8")
        track = _css_declarations(css, ".practice-carousel")
        self.assertEqual(track.get("grid-auto-columns"), "47%")
        self.assertEqual(track.get("overflow-x"), "auto")
        self.assertEqual(track.get("overflow-y"), "hidden")
        self.assertEqual(track.get("scroll-snap-type"), "x mandatory")
        self.assertEqual(track.get("align-items"), "start")
        self.assertEqual(track.get("overscroll-behavior-x"), "contain")
        self.assertEqual(
            track.get("scrollbar-color"),
            "rgba(216, 255, 98, .48) rgba(255, 255, 255, .08)",
        )
        self.assertEqual(track.get("scrollbar-width"), "thin")
        self.assertEqual(
            {
                key: _css_declarations(css, ".practice-slide").get(key)
                for key in ("align-self", "scroll-snap-align")
            },
            {"align-self": "start", "scroll-snap-align": "start"},
        )
        self.assertEqual(
            _css_declarations(css, ".practice-flip-card").get("cursor"),
            "pointer",
        )
        self.assertEqual(
            _css_declarations(css, ".practice-flip-card").get("position"),
            "absolute",
        )
        self.assertEqual(
            _css_declarations(css, ".practice-card-inner").get("pointer-events"),
            "none",
        )
        self.assertEqual(
            _css_declarations(css, ".practice-answer-link").get("pointer-events"),
            "auto",
        )
        self.assertEqual(
            _css_declarations(css, ".practice-card-face").get("border-radius"),
            "24px",
        )
        flip_ready = _css_declarations(
            css, ".practice-slide.is-flip-ready"
        )
        self.assertEqual(flip_ready.get("perspective"), "1400px")
        self.assertIn("height .62s", flip_ready.get("transition", ""))
        flip_inner = _css_declarations(
            css, ".practice-slide.is-flip-ready .practice-card-inner"
        )
        self.assertEqual(flip_inner.get("transform-style"), "preserve-3d")
        self.assertIn("transform .62s", flip_inner.get("transition", ""))
        flip_face = _css_declarations(
            css, ".practice-slide.is-flip-ready .practice-card-face"
        )
        self.assertEqual(flip_face.get("backface-visibility"), "hidden")
        self.assertEqual(flip_face.get("-webkit-backface-visibility"), "hidden")
        self.assertEqual(
            _css_declarations(
                css, ".practice-slide.is-flip-ready .practice-card-back"
            ).get("transform"),
            "rotateY(-180deg)",
        )
        self.assertEqual(
            _css_declarations(
                css,
                ".practice-slide.is-flip-ready.is-flipped .practice-card-inner",
            ).get("transform"),
            "rotateY(-180deg)",
        )
        reduced_motion = _css_block(css, "@media (prefers-reduced-motion: reduce)")
        self.assertIn(".practice-slide.is-flip-ready", reduced_motion)
        self.assertIn("perspective: none", reduced_motion)
        self.assertIn(".practice-card-face[aria-hidden=\"true\"]", reduced_motion)
        self.assertIn("display: none", reduced_motion)
        self.assertIn("carousel.scrollBy({", self.html)
        self.assertIn("const focusCarouselSlide = (slide) => {", self.html)
        self.assertIn("carousel.scrollTo({", self.html)
        self.assertIn("focusCarouselSlide(slide)", self.html)
        self.assertIn("carousel.addEventListener('focusin', (event) => {", self.html)
        self.assertIn("event.target.closest('.practice-slide')", self.html)
        self.assertIn("slideRect.right <= visibleRight + 2", self.html)
        self.assertIn(
            "좌우로 스크롤하거나 이동 버튼으로 유형을 바꿉니다.", self.html
        )
        self.assertIn(
            "키보드에서는 캐러셀에 초점을 둔 뒤 왼쪽·오른쪽 화살표 키",
            self.html,
        )
        self.assertIn("reducedMotion.matches ? 'auto' : 'smooth'", self.html)
        for snippet in (
            "const inner = slide?.querySelector('.practice-card-inner')",
            "syncFlipHeight(front)",
            "const height = face.offsetHeight",
            "back.hidden = false",
            "slide.style.setProperty('--practice-card-height'",
            "slide.classList.add('is-flip-ready')",
            "new ResizeObserver(syncActiveFlipHeight)",
            "syncFlipHeight(showAnswer ? back : front)",
            "button.setAttribute('aria-expanded', String(showAnswer))",
            "front.setAttribute('aria-hidden', String(showAnswer))",
            "back.setAttribute('aria-hidden', String(!showAnswer))",
            "state.textContent = showAnswer ? '정답·해설 면' : '문제 면'",
            "slide.classList.toggle('is-flipped', showAnswer)",
            "const status = document.getElementById(`${carousel.id}-status`)",
            "if (index === currentSlideIndex) slide.setAttribute('aria-current', 'true')",
            "else slide.removeAttribute('aria-current')",
            "if (status) status.textContent = `현재 ${slides[currentSlideIndex].getAttribute('aria-label')}`",
            "carousel.addEventListener('scroll', scheduleUpdate, { passive: true })",
        ):
            self.assertIn(snippet, self.html)
        flip_block = self.html.index(
            "document.querySelectorAll('[data-flip-card]').forEach((button) => {"
        )
        click_handler = self.html.index(
            "button.addEventListener('click', () => {", flip_block
        )
        reveal_back = self.html.index(
            "back.setAttribute('aria-hidden', String(!showAnswer))", click_handler
        )
        reveal_link = self.html.index(
            "answerLink.hidden = !showAnswer", click_handler
        )
        measure_active_face = self.html.index(
            "syncFlipHeight(showAnswer ? back : front)", click_handler
        )
        self.assertLess(reveal_back, measure_active_face)
        self.assertLess(reveal_link, measure_active_face)
        self.assertNotIn("face.scrollHeight", self.html)
        self.assertNotIn("front.hidden = showAnswer", self.html)
        self.assertNotIn("back.hidden = !showAnswer", self.html)

    def test_reference_showcase_matches_the_nine_card_contract(self) -> None:
        self.assertFalse((SITE_ROOT / "assets" / "reference-calendar.png").exists())
        self.assertNotIn("reference-calendar.png", self.html)
        self.assertNotIn("전체 표 보기", self.html)
        for snippet in (
            'class="section reference-section" id="reference"',
            'class="reference-preview-card"',
            "일부 항목으로 구성한 사이트 미리보기",
            "1月",
            "しがつ",
            "日曜日",
            "すいようび",
            "1日",
            "はつか",
            "9</strong><span>덱 안의 참조표 카드",
            "월 12개, 요일 7개, 날짜 31개",
            "수량 표현 8파트",
            "個·つ",
            "年·時",
            "실제 덱 카드에는 50개 항목",
        ):
            self.assertIn(snippet, self.html)

    def test_site_preserves_desktop_scale_and_compacts_mobile_hierarchy(self) -> None:
        css = (SITE_ROOT / "assets" / "site.css").read_text(encoding="utf-8")
        expected_sizes = {
            "body": "20px",
            ".brand": "20px",
            ".site-header nav": "20px",
            ".feature-callouts p": "20px",
            ".curation-card p": "20px",
            ".content-card > p:last-of-type": "20px",
            ".trust-card p": "20px",
            ".boundary-card p": "20px",
            "footer": "20px",
        }
        for selector, size in expected_sizes.items():
            self.assertEqual(
                _css_declarations(css, selector).get("font-size"), size
            )
        self.assertEqual(
            _css_declarations(css, ".nav-action", occurrence=1).get("font-size"),
            "16px",
        )

        brand_mark = _css_declarations(css, ".brand-mark")
        self.assertEqual(
            {key: brand_mark.get(key) for key in ("width", "height")},
            {"width": "52px", "height": "52px"},
        )
        self.assertEqual(
            _css_declarations(css, ".brand-mark-jlpt").get("font-size"), "8px"
        )
        self.assertEqual(
            _css_declarations(css, ".brand-mark-jlpt").get("position"),
            "absolute",
        )
        self.assertEqual(
            _css_declarations(css, ".brand-mark-jlpt").get("top"), "9px"
        )
        self.assertEqual(
            _css_declarations(css, ".brand-mark-max").get("font-size"), "21px"
        )
        self.assertEqual(
            _css_declarations(css, ".brand-mark-max").get("transform"),
            "translateY(2px)",
        )
        self.assertEqual(
            _css_declarations(css, ".site-header .nav-guide-links").get(
                "margin-left"
            ),
            "10px",
        )

        tablet = _css_block(css, "@media (max-width: 820px)")
        self.assertEqual(
            _css_declarations(tablet, "body").get("font-size"), "18px"
        )
        self.assertEqual(
            _css_declarations(tablet, ".site-header nav").get("font-size"),
            "16px",
        )
        tablet_section = _css_declarations(tablet, ".section")
        self.assertEqual(tablet_section.get("padding-top"), "88px")
        self.assertEqual(tablet_section.get("padding-bottom"), "88px")
        self.assertEqual(
            _css_declarations(tablet, ".hero h1").get("font-size"),
            "clamp(44px, 8vw, 52px)",
        )
        self.assertEqual(
            _css_declarations(
                tablet, ".section-heading h2,\n  .start-copy h2,\n  .closing h2"
            ).get("font-size"),
            "clamp(40px, 5vw, 43px)",
        )

        phone = _css_block(css, "@media (max-width: 560px)")
        self.assertEqual(
            _css_declarations(phone, "body").get("font-size"), "17px"
        )
        self.assertEqual(
            _css_declarations(phone, ".brand").get("font-size"), "16px"
        )
        phone_mark = _css_declarations(phone, ".brand-mark")
        self.assertEqual(
            {key: phone_mark.get(key) for key in ("width", "height")},
            {"width": "44px", "height": "44px"},
        )
        self.assertEqual(
            _css_declarations(phone, ".brand-mark-jlpt").get("font-size"), "8px"
        )
        self.assertEqual(
            _css_declarations(phone, ".brand-mark-jlpt").get("top"), "8px"
        )
        self.assertEqual(
            _css_declarations(phone, ".brand-mark-max").get("font-size"), "18px"
        )
        self.assertEqual(
            _css_declarations(phone, ".nav-action").get("font-size"), "14px"
        )
        phone_nav_link = _css_declarations(phone, ".site-header nav a")
        self.assertEqual(phone_nav_link.get("min-height"), "44px")
        self.assertEqual(phone_nav_link.get("background"), "transparent")
        self.assertEqual(phone_nav_link.get("border"), "0")
        self.assertEqual(phone_nav_link.get("border-radius"), "0")
        phone_header = _css_declarations(phone, ".site-header")
        self.assertEqual(phone_header.get("height"), "180px")
        self.assertEqual(phone_header.get("padding-bottom"), "104px")
        phone_nav = _css_declarations(phone, ".site-header nav")
        self.assertEqual(phone_nav.get("display"), "grid")
        self.assertEqual(phone_nav.get("overflow"), "visible")
        self.assertEqual(phone_nav.get("scroll-snap-type"), "none")
        self.assertEqual(phone_nav.get("mask-image"), "none")
        self.assertEqual(
            _css_declarations(phone, ".site-header .nav-section-links").get(
                "grid-template-columns"
            ),
            "repeat(5, minmax(0, 1fr))",
        )
        phone_guide_links = _css_declarations(
            phone, ".site-header .nav-guide-links"
        )
        self.assertEqual(
            phone_guide_links.get("grid-template-columns"),
            "repeat(2, minmax(0, 1fr))",
        )
        self.assertEqual(phone_guide_links.get("margin-left"), "0")
        self.assertEqual(
            _css_declarations(
                phone, ".site-header .nav-guide-links::before"
            ).get("display"),
            "none",
        )
        phone_section = _css_declarations(phone, ".section")
        self.assertEqual(phone_section.get("padding"), "72px 20px")
        self.assertEqual(
            _css_declarations(phone, ".hero h1").get("font-size"),
            "clamp(40px, 8vw, 48px)",
        )
        self.assertEqual(
            _css_declarations(phone, ".content-card").get("min-height"), "0"
        )
        self.assertEqual(
            _css_declarations(phone, ".boundary-card").get("min-height"), "0"
        )

        narrow = _css_block(css, "@media (max-width: 360px)")
        self.assertEqual(
            _css_declarations(
                narrow, ".nav-action-label,\n  .card-feature-label small"
            ).get("display"),
            "none",
        )

    def test_phone_navigation_ctas_and_card_samples_have_compact_affordances(
        self,
    ) -> None:
        for full, compact in (
            ("어휘 카드", "어휘"),
            ("한자 카드", "한자"),
            ("실전 문제", "문제"),
            ("참조표", "참조"),
            ("빌드", "빌드"),
            ("시작 가이드", "가이드"),
            ("Anki 설치", "설치"),
        ):
            self.assertRegex(
                self.html,
                rf'<span\s+class="nav-label-full">\s*{re.escape(full)}\s*</span>'
                rf'\s*<span\s+class="nav-label-compact">\s*{re.escape(compact)}'
                r"\s*</span>",
            )
        self.assertEqual(self.html.count('class="nav-label-full"'), 7)
        self.assertEqual(self.html.count('class="nav-label-compact"'), 7)
        self.assertEqual(self.html.count('class="mobile-label">PC 빌드 방법 보기'), 1)
        self.assertIn('class="mobile-label">시작 가이드', self.html)

        expected_nav_labels = {
            "#cards": "어휘 카드",
            "#kanji": "한자 카드",
            "#practice": "실전 문제",
            "#reference": "참조표",
            "#start": "빌드",
            "getting-started.html": "시작 가이드",
            "install-anki.html": "Anki 설치",
        }
        nav_links: dict[str, str] = {}
        for tag, attrs in self.parser.elements:
            href = attrs.get("href")
            label = attrs.get("aria-label")
            if (
                tag == "a"
                and href is not None
                and label is not None
                and href in expected_nav_labels
                and label == expected_nav_labels[href]
            ):
                nav_links[href] = label
        self.assertEqual(nav_links, expected_nav_labels)

        support_grid_element = next(
            attrs
            for tag, attrs in self.parser.elements
            if tag == "div" and "support-card-grid" in attrs.get("class", "").split()
        )
        self.assertEqual(support_grid_element.get("role"), "region")
        self.assertEqual(support_grid_element.get("tabindex"), "0")
        self.assertIn("가로로 스크롤", support_grid_element.get("aria-label", ""))

        zoom = next(
            attrs
            for tag, attrs in self.parser.elements
            if tag == "a" and "main-card-zoom" in attrs.get("class", "").split()
        )
        self.assertEqual(zoom.get("href"), "assets/card-dasu-answer.webp")
        self.assertEqual(zoom.get("target"), "_blank")
        self.assertIn("새 탭", zoom.get("aria-label", ""))

        css = (SITE_ROOT / "assets" / "site.css").read_text(encoding="utf-8")
        self.assertEqual(
            _css_declarations(css, ".main-card-zoom").get("display"), "none"
        )
        self.assertEqual(
            _css_declarations(css, ".nav-label-compact,\n.mobile-label").get(
                "display"
            ),
            "none",
        )
        self.assertEqual(
            _css_declarations(css, ".mobile-device .desktop-label").get("display"),
            "none",
        )
        self.assertEqual(
            _css_declarations(css, ".mobile-device .mobile-label").get("display"),
            "inline",
        )
        platform_script = (SITE_ROOT / "assets" / "platform.js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "document.documentElement.classList.add('mobile-device')",
            platform_script,
        )
        compact_showcase = _css_block(css, "@media (max-width: 900px)")
        self.assertEqual(
            _css_declarations(
                compact_showcase, ".kanji-showcase,\n  .reference-showcase"
            ).get("grid-template-columns"),
            "1fr",
        )
        tablet = _css_block(css, "@media (max-width: 820px)")
        self.assertEqual(
            _css_declarations(tablet, ".desktop-label").get("display"), "none"
        )
        self.assertEqual(
            _css_declarations(tablet, ".mobile-label").get("display"), "inline"
        )
        phone = _css_block(css, "@media (max-width: 560px)")
        self.assertEqual(
            _css_declarations(phone, ".nav-label-full,\n  .desktop-label").get(
                "display"
            ),
            "none",
        )
        self.assertEqual(
            _css_declarations(phone, ".nav-label-compact,\n  .mobile-label").get(
                "display"
            ),
            "inline",
        )
        phone_zoom = _css_declarations(phone, ".main-card-zoom")
        self.assertEqual(phone_zoom.get("display"), "inline-flex")
        self.assertEqual(phone_zoom.get("min-height"), "44px")
        support_grid = _css_declarations(phone, ".support-card-grid")
        self.assertEqual(support_grid.get("grid-auto-columns"), "88%")
        self.assertEqual(support_grid.get("grid-auto-flow"), "column")
        self.assertEqual(support_grid.get("overflow-x"), "auto")
        self.assertEqual(support_grid.get("scroll-snap-type"), "x mandatory")
        support_samples = _css_declarations(
            phone, ".mini-card-sample,\n  .support-register-sample"
        )
        self.assertEqual(support_samples.get("scroll-snap-align"), "start")

    def test_curation_spacing_and_hero_glyph_contrast_are_deliberate(self) -> None:
        css = (SITE_ROOT / "assets" / "site.css").read_text(encoding="utf-8")
        self.assertEqual(
            _css_declarations(css, ".curation-card h3").get("margin"),
            "20px 0 16px",
        )

        tablet = _css_block(css, "@media (max-width: 820px)")
        phone = _css_block(css, "@media (max-width: 560px)")
        self.assertEqual(
            _css_declarations(tablet, ".curation-card h3").get("margin-top"),
            "18px",
        )
        self.assertEqual(
            _css_declarations(phone, ".curation-card h3").get("margin-top"),
            "16px",
        )

        glyphs = _css_declarations(css, ".hero-glyphs")
        self.assertEqual(glyphs.get("color"), "rgba(216, 255, 98, .035)")
        self.assertEqual(
            glyphs.get("-webkit-text-stroke"),
            "1px rgba(216, 255, 98, .18)",
        )

    def test_scrollable_tables_and_inline_links_keep_accessible_cues(self) -> None:
        source_table = next(
            attrs
            for tag, attrs in self.parser.elements
            if tag == "div" and "source-table" in attrs.get("class", "").split()
        )
        self.assertEqual(source_table.get("role"), "table")
        self.assertEqual(source_table.get("tabindex"), "0")
        self.assertEqual(
            source_table.get("aria-describedby"), "materials-table-scroll-hint"
        )
        row_headers = [
            attrs
            for _, attrs in self.parser.elements
            if attrs.get("role") == "rowheader"
        ]
        self.assertEqual(len(row_headers), 3)

        css = (SITE_ROOT / "assets" / "site.css").read_text(encoding="utf-8")
        focus_cue = _css_declarations(css, ".source-table:focus-visible")
        self.assertEqual(focus_cue.get("outline"), "3px solid var(--ink)")
        self.assertEqual(focus_cue.get("outline-offset"), "4px")
        self.assertEqual(
            _css_declarations(css, ".practice-flip-prompt small").get("color"),
            "#414a45",
        )
        faq_link = _css_declarations(css, ".faq-list details p a")
        self.assertEqual(faq_link.get("text-decoration"), "underline")
        self.assertEqual(faq_link.get("text-decoration-thickness"), "1.5px")
        self.assertEqual(faq_link.get("text-underline-offset"), "3px")

        phone = _css_block(css, "@media (max-width: 560px)")
        mobile_source_head = _css_declarations(phone, ".source-head")
        self.assertEqual(mobile_source_head.get("position"), "absolute")
        self.assertEqual(mobile_source_head.get("clip-path"), "inset(50%)")
        self.assertNotEqual(mobile_source_head.get("display"), "none")

        guide_css = (SITE_ROOT / "assets" / "guide.css").read_text(
            encoding="utf-8"
        )
        scope_link = _css_declarations(guide_css, ".guide-scope-note a")
        self.assertEqual(scope_link.get("color"), "var(--lime)")
        self.assertEqual(scope_link.get("text-decoration"), "underline")
        self.assertEqual(scope_link.get("text-underline-offset"), "3px")
        guide_phone = _css_block(guide_css, "@media (max-width: 640px)")
        mobile_import_head = _css_declarations(
            guide_phone, ".guide-import-option-head"
        )
        self.assertEqual(mobile_import_head.get("position"), "absolute")
        self.assertEqual(mobile_import_head.get("clip-path"), "inset(50%)")
        self.assertNotEqual(mobile_import_head.get("display"), "none")

    def test_public_sample_note_breaks_only_between_sentences(self) -> None:
        expected = (
            '<p class="public-sample-note reveal">'
            "<span>아래 이미지는 카드 기능을 설명하기 위한 고정 샘플 "
            "렌더입니다.</span>"
            "<span>현재 빌드의 개별 뜻·예문 수·학습 우선순위는 샘플과 "
            "달라질 수 있습니다.</span></p>"
        )
        self.assertIn(expected, self.html)

        css = (SITE_ROOT / "assets" / "site.css").read_text(encoding="utf-8")
        note = _css_declarations(css, ".public-sample-note")
        self.assertEqual(note.get("max-width"), "none")
        self.assertEqual(note.get("word-break"), "keep-all")
        self.assertEqual(
            _css_declarations(css, ".public-sample-note span").get("display"),
            "block",
        )

    def test_support_samples_keep_card_details_readable(self) -> None:
        css = (SITE_ROOT / "assets" / "site.css").read_text(encoding="utf-8")

        full_size_links = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "a" and "mini-card-crop" in attrs.get("class", "").split()
        ]
        self.assertEqual(
            [attrs.get("href") for attrs in full_size_links],
            [
                "assets/card-hontou-usage.webp",
                "assets/card-itoguchi-formation.webp",
                "assets/card-heiki-register.webp",
            ],
        )
        for attrs in full_size_links:
            self.assertEqual(attrs.get("target"), "_blank")
            self.assertIn("원본 크기", attrs.get("aria-label", ""))

        grid = _css_declarations(css, ".support-card-grid")
        self.assertEqual(grid.get("grid-template-columns"), "1fr")

        sample = _css_declarations(css, ".mini-card-sample")
        self.assertEqual(
            sample.get("grid-template-columns"),
            "minmax(0, 1fr) minmax(520px, 640px)",
        )
        crop = _css_declarations(css, ".mini-card-crop")
        self.assertEqual(crop.get("width"), "100%")
        self.assertEqual(crop.get("max-width"), "640px")

        tablet = _css_block(css, "@media (max-width: 1050px)")
        responsive_sample = _css_declarations(tablet, ".mini-card-sample")
        self.assertEqual(
            responsive_sample.get("grid-template-columns"),
            "1fr",
        )
        self.assertEqual(responsive_sample.get("gap"), "0")
        responsive_width = _css_declarations(
            tablet, ".mini-card-sample,\n  .support-register-sample"
        )
        self.assertEqual(responsive_width.get("width"), "min(100%, 666px)")

    def test_audio_controls_are_bound_to_local_lazy_media(self) -> None:
        audios = {
            attrs["id"]: attrs
            for tag, attrs in self.parser.elements
            if tag == "audio"
        }
        buttons = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "button" and "data-audio" in attrs
        ]
        self.assertEqual(len(audios), 4)
        self.assertEqual(len(buttons), 4)
        for button in buttons:
            audio_id = button["data-audio"]
            self.assertIn(audio_id, audios)
            self.assertEqual(button.get("aria-controls"), audio_id)
            self.assertEqual(button.get("aria-pressed"), "false")
            self.assertEqual(audios[audio_id].get("preload"), "none")
            self.assertTrue((SITE_ROOT / audios[audio_id]["src"]).is_file())

    def test_site_claims_match_the_verified_final_apkg(self) -> None:
        expected_snippets = (
            "노트 15,996개 · 카드 21,897개",
            "5,759<small>예문 6,305개</small>",
            "3,013<small>어휘</small>",
            "1,147<small>표시 연결 1,398개</small>",
            "199<small>어휘</small>",
            "문체·사용역</dt><dd>104",
            "핵심 용법</dt><dd>74<small>용법 76개</small>",
            "어휘(히라가나)</dt><dd>101<small>추가 카드</small>",
            "한자 노트</dt><dd>2,337<small>일상무따 1·2권 구성</small>",
            "7,850개 유형별 실전 카드",
            "한자 읽기 1,758",
            "표기 1,090",
            "단어 형성 247",
            "문맥 규정 1,624",
            "바꿔쓰기 839",
            "용법 2,077",
            "N5 수량 표현·날짜·월·요일 읽기 215개",
            "15,996 notes",
            "21,897 cards",
            "17,489 media",
        )
        for snippet in expected_snippets:
            self.assertIn(snippet, self.html)
        self.assertNotIn("1,342", self.html)
        self.assertNotIn("1,628", self.html)
        self.assertNotIn("<dd>206<small>어휘", self.html)
        self.assertNotIn("상위급수 한자 표기", self.html)
        self.assertNotIn("17,511", self.html)

    def test_build_section_commands_are_copy_paste_complete(self) -> None:
        self.assertIn(REPOSITORY_URL, self.html)
        self.assertNotIn("OWNER/REPOSITORY", self.html)
        for friendly_copy in (
            "준비됐다면 바로",
            "처음이라면 시작 가이드부터 확인하세요.",
            "터미널 여는 법:",
            "PowerShell 여는 법:",
            "복사되는 것은 한 줄뿐입니다.",
        ):
            self.assertIn(friendly_copy, self.html)
        all_site_html = "\n".join(
            page.read_text(encoding="utf-8")
            for page in sorted(SITE_ROOT.glob("*.html"))
        )
        for prelaunch_caveat in (
            "지금은 준비 중입니다",
            "GitHub remote",
            "Pages를 배포하면 저장소 주소를 자동으로",
            "현재 릴리스 후보",
            "Windows 실제 컴퓨터에서의 최종 확인",
            "Windows 검증 대기",
            "Windows 미검증",
            "현재 공개 배포 준비 상태",
            "사이트가 GitHub Pages와 첫 Release에 연결되기 전",
        ):
            self.assertNotIn(prelaunch_caveat, all_site_html)
        self.assertNotIn("macOS용 방법을 보여드리고 있습니다", self.html)
        self.assertNotIn("data-platform-status", self.html)
        self.assertIn('data-copy-command="macos-build-command"', self.html)
        self.assertIn('data-copy-command="windows-build-command"', self.html)
        self.assertIn('id="macos-build-command"', self.html)
        self.assertIn('id="windows-build-command"', self.html)
        self.assertNotIn("data-repository-command", self.html)
        self.assertEqual(
            self.html.count('<pre class="command-line" tabindex="0">'), 2
        )
        for removed_copy in (
            "노란 버튼",
            "한 줄 시작 명령 복사",
            '<details class="command-details">',
            "한 줄 명령 보기",
            'class="steps reveal"',
            'class="start-prerequisite"',
        ):
            self.assertNotIn(removed_copy, self.html)
        self.assertIn('aria-label="macOS 명령 복사">복사</button>', self.html)
        self.assertIn('aria-label="Windows 명령 복사">복사</button>', self.html)

        commands: dict[str, str] = {}
        for platform in ("macos", "windows"):
            match = re.search(
                rf'<code id="{platform}-build-command"[^>]*>(.*?)</code>',
                self.html,
                re.DOTALL,
            )
            self.assertIsNotNone(match)
            assert match is not None
            commands[platform] = html_lib.unescape(match.group(1))
            self.assertNotIn("\n", commands[platform])

        macos_command = commands["macos"]
        self.assertIn("set -o pipefail", macos_command)
        self.assertIn("curl -fsSL", macos_command)
        self.assertIn(
            f"{REPOSITORY_URL}/raw/refs/heads/main/scripts/bootstrap-public.sh",
            macos_command,
        )
        self.assertIn("| bash", macos_command)
        self.assertNotIn("bash -s --", macos_command)
        self.assertNotIn("mktemp", macos_command)
        self.assertLess(len(macos_command), 240)

        windows_command = commands["windows"]
        self.assertIn("[scriptblock]::Create", windows_command)
        self.assertIn("(irm ", windows_command)
        self.assertIn(
            f"{REPOSITORY_URL}/raw/refs/heads/main/scripts/bootstrap-public.ps1",
            windows_command,
        )
        self.assertNotIn("-RepositoryUrl", windows_command)
        self.assertNotIn("GetTempPath", windows_command)
        self.assertNotIn("iex", windows_command.lower())
        self.assertLess(len(windows_command), 240)

        for implementation_detail in (
            "JLPT-MAX-public-bundle.zip.sha256",
            "Get-FileHash",
            "osascript",
        ):
            self.assertNotIn(implementation_detail, self.html)

        shell_bootstrap = (ROOT / "scripts" / "bootstrap-public.sh").read_text(
            encoding="utf-8"
        )
        powershell_bootstrap = (
            ROOT / "scripts" / "bootstrap-public.ps1"
        ).read_text(encoding="utf-8")
        for snippet in (
            f'release_url="{REPOSITORY_URL}/releases/latest/download"',
            'if [[ $# -ne 0 ]]',
            "JLPT-MAX-public-bundle.zip.sha256",
            '[[ "$pdf_count" -ne 17 ]]',
            '"$actual_hash" != "$pin_hash"',
            'bash "$bundle_root/scripts/build-public.sh" "$pdf_root"',
            "[1/4] 먼저 PDF 17개가 든 폴더를 확인합니다.",
        ):
            self.assertIn(snippet, shell_bootstrap)
        for snippet in (
            f'$ReleaseUrl = "{REPOSITORY_URL}/releases/latest/download"',
            "param()",
            "JLPT-MAX-public-bundle.zip.sha256",
            "Get-FileHash $ZipPath -Algorithm SHA256",
            "if ($PdfCount -ne 17)",
            "-File $BuildScript -PdfRoot $PdfRoot",
            "[1/4] 먼저 PDF 17개가 든 폴더를 확인합니다.",
        ):
            self.assertIn(snippet, powershell_bootstrap)
        self.assertNotIn("repository_url", shell_bootstrap)
        self.assertNotIn("RepositoryUrl", powershell_bootstrap)

        platform_script = (SITE_ROOT / "assets" / "platform.js").read_text(
            encoding="utf-8"
        )
        for snippet in (
            "navigator.userAgentData?.platform",
            "navigator.platform || ''",
            "navigator.maxTouchPoints > 1",
            "if (/Android/i.test(userAgent)) return 'android'",
            "if (isiPad || /iPhone|iPod/i.test(userAgent)) return 'ios'",
            "panel.hidden = panel.dataset.platformPanel !== platform",
            "event.key === 'ArrowLeft'",
            "event.key === 'ArrowRight'",
            "event.key === 'Home'",
            "event.key === 'End'",
            "{ focus: true }",
            "document.documentElement.classList.add('platform-tabs-ready')",
            "document.querySelectorAll('[data-copy-command]')",
            "await copyText(command.textContent.trim())",
            "fallbackCopyText(value)",
            "document.documentElement.classList.add('copy-ready')",
        ):
            self.assertIn(snippet, platform_script)

        tabs = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "button" and attrs.get("role") == "tab"
        ]
        panels = {
            attrs["id"]: attrs
            for tag, attrs in self.parser.elements
            if tag == "article" and attrs.get("role") == "tabpanel"
        }
        self.assertEqual(
            [attrs.get("data-platform-tab") for attrs in tabs],
            ["macos", "windows"],
        )
        self.assertEqual(len(panels), 2)
        self.assertEqual(
            [attrs.get("aria-selected") for attrs in tabs], ["true", "false"]
        )
        self.assertNotIn("tabindex", tabs[0])
        self.assertEqual(tabs[1].get("tabindex"), "-1")
        for tab in tabs:
            panel = panels[tab["aria-controls"]]
            self.assertEqual(panel.get("aria-labelledby"), tab.get("id"))
            self.assertEqual(
                panel.get("data-platform-panel"), tab.get("data-platform-tab")
            )
            self.assertNotIn("hidden", panel)

        copy_buttons = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "button" and "data-copy-command" in attrs
        ]
        self.assertEqual(len(copy_buttons), 2)
        self.assertTrue(
            all(
                attrs.get("aria-controls") == attrs.get("data-copy-command")
                for attrs in copy_buttons
            )
        )
        self.assertEqual(
            {attrs.get("aria-label") for attrs in copy_buttons},
            {"macOS 명령 복사", "Windows 명령 복사"},
        )

        css = (SITE_ROOT / "assets" / "site.css").read_text(encoding="utf-8")
        self.assertEqual(_css_declarations(css, ".platform-tabs").get("display"), "none")
        self.assertEqual(
            _css_declarations(css, ".platform-tabs-ready .platform-tabs").get(
                "display"
            ),
            "inline-flex",
        )
        self.assertEqual(_css_declarations(css, ".copy-command").get("display"), "none")
        self.assertEqual(
            _css_declarations(css, ".copy-command").get("min-width"), "72px"
        )
        self.assertEqual(
            _css_declarations(css, ".copy-ready .copy-command").get("display"),
            "inline-flex",
        )
        self.assertEqual(
            _css_declarations(css, ".platform-panel[hidden]").get("display"),
            "none",
        )
        self.assertEqual(
            _css_declarations(css, ".platform-grid").get("grid-template-columns"),
            "1fr",
        )
        command_block = _css_declarations(css, ".platform-grid pre")
        self.assertEqual(command_block.get("overflow-x"), "auto")
        self.assertEqual(command_block.get("white-space"), "pre")
        phone = _css_block(css, "@media (max-width: 560px)")
        self.assertEqual(
            _css_declarations(phone, ".platform-grid article > header").get(
                "flex-direction"
            ),
            "column",
        )

    def test_pages_artifact_preserves_static_repository_links_without_javascript(
        self,
    ) -> None:
        expected_links = [
            REPOSITORY_URL,
            f"{REPOSITORY_URL}/blob/main/docs/build.md",
            f"{REPOSITORY_URL}/blob/main/docs/build.md",
            f"{REPOSITORY_URL}/blob/main/scripts/bootstrap-public.sh",
            f"{REPOSITORY_URL}/blob/main/scripts/bootstrap-public.ps1",
            f"{REPOSITORY_URL}/blob/main/docs/privacy-and-licensing.md",
            f"{REPOSITORY_URL}/blob/main/NOTICE",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "pages-site"
            PREPARE.prepare_site(SITE_ROOT, output)
            parser = _parse(output / "index.html")
            rendered = (output / "index.html").read_text(encoding="utf-8")

        linked = [
            attrs["href"]
            for tag, attrs in parser.elements
            if tag == "a" and attrs.get("href", "").startswith(REPOSITORY_URL)
        ]
        self.assertEqual(linked, expected_links)
        self.assertIn(
            f"{REPOSITORY_URL}/raw/refs/heads/main/scripts/bootstrap-public.sh",
            rendered,
        )
        self.assertIn(
            f"{REPOSITORY_URL}/raw/refs/heads/main/scripts/bootstrap-public.ps1",
            rendered,
        )
        for removed_hook in (
            "OWNER/REPOSITORY",
            "data-repository-path",
            "data-repository-command",
            "-RepositoryUrl",
            "document.querySelectorAll('[data-repository-path]')",
        ):
            self.assertNotIn(removed_hook, rendered)
        rendered_ctas = {
            attrs["id"]: attrs
            for tag, attrs in parser.elements
            if tag == "a"
            and attrs.get("id") in {"release-cta", "closing-release-cta"}
        }
        self.assertEqual(set(rendered_ctas), {"release-cta", "closing-release-cta"})
        self.assertEqual(rendered_ctas["release-cta"].get("href"), "getting-started.html")
        self.assertEqual(
            rendered_ctas["closing-release-cta"].get("href"), "#build-commands"
        )

    def test_hero_cta_opens_the_guide_and_closing_cta_jumps_to_build(self) -> None:
        ctas = {
            attrs["id"]: attrs
            for tag, attrs in self.parser.elements
            if tag == "a"
            and attrs.get("id") in {"release-cta", "closing-release-cta"}
        }
        self.assertEqual(set(ctas), {"release-cta", "closing-release-cta"})
        self.assertEqual(ctas["release-cta"].get("href"), "getting-started.html")
        self.assertEqual(ctas["closing-release-cta"].get("href"), "#build-commands")
        for attrs in ctas.values():
            self.assertNotIn("data-repository-path", attrs)

    def test_pages_preparation_rejects_unsafe_source_and_output_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            missing_source = temp_root / "missing-source"
            missing_source_output = temp_root / "missing-source-output"
            with self.assertRaises(PREPARE.SitePreparationError):
                PREPARE.prepare_site(missing_source, missing_source_output)
            self.assertFalse(missing_source_output.exists())

            incomplete_source = temp_root / "incomplete-source"
            incomplete_source.mkdir()
            (incomplete_source / "index.html").write_text(
                '<link rel="stylesheet" href="assets/missing.css">',
                encoding="utf-8",
            )
            incomplete_output = temp_root / "incomplete-output"
            with self.assertRaises(PREPARE.SitePreparationError):
                PREPARE.prepare_site(incomplete_source, incomplete_output)
            self.assertFalse(incomplete_output.exists())

            existing_output = temp_root / "existing-output"
            existing_output.mkdir()
            sentinel = existing_output / "sentinel.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            with self.assertRaises(PREPARE.SitePreparationError):
                PREPARE.prepare_site(SITE_ROOT, existing_output)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")

            nested_source = temp_root / "nested-source"
            nested_source.mkdir()
            (nested_source / "index.html").write_text(
                "<!doctype html><title>safe source</title>",
                encoding="utf-8",
            )
            nested_output = nested_source / "build" / "site"
            with self.assertRaises(PREPARE.SitePreparationError):
                PREPARE.prepare_site(nested_source, nested_output)
            self.assertFalse(nested_output.exists())

    def test_skip_target_and_repository_links_are_static(self) -> None:
        main = next(
            attrs
            for tag, attrs in self.parser.elements
            if tag == "main" and attrs.get("id") == "main"
        )
        self.assertEqual(main.get("tabindex"), "-1")
        for page in sorted(SITE_ROOT.glob("*.html")):
            html = page.read_text(encoding="utf-8")
            self.assertIn(REPOSITORY_URL, html, page.name)
            for removed_hook in (
                "OWNER/REPOSITORY",
                "data-repository-path",
                "data-repository-command",
                "document.querySelectorAll('[data-repository-path]')",
                "document.querySelectorAll('[data-repository-command]')",
            ):
                self.assertNotIn(removed_hook, html, page.name)

    def test_brand_lockups_and_favicon_surface_max(self) -> None:
        self.assertEqual(
            self.html.count(
                '<span class="brand-mark" aria-hidden="true"><span class="brand-mark-jlpt">JLPT</span><strong class="brand-mark-max">MAX</strong></span>'
            ),
            2,
        )
        self.assertEqual(
            self.html.count(
                '<span class="brand-wordmark">JLPT <b>MAX</b> Deck</span>'
            ),
            2,
        )
        self.assertIn(
            'class="brand footer-brand" role="img" aria-label="JLPT MAX Deck"',
            self.html,
        )

        favicon = (SITE_ROOT / "assets" / "favicon.svg").read_text(encoding="utf-8")
        self.assertIn(">MAX</text>", favicon)
        self.assertNotIn(">日</text>", favicon)

    def test_feature_introduction_surfaces_audio_and_kanji(self) -> None:
        expected_snippets = (
            "자연스러운 일본어 음성",
            'AivisSpeech 1.2.0의 <span lang="ja">まい</span>(마이) 모델',
            "모든 5,800개 단어와 6,305개 검토 예문",
            "음성만 듣는 복습 카드",
            "단어 속 한자까지 함께",
            "한국어 학습 뜻과 읽기, 부수·획수",
            "별도 한자 덱은 『일본어 상용한자 무작정 따라하기』(일상무따) 1·2권 구성",
            "일상무따 1·2권 구성의 한자 정보",
        )
        for snippet in expected_snippets:
            self.assertIn(snippet, self.html)


class SiteSeoContractTest(unittest.TestCase):
    def _single_meta(
        self,
        parser: _SiteParser,
        attribute: str,
        value: str,
    ) -> str:
        matches = [
            attrs.get("content", "")
            for tag, attrs in parser.elements
            if tag == "meta" and attrs.get(attribute) == value
        ]
        self.assertEqual(len(matches), 1, f"meta {attribute}={value}")
        self.assertTrue(matches[0], f"empty meta {attribute}={value}")
        return matches[0]

    def _canonical(self, parser: _SiteParser) -> str:
        canonicals = [
            attrs.get("href", "")
            for tag, attrs in parser.elements
            if tag == "link" and attrs.get("rel") == "canonical"
        ]
        self.assertEqual(len(canonicals), 1)
        return canonicals[0]

    def _sitemap_locations(self, path: Path) -> list[str]:
        namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        root = ET.parse(path).getroot()
        self.assertEqual(
            root.tag, "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"
        )
        return [
            element.text or ""
            for element in root.findall("sitemap:url/sitemap:loc", namespace)
        ]

    def test_indexable_pages_have_complete_unique_social_metadata_and_json_ld(
        self,
    ) -> None:
        canonical_urls: list[str] = []
        open_graph_urls: list[str] = []
        expected_image = f"{SITE_URL}/assets/social-card.jpg"
        expected_types = {
            "index.html": "website",
            "getting-started.html": "article",
            "install-anki.html": "article",
        }

        for page_name, expected_url in INDEXABLE_PAGE_URLS.items():
            with self.subTest(page=page_name):
                page = SITE_ROOT / page_name
                parser = _parse(page)
                self.assertEqual(
                    self._single_meta(parser, "name", "robots"),
                    "index,follow",
                )
                self.assertTrue(
                    self._single_meta(parser, "name", "description")
                )

                canonical = self._canonical(parser)
                open_graph_url = self._single_meta(parser, "property", "og:url")
                self.assertEqual(canonical, expected_url)
                self.assertEqual(open_graph_url, expected_url)
                self.assertEqual(urlsplit(canonical).scheme, "https")
                canonical_urls.append(canonical)
                open_graph_urls.append(open_graph_url)

                self.assertEqual(
                    self._single_meta(parser, "property", "og:type"),
                    expected_types[page_name],
                )
                self.assertEqual(
                    self._single_meta(parser, "property", "og:locale"),
                    "ko_KR",
                )
                self.assertEqual(
                    self._single_meta(parser, "property", "og:site_name"),
                    "JLPT MAX Deck",
                )
                open_graph_title = self._single_meta(
                    parser, "property", "og:title"
                )
                self.assertTrue(
                    self._single_meta(parser, "property", "og:description")
                )
                self.assertEqual(
                    self._single_meta(parser, "property", "og:image"),
                    expected_image,
                )
                self.assertEqual(
                    self._single_meta(parser, "property", "og:image:type"),
                    "image/jpeg",
                )
                self.assertEqual(
                    self._single_meta(parser, "property", "og:image:width"),
                    "1200",
                )
                self.assertEqual(
                    self._single_meta(parser, "property", "og:image:height"),
                    "630",
                )
                image_alt = self._single_meta(
                    parser, "property", "og:image:alt"
                )

                self.assertEqual(
                    self._single_meta(parser, "name", "twitter:card"),
                    "summary_large_image",
                )
                self.assertEqual(
                    self._single_meta(parser, "name", "twitter:title"),
                    open_graph_title,
                )
                self.assertTrue(
                    self._single_meta(parser, "name", "twitter:description")
                )
                self.assertEqual(
                    self._single_meta(parser, "name", "twitter:image"),
                    expected_image,
                )
                self.assertEqual(
                    self._single_meta(parser, "name", "twitter:image:alt"),
                    image_alt,
                )

                documents = _json_ld_documents(page)
                self.assertEqual(len(documents), 1)
                document = documents[0]
                self.assertIsInstance(document, dict)
                assert isinstance(document, dict)
                self.assertEqual(document.get("@context"), "https://schema.org")
                json_strings = _json_strings(document)
                self.assertIn(expected_url, json_strings)
                self.assertIn("ko-KR", json_strings)

        self.assertEqual(len(canonical_urls), len(set(canonical_urls)))
        self.assertEqual(len(open_graph_urls), len(set(open_graph_urls)))
        self.assertEqual(canonical_urls, open_graph_urls)
        self.assertEqual(
            _jpeg_dimensions(SITE_ROOT / "assets" / "social-card.jpg"),
            (1200, 630),
        )

    def test_404_is_noindex_and_discovery_files_list_only_indexable_pages(
        self,
    ) -> None:
        parser = _parse(SITE_ROOT / "404.html")
        self.assertEqual(
            self._single_meta(parser, "name", "robots"), "noindex,follow"
        )
        self.assertEqual(
            [
                attrs
                for tag, attrs in parser.elements
                if tag == "link" and attrs.get("rel") == "canonical"
            ],
            [],
        )
        expected_404_hrefs = {
            "#main",
            f"{SITE_URL}/",
            f"{SITE_URL}/#cards",
            f"{SITE_URL}/#kanji",
            f"{SITE_URL}/#practice",
            f"{SITE_URL}/#reference",
            f"{SITE_URL}/#start",
            f"{SITE_URL}/getting-started.html",
            f"{SITE_URL}/install-anki.html",
            REPOSITORY_URL,
        }
        actual_404_hrefs = {
            attrs["href"]
            for tag, attrs in parser.elements
            if tag == "a" and attrs.get("href")
        }
        self.assertEqual(actual_404_hrefs, expected_404_hrefs)
        for tag, attrs in parser.elements:
            if tag != "link":
                continue
            parsed_asset = urlsplit(attrs.get("href", ""))
            self.assertEqual(parsed_asset.scheme, "https")
            self.assertEqual(parsed_asset.netloc, "truthyblue.github.io")
            self.assertTrue(
                parsed_asset.path.startswith("/jlpt-max-deck/assets/"),
                attrs.get("href"),
            )
        self.assertEqual(
            [
                attrs
                for tag, attrs in parser.elements
                if tag == "meta" and attrs.get("property") == "og:url"
            ],
            [],
        )

        robots = (SITE_ROOT / "robots.txt").read_text(encoding="utf-8")
        self.assertEqual(
            robots.splitlines(),
            [
                "User-agent: *",
                "Allow: /",
                "",
                f"Sitemap: {SITE_URL}/sitemap.xml",
            ],
        )
        sitemap_locations = self._sitemap_locations(SITE_ROOT / "sitemap.xml")
        self.assertEqual(sitemap_locations, list(INDEXABLE_PAGE_URLS.values()))
        self.assertNotIn("404.html", "\n".join(sitemap_locations))

    def test_prepared_artifact_preserves_static_site_urls_and_fingerprints_assets(
        self,
    ) -> None:
        social_asset = SITE_ROOT / "assets" / "social-card.jpg"
        social_version = hashlib.sha256(social_asset.read_bytes()).hexdigest()[:12]
        expected_social_image = (
            f"{SITE_URL}/assets/social-card.jpg?v={social_version}"
        )

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "pages-site"
            PREPARE.prepare_site(SITE_ROOT, output)

            for path in [
                *sorted(output.glob("*.html")),
                output / "robots.txt",
                output / "sitemap.xml",
            ]:
                rendered = path.read_text(encoding="utf-8")
                self.assertNotIn("OWNER/REPOSITORY", rendered, path.name)
                self.assertNotIn("OWNER.github.io", rendered, path.name)

            fingerprinted_references = 0
            for page_name, expected_url in INDEXABLE_PAGE_URLS.items():
                page = output / page_name
                parser = _parse(page)
                self.assertEqual(self._canonical(parser), expected_url)
                self.assertEqual(
                    self._single_meta(parser, "property", "og:url"),
                    expected_url,
                )
                self.assertEqual(
                    self._single_meta(parser, "property", "og:image"),
                    expected_social_image,
                )
                self.assertEqual(
                    self._single_meta(parser, "name", "twitter:image"),
                    expected_social_image,
                )

                documents = _json_ld_documents(page)
                self.assertEqual(len(documents), 1)
                json_strings = _json_strings(documents[0])
                self.assertIn(expected_url, json_strings)
                self.assertFalse(
                    any("OWNER" in value for value in json_strings),
                    page_name,
                )

            for page in sorted(output.glob("*.html")):
                for _, attrs in _parse(page).elements:
                    for attribute in ("href", "src"):
                        reference = attrs.get(attribute, "")
                        parsed = urlsplit(reference)
                        if parsed.scheme or parsed.netloc:
                            if (
                                parsed.scheme != "https"
                                or parsed.netloc != "truthyblue.github.io"
                                or not parsed.path.startswith(
                                    "/jlpt-max-deck/assets/"
                                )
                            ):
                                continue
                            relative_asset_path = parsed.path.removeprefix(
                                "/jlpt-max-deck/"
                            )
                        else:
                            relative_asset_path = parsed.path
                        if not relative_asset_path.startswith("assets/"):
                            continue
                        source_asset = SITE_ROOT / relative_asset_path
                        self.assertTrue(source_asset.is_file(), reference)
                        expected_version = hashlib.sha256(
                            source_asset.read_bytes()
                        ).hexdigest()[:12]
                        self.assertEqual(
                            parse_qs(parsed.query),
                            {"v": [expected_version]},
                            f"{page.name}: {reference}",
                        )
                        fingerprinted_references += 1

            self.assertGreater(fingerprinted_references, 30)
            self.assertEqual(
                (output / "robots.txt").read_text(encoding="utf-8").splitlines(),
                [
                    "User-agent: *",
                    "Allow: /",
                    "",
                    f"Sitemap: {SITE_URL}/sitemap.xml",
                ],
            )
            self.assertEqual(
                self._sitemap_locations(output / "sitemap.xml"),
                list(INDEXABLE_PAGE_URLS.values()),
            )


class BeginnerGuideContractTest(unittest.TestCase):
    GUIDE_NAMES = ("getting-started.html", "install-anki.html")

    def _primary_nav_items(
        self, page_name: str
    ) -> list[tuple[dict[str, str], str, str]]:
        html = (SITE_ROOT / page_name).read_text(encoding="utf-8")
        nav_match = re.search(
            r'<nav\s+aria-label="주요 메뉴">(.*?)</nav>',
            html,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(nav_match, page_name)
        assert nav_match is not None

        items: list[tuple[dict[str, str], str, str]] = []
        for attributes, body in re.findall(
            r"<a\b([^>]*)>(.*?)</a>", nav_match.group(1), flags=re.DOTALL
        ):
            parser = _SiteParser()
            parser.feed(f"<a{attributes}></a>")
            link_attributes = parser.elements[0][1]
            full_label = re.search(
                r'<span\s+class="nav-label-full">(.*?)</span>',
                body,
                flags=re.DOTALL,
            )
            compact_label = re.search(
                r'<span\s+class="nav-label-compact">(.*?)</span>',
                body,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(full_label, f"{page_name}: {body}")
            self.assertIsNotNone(compact_label, f"{page_name}: {body}")
            assert full_label is not None and compact_label is not None
            items.append(
                (
                    link_attributes,
                    html_lib.unescape(full_label.group(1)).strip(),
                    html_lib.unescape(compact_label.group(1)).strip(),
                )
            )
        return items

    def _page_ids(self, path: Path) -> set[str]:
        return {
            attrs["id"]
            for _, attrs in _parse(path).elements
            if attrs.get("id")
        }

    def _assert_platform_switcher(
        self,
        page_name: str,
        id_prefix: str,
        expected_platforms: list[str],
    ) -> None:
        parser = _parse(SITE_ROOT / page_name)
        tabs = [
            attrs
            for tag, attrs in parser.elements
            if tag == "button"
            and attrs.get("role") == "tab"
            and attrs.get("id", "").startswith(id_prefix)
        ]
        panels = {
            attrs["id"]: attrs
            for tag, attrs in parser.elements
            if tag == "article"
            and attrs.get("role") == "tabpanel"
            and attrs.get("id", "").startswith(id_prefix)
        }

        self.assertEqual(
            [tab.get("data-platform-tab") for tab in tabs],
            expected_platforms,
            f"{page_name}: {id_prefix}",
        )
        self.assertEqual(len(panels), len(expected_platforms))
        self.assertEqual(
            [tab.get("aria-selected") for tab in tabs],
            ["true", *["false"] * (len(tabs) - 1)],
        )
        for index, tab in enumerate(tabs):
            self.assertEqual(tab.get("tabindex"), None if index == 0 else "-1")
            panel = panels[tab["aria-controls"]]
            self.assertEqual(panel.get("aria-labelledby"), tab.get("id"))
            self.assertEqual(
                panel.get("data-platform-panel"),
                tab.get("data-platform-tab"),
            )
            self.assertNotIn("hidden", panel)

    def _assert_local_contracts(self, site_root: Path) -> None:
        resolved_site_root = site_root.resolve()
        for page in sorted(site_root.glob("*.html")):
            parser = _parse(page)
            ids = [
                attrs["id"]
                for _, attrs in parser.elements
                if attrs.get("id")
            ]
            self.assertEqual(
                len(ids),
                len(set(ids)),
                f"duplicate id in {page.name}",
            )
            for tag, attrs in parser.elements:
                controls = attrs.get("aria-controls")
                if controls:
                    self.assertIn(
                        controls,
                        ids,
                        f"{page.name}: aria-controls={controls}",
                    )

                href = attrs.get("href", "")
                if tag == "a" and href.startswith("#"):
                    self.assertIn(
                        urlsplit(href).fragment,
                        ids,
                        f"{page.name}: {href}",
                    )

                local_reference = ""
                if tag in {"img", "audio", "script"}:
                    local_reference = attrs.get("src", "")
                elif tag == "link":
                    local_reference = href
                elif (
                    tag == "a"
                    and href
                    and not urlsplit(href).scheme
                    and not href.startswith("#")
                ):
                    local_reference = href
                if not local_reference:
                    continue

                parsed = urlsplit(local_reference)
                if parsed.scheme or parsed.netloc:
                    continue
                relative_path = parsed.path
                target = (
                    (page.parent / relative_path).resolve()
                    if relative_path
                    else page.resolve()
                )
                self.assertTrue(
                    target.is_file(),
                    f"{page.name}: {local_reference}",
                )
                if site_root != SITE_ROOT:
                    self.assertTrue(
                        target == resolved_site_root
                        or resolved_site_root in target.parents,
                        f"prepared link escapes site: {page.name}: {local_reference}",
                    )
                if parsed.fragment and target.suffix.lower() == ".html":
                    self.assertIn(
                        parsed.fragment,
                        self._page_ids(target),
                        f"{page.name}: {local_reference}",
                    )

    def test_beginner_guides_are_linked_and_cross_navigate(self) -> None:
        index = (SITE_ROOT / "index.html").read_text(encoding="utf-8")
        getting_started = (SITE_ROOT / "getting-started.html").read_text(
            encoding="utf-8"
        )
        install = (SITE_ROOT / "install-anki.html").read_text(encoding="utf-8")

        for snippet in (
            '<a href="getting-started.html" aria-label="시작 가이드">',
            '<a href="install-anki.html" aria-label="Anki 설치">',
            'id="beginner-guide-link" href="getting-started.html"',
            'id="anki-install-guide-link" href="install-anki.html"',
            'href="getting-started.html#result"',
            "Anki가 처음이라면 설치부터",
        ):
            self.assertIn(snippet, index)

        self.assertIn('href="install-anki.html"', getting_started)
        self.assertIn('href="getting-started.html"', install)
        self.assertIn('href="index.html"', getting_started)
        self.assertIn('href="index.html"', install)
        self.assertNotIn("macOS용 방법을 보여드리고 있습니다", index)
        self.assertNotIn("data-platform-status", index)

    def test_getting_started_branches_without_duplicate_progress_bar(self) -> None:
        html = (SITE_ROOT / "getting-started.html").read_text(encoding="utf-8")
        for snippet in (
            "Anki가 있으면 PDF 준비부터, 아직 없으면 설치부터 시작하세요.",
            '<a class="button button-primary" href="#materials">Anki 있음 · PDF 준비부터',
            '<a class="button button-quiet" href="install-anki.html">Anki 없음 · 설치부터',
            "완성 APKG는 약 840MB",
            "8GB 이상의 여유 저장 공간을 권장합니다.",
            "빌드 컴퓨터의 여유 저장 공간 8GB 이상 권장",
            "로그인과 구매 도서 인증이 필요할 수 있습니다.",
            "iPhone·iPad용 공식 AnkiMobile은 유료",
            f'href="{REPOSITORY_URL}/blob/main/docs/troubleshooting.md"',
            "문제 해결 안내",
        ):
            self.assertIn(snippet, html)
        self.assertNotIn("guide-flow-core", html)
        self.assertNotIn('aria-label="핵심 시작 순서"', html)

        install_html = (SITE_ROOT / "install-anki.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('class="guide-lead"'), 1)
        self.assertEqual(install_html.count('class="guide-lead"'), 1)
        guide_css = (SITE_ROOT / "assets" / "guide.css").read_text(encoding="utf-8")
        self.assertEqual(
            _css_declarations(guide_css, ".guide-lead").get("min-height"),
            "3.4em",
        )

    def test_all_pages_share_the_same_primary_navigation_contract(self) -> None:
        expected_full_labels = [
            "어휘 카드",
            "한자 카드",
            "실전 문제",
            "참조표",
            "빌드",
            "시작 가이드",
            "Anki 설치",
        ]
        expected_compact_labels = [
            "어휘",
            "한자",
            "문제",
            "참조",
            "빌드",
            "가이드",
            "설치",
        ]
        expected_index_hrefs = [
            "#cards",
            "#kanji",
            "#practice",
            "#reference",
            "#start",
            "getting-started.html",
            "install-anki.html",
        ]
        expected_guide_hrefs = [
            "index.html#cards",
            "index.html#kanji",
            "index.html#practice",
            "index.html#reference",
            "index.html#start",
            "getting-started.html",
            "install-anki.html",
        ]
        current_pages = {
            "index.html": None,
            "getting-started.html": "getting-started.html",
            "install-anki.html": "install-anki.html",
        }

        for page_name, current_href in current_pages.items():
            with self.subTest(page=page_name):
                html = (SITE_ROOT / page_name).read_text(encoding="utf-8")
                self.assertIn(
                    '<a class="brand" href="index.html" '
                    'aria-label="JLPT MAX Deck 홈">',
                    html,
                )
                self.assertNotIn('href="#top"', html)
                self.assertNotIn('href="index.html#top"', html)
                nav_match = re.search(
                    r'<nav\s+aria-label="주요 메뉴">(.*?)</nav>',
                    html,
                    flags=re.DOTALL,
                )
                self.assertIsNotNone(nav_match)
                assert nav_match is not None
                groups = re.findall(
                    r'<div class="nav-group ([^"]+)" role="group" '
                    r'aria-label="([^"]+)">(.*?)</div>',
                    nav_match.group(1),
                    flags=re.DOTALL,
                )
                self.assertEqual(
                    [(class_name, label) for class_name, label, _ in groups],
                    [
                        ("nav-section-links", "덱 소개 섹션"),
                        ("nav-guide-links", "별도 가이드"),
                    ],
                )
                self.assertEqual(
                    [group_html.count("<a ") for _, _, group_html in groups],
                    [5, 2],
                )

                items = self._primary_nav_items(page_name)
                self.assertEqual(
                    [full_label for _, full_label, _ in items],
                    expected_full_labels,
                )
                self.assertEqual(
                    [compact_label for _, _, compact_label in items],
                    expected_compact_labels,
                )
                self.assertEqual(
                    [attrs.get("aria-label") for attrs, _, _ in items],
                    expected_full_labels,
                )
                self.assertEqual(
                    [attrs.get("href") for attrs, _, _ in items],
                    (
                        expected_index_hrefs
                        if page_name == "index.html"
                        else expected_guide_hrefs
                    ),
                )
                self.assertEqual(
                    [
                        attrs.get("href")
                        for attrs, _, _ in items
                        if attrs.get("aria-current") == "page"
                    ],
                    [] if current_href is None else [current_href],
                )

                repo_links = [
                    attrs
                    for tag, attrs in _parse(SITE_ROOT / page_name).elements
                    if tag == "a" and attrs.get("id") == "repo-link"
                ]
                self.assertEqual(len(repo_links), 1)
                repo_link = repo_links[0]
                self.assertIn("nav-action", repo_link.get("class", "").split())
                self.assertEqual(repo_link.get("href"), REPOSITORY_URL)
                self.assertNotIn("data-repository-path", repo_link)
                self.assertEqual(repo_link.get("target"), "_blank")
                self.assertEqual(repo_link.get("rel"), "noopener noreferrer")
                self.assertEqual(
                    repo_link.get("aria-label"), "GitHub 저장소, 새 탭에서 열림"
                )
                page_html = (SITE_ROOT / page_name).read_text(encoding="utf-8")
                self.assertIn('class="nav-action-icon"', page_html)
                self.assertIn(
                    '<span class="nav-action-label">GitHub</span>', page_html
                )
                self.assertIn(
                    '<span class="nav-action-arrow" aria-hidden="true">↗</span>',
                    page_html,
                )
                self.assertNotIn("소스 보기", page_html)

    def test_all_site_pages_close_ids_controls_and_local_references(self) -> None:
        self.assertEqual(
            {path.name for path in SITE_ROOT.glob("*.html")},
            {"404.html", "index.html", *self.GUIDE_NAMES},
        )
        self._assert_local_contracts(SITE_ROOT)

    def test_build_result_guide_matches_output_and_device_contracts(self) -> None:
        html = (SITE_ROOT / "getting-started.html").read_text(encoding="utf-8")
        for snippet in (
            "public-release/",
            "JLPT-MAX덱-1.0.0.apkg",
            "public-build-report.json",
            "public-materialization-report.json",
            "source-proof.json",
            "Anki에는 APKG만 가져옵니다.",
            "macOS 또는 Windows x64",
            "iPhone · iPad",
            "Android",
            "AnkiMobile",
            "AnkiDroid",
            "JLPT MAX덱",
            "미디어 17,489개",
            "AnkiWeb 무료 가입",
            "업로드(Upload)",
            "다운로드(Download)",
            "첫 미디어 동기화",
            "로그인만 하고 끝내지 말고 동기화 버튼도 눌러 주세요.",
        ):
            self.assertIn(snippet, html)
        self.assertIn("공유 가능한 파일·공개 링크·일반 클라우드", html)
        self.assertIn("판매, 미러링", html)
        self.assertIn("외부에 올리거나", html)
        self.assertNotIn("기기별 학습 기록은 따로", html)
        self.assertNotIn("계정도 필요하지 않습니다", html)

    def test_getting_started_includes_complete_pdf_download_instructions(
        self,
    ) -> None:
        html = (SITE_ROOT / "getting-started.html").read_text(encoding="utf-8")
        before_match = re.search(
            r'<section\s+class="guide-section"\s+id="before">(.*?)</section>',
            html,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(before_match)
        assert before_match is not None
        self.assertIn("세 가지만 준비하면 됩니다.", before_match.group(1))
        self.assertNotIn(
            "한 폴더에 모은 정확한 PDF 17개",
            before_match.group(1),
        )

        section_match = re.search(
            r'<section\s+class="guide-section"\s+id="materials">(.*?)</section>',
            html,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(section_match)
        assert section_match is not None
        materials = section_match.group(1)
        parser = _SiteParser()
        parser.feed(materials)

        expected_links = [
            (
                "해커스 N1 공식 자료, 새 탭에서 열림",
                "https://japan.hackers.com/?r=japan&m=mp3&c=mp3%2Fmp3_free&p=1&book_cd=863",
            ),
            (
                "해커스 N2 공식 자료, 새 탭에서 열림",
                "https://japan.hackers.com/?r=japan&m=mp3&c=mp3%2Fmp3_free&p=1&book_cd=1356",
            ),
            (
                "해커스 N3 공식 자료, 새 탭에서 열림",
                "https://japan.hackers.com/?r=japan&m=mp3&c=mp3%2Fmp3_free&p=1&book_cd=1337",
            ),
            (
                "해커스 N4 공식 자료, 새 탭에서 열림",
                "https://japan.hackers.com/?r=japan&m=mp3&c=mp3%2Fmp3_free&p=1&book_cd=311",
            ),
            (
                "해커스 N5 공식 자료, 새 탭에서 열림",
                "https://japan.hackers.com/?r=japan&m=mp3&c=mp3%2Fmp3_free&p=1&cate4_cd=&lec_lvl_cd=&book_cd=415",
            ),
            (
                "동양북스 N1, 새 탭에서 열림",
                "https://www.dongyangbooks.com/book/book_view.asp?goods_code=2968&menu_1=jp&menu_2=jp_JLPT",
            ),
            (
                "동양북스 N2, 새 탭에서 열림",
                "https://www.dongyangbooks.com/book/book_view.asp?goods_code=2969&menu_1=jp&menu_2=jp_JLPT",
            ),
            (
                "동양북스 N3, 새 탭에서 열림",
                "https://www.dongyangbooks.com/book/book_view.asp?goods_code=2970&menu_1=jp&menu_2=jp_JLPT",
            ),
            (
                "동양북스 N4, 새 탭에서 열림",
                "https://www.dongyangbooks.com/reference/reference_010100-view.asp?bidx=11&bsno=44978",
            ),
            (
                "동양북스 N5, 새 탭에서 열림",
                "https://www.dongyangbooks.com/reference/reference_010100-view.asp?bidx=11&bsno=44979",
            ),
            (
                "길벗 1권, 새 탭에서 열림",
                "https://www.gilbut.co.kr/book/view?bookcode=BN003617",
            ),
            (
                "길벗 2권, 새 탭에서 열림",
                "https://www.gilbut.co.kr/book/view?bookcode=BN003669",
            ),
        ]
        actual_links = [
            (attrs.get("aria-label"), attrs.get("href"))
            for tag, attrs in parser.elements
            if tag == "a" and attrs.get("target") == "_blank"
        ]
        self.assertEqual(actual_links, expected_links)
        index_hackers_links = [
            (attrs.get("aria-label"), attrs.get("href"))
            for tag, attrs in _parse(SITE_ROOT / "index.html").elements
            if tag == "a"
            and attrs.get("aria-label", "").startswith("해커스 N")
        ]
        self.assertEqual(index_hackers_links, expected_links[:5])
        self.assertEqual(
            re.findall(
                r'<b\s+role="cell">\s*<span>\s*(\d+)개\s*</span>',
                materials,
            ),
            ["10", "5", "2"],
        )
        for snippet in (
            "해커스 자료는 로그인 후 N1~N5 각 교재를 보유한 상태에서 구매 도서 인증을 완료해야 내려받을 수 있습니다.",
            "이 프로젝트는 인증에 필요한 정보를 제공하거나 인증 절차를 대신하지 않습니다.",
            "전체 합계는 17개·지원 판본 기준 785쪽",
            "비어 있는 새 폴더",
            "모두 같은 전용 폴더 아래에 넣습니다.",
            "PDF를 다시 저장하거나 합치지 않습니다.",
            "재저장·병합·최적화하면 검증값이 바뀌어",
            "지원하지 않는 PDF가 함께 있으면",
        ):
            self.assertIn(snippet, materials)
        self.assertIn('href="#materials"', html)

    def test_getting_started_selects_build_and_import_platforms(self) -> None:
        html = (SITE_ROOT / "getting-started.html").read_text(encoding="utf-8")
        self.assertEqual(html.count("data-platform-switcher"), 4)
        self._assert_platform_switcher(
            "getting-started.html",
            "guide-",
            ["macos", "windows"],
        )
        self._assert_platform_switcher(
            "getting-started.html",
            "import-",
            ["macos", "windows", "ios", "android"],
        )
        self._assert_platform_switcher(
            "getting-started.html",
            "settings-",
            ["macos", "windows", "ios", "android"],
        )
        self._assert_platform_switcher(
            "getting-started.html",
            "answers-",
            ["macos", "windows", "ios", "android"],
        )
        for snippet in (
            'data-copy-command="guide-macos-build-command"',
            'data-copy-command="guide-windows-build-command"',
            'id="guide-macos-build-command"',
            'id="guide-windows-build-command"',
            "접속한 기기의 가져오기 방법이 자동으로 열립니다.",
            "공부할 기기에 APKG를 직접 넣습니다.",
        ):
            self.assertIn(snippet, html)
        self.assertNotIn("data-repository-command", html)
        self.assertEqual(html.count('<pre class="command-line" tabindex="0">'), 2)
        self.assertNotIn('<details class="command-details">', html)
        self.assertNotIn("한 줄 명령 보기", html)
        self.assertNotIn("한 줄 시작 명령 복사", html)
        self.assertNotIn("노란 버튼", html)
        self.assertIn('aria-label="macOS 명령 복사">복사</button>', html)
        self.assertIn('aria-label="Windows 명령 복사">복사</button>', html)

    def test_getting_started_explains_apkg_import_options(self) -> None:
        html = (SITE_ROOT / "getting-started.html").read_text(encoding="utf-8")
        self.assertLess(html.index('id="import"'), html.index('id="import-options"'))
        self.assertLess(html.index('id="import-options"'), html.index('id="settings"'))
        for snippet in (
            "가져오기 창 설정",
            "덮어쓰기(Updates)",
            "학습 진행 상태 가져오기",
            "Import any learning progress · 복습 포함",
            "덱 사전 설정 가져오기",
            "Import any deck presets",
            "노트 타입 병합",
            "Merge note types",
            "서로 다른 덱을 한 덱으로 합치는 기능은 아닙니다.",
            "노트 업데이트",
            "Update notes",
            "노트 유형 업데이트",
            "Update note types",
            "Always",
            "Never",
            "Android에서 옵션이 보이면",
        ):
            self.assertIn(snippet, html)
        self.assertEqual(html.count('class="guide-option-state is-off"'), 1)
        self.assertEqual(html.count('class="guide-option-state is-on"'), 2)
        self.assertEqual(html.count('class="guide-option-state is-newer"'), 2)
        self.assertEqual(html.count(">If newer</span>"), 2)
        self.assertIn(
            "기존 JLPT MAX덱의 필드나 카드 모양을 직접 수정했다면 먼저 백업하세요.",
            html,
        )
        self.assertIn(
            "https://docs.ankiweb.net/importing/packaged-decks.html", html
        )

        guide_css = (SITE_ROOT / "assets" / "guide.css").read_text(
            encoding="utf-8"
        )
        options = _css_declarations(guide_css, ".guide-import-options")
        self.assertEqual(options.get("border-radius"), "22px")
        option_row = _css_declarations(guide_css, ".guide-import-option")
        self.assertIn("100px", option_row.get("grid-template-columns", ""))
        phone = _css_block(guide_css, "@media (max-width: 640px)")
        self.assertEqual(
            _css_declarations(phone, ".guide-import-option").get(
                "grid-template-columns"
            ),
            "minmax(0, 1fr) auto",
        )

    def test_getting_started_covers_beginner_fsrs_settings(self) -> None:
        html = (SITE_ROOT / "getting-started.html").read_text(encoding="utf-8")
        self.assertLess(html.index('id="import"'), html.index('id="settings"'))
        self.assertLess(html.index('id="settings"'), html.index('id="study"'))
        for snippet in (
            "톱니바퀴 → 옵션(Options)",
            "톱니바퀴 → Study Options",
            "JLPT MAX덱</strong>을 길게 누릅니다.",
            "Deck options",
            "새 카드 수는 하루 10~20개로 시작합니다.",
            "New Cards/Day",
            "FSRS를 켜고 목표 기억률은 90%로 둡니다.",
            "Desired Retention 0.90",
            "Reschedule Cards on Change",
            "처음에도 Optimize를 눌러 확인할 수 있습니다.",
            "리뷰 수와 관계없이",
            "기록이 적으면 현재 파라미터가 이미 최적이라는 안내",
            "한 달에 한 번 정도",
            "나머지 옵션은 기본값을 유지합니다.",
            "처음에는 Again과 Good만 사용해도 충분합니다.",
            "틀렸거나 기억나지 않으면 Again",
            "기억해 냈으면 Good",
            "Hard는 맞혔지만 오래 망설였을 때",
            "Easy는 거의 생각하지 않고 바로 맞혔을 때",
            "이미 아는 단어라는 이유만으로 Easy",
            "1 Again · 2 Hard · 3 Good · 4 Easy",
            "왼쪽이 Again, 오른쪽이 Good",
            "Hard와 Easy는 화면 아래의 답변 버튼",
            "Android · AnkiDroid에서 답변 버튼 사용",
            "탭과 스와이프 동작에 각 답변 버튼",
            "평가 기준에 익숙해질 때까지",
            "기억나지 않았다면 Hard가 아니라 Again",
            "오래된 Anki 앱이 섞여 있으면",
        ):
            self.assertIn(snippet, html)
        self.assertIn("https://docs.ankiweb.net/deck-options", html)
        self.assertIn("https://docs.ankimobile.net/study-tools.html", html)
        self.assertIn(
            "https://docs.ankidroid.org/manual.html#other-deck-actions",
            html,
        )
        self.assertIn("https://docs.ankimobile.net/preferences.html#taps", html)
        self.assertIn("https://docs.ankidroid.org/manual.html#gestures", html)
        self.assertIn("https://docs.ankiweb.net/studying.html#answer-buttons", html)
        self.assertIn(
            "https://faqs.ankiweb.net/frequently-asked-questions-about-fsrs.html",
            html,
        )
        self.assertNotIn("리뷰가 수백 회 쌓인 뒤", html)

    def test_home_and_guides_share_the_same_desktop_content_width(self) -> None:
        css = (SITE_ROOT / "assets" / "site.css").read_text(encoding="utf-8")
        guide_css = (SITE_ROOT / "assets" / "guide.css").read_text(
            encoding="utf-8"
        )
        gutter = "max(24px, calc((100vw - 1240px) / 2))"
        self.assertEqual(
            _css_declarations(css, ":root").get("--site"),
            "min(1240px, calc(100vw - 48px))",
        )
        self.assertIn(gutter, _css_declarations(css, ".hero").get("padding", ""))
        self.assertIn(
            gutter, _css_declarations(css, ".section").get("padding", "")
        )
        self.assertIn(
            gutter, _css_declarations(guide_css, ".guide-hero").get("padding", "")
        )
        self.assertEqual(
            _css_declarations(guide_css, ".guide-main").get("width"), "var(--site)"
        )

    def test_anki_install_guide_covers_all_supported_study_devices(self) -> None:
        html = (SITE_ROOT / "install-anki.html").read_text(encoding="utf-8")
        for snippet in (
            "https://apps.ankiweb.net/",
            "https://apps.apple.com/app/ankimobile-flashcards/id373493387",
            "https://play.google.com/store/apps/details?id=com.ichi2.anki",
            "Windows x64",
            "Windows 10+ x64 · Windows 11 ARM",
            "Windows 11 ARM이면 Windows ARM 설치 파일",
            "JLPT MAX 덱 빌더의 Windows 실행 범위는 x64 컴퓨터",
            "전체 빌드 지원 범위와 Anki 앱 자체의 지원 범위는 서로 다릅니다.",
            "macOS",
            "AnkiMobile Flashcards",
            "Anki Software, LLC",
            "AnkiDroid Flashcards",
            "AnkiDroid Open Source Team",
            "com.ichi2.anki",
            "Get started",
            "설정 → Profiles",
            "AnkiWeb",
            "macOS용 Anki 받기",
            "Windows용 Anki 받기",
            "iPhone·iPad (유료)",
            "iPhone·iPad용 공식 Anki 앱은 무료가 아닙니다.",
            "App Store에서 유료 앱 보기",
            "유료 공식 앱인 AnkiMobile",
            "Google Play에서 받기",
            "Anki 공식 지원 기기",
            "2026-07-21 기준",
        ):
            self.assertIn(snippet, html)
        self.assertNotIn("Ankitects Pty Ltd", html)
        self.assertNotIn("공식 모바일 앱", html)
        self.assertIn("AnkiApp, Anki Pro", html)
        self.assertIn('href="getting-started.html#import-options"', html)
        self.assertIn('href="getting-started.html#settings"', html)
        self.assertEqual(html.count("data-platform-switcher"), 1)
        self.assertIn('class="guide-flow guide-flow-compact"', html)
        self._assert_platform_switcher(
            "install-anki.html",
            "install-",
            ["macos", "windows", "ios", "android"],
        )

        download_links = [
            attrs
            for tag, attrs in _parse(SITE_ROOT / "install-anki.html").elements
            if tag == "a"
            and "guide-download-link" in attrs.get("class", "").split()
        ]
        self.assertEqual(
            [attrs.get("href") for attrs in download_links],
            [
                "https://apps.ankiweb.net/",
                "https://apps.ankiweb.net/",
                "https://apps.apple.com/app/ankimobile-flashcards/id373493387",
                "https://play.google.com/store/apps/details?id=com.ichi2.anki",
            ],
        )
        guide_css = (SITE_ROOT / "assets" / "guide.css").read_text(
            encoding="utf-8"
        )
        prominent_link = _css_declarations(
            guide_css, ".guide-os-card .guide-download-link"
        )
        self.assertEqual(prominent_link.get("display"), "inline-flex")
        self.assertEqual(prominent_link.get("background"), "var(--lime)")
        self.assertEqual(prominent_link.get("font-weight"), "850")

    def test_guide_stylesheet_versions_match_content_hashes(self) -> None:
        for name in self.GUIDE_NAMES:
            stylesheets = [
                attrs
                for tag, attrs in _parse(SITE_ROOT / name).elements
                if tag == "link" and attrs.get("rel") == "stylesheet"
            ]
            self.assertEqual(len(stylesheets), 2, name)
            for stylesheet in stylesheets:
                stylesheet_url = urlsplit(stylesheet["href"])
                asset = SITE_ROOT / stylesheet_url.path
                expected_version = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
                self.assertEqual(
                    parse_qs(stylesheet_url.query),
                    {"v": [expected_version]},
                    f"{name}: {stylesheet['href']}",
                )

    def test_shared_platform_script_is_versioned_and_accessible(self) -> None:
        script_path = SITE_ROOT / "assets" / "platform.js"
        script = script_path.read_text(encoding="utf-8")
        expected_version = hashlib.sha256(script_path.read_bytes()).hexdigest()[:12]
        for name in ("index.html", *self.GUIDE_NAMES):
            external_scripts = [
                attrs
                for tag, attrs in _parse(SITE_ROOT / name).elements
                if tag == "script" and attrs.get("src")
            ]
            self.assertEqual(len(external_scripts), 1, name)
            script_url = urlsplit(external_scripts[0]["src"])
            self.assertEqual(script_url.path, "assets/platform.js", name)
            self.assertEqual(
                parse_qs(script_url.query),
                {"v": [expected_version]},
                f"{name}: {external_scripts[0]['src']}",
            )

        for snippet in (
            "navigator.userAgentData?.platform",
            "navigator.platform || ''",
            "navigator.userAgent || ''",
            "navigator.maxTouchPoints > 1",
            "if (/Android/i.test(userAgent)) return 'android'",
            "if (isiPad || /iPhone|iPod/i.test(userAgent)) return 'ios'",
            "document.querySelectorAll('[data-platform-switcher]')",
            "panel.hidden = panel.dataset.platformPanel !== platform",
            "event.key === 'ArrowLeft'",
            "event.key === 'ArrowRight'",
            "event.key === 'Home'",
            "event.key === 'End'",
            "document.documentElement.classList.add('mobile-device')",
            "navigator.clipboard?.writeText",
            "window.isSecureContext",
            "document.execCommand('copy')",
            "focusedElement.focus({ preventScroll: true })",
        ):
            self.assertIn(snippet, script)

    def test_guide_external_links_have_new_tab_contracts(self) -> None:
        for name in self.GUIDE_NAMES:
            for tag, attrs in _parse(SITE_ROOT / name).elements:
                if tag != "a" or attrs.get("target") != "_blank":
                    continue
                self.assertTrue(
                    {"noopener", "noreferrer"}.issubset(
                        set(attrs.get("rel", "").split())
                    ),
                    f"{name}: {attrs.get('href')}",
                )
                self.assertIn("새 탭", attrs.get("aria-label", ""))

    def test_pages_artifact_preserves_guides_and_closes_local_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "pages-site"
            PREPARE.prepare_site(SITE_ROOT, output)
            source_inventory = {
                path.relative_to(SITE_ROOT).as_posix()
                for path in SITE_ROOT.rglob("*")
                if path.is_file()
            }
            output_inventory = {
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(output_inventory, source_inventory)
            self.assertTrue((output / ".nojekyll").is_file())
            for name in self.GUIDE_NAMES:
                rendered = (output / name).read_text(encoding="utf-8")
                self.assertNotIn("OWNER/REPOSITORY", rendered)
            rendered_guide = (output / "getting-started.html").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                f"{REPOSITORY_URL}/raw/refs/heads/main/scripts/bootstrap-public.sh",
                rendered_guide,
            )
            self.assertIn(
                f"{REPOSITORY_URL}/raw/refs/heads/main/scripts/bootstrap-public.ps1",
                rendered_guide,
            )
            self.assertNotIn("-RepositoryUrl", rendered_guide)
            self.assertNotIn("data-repository", rendered_guide)
            self._assert_local_contracts(output)


if __name__ == "__main__":
    unittest.main()
