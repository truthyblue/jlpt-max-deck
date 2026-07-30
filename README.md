# JLPT MAX Deck

> 한국어권 JLPT 학습용 Anki 덱. 어휘·음성·실전 문제·참조표가 담긴 기본 덱으로
> 시작하고, 원하면 일상무따 한자 2,337개를 확장으로 추가할 수 있습니다.

## 처음 시작한다면

가장 쉬운 방법은 [웹 시작 가이드](https://truthyblue.github.io/jlpt-max-deck/getting-started.html)를
따르는 것입니다.

1. 공부할 기기에 맞는 [Anki 앱](https://truthyblue.github.io/jlpt-max-deck/install-anki.html)을 설치합니다.
2. [JLPT-MAX-Deck-1.0.0.apkg](https://github.com/truthyblue/jlpt-max-deck/releases/download/v1.0.0/JLPT-MAX-Deck-1.0.0.apkg)를 받습니다.
3. 다운로드한 APKG를 Anki에서 열고 가져오기가 끝날 때까지 기다립니다.
4. `JLPT MAX덱::어휘`에서 목표 급수의 새 카드를 시작합니다.

기본 덱은 완성된 APKG 파일입니다. Anki Desktop, AnkiMobile 또는 AnkiDroid에서
다운로드한 파일을 열어 가져오세요. 브라우저의 AnkiWeb은 APKG 가져오기를
지원하지 않습니다.

## 어떤 파일을 받으면 되나요?

| 원하는 구성 | 받을 파일 | 추가 준비물 |
| --- | --- | --- |
| 어휘·음성·실전 문제·참조표 | `JLPT-MAX-Deck-1.0.0.apkg` | Anki·AnkiMobile·AnkiDroid |
| 위 구성 + 일상무따 한자 | 기본 덱 + `JLPT-MAX-kanji-builder-1.0.0.zip` | 지원 PDF 2개, Python 3.13, `uv`, 컴퓨터 |

## 덱 구성

| 구성 | 노트 | 카드 | 미디어 |
| --- | ---: | ---: | ---: |
| 기본 덱: 어휘·음성·실전 문제·참조표 | 13,903 | 20,065 | 17,950 |
| 선택형 일상무따 한자 확장 | 2,337 | 2,337 | 14 |
| 두 APKG를 같은 컬렉션에 가져온 전체 | 16,240 | 22,402 | 17,964 |

기본 덱에는 어휘 6,018개, 실전 문제
7,876개, 참조표 9개와
단어·예문 음성이 들어 있습니다. 일상무따 한자 2,337개는 아래 별도 선택 확장
과정에서 개인용 APKG로 만든 뒤 같은 Anki 컬렉션에 추가합니다.

처음에는 FSRS 기억 유지율을 90%,
어휘 새 카드를 하루 10~20장으로 두는 것을 권합니다.
독립 음성 카드는 처음에는 하루 0장으로
두고 어휘가 익숙해진 뒤 늘리세요. 자세한 설정과 업데이트 절차는
[Anki 가이드](docs/anki.md)에 있습니다.

## 선택형 한자 확장

일상무따 한자 2,337개를 추가하려면 같은
v1.0.0의
[JLPT-MAX-kanji-builder-1.0.0.zip](https://github.com/truthyblue/jlpt-max-deck/releases/download/v1.0.0/JLPT-MAX-kanji-builder-1.0.0.zip)과
길벗 《일본어 상용한자 무작정 따라하기》 1·2권의 지원 소책자 PDF가 필요합니다.

- [1권 공식 자료 페이지](https://www.gilbut.co.kr/book/view?bookcode=BN003617)
- [2권 공식 자료 페이지](https://www.gilbut.co.kr/book/view?bookcode=BN003669)

각 페이지에서 자료 제공 방식과 이용 조건을 확인하고 정상적으로 받은 PDF 원본을
사용하세요. 다시 저장·병합·최적화한 파일이나 다른 판본은 지원하지 않습니다.
빌더는 Release에서 검증한 macOS 12+ 또는 Windows
x64 컴퓨터에서 실행합니다.

```bash
./scripts/build-kanji-addon.sh "/경로/상권.pdf" "/경로/하권.pdf"
```

```powershell
.\scripts\build-kanji-addon.ps1 -UpperPdf "C:\경로\상권.pdf" -LowerPdf "C:\경로\하권.pdf"
```

완성된 `JLPT-MAX-kanji-addon-1.0.0.apkg`를 기본 덱 다음에
가져오면 됩니다. PDF·페이지 이미지·생성 APKG는 외부 서비스로 전송되지 않습니다.
준비부터 오류 해결까지는 [한자 확장 가이드](docs/build.md)를 보세요.

## 업데이트와 문제 해결

- 기존 학습 기록을 유지하는 업데이트: [Anki 가져오기·업데이트](docs/anki.md)
- 다운로드, 음성, PDF 또는 빌더 오류: [문제 해결](docs/troubleshooting.md)
- 현재 자산과 검증 결과: [v1.0.0 릴리스 노트](docs/releases/v1.0.0.md)
- 개인정보와 재배포 범위: [개인정보·저작권·라이선스](docs/privacy-and-licensing.md)

공식 기본 덱 파일을 다시 올리는 대신 이 저장소나 공식 Release 링크를 공유해
주세요. 사용자가 PDF로 만든 한자 확장 APKG는 개인 학습용입니다. 정확한 조건은
[NOTICE](NOTICE)가 우선합니다.

## 개발과 기여

코드나 문서를 수정하려면 [CONTRIBUTING](CONTRIBUTING.md)을 먼저 확인하세요.

이 프로젝트는 Anki, JLPT 시험 운영기관, 출판사 또는 EDRDG의 공식 제품이나 후원
프로젝트가 아닙니다.
