# Tilal Mall — 3D Ground Floor Parking Map

A **real, navigable 3D parking map** for the Tilal Mall ground floor, built with
[Three.js](https://threejs.org/) in a single self-contained `index.html`
(Three.js loads from a CDN — no build step needed).

## Navigate it yourself
- **Left-drag** = orbit / rotate the lot
- **Right-drag** = pan
- **Scroll** = zoom
- **Click a bay** = open its details panel
- **Reset view** / **Top view** buttons reframe the camera

## Features
- **262 parking bays** across 10 zones (A–J), matching the real layout counts:
  A 14 · B 28 · C 24 · D 20 · E 32 · F 24 · G 28 · H 24 · I 16 · J 52.
- Bays are at **ground level** (not the F1 render) and named `A01, A02, …` (zero-padded).
- Every bay is a **clickable 3D object** showing name, zone, status and plate.
- **Check availability** reveals **free (green)** / **busy (red)**; 50 bays are randomly
  occupied (with 3D car models + plate numbers) and stay hidden until you press the button.
- **Search** by **plate number** or **slot number** — matches glow yellow and the
  camera **flies to** the bay.
- **Blue gradient** background, soft shadows, fog depth.

## Run / host
Open `index.html` in any modern browser, or host on GitHub Pages / any static host.
Needs internet access the first time to fetch Three.js from the CDN.
