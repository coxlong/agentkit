#!/usr/bin/env python3
"""Self-audit of the board against its own tokens, from the extract (no browser).

    python3 audit_layout.py build/design_layout.json --tokens tokens.json [--measured build/measured_text.json] [--strict]

Reports, per screen:
  scale    a text size / weight, icon size, icon stroke or corner radius that is not on the scale of tokens.json
  overflow text that leaves the screen (width from the ruler: measured when --measured is given, else the estimate)
  overlap  two texts whose boxes overlap by more than 2 px in both directions
  ids      elements without an id (info; check_board.py --require-ids makes it an error)
--strict: exit 1 when `scale` or `overflow` has an entry. `overlap` is reported but never fails: a sheet over a page
legitimately overlaps what is behind it; compare overlaps between design and app with parity.py instead.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kit  # noqa: E402


def text_box(t, w_screen):
    size, weight, mono = t['fs'], t['fw'], t['mono']
    lines = t['s'].split('\n')
    width = max(kit.ruler().width(ln, size, weight, mono) for ln in lines)
    x0 = t['x'] - (width / 2 if t['anchor'] == 'middle' else width if t['anchor'] == 'end' else 0)
    lh = t.get('lh') or size * 1.4
    top = t['y'] - kit.ruler().baseline(size, weight, lh, mono)
    return x0, x0 + width, top, top + lh * len(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('layout')
    ap.add_argument('--tokens', required=True)
    ap.add_argument('--measured')
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    kit.init(a.tokens, measured=a.measured)
    data = json.load(open(a.layout, encoding='utf-8'))['screens']
    out = defaultdict(list)
    for name, s in data.items():
        w, h = s['size']
        texts = [t for t in s['texts'] if not t['deco']]
        for t in texts:
            tag = f'{name}: text "{t["s"][:20]}"'
            if t['fs'] not in kit.SIZES:
                out['scale'].append(f'{tag} size {t["fs"]:g}')
            if t['fw'] not in kit.WEIGHTS:
                out['scale'].append(f'{tag} weight {t["fw"]}')
            x0, x1, y0, y1 = text_box(t, w)
            if x0 < -0.5 or x1 > w + 0.5 or y1 > h + 0.5:
                out['overflow'].append(f'{tag} spans x {x0:.0f}..{x1:.0f}, y to {y1:.0f} on a {w} x {h} screen')
            if not t['id']:
                out['ids'].append(f'{tag} has no id')
        for i, a_ in enumerate(texts):
            for b_ in texts[i + 1:]:
                ax0, ax1, ay0, ay1 = text_box(a_, w)
                bx0, bx1, by0, by1 = text_box(b_, w)
                if min(ax1, bx1) - max(ax0, bx0) > 2 and min(ay1, by1) - max(ay0, by0) > 2:
                    out['overlap'].append(f'{name}: "{a_["s"][:16]}" x "{b_["s"][:16]}"')
        for ic in s['icons']:
            if ic['deco']:
                continue
            tag = f'{name}: icon {ic["name"]}'
            if ic['size'] not in kit.ICON_SIZES and ic['size'] <= max(kit.ICON_SIZES) * 1.4:
                out['scale'].append(f'{tag} size {ic["size"]:g}')
            want = kit.icon_stroke(ic['size'])
            if not ic['filled'] and ic['stroke_units'] is not None and abs(ic['stroke_units'] - want) > 0.01:
                out['scale'].append(f'{tag} stroke {ic["stroke_units"]:g} units, rule says {want:g} at {ic["size"]:g}px')
            if not ic['id']:
                out['ids'].append(f'{tag} has no id')
        for b in s['boxes']:
            if b['deco'] or min(b['w'], b['h']) < 14 or not b['rx']:
                continue
            pill = b['rx'] >= min(b['w'], b['h']) / 2 - 1
            if not pill and b['rx'] not in kit.RADII and b['rx'] >= kit.TOKENS['scales'].get('radius_free_below', 0):
                out['scale'].append(f'{name}: box {b["w"]:g}x{b["h"]:g} at ({b["x"]:g},{b["y"]:g}) radius {b["rx"]:g}')
    bad = 0
    for kind in ('scale', 'overflow', 'overlap', 'ids'):
        items = out.get(kind, [])
        print(f'== {kind}: {len(items)} ==')
        for it in items[:25]:
            print('  ', it)
        if len(items) > 25:
            print(f'   ... {len(items) - 25} more')
        if kind in ('scale', 'overflow'):
            bad += len(items)
    if a.strict and bad:
        sys.exit(1)


if __name__ == '__main__':
    main()
