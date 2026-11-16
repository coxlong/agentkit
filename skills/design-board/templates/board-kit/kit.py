"""Design board kit (Python standard library only).

What it gives a board generator:
  * tokens   - one tokens.json (palettes, type/weight/radius/icon scales, named text styles, shadows) read by `init()`.
               Every downstream consumer (an implementation, a checker) reads the same file, so they cannot drift.
  * scales   - every size, weight, radius and icon size goes through snap_*() so a call site cannot leave the scale.
  * ruler    - text width, line breaks and the baseline of a line box. Default: a built-in character-width estimate.
               Optionally, MeasuredRuler reads answers produced by a target rendering engine (e.g. a headless browser)
               from measured_text.json.
  * ids      - every text / icon / box can carry a stable id (data-id="<screen>/<path>"), so any later consumer can
               refer to an element unambiguously, never by content or position.
  * G        - the element accumulator for ONE artboard in phone coordinates (x right, y down, 0,0 = top-left).

    import kit
    K = kit.init('tokens.json', icons='icons.json', measured='build/measured_text.json')   # measured is optional
    g = kit.G(K.light, screen='settings.list')
    g.text(20, 60, 'Settings', 'title', id='bar/title')           # y = top of the line box
    g.rect(20, 100, 350, 56, 12, K.light.surface, K.light.line, id='row/1/box')
    g.ic('chevron-right', 346, 128, 16, K.light.muted, id='row/1/chev')
"""
import html
import json
import os
import sys
from types import SimpleNamespace as NS

HERE = os.path.dirname(os.path.abspath(__file__))

# ── state filled by init() ───────────────────────────────────────────────────────
TOKENS = None
light = dark = board = None
SIZES = WEIGHTS = RADII = ICON_SIZES = ()
STYLES = {}
SHADOWS = {}
ICONS = {}          # key -> inner svg markup (outline icons, drawn with stroke)
CUSTOM = {}         # key -> inner svg markup (filled shapes, drawn with fill)
ICON_NAMES = {}     # key -> name in the icon set (Lucide ...), for any downstream glyph map
FONT = MONO = ''
WARNINGS = []       # off-scale requests and other layout notes; the build script prints them
SRC = {}            # data-id -> "file.py:line" of the call that made it (written by write_id_index)
_SEEN = {}          # screen -> ids already used on it
_uid = [0]
_ruler = None

REQUIRED = ('page', 'surface', 'ink', 'ink2', 'muted', 'line', 'strong', 'brand', 'onBrand', 'phoneStroke', 'scrim', 'scrimOp')


def uid(prefix='c'):
    """Board-unique ids for clipPaths and the like. Deterministic: the same build order gives the same ids."""
    _uid[0] += 1
    return f'{prefix}{_uid[0]}'


def f(v):
    s = ('%.2f' % v).rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def esc(s):
    return html.escape(str(s), quote=False).replace('"', '&quot;')


# ── text ruler ───────────────────────────────────────────────────────────────────
_W = {}
for _c, _w in {
    'a': .556, 'b': .556, 'c': .5, 'd': .556, 'e': .556, 'f': .278, 'g': .556, 'h': .556, 'i': .222,
    'j': .222, 'k': .5, 'l': .222, 'm': .833, 'n': .556, 'o': .556, 'p': .556, 'q': .556, 'r': .333,
    's': .5, 't': .278, 'u': .556, 'v': .5, 'w': .722, 'x': .5, 'y': .5, 'z': .5,
    'A': .667, 'B': .667, 'C': .722, 'D': .722, 'E': .667, 'F': .611, 'G': .778, 'H': .722, 'I': .278,
    'J': .5, 'K': .667, 'L': .556, 'M': .833, 'N': .722, 'O': .778, 'P': .667, 'Q': .778, 'R': .722,
    'S': .667, 'T': .611, 'U': .722, 'V': .667, 'W': .944, 'X': .667, 'Y': .667, 'Z': .611,
    ' ': .278, '.': .278, ',': .278, ':': .278, ';': .278, '/': .278, '-': .333, '_': .556,
    '(': .333, ')': .333, '[': .278, ']': .278, '?': .556, '!': .278, '@': 1.0, '#': .556,
    '%': .889, '&': .667, '*': .389, '+': .584, '=': .584, '~': .584, '"': .355, "'": .191,
    '|': .26, '<': .584, '>': .584, '\\': .278, '$': .556, '^': .469, '`': .333, '{': .334, '}': .334,
}.items():
    _W[_c] = _w
