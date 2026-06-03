# Tilal Mall — Ground Floor Parking Map

An interactive **3D parking map** for the Tilal Mall ground floor, built as a single
self-contained `index.html` file (no build step, no dependencies).

## Features
- **262 parking bays** across 10 zones (A–J), matching the real layout counts:
  - A: 14, B: 28, C: 24, D: 20, E: 32, F: 24, G: 28, H: 24, I: 16, J: 52
- Every bay is named `A01, A02, …` (zero-padded) and is **individually clickable**.
- Clicking a slot shows its **name, zone, status and vehicle plate** (if occupied).
- **Check availability** button reveals which bays are **free (green)** and **busy (red)**.
  - 50 bays are randomly marked busy on each load; status stays hidden until you press the button.
- **Search** by **plate number** or **parking slot number** — matches are highlighted and scrolled into view.
- **Blue gradient** background, **3D tilted floor** with a **2D/3D toggle**.
- Drag anywhere on the floor to pan.

## Usage
Just open `index.html` in any browser, or host it on GitHub Pages / any static host.

## GitHub Pages
Enable Pages on the `main` branch (root) and the map will be live at
`https://<user>.github.io/parking-only-html/`.
