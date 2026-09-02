# 한자 읽기·쓰기 덱 만들기

이 가이드는 한자
2,337개의 읽기·쓰기 카드
4,674장을 별도 선택 확장으로 추가하는 과정을
설명합니다.

[초심자용 웹 가이드](https://truthyblue.github.io/jlpt-max-deck/kanji.html) · [README](../README.md) ·
[Anki 가이드](anki.md) · [문제 해결](troubleshooting.md)

## 먼저 확인할 것

한자 덱은 완성 APKG로 배포하지 않습니다. 길벗 자료의 한글 뜻과 일부 인쇄
자형을 사용자의 컴퓨터에서 채워 개인용 APKG를 만듭니다.

필요한 것은 다음과 같습니다.

- 같은 v2.1.0의 [JLPT-MAX-kanji-builder-2.1.0.zip](https://github.com/truthyblue/jlpt-max-deck/releases/download/v2.1.0/JLPT-MAX-kanji-builder-2.1.0.zip)
- 길벗 《일본어 상용한자 무작정 따라하기》 1·2권의 지원 소책자 PDF 2개
  - [1권 공식 자료 페이지](https://www.gilbut.co.kr/book/view?bookcode=BN003617)
  - [2권 공식 자료 페이지](https://www.gilbut.co.kr/book/view?bookcode=BN003669)
- Release에서 검증한 macOS 12+ 또는 Windows x64 컴퓨터
- 처음 실행할 때 필요한 프로그램을 받을 인터넷 연결

PowerShell이나 터미널을 열 필요가 없고 Python도 직접 설치하지 않습니다.
더블클릭 실행 파일이 빌더 전용 폴더에 필요한 프로그램을 자동으로 준비합니다.

공식 자료 페이지에서 제공 방식과 이용 조건을 확인하고 정상적으로 받은 원본을
사용하세요. 빌더는 상·하권의 SHA-256, 페이지 수와 표 구조를 함께 확인합니다.
PDF를 다시 저장·병합·최적화하거나 상·하권 순서를 바꾸면 지원 판본으로 인식하지
못할 수 있습니다.

## 1. ZIP 풀기

빌더 ZIP을 빈 폴더에 풉니다. ZIP 안에서 바로 실행하거나 이전 버전 폴더 위에
덮어쓰지 마세요.

Windows:

1. ZIP을 마우스 오른쪽 버튼으로 누르고 **모두 압축 풀기**를 선택합니다.
2. 새로 생긴 `JLPT-MAX-kanji-builder` 폴더를 엽니다.
3. `Windows에서 한자 확장 만들기.cmd`가 보이는지 확인합니다.

macOS:

1. ZIP을 더블클릭합니다.
2. 새로 생긴 `JLPT-MAX-kanji-builder` 폴더를 엽니다.
3. `Mac에서 한자 확장 만들기.command`가 보이는지 확인합니다.

`assets` 폴더에는 한글 뜻이 비어 있는 제작용 자산이 있습니다. 그 안의 파일을
열거나 Anki에 직접 가져오지 마세요.

## 2. 실행 파일 더블클릭

### Windows

1. `Windows에서 한자 확장 만들기.cmd`를 더블클릭합니다.
2. 첫 번째 PDF 선택창에서 1권(상권) PDF를 고릅니다.
3. 두 번째 PDF 선택창에서 2권(하권) PDF를 고릅니다.
4. 완료 안내가 나올 때까지 열린 창을 닫지 않습니다.

### macOS

1. `Mac에서 한자 확장 만들기.command`를 더블클릭합니다.
2. 첫 번째 PDF 선택창에서 1권(상권) PDF를 고릅니다.
3. 두 번째 PDF 선택창에서 2권(하권) PDF를 고릅니다.
4. 완료 안내가 나올 때까지 열린 창을 닫지 않습니다.

첫 실행은 빌드 도구와 Python을 자동으로 받으므로 시간이 걸릴 수 있습니다.
한자 자료와 PDF 내용은 외부 서비스로 보내지 않습니다. 빌더나 PDF가 있는 폴더
이름에 한글이나 띄어쓰기가 있어도 됩니다.

## 3. 결과 확인

성공하면 `build/kanji-addon` 폴더가 자동으로 열리고 다음 두 파일이 생깁니다.

- `build/kanji-addon/JLPT-MAX-kanji-addon-2.1.0.apkg`
- `build/kanji-addon/kanji-addon-build-report.json`

Anki에 넣을 파일은 이름이 `.apkg`로 끝나는 첫 번째 파일입니다. 리포트의
`status`가 `passed`, `unresolved`가 `0`인지 확인하세요. 빌더는 한자
2,337개의 읽기·쓰기 노트
4,674개와 이미지로 복원하는 자형
14개를 모두 검증한 뒤에만 APKG를 냅니다.

## 4. Anki에 추가

1. `JLPT-MAX-Deck-2.1.0.apkg`를 먼저 가져옵니다.
2. 생성된 `JLPT-MAX-kanji-addon-2.1.0.apkg`를 같은 컬렉션에 가져옵니다.
3. `JLPT MAX덱::일상무따` 아래의 읽기·쓰기 덱을 확인합니다.
4. 합산 수량이 노트 25,324개, 카드
   43,641개, 미디어 25,525개인지 확인합니다.

PDF 선택을 취소했다면 아무 파일도 바뀌지 않으므로 실행 파일을 다시 열면 됩니다.
다시 실행하면 기존 결과를 지우고 새로 만들지 먼저 묻습니다. 오류가 나면 빌더
폴더의 `kanji-builder.log`와 [문제 해결](troubleshooting.md)의 안내를 확인하세요.
전체 로그를 공개 issue에 붙이지 말고 개인 경로를 지운 오류 문구만 공유하세요.

## 개인정보와 저작권 경계

PDF, 페이지 이미지와 추출 문자열은 사용자 컴퓨터 안에서만 처리되며 원본 PDF는
결과 APKG에 포함되지 않습니다. 생성한 한자 덱 APKG는 개인 학습용으로만
보관하세요. issue에는 PDF, 책 본문, 생성 APKG 또는 개인 경로를 첨부하지 마세요.
