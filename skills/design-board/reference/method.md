# Design method details

These are the rules that came out of Harness Go (a Flutter chat client, 87 artboards), with that app's style removed. The
style changes per app; **the structure does not**.

## 1. Board structure

- **Artboard**: a phone at 390 × 844 (wide layouts separately, e.g. 1280 × 800). Under each artboard a **note strip**: a
  numbered chip (A1…) + title + at most 3 lines. The note says which state this is, where it comes from and what to watch
  out for — not what is obvious.
- **Sections** (A, B, C…) follow the **user journey**, not page types. Typical: A start and first use · B main flow (input,
  in progress, done, cancelled, error) · C attachments/uploads · D errors and recovery · E drawers/panels/sheets ·
  F secondary flows · G settings and management · H wide layout · I dark · J design rules.
- **Rule panels** are boards too, in the last section: logo and forbidden uses, colour, type/shape/spacing, components 1:1,
  input specs, motion table, copy list, accessibility list. Panels use board coordinates, not phone coordinates.
- **Flow diagrams**: "which screen leads to which, and why" as an arrow diagram at the end of the relevant section.
- **Comparison boards**: when the user must choose A/B/C, put the options side by side, on the same sample data, with the
  recommendation and the reason marked. Do not touch the real board until the user chooses.

## 2. Drawing conventions

- All styling as **inline attributes**. No `<style>`, CSS variables, `foreignObject` or external images — otherwise some
  viewers show black boxes. `check_board.py` rejects them.
- Every element goes through `kit.G`: `text / lines / rect / circle / line / path / ic`; snapping happens inside.
- Text uses **named styles** (`'title'`, `'body'`, `'caption'`…): size + weight + line height, defined in `tokens.json`.
  One-off tweaks with `size= / weight=` are snapped and warned about.
- Vertical position is the **top of the line box**; use `at='base'` when aligning to another element's baseline.
- Components with a background (cards, bubbles, inputs): draw the box first, then the text inside. The box height comes from
  the content (line count), and the line count comes from the same ruler.
- Icons: `g.ic('key', cx, cy, size, colour, id=...)`, positioned by centre.
- Text of unknown width (user content): `maxw=` for ellipsis, or `lines()` for wrapping. Ellipsis must be drawn in the design
  (put one over-long item in the sample data).

## 3. Component library (`parts.py`)

- One component = one function `component(g, y, ..., id_prefix)` returning the y of the next element, so a screen reads like
  a list.
- Build the **minimum set** first: top bar, list row, buttons (primary/secondary/text), input, card/bubble, banner, sheet,
  empty state. Only extract a component when something appears a third time.
- Component states are parameters (`enabled=False`, `state='error'`); do not copy the component.
- Ids inside a component are prefixed: `f'{p}/title'`, so the same component stays predictable in other places and screens.

## 4. States and variants

- The state matrix is in SKILL.md. **Dark mode is another screen** (same ids, different theme), not another code path:
  `b.screen('x.dark', ..., build, K.dark)`.
- Draw every "disabled" state: buttons, inputs, icon buttons, menu items. The implementer will make them non-tappable; if
  the board does not show it, it is not specified.
- "In progress" is drawn as a static instant (a static spinner glyph), with the motion (duration, curve) in the note; the
  motion table lives in the rule panel.

## 5. Copy rules (write into DESIGN.md and list in the rule panel)

These are Harness Go's taste; another app may differ, but there must be a **written list**, and review against it:

1. Say each thing once: do not repeat a state (if the top bar says "Generating", do not say it elsewhere).
2. Common actions are icons, not words; every icon needs a semantic label (accessibility).
3. No tutorial copy, no "learn more" links, no explaining the obvious.
4. Errors: cause + what can be done, one sentence; technical detail folded away.
5. Sample data is realistic but not real: reserved addresses, example paths.

`copy_audit` (exports every visible string) helps review: how often the same sentence appears, whether a subtitle earns its
place.

## 6. DESIGN.md template

```
# <App> design system
## Principles   (4–8, one sentence each, with the reason)
## Tokens       (point at tokens.json; write why, never copy the numbers)
## Shape/spacing/layout  (radius steps, page margins, row height, tap targets ≥ 48)
## Components   (table: component | purpose | size/states/notes)
## States       (state matrix and precedence: which one wins when several apply)
## Motion       (table: what | duration | curve)
## Copy         (the list)
## Accessibility (contrast, semantic labels, tap targets, never colour alone)
```

When the board and DESIGN.md disagree, **the board + tokens.json win**, then fix the document.

## 7. Review and publishing

- Render after every change and **look at it yourself**: overflow, overlap, misalignment, anything unreadable in dark mode.
  This reviews the design, not the parity.
- Publish only when asked or under a standing permission: build → static gates → render → scan for secrets/real addresses →
  upload → hash the online file and compare. Keep only the current version; delete older ones (back them up locally first).
- Report to the user: conclusion first, then "which boards changed (numbers)", then the link; where there is a trade-off,
  list the options and recommend one.

## 8. Lessons from the parity check that belong on day one

| Thing | Why |
|---|---|
| Element ids and screen ids | Otherwise the check can only guess from content and position, and a wrong guess stays silent |
| One copy of the sample data | Written twice, it inevitably drifts in wrapping, item count or order |
| Generate tokens into code | A hand-copied token always misses one |
| Measure text with the app's engine | Estimated widths put wrap points and baselines 1px off; "close enough" forever is inconsistency |
| Strokes inside the box | SVG's centred stroke makes every bordered box 1px larger |
| Choose stroke weights the implementation can draw | Otherwise the design has to be changed afterwards to fit |
| Visible icon size | Matching the 24px frame is not matching the visible glyph: Material glyphs are ~90% of a Lucide glyph in the same frame |
