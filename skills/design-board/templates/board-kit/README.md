# board-kit: the design-board toolkit (Python standard library, no dependencies)

Copy it into the project's `docs/design/src/`, turn `*.example.json` into `tokens.json`, `icons.json`, `sample_data.json`,
and write your own `parts.py` / `screens_*.py` / `build_board.py` (following `example/build_example.py`).

| File | What it does |
|---|---|
| `kit.py` | Token loading (`init`), scale snapping (`snap_*`), text rulers (estimated and the app-measured `MeasuredRuler`), icons, the `G` element accumulator (ids) |
| `frame.py` | Artboard frame `phone()`, note strip `caption()`, section headers, `Board` layout (auto numbering), the SVG document |
| `check_board.py` | Static checks: XML, forbidden constructs, duplicate ids, `--require-ids` (text and icons must have ids) |
| `extract_layout.py` | Export the board to the design-side JSON (texts/icons/boxes/lines per screen, with ids, phone-local pixels) |
| `audit_layout.py` | Self-audit against the tokens: scales, overflow, text overlap, missing ids |
| `copy_audit.py` | Export every string on the board (sorted by how many screens use it) to review "how often is this said" |
| `render.sh` | Render a region of an SVG to PNG with headless Chromium: `./render.sh in.svg out.png x y w h scale` |
| `build.sh` | Build + all static gates (`BUILD_SCRIPT=... TOKENS=... ./build.sh board.svg`) |
| `sync_icons.py` | Refresh the SVGs in `icons.json` from the official release |
| `gen_tokens_dart.py` | `tokens.json` → Dart constants (palettes, text styles, shadows, `iconWeight`) |
| `tokens.example.json` `icons.example.json` `sample_data.example.json` | Example inputs (replace with your app's) |
| `example/build_example.py` | The smallest complete example: 2 screens × light/dark, with ids, ellipsis, wrapping, shadow, icons |

## What writing a screen looks like

```python
import kit, frame
K = kit.init('tokens.json', icons='icons.json', measured='build/measured_text.json')   # measured is optional
data = json.load(open('sample_data.json'))

def settings(g):                                   # g is this screen's G; the screen id prefix is added automatically
    g.ic('back', 36, 68, 24, g.t.ink, id='bar/back')
    g.text(64, 56, data['settings']['title'], 'title', id='bar/title')      # y = top of the line box
    g.rect(20, 112, 350, 64, 16, g.t.surface, g.t.line, 1, shadow='card', id='row/1/box')   # stroke inside

b = frame.Board(cols=4)
b.section('A', 'Main flow', 'From opening to done')
b.screen('settings.list', 'Settings list', settings, K.light, 'One row = icon + title + ellipsised subtitle.')
open('board.svg', 'w').write(b.svg())
kit.write_id_index('build/design_ids.json')        # id -> the python line that generated it (for the report)
kit.write_needed_text('build/needed_text.json')    # strings the app still has to measure (MeasuredRuler)
```

## Conventions

- `x` right, `y` down, origin at the top-left of the phone screen; `g.text(x, y, ...)`'s `y` is the **top of the line box**
  (`at='center'` / `at='base'` change that).
- `id=` is a path within the screen, unique; `deco=True` marks decoration that is not checked. A multi-line paragraph uses
  `g.lines(..., id=...)` and is one id.
- Style names come from `tokens.text_styles`; `size= / weight=` overrides are snapped and recorded in `kit.WARNINGS`
  (the build script must print them).
- Strokes are inside boxes and circles; icon strokes come from `tokens.scales.icon_stroke_units` by size.
- Board chrome text (note strips, section headers) uses the `chrome_*` estimate ruler and never appears in the list the app
  has to measure.
