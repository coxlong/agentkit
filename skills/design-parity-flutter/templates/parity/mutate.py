#!/usr/bin/env python3
"""Proves the parity check itself works: break things on purpose and demand that each break is caught.

    python3 mutate.py selftest --config parity.config.json         # needs no app: builds a perfect app dump from the design
    python3 mutate.py dump     --config parity.config.json         # mutates copies of the REAL app dumps (comparator proof)
    python3 mutate.py source   --config parity.config.json --mutations mutations.json --render-cmd "./tool/render.sh"
                                                                   # patches the app's source, renders, checks, restores
Every mode writes <report dir>/mutation_report.json and exits 1 if any mutation was NOT detected, or if the unmutated
state does not come back to zero new differences ("restore must clear it").

dump / selftest mutations (each changes one value of one element, by id):
  font-size +1 | weight | colour (one blue step) | baseline +4 px (spacing) | x +3 | box width +4 | radius +2 |
  wrong icon | icon size +4 | shadow blur +4 | border width +1 | ellipsis lost | line count +1 | missing element |
  extra element | render overflow | small tap target | text content | line height | paragraph alignment | icon position / colour /
  weight font | box fill | overlapping texts | two ids on one render object | id coverage
`dump` proves the comparator on real data. It does NOT prove the app's dumper; `source` does, because the app really draws
the mutated source.
"""
import argparse
import copy
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parity  # noqa: E402


# ── a perfect app dump made from the design ──────────────────────────────────────
def synth(design_screen, name_to_cp, screen):
    """What an app that matches the design exactly would dump (ids without the screen prefix)."""
    pre = screen + '/'
    strip = lambda i: i[len(pre):] if i and i.startswith(pre) else i  # noqa: E731
    texts, icons, boxes = [], [], []
    for t in design_screen['texts']:
        if t['deco'] or not t['id']:
            continue
        w = round(max(len(t['s'].split('\n')[0]) * t['fs'] * 0.5, 4), 2)
        lh = t.get('lh') or t['fs'] * 1.4
        ll = t['x'] - (w / 2 if t['anchor'] == 'middle' else w if t['anchor'] == 'end' else 0)
        texts.append({'id': strip(t['id']), 's': t['s'].replace('\n', ' ').replace('…', '…'), 'l': ll, 't': t['y'] - lh * 0.8,
                      'w': w, 'h': lh * t['lines'], 'bl': t['y'], 'll': ll, 'lw': w, 'lines': t['lines'], 'fs': t['fs'],
                      'fw': t['fw'], 'c': t['fill'], 'a': t['op'], 'lh': lh / t['fs'], 'ellipsis': t['s'].endswith('…'),
                      'align': t['anchor']})
    for i in design_screen['icons']:
        if i['deco'] or not i['id']:
            continue
        w = parity_weight(i)
        icons.append({'id': strip(i['id']), 'cp': name_to_cp.get(i['name'], 0xE000), 'ff': w, 'size': i['size'],
                      'cx': i['cx'], 'cy': i['cy'], 'c': i['color'], 'a': 1.0})
    for b in parity.design_boxes(design_screen):
        if not b['id']:
            continue
        r = min(b['rx'], min(b['w'], b['h']) / 2)
        boxes.append({'id': strip(b['id']), 'k': 'deco', 'l': b['x'], 't': b['y'], 'w': b['w'], 'h': b['h'],
                      'c': b['fill'] if b['fill'] != 'none' else None, 'a': b['fop'] * b['op'],
                      'circle': b['kind'] == 'circle', 'r': {'tl': r, 'tr': r, 'bl': r, 'br': r},
                      'border': {'c': b['stroke'], 'w': b['sw']} if b['stroke'] else None,
                      'shadows': [{'dx': b['shadow']['dx'], 'dy': b['shadow']['dy'], 'blur': b['shadow']['blur'],
                                   'c': b['shadow']['color'], 'a': b['shadow']['opacity']}] if b.get('shadow') else []})
    return {'texts': texts, 'icons': icons, 'boxes': boxes,
            'invariants': {'overflows': [], 'taps': [], 'coverage': {
                'texts': {'tagged': len(texts), 'total': len(texts)}, 'icons': {'tagged': len(icons), 'total': len(icons)},
                'boxes': {'tagged': len(boxes), 'total': len(boxes)}}}}


FAMILY = ['AppIcons{weight}']


def parity_weight(icon):
    units = icon.get('stroke_units') or 2.0
    return FAMILY[0].format(weight=parity.weight_of_units(units))


# ── mutations: (name, expected category, function(dump) -> id of the element changed or None) ─────────
_AVOID = []          # baseline entries: a mutation must not land on an element whose difference is already accepted
_SCREEN = ['']


