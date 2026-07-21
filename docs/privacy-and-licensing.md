# 저작권과 라이선스 경계

완성 APKG에는 사용자의 PDF에서 복원한 출판사 파생 필드가 들어갈 수 있습니다.
출판사 PDF와 그 내용을 담은 완성 덱은 배포하지 않고, 정식으로 취득한 PDF 17개를
가진 사용자가 개인 학습용 APKG를 직접 만듭니다.

JLPT MAX Deck의 공개 방식은 “빌더 코드를 공개한다”와 “교재 또는 완성 덱을
배포한다”를 명확히 분리합니다. 이 페이지는 실무적인 요약이며 법률 자문이
아닙니다. 정확한 배포 조건은 저장소의 [LICENSE](../LICENSE)와
[NOTICE](../NOTICE)가 우선합니다.

[README로 돌아가기](../README.md) · [빌드 가이드](build.md) ·
[Anki 설치·가져오기](anki.md) · [v1.0.0 릴리스 노트](releases/v1.0.0.md)

## PDF는 어디로 가나요?

사용자가 지정한 PDF 폴더는 로컬 빌드 프로세스만 읽습니다. 덱 생성 단계에서
PDF, PDF page image, 추출 문자열 또는 완성 APKG를 업로드하는 코드 경로는
없습니다.

| 데이터 | 처리 위치 | 네트워크 전송 | 기본 결과 |
| --- | --- | --- | --- |
| 사용자 PDF 17개 | 사용자 컴퓨터 | 없음 | 원본 위치에 그대로 유지 |
| PDF에서 복원한 필드 | 임시 로컬 작업 공간 | 없음 | 검증 후 APKG에 반영 |
| source proof | 로컬 출력 폴더 | 없음 | `source-proof.json` |
| 완성 APKG | 로컬 출력 폴더 | 없음 | 개인 학습용 파일 |
| 공개 bundle | GitHub Release에서 다운로드 | 다운로드만 | hash 검증 후 로컬 사용 |
| 카드의 `덱 안내 · 업데이트` 링크 | 사용자가 누를 때만 GitHub Pages 열기 | 일반 웹 접속만 | PDF·카드 내용 전송 없음 |

첫 실행에는 `uv`가 Python 3.13과 `uv.lock`에 고정된 오픈소스 패키지를
설치하기 위해 네트워크를 사용할 수 있습니다. 이 준비가 끝난 뒤 실제 덱 생성은
OCR, LLM, TTS, 분석 서비스, 출판사 서버 또는 외부 API를 호출하지 않습니다.

v1.0.0은 JLPT MAX덱 루트 덱 설명과 모든 카드 답 아래에 프로젝트 안내
링크를 넣습니다. 이 링크는 사용자가 직접 누를 때만 열립니다. 카드를
보거나 공부하는 것만으로 외부 사이트에 자동 접속하지 않습니다. 링크를 눌러도
PDF, PDF에서 가져온 뜻, 예문, 학습 기록을 주소에 넣거나 프로젝트 사이트로
보내지 않습니다.

공개 웹 페이지에는 외부 폰트, 외부 이미지, analytics, tracking pixel 또는
제3자 스크립트를 넣지 않습니다. GitHub Pages와 Releases 자체의 처리에는
GitHub의 정책이 적용됩니다.

## 왜 source proof가 생기나요?

공개 bundle은 출판사의 한국어 원문을 담는 대신 source 식별자, page·section·row
좌표, 구조 index와 hash recipe를 담습니다. 빌더는 PDF text layer에서 필요한 값을
찾아 recipe의 hash와 대조합니다.

`source-proof.json`은 실제로 어떤 PDF와 source 위치가 사용됐는지 로컬에서
검증할 수 있게 남기는 결과입니다. 이 파일은 공식 릴리스에 포함되지 않으며,
사용자가 외부에 게시해서도 안 됩니다. 문제 제보에는 PDF, 추출 문자열,
source proof 원문 대신 오류 종류와 비민감한 report 상태만 사용하세요.

## 세 가지 권리 경계

### 1. 빌더 코드

Python, shell, PowerShell 등 빌더 소프트웨어는
`AGPL-3.0-or-later`로 배포됩니다. 라이선스 조건에 따라 실행, 연구, 수정하고
수정 코드를 공유할 수 있습니다. 수정판을 배포하거나 네트워크 서비스로
제공할 때의 소스 코드 공개 의무는 AGPL 본문을 따릅니다.

AGPL은 독립적으로 라이선스된 데이터, 사용자 PDF, 생성 오디오 또는 빌더 출력에
단지 같은 archive에 있거나 빌더가 처리했다는 이유만으로 자동 적용되지 않습니다.

### 2. 공개 bundle

bundle에는 여러 종류의 자료가 함께 있습니다.

- source와 layout의 hash-pinned 계약
- 출판사 원문을 포함하지 않는 reconstruction recipe
- 프로젝트가 생성·검토한 예문, 번역, 실전 문제와 템플릿
- 미리 생성하고 hash로 고정한 MP3
- KANJIDIC2 snapshot과 EDRDG 라이선스 원문

프로젝트 recipe·생성 콘텐츠·MP3는 NOTICE에 따라 공식 bundle을 검증하고,
일치하는 공개 빌더로 개인 학습용 APKG를 만드는 범위에서 사용할 수 있습니다.
별도 허가나 자체 오픈 라이선스가 있는 부분을 제외하면 bundle을 재포장하거나,
데이터·음성 모음을 추출해 다시 게시하거나, 파생 덱 다운로드를 제공하는 권한은
부여되지 않습니다.

