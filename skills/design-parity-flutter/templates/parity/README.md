# parity: comparator, gate, mutations, pixels (Python standard library)

| File | Purpose |
|---|---|
| `parity.py` | The gate. `check`: pair design and app by id, compare every attribute and invariant, apply `baseline.json`, write JSON + Markdown reports, exit code 0/1/2. `suggest-baseline`: write new differences as baseline drafts awaiting a reason |
| `mutate.py` | Prove the check works: `selftest` (synthesize a perfect app dump from the design) · `dump` (mutate copies of real dumps) · `source` (patch app source, really render, check, restore) |
| `pixel_diff.py` | Pixel fallback: MAE inside an element's bounding box / text ink bounding box and amount; carries its own PNG reader, no dependencies |
| `render_design_pngs.py` | Render every board artboard to `<screen>.png` (uses board-kit's `render.sh`; `FONTS=...` points at the same font files) |
| `parity.config.example.json` `baseline.example.json` `mutations.example.json` | Sample config, baseline and source mutations |

## Config (`parity.config.json`; paths are relative to the config file's directory)

```json
{
 "design": "build/design_layout.json",
 "app_dir": "build/app",
 "screens": {"settings.list": "settings_list", "settings.list.dark": "settings_list_dark"},
 "design_icons": "docs/design/src/icons.json",
 "app_icons": "assets/fonts/app_icons.json",
 "weight_family": "AppIcons{weight}",
 "baseline": "parity/baseline.json",
 "design_id_index": "build/design_ids.json",
 "source_roots": ["lib"],
 "tolerance": {},
 "tolerance_reasons": {},
 "require": {"text_coverage": 1.0, "icon_coverage": 1.0, "box_coverage": 0.0, "tap_min": 48},
 "pixels": {"design_png_dir": "build/design_png", "app_png_dir": "build/app"},
 "report": {"json": "build/report.json", "md": "build/report.md"}
}
```
- `screens`: design screen id → app scene name (dump file name). A design screen not listed here **is not checked** — remember
  the line when adding a screen.
- Default tolerances (px): `pos 0.5`, `size 0.05`, `lh 0.1`, `icon_pos 0.5`, `radius 0.5`, `stroke 0.1`, `shadow_px 0.5`,
  `shadow_opacity 0.02`, `alpha 0.01`. Loosening one requires a reason in `tolerance_reasons`, otherwise it refuses to run.
- The `pixels` section is optional; when present the pixel fallback runs (design PNGs and app PNGs must be the same size).

## Behaviour verified during development (on a small app that is not shipped)

A new difference → exit code 1; a `suggest-baseline` draft's `TODO` reason is rejected (2); a real reason → baselined, pass;
after fixing, a stale entry appears and `--fail-on-stale` fails; loosening a tolerance without a reason → exit code 2;
27/27 mutations detected (once on synthesized data, once on real dumps, covering every difference category); source-level
mutations were patched, re-rendered and all detected.