for _d in '0123456789':
    _W[_d] = .556
NO_START = set('，。、；：！？）》」』”’…—,.;:!?)]}%')     # may not begin a line
NO_END = set('（《「『“‘([{')                            # may not end a line


def cw(ch, size, bold=False, mono=False):
    """Estimated advance of one character."""
    o = ord(ch)
    if o >= 0x2E80 and (o <= 0xA4CF or 0xAC00 <= o <= 0xD7AF or 0xFF00 <= o <= 0xFFEF):
        return size
    if 0x3000 <= o <= 0x303F or ch in '—…“”‘’':
        return size
    if mono:
        return .6 * size
    if ch in '·•›‹':
        return .55 * size
    w = _W.get(ch, .6) * size
    return w * (1.05 if bold else 1)


def _wrap_estimate(s, size, bold, mono, maxw):
    lines = []
    for para in str(s).split('\n'):
        cur, w, last_space = '', 0.0, -1
        for c in para:
            cwid = cw(c, size, bold, mono)
            if w + cwid > maxw and cur:
                brk = len(cur)
                if c in NO_START and len(cur) > 1:
                    brk = len(cur) - 1
                    while brk > 1 and cur[brk - 1].isascii() and cur[brk - 1] != ' ' and cur[brk].isascii() and cur[brk] != ' ':
                        brk -= 1
                elif c.isascii() and c != ' ' and cur[-1].isascii() and cur[-1] != ' ' and last_space > 0:
                    brk = last_space + 1
                if cur[brk - 1:brk] in NO_END and brk > 1:
                    brk -= 1
                lines.append(cur[:brk].rstrip())
                cur = cur[brk:].lstrip(' ')
                w = sum(cw(ch, size, bold, mono) for ch in cur)
                last_space = -1
                for i, ch in enumerate(cur):
                    if ch == ' ':
                        last_space = i
            cur += c
            w += cwid
            if c == ' ':
                last_space = len(cur) - 1
        lines.append(cur.rstrip())
    return lines


class EstimateRuler:
    """Built-in character-width estimate. Good for a first layout; leave slack for its error. For closer measurement,
    feed MeasuredRuler answers produced by the target rendering engine."""
    measured = False
    asc, desc = 1.0, 0.25          # per em; only used for the baseline estimate

    def _est_width(self, s, size, weight, mono):
        return sum(cw(c, size, weight >= 600, mono) for c in s)

    def width(self, s, size, weight=400, mono=False):
        return self._est_width(s, size, weight, mono)

    def wrap(self, s, size, weight, mono, maxw):
        return _wrap_estimate(s, size, weight >= 600, mono, maxw)

    def baseline(self, size, weight, lh, mono=False):
        """Distance from the top of a line box of height `lh` to the alphabetic baseline (even leading)."""
        return (lh - (self.asc + self.desc) * size) / 2 + self.asc * size

    def ellipsize(self, s, size, weight, mono, maxw):
        """`s` cut to the longest prefix that fits `maxw` together with an ellipsis."""
        if self._est_width(s, size, weight, mono) <= maxw:
            return s
        out = ''
        for c in s:
            if self._est_width(out + c + '…', size, weight, mono) > maxw:
                break
            out += c
        return out + '…'


