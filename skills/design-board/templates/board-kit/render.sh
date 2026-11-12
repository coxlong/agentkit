#!/bin/bash
# Renders a region of an SVG to PNG with headless Chromium. Nothing from the app is run.
#
#   ./render.sh in.svg out.png [x y w h [scale]]
#
#   ./render.sh ../design-board.svg .out/overview.png 0 0 2880 20558 0.15   # whole board, thumbnail
#   ./render.sh ../design-board.svg .out/c1.png 0 3746 2880 1100 0.6        # one section
#
# x y w h select the crop in SVG pixels; scale is the device scale factor (1 = 1:1, 2 = zoom).
# Chromium lookup order: $CHROME, a Playwright headless shell in ~/.cache/ms-playwright, then PATH.
#
# FONTS="family|/path/file.otf|weight;family|/path/other.otf|weight"   draw the text with these exact font files
# (the same ones the app is rendered with; needed for any pixel comparison with the app). The svg is then inlined
# in the page, because an svg shown as an image cannot load fonts.
set -euo pipefail
if [ $# -lt 2 ]; then sed -n '2,12p' "$0"; exit 2; fi
IN="$(readlink -f "$1")"; OUT="$2"; X="${3:-0}"; Y="${4:-0}"; W="${5:-1200}"; H="${6:-800}"; S="${7:-1}"

CHROME="${CHROME:-}"
if [ -z "$CHROME" ]; then
  for c in "$HOME"/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell; do
    [ -x "$c" ] && CHROME="$c"
  done
fi
if [ -z "$CHROME" ]; then
  for c in chrome-headless-shell chromium chromium-browser google-chrome google-chrome-stable; do
    if command -v "$c" >/dev/null 2>&1; then CHROME="$(command -v "$c")"; break; fi
  done
fi
if [ -z "$CHROME" ]; then echo "render.sh: no Chromium found; set CHROME=/path/to/chrome" >&2; exit 1; fi

DIR="$(mktemp -d "${TMPDIR:-/tmp}/hgrender.XXXXXX")"
trap 'rm -rf "$DIR"' EXIT
FONT_CSS=""
if [ -n "${FONTS:-}" ]; then
  IFS=';' read -ra FS <<< "$FONTS"
  for f in "${FS[@]}"; do
    IFS='|' read -r fam path wt <<< "$f"
    FONT_CSS+="@font-face{font-family:'$fam';src:url('file://$path');font-weight:${wt:-400}}"
  done
  { printf '<!doctype html><html><head><meta charset="utf-8"><style>%s html,body{margin:0;padding:0;background:#fff}' "$FONT_CSS"
    printf '.c{width:%spx;height:%spx;overflow:hidden;position:relative}.c>div{position:absolute;left:-%spx;top:-%spx}</style></head>' "$W" "$H" "$X" "$Y"
    printf '<body><div class="c"><div>'; cat "$IN"; printf '</div></div></body></html>'; } > "$DIR/v.html"
else
cat > "$DIR/v.html" <<HTML
<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;background:#fff}
.c{width:${W}px;height:${H}px;overflow:hidden;position:relative}
.c img{position:absolute;left:-${X}px;top:-${Y}px;max-width:none}
</style></head><body><div class="c"><img src="file://${IN}"></div></body></html>
HTML
fi
"$CHROME" --no-sandbox --disable-gpu --hide-scrollbars --force-device-scale-factor="$S" \
  --font-render-hinting=none --window-size="${W},${H}" --virtual-time-budget=2500 --screenshot="$OUT" "file://$DIR/v.html" >/dev/null 2>&1 || true
if [ -f "$OUT" ]; then ls -la "$OUT" | awk '{print $5, $9}'; else echo "render.sh: no output produced" >&2; exit 1; fi
