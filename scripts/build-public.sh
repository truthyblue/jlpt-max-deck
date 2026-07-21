#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 3 ]]; then
  echo "usage: $0 PDF_ROOT [BUNDLE_ROOT] [OUTPUT_ROOT]" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pdf_root="$(cd "$1" && pwd)"
caller_root="$PWD"
runtime_root="$(cd "$repo_root/.." && pwd)"
bundle_root="${2:-$repo_root}"
if [[ "$bundle_root" != /* ]]; then
  bundle_root="$caller_root/$bundle_root"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

cd "$repo_root"
export OMP_NUM_THREADS=1
export OMP_THREAD_LIMIT=1
export PYTHONDONTWRITEBYTECODE=1
export UV_PROJECT_ENVIRONMENT="$runtime_root/.jlpt-max-public-venv"
uv sync --locked --python 3.13
build_args=(
  src/build_public_deck.py
  --pdf-root "$pdf_root"
  --bundle-root "$bundle_root"
)
if [[ $# -eq 3 ]]; then
  output_root="$3"
  if [[ "$output_root" != /* ]]; then
    output_root="$caller_root/$output_root"
  fi
  build_args+=(--output-root "$output_root")
fi
"$UV_PROJECT_ENVIRONMENT/bin/python" "${build_args[@]}"
