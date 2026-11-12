#!/usr/bin/env python3
"""Builds the app's icon fonts from the board's icon list, so the app draws the same icons at the same stroke.

    pip install fonttools
    python3 build_icon_font.py --icons icons.json --tokens tokens.json \
        --lucide-pkg ~/.pub-cache/hosted/pub.dev/lucide_icons_flutter-4.0.3 \
        --out-fonts assets/fonts --out-dart lib/app_icons.g.dart [--prefix AppIcons]

Why one font per weight: a font glyph has one stroke width, the board's rule is a stroke by size (tokens
scales.icon_stroke_units: e.g. 12 px 1.5 px, 16 px 1.67 px, 24 px 2 px). So every weight the rule uses (units * 200:
w300 / w400 / w500 / w600) gets its own small font, and AppGlyph.at(size) picks the one for the size.
Outputs
    <out-fonts>/<Prefix>-w<weight>.ttf     only the glyphs icons.json names (about 10 KB each)
    <out-fonts>/app_icons.json            design key -> icon-set name + code point (parity.py reads it)
    <out-dart>                            const IconData per weight + the <Prefix> glyph table
Glyph outlines come from the static weight fonts of the `lucide_icons_flutter` package (MIT; Lucide is ISC); its Lucide
version must equal icons.json's version. Those fonts centre every glyph on its own bounds, so each glyph is moved back to
where the SVG sits on the 24 grid (place_like_svg); a glyph that differs in size, not only in position, stops the build.
Entries with "custom": true are drawn from their own svg (straight segments only: M L H V Z, 24-grid, y down) and added
to every weight at U+F100 upwards. Flutter's release build keeps only the glyphs the app references.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

from fontTools import subset
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont

UPM = 1000                  # the Lucide fonts: the 24-grid icon in a 1000 x 1000 em, baseline at the bottom
CUSTOM_START = 0xF100


def camel(key):
    head, *rest = re.split(r'[-_ ]+', key)
    return head + ''.join(p[:1].upper() + p[1:] for p in rest)


def find_pkg(arg):
    if arg:
        return os.path.expanduser(arg)
    cache = os.environ.get('PUB_CACHE') or os.path.expanduser('~/.pub-cache')
    hits = sorted(glob.glob(os.path.join(cache, 'hosted', 'pub.dev', 'lucide_icons_flutter-*')))
    if not hits:
        sys.exit('lucide_icons_flutter is not in the pub cache: `flutter pub add lucide_icons_flutter` in a scratch project, or pass --lucide-pkg')
    return hits[-1]


def svg_bounds(markup):
    """Bounds of an icon's drawing in the 24 grid (y down), before the stroke is added."""
    root = ET.fromstring(f'<g xmlns="http://www.w3.org/2000/svg">{markup}</g>')
    xs, ys = [], []
    for el in root:
        tag, a = el.tag.split('}')[1], el.attrib
        if tag == 'path':
            pen = BoundsPen(None)
            parse_path(a['d'], pen)
            x0, y0, x1, y1 = pen.bounds
            xs += [x0, x1]
            ys += [y0, y1]
        elif tag == 'circle':
            cx, cy, r = float(a['cx']), float(a['cy']), float(a['r'])
            xs += [cx - r, cx + r]
            ys += [cy - r, cy + r]
        elif tag == 'rect':
            x, y, w, h = (float(a.get(k, 0)) for k in ('x', 'y', 'width', 'height'))
            xs += [x, x + w]
            ys += [y, y + h]
        elif tag == 'line':
            xs += [float(a['x1']), float(a['x2'])]
            ys += [float(a['y1']), float(a['y2'])]
        else:
            raise ValueError(f'unhandled <{tag}> in an icon')
    return min(xs), min(ys), max(xs), max(ys)


def place_like_svg(font, units, cp, markup):
    """Move the glyph to where the SVG puts it on the 24 grid (a pure shift; a size difference stops the build)."""
    name = font.getBestCmap()[cp]
    half = units / 2
    bx0, by0, bx1, by1 = svg_bounds(markup)
    k = UPM / 24
    ex0, ex1 = (bx0 - half) * k, (bx1 + half) * k
    ey0, ey1 = (24 - (by1 + half)) * k, (24 - (by0 - half)) * k
    gs = font.getGlyphSet()
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    ax0, ay0, ax1, ay1 = pen.bounds
    if max(abs((ex1 - ex0) - (ax1 - ax0)), abs((ey1 - ey0) - (ay1 - ay0))) > 10:
        sys.exit(f'U+{cp:04X}: glyph size differs from the SVG by more than 10 units (not a pure shift)')
    dx, dy = round(((ex0 - ax0) + (ex1 - ax1)) / 2), round(((ey0 - ay0) + (ey1 - ay1)) / 2)
    if dx or dy:
        glyph = font['glyf'][name]
        glyph.coordinates.translate((dx, dy))
        glyph.recalcBounds(font['glyf'])
        font['hmtx'].metrics[name] = (font['hmtx'].metrics[name][0], glyph.xMin)
    return dx, dy


