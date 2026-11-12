#!/usr/bin/env python3
"""Pixel fallback: a second, independent look at every paired element. Numbers only; the heat maps are attachments.

    python3 pixel_diff.py --design-png d.png --app-png a.png --boxes boxes.json [--out heat.ppm]

parity.py calls pixel_issues() when its config has a "pixels" section:
    "pixels": {"design_png_dir": "build/design_png",       # <screen>.png, made by render_design_pngs.py
               "app_png_dir": "build/app",                  # <scene>.png, made by the render test
               "mae": 6.0,                                  # boxes / icons: mean absolute error over RGB, 0..255
               "ink_bbox_tol": 1.5,                         # text: ink bounding box edges, px
               "ink_cover_tol": 0.3,                        # text: relative difference of the amount of ink
               "ink": 60}                                   # a pixel is ink when it differs from the background by this much
Both PNGs must have the same size (the design is rendered at the scale the app PNG was captured at).
Text is not compared pixel by pixel (two engines anti-alias differently); its ink box and ink amount are. The check is
deliberately coarse: it catches what the attribute comparison cannot see (a wrong shape, a missing image, a shadow that
is not there), not sub-pixel taste. Standard library only (a small PNG reader: 8-bit, non-interlaced).
"""
import argparse
import json
import os
import struct
import sys
import zlib
from collections import Counter


def read_png(path):
    data = open(path, 'rb').read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{path} is not a PNG')
    pos, idat, ihdr = 8, b'', None
    while pos < len(data):
        n, typ = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if typ == b'IHDR':
            ihdr = struct.unpack('>IIBBBBB', body)
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
    w, h, depth, ctype, _, _, interlace = ihdr
    if depth != 8 or interlace or ctype not in (0, 2, 6):
        raise ValueError(f'{path}: only 8-bit non-interlaced gray/RGB/RGBA PNGs are supported')
    ch = {0: 1, 2: 3, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = w * ch
    rows, prev = [], bytearray(stride)
    i = 0
    for _ in range(h):
        ft = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if ft == 1:
            for x in range(ch, stride):
                line[x] = (line[x] + line[x - ch]) & 255
        elif ft == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif ft == 3:
            for x in range(stride):
                left = line[x - ch] if x >= ch else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 255
        elif ft == 4:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                b = prev[x]
                c = prev[x - ch] if x >= ch else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return {'w': w, 'h': h, 'ch': ch, 'rows': rows}


def rgb(img, x, y):
    r = img['rows'][y]
    o = x * img['ch']
    return (r[o], r[o], r[o]) if img['ch'] == 1 else (r[o], r[o + 1], r[o + 2])


def clip_rect(img, x, y, w, h, grow=0):
    x0, y0 = max(0, int(x - grow)), max(0, int(y - grow))
    x1, y1 = min(img['w'], int(x + w + grow + 0.999)), min(img['h'], int(y + h + grow + 0.999))
    return x0, y0, x1, y1


def mae(a, b, rect):
    x0, y0, x1, y1 = rect
    total = n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            pa, pb = rgb(a, x, y), rgb(b, x, y)
            total += abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
            n += 3
    return total / n if n else 0.0


def ink(img, rect, thresh):
    """(bbox, amount) of the pixels that differ from the background colour (the commonest colour on the rect's border)."""
    x0, y0, x1, y1 = rect
    border = Counter()
    for x in range(x0, x1):
        border[rgb(img, x, y0)] += 1
        border[rgb(img, x, y1 - 1)] += 1
    for y in range(y0, y1):
        border[rgb(img, x0, y)] += 1
        border[rgb(img, x1 - 1, y)] += 1
    bg = border.most_common(1)[0][0]
    xs, ys, amount = [], [], 0.0
    for y in range(y0, y1):
        for x in range(x0, x1):
            p = rgb(img, x, y)
            d = abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2])
            if d > thresh:
                xs.append(x)
                ys.append(y)
                amount += min(d, 255 * 3) / (255 * 3)
    if not xs:
        return None, 0.0
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1), amount


