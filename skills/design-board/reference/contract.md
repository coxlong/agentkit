# The board's data contract

The board is not just a picture: `extract_layout.py` turns it into a numeric description. This document fixes the rules
that make that description unambiguous — ids, the token schema, the extracted JSON, and how text measurement is plugged
in. Any downstream consumer (an implementation, a checker, a document generator) reads this contract.

## 1. Screen ids and element ids

- **Screen id**: lowercase, dot-separated, e.g. `settings.list`, `chat.card.dark`. A name, not a number. Board numbers
  (A1, B7) are generated from the insertion order, shift when boards are inserted and are **for humans only**.
- **Element id**: `<screen>/<path>`, where `<path>` is `/`-separated, lowercase, characters limited to `a-z 0-9 - _`:
  `bar/title`, `row/1/box`, `row/1/title`, `cta/label`. Repeated items use an index (`row/3/...`) or a business key
  (`session/<id>/title`).
- Unique within a screen (`kit.G._tag` raises on duplicates). Variants such as dark or landscape are **another screen**; the
  `<path>` part stays the same.
- Who needs an id: **all text and all icons**; every **box** with a fill, stroke, radius or shadow; visible dividers. Pure
  decoration (backgrounds, the system bar) is marked `deco=True`.
- A multi-line paragraph is **one id**: `g.lines(..., id='card/text')` emits several `<text>` elements with the same
  `data-id` plus `data-line / data-lines`. Extraction folds them into one entry (`lines`, `y` (first-line baseline),
  `y_last`).
- A downstream consumer maps the element id to its own stable-key mechanism (for example an HTML `id`, a React key, or a
  test key) and usually drops the screen prefix, which the screen↔scene mapping supplies.

## 2. Tokens `tokens.json`

```
scales.type_sizes / weights / radii / icon_sizes / radius_free_below / snap
scales.icon_stroke_units: [{max, units}, ...]    # stroke width (24-grid units) by size
text_styles: {name: {size, weight, lh, mono?}}   # named text styles; line height in pixels (integers)
palettes.light / dark                            # at least the keys in kit.REQUIRED
shadows.<name>.light / dark: {dx, dy, blur, color, opacity}   # blur = 2σ; SVG stdDeviation = blur / 2
board                                            # the board's own chrome colours (not checked)
```

Every downstream consumer generates or reads its own form from the same file; nobody copies values by hand. `lh` is
integer: some rendering engines round line boxes to whole pixels, and a fractional line height can never be reproduced
exactly.

## 3. Extracted layout JSON (output of `extract_layout.py`)

```
{"schema": 1, "screens": {"<screen>": {
   "code": "A1", "title": "...", "origin": [x, y], "size": [390, 844],
   "texts": [{id, s, x, y, y_last, lines, fs, fw, fill, op, anchor, mono, lh, style, spans?, deco}],
   "icons": [{id, name, cx, cy, size, color, filled, stroke_units, deco}],
   "boxes": [{id, kind: rect|circle, x, y, w, h, rx, fill, fop, op, stroke, sw, shadow{dx,dy,blur,color,opacity}, deco}],
   "lines": [{id, x1, y1, x2, y2, stroke, sw, deco}]}}}
```
Coordinates are phone-local logical pixels (0,0 = top-left of the artboard). `y` is the **first-line baseline**. A box
rectangle is the **nominal rectangle** (stroke inside): the board draws bordered rectangles inset by `sw/2` and marks them
`data-inset`; extraction restores the nominal rectangle. Elements without a data-id are exported with `id: null`.

## 4. Icon contract

- `icons.json` maps "design key → library name"; `sync_icons.py` fetches the SVGs from the official release (pinned
  version). Design keys are semantic (`back`, `settings`), not library names — the keys survive a library change.
- The stroke rule exists in one place: `tokens.scales.icon_stroke_units`.

## 5. Shared sample data `sample_data.json`

The board generator and every downstream consumer **read the same file**. Every string, list item and number a screen
needs lives there; no literals on either side.

## 6. Text measurement (optional)

The default ruler is a built-in width estimate. If a closer measurement matters:

1. Build with `--measured build/measured_text.json --needed build/needed_text.json`: a missing file means "not measured
   yet" — the board draws an estimated version and writes **what needs measuring** into `needed_text.json` (four kinds:
   `width / wrap / baseline / ellipsis`, each with size, weight, mono flag, max width and line height).
2. Produce the answers with the **target rendering engine** (for web: a headless browser measuring the same strings),
   writing `measured_text.json` (keys = `size|weight|mono|…|string`, matching `kit.MeasuredRuler.key`).
3. Rebuild: the board now reads the answers — wrap points, ellipsis positions and line-box baselines are the engine's.
   Repeat until "0 strings still estimated" (usually two rounds).

## 7. Conventions at a glance

| Item | Convention |
|---|---|
| Coordinates | logical pixels; phone-local; y downwards |
| Text position | top of the line box (`at='top'`); baseline = top + measured in-box baseline |
| Stroke | box/circle strokes inside; icon strokes by size step |
| Shadow | `blur` = 2σ (CSS blur-radius convention); `dx dy` with the same sign; colour and opacity kept separate |
| Opacity | fill alpha = `fill-opacity × opacity`; colour hex contains RGB only |
| Ellipsis | ellipsised text ends with `…`; a consumer only has to reproduce the drawn prefix |
