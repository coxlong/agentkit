#!/usr/bin/env python3
"""Exports what every artboard of the board draws, in phone-local pixels, as JSON (the numeric spec of the board).

    python3 extract_layout.py board.svg -o build/design_layout.json

An artboard is a <g data-screen="<screen id>" data-code=".." data-title=".."> made by frame.phone(). Per screen:
  texts  {id, s, x, y(first baseline), y_last, lines, fs, fw, fill, op, anchor, mono, lh, style, deco}
  icons  {id, name, cx, cy, size, color, filled, stroke_units, deco}
  boxes  {id, kind(rect|circle), x, y, w, h, rx, fill, fop, op, stroke, sw, shadow{dx,dy,blur,color,opacity}, deco}
  lines  {id, x1, y1, x2, y2, stroke, sw, deco}
Elements without a data-id are exported with id null (the check counts them as untagged). Standard library only.
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def transform(attr):
    """translate()/scale() sequences -> (tx, ty, sx, sy) such that x' = sx * x + tx."""
    tx = ty = 0.0
    sx = sy = 1.0
    for name, args in re.findall(r'(translate|scale)\(([^)]*)\)', attr or ''):
        v = [float(n) for n in re.findall(r'-?\d*\.?\d+(?:e-?\d+)?', args)]
        if name == 'translate':
            tx += sx * v[0]
            ty += sy * (v[1] if len(v) > 1 else 0)
        else:
            sx *= v[0]
            sy *= v[1] if len(v) > 1 else v[0]
    return tx, ty, sx, sy


def compose(parent, child):
    ptx, pty, psx, psy = parent
    ctx, cty, csx, csy = child
    return ptx + psx * ctx, pty + psy * cty, psx * csx, psy * csy


def shadows(root):
    """filter id -> drop shadow {dx, dy, blur (CSS blur radius = 2 sigma), color, opacity}."""
    out = {}
    for flt in root.iter(NS + 'filter'):
        sh = flt.find(NS + 'feDropShadow')
        if sh is not None:
            out[flt.get('id')] = {'dx': num(sh.get('dx')), 'dy': num(sh.get('dy')),
                                  'blur': 2 * num(sh.get('stdDeviation')), 'color': sh.get('flood-color'),
                                  'opacity': num(sh.get('flood-opacity'), 1.0)}
    return out


def r2(v):
    return round(v, 2)


