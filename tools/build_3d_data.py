#!/usr/bin/env python3
"""Bake the Tilal Mall leasing polygons into a compact 3D-ready dataset.

Source: tools/floors_raw.json  (raw SVG path `d` strings per floor, extracted
from the interactive map — viewBox "0 0 3370 2384", y-down).

For each unit we:
  * parse the path (absolute M/L/H/V/Z only — no curves in this data),
  * drop sub-pixel duplicate vertices and simplify every ring with
    Ramer-Douglas-Peucker so 6000-point pixel traces collapse to clean rooms,
  * discard sliver rings below a minimum area,
  * classify rings into outer contours + holes using the SVG even-odd rule
    (a ring whose interior point sits inside an odd number of other rings is a
    hole of the nearest containing outer),
  * scale the shared coordinate space down to friendly world units so the
    per-category extrusion heights read well in 3D.

Output: tools/floors_3d.json — { floorKey: { name, units:[{id,cat,name,m2,
shapes:[{o:[x,y,...], h:[[x,y,...],...]}]}] } } with coords rounded to 1dp.

A pure-Python PNG preview of each floor is also written to /tmp for a visual
sanity check (no browser / image libs required).
"""
import json, re, os, sys, zlib, struct

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'floors_raw.json')
OUT = os.path.join(HERE, 'floors_3d.json')
TEMPLATE = os.path.join(HERE, 'index_3d.template.html')
INDEX = os.path.join(HERE, '..', 'index.html')

# Tuning -----------------------------------------------------------------
RDP_EPS   = 1.4     # simplification tolerance, viewBox units (~4px @200dpi)
MIN_AREA  = 14.0    # drop rings smaller than this (viewBox units^2) — slivers
INSET     = 1.1     # shrink outer rings inward (viewBox units) to de-coincide shared walls
PLAN_SCALE = 0.11   # viewBox units -> world units (plan longest side ~= 205)
DEC = 1             # output decimal places (after scaling)
MIRROR_X = True     # mirror the plan left<->right (the source SVG is flipped vs reality)

FLOOR_NAMES = {'BL': 'Basement', 'G': 'Ground Floor', 'F1': 'Level 1'}
FLOOR_ORDER = ['BL', 'G', 'F1']

# Category fill colours (mirror of CATS in the source app) — used only for the
# preview render; the live viewer carries its own palette.
CAT_COLOR = {
    'hypermarket':'#ede5d2','hyper-store':'#d8d2c2','anchor':'#34517e',
    'mini-major':'#7390ba','line-shop':'#ccd9ea','fnb':'#c79a4e',
    'fnb-cafe':'#d8b170','fnb-kiosk':'#cda45c','fnb-seating':'#e7d4a8',
    'kiosk':'#b9914a','kiosk-seating':'#ccd9ea','food-village':'#d8b170',
    'food-court':'#c79a4e','fc-seating':'#e7d4a8','fec':'#7390ba',
    'cinema':'#34517e','customer-service':'#e3d9c2','management-suite':'#c6d1de',
    'tenant-store':'#d6cfbf','prayer-room':'#e6e1d2','circulation':'#f0f2f4',
    'mep':'#d9d6cd','boh':'#dddacf','toilet':'#bfcbdb','hyper':'#ede5d2',
    'retail':'#ccd9ea','specialty':'#ccd9ea','specialty-retail':'#ccd9ea',
    'seating':'#e7d4a8','service':'#e3d9c2',
}

# Path parsing -----------------------------------------------------------
TOK = re.compile(r'([MLHVZ])([^MLHVZ]*)', re.I)
NUM = re.compile(r'-?\d+\.?\d*')

