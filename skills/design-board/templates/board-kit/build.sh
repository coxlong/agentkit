#!/bin/bash
# Build the board and run every static gate, then list the screens whose content changed.
#
#   ./build.sh [board.svg]
#   BUILD_SCRIPT   the board generator (default: build_board.py next to this script)
#   BUILD_ARGS     extra generator args, e.g. "--meta build/screen_meta.json"
#   TOKENS         tokens.json (default: tokens.json)
#   MEASURED       measured_text.json from the target engine (optional)
#   META           screen_meta.json written by the generator (default: build/screen_meta.json)
set -euo pipefail
cd "$(dirname "$0")"
OUT="${1:-board.svg}"
BUILD_SCRIPT="${BUILD_SCRIPT:-build_board.py}"
BUILD_ARGS="${BUILD_ARGS:-}"
TOKENS="${TOKENS:-tokens.json}"
META="${META:-build/screen_meta.json}"
LAYOUT="${LAYOUT:-build/design_layout.json}"
mkdir -p "$(dirname "$LAYOUT")"
# shellcheck disable=SC2086
python3 "$BUILD_SCRIPT" --out "$OUT" $BUILD_ARGS
python3 check_board.py "$OUT" --require-ids
python3 extract_layout.py "$OUT" -o "$LAYOUT"
python3 audit_layout.py "$LAYOUT" --tokens "$TOKENS" ${MEASURED:+--measured "$MEASURED"} --strict
if [ -f "$META" ]; then
  if [ -f "$META.prev" ]; then
    python3 - "$META.prev" "$META" <<'PY'
import json
import sys

old = json.load(open(sys.argv[1], encoding='utf-8')).get('screens', {})
new = json.load(open(sys.argv[2], encoding='utf-8')).get('screens', {})
changed = sorted(k for k in new if k in old and old[k]['sha'] != new[k]['sha'])
added = sorted(k for k in new if k not in old)
removed = sorted(k for k in old if k not in new)
print(f'changed: {", ".join(changed) or "none"}')
print(f'added:   {", ".join(added) or "none"}')
print(f'removed: {", ".join(removed) or "none"}')
with open(sys.argv[2] + '.changed', 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(changed + added))
    if changed or added:
        fh.write('\n')
PY
  else
    echo 'changed: all (first build, no previous screen_meta.json)'
  fi
  cp "$META" "$META.prev"
else
  echo "note: generator wrote no $META - changed-screen detection disabled (pass BUILD_ARGS=\"--meta $META\")"
fi
