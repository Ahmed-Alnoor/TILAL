#!/usr/bin/env python3
"""
Extract leasing-unit polygons from the Tilal Grand Mall architectural PDFs
(Level 1 and Basement) and emit baked <path class="unit"> markup that overlays
the existing Ground-Floor map.

How it works
------------
* The interactive map's SVG viewBox ("0 0 3370 2384") is exactly the A0 page
  box measured in PDF points.  Rendering a page at D dpi therefore maps pixels
  to viewBox units by a pure scale of 72/D (no offset, no rotation) -- verified
  against the Ground-Floor baked paths (units bbox x[761..2640] y[893..1634]).
* Units in every sheet are filled with the same small palette of flat colours,
  each of which maps to one leasing/facility category (mapping taken from the
  Ground-Floor baked paths, the ground truth).  We classify each pixel inside
  the mall region to its nearest palette colour (vs white/black/grey), build a
  per-category mask, trace contours with OpenCV and simplify them.

Parking is NOT traced here: it is a stylised design layer drawn procedurally by
the web app from the basement's mall bounding box (the band along the top edge).

Usage
-----
  pdftoppm -r 200 -png TM-ARC-ML-DR-AR-1F-7030.pdf /tmp/r200_f1
  pdftoppm -r 200 -png TM-ARC-ML-DR-AR-BL-7010.pdf /tmp/r200_bl
  python3 tools/extract_floor.py        # -> /tmp/floor_F1.txt, /tmp/floor_BL.txt
  python3 tools/build_html.py           # inject paths -> HTML + index.html
"""
import json, sys
import numpy as np
import cv2
from PIL import Image

DPI   = 200
SCALE = 72.0 / DPI            # pixel -> viewBox(point) factor

# Leasing/facility fill centroids -> category. Sampled directly from the rendered
# sheets (more accurate than the GF baked attributes) and mapped into the app's
# existing 8-category system (CATS) so 1F/BL behave exactly like the Ground Floor.
PAL = [
    ((254,232,224),'specialty'), ((248,232,224),'specialty'), ((252,233,233),'specialty'),
    ((232,192,232),'toilet'),    ((232,197,232),'toilet'),
    ((176,202,232),'retail'),    ((176,200,232),'retail'),
    ((248,216,168),'retail'),    # tan/orange perimeter leasing wings (1F) -> retail
    ((248,184,184),'fnb'),       ((248,191,191),'fnb'),  ((232,216,248),'fnb'),
    ((216,232,232),'seating'),   ((104,182,255),'seating'),
    ((255,237,210),'service'),
    ((247,232,170),'kiosk'),     ((152,248,152),'kiosk'), ((159,255,159),'kiosk'),
    ((215,255,215),'hyper'),
]
# background / linework / non-leasing centroids (classify away from real fills)
NONC = [
    (255,255,255), (245,245,245), (200,200,200), (150,150,150), (0,0,0),
    (248,248,208),               # pale-yellow central court / atrium (exclude)
    (240,232,232), (240,224,216), # near-white anti-aliased fringes
    (248,0,0),                    # red dimension / annotation linework
]
# runtime category colours (must match CATS in the HTML so the bake looks right
# even before the app recolours them)
CAT_COLOR = {
    'hyper':'#d7ffd7','retail':'#b0cae8','specialty':'#fee8e0','fnb':'#f8bfbf',
    'kiosk':'#9fff9f','seating':'#dbeded','service':'#ffedd2','toilet':'#ebc5eb',
}
# non-palette anchors so background / linework classify away from real fills
NON = {'_white': (255,255,255), '_black': (0,0,0), '_grey': (150,150,150),
       '_grey2': (200,200,200)}

# mall region of interest, in viewBox units (parking band lies above ymin)
ROI_VB = (680.0, 840.0, 2720.0, 1720.0)   # xmin,ymin,xmax,ymax

MIN_AREA_VB = 70.0       # drop specks  (viewBox units^2)
MAX_AREA_VB = 90000.0    # drop atrium / court / background blobs
EPS_PX      = 1.6        # Douglas-Peucker tolerance (pixels)


def hx(h):
    h = h.lstrip('#'); return (int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))


def classify(arr):
    """Return a category-label image of strings ('' = background/linework)."""
    cents = [rgb for rgb, _ in PAL] + list(NONC)
    cats  = [cat for _, cat in PAL] + [None] * len(NONC)
    C = np.array(cents, dtype=np.int32)                  # (K,3)
    h, w, _ = arr.shape
    flat = arr.reshape(-1, 3).astype(np.int32)
    best = np.zeros(flat.shape[0], dtype=np.int32)
    bestd = np.full(flat.shape[0], 1 << 30, dtype=np.int64)
    for i in range(C.shape[0]):
        d = ((flat - C[i]) ** 2).sum(1)
        m = d < bestd
        bestd[m] = d[m]; best[m] = i
    lab = np.array(cats, dtype=object)[best].reshape(h, w)
    return lab