def parse_d(d):
    rings, cur, x, y = [], [], 0.0, 0.0
    for cmd, args in TOK.findall(d):
        C = cmd.upper()
        nums = [float(n) for n in NUM.findall(args)]
        if C == 'M':
            if len(cur) >= 3:
                rings.append(cur)
            cur = []
            for i in range(0, len(nums) - 1, 2):
                x, y = nums[i], nums[i + 1]; cur.append((x, y))
        elif C == 'L':
            for i in range(0, len(nums) - 1, 2):
                x, y = nums[i], nums[i + 1]; cur.append((x, y))
        elif C == 'H':
            for n in nums:
                x = n; cur.append((x, y))
        elif C == 'V':
            for n in nums:
                y = n; cur.append((x, y))
        elif C == 'Z':
            if len(cur) >= 3:
                rings.append(cur)
            cur = []
    if len(cur) >= 3:
        rings.append(cur)
    return rings

def dedupe(pts, eps=0.05):
    out = []
    for p in pts:
        if not out or abs(p[0]-out[-1][0]) > eps or abs(p[1]-out[-1][1]) > eps:
            out.append(p)
    if len(out) > 1 and abs(out[0][0]-out[-1][0]) < eps and abs(out[0][1]-out[-1][1]) < eps:
        out.pop()
    return out

def rdp(points, eps):
    """Iterative Ramer-Douglas-Peucker on an open polyline."""
    n = len(points)
    if n < 3:
        return points[:]
    keep = [False] * n
    keep[0] = keep[n-1] = True
    stack = [(0, n-1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]; bx, by = points[b]
        dx, dy = bx-ax, by-ay
        d2 = dx*dx + dy*dy
        idx, dmax = -1, eps*eps
        for i in range(a+1, b):
            px, py = points[i]
            if d2 == 0:
                dist2 = (px-ax)**2 + (py-ay)**2
            else:
                t = ((px-ax)*dx + (py-ay)*dy) / d2
                t = 0 if t < 0 else 1 if t > 1 else t
                cx, cy = ax+t*dx, ay+t*dy
                dist2 = (px-cx)**2 + (py-cy)**2
            if dist2 > dmax:
                idx, dmax = i, dist2
        if idx != -1:
            keep[idx] = True
            stack.append((a, idx)); stack.append((idx, b))
    return [points[i] for i in range(n) if keep[i]]

def simplify_ring(pts):
    pts = dedupe(pts)
    if len(pts) < 3:
        return None
    closed = pts + [pts[0]]
    simp = rdp(closed, RDP_EPS)
    if simp and simp[0] == simp[-1]:
        simp = simp[:-1]
    return simp if len(simp) >= 3 else None

def signed_area(r):
    a = 0.0
    n = len(r)
    for i in range(n):
        x1, y1 = r[i]; x2, y2 = r[(i+1) % n]
        a += x1*y2 - x2*y1
    return a / 2.0

def point_in_poly(pt, poly):
    x, y = pt; inside = False; n = len(poly)
    j = n-1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj-xi)*(y-yi)/(yj-yi+1e-12) + xi):
            inside = not inside
        j = i
    return inside

def interior_point(r):
    cx = sum(p[0] for p in r)/len(r)
    cy = sum(p[1] for p in r)/len(r)
    if point_in_poly((cx, cy), r):
        return (cx, cy)
    # scanline fallback: widest interior span at y ~ centroid
    for dy in (0.0, 0.37, -0.37, 0.91, -0.91):
        y0 = cy + dy
        xs = []
        n = len(r)
        for i in range(n):
            x1, yy1 = r[i]; x2, yy2 = r[(i+1) % n]
            if (yy1 <= y0 < yy2) or (yy2 <= y0 < yy1):
                t = (y0-yy1)/(yy2-yy1)
                xs.append(x1 + t*(x2-x1))
        xs.sort()
        best, bestw = None, -1
        for k in range(0, len(xs)-1, 2):
            w = xs[k+1]-xs[k]
            if w > bestw:
                bestw = w; best = (xs[k]+xs[k+1])/2
        if best is not None:
            return (best, y0)
    return (cx, cy)