KANJIDIC2는 EDRDG가 제작하며 EDRDG 라이선스, 현재 CC BY-SA 4.0 조건으로
제공됩니다. 공개 bundle은 원본 gzip snapshot과 라이선스 문서를 함께 싣고,
정확한 SHA-256과 metadata를 manifest에 기록합니다. 현재 snapshot은 database
`2026-200`, created `2026-07-19`입니다. KANJIDIC2에 직접 부여된 권리는 이
프로젝트의 개인용 bundle 조건으로 축소되지 않습니다.

MP3는 AivisSpeech와 별도 voice model로 미리 생성된 출력 자산입니다. 엔진과
voice model binary는 bundle에 없고, 사용자의 덱 빌드에도 필요하지 않습니다.
정확한 모델, 생성 provenance와 개별 라이선스는 NOTICE와 bundle manifest를
확인하세요.

프로젝트 사이트에는 `site/assets/demo-dasu-word.mp3`와
`site/assets/demo-dasu-example.mp3`, `site/assets/demo-dasu-example-2.mp3`,
`site/assets/demo-dasu-example-3.mp3` 네 파일만 고정 청취 데모로 포함됩니다.
각각 `出す`의 단어 발음과 카드에 표시된 세 예문 낭독을 들려주는 샘플이며,
AivisSpeech 1.2.0의 `まい` 모델(Aivis Common Model License 1.0)로 생성한 비공식
합성 음성입니다. 이 예외는 사이트에서 네 고정 샘플을 듣기 위한 것일 뿐, bundle의
MP3 모음이나 이를 포함한 APKG를 추출, 재포장 또는 재배포할 권한을 부여하지
않습니다.

사이트에는 카드 기능을 설명하기 위한 고정 WebP 샘플 17개도 포함됩니다. 이 화면은
전체 덱이나 출판사 원문 데이터셋을 대신하는 배포물이 아니며, 현재 빌드의 개별
뜻·예문 수·학습 우선순위와 달라질 수 있습니다. 샘플의 포함은 bundle 콘텐츠나
완성 APKG를 추출·재포장·재배포할 권한을 부여하지 않습니다.

### 3. 사용자 PDF와 완성 APKG

출판사 PDF의 저작권, 데이터베이스권, 상표권과 그 밖의 권리는 각 권리자에게
남습니다. 빌더 코드의 AGPL이나 이 프로젝트의 공개는 PDF를 복제·공유할 권한,
구매 인증을 우회할 권한 또는 출판사 파생 콘텐츠를 재배포할 권한을 주지 않습니다.

완성 APKG에는 사용자의 PDF에서 로컬 복원한 출판사 파생 필드가 들어갈 수
있습니다. 따라서 결과물은 **개인 학습용**입니다.

다음 항목을 업로드, 미러링, 판매, 공유 또는 다른 사람에게 전달하지 마세요.

- 필요한 PDF와 그 복사본
- PDF에서 추출한 문자열이나 표
- `source-proof.json`
- 완성 APKG
- bundle에서 분리한 MP3·recipe·생성 콘텐츠 모음

여기서 금지하는 업로드는 APKG나 생성 콘텐츠를 공유 가능한 파일, 공개 링크,
일반 클라우드 또는 다른 사람에게 배포하는 행위입니다. 같은 사용자가 자신의
개인 기기 사이에서 학습 상태를 이어가기 위해 비공개 AnkiWeb 계정으로 동기화하는
것은 개인 학습 흐름으로 봅니다. 계정 접근 권한을 공유하거나 다른 사람이 덱에
접근할 수 있게 해서는 안 되며, AnkiWeb과 원자료에 독립적으로 적용되는 약관은
사용자가 확인해야 합니다.

개선 사항을 공유하고 싶다면 완성 덱 대신 AGPL 빌더 코드 변경으로 기여하세요.

## 공개 릴리스에 포함되는 것과 제외되는 것

| 포함 | 제외 |
| --- | --- |
| 공개 빌더 코드 | 출판사 PDF |
| source/layout hash 계약 | 출판사 한국어 원문 dump |
| 원문 없는 reconstruction recipe | PDF page image와 OCR 산출물 |
| 생성·검토 콘텐츠와 hash-pinned MP3 | 완성 APKG |
| KANJIDIC2 snapshot + EDRDG license | 사용자별 `source-proof.json` |
| bundle·logical manifest와 checksum | 작성·검토용 작업 이력 |

## 오류 제보 시 안전하게 공유하기

공개 issue에는 다음만 남기는 것을 권장합니다.

- 운영체제와 CPU architecture
- 사용한 release 이름
- 실행한 명령에서 개인 경로를 일반화한 형태
- 오류 메시지
- `status`, `unresolved`, count, policy version 같은 비민감 report 필드

PDF 파일, PDF hash 전체 목록, 책의 본문·표, 화면 캡처, 추출 JSONL,
`source-proof.json`, APKG를 첨부하지 마세요. 경로에 실명이 들어 있다면 오류
메시지에서도 먼저 지우세요.

## 명칭과 보증

Anki, JLPT, 해커스, 동양북스, 길벗, EDRDG와 그 제품명은 호환 대상, 시험 명칭과
자료 출처를 식별하기 위해 사용됩니다. 공식 제휴, 후원 또는 보증을 뜻하지 않습니다.
소프트웨어와 데이터는 각 라이선스가 허용하는 범위에서 별도 보증 없이 제공됩니다.
