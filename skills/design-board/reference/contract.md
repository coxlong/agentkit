# Design board ↔ implementation: the contract

For a board to be checked element by element by a script, there has to be an **unambiguous contract** with the
implementation. This contract is the input of `design-parity-flutter`.

## 1. Screen ids and element ids

- **Screen id**: lowercase, dot-separated, e.g. `settings.list`, `chat.card.dark`. A name, not a number. Board numbers
  (A1, B7) are generated from the insertion order, shift when boards are inserted and are **for humans only**.
- **Element id**: `<screen>/<path>`, where `<path>` is `/`-separated, lowercase, characters limited to `a-z 0-9 - _`:
  `bar/title`, `row/1/box`, `row/1/title`, `cta/label`. Repeated items use an index (`row/3/...`) or a business key
  (`session/<id>/title`).
- Unique within a screen (`kit.G._tag` raises on duplicates). Variants such as dark or landscape are **another screen**; the
  `<path>` part stays the same.
- Who needs an id: **all text and all icons**; every **box** with a fill, stroke, radius or shadow; visible dividers. Pure
  decoration (backgrounds, the system bar) is marked `deco=True` — it is neither paired nor counted in coverage.
- A multi-line paragraph is **one id**: `g.lines(..., id='card/text')` emits several `<text>` elements with the same
  `data-id` plus `data-line / data-lines`. Extraction folds them into one entry (`lines`, `y` (first-line baseline),
  `y_last`).
- Implementation side: `key: ValueKey('row/1/title')` (without the screen id; the check's "design screen ↔ scene" mapping
  supplies it). Text, icon glyph and decorated box each take their own id: a key applies to the **first** measurable object
  inside it; two nested keys landing on the same render object are reported as `idConflicts`.

## 2. Tokens `tokens.json`

```
scales.type_sizes / weights / radii / icon_sizes / radius_free_below / snap
scales.icon_stroke_units: [{max, units}, ...]    # stroke weight (24-grid units) by size; font weight step = units * 200
text_styles: {name: {size, weight, lh, mono?}}   # named text styles; line height in pixels
palettes.light / dark                            # at least the keys in kit.REQUIRED
shadows.<name>.light / dark: {dx, dy, blur, color, opacity}   # blur = Flutter blurRadius; SVG stdDeviation = blur / 2
board                                            # the board's own chrome colours (not checked)
```
`gen_tokens_dart.py` turns it into Dart (palettes, text styles, shadows, `iconWeight(size)`). A text style's `height` is
`lh / size` with `leadingDistribution: even`, so putting that style's `Text` in a box `lh` tall fixes the baseline position.

## 3. Design-side layout JSON (output of `extract_layout.py`)

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
`data-inset`; extraction restores the nominal rectangle. A divider is usually a 1px box in the app; `parity.py` pairs the
design's `lines` with app boxes.

## 4. App-side dump JSON (one file per scene)

```
{"scene", "screen_size": [w, h],
 "texts": [{id, s, l,t,w,h, bl, ll, lw, lines, fs, fw, c, a, ff, lh(ratio), ls, align, maxLines, ellipsis}],
 "icons": [{id, cp, ff, size, cx, cy, c, a, spinner?}],
 "boxes": [{id, k, l,t,w,h, c, a, circle, pill, r{tl,tr,bl,br}, border{c,w}, shadows[{dx,dy,blur,spread,c,a}]}],
 "invariants": {overflows[], taps[{id,label,l,t,w,h}], coverage{texts,icons,boxes: {tagged,total}}, idConflicts[]}}
```
`bl` is the first-line baseline; `ll/lw` are the left edge and width of the first line (the anchor for centred or
right-aligned text is derived from them: centre = ll + lw/2). Other frameworks (RN/Web/native) can produce the same JSON;
`parity.py` does not care who wrote it.

## 5. Icon contract

- Design: `icons.json` maps "design key → library name"; SVGs are synced from the official release.
- Implementation: `app_icons.json` (output of the icon-font builder) maps "design key → {name, cp}". The `cp` in the app dump
  is looked up to a `name`, which must equal the design's `name` — this is the "the icon was not swapped" check. The font
  family (= weight step) must equal the step the stroke rule gives for that size.
- The stroke rule exists in one place: `tokens.scales.icon_stroke_units`.

## 6. Shared sample data `sample_data.json`

The board generator and the app's preview scenes **read the same file**. Every string, list item and number a screen needs
lives there; no literals on either side.

## 7. Text measurement protocol (let the board use the app's text engine)

1. `python3 build_board.py --measured build/measured_text.json --needed build/needed_text.json`: a missing file means
   "not measured yet" — the board draws an estimated version and writes **what needs measuring** into `needed_text.json`
   (four kinds: `width / wrap / baseline / ellipsis`, each with size, weight, mono flag, max width and line height).
2. The app-side `measure_text_test.dart` reads it and measures with `TextPainter` (the same font files as the app), writing
   `measured_text.json` (keys = `size|weight|mono|…|string`, matching `kit.MeasuredRuler.key`).
3. Rebuild: the board now reads the answers — wrap points, ellipsis positions and line-box baselines are the app's. Repeat
   until "0 strings still estimated" (usually two rounds).
4. Record the sha256 of the font files (`fonts.json`): measurement and rendering must use the same files.

## 8. Conventions at a glance

| Item | Convention |
|---|---|
| Coordinates | logical pixels; phone-local; y downwards |
| Text position | top of the line box (`at='top'`); baseline = top + measured in-box baseline |
| Stroke | box/circle strokes inside; icon strokes by size step |
| Shadow | `blur` (Flutter blurRadius) = 2σ; `dx dy` with the same sign; colour and opacity kept separate |
| Opacity | fill alpha = `fill-opacity × opacity`; colour hex contains RGB only |
| Ellipsis | the design's ellipsised text ends with `…`; the app's `ellipsis` is true; the content check only requires the app's full string to start with the design's prefix |
