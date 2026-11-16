# Icon system

Goal: the board draws **one consistent icon system with a defined stroke**, and every consumer can reproduce each icon's
identity, size, weight, position and colour from the same files.

## How

1. **Pick one icon library** (outlined, 24-grid, round caps), e.g. Lucide. The whole app uses only it; brand marks and
   other custom glyphs go under `custom`.
2. **`icons.json`**: design key → library name. `sync_icons.py` fetches the SVGs from the official release (pinned
   version). Design keys are semantic (`back`, `settings`), not library names — the keys survive a library change.
3. **Stroke weight by size** (`tokens.scales.icon_stroke_units`). One data rule that the board and every downstream
   consumer read. Example: 12px → 3.0 units · 16px → 2.5 · 20px → 2.0 · 24px → 2.0 · above 27px → 1.5. Pick the rule
   while designing, and only use steps that can actually be drawn (a "1.8px at every size" rule is the kind that has to
   be changed later).
4. **Use only the set in `icons.json`.** Custom glyphs are straight segments only (so any consumer can rebuild them), and
   are never fetched by `sync_icons.py`.

## Why not Material icons

- In the same 24px frame, Material's visible glyph is smaller than Lucide's (measured median 91%, arrows as low as 80%),
  so "the icon size matches" does not mean it looks the same size.
- Mixing Material's rounded, outlined and default variants leaves stroke width and caps inconsistent (47 icons split
  27/16/4 across variants).
- Meaning drifts too: error as a circled `!` or a triangle, cancelled as a stop square or ⊗ — one side picks one, the
  other picks the other, and the design no longer matches.

## Licensing

Keep a `LICENSE` in the repo for the chosen library (Lucide: ISC, Feather parts MIT) and note the provenance of custom
glyphs.
