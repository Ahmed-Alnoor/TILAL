#!/usr/bin/env python3
"""Clean vector extraction of leasing rooms from the Tilal Grand Mall PDFs.

Instead of tracing rasterised pixels (which produced holes + jagged slivers),
we read the actual vector fills the architect drew via PyMuPDF get_drawings().
Each room is a filled path whose colour maps to a BUILDING-AREA-LEGEND category.
The page is rotated 90 deg, so points are mapped through page.rotation_matrix
into the landscape viewBox (0 0 3370 2384) used by the interactive map.
"""
import fitz

VB_W, VB_H = 3370, 2384

# colour (exact PDF fill) -> category, per floor legend
PAL_BL = {
    '#ffedd2': 'CUSTOMER SERVICE', '#d5e4ec': 'MANAGEMENT SUITE',
    '#fffbec': 'PRAYER ROOM', '#d7ffd7': 'HYPERMARKET',
    '#cfc9ae': 'TENANT STORE', '#fffff8': 'CIRCULATION',
    '#d5d5d5': 'MEP', '#dfdfdf': 'BOH', '#ebc5eb': 'TOILET',
}
PAL_F1 = {
    '#ffedd2': 'CUSTOMER SERVICE', '#fefed3': 'CINEMA', '#f8bfbf': 'F&B',
    '#dbeded': 'F.C. SEATING', '#eddffd': 'F&B / CAFE', '#ffdfaf': 'FEC',
    '#9fff9f': 'F&B KIOSK', '#6cb6ff': 'F&B KIOSK SEATING AREA',
    '#e4c9c9': 'FC KITCHEN', '#b0cae8': 'RETAIL', '#fee8e0': 'SPECIALTY RETAIL',
    '#ffeac4': 'FOOD COURT STALL', '#f7ece8': 'FOOD VILLAGE',
    '#b4f4f4': 'F.C. SEATING', '#20e0e0': 'OFFICE AREA',
    '#fffff8': 'CIRCULATION', '#d5d5d5': 'MEP', '#dfdfdf': 'BOH',
    '#ebc5eb': 'TOILET',
}


def hexof(f):
    return '#%02x%02x%02x' % (int(f[0] * 255 + .5), int(f[1] * 255 + .5), int(f[2] * 255 + .5))


def fmt(p):
    return '%.1f %.1f' % (p.x, p.y)


def clip_to_d(items, M):
    """Reconstruct an SVG path from a clip path's segment list (mapped by M)."""
    subs = []
    cur = None
    for it in items:
        op = it[0]
        if op == 'l':
            p1, p2 = it[1] * M, it[2] * M
            if cur is None or abs(p1.x - cur.x) > 0.05 or abs(p1.y - cur.y) > 0.05:
                subs.append('M' + fmt(p1))
            subs.append('L' + fmt(p2)); cur = p2
        elif op == 'c':
            p1, p2, p3, p4 = (it[i] * M for i in range(1, 5))
            if cur is None or abs(p1.x - cur.x) > 0.05 or abs(p1.y - cur.y) > 0.05:
                subs.append('M' + fmt(p1))
            subs.append('C%s %s %s' % (fmt(p2), fmt(p3), fmt(p4))); cur = p4
        elif op == 're':
            r = it[1] * M
            subs.append('M%.1f %.1f H%.1f V%.1f H%.1f Z' % (r.x0, r.y0, r.x1, r.y1, r.x0))
            cur = None
    return ''.join(subs)


def rect_d(r, M):
    r = r * M
    return 'M%.1f %.1f H%.1f V%.1f H%.1f Z' % (r.x0, r.y0, r.x1, r.y1, r.x0)


def extract(path, palette):
    pg = fitz.open(path)[0]
    M = pg.rotation_matrix
    dr = pg.get_drawings(extended=True)
    rooms = []
    for i, d in enumerate(dr):
        if d.get('type') not in ('f', 'fs'):
            continue
        f = d.get('fill')
        if f is None:
            continue
        hx = hexof(f)
        cat = palette.get(hx)
        if cat is None:
            continue
        r = d['rect']
        if r.width * r.height < 60:
            continue
        # true shape = the clip path applied just before this fill
        prev = dr[i - 1] if i > 0 else None
        if prev is not None and prev.get('type') == 'clip' and prev.get('items'):
            d_attr = clip_to_d(prev['items'], M)
        else:
            d_attr = rect_d(r, M)
        if not d_attr:
            continue
        rr = r * M
        cx, cy = (rr.x0 + rr.x1) / 2, (rr.y0 + rr.y1) / 2
        # keep only the leasing plan; drop legend swatches, title block, key plans
        if not (500 < cx < 2920 and 855 < cy < 1740):
            continue
        # disambiguate the colour-collision groups by the room's printed label
        if hx in ('#e4c9c9', '#f7ece8'):
            txt = pg.get_textbox(r).upper()
            cat = split_food(hx, txt)
        rooms.append((cat, hx, d_attr, abs(r.width * r.height), cx, cy))
    return rooms


