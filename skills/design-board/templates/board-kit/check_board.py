#!/usr/bin/env python3
"""Static checks for the generated board (no browser needed).

    python3 check_board.py board.svg [--require-ids] [--box-coverage 0.0]

Fails (exit 1) on: malformed XML; constructs many viewers draw as black boxes or nothing (<style>, CSS variables,
foreignObject, external images, scripts); dangling url(#id) references; duplicate ids; duplicate data-id or data-screen;
NaN/None/undefined in text or numbers; empty <text>; CRLF or trailing whitespace; a missing final newline.
With --require-ids every <text> and icon inside an artboard must carry data-id (or be marked data-deco), and the share
of tagged boxes (rect/circle) must reach --box-coverage. This is a source check only: it says nothing about how the
board looks.
"""
import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'
FORBIDDEN = [('<style', 'CSS <style> block'), ('var(--', 'CSS variable'), ('foreignObject', 'foreignObject'),
             ('<image', 'embedded/external image'), ('<script', 'script'), ('href="http', 'external link'),
             ('@import', 'CSS import'), ('onload=', 'event handler')]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('svg')
    ap.add_argument('--require-ids', action='store_true')
    ap.add_argument('--box-coverage', type=float, default=0.0)
    a = ap.parse_args()
    path = os.path.abspath(a.svg)
    raw = open(path, 'rb').read()
    s = raw.decode('utf-8')
    problems = []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print('FAIL  XML is not well-formed:', e)
        sys.exit(1)

    for needle, what in FORBIDDEN:
        if needle in s:
            problems.append(f'uses {what} ({needle!r})')

    ids = re.findall(r'(?<![\w-])id="([^"]+)"', s)
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        problems.append(f'duplicate ids: {dup[:8]}')
    refs = set(re.findall(r'url\(#([^)]+)\)', s))
    missing = sorted(refs - set(ids))
    if missing:
        problems.append(f'url(#id) with no matching id: {missing[:8]}')

    texts = list(root.iter(NS + 'text'))
    empty = [t for t in texts if not ''.join(t.itertext()).strip()]
    if empty:
        problems.append(f'{len(empty)} empty <text> elements')
    bad = [t for t in texts if re.search(r'\b(None|NaN|nan|undefined|null)\b', ''.join(t.itertext()))]
    if bad:
        problems.append(f'{len(bad)} <text> contain None/NaN/undefined: {["".join(t.itertext())[:30] for t in bad[:3]]}')
    if re.search(r'="[^"]*\b(nan|inf|None)\b[^"]*"', s):
        problems.append('NaN/inf/None inside an attribute value')
    if '\r' in s:
        problems.append('contains CR (CRLF line endings)')
    trailing = [i + 1 for i, line in enumerate(s.split('\n')) if line != line.rstrip()]
    if trailing:
        problems.append(f'trailing whitespace on {len(trailing)} lines (first: {trailing[:5]})')
    if not s.endswith('\n'):
        problems.append('no final newline')

    # per-screen ids
    screens = [g.get('data-screen') for g in root.iter(NS + 'g') if g.get('data-screen')]
    dup_screen = sorted({x for x in screens if screens.count(x) > 1})
    if dup_screen:
        problems.append(f'duplicate data-screen: {dup_screen}')
    data_ids = []
    untagged_text = untagged_icon = boxes = tagged_boxes = 0
    for art in (g for g in root.iter(NS + 'g') if g.get('data-screen')):
        parent = {c: p for p in art.iter() for c in p}
        inside_icon = {d for g in art.iter() if g.get('data-icon') for d in g.iter() if d is not g}
        for el in art.iter():
            tag = el.tag.replace(NS, '')
            did = el.get('data-id')
            if did and el.get('data-line') in (None, '0'):
                data_ids.append(did)
            if el in inside_icon or el.get('data-deco') or (el in parent and parent[el].tag.replace(NS, '') == 'clipPath'):
                continue
            if tag == 'text' and not did:
                untagged_text += 1
            elif tag == 'g' and el.get('data-icon') and not did:
                untagged_icon += 1
            elif tag in ('rect', 'circle'):
                boxes += 1
                tagged_boxes += 1 if did else 0
    dup_id = sorted({x for x in data_ids if data_ids.count(x) > 1})
    if dup_id:
        problems.append(f'duplicate data-id: {dup_id[:8]}')
    cover = tagged_boxes / boxes if boxes else 1.0
    if a.require_ids:
        if untagged_text:
            problems.append(f'{untagged_text} <text> without data-id (give it id=..., or deco=True for decoration)')
        if untagged_icon:
            problems.append(f'{untagged_icon} icons without data-id')
        if cover < a.box_coverage:
            problems.append(f'only {cover:.0%} of boxes carry data-id, need {a.box_coverage:.0%}')

    w, h = root.get('width'), root.get('height')
    print(f'{os.path.relpath(path)}: {len(raw) // 1024} KB, {w} x {h}, {len(screens)} artboards, {len(texts)} texts, '
          f'{len(data_ids)} data-ids (untagged: {untagged_text} texts, {untagged_icon} icons; boxes tagged {cover:.0%})')
    if problems:
        for p in problems:
            print('FAIL ', p)
        sys.exit(1)
    print('OK    all static checks passed (this is not a visual check)')


if __name__ == '__main__':
    main()
