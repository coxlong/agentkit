#!/usr/bin/env python3
"""Refreshes icons.json from the official release of an icon set, so the board draws the real icons.

    python3 sync_icons.py icons.json                  # refetch every svg at the pinned version
    python3 sync_icons.py icons.json --version 1.70.0 # pin another release
    python3 sync_icons.py icons.json --check          # exit 1 if the file differs from the release (no write)

icons.json:
  {"set": "lucide", "version": "1.70.0",
   "source": "https://cdn.jsdelivr.net/npm/lucide-static@{version}/icons/{name}.svg",
   "icons": {"back": {"name": "arrow-left"}, "think": {"custom": true, "svg": "<path .../>"}}}
Each design key maps to an official icon name; `custom` entries keep their own svg (a filled glyph that is not in the
set) and are never fetched. The app's icon font is built from the same file (flutter/build_icon_font.py), so the board
and the app draw the same shapes at the same stroke. Standard library only.
"""
import argparse
import json
import re
import sys
import urllib.request


def fetch_inner(source, version, name):
    with urllib.request.urlopen(source.format(version=version, name=name), timeout=30) as r:
        svg = r.read().decode('utf-8')
    body = re.search(r'<svg[^>]*>(.*)</svg>', svg, re.S).group(1)
    body = re.sub(r'<!--.*?-->', '', body, flags=re.S)
    body = re.sub(r'\s+', ' ', body).strip()
    body = re.sub(r'\s*/>', '/>', body)
    return body.replace('> <', '><')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path')
    ap.add_argument('--version')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    data = json.load(open(a.path, encoding='utf-8'))
    version = a.version or data['version']
    names = sorted({v['name'] for v in data['icons'].values() if not v.get('custom')})
    inner = {}
    for n in names:
        try:
            inner[n] = fetch_inner(data['source'], version, n)
        except Exception as e:                          # noqa: BLE001 - name the icon, then stop
            sys.exit(f'cannot fetch {n} @ {version}: {e}')
    changed = []
    for key, v in data['icons'].items():
        if v.get('custom'):
            continue
        if v.get('svg') != inner[v['name']]:
            changed.append(key)
            v['svg'] = inner[v['name']]
    data['version'] = version
    if a.check:
        print('differs:', ', '.join(changed) if changed else 'nothing')
        sys.exit(1 if changed else 0)
    with open(a.path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    print(f'{len(data["icons"])} icons @ {version}; updated: {", ".join(changed) if changed else "none"}')


if __name__ == '__main__':
    main()
