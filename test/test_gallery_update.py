from pathlib import Path
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.render_gallery_preview import (
    GalleryPreviewError,
    render_gallery_preview,
)

UPDATE = (
    ROOT / "docs" / "jlpt-gallery-updates" / "v1.1.0.html"
).read_text(encoding="utf-8")
HOTFIX_UPDATE = (
    ROOT / "docs" / "jlpt-gallery-updates" / "v1.1.1.html"
).read_text(encoding="utf-8")
V120_UPDATE = (
    ROOT / "docs" / "jlpt-gallery-updates" / "v1.2.0.html"
).read_text(encoding="utf-8")
V200_UPDATE = (
    ROOT / "docs" / "jlpt-gallery-updates" / "v2.0.0.html"
).read_text(encoding="utf-8")
V201_UPDATE = (
    ROOT / "docs" / "jlpt-gallery-updates" / "v2.0.1.html"
).read_text(encoding="utf-8")
V202_UPDATE = (
    ROOT / "docs" / "jlpt-gallery-updates" / "v2.0.2.html"
).read_text(encoding="utf-8")
RELEASE_NOTES = (ROOT / "docs" / "releases" / "v1.1.0.md").read_text(
    encoding="utf-8"
)
V120_RELEASE_NOTES = (ROOT / "docs" / "releases" / "v1.2.0.md").read_text(
    encoding="utf-8"
)
V120_RELEASE_TEMPLATE = (
    ROOT / "docs-src" / "docs" / "releases" / "v1.2.0.md.j2"
).read_text(encoding="utf-8")
V120_RELEASE_DRAFT = (
    ROOT / "docs" / "release-drafts" / "v1.2.0-github-release.md"
).read_text(encoding="utf-8")
V120_USAGE_FOLLOWUP = (
    ROOT / "docs" / "release-drafts" / "v1.2.0-usage-details.md"
).read_text(encoding="utf-8")
SCREENSHOTS = {
    "releases/v1.1.0/gallery-v1.1.0-card-settings.webp": (390, 500),
    "releases/v1.1.0/gallery-v1.1.0-error-report.webp": (354, 644),
}
V120_SCREENSHOTS = {
    "releases/v1.2.0/gallery-v1.2.0-pitch.png": (781, 218),
    "releases/v1.2.0/gallery-v1.2.0-card-settings.png": (781, 315),
    "releases/v1.2.0/gallery-v1.2.0-context-hint.png": (780, 280),
    "releases/v1.2.0/gallery-v1.2.0-error-dialog.png": (640, 604),
    "releases/v1.2.0/gallery-v1.2.0-usage-dialog.png": (640, 604),
    "releases/v1.2.0/gallery-v1.2.0-update-notice.png": (390, 178),
    "releases/v1.2.0/gallery-v1.2.0-usage-summary.png": (2348, 1240),
}
V120_FEATURES = (
    "pitch-accent",
    "meanings-examples",
    "card-settings-fonts",
    "kanji-display-fixes",
    "vocabulary-context-hints",
    "mobile-support-dialogs",
    "update-notice-persistence",
    "new-review-mix",
)

TEST_LIFECYCLE = {
    "test_contracts": {
        "GalleryUpdateTests.test_v200_uses_tables_for_dcinside_layouts": (
            "The saved DCInside v2.0.0 gallery post keeps its two-column "
            "tables and puts every caption below its image after DCInside "
            "sanitizes styles. Existing gallery tests do not cover this post."
        ),
        "GalleryUpdateTests.test_v201_uses_tables_for_dcinside_layouts": (
            "The saved DCInside v2.0.1 gallery post keeps its two-column "
            "tables, keeps captions below images, and prevents fixed-width "
            "card images from overflowing their cells. "
            "Existing gallery tests do not cover DCInside's image-style "
            "sanitization."
        ),
        "GalleryUpdateTests.test_v202_announcement_covers_patch_scope": (
            "The saved v2.0.2 gallery post covers the released grammar "
            "furigana, local-first records, Android storage migration, "
            "touch feedback, composite kanji builder fixes, and the "
            "established feedback and GitHub Star calls to action. Earlier "
            "gallery tests do not cover this patch announcement."
        ),
    },
}


