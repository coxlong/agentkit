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
| A mutation lands on a baselined element | Reported as "missed" when the baseline absorbed it | `mutate.py` automatically avoids elements in the baseline; hand-written mutations must pick clean elements too |
