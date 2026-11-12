"""Artboard framing: phones, captions, section headers, the board layout and the SVG document."""
import kit
from kit import esc, f, uid


def board_text(x, y, s, size=14, w=400, fill=None, anchor='start', mono=False, maxw=None):
    """Board chrome text (captions, section titles). It sits outside the artboards, so it is never compared."""
    b = kit.board
    fill = fill or b.ink
    if maxw:
        s = kit.chrome_ell(s, size, maxw, w, mono)
    a = f'<text x="{f(x)}" y="{f(y)}" font-size="{f(size)}" font-weight="{w}" fill="{fill}"'
    if anchor != 'start':
        a += f' text-anchor="{anchor}"'
    if mono:
        a += f' font-family="{kit.MONO}"'
    return a + f'>{esc(s)}</text>'


def phone(x, y, content, t, screen, code, title, w=390, h=844, radius=40, bg=None, status=None, nav=None):
    """One artboard at board position (x, y). Everything inside is in phone coordinates (0,0 = top-left of the screen).
    `status` / `nav` are optional callables drawing the system bars into a G (they are part of the artboard)."""
    cid = uid('clip')
    bars = kit.G(t, screen=screen)
    if status:
        status(bars)
    if nav:
        nav(bars)
    return (f'<g transform="translate({f(x)},{f(y)})" data-screen="{esc(screen)}" data-code="{esc(code)}" '
            f'data-title="{esc(title)}" data-w="{w}" data-h="{h}">'
            f'<rect width="{w}" height="{h}" rx="{radius}" fill="{bg or t.page}" filter="url(#shPhone)" data-deco="1"/>'
            f'<clipPath id="{cid}"><rect width="{w}" height="{h}" rx="{radius}"/></clipPath>'
            f'<g clip-path="url(#{cid})">{content}{bars}</g>'
            f'<rect x=".75" y=".75" width="{w - 1.5}" height="{h - 1.5}" rx="{radius - .75}" fill="none" '
            f'stroke="{t.phoneStroke}" stroke-width="1.5" data-deco="1"/></g>')


def caption(x, y, code, title, desc=None, w=390):
    """Under an artboard: code tag + title + up to 3 lines of description."""
    b = kit.board
    out = []
    tag_w = kit.chrome_width(code, 13, 800) + 18
    out.append(f'<rect x="{f(x)}" y="{f(y)}" width="{f(tag_w)}" height="24" rx="12" fill="{b.brand}"/>')
    out.append(board_text(x + tag_w / 2, y + 17, code, 13, 800, b.onBrand, 'middle'))
    out.append(board_text(x + tag_w + 10, y + 18, title, 16, 800, b.ink, maxw=w - tag_w - 10))
    if desc:
        lines = kit.chrome_wrap(desc, 13, 400, False, w)
        if len(lines) > 3:
            kit.WARNINGS.append(f'caption {code} "{title}" needs {len(lines)} lines, only 3 are drawn')
        for i, ln in enumerate(lines[:3]):
            out.append(board_text(x, y + 46 + i * 19, ln, 13, 400, b.muted))
    return ''.join(out)


def section_head(x, y, letter, title, sub, count=None, w=2640):
    b = kit.board
    out = [f'<rect x="{f(x)}" y="{f(y)}" width="46" height="46" rx="14" fill="{b.brand}"/>',
           board_text(x + 23, y + 31.5, letter, 24, 800, b.onBrand, 'middle'),
           board_text(x + 64, y + 21, title, 28, 800, b.ink),
           board_text(x + 64, y + 46, sub, 14, 400, b.muted, maxw=w - 200)]
    if count:
        out.append(board_text(x + w, y + 21, count, 14, 600, b.brandInk, 'end'))
    out.append(f'<line x1="{f(x)}" y1="{f(y + 70)}" x2="{f(x + w)}" y2="{f(y + 70)}" stroke="{b.line}" stroke-width="1.5"/>')
    return ''.join(out)


class Board:
    """Lays artboards out in sections (letters A, B ...). Codes (A1, A2, B1 ...) follow the order of add(), so inserting
    a screen renumbers the ones after it: never use a code as an identifier, use the screen id."""

    def __init__(self, cols=4, margin=80, gap_x=60, gap_y=40, caption_h=110):
        self.cols, self.margin, self.gap_x, self.gap_y, self.caption_h = cols, margin, gap_x, gap_y, caption_h
        self.width = margin * 2 + cols * 390 + (cols - 1) * gap_x
        self.parts, self.codes, self.titles = [], {}, {}
        self.y = margin
        self.col = 0
        self.letter, self.n, self.row_h = None, 0, 0
        self.counts = {}

    def section(self, letter, title, sub=''):
        self._end_row()
        self.parts.append(section_head(self.margin, self.y, letter, title, sub, w=self.width - 2 * self.margin))
        self.y += 100
        self.letter, self.n = letter, 0
        self.counts[letter] = 0

    def _end_row(self):
        if self.col:
            self.y += self.row_h + self.gap_y
            self.col, self.row_h = 0, 0

    def screen(self, screen, title, build, theme=None, desc=None, w=390, h=844, status=None, nav=None, bg=None):
        """Add an artboard. `build(g)` draws it into a G whose element ids are prefixed with `screen`."""
        t = theme or kit.light
        g = kit.G(t, screen=screen)
        build(g)
        self.n += 1
        self.counts[self.letter] += 1
        code = f'{self.letter}{self.n}'
        self.codes[screen], self.titles[screen] = code, title
        x = self.margin + self.col * (390 + self.gap_x)
        self.parts.append(phone(x, self.y, str(g), t, screen, code, title, w, h, bg=bg, status=status, nav=nav))
        self.parts.append(caption(x, self.y + h + 22, code, title, desc))
        self.row_h = max(self.row_h, h + self.caption_h)
        self.col += 1
        if self.col >= self.cols:
            self._end_row()

    def svg(self):
        self._end_row()
        height = self.y + self.margin
        body = '\n'.join(self.parts)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{height}" '
                f'viewBox="0 0 {self.width} {height}" font-family="{kit.FONT}">\n{kit.defs()}\n'
                f'<rect width="{self.width}" height="{height}" fill="{kit.board.bg}"/>\n{body}\n</svg>\n')
