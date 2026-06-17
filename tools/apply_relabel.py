#!/usr/bin/env python3
"""Apply /tmp/relabel.json to index.html: rewrite each unit's data-id / data-cat
and add real area attributes (data-m2 / data-ft2 / data-name).  Units the PDF
matcher didn't reach keep their geometry but get a light category cleanup
(the auto 'kitchen' tiles the user flagged become food-village / food-court)."""
import json, re

mp = json.load(open('/tmp/relabel.json'))
ALL = {}
for fl in ('GF','F1','BL'):
    ALL.update(mp.get(fl, {}))

# cleanup for tiles the forward matcher didn't carry a code into
REMAP = {'fc-kitchen':'food-court', 'fv-kitchen':'food-village',
         'hyper':'hypermarket', 'hypermarket':'hyper-store',
         'specialty-retail':'line-shop', 'specialty':'line-shop', 'retail':'line-shop',
         'seating':'fc-seating', 'service':'customer-service',
         'fnb-kiosk-seating-area':'kiosk-seating', 'food-village':'food-village'}

html = open('index.html').read()
changed = {'relabel':0, 'remap':0}

def esc(s):
    return s.replace('&','&amp;').replace('"','&quot;').replace('<','&lt;').replace('>','&gt;')

def repl(m):
    head, oid, ocat, old_extra = m.group(1), m.group(2), m.group(3), m.group(4)
    if oid in ALL:
        r = ALL[oid]
        nid, ncat = r['id'], r['cat']
        extra = ' data-name="%s"' % esc(r['name'] or '')
        if r.get('m2'): extra += ' data-m2="%s" data-ft2="%s"' % (r['m2'], r.get('ft2') or '')
        changed['relabel'] += 1
        # old data-name/m2/ft2 (old_extra) are intentionally dropped & replaced
        return '%sdata-id="%s" data-cat="%s"%s' % (head, nid, ncat, extra)
    ncat = REMAP.get(ocat, ocat)
    if ncat != ocat:
        changed['remap'] += 1
    # unmatched unit: keep its existing data-name/m2/ft2 untouched
    return '%sdata-id="%s" data-cat="%s"%s' % (head, oid, ncat, old_extra)

# consume any existing data-name / data-m2 / data-ft2 so they are replaced,
# not duplicated, for relabelled units.
html = re.sub(
    r'(<path class="unit" )data-id="([^"]+)" data-cat="([^"]+)"'
    r'((?: data-name="[^"]*")?(?: data-m2="[^"]*")?(?: data-ft2="[^"]*")?)',
    repl, html)
open('index.html','w').write(html)
print('relabelled (real PDF code/area):', changed['relabel'])
print('category cleanup (unmatched tiles):', changed['remap'])
# distribution after
cats = re.findall(r'<path class="unit" data-id="[^"]+" data-cat="([^"]+)"', html)
from collections import Counter
for c,n in Counter(cats).most_common():
    print('  %-18s %d' % (c, n))
