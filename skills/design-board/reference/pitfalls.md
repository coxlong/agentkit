# Mistakes already made (design side)

| Mistake | Consequence | Do this instead |
|---|---|---|
| Using board numbers (A1, B7) as ids | Inserting a board in the middle shifts all numbers; the check config and baseline stop matching | Screen ids are names; numbers are for humans |
| Estimating text widths from a table | Wrap points, bubble widths, ellipsis positions and baselines are ~1px off; so someone "shortens the sample text to dodge the wrap" | Estimate for the first draft; measure with the app's text engine before strict comparison (contract §7); **never change the sample data to fit the estimate** |
| Vertical position as "centre + empirical constant" (e.g. `cy + 0.35 * size`) | 0.5–1px off across fonts | Position by the top of the line box; take the baseline from measurement |
| SVG's default centred stroke | Bordered boxes are 1px larger than the implementation (0.5 on each side) | Inset the stroke (the kit does it) and restore the nominal rectangle on extraction |
| Type sizes 12.5 / 13.5 / 14.5, weights 500 / 700 sneaking in | The scale quietly grows, and every step must be checked element by element | Everything goes through `snap_*`; call sites warn; `audit_layout --strict` rejects |
| Stroke rule "1.8px at every size" | The implementation's icon font only has discrete weights; it cannot match, so the design gets changed to fit | Choose a stroke rule the implementation can draw, while designing (by-size data in the tokens) |
| Assuming matching icon frames mean equal size | Material's visible glyph is ~91% of Lucide's in the same frame | One library on both sides; compare identity, not just the frame |
| Drawing only the "normal" state | The implementer invents disabled/empty/error states, and they do not match | State matrix; draw disabled states explicitly |
| Writing the sample data twice | Item count, order and lengths drift and show up as a pile of "content" differences | One `sample_data.json` |
| Copying tokens into code by hand | One gets missed; one side changes and the other does not | Generate with `gen_tokens_dart.py` |
| Fixed heights for components with a background | One more line of content overflows | Count lines first (same ruler), then draw the box |
| Reusing light shadows in dark mode | Shadows are almost invisible in dark mode | Each shadow has light and dark entries in the tokens |
| Changing before answering (the user asked "what do you think?" / "should we?") | The user never got to choose | Answer/recommend decision questions first; build a comparison board when it needs to be seen |
| Real addresses or secrets in the sample data | The board gets published | Reserved addresses (192.168.x.x, 203.0.113.x, example.com); scan before publishing |
| `<style>`, `foreignObject` or external images in the board | Some viewers show black boxes | `check_board.py` rejects them; all styling inline |
| Hand-editing the generated SVG | Lost on the next build | Change the generator |
| Elements without ids | The check can only say "coverage too low", never which element | `check_board.py --require-ids`; `deco=True` only for decoration |
| Reusing one id inside a board | `kit` raises immediately (a good thing) | Use an index or a business key |
