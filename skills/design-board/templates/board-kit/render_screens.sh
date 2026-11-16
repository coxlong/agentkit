#!/bin/bash
# Renders each screen of the board as its own PNG with headless Chromium (one PNG per artboard, note strip included).
#
#   ./render_screens.sh board.svg outdir [changed.txt]   # changed.txt: one screen id per line; omit = every screen
#
# Reads META (default build/screen_meta.json), written by the generator via frame.Board.write_meta().
# RENDER_SCALE scales the PNGs (default 1 = artboard at logical size).
set -euo pipefail
cd "$(dirname "$0")"
IN="${1:?usage: render_screens.sh board.svg outdir [changed.txt]}"
OUT="${2:?usage: render_screens.sh board.svg outdir [changed.txt]}"
CHANGED="${3:-}"
META="${META:-build/screen_meta.json}"
SCALE="${RENDER_SCALE:-1}"
[ -f "$META" ] || { echo "render_screens.sh: $META not found; the generator must call frame.Board.write_meta()" >&2; exit 2; }
mkdir -p "$OUT"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
python3 - "$META" "$CHANGED" > "$TMP" <<'PY'
import json
import sys

meta = json.load(open(sys.argv[1], encoding='utf-8'))['screens']
only = None
if sys.argv[2]:
    only = {ln.strip() for ln in open(sys.argv[2], encoding='utf-8') if ln.strip()}
for sid in sorted(meta):
    if only and sid not in only:
        continue
    m = meta[sid]
    x, y, w, h = m['region']
    print(f'{sid} {x} {y} {w} {h}')
PY
COUNT=0
while read -r sid x y w h; do
  ./render.sh "$IN" "$OUT/$sid.png" "$x" "$y" "$w" "$h" "$SCALE" >/dev/null
  echo "rendered $OUT/$sid.png"
  COUNT=$((COUNT + 1))
done < "$TMP"
echo "$COUNT screens -> $OUT/"