class MeasuredRuler(EstimateRuler):
    """Answers measured by a target rendering engine (e.g. a headless browser). A miss falls back to the estimate and is
    recorded in `needed`, which write_needed_text() saves; produce the answers, rebuild, repeat until nothing is
    missing."""
    measured = True

    def __init__(self, path):
        data = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
        self.meta = data.get('meta', {})
        self.w = data.get('width', {})
        self.wr = data.get('wrap', {})
        self.bl = data.get('baseline', {})
        self.el = data.get('ellipsis', {})
        self.needed = {'width': {}, 'wrap': {}, 'baseline': {}, 'ellipsis': {}}

    @staticmethod
    def key(size, weight, mono, *rest):
        return '|'.join([f'{size:g}', str(weight), '1' if mono else '0', *[str(r) for r in rest]])

    def width(self, s, size, weight=400, mono=False):
        k = self.key(size, weight, mono, s)
        if k in self.w:
            return self.w[k]
        self.needed['width'][k] = {'s': s, 'size': size, 'weight': weight, 'mono': mono}
        return self._est_width(s, size, weight, mono)

    def wrap(self, s, size, weight, mono, maxw):
        k = self.key(size, weight, mono, f'{maxw:g}', s)
        if k in self.wr:
            return list(self.wr[k])
        self.needed['wrap'][k] = {'s': s, 'size': size, 'weight': weight, 'mono': mono, 'maxw': maxw}
        return super().wrap(s, size, weight, mono, maxw)

    def ellipsize(self, s, size, weight, mono, maxw):
        k = self.key(size, weight, mono, f'{maxw:g}', s)
        if k in self.el:
            return self.el[k]
        self.needed['ellipsis'][k] = {'s': s, 'size': size, 'weight': weight, 'mono': mono, 'maxw': maxw}
        return EstimateRuler.ellipsize(self, s, size, weight, mono, maxw)

    def baseline(self, size, weight, lh, mono=False):
        k = self.key(size, weight, mono, f'{lh:g}')
        if k in self.bl:
            return self.bl[k]
        self.needed['baseline'][k] = {'size': size, 'weight': weight, 'mono': mono, 'lh': lh}
        return super().baseline(size, weight, lh, mono)


def ruler():
    return _ruler


_chrome = EstimateRuler()          # board chrome (captions, section titles) is never compared: always estimated


def chrome_width(s, size, weight=400, mono=False):
    return _chrome.width(s, size, weight, mono)


def chrome_ell(s, size, maxw, weight=400, mono=False):
    return _chrome.ellipsize(s, size, weight, mono, maxw)


def chrome_wrap(s, size, weight, mono, maxw):
    return _chrome.wrap(s, size, weight, mono, maxw)


def tw(s, size, bold=False, mono=False):
    return _ruler.width(s, size, 600 if bold else 400, mono)


