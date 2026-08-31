<p align="center">
  <a href="https://truthyblue.github.io/jlpt-max-deck/">
    <img src="site/assets/brand-lockup.svg" alt="JLPT MAX Deck" width="560">
  </a>
</p>

# JLPT MAX Deck

> 한국어권 JLPT 학습용 Anki 덱. 문법·어휘·음성·실전 문제·참조표가 담긴 기본 덱으로
> 시작하고, 원하면 한자 2,337개의
> 읽기·쓰기 카드를 확장으로 추가할 수 있습니다.

## 어디서 시작하나요?

전체 흐름은 [웹 시작 가이드](https://truthyblue.github.io/jlpt-max-deck/getting-started.html)에서
확인할 수 있습니다.

- **Anki가 처음이에요**: [기기별 설치 안내](https://truthyblue.github.io/jlpt-max-deck/install-anki.html)부터
  시작합니다.
- **Anki를 이미 사용 중이에요**: 동기화를 마친 뒤
  [기존 사용자 가져오기](https://truthyblue.github.io/jlpt-max-deck/getting-started.html#existing-user)를
  따릅니다.
- **JLPT MAX덱을 업데이트할게요**:
  [업데이트 가이드](https://truthyblue.github.io/jlpt-max-deck/update.html)를 먼저 확인합니다.

처음 가져온 뒤에는 시험 볼 급수와 관계없이 `JLPT MAX덱::어휘::N5`부터 시작합니다.
아는 카드는 `Easy`로 빠르게 넘기고, 시험 볼 급수까지 차례대로 공부합니다.
어떤 덱을 언제 시작하는지는
[덱 학습법](https://truthyblue.github.io/jlpt-max-deck/study-guide.html)에 정리했습니다.

기본 덱은 완성된 APKG 파일입니다. Anki Desktop, AnkiMobile 또는 AnkiDroid에서
다운로드한 파일을 열어 가져오세요. 브라우저의 AnkiWeb은 APKG 가져오기를
지원하지 않습니다.

## 어떤 파일을 받으면 되나요?

| 원하는 구성 | 받을 파일 | 추가 준비물 |
| --- | --- | --- |
| 문법·어휘·음성·실전 문제·참조표 | `JLPT-MAX-Deck-2.0.3.apkg` | Anki·AnkiMobile·AnkiDroid |
| 위 구성 + 한자 읽기·쓰기 | 기본 덱 + `JLPT-MAX-kanji-builder-2.0.3.zip` | 지원 PDF 2개, macOS 또는 Windows 컴퓨터 |

## 덱 구성

| 구성 | 노트 | 카드 | 미디어 |
| --- | ---: | ---: | ---: |
| 기본 덱: 문법·어휘·음성·실전 문제·참조표 | 20,650 | 38,970 | 24,978 |
| 선택형 한자 읽기·쓰기 덱 | 4,674 | 4,674 | 14 |
| 두 APKG를 같은 컬렉션에 가져온 전체 | 25,324 | 43,644 | 24,992 |

기본 덱에는 문법 3,605개, 어휘 9,160개, 실전 문제
7,876개, 참조표 9개와
단어·예문 음성이 들어 있습니다. 한자
2,337개는 읽기·쓰기 노트
4,674개로 구성됩니다. 원할 때 아래 방법으로
개인용 APKG를 만들어 같은 Anki 컬렉션에 추가합니다.

v1.3.0부터 iPhone·iPad의 기본 재생 방식은 무음 모드에서도 카드 음성을 냅니다.
v1.2.1까지처럼 다른 앱 음악과 카드 음성을 섞어 재생하려면 답안 오른쪽 위
**설정 → 다른 앱 음악과 함께 재생**을 켜세요. 이 옵션을 켜면 iPhone·iPad의
무음 모드에서는 카드 음성이 나오지 않을 수 있습니다.

v1.1.0부터 답안 오른쪽 위 **설정**에서 후리가나·해석·자동재생과
0.8·1·1.2·1.5배 재생 속도를 함께 조절할 수 있습니다. 카드 아래에서는 오류를
바로 제보할 수 있고, 모바일 사용 통계는 명시적으로 동의한 경우에만 공유합니다.
어휘 386개의 한국어 뜻과 의미별 예문도 실제 쓰임에 맞게 교정했습니다.

v1.1.1부터 카드 설정과 익명 통계 상태를 쿠키와 `localStorage`에 함께 저장해
iPhone·iPad에서도 앱을 다시 연 뒤 선택이 유지됩니다. AnkiDroid에서는
**설정 → 고급 → 학습 화면 로컬 스토리지**를 켜면 `localStorage`도 같은 카드
주소에서 유지되며, 이 설정을 끈 상태에서도 기존 쿠키 저장은 계속 사용합니다.
iPhone·iPad 음성은 Web Audio의 fetch·decode 경로를 거치지 않고 HTML 오디오
요소를 직접 재생합니다. 모든 카드 답면의 새 버전 안내에서는 업데이트 가이드로
바로 이동하거나 7일간 숨기고, 해당 버전 알림을 다시 보지 않도록 선택할 수 있습니다.

v1.2.0부터 어휘와 예문에 고저 악센트 선을 표시하고, 설정에서 표시 여부와
일본어 글꼴을 고를 수 있습니다. 새 카드는 복습 카드 사이에 섞여 나오며, 모바일
팝업과 한자 펼치기 동작도 안정화했습니다. 학습자 뜻 표시 249개를 다듬고 예문
182개를 추가했습니다. JLPT MAX 덱을 업데이트할 때는 출발 버전과 관계없이 기존
노트 업데이트를 `항상`으로 선택하세요.

v1.3.0부터 한자마다 읽기 카드와 쓰기 카드를 따로 제공합니다. 가져오기가
끝나면 모든 기기에서 다시 전체 동기화하세요. 한자 덱은 현재 버전 빌더로 다시
만들어 가져와야 새 읽기·쓰기 구조와 쓰기 순서가 모두 적용됩니다.

v2.0.1은 v2.0.0의 문법 3,605개·어휘 9,160개·한국어→일본어 회상 카드와 모바일 내 기록을 그대로 담고,
AnkiDroid에서 기록 데이터가 커졌을 때 가져오기나 카드 표시가 실패할 수 있던
문제를 고쳤습니다. 기존 사용자는 학습 진행 상태를 끄고 기존 노트·노트 유형 업데이트를
항상, 노트 유형 병합을 켜서 가져옵니다. 새 BCCWJ 중요도 순서를 쓰기 위해 이미
학습한 급수를 삭제하면 안 됩니다. 완전히 미학습 상태인 급수만 어휘·음성 덱을
함께 삭제한 뒤 다시 가져올 수 있습니다. 예전 버전에서 올린다면
[업데이트 방법](https://truthyblue.github.io/jlpt-max-deck/update.html)의 빈 카드와 삭제된 어휘 정리도
확인하세요.

v2.0.3은 기기에 남은 내 기록과 JLPT 목표를 서버에서 자동으로 다시 확인하고,
잠깐의 연결 실패를 한 번 더 시도합니다. 개인 최고 기록 알림은 하루 한 번 카드
가운데에 표시되며, 문법 카드의 업데이트 공지도 다른 카드와 같은 모양으로 보입니다.

처음에는 FSRS 기억 유지율을 90%,
어휘 새 카드를 하루 10~20장으로 두는 것을 권합니다.
독립 음성 카드는 필요할 때만 공부하고, 이미 공부 중이라면 지금 설정을 유지하세요.
종합 실전은 시험 볼 급수까지 어휘를 모두 한 번 본 뒤
그 급수의 문제만 풉니다. 자세한 순서는 [덱 학습법](https://truthyblue.github.io/jlpt-max-deck/study-guide.html),
설정과 업데이트 절차는 [Anki 가이드](docs/anki.md)에 있습니다.

## 한자 읽기·쓰기 덱

한자 2,337개의 읽기·쓰기 카드에
필요한 한글 뜻은 저작권 때문에 완성본으로 배포하지 않습니다. 필요한 학습자만
공식 PDF 2개를 자기 컴퓨터에서 읽어 개인용 APKG를 완성합니다. 처음이라면
[한자 덱 만들기](https://truthyblue.github.io/jlpt-max-deck/kanji.html)를 그대로 따라가세요.

1. [1권 공식 자료 페이지](https://www.gilbut.co.kr/book/view?bookcode=BN003617)와
   [2권 공식 자료 페이지](https://www.gilbut.co.kr/book/view?bookcode=BN003669)에서
   지원 소책자 PDF를 각각 받습니다.
2. 같은 v2.0.3의
   [JLPT-MAX-kanji-builder-2.0.3.zip](https://github.com/truthyblue/jlpt-max-deck/releases/download/v2.0.3/JLPT-MAX-kanji-builder-2.0.3.zip)을
   받아 압축을 완전히 풉니다.
3. Windows는 `Windows에서 한자 확장 만들기.cmd`, macOS는
   `Mac에서 한자 확장 만들기.command`를 더블클릭합니다.
4. 첫 번째 PDF 선택창에 1권, 두 번째 선택창에 2권을 고르고 완료될 때까지 기다립니다.
5. 자동으로 열린 폴더의 `JLPT-MAX-kanji-addon-2.0.3.apkg`를
   기본 덱과 같은 Anki 컬렉션에 가져옵니다.

PowerShell·터미널 명령이나 Python 설치는 필요하지 않습니다. 빌더는 처음 한 번
필요한 프로그램을 자동으로 준비하며, PDF·페이지 이미지·생성 APKG를 외부
서비스로 전송하지 않습니다. 받은 PDF는 다시 저장·병합·최적화하지 마세요.
세부 검증 정보는 [저장소용 한자 덱 문서](docs/build.md)에 있습니다.

## 업데이트와 문제 해결

- 기존 학습 기록을 유지하는 업데이트: [웹 업데이트 가이드](https://truthyblue.github.io/jlpt-max-deck/update.html)
- 다운로드, 음성, PDF 또는 빌더 오류: [문제 해결](docs/troubleshooting.md)
- 현재 자산과 검증 결과: [v2.0.3 릴리스 노트](docs/releases/v2.0.3.md)
- 개인정보와 재배포 범위: [개인정보·저작권·라이선스](docs/privacy-and-licensing.md)

공식 기본 덱 파일을 다시 올리는 대신 이 저장소나 공식 Release 링크를 공유해
주세요. 사용자가 PDF로 만든 한자 덱 APKG는 개인 학습용입니다. 정확한 조건은
[NOTICE](NOTICE)가 우선합니다.

## 개발과 기여

코드나 문서를 수정하려면 [CONTRIBUTING](CONTRIBUTING.md)을 먼저 확인하세요.

이 프로젝트는 Anki, JLPT 시험 운영기관, 출판사 또는 EDRDG의 공식 제품이나 후원
프로젝트가 아닙니다.
