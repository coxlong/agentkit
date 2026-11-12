#!/usr/bin/env python3
"""Lists every string the board shows (from the extract), to review the copy.

    python3 copy_audit.py build/design_layout.json [--min 2]

Prints strings by how many screens show them (a status said in several places is a smell), then the longest strings
(candidates to cut). Decoration is skipped. Standard library only.
"""
import argparse
import json
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('layout')
    ap.add_argument('--min', type=int, default=2, help='only strings shown on at least this many screens')
    a = ap.parse_args()
    data = json.load(open(a.layout, encoding='utf-8'))['screens']
    seen = defaultdict(set)
    for name, s in data.items():
        for t in s['texts']:
            if not t['deco']:
                seen[' '.join(t['s'].split())].add(name)
    print(f'{len(seen)} distinct strings on {len(data)} screens')
    print(f'\n== shown on >= {a.min} screens ==')
    for text, screens in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        if len(screens) >= a.min:
            print(f'{len(screens):3d}  {text[:70]}')
    print('\n== longest ==')
    for text in sorted(seen, key=len, reverse=True)[:10]:
        print(f'{len(text):3d}  {text[:90]}')


if __name__ == '__main__':
    main()
