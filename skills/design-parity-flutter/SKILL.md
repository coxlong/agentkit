---
name: design-parity-flutter
description: >
  Implement a Flutter app from its SVG design board and PROVE, with scripts only, that the implementation matches the
  design: tokens generated into code, preview scenes fed by the board's sample data, stable element ids, a layout dump of
  the real widget tree, id-paired comparison of every text / icon / box attribute (font size, weight, line height, colour,
  baseline, glyph identity, stroke weight, radius, border, shadow, ellipsis ...), render-tree invariants (overflow, tap
  targets, overlap, id coverage), a pixel fallback, a baseline file with a pass/fail exit code, JSON + Markdown reports and
  mutation tests that prove the check itself works. No step lets a model judge screenshots. Use when building UI from a
  design board, "making the app match the design", adding a screen to an already-checked app, or setting up / continuing
  the consistency gate. The comparator is framework-neutral (it consumes a JSON dump); the templates here are for Flutter.
metadata:
  last_verified: 2026-11-12
  proven_on: Flutter 3.47.9 — verified end to end on a throwaway 4-screen app during development: 22 differences with estimated text metrics -> 0 with app-measured metrics; 27/27 dump mutations, 7/7 app-level faults and 5/5 source-patch mutations detected; pixel fallback 1 baselined difference. No example app is shipped.
---

# design-parity-flutter: implement the app and prove it matches the board, with scripts

Used together with `design-board`: that side produces the board with ids; this side implements it as an app and proves the
two match **with the numbers and pass/fail the scripts produce**. The style differs per app; the check does not.

> Status note (do not overstate): the method was run end to end on a 4-screen app during development (not shipped with this
> skill): 22 differences with estimated metrics → 0 with app-measured metrics; 27/27 mutations detected (against a real app
> dump, covering every difference category); the app itself drawing 7 deliberate faults (including a too-small tap target)
> all detected; 5/5 source-patch mutations detected (with one useful lesson: +2 on the "pill" button radius is invisible, so
> the check **correctly** did not report it — pick mutations on elements where the change shows); the pixel fallback was
> down to 1 baselined difference with the same fonts and hinting off. **Harness Go has not been migrated to id pairing** (it
> uses the old content + position comparison without a baseline gate), so this is a verified method + templates, not
> "Harness Go already works this way".

## Iron rules (the user's hard requirements; follow every one)

1. **Parity is judged by scripts only.** The judgment is `parity.py`'s numbers and exit code. Screenshots and heat maps are
   **attachments** for human review; "it looked the same to me" is not a conclusion.
2. **Never loosen tolerances, delete comparisons, or change the design to fit the implementation.** Any exemption goes into
   `baseline.json`: screen, id, property, tolerance, **reason**, date. Loosening the default tolerance requires a reason in the
   config (`tolerance_reasons`), otherwise `parity.py` refuses to run. Design changes happen only when they are **a design
   decision** (go through the design-board flow, tell the user) and are listed separately in the report as "design changes";
   never to make the check pass.
3. **Do not change product behaviour.** While building the check, only these may change: the check tools, the test harness,
   and stable identifiers (`ValueKey` / `Semantics(identifier)`). Fixing a difference = fixing the implementation's visuals and
   layout (that is the task), and still does not change behaviour.
4. **Every claim is backed by command output.** Anything not verified is explicitly marked "not verified".
5. **No commit, push or upload unless the user explicitly asks.**

## When to use / prerequisites

Use when: implementing a board as an app; aligning an existing app to a board; adding a check to a new screen; setting up or
continuing the consistency gate.

Prerequisites (fix what is missing first; do not force it):
- The board satisfies the contract: `check_board.py --require-ids` passes (every text and icon has an id), and `tokens.json`,
  `icons.json`, `sample_data.json` exist (see `design-board/reference/contract.md`). **Old boards without ids** → add ids with
  the design-board flow; never fall back to matching by content.
- A working `flutter test` environment (local is fine; all commands run in the project root) and the **same font files** the
  design was measured with.

## Workflow (in order; verify each step on its own)

**A. Tokens into code.** `gen_tokens_dart.py tokens.json lib/design_tokens.g.dart`; the theme (colours, `TextStyle`, shadows,
radii) comes entirely from the generated classes — no hand copying. Icons: `flutter/build_icon_font.py` generates the per-weight
fonts + `lib/app_icons.g.dart` + `app_icons.json`; product code writes only `AppIcon(AppIcons.x, size: N)`.
Exit: `flutter analyze` is clean.

**B. Preview scenes.** One scene per design screen (fake services/fake data), fed from the **same `sample_data.json`**; variants
such as dark mode are separate scenes. Scene names map to design screen ids (the config holds `screen id → scene name`).
Exit: the scenes render and their content comes from the shared data.

**C. Stable ids.** Every text/icon/box that has an id in the design gets `key: ValueKey('<id without screen prefix>')` on the
matching widget (one key applies to the **first** measurable object; nesting duplicates are reported as `idConflicts`).
Tappable things get `Semantics(identifier: ...)`. Exit: the app dump's `coverage` meets the config (text/icons 100%).

