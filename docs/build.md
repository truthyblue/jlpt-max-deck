# 공개판 빌드 가이드

이 문서는 공개 릴리스로 개인용 `JLPT MAX덱` APKG를 만드는 전체 절차입니다.
완성 덱은 배포되지 않으며, 사용자가 정식으로 취득한 PDF 17개가 모두 있어야
빌드할 수 있습니다. 완성 APKG에는 PDF에서 복원한 출판사 파생 내용이 포함될 수
있으므로 결과물은 개인 학습용으로만 보관합니다.

[README로 돌아가기](../README.md) · [Anki 설치·가져오기](anki.md) ·
[문제 해결](troubleshooting.md) ·
[저작권과 라이선스](privacy-and-licensing.md)

## 1. 준비물

- macOS 또는 Windows x64
- `uv`
- 빌드 컴퓨터의 여유 저장 공간 8GB 이상 권장 (완성 APKG 약 840MB)
- 같은 GitHub Release의 빌더 코드와 아래 세 asset
  - `JLPT-MAX-public-bundle.zip`
  - `JLPT-MAX-public-bundle.zip.sha256`
  - `public-release.json`
- 필요한 PDF 17개의 정확한 판본

`uv`는 Python 3.13과 `uv.lock`에 고정된 패키지를 준비합니다. 첫 의존성 설치에는
네트워크가 필요할 수 있습니다. 의존성 준비가 끝난 뒤 덱 생성 단계에서는 PDF를
업로드하지 않으며 OCR, LLM, TTS, 출판사 서버 또는 외부 API를 호출하지 않습니다.

### 필요한 PDF 17개

