#!/usr/bin/env python3
"""Build the 3D carpark deck texture from the real architectural linework.

The carpark plan that sits above the leasing fan on the mall sheets is the same
plan referenced by the standalone carpark drawings (TM-ARC-CP-DR-AR-P1/ P3).
We trace it faithfully (no redesign / no simplification) straight from the
vector linework with tools/extract_vec.extract_carpark, then rasterise that
exact trace to a white-on-transparent PNG so the interactive map can drape it
over a dark 3D deck slab (images/carpark_deck.png) — rendering 46k individual
DOM paths live would be far too heavy.

Usage:
    python3 tools/build_carpark_deck.py
    -> carpark.json            (exact traced path + bbox, source of truth)
    -> images/carpark_deck.png (white linework, transparent background)
"""
import json
import re
import sys

import cv2
import numpy as np

sys.path.insert(0, 'tools')
from extract_vec import extract_carpark  # noqa: E402

SRC = 'TM-ARC-ML-DR-AR-1F-7030.pdf'   # carpark band is identical on every level
SCALE = 6                              # px per viewBox unit


def main():
    d, bb = extract_carpark(SRC)
    json.dump({'d': d, 'bbox': [round(v, 1) for v in bb]}, open('carpark.json', 'w'))
    x0, y0, x1, y1 = bb
    cw, ch = int((x1 - x0) * SCALE), int((y1 - y0) * SCALE)
    img = np.zeros((ch, cw, 4), np.uint8)
    col = (255, 255, 255, 255)
    lw = max(1, int(SCALE * 0.32))

    def P(x, y):
        return (int((x - x0) * SCALE), int((y - y0) * SCALE))

    for t in (t.strip() for t in d.split('M') if t.strip()):
        if 'H' in t:  # rectangle: "x0 y0 Hx1 Vy1 Hx0 Z"
            m = re.match(r'([-\d.]+) ([-\d.]+) H([-\d.]+) V([-\d.]+)', t)
            if m:
                ax, ay, bx, by = map(float, m.groups())
                cv2.rectangle(img, P(ax, ay), P(bx, by), col, lw)
            continue
        m = re.match(r'([-\d.]+) ([-\d.]+) L([-\d.]+) ([-\d.]+)', t)
        if m:
            ax, ay, bx, by = map(float, m.groups())
            cv2.line(img, P(ax, ay), P(bx, by), col, lw, cv2.LINE_AA)

    cv2.imwrite('images/carpark_deck.png', img)
    print('carpark.json bbox %s | deck %dx%d px (%d subpaths)' %
          ([round(v) for v in bb], cw, ch, d.count('M')))


if __name__ == '__main__':
    main()
