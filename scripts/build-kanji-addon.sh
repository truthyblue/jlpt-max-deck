#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "사용법: $0 <일상무따-상권.pdf> <일상무따-하권.pdf> [출력-폴더]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_ROOT="${3:-$ROOT/build/kanji-addon}"

cd "$ROOT"
uv run --locked python src/build_kanji_addon.py \
  --upper-pdf "$1" \
  --lower-pdf "$2" \
  --asset-root "$ROOT/assets" \
  --output-root "$OUTPUT_ROOT"