class GalleryUpdateTests(unittest.TestCase):
    def assert_dcinside_safe_v2_tables(self, update: str) -> None:
        table_markup = "\n".join(
            re.findall(r"<table\b.*?</table>", update, flags=re.DOTALL)
        )
        self.assertEqual(update.count("<table"), 3)
        self.assertIn('width="16%"', update)
        self.assertIn('width="42%"', update)
        self.assertIn('colspan="2"', update)
        self.assertNotIn(
            "grid-template-columns:repeat(2,minmax(0,1fr))",
            update,
        )
        self.assertNotIn(
            "grid-template-columns:52px minmax(0,1fr) minmax(0,1fr)",
            update,
        )
        self.assertNotIn(
            "grid-template-columns:repeat(auto-fit,minmax(260px,1fr))",
            update,
        )
        self.assertEqual(table_markup.count("max-width:100%"), 9)
        self.assertEqual(table_markup.count('align="center"'), 9)
        self.assertEqual(
            len(re.findall(r"<img\b[^>]*>\s*<br>", table_markup)),
            9,
        )
        self.assertNotIn(
            "width:100%;max-width:390px",
            table_markup,
        )

    def test_v200_uses_tables_for_dcinside_layouts(self) -> None:
        self.assert_dcinside_safe_v2_tables(V200_UPDATE)

    def test_v201_uses_tables_for_dcinside_layouts(self) -> None:
        self.assert_dcinside_safe_v2_tables(V201_UPDATE)

    def test_v202_announcement_covers_patch_scope(self) -> None:
        title_match = re.search(r"<!-- 게시글 제목: (.+?) -->", V202_UPDATE)
        self.assertIsNotNone(title_match)
        self.assertLessEqual(len(title_match.group(1)), 40)

        for copy in (
            "문법 4종 답면에 후리가나",
            "첫 복원 뒤에는 기기에서 바로 계산",
            "최근 90일은 일별, 최근 1년은 월별",
            "7일·30일·이번 달·3개월·1년·전체의 기간 합계 유지",
            "영역별·급수별 합계",
            "최대 1시간에 한 번",
            "월별 기록을 더 작게 압축",
            "전체 합계를 없앤 게 아님",
            "한자 빌더 복합 자형 수정",
            "艹/䒑",
            "巴/巳",
            "兎(兔)",
            "버튼을 눌렀다는 느낌도 보강",
            "v2.0.2 한자 빌더 ZIP",
            "v2.0.2 다운로드 · GitHub Release",
            "써보고 괜찮았다면 개추 + GitHub Star 부탁함",
            "뜻이나 예문이 이상한 부분은 카드의 오류 제보로 보내 주면",
            "★ GitHub에서 Star →",
        ):
            with self.subTest(copy=copy):
                self.assertIn(copy, V202_UPDATE)

        self.assertIn(
            "https://truthyblue.github.io/jlpt-max-deck/assets/releases/"
            "v2.0.2/gallery-v2.0.2-study-records-analysis.png",
            V202_UPDATE,
        )
        self.assertLess(
            V202_UPDATE.index("확인한 범위"),
            V202_UPDATE.index("v2.0.1 사용자"),
        )
        self.assertLess(
            V202_UPDATE.index("v2.0.1 사용자"),
            V202_UPDATE.index("v2.0.2 다운로드"),
        )

    def test_v120_announcement_covers_every_important_learner_feature_once(
        self,
    ) -> None:
        features = re.findall(r'data-release-feature="([^"]+)"', V120_UPDATE)
        self.assertEqual(tuple(features), V120_FEATURES)
        for copy in (
            '<meta charset="utf-8">',
            "<!-- 상태:",
            "<!-- 게시글 제목:",
            "어휘 6,018개와 예문 7,065개",
            "そば·開く·避ける·紅葉·なる",
            "5개 표제어의 10개 카드",
            "기존 preset ID와 지금까지의 학습 기록·스케줄은 그대로",
            "오류 제보·익명 통계 팝업",
            "학습자 뜻 249개와 예문 182개",
            "変わる",
            "持つ",
            "六本",
            "뜻·예문 상세 패치노트 전체 보기 →",
            "docs/release-details/v1.2.0.md",
            "기존 노트 업데이트: 항상",
            "v1.1.x와 v1.0.x 모두",
            "한자 확장도 v1.2.0 빌더로 다시 만들기",
            "Windows Anki 야간 모드용 투명 SVG 렌더링",
            "한자 펼침과 이미지 표시 수정",
            "원본부터 빌더 출력까지 투명한 path-only SVG로 통일",
            "다크 모드 대비 보정은 v1.1.0 한자 빌더부터 적용됐으며",
            "한자 보이기·감추기 버튼은 v1.2.0 카드에 반영했고",
            "업데이트 알림 닫기 상태 저장 수정",
            "<strong>7일간 숨기기</strong>와",
            "v1.1.1부터 제공됐음",
            "쿠키와 localStorage가 서로 다른 상태를 읽어",
            "×</strong>는 이번 학습",
            "설정 패널은 어휘·음성·실전 문제의 답안에서 열 수 있음",
            "참조표와 한자 카드를 포함한 전체 덱에 공통 적용됨",
            "오른쪽 위 ×는 이번 학습에서만 알림을 닫음",
            "기존 덱에서 v1.2.0 출시 응답을 재현한 실제 생성 카드 화면",
            "업데이트 뒤 남은 예전 음성은 미디어 검사로 정리",
            "도구 → 미디어 검사",
            "다른 덱의 미사용 파일도 함께 잡힐 수 있으니",
            "운영체제 휴지통에서 복구할 수 있음",
            "v1.2.0 GitHub Release →",
            "제보해 준 내용은 이렇게 처리했음",
            "8월 14일까지 접수된 실제 제보 27건",
            "v1.2.0 반영 · 18건",
            "이전 반영·v1.2.0 보강 · 4건",
            "추가 확인·검토 · 4건",
            "현재 표기 · 1건",
            "六本",
            "十つ",
            "敬語·録画",
            "上がる",
            "最小限",
            "売買",
            "郊外",
            "검토한 발음·모라 근거",
            "고저선과 음성 합성 입력에 함께 반영",
            "생성 APKG에서 교정된 음성을 확인했음",
            "iOS 스피커",
            "定員",
            "규정 인원 / 수용 인원",
            "한자 보이기·감추기 버튼",
            "상단 후리가나 바로 켜기·끄기",
            "다크 모드 대비 보정은 v1.1.0 한자 빌더부터 반영됐음",
            "중복 1건을 포함해 제보된 3개 카드",
            "이미지 한자 14자를 투명한 path-only SVG로 통일했음",
            "好調",
            "익명 통계로 보는 현재 이용 현황",
            "익명 통계 → 사용 통계 공유하기",
    "활성 설치는 최근 30일 동안 학습한 무작위 설치 ID 수",
            "플랫폼·덱 버전·학습 영역·JLPT 급수별 집계를 함께 보여 줌",
            "별도 통계 글로 공유할 예정임",
        ):
            with self.subTest(copy=copy):
                self.assertIn(copy, V120_UPDATE)

        self.assertFalse(
            (ROOT / "docs" / "jlpt-gallery-updates" / "v1.2.0.md").exists()
        )
        self.assertNotIn("## 독립 뜻 분리·통합", V120_UPDATE)
        self.assertNotIn("## 새 예문", V120_UPDATE)
        self.assertNotIn("테스트 제보", V120_UPDATE)

    def test_v120_report_feedback_and_audio_scope_stay_synchronized(
        self,
    ) -> None:
        public_copies = {
            "gallery": re.sub(r"<[^>]+>", " ", V120_UPDATE),
            "github-release": V120_RELEASE_DRAFT,
            "release-template": V120_RELEASE_TEMPLATE,
            "release-notes": V120_RELEASE_NOTES,
        }
        required_copy = (
            "8월 14일까지 접수된 실제 제보 27건",
            "발음·모라 근거",
            "음성 합성 입력",
            "敬語",
            "録画",
            "上がる",
            "最小限",
            "売買",
            "郊外",
            "상단 후리가나 바로 켜기·끄기",
            "iOS 스피커",
            "定員",
            "규정 인원 / 수용 인원",
            "현재 표기",
        )
        stale_copy = (
            "8월 13일까지 접수된 실제 제보 25건",
            "v1.2.0 반영 · 11건",
            "다음 패치 후보·추가 확인",
            "발음 6건은 새 악센트선과 함께 전수검사한 뒤 결정",
        )
        report_rows = (
            (r"v1\.2\.0 반영.{0,40}18건", "v1.2.0 reflected"),
            (r"이전 반영·v1\.2\.0 보강.{0,40}4건", "previous reflected"),
            (r"추가 확인·검토.{0,40}4건", "reviewing"),
            (r"현재 표기.{0,40}1건", "current display"),
        )

        for label, raw_copy in public_copies.items():
            compact = " ".join(raw_copy.split())
            for copy in required_copy:
                with self.subTest(source=label, copy=copy):
                    self.assertIn(copy, compact)
            for copy in stale_copy:
                with self.subTest(source=label, stale_copy=copy):
                    self.assertNotIn(copy, compact)
            for pattern, row in report_rows:
                with self.subTest(source=label, row=row):
                    self.assertRegex(compact, pattern)

    def test_v120_announcement_and_release_notes_use_all_ui_evidence(
        self,
    ) -> None:
        for screenshot, (width, height) in V120_SCREENSHOTS.items():
            with self.subTest(screenshot=screenshot):
                self.assertTrue((ROOT / "site" / "assets" / screenshot).is_file())
                self.assertIn(
                    "https://truthyblue.github.io/jlpt-max-deck/assets/"
                    + screenshot,
                    V120_UPDATE,
                )
                self.assertIn(
                    f'width="{width}" height="{height}"', V120_UPDATE
                )
                self.assertIn(
                    "https://raw.githubusercontent.com/truthyblue/"
                    "jlpt-max-deck/main/site/assets/" + screenshot,
                    V120_RELEASE_NOTES,
                )

    def test_v120_meaning_section_shows_one_example_per_change_type(self) -> None:
        change_types = re.findall(
            r'data-change-example="([^"]+)"', V120_UPDATE
        )
        self.assertEqual(
            tuple(change_types),
            (
                "meaning-split",
                "meaning-wording",
                "new-example",
                "example-correction",
            ),
        )
        for copy in (
            "濃い",
            "取り上げる",
            "職人は長年かけて技を磨いた。",
            "矢印は駅の方向を示す。",
        ):
            with self.subTest(copy=copy):
                self.assertIn(copy, V120_UPDATE)
                self.assertIn(copy, V120_RELEASE_NOTES)

    def test_v120_usage_followup_is_ready_for_a_seven_day_capture(self) -> None:
        followup_compact = " ".join(V120_USAGE_FOLLOWUP.split())
        for copy in (
            "v1.2.0 익명 이용 현황",
            "업데이트 이후 이용 현황",
            "게시 직전 Grafana에서 새로 고침",
            "Last 7 days",
            "버전별 설치 수와 전환 추이",
            "설치별 학습 횟수와 이용 추이",
            "학습 구성",
            "설치별 학습 횟수와 활동일을 구간별 분포로 공개함",
            "집계 항목은 무작위 설치 ID, 플랫폼, 덱 버전, 학습 영역",
            "익명 통계 → 사용 통계 공유하기",
            "오류 제보는 모바일 카드의 **오류 제보** 버튼",
        ):
            with self.subTest(copy=copy):
                self.assertIn(copy, followup_compact)

        for stale_copy in (
            "배포 7일 뒤",
            "배포 뒤 7일",
            "최근 30일 활성 설치",
            "최근 30일 총 학습 횟수",
            "추이 그래프는 최근 7일",
            "사람 수나 전체 이용자 수가 아니고",
            "개별 설치 ID는 표시하지 않고",
            "수집하지 않음",
            "동의 여부와 무관함",
        ):
            with self.subTest(stale_copy=stale_copy):
                self.assertNotIn(stale_copy, followup_compact)

    def test_local_preview_resolves_every_versioned_release_image(self) -> None:
        (ROOT / "build").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as raw:
            for version, expected_count in (("1.1.0", 2), ("1.2.0", 7)):
                with self.subTest(version=version):
                    output = Path(raw) / f"v{version}.html"
                    receipt = render_gallery_preview(
                        source=(
                            ROOT
                            / "docs/jlpt-gallery-updates"
                            / f"v{version}.html"
                        ),
                        output=output,
                    )
                    preview = output.read_text(encoding="utf-8")
                    self.assertEqual(expected_count, receipt["image_count"])
                    self.assertEqual(expected_count, len(receipt["assets"]))
                    self.assertNotIn(
                        "truthyblue.github.io/jlpt-max-deck/assets/", preview
                    )
                    for asset in receipt["assets"]:
                        resolved = (
                            output.parent / asset["preview_src"]
                        ).resolve()
                        self.assertTrue(resolved.is_file())
                        self.assertTrue(
                            resolved.is_relative_to(
                                ROOT / f"site/assets/releases/v{version}"
                            )
                        )

    def test_local_preview_rejects_a_missing_public_image(self) -> None:
        (ROOT / "build").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as raw:
            temp_root = Path(raw)
            source = temp_root / "missing.html"
            source.write_text(
                '<img src="https://truthyblue.github.io/'
                'jlpt-max-deck/assets/releases/v9.9.9/missing.png">',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GalleryPreviewError, "preview asset does not exist"
            ):
                render_gallery_preview(
                    source=source,
                    output=temp_root / "preview.html",
                )

    def test_hotfix_announcement_preserves_the_established_gallery_format(
        self,
    ) -> None:
        for copy in (
            '<meta charset="utf-8">',
            "<!-- 상태:",
            "<!-- 게시글 제목:",
            "디시인사이드가 저장 후 제거하는 스타일이나 표 레이아웃에 의존하지 않는 본문",
            "color:#1b211d;background:#fff",
            "border-top:8px solid #d8ff62",
            "border-left:8px solid #8ee6b1",
            "업데이트 방법 보기 →",
            "★ GitHub에서 Star →",
        ):
            with self.subTest(copy=copy):
                self.assertIn(copy, HOTFIX_UPDATE)

        self.assertNotIn("border-radius:22px", HOTFIX_UPDATE)
        self.assertNotIn("linear-gradient(135deg", HOTFIX_UPDATE)

    def test_hotfix_announcement_matches_the_closed_v111_scope(self) -> None:
        for copy in (
            "뜻 묶음과 예문의 연결을 더 또렷하게",
            "가운데점(·)",
            "슬래시(/)",
            "예문 1·2 대신 각 문장 위에 대응하는 뜻 칩",
            "兄 — 형 · 오빠",
            "私は妹で、兄は私より三歳上です。",
            "弟は兄と毎朝一緒に学校へ行く。",
            "보충 예문 100개",
            "6,883개",
            "쿠키 + localStorage 이중 저장",
            "아이폰·아이패드 음성 재생 수정",
            "HTML 오디오 요소를 직접 재생",
            "새 버전 안내 보강",
            "7일간 숨기기",
            "알림 다시 보지 않기",
            "설정 → 고급 → 학습 화면 로컬 스토리지",
            "기존 노트 업데이트: 새 버전일 때",
            "1.1.0 → 1.1.1 패치 업데이트",
            "1.0.x → 1.1.x",
            "가운데 숫자가 바뀌는 마이너 버전 업데이트에서만",
            "노트 유형 병합: 켜기",
            "18,267개",
            "v1.1.1 GitHub Release",
        ):
            self.assertIn(copy, HOTFIX_UPDATE)
        self.assertNotIn("음성 재생은 그대로", HOTFIX_UPDATE)
        self.assertNotIn("카드 내용과 학습 기록은 그대로", HOTFIX_UPDATE)
        self.assertNotIn("미디어 18,167개", HOTFIX_UPDATE)

    def test_announcement_leads_with_new_feature_value(self) -> None:
        settings_heading = "1. 카드 설정 통합 + 4단계 재생 배속"
        meaning_heading = "2. 어휘 뜻 386개와 의미별 예문 교정"
        report_heading = "3. 문제 있는 카드에서 바로 오류 제보"
        telemetry_heading = "4. 선택형 모바일 익명 통계 추가"

        self.assertLess(UPDATE.index(settings_heading), UPDATE.index(meaning_heading))
        self.assertLess(UPDATE.index(meaning_heading), UPDATE.index(report_heading))
        self.assertLess(UPDATE.index(report_heading), UPDATE.index(telemetry_heading))
        self.assertNotIn("동의하기 전에는 사용 통계를 보내지 않음", UPDATE)
        self.assertNotIn("1. v1.0.3 덱을 지우지 않고 업데이트", UPDATE)

    def test_announcement_explains_all_new_playback_speeds(self) -> None:
        for copy in (
            "새로 추가된 0.8·1·1.2·1.5배속",
            "빠르게 들리는 단어나 예문을 천천히 확인할 때",
            "v1.0.3과 같은 기본 속도로 들을 때",
            "익숙한 카드를 빠르게 복습할 때",
            "자동재생과 직접 누른 음성에 똑같이 적용",
            "앱을 다시 열어도 유지",
            "배경 음악이 줄거나 멈출 수 있어 주의가 필요함",
        ):
            self.assertIn(copy, UPDATE)
        self.assertNotIn("설정 안에 안내를 표시", UPDATE)

    def test_announcement_describes_meaning_corrections_without_id_churn(self) -> None:
        for copy in (
            "N5 70개, N4 46개, N3 77개, N2 91개, N1 102개",
            "6,681개에서 6,783개",
            "어휘 노트·카드 ID와 실전 문제 GUID는 바꾸지 않았음",
        ):
            self.assertIn(copy, UPDATE)

    def test_announcement_covers_every_learner_visible_meaning_change_type(self) -> None:
        for copy in (
            "① 새 뜻 묶음 추가",
            "144개",
            "② 기존 뜻 묶음 안의 한국어 표현 보강",
            "77개",
            "③ 과하게 나뉜 뜻 묶음 통합",
            "75개",
            "④ 뜻 표현 자체를 자연스럽게 교정",
            "90개",
            "완전히 삭제한 뜻은 0개",
            "생각해내다, 생각나다",
            "この歌を聞くと故郷を思い出す。",
            "학급, 수업",
            "病気で昨日のクラスを休んだ。",
        ):
            with self.subTest(copy=copy):
                self.assertIn(copy, UPDATE)

    def test_announcement_and_release_notes_show_concrete_meaning_examples(self) -> None:
        for copy in (
            "하다 / 나다",
            "外で変な音がする。",
            "집어 들다 / 다루다 / 빼앗다",
            "次の会議で、この提案を取り上げる。",
            "소진되다 / 끊어지다 / (기한이) 만료되다",
            "私のパスポートは来月で期限が切れる。",
            "순조롭다",
            "호조이다",
            "今月の輸出は好調だと報告された。",
        ):
            with self.subTest(copy=copy):
                self.assertIn(copy, UPDATE)
                self.assertIn(copy, RELEASE_NOTES)

        self.assertIn("音がする", UPDATE)
        self.assertIn("주제·제안을 ‘다루다’라는 문맥", UPDATE)
        self.assertIn("성과나 상태가 좋은 ‘호조’", UPDATE)
        self.assertIn("각 예문 위에 <strong>뜻</strong> 칩을 표시", UPDATE)
        self.assertIn("각 예문 위에 **뜻** 칩을 표시", RELEASE_NOTES)
        self.assertIn("기존 뜻만으로 해석하기 어려웠던", RELEASE_NOTES)

    def test_announcement_preserves_verified_update_instructions(self) -> None:
        for copy in (
            "학습 진행 상태 가져오기",
            "기존 노트 업데이트",
            "노트 유형 병합",
            "반드시 <strong>항상</strong>",
            "새 버전일 때</strong>로 두면 v1.0.3 뜻과 예문이 그대로 남음",
            "クラス</strong>가 아직 <strong>학급 / 수업",
            "思い出す</strong>가 <strong>생각해내다</strong>로만 보인다면",
            "직접 고친 뜻·예문 필드도 덮어쓸 수 있으니",
        ):
            self.assertIn(copy, UPDATE)
        self.assertIn("**기존 노트 업데이트**는 반드시", RELEASE_NOTES)
        self.assertIn("**항상**, **노트 유형 병합**", RELEASE_NOTES)
        self.assertIn("**새 버전일 때**로 두면 v1.0.3 기존 노트의 뜻·예문", RELEASE_NOTES)

    def test_announcement_uses_pages_hosted_ui_screenshots(self) -> None:
        for filename, (width, height) in SCREENSHOTS.items():
            self.assertTrue((ROOT / "site" / "assets" / filename).is_file())
            self.assertIn(
                f'src="https://truthyblue.github.io/jlpt-max-deck/assets/{filename}"',
                UPDATE,
            )
            self.assertIn(f'width="{width}" height="{height}"', UPDATE)
        self.assertIn("0.8·1·1.2·1.5배속을 조절하는 화면", UPDATE)
        self.assertIn("함께 전송되는 정보를 확인하는 화면", UPDATE)

    def test_release_notes_use_main_hosted_ui_screenshots(self) -> None:
        for filename in SCREENSHOTS:
            self.assertIn(
                "https://raw.githubusercontent.com/truthyblue/jlpt-max-deck/"
                f"main/site/assets/{filename}",
                RELEASE_NOTES,
            )
        self.assertIn("0.8·1·1.2·1.5배속을 조절하는 화면", RELEASE_NOTES)
        self.assertIn("함께 전송되는 정보를 확인하는 화면", RELEASE_NOTES)


if __name__ == "__main__":
    unittest.main()
