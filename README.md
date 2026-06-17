# TILAL
TILAL MALL

## Maps

- **`index.html`** — a smooth, golden-hour **3D floor-plan viewer** (single
  self-contained file). Double-click it or host it on any static site. Loads
  Three.js r137 from a CDN via classic `<script>` tags, so it runs from
  `file://` too. One finger orbits, two fingers pinch-zoom/pan, tap a unit for
  its details. Floors: Basement / Ground / Level 1.
- **`tilal-mall-interactive-map.html`** — the earlier 2.5D SVG mall map
  (kept for reference; also the source of the floor-plan polygons).

## Rebuilding the 3D viewer

The polygon data is baked offline (parsed, simplified, even-odd holes,
scaled) and inlined into `index.html`:

```sh
python3 tools/build_3d_data.py
```

- `tools/floors_raw.json` — raw extracted SVG paths per floor (source).
- `tools/build_3d_data.py` — simplify + classify holes → `tools/floors_3d.json`.
- `tools/index_3d.template.html` — the viewer; `__FLOORDATA__` is replaced with
  the baked dataset to produce `index.html`.
