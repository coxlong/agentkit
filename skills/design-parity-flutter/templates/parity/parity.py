#!/usr/bin/env python3
"""Design <-> implementation parity gate. Judges by numbers only; no step looks at a screenshot.

    python3 parity.py check --config parity.config.json [--previous build/parity_report.prev.json] [--fail-on-stale]
    python3 parity.py suggest-baseline --config parity.config.json     # new differences as baseline entries to review

Inputs
  design   build/design_layout.json   from the board's extract_layout.py (elements carry data-id = "<screen>/<path>")
  app      build/app/<scene>.json     from the Flutter render test (layout_dump.dart); ids are the widgets' ValueKey strings
Pairing is by id and kind (text / icon / box), one to one. A design id the app lacks is `missing`, an app id the design
lacks is `extra`; nothing is matched by text or by position.

Compared (tolerances in px; the defaults below may be tightened freely, loosened only with a reason in the config)
  text   content, font-size, weight, line-height, colour, align (multi-line), x (first-line anchor), baseline,
         line count, ellipsis
  icon   glyph (design icon -> icon-set name == the app glyph's name), size, weight font for the size, centre, colour
  box    x, y, w, h, fill, border colour and width, corner radius, shadow offset / blur / colour / opacity
  app    invariants: no RenderFlex overflow, tap targets >= tap_min, no overlapping tagged texts, id coverage
Spacing is not measured separately: it is what the position differences add up to.

Gate: a difference that is not in baseline.json fails the run (exit 1). Every baseline entry needs a reason and a date;
an entry whose difference is gone is reported as stale (fix: delete it, so the baseline only shrinks).
Exit codes: 0 pass, 1 new differences, 2 bad config / data / baseline. Standard library only.
"""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from collections import Counter, OrderedDict, defaultdict

DEFAULT_TOL = {'pos': 0.5, 'size': 0.05, 'lh': 0.1, 'icon_pos': 0.5, 'radius': 0.5, 'stroke': 0.1, 'shadow_px': 0.5,
               'shadow_opacity': 0.02, 'alpha': 0.01}
DEFAULT_REQUIRE = {'text_coverage': 1.0, 'icon_coverage': 1.0, 'box_coverage': 0.0, 'tap_min': 48}