**D. The same ruler.** The board's text width/wrap/baseline come from **the app's own text engine**:
`kit.init(..., measured=...)` + `measure_text_test.dart`, two rounds until "0 strings still estimated"; record the font sha256
(the render test writes `fonts.json`). **Never** shorten the sample text to dodge a wrap difference.

**E. Dump and compare.** Render test: each scene writes `<scene>.json` (`layout_dump.dart`) and `<scene>.png`; design side
`extract_layout.py`; `parity.py check --config parity.config.json` pairs by id one-to-one and compares:
text (content, size, weight, line height, colour, alignment, first-line anchor x, first-line baseline, line count, ellipsis) ·
icons (glyph identity, size, **stroke weight step**, centre, colour) · boxes (x y w h, fill, border width and colour, radius,
shadow offset/blur/colour) · invariants (RenderFlex overflow, tap target ≥ 48, overlapping text, id coverage).
**Spacing is not measured separately**; it is the sum of the position differences.

**F. Baseline and gate.** `baseline.json`: differences already confirmed acceptable (screen, id, property, `max_delta`,
reason, date). A new difference → exit code 1; an entry whose difference is gone → a "stale, delete it" note (fails under
`--fail-on-stale`); an entry with an empty or `TODO` reason is rejected (exit code 2). **One command** runs everything
(including rendering) and its exit code goes into CI.

**G. Report.** Machine-readable `report.json` + human `report.md`: a "before/after" difference-count table at the top
(`--previous`), a screen × category summary, and for each difference the id, design value, implementation value, delta,
tolerance and **code location** (design: the python line that generated it; implementation: the line of the `ValueKey` literal
found by grep).

**H. Mutation tests prove the check works.** `mutate.py selftest|dump|source`: size +1, baseline +4px (spacing), wrong icon,
one colour step, radius +2, overflow, shadow, border, ellipsis, missing element, extra element, tap target, line height,
alignment, icon position/weight, fill, overlap, id conflict, coverage … (27 in total), each of which must be detected and
must go back to zero after the mutation is reverted. `dump` proves the comparator; `source` patches the app source and really
re-renders, proving the dumper too. Make it automatic.

**I. Pixel fallback.** Render the board with **the same font files**, hinting off (`render_design_pngs.py` + `render.sh
FONTS=...`), then `pixel_diff.py` compares inside each element's bounding box: boxes/icons by mean absolute error, text by
ink bounding box and ink amount. It is a second opinion that catches what attributes cannot (wrong shape, missing shadow);
engine antialiasing differences go into the baseline with a reason.

**J. Documentation and reporting.** How to run, how to add a screen, how to add a baseline entry, how to read the report (see
reference); report in the user's language: conclusion first, then changed files, every verification as "command + result",
unverified items separately, and which steps still need a human.

## Daily loop (fixing differences)

```
render → dump → parity.py check → read "new differences" in report.md → fix the implementation (not the design, not the tolerance) → repeat
```

Differences come from: the implementation is wrong (fix it) · the board is wrong (go through the design flow, tell the user,
record it) · engine rendering differences (baseline, with a reason) · different data (check that the data is shared).

## Which steps still need a human

Design choices and approval; **approval of baseline entries** (whether the reason holds); reviewing heat maps/screenshots by
eye; real-device checks; feel and motion.

## Out of scope (state these in every "not verified" list)

Real-device fonts and rendering · feel · animation · keyboard · accessibility · performance. (This check reads numbers from
Flutter's test renderer, not from a device.)

## Command cheat sheet

```
# Design side (design-board/templates/board-kit)
python3 build_board.py --measured build/measured_text.json --needed build/needed_text.json
python3 extract_layout.py board.svg -o build/design_layout.json
# App side (project root; templates in templates/flutter/)
MEASURE=1 flutter test test/render/measure_text_test.dart
RENDER=1 RENDER_OUT=build/app flutter test test/render/render_scenes_test.dart
# Comparison (templates/parity/)
python3 parity.py check --config parity.config.json [--previous build/report.prev.json] [--fail-on-stale]
python3 parity.py suggest-baseline --config parity.config.json          # new differences -> baseline draft awaiting a reason
python3 mutate.py selftest|dump --config parity.config.json            # prove the check works
python3 render_design_pngs.py --board board.svg --layout build/design_layout.json --out build/design_png   # for the pixel fallback
```

## Further reading

- `reference/pipeline.md` — each step, exit criteria, common failures.
- `reference/flutter.md` — Flutter implementation and checking details (test renderer, fonts, dumper, icon fonts, pitfalls).
- `reference/baseline-and-gate.md` — baseline format, gate rules, exit codes, how to design mutation tests.
- `reference/reading-the-report.md` — how to read the report, what each category means, how to locate things.
- `reference/pitfalls.md` — mistakes already made.
- `templates/parity/README.md`, `templates/flutter/README.md`.
