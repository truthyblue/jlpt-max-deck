from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UPDATE = (
    ROOT / "docs" / "jlpt-gallery-updates" / "v1.1.0.html"
).read_text(encoding="utf-8")


class GalleryUpdateTests(unittest.TestCase):
    def test_announcement_leads_with_new_feature_value(self) -> None:
        settings_heading = "1. 카드 설정 통합 + 4단계 재생 배속"
        report_heading = "2. 문제 있는 카드에서 바로 오류 제보"
        telemetry_heading = "3. 선택형 모바일 익명 통계 추가"

        self.assertLess(UPDATE.index(settings_heading), UPDATE.index(report_heading))
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

    def test_announcement_preserves_verified_update_instructions(self) -> None:
        for copy in (
            "학습 진행 상태 가져오기",
            "기존 노트 업데이트",
            "노트 유형 병합",
        ):
            self.assertIn(copy, UPDATE)


if __name__ == "__main__":
    unittest.main()