def compare_item(a, b, item, cfg):
    """-> list of (property, design value, app value, tolerance)."""
    out = []
    if item['kind'] == 'text':
        rect = clip_rect(a, *item['rect'], grow=4)
        ba, ca = ink(a, rect, cfg['ink'])
        bb, cb = ink(b, rect, cfg['ink'])
        if (ba is None) != (bb is None):
            out.append(('ink present', ba is not None, bb is not None, None))
        elif ba:
            for name, va, vb in zip(('ink x0', 'ink y0', 'ink x1', 'ink y1'), ba, bb):
                if abs(va - vb) > cfg['ink_bbox_tol']:
                    out.append((name, va, vb, cfg['ink_bbox_tol']))
            if ca and abs(ca - cb) / ca > cfg['ink_cover_tol']:
                out.append(('ink amount', round(ca, 1), round(cb, 1), cfg['ink_cover_tol']))
    else:
        rect = clip_rect(a, *item['rect'], grow=1)
        m = mae(a, b, rect)
        if m > cfg['mae']:
            out.append(('mae', 0, round(m, 2), cfg['mae']))
    return out


def items_for(screen, d, app, prefix):
    """Elements to compare: paired ids with the rectangle to look at."""
    texts = {prefix + t['id']: t for t in app.get('texts', []) if t.get('id')}
    out = []
    for t in d['texts']:
        if t['id'] in texts and not t['deco']:
            a = texts[t['id']]
            out.append({'id': t['id'], 'kind': 'text', 'rect': (a['l'], a['t'], a['w'], a['h'])})
    appicons = {prefix + i['id'] for i in app.get('icons', []) if i.get('id')}
    for i in d['icons']:
        if i['id'] in appicons and not i['deco']:
            out.append({'id': i['id'], 'kind': 'icon', 'rect': (i['cx'] - i['size'] / 2, i['cy'] - i['size'] / 2, i['size'], i['size'])})
    appboxes = {prefix + b['id'] for b in app.get('boxes', []) if b.get('id')}
    for b in d['boxes']:
        if b['id'] in appboxes and not b['deco'] and min(b['w'], b['h']) >= 4 and (b['fill'] not in (None, 'none') or b['stroke']):
            pad = 0
            if b.get('shadow'):
                pad = 0
            out.append({'id': b['id'], 'kind': 'box', 'rect': (b['x'], b['y'], b['w'], b['h'])})
    return out


def pixel_issues(cfg, base, design, iss):
    px = {'mae': 6.0, 'ink_bbox_tol': 1.5, 'ink_cover_tol': 0.3, 'ink': 60, **cfg['pixels']}
    for screen, scene in cfg['screens'].items():
        dpng = os.path.join(base, px['design_png_dir'], screen + '.png')
        apng = os.path.join(base, px['app_png_dir'], scene + '.png')
        if not (os.path.exists(dpng) and os.path.exists(apng)):
            raise SystemExit(f'parity: pixel check needs {dpng} and {apng}')
        a, b = read_png(dpng), read_png(apng)
        if (a['w'], a['h']) != (b['w'], b['h']):
            raise SystemExit(f'parity: {screen}: design PNG is {a["w"]}x{a["h"]}, app PNG {b["w"]}x{b["h"]}; render both at one scale')
        app = json.load(open(os.path.join(base, cfg['app_dir'], scene + '.json'), encoding='utf-8'))
        scale = a['w'] / design[screen]['size'][0]
        for item in items_for(screen, design[screen], app, screen + '/'):
            item['rect'] = tuple(v * scale for v in item['rect'])
            for prop, dv, av, tol in compare_item(a, b, item, px):
                iss.add(screen, item['id'], item['kind'], 'pixel', prop, dv, av, tol)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--design-png', required=True)
    ap.add_argument('--app-png', required=True)
    ap.add_argument('--boxes', required=True, help='JSON list of {id, kind: text|icon|box, rect: [x, y, w, h]} in px of the PNG')
    ap.add_argument('--mae', type=float, default=6.0)
    ap.add_argument('--ink', type=int, default=60)
    a = ap.parse_args()
    d, p = read_png(a.design_png), read_png(a.app_png)
    cfg = {'mae': a.mae, 'ink': a.ink, 'ink_bbox_tol': 1.5, 'ink_cover_tol': 0.3}
    bad = 0
    for item in json.load(open(a.boxes, encoding='utf-8')):
        for prop, dv, av, tol in compare_item(d, p, item, cfg):
            bad += 1
            print(f'{item["id"]}: {prop} design {dv} app {av} (tol {tol})')
    print('PIXEL', 'FAIL' if bad else 'PASS', f'({bad} differences)')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
