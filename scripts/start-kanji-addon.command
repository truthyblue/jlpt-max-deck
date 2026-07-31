#!/bin/bash
set -euo pipefail

ENTRY_ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -x "$ENTRY_ROOT/scripts/start-kanji-addon.sh" ]]; then
  ENTRY_ROOT="$(cd "$ENTRY_ROOT/.." && pwd)"
fi

exec "$ENTRY_ROOT/scripts/start-kanji-addon.sh"
