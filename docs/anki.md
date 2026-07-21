# Anki 설치와 기기별 덱 가져오기

이 문서는 Anki를 처음 쓰는 사람을 위한 설치·가져오기 안내입니다. 덱 빌드는
macOS 또는 Windows x64 컴퓨터에서 하지만, 완성된
<code>JLPT-MAX덱-1.0.0.apkg</code>는 컴퓨터, iPhone/iPad, Android에 각각 직접
가져올 수 있습니다.

[README로 돌아가기](../README.md) · [덱 빌드 가이드](build.md) ·
[문제 해결](troubleshooting.md)

## 1. 어떤 앱을 설치하나요?

이름이 비슷한 비공식 앱 대신 [Anki 공식 앱 페이지](https://apps.ankiweb.net/)에서
각 스토어로 이동하세요.

| 공부할 기기 | 설치할 앱 | 비용 | APKG 가져오기 |
| --- | --- | --- | --- |
| Windows·macOS | Anki Desktop | 무료 | 파일 → 가져오기 |
| iPhone·iPad | AnkiMobile Flashcards | 유료 | 파일의 공유 메뉴에서 AnkiMobile 선택 |
| Android | AnkiDroid Flashcards | 무료 | 파일 열기 또는 덱 목록의 가져오기 |
| 웹 브라우저 | AnkiWeb | 무료 동기화 서비스 | APKG 직접 가져오기 불가 |

AnkiApp, Anki Pro처럼 이름이 비슷한 앱은 이 가이드의 대상이 아닙니다.

## 2. Windows·macOS에 Anki Desktop 설치

### Windows x64

1. 설정 → 시스템 → 정보에서 시스템 종류가 x64 기반인지 확인합니다.
2. [Anki 공식 다운로드 페이지](https://apps.ankiweb.net/)에서 Windows x64 설치
   파일을 받습니다.
3. 설치 파일을 실행하고 화면 안내에 따라 설치합니다.
4. 시작 메뉴에서 Anki를 실행합니다.

현재 Windows 공식 설치 조건은
[Anki Windows 설치 문서](https://docs.ankiweb.net/platform/windows/installing.html)가
우선합니다.

### macOS

1. Apple 메뉴 → 이 Mac에 관하여에서 칩이 Apple M 계열인지 Intel인지
   확인합니다.
2. [Anki 공식 다운로드 페이지](https://apps.ankiweb.net/)에서 칩에 맞는 설치
   파일을 받습니다.
3. 다운로드한 파일을 열고 Anki를 Applications(응용 프로그램) 폴더로
   드래그합니다.
4. 응용 프로그램 폴더에서 Anki를 실행합니다.

현재 macOS 공식 설치 조건은
[Anki macOS 설치 문서](https://docs.ankiweb.net/platform/mac/installing.html)가
우선합니다.

처음 쓰는 사람은 기본 프로필 그대로 시작해도 됩니다. 이미 다른 JLPT MAX
시험판을 쓰고 있어 분리하고 싶을 때만 파일 → 프로필 전환에서 별도 프로필을
만드세요.

## 3. iPhone·iPad에 AnkiMobile 설치

1. [App Store의 AnkiMobile 페이지](https://apps.apple.com/app/ankimobile-flashcards/id373493387)를
   엽니다.
2. 앱 이름이 AnkiMobile Flashcards이고 제공자가 Anki Software, LLC인지
   확인합니다. AnkiMobile은 공식 유료 앱입니다.
3. 설치한 뒤 한 번 실행해 덱 목록이 열리는지 확인합니다.

최신 앱 요구 사항과 가격은 App Store 표시가 우선합니다.
기존 AnkiMobile 컬렉션과 분리해 확인하려면
[설정 → Profiles](https://docs.ankimobile.net/preferences.html#profiles)에서 별도
프로필을 추가할 수 있습니다.

### APKG를 로컬로 옮겨 가져오기

완성 APKG는 개인 학습용이므로 이메일, 메신저, 공개 링크나 클라우드에 올리지
말고 AirDrop 또는 USB 파일 공유처럼 기기 사이의 로컬 전송을 사용하세요.

Mac에서 iPhone/iPad로:

1. Finder에서 <code>JLPT-MAX덱-1.0.0.apkg</code>를 AirDrop으로 보냅니다.
2. iPhone/iPad에서 전송을 수락합니다.
3. AnkiMobile이 바로 열리지 않으면 파일 앱에서 APKG를 길게 누른 뒤
   공유 → AnkiMobile을 선택합니다. 보이지 않으면 더 보기에서 찾습니다.

Windows에서 iPhone/iPad로:

1. Windows의 [Apple 기기 앱](https://support.apple.com/ko-kr/120402)을
   설치합니다.
2. iPhone/iPad를 USB로 연결하고 기기에서 이 컴퓨터를 신뢰하도록 허용합니다.
3. Apple 기기 앱에서 해당 기기와 파일을 열고 AnkiMobile을 선택합니다.
4. APKG를 AnkiMobile 파일 영역에 추가합니다.
5. AnkiMobile 덱 목록 왼쪽 아래의 Add/Export를 누르고
   Import from iTunes를 선택합니다. 메뉴 이름에 iTunes가 남아 있어도 현재
   Windows 전송 도구는 Apple 기기 앱입니다.

가져오기 완료 뒤 JLPT MAX덱을 열어 글자와 음성이 정상인지 확인합니다.
공식 메뉴 설명은
[AnkiMobile 덱 목록](https://docs.ankimobile.net/deck-list.html)과
[덱 가져오기](https://docs.ankimobile.net/shared-decks.html)를 참고하세요.

## 4. Android에 AnkiDroid 설치

1. [Google Play의 AnkiDroid 페이지](https://play.google.com/store/apps/details?id=com.ichi2.anki)를
   엽니다.
2. 앱 이름이 AnkiDroid Flashcards, 개발자가 AnkiDroid Open Source Team,
   패키지 이름이 <code>com.ichi2.anki</code>인지 확인합니다.
3. 처음 쓰는 경우 Get started를 누릅니다. APKG를 고르는 데 모든 파일 접근
   권한은 필요하지 않습니다.

### APKG를 로컬로 옮겨 가져오기

1. USB 케이블이나 기기 간 로컬 전송으로
   <code>JLPT-MAX덱-1.0.0.apkg</code>를 Android의 다운로드 폴더에 복사합니다.
2. Android 파일 앱에서 APKG를 누르고 AnkiDroid로 엽니다.
3. 자동으로 열리지 않으면 AnkiDroid 덱 목록의 ⋮ 메뉴에서 가져오기를 누르고
   덱 패키지(.apkg)와 APKG 파일을 차례로 선택합니다.
4. 추가를 누르고 가져오기가 끝날 때까지 앱을 닫지 않습니다.
5. 덱 목록의 JLPT MAX덱에서 글자와 음성이 정상인지 확인합니다.

자세한 현재 메뉴는
[AnkiDroid 공식 가져오기 문서](https://docs.ankidroid.org/manual.html#importing)를
참고하세요.

## 5. 가져오기 창에서는 무엇을 선택하나요?

가져오기 옵션이 표시되면 다음 값을 선택합니다. 덮어쓰기(Updates)가 접혀 있으면
펼쳐서 마지막 세 항목까지 확인하세요.

| 항목 | 선택 | 이유 |
| --- | --- | --- |
| 학습 진행 상태 가져오기(Import any learning progress, 복습 포함) | 끄기 | 패키지의 학습 일정 없이 새 카드로 시작하고, 재가져오기 때 기존 학습 진도를 보존합니다. |
| 덱 사전 설정 가져오기(Import any deck presets) | 켜기 | JLPT MAX덱의 새 카드 수, 카드 순서와 음성 설정을 적용합니다. |
| 노트 타입 병합(Merge note types) | 켜기 | 재가져오기 때 달라진 필드와 템플릿 구조를 합칩니다. 서로 다른 덱을 합치는 기능은 아닙니다. |
| 노트 업데이트(Update notes) | If newer | 가져오는 노트가 더 최신인 경우에만 갱신합니다. |
| 노트 유형 업데이트(Update note types) | If newer | 카드 템플릿과 스타일이 더 최신인 경우에만 갱신합니다. |

iPhone·iPad에서 옵션이 나타나지 않으면 그대로 가져오면 됩니다. Android에서
옵션이 표시되면 위와 같이 맞춥니다. 기존 JLPT MAX덱의 필드나 카드 템플릿을
직접 수정했다면 노트 타입 병합 전에 백업하세요. 병합 뒤 전체 업로드 또는
다운로드 동기화가 필요할 수 있습니다.

공식 동작은 [Anki 패키지 덱 가져오기](https://docs.ankiweb.net/importing/packaged-decks.html)를
참고하세요.

## 6. 왜 각 기기에 APKG를 직접 넣나요?

이 덱에는 미디어 17,489개가 들어 있습니다. 같은 APKG를 각 기기에 로컬로
복사해 가져오면 카드와 음성이 함께 설치되므로, 대용량 미디어를 별도로 전송하거나
내려받는 시간을 기다리지 않고 바로 공부를 시작할 수 있습니다.

가져오는 동안에는 원본 APKG와 앱 안에 풀린 미디어가 함께 존재합니다. 충분한
저장 공간을 준비하고, 덱과 음성을 확인한 뒤 휴대기기의 전송용 APKG는 삭제해도
됩니다. 재설치용 원본은 외부에 업로드하지 말고 개인용 로컬 저장 장치에
보관하세요.

## 7. 처음에는 어떤 설정을 쓰나요?

JLPT MAX덱을 가져온 뒤 덱 옵션을 엽니다.

- Windows·macOS: 덱 목록의 JLPT MAX덱 오른쪽 톱니바퀴 → 옵션(Options)
- iPhone·iPad: JLPT MAX덱 학습 화면 오른쪽 아래 톱니바퀴 → Study Options
- Android: 덱 목록에서 JLPT MAX덱 길게 누르기 → Deck options

가져온 프리셋에는 하루 새 카드 20개와 목표 기억률 90%가 설정되어 있습니다.
처음에는 다음 항목만 확인하세요.

1. 새 카드 수는 하루 10~20개로 시작합니다. 매일 복습할 카드가 부담되면
   New Cards/Day를 10개 이하로 낮춥니다.
2. 사용하는 모든 Anki 앱을 최신 버전으로 맞춘 뒤 FSRS를 켭니다.
3. Desired Retention은 0.90으로 둡니다. 높일수록 복습량이 빠르게 늘어납니다.
4. Reschedule Cards on Change는 끈 상태로 둡니다. 다음 복습부터 FSRS가
   적용되며, 기존 카드가 한꺼번에 다시 예약되는 일을 피할 수 있습니다.
5. 리뷰가 수백 회 쌓인 뒤 Optimize를 누릅니다. 이후에는 한 달에 한 번
   정도면 충분합니다. 나머지 옵션은 우선 기본값을 유지하세요.

처음에는 Again과 Good 두 버튼만 사용하는 것을 권장합니다. 틀렸거나 기억나지
않으면 Again, 기억해 냈으면 Good을 누릅니다. [Anki 공식 FSRS FAQ](https://faqs.ankiweb.net/frequently-asked-questions-about-fsrs.html)는
FSRS가 두 등급만으로도 정상 동작하며 경우에 따라 더 정확할 수도 있다고
안내합니다. 네 버튼을 쓰고 싶다면 Hard는 맞았지만 어려웠을 때, Easy는 아주
쉽게 맞았을 때만 선택하세요. 기기마다 버튼을 단순화하는 방법은 다릅니다.

- Android: AnkiDroid 2.23 이상의 설정 → 새 학습 화면에서 새 학습 화면을 켠 뒤,
  답변 버튼 → ‘어려움’, ‘쉬움’ 버튼 숨기기를 켭니다. Again과 Good만
  화면에 남습니다. 메뉴가 보이지 않으면 AnkiDroid를 먼저 업데이트합니다.
- iPhone·iPad: Hard와 Easy만 숨기는 기능은 없습니다. 설정 → Review →
  Bottom Bar → Answer Buttons를 끄면 버튼 전체를 숨길 수 있고, 답을 본 뒤
  화면 왼쪽 탭은 Again, 오른쪽 탭은 Good으로 동작합니다. 처음에는 버튼을
  표시한 채 두 등급만 사용하다가 익숙해진 뒤 숨기는 편이 안전합니다.
- Windows·macOS: Hard와 Easy만 숨기는 기본 설정은 없습니다. 1은 Again,
  Space·Enter는 Good으로 사용하면 됩니다. 버튼 자체를 숨기려면 서드파티
  애드온이 필요하므로 이 초보자용 가이드에서는 권장하지 않습니다.

답을 기억하지 못했다면 Hard가 아니라 Again을 누릅니다. Hard는 힘들었지만
스스로 기억해 낸 경우에만 사용합니다. 자세한 기준은
[Anki 공식 FSRS 안내](https://docs.ankiweb.net/deck-options#fsrs),
[AnkiMobile 학습 옵션](https://docs.ankimobile.net/study-tools.html),
[AnkiDroid 덱 옵션](https://docs.ankidroid.org/manual.html#other-deck-actions)을
확인하세요.

## 8. AnkiWeb으로 학습 상태를 동기화하려면

[AnkiWeb 무료 계정](https://ankiweb.net/account/signup)을 만들고 각 기기에서
같은 계정으로 로그인한 뒤 동기화를 실행하면 카드, 복습 기록과 현재 학습 상태를
이어갈 수 있습니다. 이미지와 음성도 함께 동기화됩니다.

1. Mac 또는 Windows에서 빌드했더라도 당장 공부할 기기마다 같은 APKG를 먼저
   옮겨 가져옵니다. 여러 기기를 바로 쓸 예정이라면 각 기기에 직접 가져와 첫
   미디어 다운로드를 기다리지 않고 시작할 수 있습니다.
2. 그 기기에서 AnkiWeb에 로그인하고 동기화 버튼을 누릅니다. 비어 있는
   AnkiWeb과의 첫 동기화라면 업로드(Upload)를 선택합니다.
3. 미디어 17,489개의 첫 동기화는 시간이 오래 걸릴 수 있습니다. 직접 가져온
   기기에는 음성이 이미 있으므로 미디어 동기화 완료를 기다리지 않고 학습할 수
   있습니다. 중단했다면 나중에 동기화를 다시 실행해 이어갑니다. 진행 상태는
   [Anki 미디어 동기화 안내](https://faqs.ankiweb.net/media-files-may-take-time-to-sync.html)에서
   확인할 수 있습니다.
4. 다른 기기에서는 같은 계정으로 로그인해 동기화하고, 첫 선택이 나오면
   다운로드(Download)를 선택합니다.
5. 이후에는 공부 전후로 동기화해 복습 기록과 학습 상태를 맞춥니다.

이미 AnkiWeb이나 다른 기기에 카드·학습 기록이 있다면 먼저 백업하고
[Anki 공식 동기화 안내](https://docs.ankiweb.net/syncing.html)를 확인하세요.
로그인만 하는 것으로는 충분하지 않으며 동기화가 실행되어야 합니다.

같은 사용자의 개인 기기 사이에서 비공개 AnkiWeb 동기화를 쓰는 것은 개인 학습
흐름입니다. APKG 파일, 계정 접근 권한 또는 생성 콘텐츠를 다른 사람에게
전달하거나 공개 링크·일반 클라우드에 올려서는 안 됩니다.

## 9. 덱을 가져온 뒤

덱 목록에서 JLPT MAX덱을 펼치면 주요 하위 덱이 보입니다.

- 어휘
- 음성
- 일상무따
- 종합 실전
- 참조표

원하는 덱을 누르고 지금 공부하기(Study Now)를 선택합니다. 단어 카드에서
음성이 나오지 않으면 먼저 기기의 음량, 음소거와 출력 장치를 확인하세요.