# ── helpers ──────────────────────────────────────────────────────────────────────
def load(path, what):
    try:
        return json.load(open(path, encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise SystemExit(f'parity: cannot read {what} {path}: {e}') from None


def hexn(c):
    return (c or '').upper()


def anchor_name(a):
    return {'start': 'start', 'left': 'start', 'middle': 'middle', 'center': 'middle', 'end': 'end', 'right': 'end'}.get(a, a)


def weight_of_units(u):
    return int(round(u * 200))


def tolerances(cfg):
    tol = dict(DEFAULT_TOL)
    reasons = cfg.get('tolerance_reasons', {})
    for k, v in cfg.get('tolerance', {}).items():
        if k not in DEFAULT_TOL:
            raise SystemExit(f'parity: unknown tolerance {k!r}; known: {sorted(DEFAULT_TOL)}')
        if v > DEFAULT_TOL[k] and not reasons.get(k, '').strip():
            raise SystemExit(f'parity: tolerance.{k} = {v} is looser than the default {DEFAULT_TOL[k]}; '
                             f'give a reason in tolerance_reasons.{k}, or fix the difference instead')
        tol[k] = v
    return tol


class Issues:
    def __init__(self):
        self.items = []

    def add(self, screen, id_, kind, category, prop, design, app, tol=None, delta=None):
        if delta is None and isinstance(design, (int, float)) and isinstance(app, (int, float)):
            delta = round(app - design, 3)
        self.items.append({'screen': screen, 'id': id_, 'kind': kind, 'category': category, 'property': prop,
                           'design': design, 'app': app, 'delta': delta, 'tol': tol})


def num_diff(iss, screen, id_, kind, category, prop, d, a, tol):
    if d is None or a is None:
        return
    if abs(a - d) > tol + 1e-9:
        iss.add(screen, id_, kind, category, prop, round(d, 3), round(a, 3), tol)


def color_diff(iss, screen, id_, kind, category, prop, dc, dalpha, ac, aalpha, tol):
    if dc is None or ac is None or dc == 'none':
        return
    if hexn(dc) != hexn(ac):
        iss.add(screen, id_, kind, category, prop, hexn(dc), hexn(ac))
    elif abs((dalpha if dalpha is not None else 1) - (aalpha if aalpha is not None else 1)) > tol['alpha']:
        iss.add(screen, id_, kind, category, prop + '.alpha', round(dalpha, 3), round(aalpha, 3), tol['alpha'])


# ── element normalisation ────────────────────────────────────────────────────────
def design_boxes(s):
    out = []
    for b in s['boxes']:
        if b['deco']:
            continue
        out.append(dict(b))
    for ln in s['lines']:                         # a hairline pairs with a box: the app draws it as a 1 px Container
        if ln['deco']:
            continue
        sw = ln['sw']
        horiz = abs(ln['y1'] - ln['y2']) < 1e-6
        x, y = min(ln['x1'], ln['x2']), min(ln['y1'], ln['y2'])
        w, h = (abs(ln['x2'] - ln['x1']), sw) if horiz else (sw, abs(ln['y2'] - ln['y1']))
        out.append({'id': ln['id'], 'kind': 'line', 'x': x - (0 if horiz else sw / 2), 'y': y - (sw / 2 if horiz else 0),
                    'w': w, 'h': h, 'rx': 0, 'fill': ln['stroke'], 'fop': 1.0, 'op': 1.0, 'stroke': None, 'sw': 0,
                    'shadow': None, 'deco': False})
    return out


def app_radius(b):
    if b.get('circle'):
        return min(b['w'], b['h']) / 2
    if b.get('pill'):
        return min(b['w'], b['h']) / 2
    r = b.get('r')
    return r['tl'] if r else 0.0


def anchor_x(rec, anchor):
    """The x of the text's anchor point from an app record (first line)."""
    if anchor == 'middle':
        return rec['ll'] + rec['lw'] / 2
    if anchor == 'end':
        return rec['ll'] + rec['lw']
    return rec['ll']


# ── comparison ───────────────────────────────────────────────────────────────────
def compare_screen(screen, d, a, cfg, tol, iss, icon_tables):
    prefix = screen + '/'
    D = {'text': OrderedDict(), 'icon': OrderedDict(), 'box': OrderedDict()}
    untagged_design = Counter()
    for t in d['texts']:
        if t['deco']:
            continue
        (D['text'].__setitem__(t['id'], t) if t['id'] else untagged_design.update(['text']))
    for i in d['icons']:
        if i['deco']:
            continue
        (D['icon'].__setitem__(i['id'], i) if i['id'] else untagged_design.update(['icon']))
    for b in design_boxes(d):
        (D['box'].__setitem__(b['id'], b) if b['id'] else untagged_design.update(['box']))
    A = {'text': {}, 'icon': {}, 'box': {}}
    for kind, key in (('text', 'texts'), ('icon', 'icons'), ('box', 'boxes')):
        for e in a.get(key, []):
            if e.get('spinner'):
                continue
            if e.get('id'):
                A[kind][prefix + e['id']] = e
    for k in ('text', 'icon'):
        if untagged_design[k]:
            iss.add(screen, None, k, 'coverage', f'design {k}s without id', 0, untagged_design[k])

    for kind in ('text', 'icon', 'box'):
        for id_ in D[kind]:
            if id_ not in A[kind]:
                iss.add(screen, id_, kind, 'missing', 'present in app', 'yes', 'no')
        for id_ in A[kind]:
            if id_ not in D[kind]:
                iss.add(screen, id_, kind, 'extra', 'present in design', 'no', 'yes')

    for id_, dt in D['text'].items():
        at = A['text'].get(id_)
        if at:
            compare_text(screen, id_, dt, at, tol, iss)
    for id_, di in D['icon'].items():
        ai = A['icon'].get(id_)
        if ai:
            compare_icon(screen, id_, di, ai, cfg, tol, iss, icon_tables)
    for id_, db in D['box'].items():
        ab = A['box'].get(id_)
        if ab:
            compare_box(screen, id_, db, ab, tol, iss)

    inv = a.get('invariants', {})
    for msg in inv.get('overflows', []):
        iss.add(screen, None, 'app', 'overflow', 'render overflow', 'none', msg[:140])
    for msg in inv.get('idConflicts', []):
        iss.add(screen, None, 'app', 'id-conflict', 'two ids on one render object', 'none', msg[:140])
    tap_min = cfg['require']['tap_min']
    for tp in inv.get('taps', []):
        if min(tp['w'], tp['h']) < tap_min - 1e-6:
            iss.add(screen, tp.get('id') or tp.get('label'), 'app', 'tap-target', 'tap target min side', tap_min,
                    round(min(tp['w'], tp['h']), 2))
    tagged = [(prefix + t['id'], t) for t in a.get('texts', []) if t.get('id')]
    for i, (ida, ta) in enumerate(tagged):
        for idb, tb in tagged[i + 1:]:
            ox = min(ta['l'] + ta['w'], tb['l'] + tb['w']) - max(ta['l'], tb['l'])
            oy = min(ta['t'] + ta['h'], tb['t'] + tb['h']) - max(ta['t'], tb['t'])
            if ox > 2 and oy > 2:
                iss.add(screen, ida, 'text', 'overlap', 'overlaps ' + idb, 'no', 'yes')
    cov = inv.get('coverage', {})
    for key, need in (('texts', cfg['require']['text_coverage']), ('icons', cfg['require']['icon_coverage']),
                      ('boxes', cfg['require']['box_coverage'])):
        c = cov.get(key)
        if c and c['total'] and c['tagged'] / c['total'] < need - 1e-9:
            iss.add(screen, None, 'app', 'coverage', f'app {key} with id', f'>= {need:.0%}',
                    f'{c["tagged"]}/{c["total"]}')


def compare_text(screen, id_, d, a, tol, iss):
    k = 'text'
    ds = re.sub(r'\s+', ' ', d['s']).strip()
    as_ = re.sub(r'\s+', ' ', a['s']).strip()
    truncated = ds.endswith('…') and not as_.endswith('…')
    if truncated:
        if not as_.startswith(ds[:-1].rstrip()):
            iss.add(screen, id_, k, 'text', 'content', ds, as_)
    elif ds != as_:
        iss.add(screen, id_, k, 'text', 'content', ds, as_)
    num_diff(iss, screen, id_, k, 'font-size', 'font-size', d['fs'], a['fs'], tol['size'])
    if d['fw'] != a['fw']:
        iss.add(screen, id_, k, 'weight', 'font-weight', d['fw'], a['fw'])
    if d.get('lh') and a.get('lh') and a['fs']:
        num_diff(iss, screen, id_, k, 'line-height', 'line-height px', d['lh'], a['lh'] * a['fs'], tol['lh'])
    color_diff(iss, screen, id_, k, 'color', 'color', d['fill'], d['op'], a['c'], a.get('a'), tol)
    if d['lines'] > 1 or a['lines'] > 1:
        da, aa = anchor_name(d['anchor']), anchor_name(a.get('align', 'start'))
        if da != aa:
            iss.add(screen, id_, k, 'align', 'text-align', da, aa)
    num_diff(iss, screen, id_, k, 'x', 'first-line x (' + d['anchor'] + ')', d['x'], anchor_x(a, anchor_name(d['anchor'])), tol['pos'])
    num_diff(iss, screen, id_, k, 'baseline', 'first baseline y', d['y'], a['bl'], tol['pos'])
    if d['lines'] != a['lines']:
        iss.add(screen, id_, k, 'lines', 'line count', d['lines'], a['lines'])
    d_ell, a_ell = ds.endswith('…') or ds.endswith('……'), bool(a.get('ellipsis'))
    if d_ell != a_ell:
        iss.add(screen, id_, k, 'ellipsis', 'ellipsis', d_ell, a_ell)


def compare_icon(screen, id_, d, a, cfg, tol, iss, tables):
    k = 'icon'
    want = tables['design'].get(d['name'])
    got = tables['app'].get(a.get('cp'))
    if want is not None and want != got:
        iss.add(screen, id_, k, 'icon-glyph', 'glyph', f'{d["name"]} ({want})', got or f'U+{a.get("cp", 0):04X}')
    num_diff(iss, screen, id_, k, 'icon-size', 'size', d['size'], a['size'], tol['size'])
    units = d.get('stroke_units')
    fam = a.get('ff')
    if units and fam and cfg.get('weight_family'):
        expect = cfg['weight_family'].format(weight=weight_of_units(units))
        if fam != expect:
            iss.add(screen, id_, k, 'icon-weight', 'font family', expect, fam)
    num_diff(iss, screen, id_, k, 'icon-pos', 'centre x', d['cx'], a['cx'], tol['icon_pos'])
    num_diff(iss, screen, id_, k, 'icon-pos', 'centre y', d['cy'], a['cy'], tol['icon_pos'])
    color_diff(iss, screen, id_, k, 'icon-color', 'color', d['color'], 1.0, a['c'], a.get('a'), tol)


def compare_box(screen, id_, d, a, tol, iss):
    k = 'box'
    for prop, dv, av in (('x', d['x'], a['l']), ('y', d['y'], a['t']), ('w', d['w'], a['w']), ('h', d['h'], a['h'])):
        num_diff(iss, screen, id_, k, 'box', 'box.' + prop, dv, av, tol['pos'])
    if d['fill'] and d['fill'] != 'none':
        color_diff(iss, screen, id_, k, 'fill', 'fill', d['fill'], d['fop'] * d['op'], a.get('c'), a.get('a'), tol)
    elif a.get('c') and (a.get('a') or 0) > 0:
        iss.add(screen, id_, k, 'fill', 'fill', 'none', hexn(a['c']))
    border = a.get('border')
    if d['stroke']:
        if not border:
            iss.add(screen, id_, k, 'border', 'border', f'{hexn(d["stroke"])} {d["sw"]:g}px', 'none')
        else:
            if hexn(d['stroke']) != hexn(border['c']):
                iss.add(screen, id_, k, 'border', 'border colour', hexn(d['stroke']), hexn(border['c']))
            num_diff(iss, screen, id_, k, 'border', 'border width', d['sw'], border['w'], tol['stroke'])
    elif border and border['w'] > 0:
        iss.add(screen, id_, k, 'border', 'border', 'none', f'{hexn(border["c"])} {border["w"]:g}px')
    dr = min(d['rx'], min(d['w'], d['h']) / 2)
    ar = min(app_radius(a), min(a['w'], a['h']) / 2)
    num_diff(iss, screen, id_, k, 'radius', 'radius', dr, ar, tol['radius'])
    ds, ashs = d.get('shadow'), a.get('shadows') or []
    if ds and not ashs:
        iss.add(screen, id_, k, 'shadow', 'shadow', f'dy {ds["dy"]:g} blur {ds["blur"]:g}', 'none')
    elif ashs and not ds:
        iss.add(screen, id_, k, 'shadow', 'shadow', 'none', f'dy {ashs[0]["dy"]:g} blur {ashs[0]["blur"]:g}')
    elif ds and ashs:
        s = ashs[0]
        num_diff(iss, screen, id_, k, 'shadow', 'shadow.dx', ds['dx'], s['dx'], tol['shadow_px'])
        num_diff(iss, screen, id_, k, 'shadow', 'shadow.dy', ds['dy'], s['dy'], tol['shadow_px'])
        num_diff(iss, screen, id_, k, 'shadow', 'shadow.blur', ds['blur'], s['blur'], tol['shadow_px'])
        if hexn(ds['color']) != hexn(s['c']):
            iss.add(screen, id_, k, 'shadow', 'shadow.color', hexn(ds['color']), hexn(s['c']))
        num_diff(iss, screen, id_, k, 'shadow', 'shadow.opacity', ds['opacity'], s['a'], tol['shadow_opacity'])


# ── baseline ─────────────────────────────────────────────────────────────────────
def load_baseline(path):
    if not path or not os.path.exists(path):
        return []
    data = load(path, 'baseline')
    entries = data.get('entries', [])
    bad = [e for e in entries if not (e.get('reason') or '').strip() or (e.get('reason') or '').strip().upper().startswith('TODO')
           or not e.get('date') or not e.get('screen') or not e.get('property')]
    if bad:
        raise SystemExit('parity: baseline entries need screen, property, a real reason and a date: '
                         + '; '.join(f'{e.get("screen")}/{e.get("id")}/{e.get("property")}' for e in bad[:5]))
    return entries


def baseline_hit(entry, issue):
    if not fnmatch.fnmatch(issue['screen'], entry['screen']):
        return False
    if entry.get('id') is not None and not fnmatch.fnmatch(issue['id'] or '', entry['id']):
        return False
    if not fnmatch.fnmatch(issue['property'], entry['property']) and not fnmatch.fnmatch(issue['category'], entry['property']):
        return False
    if 'max_delta' in entry:
        return isinstance(issue['delta'], (int, float)) and abs(issue['delta']) <= entry['max_delta'] + 1e-9
    if 'expect_app' in entry:
        return str(issue['app']) == str(entry['expect_app'])
    return True


# ── source locations ─────────────────────────────────────────────────────────────
def locator(cfg, base):
    idx = {}
    p = cfg.get('design_id_index')
    if p and os.path.exists(os.path.join(base, p)):
        idx = json.load(open(os.path.join(base, p), encoding='utf-8'))
    roots = [os.path.join(base, r) for r in cfg.get('source_roots', [])]
    cache = {}

    def grep(needle):
        if needle in cache:
            return cache[needle]
        hit = None
        for root in roots:
            try:
                out = subprocess.run(['grep', '-rnF', '--include=*.dart', '--include=*.kt', '--include=*.swift', '--include=*.tsx',
                                      '--include=*.ts', '--include=*.js', needle, root], capture_output=True, text=True).stdout
            except OSError:
                out = ''
            if out:
                f, line = out.split('\n')[0].split(':')[:2]
                hit = f'{os.path.relpath(f, base)}:{line}'
                break
        cache[needle] = hit
        return hit

    def where(issue):
        id_ = issue['id']
        if not id_:
            return None
        parts = []
        if id_ in idx:
            parts.append('design ' + idx[id_])
        raw = id_.split('/', 1)[1] if '/' in id_ else id_
        segs = raw.split('/')
        for n in range(len(segs), 0, -1):
            hit = grep('/'.join(segs[:n]))
            if hit:
                parts.append('app ' + hit + ('' if n == len(segs) else ' (prefix)'))
                break
        return '; '.join(parts) or None
    return where


# ── report ───────────────────────────────────────────────────────────────────────
def summarize(items):
    by_cat = Counter(i['category'] for i in items)
    by_screen = defaultdict(Counter)
    for i in items:
        by_screen[i['screen']][i['category']] += 1
    return by_cat, by_screen


def markdown(rep):
    s = rep['summary']
    L = [f'# Parity report: {"PASS" if rep["pass"] else "FAIL"}', ''] + [f'- **fails because:** {r}' for r in rep.get('fail_reasons', [])] + ['',
         f'- screens compared: {s["screens"]}; paired elements: text {s["paired"]["text"]}, icon {s["paired"]["icon"]}, box {s["paired"]["box"]}',
         f'- differences: {s["total"]} ({s["new"]} new, {s["baselined"]} baselined); stale baseline entries: {len(rep["stale"])}',
         f'- fonts used by the render (sha256): ' + (', '.join(f'{f["family"]} {f["sha256"][:12]}' for f in rep.get('fonts', [])) or 'not recorded'),
         '']
    if rep.get('previous'):
        L += ['## Before / after', '', '| category | before | after | change |', '|---|---:|---:|---:|']
        cats = sorted(set(rep['previous']['by_category']) | set(s['by_category']))
        for c in cats:
            b, a = rep['previous']['by_category'].get(c, 0), s['by_category'].get(c, 0)
            L.append(f'| {c} | {b} | {a} | {a - b:+d} |')
        L += [f'| **total** | {rep["previous"]["total"]} | {s["total"]} | {s["total"] - rep["previous"]["total"]:+d} |', '']
    cats = sorted(s['by_category'])
    if cats:
      L += ['## By screen and category (all differences)', '', '| screen | ' + ' | '.join(cats) + ' |', '|---|' + '---:|' * len(cats)]
      for scr, cnt in sorted(rep['by_screen'].items()):
        L.append(f'| {scr} | ' + ' | '.join(str(cnt.get(c, '')) if cnt.get(c) else '' for c in cats) + ' |')
    L.append('')
    new = [i for i in rep['issues'] if i['status'] == 'new']
    L += [f'## New differences ({len(new)})', '']
    if new:
        L += ['| screen | id | category | property | design | app | delta | tol | where |', '|---|---|---|---|---|---|---:|---:|---|']
        for i in new[:300]:
            L.append(f'| {i["screen"]} | {i["id"] or ""} | {i["category"]} | {i["property"]} | {i["design"]} | {i["app"]} | '
                     f'{i["delta"] if i["delta"] is not None else ""} | {i["tol"] if i["tol"] is not None else ""} | {i.get("where") or ""} |')
        if len(new) > 300:
            L.append(f'... and {len(new) - 300} more in the JSON report')
    else:
        L.append('none')
    if rep['stale']:
        L += ['', '## Stale baseline entries (the difference is gone: delete them)', '']
        L += [f'- {e["screen"]} / {e.get("id")} / {e["property"]}: {e["reason"]} ({e["date"]})' for e in rep['stale']]
    if rep['tighten']:
        L += ['', '## Baseline entries that can be tightened (the difference shrank)', '']
        L += [f'- {t["entry"]["screen"]} / {t["entry"].get("id")} / {t["entry"]["property"]}: max_delta {t["entry"]["max_delta"]} -> {t["now"]}' for t in rep['tighten']]
    return '\n'.join(L) + '\n'


# ── main ─────────────────────────────────────────────────────────────────────────
def run(cfg_path, previous=None, fail_on_stale=False, write=True):
    base = os.path.dirname(os.path.abspath(cfg_path))
    cfg = load(cfg_path, 'config')
    cfg.setdefault('require', {})
    cfg['require'] = {**DEFAULT_REQUIRE, **cfg['require']}
    tol = tolerances(cfg)
    P = lambda p: os.path.join(base, p)  # noqa: E731
    design = load(P(cfg['design']), 'design layout')['screens']
    tables = {'design': {}, 'app': {}}
    if cfg.get('design_icons') and cfg.get('app_icons'):
        di = load(P(cfg['design_icons']), 'design icons')['icons']
        ai = load(P(cfg['app_icons']), 'app icons')['icons']
        tables['design'] = {k: (v.get('name') or k) if not v.get('custom') else k for k, v in di.items()}
        tables['app'] = {v['cp']: (v.get('name') or v.get('lucide') or k) for k, v in ai.items()}
        for k, v in ai.items():
            if v.get('name') is None and v.get('lucide') is None:
                tables['app'][v['cp']] = k
    iss = Issues()
    paired = Counter()
    errors = []
    for screen, scene in cfg['screens'].items():
        if screen not in design:
            errors.append(f'design has no screen {screen!r}')
            continue
        dump = P(os.path.join(cfg['app_dir'], scene + '.json'))
        if not os.path.exists(dump):
            errors.append(f'no app dump for scene {scene!r} ({dump})')
            continue
        app = json.load(open(dump, encoding='utf-8'))
        compare_screen(screen, design[screen], app, cfg, tol, iss, tables)
        pre = screen + '/'
        ids = {k: {e.get('id') for e in app.get(key, []) if e.get('id')} for k, key in (('text', 'texts'), ('icon', 'icons'), ('box', 'boxes'))}
        dids = {'text': {t['id'] for t in design[screen]['texts'] if t['id'] and not t['deco']},
                'icon': {i['id'] for i in design[screen]['icons'] if i['id'] and not i['deco']},
                'box': {b['id'] for b in design_boxes(design[screen]) if b['id']}}
        for k in paired.keys() | {'text', 'icon', 'box'}:
            paired[k] += len({pre + x for x in ids[k]} & dids[k])
    if errors:
        raise SystemExit('parity: ' + '; '.join(errors))

    if cfg.get('pixels'):
        from pixel_diff import pixel_issues   # optional second opinion, see pixel_diff.py
        pixel_issues(cfg, base, design, iss)

    baseline = load_baseline(P(cfg['baseline']) if cfg.get('baseline') else None)
    where = locator({**cfg}, base)
    hit_entries = set()
    for i in iss.items:
        i['status'] = 'new'
        for n, e in enumerate(baseline):
            if baseline_hit(e, i):
                i['status'] = 'baselined'
                i['baseline'] = n
                hit_entries.add(n)
                break
        i['where'] = where(i)
    stale = [e for n, e in enumerate(baseline) if n not in hit_entries]
    tighten = []
    for n in hit_entries:
        e = baseline[n]
        if 'max_delta' in e:
            now = max(abs(i['delta']) for i in iss.items if i.get('baseline') == n and i['delta'] is not None)
            if now < e['max_delta'] - 1e-9:
                tighten.append({'entry': e, 'now': round(now, 3)})
    by_cat, by_screen = summarize(iss.items)
    new = [i for i in iss.items if i['status'] == 'new']
    new_cat, _ = summarize(new)
    fonts = []
    fp = P(os.path.join(cfg['app_dir'], 'fonts.json'))
    if os.path.exists(fp):
        fonts = json.load(open(fp, encoding='utf-8'))
    reasons = []
    if new:
        reasons.append(f'{len(new)} new differences (not in the baseline)')
    if fail_on_stale and stale:
        reasons.append(f'{len(stale)} stale baseline entries (--fail-on-stale)')
    rep = {'schema': 1, 'pass': not reasons, 'fail_reasons': reasons, 'config': os.path.relpath(cfg_path),
           'tolerance': tol, 'fonts': fonts,
           'summary': {'screens': len(cfg['screens']), 'paired': dict(paired), 'total': len(iss.items), 'new': len(new),
                       'baselined': len(iss.items) - len(new), 'by_category': dict(by_cat), 'new_by_category': dict(new_cat)},
           'by_screen': {k: dict(v) for k, v in by_screen.items()}, 'issues': iss.items, 'stale': stale, 'tighten': tighten}
    if previous and os.path.exists(previous):
        old = json.load(open(previous, encoding='utf-8'))
        rep['previous'] = {'total': old['summary']['total'], 'by_category': old['summary']['by_category']}
    if write and cfg.get('report'):
        for key, render in (('json', lambda r: json.dumps(r, ensure_ascii=False, indent=1)), ('md', markdown)):
            if cfg['report'].get(key):
                path = P(cfg['report'][key])
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, 'w', encoding='utf-8').write(render(rep) + ('\n' if key == 'json' else ''))
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['check', 'suggest-baseline'])
    ap.add_argument('--config', required=True)
    ap.add_argument('--previous')
    ap.add_argument('--fail-on-stale', action='store_true')
    a = ap.parse_args()
    try:
        rep = run(a.config, a.previous, a.fail_on_stale)
    except SystemExit as e:
        print(e)
        sys.exit(2)
    s = rep['summary']
    if a.command == 'suggest-baseline':
        today = __import__('datetime').date.today().isoformat()
        sug = [{'screen': i['screen'], 'id': i['id'], 'property': i['property'], 'max_delta': abs(i['delta']) if isinstance(i['delta'], (int, float)) else None,
                'reason': 'TODO: why this difference is acceptable', 'date': today}
               for i in rep['issues'] if i['status'] == 'new']
        for e in sug:
            if e['max_delta'] is None:
                del e['max_delta']
        out = os.path.join(os.path.dirname(os.path.abspath(a.config)), 'baseline.suggested.json')
        json.dump({'schema': 1, 'entries': sug}, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'{len(sug)} entries -> {out} (fill in the reasons, then merge into the baseline: TODO reasons are rejected)')
        return
    print(f'screens {s["screens"]}  paired text/icon/box {s["paired"].get("text", 0)}/{s["paired"].get("icon", 0)}/{s["paired"].get("box", 0)}'
          f'  differences {s["total"]} (new {s["new"]}, baselined {s["baselined"]})  stale baseline {len(rep["stale"])}')
    if s['new_by_category']:
        print('new by category:', ', '.join(f'{k} {v}' for k, v in sorted(s['new_by_category'].items(), key=lambda kv: -kv[1])))
    for e in rep['stale']:
        print('stale baseline entry:', e['screen'], e.get('id'), e['property'])
    print('PARITY', 'PASS' if rep['pass'] else 'FAIL')
    sys.exit(0 if rep['pass'] else 1)


if __name__ == '__main__':
    main()