def baselined(raw_id):
    full = f'{_SCREEN[0]}/{raw_id}'
    return any(fnmatch.fnmatch(_SCREEN[0], e['screen']) and (e.get('id') is None or fnmatch.fnmatch(full, e['id'])) for e in _AVOID)


def first(dump, key, pred=lambda e: True):
    return next((e for e in dump.get(key, []) if e.get('id') and not baselined(e['id']) and pred(e)), None)


def m_font(d):
    t = first(d, 'texts')
    if t:
        t['fs'] += 1
        return t['id']


def m_weight(d):
    t = first(d, 'texts')
    if t:
        t['fw'] = 800 if t['fw'] != 800 else 600
        return t['id']


def m_color(d):
    t = first(d, 'texts')
    if t:
        c = t['c'].lstrip('#')
        t['c'] = '#' + c[:-2] + format((int(c[-2:], 16) + 1) % 256, '02X')
        return t['id']


def m_baseline(d):
    t = first(d, 'texts')
    if t:
        t['bl'] += 4
        t['t'] += 4
        return t['id']


def m_x(d):
    t = first(d, 'texts')
    if t:
        t['ll'] += 3
        t['l'] += 3
        return t['id']


def m_box_w(d):
    b = first(d, 'boxes', lambda e: e['w'] > 20)
    if b:
        b['w'] += 4
        return b['id']


def m_radius(d):
    b = first(d, 'boxes', lambda e: e['r']['tl'] > 0 and not e.get('circle'))
    if b:
        for k in ('tl', 'tr', 'bl', 'br'):
            b['r'][k] += 2
        return b['id']


def m_icon(d):
    i = first(d, 'icons')
    other = next((e['cp'] for e in d['icons'] if e['cp'] != (i or {}).get('cp')), None)
    if i and other is not None:
        i['cp'] = other
        return i['id']
    if i:
        i['cp'] += 1
        return i['id']


def m_icon_size(d):
    i = first(d, 'icons')
    if i:
        i['size'] += 4
        return i['id']


def m_shadow(d):
    b = first(d, 'boxes', lambda e: e.get('shadows'))
    if b:
        b['shadows'][0]['blur'] += 4
        return b['id']


def m_border(d):
    b = first(d, 'boxes', lambda e: e.get('border'))
    if b:
        b['border']['w'] += 1
        return b['id']


def m_ellipsis(d):
    t = first(d, 'texts', lambda e: e.get('ellipsis'))
    if t:
        t['ellipsis'] = False
        return t['id']


def m_lines(d):
    t = first(d, 'texts')
    if t:
        t['lines'] += 1
        return t['id']


def m_missing(d):
    t = first(d, 'texts')
    if t:
        d['texts'].remove(t)
        return t['id']


def m_extra(d):
    if d['texts']:
        e = copy.deepcopy(d['texts'][0])
        e['id'] = 'mutation/extra'
        d['texts'].append(e)
        return e['id']


def m_overflow(d):
    d['invariants']['overflows'].append('A RenderFlex overflowed by 12 pixels on the right.')
    return None


def m_tap(d):
    d['invariants']['taps'].append({'id': 'mutation/tap', 'label': 'small button', 'l': 10, 't': 10, 'w': 40, 'h': 40})
    return 'mutation/tap'


def step_hex(c):
    h = c.lstrip('#')
    return '#' + h[:-2] + format((int(h[-2:], 16) + 1) % 256, '02X')


def m_text(d):
    t = first(d, 'texts')
    if t:
        t['s'] += ' X'
        return t['id']


def m_line_height(d):
    t = first(d, 'texts', lambda e: e.get('lh'))
    if t:
        t['lh'] *= 1.5
        return t['id']


def m_pitch(d):
    # the layout rounded a line box: the rendered pitch moves while the style still says what the board says
    t = first(d, 'texts', lambda e: e.get('lh') and e.get('lines'))
    if t:
        t['h'] += t['lines'] * 1.0
        return t['id']


def m_tracking(d):
    t = first(d, 'texts', lambda e: e.get('s'))
    if t:
        t['ls'] = 0.25
        return t['id']


def m_align(d):
    t = first(d, 'texts', lambda e: e['lines'] > 1)
    if t:
        t['align'] = 'end' if t['align'] != 'end' else 'start'
        return t['id']


def m_icon_pos(d):
    i = first(d, 'icons')
    if i:
        i['cx'] += 3
        return i['id']


def m_icon_color(d):
    i = first(d, 'icons')
    if i:
        i['c'] = step_hex(i['c'])
        return i['id']


def m_icon_weight(d):
    i = first(d, 'icons')
    if i:
        i['ff'] = 'AppIcons999'
        return i['id']


def m_fill(d):
    b = first(d, 'boxes', lambda e: e.get('c'))
    if b:
        b['c'] = step_hex(b['c'])
        return b['id']


