# 문제 해결

공개 빌더는 “가능한 만큼 만들기”보다 “정확히 같은 입력일 때만 만들기”를
우선합니다. 실패는 대개 데이터 손상이 아니라 안전장치가 차이를 발견했다는
뜻입니다. 검증을 우회하거나 bundle 파일을 고쳐 통과시키지 마세요.

[README로 돌아가기](../README.md) · [빌드 가이드](build.md) ·
[Anki 설치·가져오기](anki.md) ·
[저작권과 라이선스](privacy-and-licensing.md)

## 먼저 확인할 것

1. 소스 코드 태그, bundle ZIP, `.sha256`, `public-release.json`이 모두 같은 GitHub
   Release에서 왔는지 확인합니다.
2. ZIP SHA-256이 같은 Release의 `public-release.json`에 기록된
   `archive_sha256`과 같은지 확인합니다.
3. 이전 bundle 위에 덮어쓴 것이 아니라 새 폴더에 압축을 풀었는지 확인합니다.
4. PDF 폴더에 필요한 PDF 17개만 있는지 확인합니다.
5. PDF를 다시 저장, 병합, 분할, 압축 최적화하거나 인쇄한 파일이 아닌지
   확인합니다.
6. 출력 경로에 사용자가 만든 다른 파일이 섞여 있지 않은지 확인합니다.

## 오류별 조치

### `required PDFs are missing`

필요한 PDF 17개 중 하나 이상을 찾지 못했습니다.

- 해커스 10개, 동양북스 5개, 길벗 2개가 있는지 셉니다.
- 모든 PDF가 `-PdfRoot` 또는 첫 번째 인자로 지정한 폴더 아래에 있는지
  확인합니다. 하위 폴더는 허용됩니다.
- 출판사에서 받은 원본 파일을 사용합니다. 파일명을 바꾸는 것은 괜찮지만 내용을
  다시 저장하면 안 됩니다.

### `unsupported PDF hash`

폴더에 해당 release가 인식하지 못하는 PDF가 있거나, 필요한 자료의 판본이 바뀌었습니다.

- 관련 없는 PDF를 전용 PDF 폴더 밖으로 옮깁니다.
- 다운로드 과정에서 파일을 변환한 앱을 거치지 않았는지 확인합니다.
- 출판사가 파일을 새 판본으로 교체했다면 이전 hash에 맞추려고 변조하지 말고,
  새 source catalog가 포함된 릴리스를 기다리거나 issue에 판본 변경 사실만
  제보합니다. PDF 자체는 첨부하지 마세요.

### `duplicate supported PDF`

같은 PDF의 복사본을 둘 이상 발견했습니다. 원본 한 개만 남기고 복사본을
PDF 폴더 밖으로 옮기세요.

### `public bundle and builder source release differ`

빌더 코드와 bundle이 다른 릴리스입니다. ZIP 안의 일부 코드 파일을 별도
checkout의 파일로 교체하지 마세요. 같은 Release asset을 새 디렉터리에 다시
압축 해제합니다.

### `public bundle differs from the pinned release`

tracked `public-release.json`과 bundle manifest가 맞지 않습니다. 소스 코드 태그,
ZIP, checksum, pin을 같은 Release에서 다시 받으세요.

### `public bundle file tree changed`

bundle 안의 파일이 추가, 삭제 또는 변경됐습니다.

- 편집한 파일이 있다면 그 bundle은 버리고 원본 ZIP을 새 디렉터리에 풉니다.
- 동기화 도구나 보안 프로그램이 파일을 바꿨는지 확인합니다.
- 여러 릴리스의 bundle을 같은 폴더에 합치지 마세요.

### source row / layout / recipe / hash 오류

필요한 PDF에서 release recipe가 요구하는 값을 정확히 복원하지 못했습니다.
PDF를 재저장하거나 recipe를 직접 수정해서 우회하면 결과의 의미가 사라집니다.

- 원본 PDF와 release 조합을 다시 확인합니다.
- 새 폴더에 bundle을 다시 풉니다.
- 같은 오류가 반복되면 오류 메시지와 비민감 report 필드만 제보합니다.
- 실패한 실행의 APKG가 우연히 남아 있더라도 사용하거나 공유하지 마세요.

### reviewed kanji coverage / binding / KANJIDIC2 오류

KANJIDIC2 snapshot 또는 보충 한자 49자의 검토 원장이 release 계약과 다릅니다.
`open-data/kanjidic2.xml.gz`만 최신 파일로 바꾸거나 ledger를 편집하지 마세요.
snapshot, ledger와 builder가 함께 갱신된 공식 릴리스를 사용해야 합니다.

현재 릴리스의 KANJIDIC2 계약은 database `2026-200`, created `2026-07-19`입니다.

### `refusing to replace an unmanaged output root`

출력 경로에 공개 빌더가 관리한다고 확인할 수 없는 파일이 있습니다. 중요한 파일을
지우지 말고, 비어 있는 새 출력 경로를 지정하세요.

macOS:

```bash
bash scripts/build-public.sh \
  /absolute/path/to/my-jlpt-pdfs \
  /absolute/path/to/public-bundle \
  /absolute/path/to/new-public-release
```

Windows PowerShell:

```powershell
.\scripts\build-public.ps1 `
  -PdfRoot 'C:\Users\me\Documents\jlpt-pdfs' `
  -BundleRoot 'D:\jlpt\public-bundle' `
  -OutputRoot 'D:\jlpt\new-public-release'
