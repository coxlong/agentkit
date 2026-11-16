# Mistakes already made (design side)

| Mistake | Consequence | Do this instead |
|---|---|---|
| Using board numbers (A1, B7) as ids | Inserting a board in the middle shifts all numbers; every reference stops matching | Screen ids are names; numbers are for humans |
| Estimating text widths from a table, then trusting it | Wrap points, bubble widths, ellipsis positions and baselines are ~1px off; so someone "shortens the sample text to dodge the wrap" | Estimate for the first draft and leave slack; measure with the target rendering engine when precision matters (contract §6); **never change the sample data to fit the estimate** |
| Vertical position as "centre + empirical constant" (e.g. `cy + 0.35 * size`) | 0.5–1px off across fonts, and no single constant fits — a centred line's baseline offset depends on the style's line height, so styles with different line heights land at different offsets. Fitting a table of offsets just copies the renderer into the board | Position by the top of the line box with a named style (size, weight, line height) and take the baseline from the ruler |
| SVG's default centred stroke | Bordered boxes are 1px larger than intended (0.5 on each side) | Inset the stroke (the kit does it) and restore the nominal rectangle on extraction |
| Type sizes 12.5 / 13.5 / 14.5, weights 500 / 700 sneaking in | The scale quietly grows, and every step must be checked element by element | Everything goes through `snap_*`; call sites warn; `audit_layout --strict` rejects |
| Fractional line heights (26.5) | Some rendering engines round a line box to whole pixels (26.5 renders 27), so every paragraph is taller than drawn | Integer line heights in the tokens |
| Stroke rule "1.8px at every size" | Only discrete stroke steps can actually be drawn; the rule cannot be met and the design gets changed to fit | Choose a stroke-by-size rule in the tokens while designing |
| Assuming matching icon frames mean equal size | Material's visible glyph is ~91% of Lucide's in the same frame | One library; compare identity, not just the frame |
| Drawing only the "normal" state | The implementer invents disabled/empty/error states, and they do not match | Draw the state in the layer that owns it: composition states as artboards, fine-grained variants in the component panel |
| Writing the sample data twice | Item count, order and lengths drift and show up as a pile of "content" differences | One `sample_data.json` |
| Fixed heights for components with a background | One more line of content overflows | Count lines first (same ruler), then draw the box |
| Reusing light shadows in dark mode | Shadows are almost invisible in dark mode | Each shadow has light and dark entries in the tokens |
| Changing before answering (the user asked "what do you think?" / "should we?") | The user never got to choose | Answer/recommend decision questions first; build a comparison board when it needs to be seen |
| Real addresses or secrets in the sample data | The board gets published | Reserved addresses (192.168.x.x, 203.0.113.x, example.com); scan before publishing |
| `<style>`, `foreignObject` or external images in the board | Some viewers show black boxes | `check_board.py` rejects them; all styling inline |
| Hand-editing the generated SVG | Lost on the next build | Change the generator |
| Elements without ids | A report can only say "coverage too low", never which element | `check_board.py --require-ids`; `deco=True` only for decoration |
| Reusing one id inside a board | `kit` raises immediately (a good thing) | Use an index or a business key |
| Reviewing the whole board every round | Model review drowns in unchanged PNGs, so nothing gets looked at properly | The generator records per-screen content hashes; review only the screens `build.sh` lists as changed |
| Drawing every state as its own screen (empty × dark × size × …) | The board balloons into hundreds of near-duplicate artboards and stops being a curation decision; ~40 artboards is a normal single-app board | Screen = composition change only (regions, overlays, pages, viewport); component panel = appearance change, including theme cross-products |
| Extending the project's existing custom generator instead of migrating | The ids, meta and gate contract stay half-present and get patched on; the next agent inherits the same gap | Migrate to the board-kit; carry over only token values, measured-text answers and icon sets |
| Building the whole board before any approval | A wrong visual direction multiplies into every artboard and the correction is a full rebuild | Deliver one representative screen + one component panel and wait for approval (pilot step) |
