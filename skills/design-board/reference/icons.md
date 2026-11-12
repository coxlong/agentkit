# Icon system

Goal: the board and the app draw **the same icons with the same stroke**, and a script can verify each one's identity, size,
weight, position and colour.

## How

1. **Pick one icon library** (outlined, 24-grid, round caps), e.g. Lucide. The whole app uses only it; brand marks and other
   custom glyphs go under `custom`.
2. **`icons.json`**: design key → library name. `sync_icons.py` fetches the SVGs from the official release (pinned version).
   The board draws the SVGs; the app's icon font is built from the same list. Design keys are semantic (`back`, `settings`),
   not library names — the keys survive a library change.
3. **Stroke weight by size** (`tokens.scales.icon_stroke_units`). A font glyph has exactly one stroke, so Flutter gets "one
   font per weight step", selected by size in `AppGlyph.at(size)`. The rule is data: the board, the font builder and the Dart
   tokens all read the same file. Example: 12px → 3.0 units (w600, 1.5px) · 16px → 2.5 (w500, 1.67px) · 20px → 2.0 (w400,
   1.67px) · 24px → 2.0 (w400, 2px) · above 27px → 1.5 (w300).
4. **Font build** (`build_icon_font.py`, needs fonttools): keep only the listed glyphs from the per-weight static fonts of
   `lucide_icons_flutter`, producing a small font per weight (about 2–12 KB each); shift glyphs back onto the SVG 24-grid
   (the source font centres each glyph on its own bounding box, up to 0.5 grid off); add `custom` glyphs (straight segments
   only) from U+F100 up.
5. **Dart**: a `@staticIconProvider` class with one `static const IconData` per icon per weight, an `AppIcons` table mapping
   each key to an `AppGlyph`; product code only writes `AppIcon(AppIcons.back, size: 24, color: ...)`.

## Why not Material icons

- In the same 24px frame, Material's visible glyph is smaller than Lucide's (measured median 91%, arrows as low as 80%), so
  "the icon size matches" does not mean it looks the same size.
- Mixing Material's rounded, outlined and default variants leaves stroke width and caps inconsistent (47 icons split
  27/16/4 across variants).
- Meaning drifts too: error as a circled `!` or a triangle, cancelled as a stop square or ⊗ — one side picks one, the other
  picks the other, and the design no longer matches.

## Licensing

The font carries the icon library's copyright notice (name table); keep a `LICENSE` in the repo (Lucide: ISC, Feather parts
MIT; `lucide_icons_flutter`: MIT; provenance of custom glyphs).

## Checking

`parity.py` checks every paired icon: design icon name → library name == the name reverse-looked-up from the app glyph; font
family == the step from the rule; size; centre; colour. **The identity check needs `app_icons.json`** (the font builder's
output), so icons must always go through the generated font, never hand-written code points.
