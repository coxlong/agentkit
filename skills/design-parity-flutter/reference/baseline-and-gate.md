# Baseline and gate

## baseline.json

```json
{"schema": 1, "entries": [
  {"screen": "settings.list.dark",
   "id": "settings.list.dark/row/3/icon",
   "property": "mae",
   "max_delta": 8.1,
   "reason": "why this difference is acceptable (specific, checkable)",
   "date": "2026-11-12"}
]}
```

| Field | Meaning |
|---|---|
| `screen` | Design screen id (`*` wildcard supported) |
| `id` | Element id with screen prefix (wildcards supported; omitted = any element in the screen) |
| `property` | The differing property (`font-size`, `box.x`, `mae` …) or category (`baseline`, `shadow` …) |
| `max_delta` | Upper bound for a numeric difference: the difference counts as "known" when ≤ it; omitted = any value |
| `expect_app` | For non-numeric differences: the app value must equal this |
| `reason` | **Required**, and must not be empty or `TODO…` |
| `date` | **Required** |

A matched difference is marked `baselined` and does not fail the gate; an unmatched one is `new`.

## Rules

1. The baseline holds **only confirmed acceptable** differences, with a specific reason (who, why, when it can be deleted).
   **Never add an entry just to make a run pass.**
2. The baseline only shrinks: `parity.py` lists entries that no longer exist (stale — delete them) and entries whose difference
   got smaller (tighten `max_delta`). `--fail-on-stale` makes stale entries fail too; enable it in CI.
3. New entries start as a draft from `parity.py suggest-baseline` (reason `TODO`, which is rejected); they are merged **after
   a human (or the user) confirms the reason**.
4. Loosening a default tolerance (`pos 0.5`, `size 0.05`, `radius 0.5` …) needs `tolerance_reasons.<key>` in the config,
   otherwise exit code 2. Tightening needs no reason.
5. Never change the board to fit the implementation because "the implementation cannot do it" — that is a design decision: go
   through the design-board flow and tell the user. Differences that are genuinely accepted go into the baseline.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Pass: no new differences (and no stale ones when `--fail-on-stale` is on) |
| 1 | New differences (or stale entries with `--fail-on-stale`) |
| 2 | Invalid config/data/baseline (missing file, entry without a reason, loosened tolerance without a reason, scene has no dump) |

## One command (what `tool/parity.sh` looks like)

```bash
#!/bin/bash
set -euo pipefail
python3 docs/design/src/build_board.py --measured build/measured_text.json --out docs/design/board.svg
python3 docs/design/src/check_board.py docs/design/board.svg --require-ids
python3 docs/design/src/extract_layout.py docs/design/board.svg -o build/design_layout.json
tool/render.sh                      # render the scenes into build/app/*.json|png (project root)
python3 tool/parity/parity.py check --config parity/parity.config.json --previous build/report.prev.json --fail-on-stale
python3 tool/parity/mutate.py dump --config parity/parity.config.json     # the check itself works (nightly CI)
```
`set -e` makes any failing step fail the whole command; `parity.py`'s exit code is the conclusion.

## How to design mutation tests

- Each mutation changes **one value of one element**, and the expected category is known (size → `font-size`, baseline +4 →
  `baseline`, wrong icon → `icon-glyph`, one colour step → `color`, radius +2 → `radius`, overflow → `overflow` …).
- Pass criterion: each mutation produces a **new** difference of that category on the mutated element's id; after reverting,
  `new` returns to the pre-mutation count.
- `dump` mutations prove the comparator; `source` mutations (patch + re-render) prove the dumper and the whole chain. Keep
  both: the first is fast (seconds), the second can run nightly.
- Mutations must not touch baselined elements: accepted differences stay as they are, so mutations pick "clean" elements.
- **Equivalent mutations**: mutating something already at its limit (pill button radius 26 → 28, clamped to half the short
  side) changes neither the pixels nor the numbers, and the check **correctly** reports nothing. Pick elements where the change
  is visible, and confirm every entry in the mutation list actually changes something measurable.
