#!/usr/bin/env python3
"""A tiny board built with the kit: two screens (a settings list, a chat card), light and dark. Run it from anywhere:

    python3 build_example.py --out /tmp/example_board.svg
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, KIT)
import frame  # noqa: E402
import kit  # noqa: E402


def status_bar(g):
    g.text(24, 14, '9:41', 'caption', deco=True)


def top_bar(g, title):
    g.ic('back', 36, 68, 24, g.t.ink, id='bar/back')
    g.text(64, 56, title, 'title', id='bar/title')


def settings(data, g):
    d = data['settings']
    top_bar(g, d['title'])
    for i, row in enumerate(d['rows'], 1):
        y = 112 + (i - 1) * 72
        g.rect(20, y, 350, 64, 16, g.t.surface, g.t.line, 1, shadow='card', id=f'row/{i}/box')
        g.ic(row['icon'], 44, y + 32, 20, g.t.brandInk, id=f'row/{i}/icon')
        g.text(68, y + 10, row['title'], 'row-title', id=f'row/{i}/title')
        g.text(68, y + 34, row['sub'], 'caption', g.t.muted, maxw=240, id=f'row/{i}/sub')
        g.ic('chevron', 346, y + 32, 16, g.t.muted, id=f'row/{i}/chev')
    g.rect(20, 740, 350, 52, 26, g.t.brand, id='cta/box')
    g.text(195, 755, d['cta'], 'button', g.t.onBrand, anchor='middle', id='cta/label')


def chat(data, g):
    d = data['chat']
    top_bar(g, d['title'])
    n = len(kit.ruler().wrap(d['message'], 16, 400, False, 318))
    h = 16 + n * 24 + 8 + 16 + 16
    g.rect(20, 112, 350, h, 16, g.t.surface, g.t.line, 1, shadow='card', id='card/box')
    g.lines(36, 128, d['message'], 'body', maxw=318, id='card/text')
    g.text(36, 128 + n * 24 + 8, d['meta'], 'caption', g.t.muted, id='card/meta')
    g.ic('check', 346, 128 + n * 24 + 16, 16, g.t.green, id='card/done')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='example_board.svg')
    ap.add_argument('--tokens', default=os.path.join(KIT, 'tokens.example.json'))
    ap.add_argument('--icons', default=os.path.join(KIT, 'icons.example.json'))
    ap.add_argument('--data', default=os.path.join(KIT, 'sample_data.example.json'))
    ap.add_argument('--measured')
    ap.add_argument('--meta', help='write screen_meta.json (content hashes + render regions) here')
    ap.add_argument('--id-index')
    ap.add_argument('--needed')
    a = ap.parse_args()
    K = kit.init(a.tokens, icons=a.icons, measured=a.measured)
    data = json.load(open(a.data, encoding='utf-8'))
    b = frame.Board(cols=2)
    b.section('A', 'Example', 'Two screens, light and dark')
    b.screen('settings.list', 'Settings list', lambda g: settings(data, g), K.light, 'Rows with icon, title, truncated subtitle.', status=status_bar)
    b.screen('chat.card', 'Chat card', lambda g: chat(data, g), K.light, 'A wrapped paragraph in a card with a shadow.', status=status_bar)
    b.screen('settings.list.dark', 'Settings list, dark', lambda g: settings(data, g), K.dark, 'Same ids, dark palette.', status=status_bar)
    b.screen('chat.card.dark', 'Chat card, dark', lambda g: chat(data, g), K.dark, 'Same ids, dark palette.', status=status_bar)
    open(a.out, 'w', encoding='utf-8').write(b.svg())
    if a.meta:
        b.write_meta(a.meta)
    if a.id_index:
        kit.write_id_index(a.id_index)
    missing = kit.write_needed_text(a.needed) if a.needed else 0
    for w in kit.WARNINGS:
        print('WARN', w)
    print(f'{a.out}: {len(b.codes)} artboards {b.codes}; ruler: {"measured" if K.ruler.measured else "estimate"}'
          + (f'; {missing} strings still estimated -> {a.needed}' if missing else ''))


if __name__ == '__main__':
    main()