def split_food(hx, txt):
    """#e4c9c9 = FC KITCHEN / FOOD COURT STALL / FOOD COURT (same fill);
       #f7ece8 = FV KITCHEN / FOOD VILLAGE STALL / FOOD VILLAGE (same fill).
       Split by the function name printed inside the room."""
    if hx == '#e4c9c9':
        if 'KITCHEN' in txt or 'FC-FF' in txt:
            return 'FC KITCHEN'
        if 'STALL' in txt:
            return 'FOOD COURT STALL'
        if 'FOOD COURT' in txt:
            return 'FOOD COURT'
        return 'FC KITCHEN'
    else:
        if 'KITCHEN' in txt or 'FV-FF' in txt:
            return 'FV KITCHEN'
        if 'STALL' in txt:
            return 'FOOD VILLAGE STALL'
        return 'FOOD VILLAGE'



def slug(name):
    s = name.lower().replace('&', 'n').replace('/', ' ').replace('.', '')
    return '-'.join(s.split())


def extract_carpark(path, ymin=715, ymax=898, xmin=560, xmax=2800):
    """Trace the real carpark band (black linework only) that sits above the
    leasing plan, returning one combined SVG path (integer coords) + bbox.
    The diagonal hatching / grid (light grey) is skipped."""
    pg = fitz.open(path)[0]
    M = pg.rotation_matrix
    parts = []
    xs = []
    ys = []

    def keep(p):
        return xmin < p.x < xmax and ymin < p.y < ymax

    for d in pg.get_drawings(extended=True):
        if d.get('type') != 's':
            continue
        col = d.get('color') or (0, 0, 0)
        if hexof(col) != '#000000':
            continue
        for it in d['items']:
            if it[0] == 'l':
                p1, p2 = it[1] * M, it[2] * M
                if keep(p1) and keep(p2):
                    parts.append('M%d %d L%d %d' % (p1.x, p1.y, p2.x, p2.y))
                    xs += [p1.x, p2.x]; ys += [p1.y, p2.y]
            elif it[0] == 're':
                r = it[1] * M
                if ymin < r.y0 < ymax and ymin < r.y1 < ymax:
                    parts.append('M%d %d H%d V%d H%d Z' % (r.x0, r.y0, r.x1, r.y1, r.x0))
                    xs += [r.x0, r.x1]; ys += [r.y0, r.y1]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    return ''.join(parts), bbox


if __name__ == '__main__':
    import json
    from collections import Counter
    out = {}
    cats = {}
    for path, pal, tag in [('TM-ARC-ML-DR-AR-1F-7030.pdf', PAL_F1, 'F1'),
                           ('TM-ARC-ML-DR-AR-BL-7010.pdf', PAL_BL, 'BL')]:
        rooms = extract(path, pal)
        c = Counter(r[0] for r in rooms)
        print('%s: %d rooms' % (tag, len(rooms)))
        for k, v in c.most_common():
            print('   %-24s %d' % (k, v))
        paths = []
        for j, (cat, hx, d, a, cx, cy) in enumerate(rooms):
            sl = slug(cat)
            cats[sl] = {'label': cat, 'color': hx}
            paths.append('<path class="unit" data-id="%s%04d" data-cat="%s" fill="%s" '
                         'fill-rule="evenodd" d="%s"/>' % (tag, j + 1, sl, hx, d))
        out[tag] = paths
        open('/tmp/floor_%s.txt' % tag, 'w').write('\n'.join(paths))
    # the carpark is the same on every floor — trace it once (from Level 1)
    cpd, cpbb = extract_carpark('TM-ARC-ML-DR-AR-1F-7030.pdf')
    json.dump({'d': cpd, 'bbox': cpbb}, open('/tmp/carpark.json', 'w'))
    print('carpark: %d chars, bbox %s' % (len(cpd), [round(v) for v in cpbb]))
    json.dump(out, open('/tmp/floors_vec.json', 'w'))
    json.dump(cats, open('/tmp/cats_vec.json', 'w'))
    print('wrote floor_F1/BL.txt, carpark.json, floors_vec.json, cats_vec.json')