def m_overlap(d):
    ts = [t for t in d['texts'] if t.get('id') and not baselined(t['id'])]
    if len(ts) >= 2:
        ts[1]['l'], ts[1]['t'] = ts[0]['l'], ts[0]['t']
        return ts[1]['id']


def m_id_conflict(d):
    d['invariants'].setdefault('idConflicts', []).append('a and b draw the same render object; key the inner widget only')
    return 'conflict'


def m_coverage(d):
    cov = d['invariants']['coverage']['texts']
    cov['tagged'] -= 1
    return 'coverage'


MUTATIONS = [
    ('font-size +1', 'font-size', m_font), ('font-weight', 'weight', m_weight), ('colour, one blue step', 'color', m_color),
    ('baseline +4 px (spacing)', 'baseline', m_baseline), ('x +3 px', 'x', m_x), ('box width +4', 'box', m_box_w),
    ('corner radius +2', 'radius', m_radius), ('wrong icon', 'icon-glyph', m_icon), ('icon size +4', 'icon-size', m_icon_size),
    ('shadow blur +4', 'shadow', m_shadow), ('border width +1', 'border', m_border), ('ellipsis lost', 'ellipsis', m_ellipsis),
    ('line count +1', 'lines', m_lines), ('element missing in app', 'missing', m_missing),
    ('extra element in app', 'extra', m_extra), ('render overflow', 'overflow', m_overflow),
    ('tap target 40 px', 'tap-target', m_tap), ('text content changed', 'text', m_text), ('line height x1.5', 'line-height', m_line_height),
    ('rendered line pitch +1 px', 'line-height', m_pitch), ('letter spacing 0.25', 'tracking', m_tracking),
    ('paragraph alignment', 'align', m_align), ('icon moved 3 px', 'icon-pos', m_icon_pos), ('icon colour, one step', 'icon-color', m_icon_color),
    ('icon weight font', 'icon-weight', m_icon_weight), ('box fill, one step', 'fill', m_fill), ('two texts overlap', 'overlap', m_overlap),
    ('two ids on one render object', 'id-conflict', m_id_conflict), ('id coverage drops', 'coverage', m_coverage),
]
ID_LESS = {'overflow', 'overlap', 'id-conflict', 'coverage'}     # these are reported without an element id


def write_tmp_cfg(cfg_path, cfg, app_dir):
    """A config copy whose app_dir points at app_dir; written next to the original so relative paths keep working."""
    base = os.path.dirname(os.path.abspath(cfg_path))
    c = copy.deepcopy(cfg)
    c['app_dir'] = os.path.relpath(app_dir, base)
    c['report'] = {}
    path = os.path.join(base, '.mutation_cfg.json')
    json.dump(c, open(path, 'w', encoding='utf-8'), indent=1)
    return path


def check(cfg_path, cfg, app_dir):
    return parity.run(write_tmp_cfg(cfg_path, cfg, app_dir), write=False)


def new_of(rep, category, id_):
    return [i for i in rep['issues'] if i['status'] == 'new' and i['category'] == category and (id_ is None or i['id'] and i['id'].endswith(id_))]


def run_dump(cfg_path, selftest):
    base = os.path.dirname(os.path.abspath(cfg_path))
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    tmp = tempfile.mkdtemp(prefix='parity_mut_')
    results = []
    try:
        clean = os.path.join(tmp, 'clean')
        os.makedirs(clean)
        design = json.load(open(os.path.join(base, cfg['design']), encoding='utf-8'))['screens']
        if selftest:
            ai = json.load(open(os.path.join(base, cfg['app_icons']), encoding='utf-8'))['icons']
            di = json.load(open(os.path.join(base, cfg['design_icons']), encoding='utf-8'))['icons']
            name_to_cp = {}
            for k, v in di.items():
                a = ai.get(k) or next((x for x in ai.values() if (x.get('name') or x.get('lucide')) == v.get('name')), None)
                if a:
                    name_to_cp[k] = a['cp']
            for screen, scene in cfg['screens'].items():
                json.dump(synth(design[screen], name_to_cp, screen), open(os.path.join(clean, scene + '.json'), 'w', encoding='utf-8'))
        else:
            for scene in cfg['screens'].values():
                shutil.copy(os.path.join(base, cfg['app_dir'], scene + '.json'), clean)
        bl_path = os.path.join(base, cfg['baseline']) if cfg.get('baseline') else None
        _AVOID[:] = json.load(open(bl_path, encoding='utf-8')).get('entries', []) if bl_path and os.path.exists(bl_path) else []
        rep0 = check(cfg_path, cfg, clean)
        base_new = rep0['summary']['new']
        scenes = list(cfg['screens'].items())
        for name, category, fn in MUTATIONS:
            detected, changed_in, note = False, None, ''
            for screen, scene in scenes:
                _SCREEN[0] = screen
                work = os.path.join(tmp, 'work')
                shutil.rmtree(work, ignore_errors=True)
                shutil.copytree(clean, work)
                path = os.path.join(work, scene + '.json')
                dump = json.load(open(path, encoding='utf-8'))
                id_ = fn(dump)
                if id_ is None and category not in ID_LESS:
                    continue
                json.dump(dump, open(path, 'w', encoding='utf-8'))
                rep = check(cfg_path, cfg, work)
                hits = new_of(rep, category, id_) if category not in ID_LESS else [i for i in rep['issues'] if i['status'] == 'new' and i['category'] == category]
                changed_in, detected = (screen, id_), bool(hits)
                if not detected:
                    note = f'new categories: {rep["summary"]["new_by_category"]}'
                break
            else:
                note = 'no suitable element in any screen (skipped)'
            results.append({'mutation': name, 'category': category, 'where': changed_in, 'detected': detected,
                            'skipped': changed_in is None, 'note': note})
        rep_restored = check(cfg_path, cfg, clean)
        restored_ok = rep_restored['summary']['new'] == base_new
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        tmp_cfg = os.path.join(base, '.mutation_cfg.json')
        if os.path.exists(tmp_cfg):
            os.remove(tmp_cfg)
    return results, {'baseline_new': base_new, 'restored_new': rep_restored['summary']['new'], 'restored_ok': restored_ok}