def polygon_contours(markup):
    """Contours (font units, y up) of a custom icon made of straight segments, orientation fixed for TrueType."""
    root = ET.fromstring(f'<g xmlns="http://www.w3.org/2000/svg">{markup}</g>')
    contours = []
    for el in root:
        if el.tag.split('}')[1] != 'path':
            raise ValueError('custom icons must be <path> elements made of straight segments')
        d = el.attrib['d']
        if re.search(r'[CcSsQqTtAa]', d):
            raise ValueError('custom icons: curves are not supported here (M L H V Z only)')
        x = y = sx = sy = 0.0
        pts = []
        for cmd, args in re.findall(r'([MmLlHhVvZz])([^MmLlHhVvZz]*)', d):
            n = [float(v) for v in re.findall(r'-?\d*\.?\d+(?:e-?\d+)?', args)]
            if cmd in 'Zz':
                if pts:
                    contours.append(pts)
                pts, x, y = [], sx, sy
                continue
            step = {'M': 2, 'm': 2, 'L': 2, 'l': 2, 'H': 1, 'h': 1, 'V': 1, 'v': 1}[cmd]
            for i in range(0, len(n), step):
                if cmd in 'Mm':
                    x, y = (n[i], n[i + 1]) if cmd == 'M' else (x + n[i], y + n[i + 1])
                    if not pts:
                        sx, sy = x, y
                elif cmd in 'Ll':
                    x, y = (n[i], n[i + 1]) if cmd == 'L' else (x + n[i], y + n[i + 1])
                elif cmd in 'Hh':
                    x = n[i] if cmd == 'H' else x + n[i]
                elif cmd in 'Vv':
                    y = n[i] if cmd == 'V' else y + n[i]
                pts.append((round(x * UPM / 24), round((24 - y) * UPM / 24)))
                if cmd in 'Mm':
                    cmd = 'L' if cmd == 'M' else 'l'     # coordinate pairs after the first are implicit lineto
        if pts:
            contours.append(pts)

    def area(c):
        return sum(c[i][0] * c[(i + 1) % len(c)][1] - c[(i + 1) % len(c)][0] * c[i][1] for i in range(len(c))) / 2

    def inside(pt, c):
        px, py, hit = pt[0], pt[1], False
        for i in range(len(c)):
            (x1, y1), (x2, y2) = c[i], c[(i + 1) % len(c)]
            if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
                hit = not hit
        return hit

    out = []
    for i, c in enumerate(contours):
        hole = any(j != i and inside(c[0], o) for j, o in enumerate(contours))
        if hole != (area(c) > 0):              # TrueType: outer clockwise, hole counter-clockwise
            c = c[::-1]
        out.append(c)
    return out


def add_custom(font, cp, contours):
    pen = TTGlyphPen(None)
    for c in contours:
        pen.moveTo(c[0])
        for p in c[1:]:
            pen.lineTo(p)
        pen.closePath()
    name = 'uni%04X' % cp
    order = font.getGlyphOrder()
    font.setGlyphOrder(order + [name])
    font['glyf'][name] = pen.glyph()
    font['hmtx'].metrics[name] = (UPM, min(x for c in contours for x, _ in c))
    for table in font['cmap'].tables:
        if table.isUnicode():
            table.cmap[cp] = name
    font['maxp'].numGlyphs = len(order) + 1


