#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 https://github.com/OWNER/REPOSITORY" >&2
  exit 2
fi

repository_url="${1%/}"
if [[ ! "$repository_url" =~ ^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "올바른 GitHub 저장소 주소가 아닙니다: $repository_url" >&2
  exit 2
fi
repository_path="${repository_url#https://github.com/}"
repository_owner="${repository_path%%/*}"
repository_name="${repository_path#*/}"
if [[ "$repository_owner" == "." || "$repository_owner" == ".." || "$repository_name" == "." || "$repository_name" == ".." ]]; then
  echo "올바른 GitHub 저장소 주소가 아닙니다: $repository_url" >&2
  exit 2
fi

for command_name in curl open osascript shasum unzip; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Mac에 필요한 기본 명령을 찾지 못했습니다: $command_name" >&2
    exit 1
  fi
done

printf '\n[1/4] 먼저 PDF 17개가 든 폴더를 확인합니다.\n'
if ! pdf_root="$(osascript -e 'POSIX path of (choose folder with prompt "PDF 17개가 든 폴더를 선택하세요")')"; then
  echo "폴더 선택을 취소했습니다. 준비되면 같은 명령을 다시 실행해 주세요." >&2
  exit 1
fi
pdf_count="$(find "$pdf_root" -type f -iname '*.pdf' | wc -l | tr -d ' ')"
if [[ "$pdf_count" -ne 17 ]]; then
  echo "선택한 폴더에서 PDF ${pdf_count}개를 찾았습니다. 정확히 17개가 필요합니다." >&2
  exit 1
fi
echo "PDF 17개를 확인했습니다. PDF는 이 컴퓨터 안에서만 사용합니다."

printf '\n[2/4] 덱을 만드는 데 필요한 프로그램을 확인합니다.\n'
if ! command -v uv >/dev/null 2>&1; then
  echo "필요한 프로그램 uv가 없어 지금 설치합니다."
  curl --proto '=https' --proto-redir '=https' --tlsv1.2 -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "필요한 프로그램이 준비되어 있습니다."
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "uv 설치 후 터미널을 다시 열고 같은 명령을 실행해 주세요." >&2
  exit 1
fi

release_url="$repository_url/releases/latest/download"
work_root="$(mktemp -d "$HOME/JLPT-MAX-public-build-$(date +%Y%m%d-%H%M%S).XXXXXX")"
download_root="$work_root/download"
mkdir -p "$download_root"

printf '\n[3/4] 공개 빌더 파일을 내려받고 손상되지 않았는지 확인합니다.\n'
assets=(
  JLPT-MAX-public-bundle.zip
  JLPT-MAX-public-bundle.zip.sha256
  public-release.json
)
for asset in "${assets[@]}"; do
  curl --proto '=https' --proto-redir '=https' --tlsv1.2 \
    --fail --location --progress-bar \
    "$release_url/$asset" --output "$download_root/$asset"
done

pin_hash="$(awk -F'"' '/"archive_sha256"/ { print $4; exit }' "$download_root/public-release.json")"
file_hash="$(awk '{ print $1; exit }' "$download_root/JLPT-MAX-public-bundle.zip.sha256")"
actual_hash="$(shasum -a 256 "$download_root/JLPT-MAX-public-bundle.zip" | awk '{ print $1 }')"
if [[ -z "$pin_hash" || "$actual_hash" != "$pin_hash" || "$actual_hash" != "$file_hash" ]]; then
  echo "내려받은 파일이 손상되었거나 릴리스 정보와 일치하지 않습니다. 파일을 실행하지 않고 멈춥니다." >&2
  exit 1
fi
echo "파일이 릴리스에 등록된 원본과 일치합니다."

build_root="$work_root/build"
mkdir -p "$build_root"
unzip -q "$download_root/JLPT-MAX-public-bundle.zip" -d "$build_root"
bundle_root="$build_root/public-bundle"
if [[ ! -f "$bundle_root/scripts/build-public.sh" || -L "$bundle_root/scripts/build-public.sh" ]]; then
  echo "내려받은 압축 파일에서 덱 만들기 스크립트를 찾지 못했습니다." >&2
  exit 1
fi

printf '\n[4/4] 이제 덱을 만듭니다. 컴퓨터에 따라 시간이 걸릴 수 있습니다.\n'
bash "$bundle_root/scripts/build-public.sh" "$pdf_root"
output_root="$build_root/public-release"
printf '\n완료했습니다. Anki에 가져올 파일이 있는 폴더:\n%s\n' "$output_root"
if ! open "$output_root"; then
  echo "Finder를 자동으로 열지 못했습니다. 위 경로를 Finder에서 직접 열어 주세요." >&2
fi