# ── source mode ──────────────────────────────────────────────────────────────────
def run_source(cfg_path, mutations_path, render_cmd, base_dir):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    muts = json.load(open(mutations_path, encoding='utf-8'))['mutations']
    base = os.path.dirname(os.path.abspath(cfg_path))
    app_dir = os.path.join(base, cfg['app_dir'])
    cfg_tmp = write_tmp_cfg(cfg_path, cfg, app_dir)
    results = []

    def render():
        subprocess.run(render_cmd, shell=True, check=True, cwd=base_dir)

    try:
        render()
        base_new = parity.run(cfg_tmp, write=False)['summary']['new']
        for m in muts:
            path = os.path.join(base_dir, m['file'])
            orig = open(path, encoding='utf-8').read()
            if m['find'] not in orig:
                results.append({'mutation': m['name'], 'category': m['expect'], 'detected': False, 'skipped': True,
                                'note': f'`{m["find"]}` not found in {m["file"]}'})
                continue
            try:
                open(path, 'w', encoding='utf-8').write(orig.replace(m['find'], m['replace'], 1))
                render()
                rep = parity.run(cfg_tmp, write=False)
                hits = [i for i in rep['issues'] if i['status'] == 'new' and i['category'] == m['expect']
                        and (not m.get('id') or (i['id'] or '').endswith(m['id']))]
                results.append({'mutation': m['name'], 'category': m['expect'], 'where': m.get('id'), 'detected': bool(hits),
                                'skipped': False, 'note': '' if hits else f'new categories: {rep["summary"]["new_by_category"]}'})
            finally:
                open(path, 'w', encoding='utf-8').write(orig)
        render()
        restored = parity.run(cfg_tmp, write=False)['summary']['new']
    finally:
        if os.path.exists(cfg_tmp):
            os.remove(cfg_tmp)
    return results, {'baseline_new': base_new, 'restored_new': restored, 'restored_ok': restored == base_new}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=['selftest', 'dump', 'source'])
    ap.add_argument('--config', required=True)
    ap.add_argument('--mutations')
    ap.add_argument('--render-cmd')
    ap.add_argument('--project-dir', default='.')
    ap.add_argument('--out')
    a = ap.parse_args()
    if a.mode == 'source':
        if not (a.mutations and a.render_cmd):
            sys.exit('source mode needs --mutations and --render-cmd')
        results, restore = run_source(a.config, a.mutations, a.render_cmd, os.path.abspath(a.project_dir))
    else:
        results, restore = run_dump(a.config, a.mode == 'selftest')
    ran = [r for r in results if not r['skipped']]
    missed = [r for r in ran if not r['detected']]
    print(f'{"mutation":28s} {"expects":12s} result')
    for r in results:
        print(f'{r["mutation"]:28s} {r["category"]:12s} ' + ('SKIPPED ' + r['note'] if r['skipped'] else 'detected' if r['detected'] else 'MISSED ' + r['note']))
    print(f'restore: new differences {restore["baseline_new"]} -> mutated -> {restore["restored_new"]} after restore: '
          + ('clean' if restore['restored_ok'] else 'NOT CLEAN'))
    ok = not missed and restore['restored_ok'] and len(ran) >= 5
    print(f'{len(ran) - len(missed)}/{len(ran)} mutations detected;', 'PASS' if ok else 'FAIL')
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.config)), 'build', 'mutation_report.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({'mode': a.mode, 'results': results, 'restore': restore, 'pass': ok}, open(out, 'w', encoding='utf-8'), indent=1)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