def write_needed_text(path):
    """Save the strings the ruler had to estimate (a MeasuredRuler only). Returns how many."""
    if not isinstance(_ruler, MeasuredRuler):
        return 0
    n = {k: list(v.values()) for k, v in _ruler.needed.items()}
    total = sum(len(v) for v in n.values())
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(n, fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    return total


def ell(s, size, maxw, weight=400, mono=False):
    """End ellipsis, cut where the ruler (measured or estimated) says the text no longer fits."""
    return _ruler.ellipsize(s, size, weight, mono, maxw)


def ell_mid(s, size, maxw, weight=400, mono=False, tail=6):
    """Middle ellipsis for file names: keeps the extension visible."""
    if _ruler.width(s, size, weight, mono) <= maxw:
        return s
    t = s[-tail:] if len(s) > tail + 1 else ''
    head = s[:len(s) - len(t)]
    out = ''
    for c in head:
        if _ruler.width(out + c + '…' + t, size, weight, mono) > maxw:
            break
        out += c
    return out + '…' + t


# ── scales ───────────────────────────────────────────────────────────────────────
def _nearest(v, scale):
    return min(scale, key=lambda c: (abs(c - v), c))


def snap_size(size):
    if size in SIZES:
        return size
    mapped = TOKENS['scales'].get('snap', {}).get('type_sizes', {}).get(f'{size:g}')
    out = mapped if mapped is not None else _nearest(size, SIZES)
    WARNINGS.append(f'type size {size:g} is not on the scale {list(SIZES)}; drew {out}')
    return out


def snap_weight(w):
    if w in WEIGHTS:
        return w
    mapped = TOKENS['scales'].get('snap', {}).get('weights', {}).get(str(w))
    out = mapped if mapped is not None else _nearest(w, WEIGHTS)
    WARNINGS.append(f'font weight {w} is not on the scale {list(WEIGHTS)}; drew {out}')
    return out


def snap_icon(size):
    if size in ICON_SIZES:
        return size
    big = max(ICON_SIZES)
    if size > big * 1.4:
        return size                      # hero glyphs (empty states) keep their size
    out = _nearest(size, ICON_SIZES)
    WARNINGS.append(f'icon size {size:g} is not on the scale {list(ICON_SIZES)}; drew {out}')
    return out


def icon_stroke(size):
    """Stroke width in 24-grid units for an icon drawn at `size` px (rule from tokens: scales.icon_stroke_units)."""
    for rule in TOKENS['scales']['icon_stroke_units']:
        if size <= rule['max']:
            return rule['units']
    return TOKENS['scales']['icon_stroke_units'][-1]['units']


def snap_radius(r, w, h):
    """Corner radii come from one scale; pills (radius >= half the short side) and tiny radii stay as they are."""
    free = TOKENS['scales'].get('radius_free_below', 0)
    if r < free or r >= min(w, h) / 2 - .5:
        return r
    if r in RADII:
        return r
    out = _nearest(r, RADII)
    WARNINGS.append(f'radius {r:g} is not on the scale {list(RADII)}; drew {out}')
    return out


def style_of(style, size=None, weight=None, lh=None, mono=None):
    """Resolve a text style name (tokens.text_styles) with optional overrides to (size, weight, lh, mono)."""
    if isinstance(style, str):
        if style not in STYLES:
            raise KeyError(f'unknown text style {style!r}; tokens.text_styles has {sorted(STYLES)}')
        s = STYLES[style]
    else:
        s = style
    size = snap_size(size if size is not None else s['size'])
    weight = snap_weight(weight if weight is not None else s['weight'])
    return size, weight, lh if lh is not None else s['lh'], bool(mono if mono is not None else s.get('mono', False))


# ── init ─────────────────────────────────────────────────────────────────────────
def init(tokens, icons=None, measured=None):
    """Load tokens (path or dict), the icon list (icons.json) and, optionally, text-measurement answers."""
    global TOKENS, light, dark, board, SIZES, WEIGHTS, RADII, ICON_SIZES, STYLES, SHADOWS, FONT, MONO, _ruler
    TOKENS = json.load(open(tokens, encoding='utf-8')) if isinstance(tokens, (str, os.PathLike)) else tokens
    sc = TOKENS['scales']
    SIZES, WEIGHTS = tuple(sc['type_sizes']), tuple(sc['weights'])
    RADII, ICON_SIZES = tuple(sc['radii']), tuple(sc['icon_sizes'])
    STYLES = TOKENS['text_styles']
    SHADOWS = TOKENS.get('shadows', {})
    for mode in ('light', 'dark'):
        missing = [k for k in REQUIRED if k not in TOKENS['palettes'][mode]]
        if missing:
            raise ValueError(f'palette {mode} lacks {missing}')
    light = NS(name='light', dark=False, **TOKENS['palettes']['light'])
    dark = NS(name='dark', dark=True, **TOKENS['palettes']['dark'])
    board = NS(**TOKENS['board'])
    sans = TOKENS.get('fonts', {}).get('sans', 'sans-serif')
    FONT = f"'{sans}','Noto Sans SC','Noto Sans CJK SC',system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif"
    MONO = "ui-monospace,'SF Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"
    ICONS.clear()
    CUSTOM.clear()
    ICON_NAMES.clear()
    if icons:
        data = json.load(open(icons, encoding='utf-8'))
        for k, v in data['icons'].items():
            (CUSTOM if v.get('custom') else ICONS)[k] = v['svg']
            ICON_NAMES[k] = v.get('name')
    _ruler = MeasuredRuler(measured) if measured else EstimateRuler()     # a missing file = nothing measured yet: record needs
    WARNINGS.clear()
    SRC.clear()
    _SEEN.clear()
    _uid[0] = 0
    return NS(light=light, dark=dark, board=board, ruler=_ruler)


def write_id_index(path):
    """id -> source line of the call that drew it (shown in reports next to every element)."""
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(SRC, fh, ensure_ascii=False, indent=0, sort_keys=True)
        fh.write('\n')


def _caller():
    fr = sys._getframe(2)
    while fr and os.path.abspath(fr.f_code.co_filename) == os.path.abspath(__file__):
        fr = fr.f_back
    return f'{os.path.basename(fr.f_code.co_filename)}:{fr.f_lineno}' if fr else '?'


def defs():
    """<defs> with the shadows of tokens.shadows (light as shX, dark as shXD) and the artboard shadow."""
    out = ['<defs>',
           '<filter id="shPhone" x="-20%" y="-10%" width="140%" height="130%" color-interpolation-filters="sRGB">'
           '<feDropShadow dx="0" dy="14" stdDeviation="20" flood-color="#0F172A" flood-opacity="0.14"/></filter>']
    for name, modes in SHADOWS.items():
        for mode, suffix in (('light', ''), ('dark', 'D')):
            s = modes[mode]
            out.append(f'<filter id="sh{name[:1].upper()}{name[1:]}{suffix}" x="-50%" y="-50%" width="200%" height="200%" '
                       f'color-interpolation-filters="sRGB"><feDropShadow dx="{f(s["dx"])}" dy="{f(s["dy"])}" '
                       f'stdDeviation="{f(s["blur"] / 2)}" flood-color="{s["color"]}" flood-opacity="{f(s["opacity"])}"/></filter>')
    out.append('</defs>')
    return '\n'.join(out)


# ── the accumulator ──────────────────────────────────────────────────────────────
class G:
    """Elements of one artboard in phone coordinates. `screen` is the artboard's stable id (e.g. 'settings.list').

    id=...  a stable id, unique per screen; it becomes data-id="<screen>/<id>", so any later consumer can refer to
            this element. deco=True marks intentional decoration (a wash, a hairline); everything else on the board
            should carry an id."""

    def __init__(self, t, screen=None):
        self.t = t
        self.screen = screen
        self.o = []

    def __str__(self):
        return ''.join(self.o)

    def raw(self, x):
        self.o.append(x)

    def _tag(self, id, deco=False):
        if id:
            full = f'{self.screen}/{id}' if self.screen else id
            seen = _SEEN.setdefault(self.screen, set())
            if full in seen:
                raise ValueError(f'duplicate id {full!r} on screen {self.screen!r}')
            seen.add(full)
            SRC[full] = _caller()
            return f' data-id="{esc(full)}"'
        return ' data-deco="1"' if deco else ''

    def _shadow(self, name):
        if not name:
            return ''
        if name not in SHADOWS:
            raise KeyError(f'unknown shadow {name!r}; tokens.shadows has {sorted(SHADOWS)}')
        return f' filter="url(#sh{name[:1].upper()}{name[1:]}{"D" if self.t.dark else ""})"'

    def rect(self, x, y, w, h, r=0, fill='none', stroke=None, sw=1, op=None, fop=None, shadow=None, dash=None,
             id=None, deco=False):
        """A box. The stroke is drawn INSIDE the given rectangle (like CSS borders): the svg rect is
        inset by sw/2 and marked data-inset, extract_layout.py gives back the nominal rectangle."""
        r = snap_radius(r, w, h)
        inset = ''
        if stroke and sw:
            x, y, w, h, r = x + sw / 2, y + sw / 2, w - sw, h - sw, max(r - sw / 2, 0)
            inset = ' data-inset="1"'
        a = f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}"'
        if r:
            a += f' rx="{f(r)}"'
        a += inset + f' fill="{fill}"'
        if fop is not None:
            a += f' fill-opacity="{fop}"'
        if stroke:
            a += f' stroke="{stroke}" stroke-width="{f(sw)}"'
        if dash:
            a += f' stroke-dasharray="{dash}"'
        if op is not None:
            a += f' opacity="{op}"'
        self.o.append(a + self._shadow(shadow) + self._tag(id, deco) + '/>')

    def circle(self, cx, cy, r, fill='none', stroke=None, sw=1, op=None, fop=None, id=None, deco=False):
        """A disc; like rect(), the stroke is drawn inside radius r."""
        inset = ''
        if stroke and sw:
            r = max(r - sw / 2, 0)
            inset = ' data-inset="1"'
        a = f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}"{inset} fill="{fill}"'
        if fop is not None:
            a += f' fill-opacity="{fop}"'
        if stroke:
            a += f' stroke="{stroke}" stroke-width="{f(sw)}"'
        if op is not None:
            a += f' opacity="{op}"'
        self.o.append(a + self._tag(id, deco) + '/>')

    def line(self, x1, y1, x2, y2, stroke=None, sw=1, op=None, dash=None, cap=None, id=None, deco=False):
        a = (f'<line x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" '
             f'stroke="{stroke or self.t.line}" stroke-width="{f(sw)}"')
        if dash:
            a += f' stroke-dasharray="{dash}"'
        if cap:
            a += f' stroke-linecap="{cap}"'
        if op is not None:
            a += f' opacity="{op}"'
        self.o.append(a + self._tag(id, deco) + '/>')

    def path(self, d, fill='none', stroke=None, sw=1, op=None, cap='round', join='round', id=None, deco=False):
        a = f'<path d="{d}" fill="{fill}"'
        if stroke:
            a += f' stroke="{stroke}" stroke-width="{f(sw)}" stroke-linecap="{cap}" stroke-linejoin="{join}"'
        if op is not None:
            a += f' opacity="{op}"'
        self.o.append(a + self._tag(id, deco) + '/>')

    def _text_el(self, x, base_y, txt, size, weight, fill, anchor, mono, op, ls, lh, style_name, tag, extra=''):
        a = (f'<text x="{f(x)}" y="{f(base_y)}" font-size="{f(size)}" font-weight="{weight}" fill="{fill}"'
             f' data-lh="{f(lh)}"')
        if style_name:
            a += f' data-style="{esc(style_name)}"'
        if anchor != 'start':
            a += f' text-anchor="{anchor}"'
        if mono:
            a += f' font-family="{MONO}"'
        if op is not None:
            a += f' opacity="{op}"'
        if ls:
            a += f' letter-spacing="{ls}"'
        return a + tag + extra + f'>{esc(txt)}</text>'

    def text(self, x, y, txt, style='body', fill=None, anchor='start', at='top', maxw=None, op=None, ls=None,
             size=None, weight=None, lh=None, mono=None, id=None, deco=False):
        """One line of text. `y` is the top of its line box (at='top'), its centre (at='center') or its baseline
        (at='base'); the baseline is derived from the ruler, so a consumer laying the same style out in a box of the
        same height lands on the same baseline."""
        size, weight, lh, mono = style_of(style, size, weight, lh, mono)
        fill = fill or self.t.ink
        if maxw is not None:
            txt = ell(txt, size, maxw, weight, mono)
        bl = _ruler.baseline(size, weight, lh, mono)
        top = y if at == 'top' else (y - lh / 2 if at == 'center' else y - bl)
        self.o.append(self._text_el(x, top + bl, txt, size, weight, fill, anchor, mono, op, ls, lh,
                                    style if isinstance(style, str) else None, self._tag(id, deco)))

    def rich(self, x, y, spans, style='body', anchor='start', at='top', op=None, id=None, deco=False):
        """One line made of coloured runs: spans = [(text, fill, weight_or_None), ...]."""
        size, weight, lh, mono = style_of(style)
        bl = _ruler.baseline(size, weight, lh, mono)
        top = y if at == 'top' else (y - lh / 2 if at == 'center' else y - bl)
        a = (f'<text x="{f(x)}" y="{f(top + bl)}" font-size="{f(size)}" font-weight="{weight}" fill="{spans[0][1]}" '
             f'data-lh="{f(lh)}"')
        if isinstance(style, str):
            a += f' data-style="{esc(style)}"'
        if anchor != 'start':
            a += f' text-anchor="{anchor}"'
        if mono:
            a += f' font-family="{MONO}"'
        if op is not None:
            a += f' opacity="{op}"'
        inner = ''.join(f'<tspan fill="{c}"' + (f' font-weight="{snap_weight(w)}"' if w else '') + f'>{esc(s)}</tspan>'
                        for s, c, w in spans)
        self.o.append(a + self._tag(id, deco) + '>' + inner + '</text>')

    def lines(self, x, y, txt, style='body', maxw=300, fill=None, anchor='start', at='top', maxlines=None, op=None,
              size=None, weight=None, lh=None, mono=None, id=None, deco=False):
        """A wrapped paragraph: one <text> per line, all with the same data-id (data-line / data-lines say which).
        Returns the number of lines drawn."""
        size, weight, lh, mono = style_of(style, size, weight, lh, mono)
        fill = fill or self.t.ink
        ls = _ruler.wrap(txt, size, weight, mono, maxw)
        if maxlines and len(ls) > maxlines:
            ls = ls[:maxlines]
            ls[-1] = ell(ls[-1] + '……', size, maxw, weight, mono)
        bl = _ruler.baseline(size, weight, lh, mono)
        top = y if at == 'top' else (y - lh / 2 if at == 'center' else y - bl)
        tag = self._tag(id, deco)
        for i, ln in enumerate(ls):
            extra = f' data-line="{i}" data-lines="{len(ls)}"' if id else ''
            self.o.append(self._text_el(x, top + i * lh + bl, ln, size, weight, fill, anchor, mono, op, None, lh,
                                        style if isinstance(style, str) else None, tag, extra))
        return len(ls)

    def ic(self, name, cx, cy, size=20, color=None, op=None, id=None, deco=False):
        """An icon centred on (cx, cy). Outline icons use the stroke rule of the tokens; `custom` icons are filled."""
        color = color or self.t.ink2
        size = snap_icon(size)
        s = size / 24
        pos = f'translate({f(cx - size / 2)},{f(cy - size / 2)}) scale({f(s)})'
        tag = f' data-icon="{esc(name)}" data-size="{f(size)}"' + self._tag(id, deco)
        extra = f' opacity="{op}"' if op is not None else ''
        if name in CUSTOM:
            self.o.append(f'<g transform="{pos}" fill="{color}"{extra}{tag}>{CUSTOM[name]}</g>')
            return
        if name not in ICONS:
            raise KeyError(f'unknown icon {name!r}; icons.json has {sorted(ICONS)}')
        self.o.append(f'<g transform="{pos}" fill="none" stroke="{color}" color="{color}" stroke-width="{f(icon_stroke(size))}" '
                      f'stroke-linecap="round" stroke-linejoin="round"{extra}{tag}>{ICONS[name]}</g>')

    def clip_begin(self, x, y, w, h, r=0):
        """Opens a group clipped to a (rounded) rect; close it with clip_end()."""
        cid = uid('cp')
        rr = f' rx="{f(r)}"' if r else ''
        self.o.append(f'<clipPath id="{cid}"><rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}"{rr}/></clipPath>')
        self.o.append(f'<g clip-path="url(#{cid})">')

    def clip_end(self):
        self.o.append('</g>')
