#!/bin/bash
# Build the board and run every static gate.   ./build.sh [board.svg]
#   BUILD_SCRIPT   the board generator (default: build_board.py next to this script)
#   TOKENS         tokens.json (default: tokens.json)
#   MEASURED       measured_text.json from the app's measure test (optional)
set -euo pipefail
cd "$(dirname "$0")"
OUT="${1:-board.svg}"
BUILD_SCRIPT="${BUILD_SCRIPT:-build_board.py}"
TOKENS="${TOKENS:-tokens.json}"
LAYOUT="${LAYOUT:-build/design_layout.json}"
mkdir -p "$(dirname "$LAYOUT")"
python3 "$BUILD_SCRIPT" --out "$OUT"
python3 check_board.py "$OUT" --require-ids
python3 extract_layout.py "$OUT" -o "$LAYOUT"
python3 audit_layout.py "$LAYOUT" --tokens "$TOKENS" ${MEASURED:+--measured "$MEASURED"} --strict