def set_names(font, family, notice):
    names = font['name']
    names.names = []
    for nid, text in ((0, notice), (1, family), (2, 'Regular'), (3, family), (4, family), (5, 'Version 1.0'),
                      (6, family), (13, notice)):
        names.setName(text, nid, 3, 1, 0x409)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--icons', required=True)
    ap.add_argument('--tokens', required=True)
    ap.add_argument('--lucide-pkg')
    ap.add_argument('--out-fonts', default='assets/fonts')
    ap.add_argument('--out-dart', default='lib/app_icons.g.dart')
    ap.add_argument('--prefix', default='AppIcons')
    ap.add_argument('--allow-version-mismatch', action='store_true')
    a = ap.parse_args()

    pkg = find_pkg(a.lucide_pkg)
    assets = os.path.join(pkg, 'assets')
    cps = json.load(open(os.path.join(assets, 'codepoints.json'), encoding='utf-8'))
    pkg_version = re.search(r'^version:\s*(\S+)', open(os.path.join(pkg, 'pubspec.yaml'), encoding='utf-8').read(), re.M).group(1)
    m = re.search(r'Lucide version:\s*([\d.]+)', open(os.path.join(pkg, 'README.md'), encoding='utf-8').read())
    spec = json.load(open(a.icons, encoding='utf-8'))
    tokens = json.load(open(a.tokens, encoding='utf-8'))
    if (m.group(1) if m else None) != spec['version'] and not a.allow_version_mismatch:
        sys.exit(f'the font package carries Lucide {m.group(1) if m else "?"} but icons.json is {spec["version"]}: '
                 f'sync_icons.py --version, or --allow-version-mismatch')
    weights = sorted({round(r['units'] * 200) for r in tokens['scales']['icon_stroke_units']})
    keys = list(spec['icons'])
    set_keys = [k for k in keys if not spec['icons'][k].get('custom')]
    custom_keys = [k for k in keys if spec['icons'][k].get('custom')]
    missing = [k for k in set_keys if spec['icons'][k]['name'] not in cps]
    if missing:
        sys.exit('not in the font: ' + ', '.join(f'{k} ({spec["icons"][k]["name"]})' for k in missing))
    unicodes = sorted({cps[spec['icons'][k]['name']] for k in set_keys})
    custom_cp = {k: CUSTOM_START + i for i, k in enumerate(custom_keys)}
    contours = {k: polygon_contours(spec['icons'][k]['svg']) for k in custom_keys}

    os.makedirs(a.out_fonts, exist_ok=True)
    sources, sizes = {}, {}
    notice = (f'{spec.get("set", "icons")} {spec["version"]} (Lucide: ISC, Feather parts MIT) in the weight fonts of '
              f'lucide_icons_flutter {pkg_version} (MIT). Custom glyphs are drawn from the board.')
    for w in weights:
        src = os.path.join(assets, 'build_font', f'LucideVariable-w{w}.ttf')
        if not os.path.exists(src):
            sys.exit(f'the package has no weight {w}: {src}')
        sources[w] = hashlib.sha256(open(src, 'rb').read()).hexdigest()[:16]
        font = TTFont(src)
        opts = subset.Options()
        opts.glyph_names = False
        opts.hinting = False
        opts.layout_features = []
        opts.name_IDs = []
        opts.notdef_outline = True
        opts.drop_tables = sorted(set(opts.drop_tables) | {'FFTM', 'cvt ', 'gasp', 'GSUB', 'GPOS', 'GDEF'})
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=unicodes)
        sub.subset(font)
        shifts = {}
        for k in set_keys:
            cp = cps[spec['icons'][k]['name']]
            if cp not in shifts:
                shifts[cp] = place_like_svg(font, w / 200, cp, spec['icons'][k]['svg'])
        for k in custom_keys:
            add_custom(font, custom_cp[k], contours[k])
        set_names(font, f'{a.prefix}{w}', notice)
        out = os.path.join(a.out_fonts, f'{a.prefix}-w{w}.ttf')
        font.save(out)
        sizes[w] = os.path.getsize(out)
        cmap = TTFont(out).getBestCmap()
        absent = [cp for cp in unicodes + list(custom_cp.values()) if cp not in cmap]
        if absent:
            sys.exit(f'w{w}: code points missing after the build: {absent}')
        moved = sum(1 for d in shifts.values() if d != (0, 0))
        print(f'  w{w}: {sizes[w]:,} bytes, {moved} glyphs moved onto the SVG grid')

    icons = {k: {'name': spec['icons'][k].get('name'), 'cp': custom_cp[k] if k in custom_cp else cps[spec['icons'][k]['name']]}
             for k in keys}
    with open(os.path.join(a.out_fonts, 'app_icons.json'), 'w', encoding='utf-8') as fh:
        json.dump({'schema': 1, 'set': spec.get('set'), 'version': spec['version'], 'fontBuild': f'lucide_icons_flutter {pkg_version}',
                   'families': {f'{a.prefix}{w}': w for w in weights}, 'sourceSha256': {str(w): s for w, s in sources.items()},
                   'icons': icons}, fh, ensure_ascii=False, indent=1)
        fh.write('\n')

    L = ['// GENERATED by build_icon_font.py from icons.json. Do not edit.',
         f'// {spec.get("set", "icons")} {spec["version"]} (Lucide: ISC, Feather parts MIT) in the weight fonts of lucide_icons_flutter {pkg_version} (MIT).',
         '', "import 'package:flutter/widgets.dart';", '', "import 'app_glyph.dart';", '']
    for w in weights:
        L += [f'/// The icons at stroke weight {w}.', '@staticIconProvider', f'abstract final class {a.prefix}{w} {{']
        for k in keys:
            L.append(f"  static const IconData {camel(k)} = IconData(0x{icons[k]['cp']:X}, fontFamily: '{a.prefix}{w}');")
        L += ['}', '']
    L += ["/// Every icon of the board, by the board's own keys (icons.json).", '@staticIconProvider', f'abstract final class {a.prefix} {{']
    for k in keys:
        L.append(f"  /// {spec['icons'][k].get('name') or 'custom glyph'}")
        L.append(f'  static const AppGlyph {camel(k)} = AppGlyph({{' + ', '.join(f'{w}: {a.prefix}{w}.{camel(k)}' for w in weights) + '});')
    L += ['}', '']
    with open(a.out_dart, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(L))
    print(f'{len(keys)} icons ({len(custom_keys)} custom) x {len(weights)} weights -> {a.out_fonts}, {a.out_dart}')


if __name__ == '__main__':
    main()