| 출판사 | 필요한 자료 | 공식 취득 경로 | 파일 | 페이지 |
| --- | --- | --- | ---: | ---: |
| 해커스 | N1~N5 최신 어휘 PDF와 단어장 PDF | [N1](https://japan.hackers.com/?r=japan&m=mp3&c=mp3%2Fmp3_free&p=1&book_cd=863) · [N2](https://japan.hackers.com/?r=japan&m=mp3&c=mp3%2Fmp3_free&p=1&book_cd=1356) · [N3](https://japan.hackers.com/?r=japan&m=mp3&c=mp3%2Fmp3_free&p=1&book_cd=1337) · [N4](https://japan.hackers.com/?r=japan&m=mp3&c=mp3%2Fmp3_free&p=1&book_cd=311) · [N5](https://japan.hackers.com/?r=japan&m=mp3&c=mp3%2Fmp3_free&p=1&cate4_cd=&lec_lvl_cd=&book_cd=415) | 10 | 442 |
| 동양북스 | `일단 합격 JLPT 완벽 대비` 단어장 N1~N5 | [N1](https://www.dongyangbooks.com/book/book_view.asp?goods_code=2968&menu_1=jp&menu_2=jp_JLPT) · [N2](https://www.dongyangbooks.com/book/book_view.asp?goods_code=2969&menu_1=jp&menu_2=jp_JLPT) · [N3](https://www.dongyangbooks.com/book/book_view.asp?goods_code=2970&menu_1=jp&menu_2=jp_JLPT) · [N4](https://www.dongyangbooks.com/reference/reference_010100-view.asp?bidx=11&bsno=44978) · [N5](https://www.dongyangbooks.com/reference/reference_010100-view.asp?bidx=11&bsno=44979) | 5 | 246 |
| 길벗 | `일본어 상용한자 무작정 따라하기` 1·2 핵심정리·훈련용 소책자 PDF | [1권](https://www.gilbut.co.kr/book/view?bookcode=BN003617) · [2권](https://www.gilbut.co.kr/book/view?bookcode=BN003669) | 2 | 97 |
| **합계** |  |  | **17** | **785** |

이 PDF들은 공개 릴리스에 포함되지 않습니다. 일부 자료는 로그인이나 구매 도서 인증이 필요할 수
있으므로 각 출판사의 정식 경로에서 직접 내려받으세요. 빌더는 로그인, 구매 인증, 접근 제어
또는 DRM을 우회하지 않으며 파일을 대신 내려받지 않습니다.

17개 파일을 다른 PDF가 없는 하나의 전용 폴더 아래에 두세요. 파일명과 하위 폴더
구조는 자유롭습니다. 빌더는 폴더를 재귀 탐색하므로 지원하지 않는 PDF가 함께 있으면
중단합니다. `public-sources.json`에 고정된 SHA-256, byte 수, page 수로 각 판본을
식별하며, PDF를 다시 저장하거나 최적화하면 내용이 눈에 같아 보여도 hash가 바뀌어
필요한 판본으로 인식되지 않습니다.

## 2. release asset 확인

소스 코드 태그와 bundle ZIP, checksum, release pin은 반드시 같은 Release에서
받으세요. ZIP 전송값은 tracked
[`config/public-release.json`](../config/public-release.json)을 단일 기준으로 사용합니다.

| 항목 | 값 |
| --- | --- |
| ZIP 크기 | `public-release.json`의 `archive_bytes` |
| ZIP SHA-256 | `public-release.json`의 `archive_sha256` |
| logical APKG hash | `8ba7f72713f2889bf6d842324b596140c4d0f78a77cc97c68f7157bb1c3b97ea` |

### macOS

세 파일을 같은 폴더에 둔 다음 실행합니다.

```bash
(
  set -euo pipefail
  expected="$(awk -F'"' '/"archive_sha256"/ {print $4}' public-release.json)"
  actual="$(shasum -a 256 JLPT-MAX-public-bundle.zip | awk '{print $1}')"
  test "$actual" = "$expected"
  shasum -a 256 -c JLPT-MAX-public-bundle.zip.sha256
  unzip JLPT-MAX-public-bundle.zip -d build
)
```

### Windows PowerShell

```powershell
$Pin = Get-Content .\public-release.json -Raw | ConvertFrom-Json
$Expected = (Get-Content .\JLPT-MAX-public-bundle.zip.sha256).Split()[0]
$Actual = (Get-FileHash .\JLPT-MAX-public-bundle.zip -Algorithm SHA256).Hash.ToLower()
if ($Actual -ne $Expected.ToLower()) { throw "Public bundle checksum mismatch" }
if ($Actual -ne $Pin.archive_sha256.ToLower()) { throw "Public release pin mismatch" }
Expand-Archive .\JLPT-MAX-public-bundle.zip -DestinationPath .\build
```

checksum은 전송 중 손상이나 서로 다른 release의 혼합을 잡아냅니다. 배포 주체의
신원을 대신 증명하는 것은 아니므로, asset과 소스 코드 태그가 공식 Release에 함께
게시된 것인지도 확인하세요.

압축을 풀면 `build/public-bundle`이 생깁니다. 이 폴더 안의 파일을 편집하거나
다른 release의 파일과 섞지 마세요. 빌더는 bundle 파일 트리 전체를 검증하며,
변경을 발견하면 의도적으로 중단합니다.

## 3. 덱 만들기

아래 예시에서 PDF 폴더는 bundle 밖에 둡니다.

### macOS

```bash
cd build/public-bundle
bash scripts/build-public.sh /absolute/path/to/my-jlpt-pdfs
```

### Windows x64 PowerShell

```powershell
Set-Location .\build\public-bundle
.\scripts\build-public.ps1 -PdfRoot 'C:\Users\me\Documents\jlpt-pdfs'
```

스크립트는 다음 순서로 동작합니다.

1. Python 3.13과 lockfile 의존성을 전용 환경에 준비합니다.
2. PDF 17개의 SHA-256, byte 수, page 수를 검사합니다.
3. PDF text layer에서 release recipe가 지시한 필요 필드만 로컬 복원합니다.
4. 모든 입력 자료·recipe·review binding을 검증합니다.
5. 공개 bundle의 템플릿과 hash-pinned MP3로 APKG를 만듭니다.
6. note/card/media 수와 logical APKG hash를 release 계약과 비교합니다.
7. 전부 통과한 결과만 `public-release`로 승격합니다.

기본 출력은 압축을 푼 bundle의 sibling입니다.

```text
build/
├── public-bundle/
└── public-release/
    ├── JLPT-MAX덱-1.0.0.apkg
    ├── public-build-report.json
    ├── source-proof.json
    ├── public-materialization-report.json
    └── ...
```

Anki에서 선택할 파일은 <code>JLPT-MAX덱-1.0.0.apkg</code> 하나입니다. 주요
나머지 파일은 빌드 검증과 오류 진단용입니다.

| 결과 | 용도 | Anki에서 선택 |
| --- | --- | --- |
| <code>JLPT-MAX덱-1.0.0.apkg</code> | 노트·카드·미디어를 담은 완성 덱 | **예** |
| <code>public-build-report.json</code> | 최종 검증 상태와 수량 요약 | 아니요 |
| <code>public-materialization-report.json</code> | PDF 복원 검증 리포트 | 아니요 |
| <code>source-proof.json</code> | 사용한 PDF와 source 위치의 로컬 증명 | 아니요·공유 금지 |
| 그 밖의 JSON·JSONL·TXT·HTML | manifest, 업데이트 비교, 렌더 샘플 | 아니요 |

APKG를 압축 해제하거나 결과 폴더 전체를 Anki에서 선택하지 마세요. 성공한 자동
실행은 결과 폴더를 Finder 또는 파일 탐색기로 열고, 열지 못하면 마지막에 정확한
경로를 출력합니다.

### bundle 또는 출력 경로 바꾸기

macOS:

```bash
bash scripts/build-public.sh \
  /absolute/path/to/my-jlpt-pdfs \
  /absolute/path/to/public-bundle \
  /absolute/path/to/public-release
```

Windows PowerShell:

```powershell
.\scripts\build-public.ps1 `
  -PdfRoot 'C:\Users\me\Documents\jlpt-pdfs' `
  -BundleRoot 'D:\jlpt\public-bundle' `
  -OutputRoot 'D:\jlpt\public-release'
```

새 출력 경로를 쓰는 경우 비어 있는 전용 폴더를 선택하세요. 빌더는 관리되지 않은
파일이 있는 폴더를 덮어쓰지 않습니다.

## 4. 성공 결과 확인

정상 결과의 `public-build-report.json`은 최소한 다음 계약을 만족합니다.

- `status`가 `passed`
- `unresolved`가 `0`
- `expected_logical_apkg_hash`가
  `8ba7f72713f2889bf6d842324b596140c4d0f78a77cc97c68f7157bb1c3b97ea`
- 노트 15,996개, 카드 21,897개(`어휘(히라가나)` 카드 101개 포함)
- 미디어 17,489개: MP3 17,475개와 정적 파일 14개

공개 콘텐츠 구성은 다음과 같습니다.

| 노트 종류 | 수 |
| --- | ---: |
| 어휘 | 5,800 |
| 실전 문제 | 7,850 |
| 한자 | 2,337 |
| 참조표 | 9 |
| **합계** | **15,996** |

APKG는 ZIP container metadata 때문에 운영체제별 byte hash가 달라질 수 있습니다.
동일성의 기준은 APKG 파일 자체의 SHA-256이 아니라 canonical logical manifest의
hash입니다. 이 hash는 note ID, Anki GUID, 카드와 덱 구조, source provenance,
템플릿과 참조 미디어를 묶습니다.

`source-proof.json`에는 사용한 PDF hash와 source 좌표가 기록됩니다. 문제를
제보하더라도 이 파일 전체를 공개하지 말고, 비민감한 상태와 오류 메시지만
공유하세요.

## 5. Anki에 가져오기

Anki가 처음이라면 [Anki 설치와 기기별 가져오기](anki.md)를 먼저 확인하세요.
완성 APKG는 Desktop, iPhone/iPad, Android에 각각 직접 가져올 수 있습니다.
미디어 17,489개가 들어 있으므로 휴대기기에 APKG를 로컬 전송해 직접 가져오면
대용량 음성을 별도로 내려받는 시간을 기다리지 않고 바로 학습할 수 있습니다.

### Windows·macOS Anki Desktop

1. Anki Desktop을 실행합니다.
2. 파일(File) → 가져오기(Import)를 누릅니다.
3. 결과 폴더의 <code>JLPT-MAX덱-1.0.0.apkg</code>를 선택합니다. 파일을
   더블클릭해도 됩니다.
4. 첫 가져오기에서 학습 진척도 관련 옵션이 보이면 켜지 않고 가져옵니다.
5. 덱 목록에 JLPT MAX덱이 생겼는지 확인합니다.

### iPhone·iPad AnkiMobile

1. App Store의 공식 유료 앱 AnkiMobile Flashcards를 설치합니다.
2. Mac은 AirDrop, Windows는 Apple 기기 앱의 USB 파일 공유로 APKG를 로컬
   전송합니다.
3. AirDrop 파일은 공유 → AnkiMobile로 엽니다. USB로 넣었다면 AnkiMobile의
   Add/Export → Import from iTunes를 사용합니다.
4. 덱 목록의 JLPT MAX덱에서 카드와 음성을 확인합니다.

### Android AnkiDroid

1. Google Play의 무료 앱 AnkiDroid Flashcards를 설치합니다.
2. USB 또는 기기 간 로컬 전송으로 APKG를 Android 저장 공간에 복사합니다.
3. 파일을 AnkiDroid로 열거나 덱 목록 메뉴의 가져오기(Import)에서 선택합니다.
4. 덱 목록의 JLPT MAX덱에서 카드와 음성을 확인합니다.

AnkiApp, Anki Pro처럼 이름이 비슷한 다른 앱은 지원 대상이 아닙니다. 각 앱은
[Anki 공식 앱 페이지](https://apps.ankiweb.net/)에서 이동해 설치하세요.

완전히 처음 쓰는 사용자는 기본 프로필로 시작해도 됩니다. 이미 다른 JLPT MAX
시험판이나 variant를 사용 중이면 Desktop 또는 AnkiMobile의 별도 프로필에서
먼저 확인하는 편이 안전합니다. AnkiDroid는 기존 컬렉션을 백업한 뒤
가져오세요. 서로 다른 variant의 기존 컬렉션 병합이나 무손실 전환은 지원
계약이 아닙니다.

같은 APKG를 여러 기기에 직접 가져오면 별도 미디어 전송을 기다리지 않고 각
기기에서 바로 시작할 수 있습니다. 여러 기기의 복습 기록과 학습 상태를
이어가려면 [AnkiWeb 무료 계정](https://ankiweb.net/account/signup)으로 로그인한
뒤 동기화를 실행하세요. 첫 미디어 동기화는 오래 걸릴 수 있으므로 당장 공부할
기기에 APKG를 먼저 직접 가져오는 편이 빠릅니다. 비어 있는 AnkiWeb의 첫
동기화에서는 APKG를 가져온 기준 기기에서 업로드(Upload)를 선택하고, 다른
기기에서는 다운로드(Download)를 선택합니다.

최종 APKG는 개인 학습용으로만 보관하세요. 개인 AnkiWeb 동기화와 별개로 APKG,
PDF, PDF 추출물,
`source-proof.json` 또는 bundle 안의 MP3·recipe를 별도 패키지로 다시 배포하면
안 됩니다.

## 재실행과 업데이트

같은 명령을 다시 실행하면 빌더는 새 결과를 임시 폴더에서 완성·검증한 뒤 기존의
검증된 출력과 교체합니다. 실패하면 기존 출력은 유지됩니다.

새 릴리스로 업데이트할 때는 소스 코드 태그, bundle ZIP, checksum, `public-release.json`
네 항목을 모두 같은 릴리스로 교체하세요. 이전 bundle 위에 새 파일을 덮어쓰지
말고 새 디렉터리에 압축을 푸는 것이 안전합니다.

현재 KANJIDIC2 snapshot은 database version `2026-200`, creation date
`2026-07-19`입니다. snapshot과 한자 검토 binding도 bundle manifest에 고정되어
있으므로 임의로 파일만 갱신할 수 없습니다.