def walk(el, ctx, out, shadow_defs):
    pending = {}                                  # data-id -> text record being built from several lines
    for ch in el:
        tag = ch.tag.replace(NS, '')
        local = compose(ctx, transform(ch.get('transform')))
        tx, ty, sx, sy = local
        did = ch.get('data-id')
        deco = bool(ch.get('data-deco'))
        if tag == 'text':
            s = ''.join(ch.itertext())
            if not s.strip():
                continue
            spans = [(t.get('fill'), ''.join(t.itertext())) for t in ch.iter(NS + 'tspan')]
            rec = {'id': did, 's': s, 'x': r2(tx + sx * num(ch.get('x'))), 'y': r2(ty + sy * num(ch.get('y'))),
                   'fs': r2(sx * num(ch.get('font-size'), 16)), 'fw': int(num(ch.get('font-weight'), 400)),
                   'fill': ch.get('fill'), 'op': num(ch.get('opacity'), 1.0), 'anchor': ch.get('text-anchor', 'start'),
                   'mono': 'mono' in (ch.get('font-family') or '').lower(), 'lh': r2(sy * num(ch.get('data-lh'), 0)) or None,
                   'ls': r2(sx * num(ch.get('letter-spacing'), 0)), 'style': ch.get('data-style'), 'lines': 1, 'y_last': r2(ty + sy * num(ch.get('y'))), 'deco': deco}
            if spans:
                rec['spans'] = [[c, t] for c, t in spans]
            if did and ch.get('data-line') is not None:
                if did in pending:
                    p = pending[did]
                    p['s'] += '\n' + s
                    p['lines'] += 1
                    p['y_last'] = rec['y']
                    continue
                pending[did] = rec
            out['texts'].append(rec)
        elif tag == 'g':
            if ch.get('data-icon'):
                size = num(ch.get('data-size')) or round(24 * sx * 2) / 2
                filled = ch.get('fill') not in (None, 'none')
                units = num(ch.get('stroke-width'), 0) or None
                out['icons'].append({'id': did, 'name': ch.get('data-icon'), 'cx': r2(tx + size / 2),
                                     'cy': r2(ty + size / 2), 'size': size,
                                     'color': ch.get('fill') if filled else ch.get('stroke'), 'filled': filled,
                                     'stroke_units': units, 'deco': deco})
                continue
            walk(ch, local, out, shadow_defs)
        elif tag in ('rect', 'circle'):
            if tag == 'rect':
                w, h = num(ch.get('width')) * sx, num(ch.get('height')) * sy
                x, y = tx + sx * num(ch.get('x')), ty + sy * num(ch.get('y'))
                rx = num(ch.get('rx')) * sx
            else:
                r = num(ch.get('r')) * sx
                w = h = 2 * r
                x, y = tx + sx * num(ch.get('cx')) - r, ty + sy * num(ch.get('cy')) - r
                rx = r
            if ch.get('width') == '390' and ch.get('height') == '844' and not did:
                continue
            sw_ = num(ch.get('stroke-width'), 0) * sx if ch.get('stroke') else 0
            if ch.get('data-inset') and sw_:               # strokes are drawn inside: give back the nominal rectangle
                x, y, w, h, rx = x - sw_ / 2, y - sw_ / 2, w + sw_, h + sw_, rx + sw_ / 2
            m = re.search(r'url\(#([^)]+)\)', ch.get('filter') or '')
            out['boxes'].append({'id': did, 'kind': tag, 'x': r2(x), 'y': r2(y), 'w': r2(w), 'h': r2(h), 'rx': r2(rx),
                                 'fill': ch.get('fill'), 'fop': num(ch.get('fill-opacity'), 1.0),
                                 'op': num(ch.get('opacity'), 1.0), 'stroke': ch.get('stroke'),
                                 'sw': r2(sw_),
                                 'shadow': shadow_defs.get(m.group(1)) if m else None, 'deco': deco})
        elif tag == 'line':
            out['lines'].append({'id': did, 'x1': r2(tx + sx * num(ch.get('x1'))), 'y1': r2(ty + sy * num(ch.get('y1'))),
                                 'x2': r2(tx + sx * num(ch.get('x2'))), 'y2': r2(ty + sy * num(ch.get('y2'))),
                                 'stroke': ch.get('stroke'), 'sw': r2(num(ch.get('stroke-width'), 1) * sx), 'deco': deco})
        elif tag in ('clipPath', 'defs'):
            continue


def extract(path):
    root = ET.parse(path).getroot()
    sd = shadows(root)
    screens = {}
    for g in root.iter(NS + 'g'):
        screen = g.get('data-screen')
        if not screen:
            continue
        out = {'texts': [], 'icons': [], 'boxes': [], 'lines': []}
        walk(g, (0.0, 0.0, 1.0, 1.0), out, sd)
        tx, ty, _, _ = transform(g.get('transform'))
        out.update({'code': g.get('data-code'), 'title': g.get('data-title'), 'origin': [r2(tx), r2(ty)],
                    'size': [int(num(g.get('data-w'), 390)), int(num(g.get('data-h'), 844))]})
        screens[screen] = out
    return {'schema': 1, 'screens': screens}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('svg')
    ap.add_argument('-o', '--out', default='build/design_layout.json')
    a = ap.parse_args()
    data = extract(a.svg)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    n = {k: sum(len(s[k]) for s in data['screens'].values()) for k in ('texts', 'icons', 'boxes', 'lines')}
    print(f'{len(data["screens"])} screens -> {a.out}: {n}')
    if not data['screens']:
        sys.exit('no artboard with data-screen found: was the board made with frame.phone()?')


if __name__ == '__main__':
    main()