def classify(rings):
    info = []
    for r in rings:
        s = simplify_ring(r)
        if not s:
            continue
        a = abs(signed_area(s))
        if a < MIN_AREA:
            continue
        info.append({'r': s, 'a': a, 'p': interior_point(s)})
    # containment depth via even-odd
    for ri in info:
        depth = 0
        for rj in info:
            if rj is ri:
                continue
            if rj['a'] > ri['a'] and point_in_poly(ri['p'], rj['r']):
                depth += 1
        ri['depth'] = depth
    shapes, outer_index = [], {}
    for k, ri in enumerate(info):
        if ri['depth'] % 2 == 0:
            outer_index[k] = len(shapes)
            shapes.append({'o': ri['r'], 'h': []})
    for k, ri in enumerate(info):
        if ri['depth'] % 2 == 1:
            best, bestA = None, float('inf')
            for j, rj in enumerate(info):
                if j == k or rj['depth'] % 2 != 0:
                    continue
                if rj['a'] > ri['a'] and point_in_poly(ri['p'], rj['r']) and rj['a'] < bestA:
                    bestA, best = rj['a'], j
            if best is not None and best in outer_index:
                shapes[outer_index[best]]['h'].append(ri['r'])
    return shapes

def with_winding(ring, want_positive):
    """Force a ring's orientation. ExtrudeGeometry faces its top cap toward +Z
    only for CCW (positive-shoelace) outer rings; holes must be the opposite."""
    if (signed_area(ring) > 0) != want_positive:
        return ring[::-1]
    return ring

def inset_ring(ring, d):
    """Shrink an outer ring inward by ~d units toward its centroid. Adjacent
    units are traced as separate paths that share a wall; without a hairline
    gap those coincident walls z-fight ("boxes noise"). The per-vertex step is
    clamped, and the whole inset is reverted if it would collapse a thin unit."""
    n = len(ring)
    cx = sum(p[0] for p in ring) / n
    cy = sum(p[1] for p in ring) / n
    out = []
    for x, y in ring:
        dx, dy = cx - x, cy - y
        L = (dx*dx + dy*dy) ** 0.5
        if L < 1e-6:
            out.append((x, y)); continue
        step = min(d, 0.30 * L)
        out.append((x + dx/L*step, y + dy/L*step))
    a0, a1 = abs(signed_area(ring)), abs(signed_area(out))
    if a1 < 0.45 * a0 or (signed_area(ring) > 0) != (signed_area(out) > 0):
        return ring          # would distort a thin unit — leave it
    return out

def mirror_ring(ring):
    """Reflect a ring across the plan's vertical axis (negate x). Orientation is
    re-normalised afterwards by with_winding, so caps/holes stay correct."""
    return [(-x, y) for (x, y) in ring] if MIRROR_X else ring

def round_ring(r):
    return [round(v, DEC) for p in r for v in p]

# Bake -------------------------------------------------------------------
def bake():
    floors = json.load(open(RAW))
    # global bbox (shared space) for centring offset baked into preview only
    out = {}
    stats = {}
    for fl in FLOOR_ORDER:
        units = floors.get(fl, [])
        baked = []
        nshapes = nholes = 0
        for u in units:
            try:
                rings = parse_d(u['d'])
                shapes = classify(rings)
                if not shapes:
                    continue
                packed = []
                for sh in shapes:
                    outer = with_winding(mirror_ring(inset_ring(sh['o'], INSET)), True)
                    o = [round(v*PLAN_SCALE, DEC) for p in outer for v in p]
                    hs = [[round(v*PLAN_SCALE, DEC) for p in with_winding(mirror_ring(hole), False) for v in p]
                          for hole in sh['h']]
                    packed.append({'o': o, 'h': hs} if hs else {'o': o})
                    nshapes += 1; nholes += len(hs)
                baked.append({'id': u['id'], 'cat': u['cat'], 'name': u['name'],
                              'm2': u['m2'], 's': packed})
            except Exception as e:  # one bad polygon must never abort the bake
                sys.stderr.write('skip %s: %s\n' % (u.get('id'), e))
        out[fl] = {'name': FLOOR_NAMES[fl], 'units': baked}
        stats[fl] = (len(baked), nshapes, nholes)
    json.dump(out, open(OUT, 'w'), separators=(',', ':'))
    for fl in FLOOR_ORDER:
        u, s, h = stats[fl]
        print('  %-3s %-12s units=%-4d shapes=%-5d holes=%-4d' % (fl, FLOOR_NAMES[fl], u, s, h))
    print('wrote %s (%.0f KB)' % (os.path.basename(OUT), os.path.getsize(OUT)/1024))
    return out

