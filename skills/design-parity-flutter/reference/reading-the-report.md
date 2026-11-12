# How to read the report

`report.md` (human) and `report.json` (machine) carry the same content. Top: pass or fail, **why it failed**, the number of
paired elements, the number of differences (new / baselined), and the font sha256.

## Categories

| Category | Meaning | Usual cause / how to fix |
|---|---|---|
| `missing` | The design has this id; the app dump does not | No `ValueKey`; the element did not render (clipped/invisible); the id is misspelled |
| `extra` | The app has this id; the design does not | The implementation draws something extra; or the board is missing it (go through the design flow) |
| `coverage` | The design has elements without ids / the app's id coverage is too low | Add ids; mark decoration with `deco=True` |
| `text` | The text content differs | Not using the shared sample data; different localised copy |
| `font-size` `weight` `line-height` `color` `align` | The corresponding text property differs | Not using the token text style; a `copyWith` changed something |
| `x` `baseline` | First-line anchor x / first-line baseline differ | Position is off (spacing = the sum of these deltas); a ~1px global baseline difference → the board was not built from app measurements (step D) |
| `lines` `ellipsis` | Line count / ellipsis differ | Wrapping width differs; `maxLines`/`overflow` not set; different fonts change wrap points |
| `icon-glyph` | Icon identity differs (design icon name ≠ app glyph name) | Wrong icon; not using the generated `AppIcons` |
| `icon-size` `icon-pos` `icon-color` | Size / centre / colour | Same as above; icon-button padding pushes the icon off |
| `icon-weight` | Font family (stroke weight step) ≠ the step the rule gives | The size is off the rule's steps; not using `AppIcon` (a bare `Icon` instead) |
| `box` | Box x/y/w/h differ | Layout difference; `margin` stacked with `padding`; stroke inside vs outside |
| `fill` `border` `radius` `shadow` | Fill / border width and colour / radius / shadow | Not using tokens; shadow `blurRadius` maps to the design's `blur` |
| `overflow` | RenderFlex overflowed while rendering | Content too big; it must be fixed |
| `tap-target` | A tappable area's smallest side < 48 | Enlarge the hit area (icon buttons need a 48×48 hit area) |
| `id-conflict` | Two `ValueKey`s landed on the same render object (the dumper keeps the first) | Put the key on the inner widget only |
| `overlap` | Two id-carrying text boxes overlap | Layout overlap; do not put ids on page content under an overlay (or baseline it with a reason) |
| `pixel` | Pixel fallback: box/icon MAE, or text ink bbox/amount | Wrong shape, missing shadow; engine antialiasing differences (baseline them with a reason) |

## Columns

`screen` (design screen) · `id` (with screen prefix) · `category` · `property` (the exact property) · `design` · `app` ·
`delta` (app − design) · `tol` · `where`.

`where` has two parts: `design <file:line>` (the python call in the board generator that produced this element, from
`build/design_ids.json`) and `app <file:line>` (the `ValueKey` literal for this id, grepped under `source_roots`; ids built
dynamically fall back to the longest static prefix and are marked `(prefix)`).

## Order for handling a new difference

1. Read `where`, open both code lines.
2. Decide the source: the implementation is wrong → fix the implementation; the board is wrong → go through the design flow
   (tell the user, record the change); engine rendering difference → baseline with a reason; different data → check that the
   data is shared.
3. Many differences of one category with similar values (e.g. every baseline off by 1.04px) → systemic: first check whether
   the board used app measurements, instead of fixing them one by one.
4. Re-run after fixing; compare the "before/after" table at the top of `report.md` to confirm the count dropped and nothing new
   appeared elsewhere.

## Do not

- Do not look at a screenshot, decide "close enough" and drop a difference.
- Do not loosen tolerances, delete comparisons or add baseline entries to make it green.
- Do not change the board because "the implementation cannot do it"; that is a design decision.
