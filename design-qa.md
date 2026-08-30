# JLPT MAX 도움말 개편 Design QA

## 비교 기준

- Source visual truth: `/Users/user/.codex/generated_images/01a0531e-00bf-7f12-afa2-7deb572c90dc/exec-891fbf1f-4de0-4ab8-84d1-29d28fcb1496.png`
- Source normalized crop: `build/design-qa/faq-guide/source-normalized-390x844.png`
- Final implementation: `build/design-qa/faq-guide/implementation-mobile-pass-4.png`
- Final side-by-side comparison: `build/design-qa/faq-guide/comparison-pass-4.png`
- Viewport: 390×844, devicePixelRatio 1
- State: 도움말 첫 화면, 모바일 내비게이션 닫힘, 스크롤 최상단

## 비교 이력

1. Pass 1: 두 줄 홍보형 제목, 카드 설명, 270px 카드 높이 때문에 핵심 경로와 FAQ가 기준보다 아래로 밀렸다. P2 밀도 차이로 판정했다.
2. Pass 2: 제목을 `도움말`로 줄이고 모바일 카드 설명을 걷어냈다. 카드 밀도는 좋아졌지만 기존 kicker와 큰 카드 높이 때문에 기준보다 여전히 길었다.
3. Pass 3: kicker를 제거하고 제목·카드 간격을 줄였다. 첫 화면의 정보 순서와 2열 카드 구조가 기준에 가까워졌다.
4. Pass 4: 카드 높이와 FAQ 위 간격을 한 번 더 줄였다. 390×844에서 네 경로와 첫 FAQ가 함께 보이며 기준의 위계와 밀도에 맞았다.

## 최종 판정

- P0: 없음
- P1: 없음
- P2: 없음
- P3: 실제 제품 문구에 맞춰 기준의 활성 메뉴 `지원`을 `도움`으로 썼다. 기능과 위계에는 영향이 없다.
- 아이콘은 Bootstrap Icons 원본 SVG를 사용했다. 임시 도형이나 텍스트 아이콘은 없다.
- 360px 이하에서는 카드가 1열로 바뀌고 가로 넘침이 없으며, 390px에서는 기준과 같은 2열을 유지한다.

## 동작 확인

- `기존 덱을 지워야 하나요?` 링크가 `#faq-update-delete`로 이동하고 해당 FAQ를 자동으로 연다.
- 모바일 시작 가이드 하위 메뉴가 열리고 닫히며 `aria-expanded` 상태가 함께 바뀐다.
- `추천 학습 순서 보기`가 `study-guide.html#tracks`로 이동한다.
- 업데이트 복구 검색어의 복사 버튼이 실제 검색어를 복사하고 `복사됨`으로 바뀐다.
- 브라우저 오류 로그: 0건

final result: passed
