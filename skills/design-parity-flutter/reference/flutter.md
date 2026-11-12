# Flutter implementation and checking details

The templates are in `templates/flutter/`. The points below were verified in Flutter 3.47.9's test renderer.

## 1. Text: tokens → TextStyle → line box

- Each named token style is `{size, weight, lh}`. `gen_tokens_dart.py` emits `TextStyle(fontSize, fontWeight, height: lh / size,
  leadingDistribution: TextLeadingDistribution.even)` with a `fontFamily`.
- A `Text` with such a style has a box exactly `lh` tall, and its first-line baseline is the box top plus the font's measured
  in-box baseline. The board positions text with the same numbers (measured by the app), so if the `Text`'s top is right, the
  baseline is right. **Do not** use `Baseline` with an empirical constant.
- Do not wrap `Text` in anything that adds padding (`Padding` is fine if you account for it in the position).
  `Container(alignment: ...)` makes the box expand and changes its height — do not use it on measured elements.
- Weights: `FontWeight.w600` matches the **closest file at or above** that weight. If the design uses 600, ship a 600
  (SemiBold) file or accept it falling back to Bold — but **measurement and rendering must use the same files** (that is why
  one `FontSpec` list feeds both tests).
- Ellipsis: `maxLines: 1, overflow: TextOverflow.ellipsis` → the dumper reports `ellipsis = didExceedMaxLines`. Ellipsised text
  on the board ends with `…`, produced by the app's own measurement.

## 2. Font loading (tests)

- `flutter test` uses Ahem (boxes) by default; register the real fonts under the **family names the theme uses** with
  `FontLoader` (`render_support.dart: loadFonts`). For CJK, register Noto Sans SC as the default family (and for `monospace`),
  otherwise Chinese characters render as boxes.
- **`loadFonts` must be in `setUpAll`.** Inside a `testWidgets` body, `Process.run('sha256sum')` never returns in the fake-async
  zone and the test hangs (this really happened).
- One family can register several files (Regular/Bold/ExtraBold); the engine matches by the weight in each file.
- Record the font sha256 (`fonts.json`); the report carries it, and a font change means measuring text again.

## 3. Scenes and dumping

- `render_scenes_test.dart`: device size = design screen size × DPR (default 2); each scene is wrapped in
  `RepaintBoundary(key) > SizedBox(390×844)`; the PNG uses `toImage(pixelRatio: 1)` (390×844, the same size the board renders).
- Do not use `pumpAndSettle` (it times out with spinners or endless animations): `pump()` plus one `pump(Duration)`.
- **RenderFlex overflow**: Flutter throws it as a test failure by default. The harness replaces `FlutterError.onError` with
  "collect messages containing `overflowed`" and writes them into `invariants.overflows`, which `parity.py` treats as
  `overflow` differences — so one run shows all overflows instead of stopping at the first. Restore `onError` at the end
  (`addTearDown`).
- **Tap targets**: after `tester.ensureSemantics()`, walk the semantics tree, take nodes with a `tap` action, transform their
  rects to root coordinates and divide by DPR. The ≥ 48 requirement is `require.tap_min` in the config. Usual fix: an icon
  button as `SizedBox(48×48)` + `Center(icon)` (`IconButton`'s default 48px padding shifts the icon; `InkResponse` with a fixed
  size is easier to control).

## 4. How the dumper (`layout_dump.dart`) reads the render tree

| Wanted | How |
|---|---|
| First-line left edge/width, line count | `RenderParagraph.getBoxesForSelection(whole text)`, take the first line's boxes |
| First-line baseline | `computeDistanceToActualBaseline(TextBaseline.alphabetic)` (protected; needs an `// ignore` comment) |
| Icons | `RenderParagraph` whose font family matches the icon-font prefix; codepoint = first code unit of the text |
| Boxes | `RenderDecoratedBox` (colour, `Border`, radius, `boxShadow`), `RenderPhysicalModel/Shape` (Material surfaces) |
| Ids | walk the **Element** tree; an element with `widget.key is ValueKey<String>` → its first measurable RenderObject |
| Spinner | it is not a glyph: recognise it with `DumpOptions.isSpinner` and dump it as `spinner: true` |

Traps: `Border.all(width: 1)` draws **inside** (matching the board); `BoxShadow.blurRadius` = the design's `blur` (= 2σ);
radii come from `BorderRadius`'s four corners.

## 5. Icon fonts (Flutter-specific)

- One font family per weight step; every `IconData` must be `static const` in a class marked `@staticIconProvider`, or release
  builds cannot tree-shake the icon font.
- **Verify the shake**: `flutter build apk --release` logs one `Font asset "..." was tree-shaken, reducing it from X to Y bytes`
  per font; a `non-constant instances of IconData` error means someone constructed `IconData(cp, ...)` at runtime.
- A declared but unreferenced font file goes into the package **whole** (it is not shaken), so only declare the weights in use.
- Tests do not load fonts automatically (see §2); the render test must add the icon fonts to `fonts` too.

## 6. Layout habits (that make the check pass)

- Spacing, radii and sizes come from tokens, never literals; do not put `margin` on a container and add `padding` inside it
  (the box rectangle will differ from the design).
- Bordered boxes: `DecoratedBox/Container(decoration: BoxDecoration(border: Border.all(...)))`; do not stack
  `Material(shape: ...side)` on top, or the inner and outer rectangles stop matching.
- Material's `ListTile`/`IconButton`/`TextField` have their own padding and minimum heights; for exact alignment build from
  primitives or push `visualDensity/minimumSize/tapTargetSize` to the design values.
- Absolute positioning (`Stack + Positioned`) is only a convenient way to mirror a board; real apps use `Column/Row` and let
  the check measure the result.

## 7. Running environment

All commands run in the project root: `flutter pub get` (with `gen-l10n` projects, `flutter gen-l10n` first) → generate
tokens/icon fonts → `flutter test` → `parity.py`. If the current machine cannot run Flutter, run `flutter test` on a machine
that can and copy `build/app/*.json|png` back into the project; `parity.py` reads the same relative paths. This skill contains
no connection instructions.

## 8. Numbers verified during development (on a small app that is not shipped)

With estimated metrics: 22 differences (all baselines, about 1px) → 0 after the app measured the text; size/weight/colour/
position/icon identity and weight/border/shadow/ellipsis were 0 from the start, because both sides read the same tokens and
data. That is the point: **one source for tokens + one source for data** removes most differences; what remains is measurement
error.