# Pure-Python PNG preview (scanline fill, even-odd holes) ----------------
def hex_rgb(h):
    h = h.lstrip('#'); return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

def write_png(path, w, h, buf):
    def chunk(typ, data):
        c = typ + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += buf[y*w*3:(y+1)*w*3]
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 6))
    png += chunk(b'IEND', b'')
    open(path, 'wb').write(png)

def fill_shape(buf, W, H, sx, sy, ox, oy, shape, color):
    rings = [shape['o']] + shape.get('h', [])
    polys = []
    for flat in rings:
        polys.append([( (flat[i]-ox)*sx, (flat[i+1]-oy)*sy ) for i in range(0, len(flat), 2)])
    ys = [p[1] for poly in polys for p in poly]
    if not ys:
        return
    y0 = max(0, int(min(ys))); y1 = min(H-1, int(max(ys)))
    r, g, b = color
    for y in range(y0, y1+1):
        yc = y + 0.5
        xs = []
        for poly in polys:
            n = len(poly)
            for i in range(n):
                x1, yy1 = poly[i]; x2, yy2 = poly[(i+1) % n]
                if (yy1 <= yc < yy2) or (yy2 <= yc < yy1):
                    xs.append(x1 + (yc-yy1)/(yy2-yy1)*(x2-x1))
        xs.sort()
        for k in range(0, len(xs)-1, 2):
            xa = max(0, int(xs[k]+0.5)); xb = min(W-1, int(xs[k+1]-0.5))
            base = (y*W + xa)*3
            for px in range(xa, xb+1):
                buf[base] = r; buf[base+1] = g; buf[base+2] = b; base += 3

def preview(out):
    # shared bbox across floors (already scaled)
    allx = []; ally = []
    for fl in FLOOR_ORDER:
        for u in out[fl]['units']:
            for sh in u['s']:
                fo = sh['o']
                allx += fo[0::2]; ally += fo[1::2]
    minx, maxx = min(allx), max(allx); miny, maxy = min(ally), max(ally)
    pad = 6
    W = 1100
    sx = (W - 2*pad) / (maxx-minx)
    sy = sx
    H = int((maxy-miny)*sy) + 2*pad
    for fl in FLOOR_ORDER:
        buf = bytearray([18, 20, 28] * (W*H))   # dark bg
        for u in out[fl]['units']:
            col = hex_rgb(CAT_COLOR.get(u['cat'], '#888888'))
            for sh in u['s']:
                fill_shape(buf, W, H, sx, sy, minx-pad/sx, miny-pad/sy, sh, col)
        p = '/tmp/preview_%s.png' % fl
        write_png(p, W, H, buf)
        print('  preview', p)

def inject():
    """Inline the baked dataset into the viewer template -> ../index.html."""
    tmpl = open(TEMPLATE, encoding='utf-8').read()
    data = open(OUT, encoding='utf-8').read()
    if '__FLOORDATA__' not in tmpl:
        sys.exit('placeholder __FLOORDATA__ not found in template')
    html = tmpl.replace('__FLOORDATA__', data)
    open(INDEX, 'w', encoding='utf-8').write(html)
    print('wrote %s (%.0f KB, self-contained)' % (os.path.relpath(INDEX, HERE), os.path.getsize(INDEX)/1024))

if __name__ == '__main__':
    print('Baking 3D dataset...')
    out = bake()
    print('Rendering previews...')
    preview(out)
    print('Injecting into viewer...')
    inject()
