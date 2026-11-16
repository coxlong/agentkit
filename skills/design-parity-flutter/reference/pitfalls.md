# Mistakes already made (implementation and check side)

| Mistake | Symptom | Do this instead |
|---|---|---|
| `loadFonts` inside a `testWidgets` body | The test hangs (`Process.run` never returns in the fake-async zone) | Put it in `setUpAll` |
| Fonts not loaded in tests | Text renders as boxes (Ahem) and every width is wrong | Register with `FontLoader` under the theme's family names, CJK included |
| The board uses estimated metrics | Every baseline ~1px off and wrap points differ; so someone shortens the sample text to dodge it | App measurement → board reads it (two rounds); do not change the sample data |
| Design and app each write their own sample data | Counts, order and lengths silently differ, producing a pile of "content" differences | One shared `sample_data.json` |
| Pairing by text content + position (the old way) | A wrong pairing stays silent; renaming a string breaks everything | Stable ids; missing and extra are both reported |
| Centred vs inside stroke | Bordered boxes 1px too big or too small | The board insets strokes (the kit does it); Flutter's `Border` is inside anyway |
| Confusing shadow σ with blurRadius | The shadow is twice as blurry as designed | Design `blur` = Flutter `blurRadius` = 2σ |
| "The icon frames match, so it matches" | The visible glyph is 10–20% different; error/cancel glyphs mean different things | One icon library; check glyph identity and weight step |
| Glyphs were centred inside the icon font | Some glyphs sit half a grid cell off | The builder's `place_like_svg` moves glyphs back onto the SVG 24-grid (already done) |
| Declaring every weight font but using one | Unused fonts ship whole | Declare only the weights in use |
| Constructing `IconData(cp, ...)` at runtime | Release cannot tree-shake the icon font; the build fails | Always use the generated `static const`s |
| `IconButton`'s default 48px padding | The icon is a few px off | `SizedBox(48×48)` + `Center(icon)` |
| `Container(alignment:)` | The box expands and its height is wrong | Do not use it; or give an explicit height |
| A `Column` overflows by 3px | One scene fails entirely (throws by default) | The harness collects `overflowed` messages into the dump; fix the layout |
| Two nested keys land on one render object | `idConflicts` | Put the key on the inner widget only |
| A dynamic id cannot be found in code | `where` is empty | Keep a static prefix in the id literal (the `row/` in `'row/${i + 1}/title'` is greppable) |
| Rendering the board in Chromium for pixel comparison: text several px wide | Blamed on the implementation | Same font files + `--font-render-hinting=none` (`render.sh FONTS=...`) |
| `pumpAndSettle` | Times out as soon as there is a spinner | `pump()` + `pump(Duration)` |
| Mutations only change the comparator's input | Proves the comparator, not the dumper | Use the `source` mode as well (patch the source, re-render) |
| Treating this check as "verified on a real device" | Device fonts, rendering and feel differ | Write "not verified: real device …" in every report |
| Tap collection returns an empty list | `tester.binding.rootPipelineOwner.semanticsOwner` (or the deprecated `pipelineOwner`) is null → no error, and "tap target ≥ 48" passes forever | The semantics tree lives on each view's own PipelineOwner: `tester.binding.renderViews.first.owner?.semanticsOwner`; **every invariant needs a negative case on real data** (make the app really draw a 24×24 tap target and check that the report says so) — JSON-level mutations alone cannot find this kind of collection bug |
| Hidden text counted as text | An empty field's hint stays in the tree at zero opacity (`InputDecorator` fades it with an `AnimatedOpacity`); the dump reports it as a text the design does not have | The dumper skips `RenderOpacity` and `RenderAnimatedOpacity` at 0 (as well as `RenderOffstage`) |
| A text field's fill missing from the boxes | `InputDecorator` paints the fill itself, so the render-tree walk finds no decorated box and reports the design's field boxes as missing | Export each filled `InputDecorator` as a box (rect from its render box, fill and radius from its `InputDecoration`) |
| Every text is 1.5–3% wider than the board | Material's text styles carry letter spacing 0.25/0.5 that any `Text` without its own `letterSpacing` inherits; wraps, bubble widths and centred groups shift | `letterSpacing: 0` on every slot of the theme's `TextTheme` (the `tracking` check finds it) |
| Fractional line height (26.5) | Flutter rounds line boxes to whole pixels: 26.5 renders 27, 26.4 renders 26; paragraphs end up taller or shorter than drawn | Integer line heights in the board; the `measure_text_test` asserts it and the rendered-pitch check catches it |
| `SelectableText` wider than `Text` | An editable text reserves a 1px caret gap plus the cursor width (2): a bubble hugging it is 3px wider than the board | `cursorWidth: 0` and take the remaining 1px back from the padding |
| One spacing for every markdown block | `flutter_markdown` puts a single `blockSpacing` between paragraphs, list items and code blocks, while a board spaces them differently (6 / 4) | `blockSpacing` for the smaller gap, `pPadding` for the extra under paragraphs |
| A test tap does nothing | An animation needs its first frame to start: one `pump(400ms)` after a tap only starts it, and the next tap hits the old layout | `pump()` then `pump(duration)` after every tap |
| A button's label sits ~1px higher than the same style elsewhere | Material's typography styles carry `leadingDistribution: even`, which an ordinary `Text` inherits; a button sets `Material(textStyle: ...)`, which replaces the inherited style, so the same `TextStyle` shares its leading proportionally there (a 16 px / 20 px line: baseline 16.0 instead of 17.0 from the top) | Put `leadingDistribution: TextLeadingDistribution.even` in the app's own text styles (the tokens), so a style draws the same wherever it is used; measure baselines through a `Text` under `MaterialApp(theme: ...)`, not a bare `TextPainter` |
| The same line box, two baselines | `height: 1.45` on 12 px and `height: 17 / 12` both give a 17 px box, but the baseline differs by 0.3 px (Flutter rounds the box, not the leading) | Tokens state the line height in px; the app derives `height: lh / size` from it, and the board asks the ruler for that very ratio |
| Baselines "fixed" in the app one component at a time | Every text was nudged until it matched a board whose baselines were a constant (`centre + 0.35 × size`); when the board moved to the measured ruler, hundreds of nudged texts were 1 px off the other way | Take the baseline from the measured ruler first, then fix the few places where the app's geometry (paddings, fixed `Baseline` constants) really differs |
| A mutation lands on a baselined element | Reported as "missed" when the baseline absorbed it | `mutate.py` automatically avoids elements in the baseline; hand-written mutations must pick clean elements too |