```

### logical / semantic / count mismatch

필요한 필드 복원은 끝났지만 최종 deck 구조가 릴리스 기준과 달라졌습니다. 정상
릴리스에서는 발생하면 안 되는 hard failure입니다.

현재 기준은 다음과 같습니다.

- logical APKG hash:
  `dcbd421a4455438be350d78cd1b9b58dd6f660071a88ac317302419fa0951b86`
- 노트 15,996개
- 카드 21,897개
- 미디어 17,511개

APKG를 사용하지 말고 release 조합과 bundle 무결성을 다시 확인한 뒤 issue로
제보하세요.

## 실행 환경 문제

### `uv`를 찾을 수 없음

`uv`를 설치한 뒤 새 터미널을 열어 `uv --version`이 동작하는지 확인합니다.
Windows에서는 `winget install --id=astral-sh.uv -e`를 사용할 수 있습니다.

### Python 또는 package 설치 실패

빌더는 Python `>=3.13,<3.14`와 `uv.lock`의 정확한 의존성을 사용합니다.

- 첫 설치 시 네트워크 연결과 남은 디스크 공간을 확인합니다.
- system Python을 직접 바꾸기보다 제공된 build script를 다시 실행합니다.
- `uv.lock`을 수정하거나 임의 package version으로 대체하지 마세요.
- 사내 proxy나 TLS inspection 환경이라면 해당 네트워크 정책의 정상적인 `uv`
  설정을 사용합니다.

### macOS에서 shell script 실행 권한 오류

압축 도구가 실행 bit를 보존하지 못했을 수 있습니다. script 내용을 먼저 확인한
뒤 Bash로 직접 실행할 수 있습니다.

```bash
bash scripts/build-public.sh /absolute/path/to/my-jlpt-pdfs
```

### Windows에서 script 실행 정책 오류

script 내용을 먼저 확인하세요. 조직 정책이 허용한다면 현재 PowerShell process에
한해서 실행 정책을 바꾼 뒤 실행할 수 있습니다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\build-public.ps1 -PdfRoot 'C:\Users\me\Documents\jlpt-pdfs'
```

조직이 관리하는 장치에서는 관리자 정책을 우회하지 말고 담당자에게 문의하세요.

### 공간 부족 또는 강제 종료

빌드는 임시 작업 공간에서 APKG를 완성한 뒤 결과를 교체하므로 bundle, dependency
환경, 임시 결과와 최종 APKG를 위한 여유 공간이 필요합니다. 공간을 확보한 다음
같은 명령을 다시 실행하세요. 검증된 기존 결과가 있었다면 실패한 실행이 그것을
부분 결과로 덮어쓰지 않습니다.

## Anki 가져오기 문제

### APKG 파일이 보이지 않음

Anki에서 선택할 파일은 결과 폴더의
<code>JLPT-MAX덱-1.0.0.apkg</code> 하나입니다. JSON, TXT, 폴더 전체 또는
압축을 푼 파일은 선택하지 않습니다.

- Desktop은 파일 → 가져오기에서 APKG를 고릅니다.
- iPhone/iPad는 파일의 공유 메뉴에서 AnkiMobile을 선택합니다. Windows의 Apple
  기기 앱으로 USB 전송했다면 AnkiMobile의 Add/Export → Import from iTunes를
  사용합니다.
- Android는 파일을 AnkiDroid로 열거나 덱 목록의 ⋮ → 가져오기 → 덱
  패키지(.apkg)를 사용합니다.

### 휴대기기에서 가져오기가 멈추거나 공간 부족

가져오는 동안 전송용 APKG와 앱 안에 풀리는 미디어가 함께 존재하므로 APKG
파일 크기보다 넉넉한 여유 공간이 필요합니다. 다른 앱을 정리하고 가져오기를 다시
시작하세요. 덱과 음성을 확인한 뒤 휴대기기의 전송용 APKG는 삭제해도 됩니다.

### 카드가 보이지만 음성이 나오지 않음

먼저 기기의 음량, 음소거와 출력 장치를 확인합니다. APKG 직접 가져오기가 끝나기
전에 앱을 닫았다면 같은 APKG를 다시 가져오세요.

### 여러 기기의 학습 진도가 서로 다름

같은 APKG를 여러 기기에 직접 가져오는 것은 덱과 미디어를 각각 설치하는
방법입니다. 동기화하지 않으면 복습 일정과 학습 기록은 기기마다 따로 쌓이는 것이
정상입니다. 같은 AnkiWeb 계정으로 로그인한 뒤 각 기기에서 동기화를 실행하세요.

처음 연결하는 비어 있는 AnkiWeb이라면 APKG를 가져온 기준 기기에서
업로드(Upload), 다른 기기에서 다운로드(Download)를 선택합니다. 이미 양쪽에
서로 다른 자료가 있다면 먼저 백업하고
[Anki 공식 동기화 안내](https://docs.ankiweb.net/syncing.html)를 따르세요.
미디어 17,511개는 첫 동기화에 시간이 걸릴 수 있으므로 당장 공부할 기기에는
APKG를 직접 가져오는 편이 빠릅니다.

## 안전한 issue 작성

포함해도 좋은 정보:

- macOS 또는 Windows version과 CPU architecture
- 사용한 release 이름
- 개인 경로를 `<PDF_ROOT>`처럼 가린 실행 명령
- 오류 메시지와 stack trace에서 개인 경로를 가린 내용
- report의 `status`, `unresolved`, count, policy version

포함하면 안 되는 정보:

- PDF 또는 PDF 본문 캡처
- PDF에서 추출한 문자열·표·JSONL
- 완성 APKG
- `source-proof.json` 원문
- bundle에서 분리한 데이터·MP3
- 실명이나 개인 폴더 구조가 드러나는 전체 경로
