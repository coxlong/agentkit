#!/usr/bin/env python3
"""Renders every artboard of the board to <out>/<screen>.png at one scale, for pixel_diff.py.

    python3 render_design_pngs.py --board board.svg --layout build/design_layout.json --out build/design_png \
        [--scale 1] [--render-sh ../design-board/templates/board-kit/render.sh]

Uses the board kit's render.sh (headless Chromium). The scale must equal the scale the app PNGs were captured at
(Flutter: the pixelRatio passed to toImage; 1 gives 390 x 844).
"""
import argparse
import json
import os
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--board', required=True)
    ap.add_argument('--layout', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--scale', default='1')
    ap.add_argument('--render-sh', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..',
                                                       'design-board', 'templates', 'board-kit', 'render.sh'))
    a = ap.parse_args()
    screens = json.load(open(a.layout, encoding='utf-8'))['screens']
    os.makedirs(a.out, exist_ok=True)
    for name, s in screens.items():
        x, y = s['origin']
        w, h = s['size']
        r = subprocess.run([a.render_sh, a.board, os.path.join(a.out, name + '.png'), str(x), str(y), str(w), str(h), a.scale],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit(f'render failed for {name}: {r.stderr[-300:]}')
    print(f'{len(screens)} artboards -> {a.out}')


if __name__ == '__main__':
    main()
