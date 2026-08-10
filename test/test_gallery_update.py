from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UPDATE = (
    ROOT / "docs" / "jlpt-gallery-updates" / "v1.1.0.html"
).read_text(encoding="utf-8")
HOTFIX_UPDATE = (
    ROOT / "docs" / "jlpt-gallery-updates" / "v1.1.1.html"
).read_text(encoding="utf-8")
RELEASE_NOTES = (ROOT / "docs" / "releases" / "v1.1.0.md").read_text(
    encoding="utf-8"
)
SCREENSHOTS = {
    "gallery-v1.1.0-card-settings.webp": (390, 500),
    "gallery-v1.1.0-error-report.webp": (354, 644),
}


class GalleryUpdateTests(unittest.TestCase):
    def test_hotfix_announcement_matches_the_storage_only_scope(self) -> None:
        for copy in (
            "쿠키 + localStorage 이중 저장",
            "설정 → 고급 → 학습 화면 로컬 스토리지",
            "음성 재생은 그대로",
            "기존 노트 업데이트: 항상",
            "노트 유형 병합: 켜기",
            "v1.1.1 GitHub Release",
        ):
            self.assertIn(copy, HOTFIX_UPDATE)
        self.assertNotIn("음성 재생 방식을 바꿨", HOTFIX_UPDATE)

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
