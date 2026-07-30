# 일상무따 한자 확장 만들기

이 도구는 지원 PDF 2개를 사용자 컴퓨터에서 읽어
`JLPT MAX덱::일상무따` 한자 2,337개의 개인용 APKG를 만듭니다. 완성된 APKG는
같은 v1.0.1 기본 덱을 가져온 Anki 컬렉션에 추가합니다.

## 필요한 것

- 길벗 《일본어 상용한자 무작정 따라하기》 1·2권의 지원 소책자 PDF 2개
- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- macOS 또는 Windows x64

PDF와 그 페이지 이미지는 외부로 전송되지 않습니다. 빌더는 두 PDF의 한자 표에서
한글 뜻과 일부 인쇄 자형만 읽어 로컬 APKG를 만들며, 원본 PDF를 결과물에 넣지
않습니다.

## 실행

macOS:

```bash
./scripts/build-kanji-addon.sh "/경로/상권.pdf" "/경로/하권.pdf"
```

Windows PowerShell:

```powershell
.\scripts\build-kanji-addon.ps1 -UpperPdf "C:\경로\상권.pdf" -LowerPdf "C:\경로\하권.pdf"
```

성공하면 `build/kanji-addon/JLPT-MAX-kanji-addon-1.0.1.apkg`와 검증 리포트가
생깁니다. 먼저 릴리스의 기본 덱 APKG를 Anki에 가져온 다음 이 APKG를 추가로
가져오세요.

PDF 해시·페이지 수·표의 2,337개 위치 중 하나라도 예상과 다르면 결과를 내지 않고
중단합니다.
