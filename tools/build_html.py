#!/usr/bin/env python3
"""Inject the extracted per-floor unit paths into the interactive map.

Reads the path blobs produced by extract_floor.py (/tmp/floor_F1.txt,
/tmp/floor_BL.txt) and drops them into the <template id="unitsF1/BL"> SVG
wrappers in the HTML, then mirrors the result to index.html.  Idempotent:
re-running replaces the template bodies in place.
"""
import re, sys, os, shutil

HTML = os.path.join(os.path.dirname(__file__), '..', 'tilal-mall-interactive-map.html')
BLOBS = {'F1': '/tmp/floor_F1.txt', 'BL': '/tmp/floor_BL.txt'}


def inject(html, floor, paths):
    pat = re.compile(
        r'(<template id="units%s"><svg[^>]*>).*?(</svg></template>)' % floor,
        re.S)
    if not pat.search(html):
        sys.exit('marker for units%s not found' % floor)
    return pat.sub(lambda m: m.group(1) + paths + m.group(2), html)


def main():
    html = open(HTML).read()
    for floor, blob in BLOBS.items():
        paths = open(blob).read().strip()
        html = inject(html, floor, paths)
        print('%s: injected %d paths' % (floor, paths.count('<path')))
    open(HTML, 'w').write(html)
    shutil.copyfile(HTML, os.path.join(os.path.dirname(HTML), 'index.html'))
    print('wrote', os.path.basename(HTML), '+ index.html')


if __name__ == '__main__':
    main()
