#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_ROOT="$ROOT/build/kanji-addon"
LOG_PATH="$ROOT/kanji-builder.log"
UV_VERSION="0.11.32"
UV_ROOT="$ROOT/.tools/uv"
UV_BIN="$UV_ROOT/uv"

show_error() {
  local message="$1"
  /usr/bin/osascript - "$message" >/dev/null 2>&1 <<'APPLESCRIPT' || true
on run argv
  display alert "JLPT MAX 한자 확장" message (item 1 of argv) as critical
end run
APPLESCRIPT
}

choose_pdf() {
  local prompt="$1"
  /usr/bin/osascript - "$prompt" <<'APPLESCRIPT'
on run argv
  set chosenFile to choose file with prompt (item 1 of argv) of type {"com.adobe.pdf"}
  return POSIX path of chosenFile
end run
APPLESCRIPT
}

confirm_replacement() {
  local answer
  answer="$(
    /usr/bin/osascript <<'APPLESCRIPT'
set answer to display dialog "이전에 만든 결과가 있습니다.
기존 결과를 지우고 다시 만들까요?" with title "JLPT MAX 한자 확장" buttons {"취소", "다시 만들기"} default button "다시 만들기"
return button returned of answer
APPLESCRIPT
  )" || return 1
  [[ "$answer" == "다시 만들기" ]]
}

echo
echo "JLPT MAX 일상무따 한자 확장 만들기"
echo "화면에 나타나는 순서대로 PDF 두 개를 선택하세요."
echo

if ! UPPER_PDF="$(choose_pdf "1권(상권)의 지원 소책자 PDF를 선택하세요")"; then
  echo "사용자가 작업을 취소했습니다."
  exit 0
fi
echo "1권 PDF: $(basename "$UPPER_PDF")"

if ! LOWER_PDF="$(choose_pdf "2권(하권)의 지원 소책자 PDF를 선택하세요")"; then
  echo "사용자가 작업을 취소했습니다."
  exit 0
fi
echo "2권 PDF: $(basename "$LOWER_PDF")"

if [[ "$UPPER_PDF" == "$LOWER_PDF" ]]; then
  show_error "같은 PDF를 두 번 선택했습니다. 1권과 2권 PDF를 각각 선택해 주세요."
  exit 1
fi

if [[ -d "$OUTPUT_ROOT" ]] && [[ -n "$(find "$OUTPUT_ROOT" -mindepth 1 -print -quit)" ]]; then
  if ! confirm_replacement; then
    echo "기존 결과를 유지하고 작업을 취소했습니다."
    exit 0
  fi
  if [[ "$OUTPUT_ROOT" != "$ROOT/build/kanji-addon" ]]; then
    show_error "출력 폴더 안전 확인에 실패했습니다."
    exit 1
  fi
  /bin/rm -rf -- "$OUTPUT_ROOT"
fi

INSTALLED_VERSION=""
if [[ -x "$UV_BIN" ]]; then
  INSTALLED_VERSION="$("$UV_BIN" --version 2>/dev/null || true)"
fi
if [[ "$INSTALLED_VERSION" != "uv $UV_VERSION"* ]]; then
  echo
  echo "1/3 필요한 빌드 도구를 준비합니다. 처음 한 번만 인터넷을 사용합니다."
  if [[ -e "$UV_ROOT" ]]; then
    /bin/rm -rf -- "$UV_ROOT"
  fi
  mkdir -p "$UV_ROOT"
  if ! curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" |
    env UV_UNMANAGED_INSTALL="$UV_ROOT" UV_NO_MODIFY_PATH=1 sh; then
    show_error "필요한 빌드 도구를 준비하지 못했습니다. 인터넷 연결을 확인해 주세요."
    exit 1
  fi
  if [[ ! -x "$UV_BIN" ]]; then
    show_error "필요한 빌드 도구를 찾지 못했습니다."
    exit 1
  fi
else
  echo
  echo "1/3 필요한 빌드 도구가 준비되어 있습니다."
fi

echo "2/3 PDF를 확인하고 한자 카드 2,337개를 만듭니다."
echo "창을 닫지 말고 기다려 주세요."
echo

cd "$ROOT"
set +e
"$UV_BIN" run --locked --python 3.13 python src/build_kanji_addon.py \
  --upper-pdf "$UPPER_PDF" \
  --lower-pdf "$LOWER_PDF" \
  --asset-root "$ROOT/assets" \
  --output-root "$OUTPUT_ROOT" \
  2>&1 | tee "$LOG_PATH"
BUILD_EXIT_CODE="${PIPESTATUS[0]}"
set -e

if [[ "$BUILD_EXIT_CODE" -ne 0 ]]; then
  show_error "한자 확장을 만들지 못했습니다. 선택한 PDF와 오류 내용을 확인해 주세요.\n\n자세한 내용: $LOG_PATH"
  open -a TextEdit "$LOG_PATH" >/dev/null 2>&1 || true
  exit 1
fi

PACKAGE="$OUTPUT_ROOT/JLPT-MAX-kanji-addon-1.0.1.apkg"
if [[ ! -f "$PACKAGE" ]]; then
  show_error "완성된 APKG를 찾지 못했습니다."
  exit 1
fi

echo
echo "3/3 한자 확장을 완성했습니다."
open "$OUTPUT_ROOT"
/usr/bin/osascript >/dev/null 2>&1 <<'APPLESCRIPT' || true
display dialog "한자 확장을 완성했습니다.
열린 폴더의 JLPT-MAX-kanji-addon-1.0.1.apkg를 Anki에 가져오세요." with title "JLPT MAX 한자 확장" buttons {"확인"} default button "확인" with icon note
APPLESCRIPT