def contour_to_path(cnt, holes, ox, oy):
    """Build an SVG path 'd' (outer + hole subpaths) from pixel contours."""
    def sub(c):
        pts = c.reshape(-1, 2)
        seg = ['M%.2f,%.2f' % ((pts[0,0]+ox)*SCALE, (pts[0,1]+oy)*SCALE)]
        for p in pts[1:]:
            seg.append('L%.2f,%.2f' % ((p[0]+ox)*SCALE, (p[1]+oy)*SCALE))
        seg.append('Z')
        return ' '.join(seg)
    d = sub(cnt)
    for hc in holes:
        d += ' ' + sub(hc)
    return d


def extract(img_path, idprefix, remap=None):
    arr = np.array(Image.open(img_path).convert('RGB'))
    # crop to mall ROI (pixels)
    x0 = int(ROI_VB[0] / SCALE); y0 = int(ROI_VB[1] / SCALE)
    x1 = int(ROI_VB[2] / SCALE); y1 = int(ROI_VB[3] / SCALE)
    roi = arr[y0:y1, x0:x1]
    lab = classify(roi)

    # demising walls / linework: carve dark pixels out of every fill mask so
    # adjacent same-colour tenancies separate into individual units.
    darks = (roi.max(2) < 115).astype(np.uint8)
    darks = cv2.dilate(darks, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))

    min_area_px = MIN_AREA_VB / (SCALE * SCALE)
    max_area_px = MAX_AREA_VB / (SCALE * SCALE)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    paths = []; counts = {}; n = 0
    cats = sorted(set(c for _, c in PAL))
    for cat in cats:
        mask = (lab == cat).astype(np.uint8)
        mask[darks > 0] = 0
        mask = (mask * 255).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hier is None:
            continue
        hier = hier[0]
        for i, c in enumerate(cnts):
            if hier[i][3] != -1:          # this is a hole; handled with its parent
                continue
            a = cv2.contourArea(c)
            if a < min_area_px or a > max_area_px:
                continue
            outer = cv2.approxPolyDP(c, EPS_PX, True)
            if len(outer) < 3:
                continue
            holes = []
            ch = hier[i][2]
            while ch != -1:
                hc = cnts[ch]
                if cv2.contourArea(hc) >= min_area_px * 0.6:
                    holes.append(cv2.approxPolyDP(hc, EPS_PX, True))
                ch = hier[ch][0]
            ecat = (remap or {}).get(cat, cat)   # per-floor category remap
            n += 1
            did = '%s%04d' % (idprefix, n)
            d = contour_to_path(outer, holes, x0, y0)
            paths.append('<path class="unit" data-id="%s" data-cat="%s" fill="%s" '
                         'fill-rule="evenodd" d="%s"/>' % (did, ecat, CAT_COLOR[ecat], d))
            counts[ecat] = counts.get(ecat, 0) + 1
    return paths, counts


def overlay(paths, out_png, w=3370, h=2384):
    """Quick raster QA: render the emitted paths to a PNG via a tiny SVG."""
    import subprocess, re, tempfile, os
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d">' % (w, h),
           '<rect width="%d" height="%d" fill="#f4f6f8"/>' % (w, h)]
    svg += [p.replace('class="unit" ', '').replace('fill-rule', 'stroke="#5b6b7a" '
            'stroke-width="0.8" fill-rule') for p in paths]
    svg.append('</svg>')
    tmp = out_png + '.svg'
    open(tmp, 'w').write('\n'.join(svg))
    try:
        subprocess.run(['rsvg-convert', '-o', out_png, tmp], check=True)
    except Exception:
        # fall back: leave the .svg for manual inspection
        pass


if __name__ == '__main__':
    jobs = [
        ('/tmp/r200_f1-1.png', 'F1', 'F1', None),
        # basement: the dominant pale-cyan back-of-house rooms collapse into one
        # neutral bucket ('service') rather than the misleading 'F.C. Seating'.
        ('/tmp/r200_bl-1.png', 'B1', 'BL', {'seating': 'service'}),
    ]
    out = {}
    for img, prefix, tag, remap in jobs:
        paths, counts = extract(img, prefix, remap)
        out[tag] = paths
        print('%s: %d units  %s' % (tag, len(paths), counts))
        open('/tmp/floor_%s.txt' % tag, 'w').write('\n'.join(paths))
        overlay(paths, '/tmp/overlay_%s.png' % tag)
    json.dump(out, open('/tmp/floors.json', 'w'))
    print('wrote /tmp/floor_F1.txt, /tmp/floor_BL.txt, /tmp/floors.json')
