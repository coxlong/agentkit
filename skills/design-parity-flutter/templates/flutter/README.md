# flutter: app-side templates

Copy them into the project (`test/render/` and `lib/`) and fill in the places the comments mark "fill in".

| File | Goes to | Purpose |
|---|---|---|
| `layout_dump.dart` | `test/render/` | Dump the render tree: texts/icons/boxes (with ids, borders, shadows, ellipsis) + invariants (overflow, tap targets, id coverage, id conflicts) |
| `render_support.dart` | `test/render/` | `loadFonts`: register fonts and record their sha256 (shared by measurement and rendering) |
| `render_scenes_test.dart` | `test/render/` | Render every scene: write `<scene>.json` and `<scene>.png`; collect overflows; only runs with `RENDER=1` |
| `measure_text_test.dart` | `test/render/` | Let the app's text engine answer the board's measurement questions (width/wrap/ellipsis/baseline); only runs with `MEASURE=1` |
| `app_glyph.dart` `app_icon.dart` | `lib/` | `AppGlyph` (IconData per weight step) and the `AppIcon` widget (picks the weight by size) |
| `build_icon_font.py` | `tool/` | Build the icon fonts, `app_icons.json` and `app_icons.g.dart` from `icons.json` (needs fonttools and a pub cache with `lucide_icons_flutter`) |

Where generated files come from: `gen_tokens_dart.py` (this folder) → `lib/design_tokens.g.dart`;
`app_glyph.dart` depends on its `iconWeight()`.

Environment variables: `RENDER=1`, `RENDER_OUT`, `ONLY` (scene names, comma-separated), `RENDER_DPR`, `RENDER_PNG_RATIO`;
`MEASURE=1`, `NEEDED`, `MEASURED_OUT`; `SAMPLE_DATA` (the scene data file).
