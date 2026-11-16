# Design method details

The rules below came out of building real boards. The style changes per app; **the structure does not**.

## 1. Board structure

- **Artboard**: a phone at 390 × 844 (wide layouts separately, e.g. 1280 × 800). Under each artboard a **note strip**: a
  numbered chip (A1…) + title + at most 3 lines. The note says which state this is, where it comes from and what to watch
  out for — not what is obvious.
- **Sections** (A, B, C…) follow the **user journey**, not page types. Typical: A start and first use · B main flow
  (input, in progress, done, cancelled, error) · C attachments/uploads · D errors and recovery · E drawers/panels/sheets ·
  F secondary flows · G settings and management · H wide layout · I dark · J design rules.
- **Rule panels** are boards too, in the last section: logo and forbidden uses, colour, type/shape/spacing, components 1:1
  with all their variants, input specs, motion table, copy list, accessibility list. Panels use board coordinates, not
  phone coordinates.
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
- Components with a background (cards, bubbles, inputs): draw the box first, then the text inside. The box height comes
  from the content (line count), and the line count comes from the same ruler.
- Icons: `g.ic('key', cx, cy, size, colour, id=...)`, positioned by centre.
- Text of unknown width (user content): `maxw=` for ellipsis, or `lines()` for wrapping. Ellipsis must be drawn in the
  design (put one over-long item in the sample data).

## 3. Component library (`parts.py`)

- One component = one function `component(g, y, ..., id_prefix)` returning the y of the next element, so a screen reads
  like a list.
- Build the **minimum set** first: top bar, list row, buttons (primary/secondary/text), input, card/bubble, banner, sheet,
  empty state. Only extract a component when something appears a third time.
- Component states are parameters (`enabled=False`, `state='error'`); do not copy the component.
- Ids inside a component are prefixed: `f'{p}/title'`, so the same component stays predictable in other places and screens.

## 4. States and variants

- The board form is layered (see SKILL.md "Board form"): **screens carry the composition, the component panel carries the
  variants, rule panels carry the system**.
- **A state earns its own artboard only when it changes the composition** — a region appears or disappears, an overlay or
  pushed page opens, or the viewport changes (keyboard, size, theme). A state that only changes one component's
  appearance — including theme × variant cross-products — belongs in that component's panel.
- Composition states (empty, error, loading, offline, wide, keyboard open, enlarged font) are **their own artboard**:
  `b.screen('x.dark', ..., build, K.dark)` — same ids, dark theme, not another code path.
- **Dark mode is another screen** (same ids, dark theme) for a small set of representative screens (usually 3–6); the
  rest of dark coverage is the theme switch drawn in the component panels.
- Fine-grained states (hover, focus, pressed, disabled, in progress) live **only in the component panel**: draw every
  component once per variant, with `state=` parameters — never repeat a variant on every screen that uses the component.
- "In progress" is drawn as a static instant (a static spinner glyph), with the motion (duration, curve) in the note; the
  motion table lives in the rule panel.
- Content lengths are data: short / long / over-long strings come from `sample_data.json`; an over-long item per list is
  mandatory (it proves ellipsis and wrapping).

## 5. Copy rules (write into DESIGN.md and list in the rule panel)

Every board has a **written list** of copy rules, and review against it:

1. Say each thing once: do not repeat a state (if the top bar says "Generating", do not say it elsewhere).
2. Common actions are icons, not words; every icon needs a semantic label (accessibility).
3. No tutorial copy, no "learn more" links, no explaining the obvious.
4. Errors: cause + what can be done, one sentence; technical detail folded away.
5. Sample data is realistic but not real: reserved addresses, example paths.

`copy_audit` (exports every visible string) helps review: how often the same sentence appears, whether a subtitle earns
its place.

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

- **Pilot first.** For a board of more than a handful of screens, deliver one representative screen + one component panel
  and wait for approval before building the rest (workflow step 5). A wrong direction then costs two artboards, not the
  whole board.
- **Render after every change and look at it yourself** — but only the screens that changed: the generator records each
  screen's content hash (`frame.Board.write_meta` → `build/screen_meta.json`), `build.sh` compares it with the previous
  build and prints the changed list, and `render_screens.sh` renders those (or all) screens as individual PNGs. Judge
  each PNG: overflow, overlap, misalignment, anything unreadable in dark mode. A whole-board thumbnail is only for
  checking section order; render one when the structure changes or before the final review.
- Publish only when asked or under a standing permission: build → static gates → render every screen once for a final
  pass → scan for secrets/real addresses → upload → hash the online file and compare. Keep only the current version;
  delete older ones (back them up locally first).
- Report to the user: conclusion first, then "which boards changed (names)", then the link; where there is a trade-off,
  list the options and recommend one.

## 8. Lessons that belong on day one

| Thing | Why |
|---|---|
| Element ids and screen ids | Without them, nothing can later refer to an element unambiguously |
| One copy of the sample data | Written twice, it inevitably drifts in wrapping, item count or order |
| The same tokens for every consumer | A hand-copied value always misses one |
| Measure text when precision matters | Estimated widths put wrap points and baselines ~1px off; "close enough" forever is inconsistency |
| Strokes inside the box | SVG's centred stroke makes every bordered box 1px larger |
| Choose stroke weights that can actually be drawn | Otherwise the design has to be changed afterwards to fit |
| One icon library | Mixing sets leaves stroke width, caps and meaning inconsistent |
| Screen = composition change only | Turning every state into its own screen balloons the board into theme × variant cross-products that nobody reviews |
| Migrate, don't extend, a legacy generator | Patching ids, meta and gates onto a non-conformant kit leaves the contract half-present |
| Pilot before mass build | A wrong direction multiplied into every artboard costs the whole board |
