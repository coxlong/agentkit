# Pipeline details (A–J)

For every step: what to do · command · exit criterion · common failures.

## 0. Suggested layout

```
docs/design/src/            board generator (design-board's board-kit) + tokens.json icons.json sample_data.json
lib/design_tokens.g.dart    generated: palettes, text styles, shadows, iconWeight()
lib/app_icons.g.dart        generated: icon glyph table
lib/app_glyph.dart lib/app_icon.dart   hand-written (templates)
assets/fonts/AppIcons-w*.ttf app_icons.json   generated: icon fonts + key↔codepoint
test/render/                layout_dump.dart render_support.dart render_scenes_test.dart measure_text_test.dart (templates)
tool/parity/                parity.py mutate.py pixel_diff.py render_design_pngs.py
parity/                     parity.config.json baseline.json mutations.json (versioned)
build/                      design extraction, app dumps, reports (not versioned)
tool/parity.sh              one command (render + dump + compare + exit code)
```

## A. Tokens into code

- `python3 gen_tokens_dart.py tokens.json lib/design_tokens.g.dart` (copy `templates/flutter/gen_tokens_dart.py` into the project)
- Icons: `python3 build_icon_font.py --icons icons.json --tokens tokens.json --lucide-pkg <lucide_icons_flutter package dir> --out-fonts assets/fonts --out-dart lib/app_icons.g.dart`
  (needs fonttools; run it where fonttools is installed and commit the outputs). Declare the four font families
  (`AppIcons300/400/500/600`) in `pubspec.yaml`.
- The theme reads `DesignPalette` / `DesignTokens`; **no colour or size literals** in product code.
- Exit: `flutter analyze` clean; `grep -rn "Color(0x" lib | grep -v g.dart` finds nothing (a hit means someone copied a value).

## B. Preview scenes

- Each design screen is one scene (`Widget Function()`), on fake services and fake data read from `sample_data.json` (the
  `SAMPLE_DATA` environment variable points at it).
- A variant (dark) is a new scene. The scene-name → design-screen-id mapping lives in `screens` in `parity.config.json`.
- Scenes render the **whole 390 × 844 screen** (or the design's size); the system bar area is padding in the harness (in the
  board it is `deco` and is not compared).
- Exit: rendering does not throw; no hard-coded strings in the scenes (everything comes from the shared data or the l10n files).

## C. Stable ids

- Rules in `design-board/reference/contract.md` §1. In the implementation `key: ValueKey('row/1/title')`, **without** the
  screen id.
- List items: `ValueKey('row/${i + 1}/title')`, numbered as on the board (if the board starts `row/{i}` at 1, start at 1).
- A key applies only to the first measurable object inside it: put it on the `Text`, not on a `Padding` wrapping the same
  `Text`.
- Exit: in the dump, `invariants.coverage` is 100% for text and icons (config `require.text_coverage/icon_coverage`);
  `idConflicts` is empty.

## D. The same ruler (text measurement)

1. `python3 build_board.py --measured build/measured_text.json --needed build/needed_text.json` → lists what needs measuring.
2. `MEASURE=1 NEEDED=build/needed_text.json MEASURED_OUT=build/measured_text.json flutter test test/render/measure_text_test.dart`.
3. Rebuild; repeat until the board prints `0 strings still estimated`.
- **The fonts must be the same files as in the render test**; record the sha256 in `fonts.json`. Fonts change → measure again.
- Exit: the board builds from the measurements; the report shows the font sha256.
- Failure: `measure_text_test` hangs → font loading was put inside `testWidgets` (`Process.run` never returns in the fake-async
  zone); move it to `setUpAll`.

## E. Dump and compare

- Render: `RENDER=1 RENDER_OUT=build/app flutter test test/render/render_scenes_test.dart` (one json + png per scene;
  `fonts.json`).
- Design side: `python3 extract_layout.py board.svg -o build/design_layout.json`.
- Compare: `python3 parity.py check --config parity/parity.config.json`.
- Pairing is by id only; `missing` (design has it, app does not), `extra` (app has it, design does not) and `coverage`
  (elements without ids) are differences, not warnings.
- Exit: every new difference is understood (see reading-the-report.md) and **the implementation is fixed** — not the design,
  not the tolerance.

## F. Baseline and gate

See `baseline-and-gate.md`. Key points: the baseline holds only **confirmed acceptable** differences, with a required reason;
it only shrinks; **one command** (`tool/parity.sh`) includes rendering.

## G. Report

`parity.py` writes `report.json` (machine) and `report.md` (human). The top has a "before/after" table (`--previous` gives
the previous `report.json`), then a screen × category matrix, then the new differences (id, design value, app value, delta,
tolerance, code location).

## H. Mutation tests

- `python3 mutate.py selftest --config ...`: no app needed; synthesizes a perfect app dump from the design and checks the
  comparator itself.
- `python3 mutate.py dump --config ...`: mutates copies of **the real app dumps**, proving the comparator on real data and
  that everything returns to zero after restoring.
- `python3 mutate.py source --config ... --mutations parity/mutations.json --render-cmd "tool/render.sh" --project-dir .`:
  patches the app source, really renders, checks, restores. This also proves **the dumper**. `mutations.json`:
  `{"mutations": [{"name": "title font +1", "file": "lib/settings.dart", "find": "fontSize: 17", "replace": "fontSize: 18", "expect": "font-size", "id": "bar/title"}]}`
- At least 5 kinds: size +1, spacing +4, wrong icon, a colour step, radius +2, element overflow (the templates have 29).
  **All detected and zero after restoring** = pass; any miss means the check has a hole — fix the check first.
- Exit: `mutation_report.json` has `pass: true`, and it runs in CI.

## I. Pixel fallback

- `FONTS="Roboto|/path/Regular.otf|400;Roboto|/path/Bold.otf|700;..." python3 render_design_pngs.py --board board.svg --layout build/design_layout.json --out build/design_png --scale 1`
  (`render.sh` defaults to `--font-render-hinting=none`, so glyph advances are fractional as in Flutter; without it text
  widths are several pixels off).
- Add `"pixels": {"design_png_dir": "build/design_png", "app_png_dir": "build/app"}` to the config and run `parity.py check`.
- The default thresholds (box/icon MAE 6.0, text ink bbox 1.5px, ink amount 30%) are **already tightened**; loosening needs a
  reason. Antialiasing-engine differences (thin-stroke icons) go into the baseline with a reason.

## J. Documentation and reporting

Put a `docs/parity.md` in the project: how to run, how to add a screen (board screen → scene → one config line → run), how to
add a baseline entry, how to read the report, which steps need a human. Report format: **conclusion first**; then the changed
files; every verification as "command + result"; unverified items listed separately (real-device fonts and rendering, feel,
animation, keyboard, accessibility, performance).
