#!/usr/bin/env python3
"""Re-label every unit on all three floors with the REAL room name / unit code /
area read from the architectural PDFs.

The baked SVG map sits in a frame that is 90deg-rotated + ~1.13x scaled vs the
PDF page.  We recover a precise per-floor affine transform (PDF -> SVG) by
iterative-closest-point between PDF code labels and SVG polygon centroids,
then assign each label to the polygon that contains its mapped point.
Outputs /tmp/relabel.json : {floor:{oldId:{id,cat,m2,ft2,name}}}.
"""
import fitz, re, json
from collections import Counter

PDFS = {'GF':'TM-ARC-ML-DR-AR-GF-7020.pdf',
        'F1':'TM-ARC-ML-DR-AR-1F-7030.pdf',
        'BL':'TM-ARC-ML-DR-AR-BL-7010.pdf'}
# Leasing codes: clean upper-floor codes (GF-001, FF-112) plus the basement's
# prefixed form (SV-BL-120, C01-BL-01, OF-BL-07 ...) which is what the BL plan
# actually prints. The optional leading group captures the prefix.
CODE_RE = re.compile(r'^(?:[A-Z]{1,4}\d{0,2}-)?(?:GF|FF|BL|KS|FV|FC)-\d{1,4}(?:-S)?$')
AREA_RE = re.compile(r'(\d+(?:\.\d+)?)\s*m²\s*(\d+(?:\.\d+)?)\s*ft²')

def classify(name):
    s=' '+name.upper()+' '
    if 'HYPERMARKET' in s and 'STORE' in s: return 'hyper-store'
    if 'HYPERMARKET' in s: return 'hypermarket'
    if 'MINI' in s and 'MAJOR' in s: return 'mini-major'
    if 'ANCHOR' in s: return 'anchor'
    if 'CINEMA' in s: return 'cinema'
    if 'ENTERTAIN' in s or ' FEC ' in s: return 'fec'
    if 'FOOD' in s and 'VILLAGE' in s: return 'food-village'
    if 'FOOD' in s and 'COURT' in s: return 'food-court'
    if 'F.C.' in s and 'SEAT' in s: return 'fc-seating'
    if 'F&B' in s and 'KIOSK' in s and 'SEAT' in s: return 'kiosk-seating'
    if 'F&B' in s and 'KIOSK' in s: return 'fnb-kiosk'
    if 'F&B' in s and 'SEAT' in s: return 'fnb-seating'
    if ('F&B' in s and 'CAFE' in s) or ' CAFE ' in s: return 'fnb-cafe'
    if 'F&B' in s: return 'fnb'
    if 'KIOSK' in s: return 'kiosk'
    if 'LINE' in s and 'SHOP' in s: return 'line-shop'
    if 'CUSTOMER' in s and 'SERVICE' in s: return 'customer-service'
    if 'PRAYER' in s or 'ABLUTION' in s: return 'prayer-room'
    if 'TOILET' in s or ' WC ' in s or 'BABY CHANGE' in s or 'WASHROOM' in s: return 'toilet'
    if 'OFFICE' in s or 'MANAGEMENT' in s or 'ADMIN' in s: return 'management-suite'
    if 'STORE' in s or 'STORAGE' in s or 'TENANT' in s: return 'tenant-store'
    if any(k in s for k in (' ELEC',' MEP ','FTR','ICT','AHU','PLANT','PUMP','TANK','SUBSTATION','RISER',' BMS','TELECOM','SPRINKLER','GENERATOR','TRANSFORMER','SWITCH','SMATV',' RM ',' ROOM ')): return 'mep'
    if any(k in s for k in ('BOH','FOH','BACK OF HOUSE','LOADING','JANITOR','CLEANER','WASTE','REFUSE')): return 'boh'
    if any(k in s for k in ('CORRIDOR','LOBBY','CIRCULATION','ESCALATOR',' ESC','STAIR','BRIDGE','PEDESTRIAN','CORE','TRAVEL','RAMP','ATRIUM','CONCOURSE')): return 'circulation'
    return None
PREFIX_CAT={'KS':'kiosk','FV':'food-village','FC':'fc-seating',
            # basement prefixes (SV=service, OF=office, TS=tenant store,
            # CB/MP/FT/FP/MT/SS/EL=building services, LB=lobby, SR/CT=service)
            'SV':'tenant-store','OF':'management-suite','TS':'tenant-store',
            'CB':'mep','MP':'mep','FT':'mep','FP':'mep','MT':'mep','EL':'mep',
            'SS':'mep','LB':'circulation','SR':'boh','CT':'boh'}
def prefix_of(code):
    seg=code.split('-')[0]
    return re.sub(r'\d+$','',seg)   # 'SS03' -> 'SS', 'C01' -> 'C'

def labels_of(pdf):
    p=fitz.open(pdf)[0]
    blocks=[]
    for b in p.get_text('dict')['blocks']:
        if 'lines' not in b: continue
        t=' '.join(s['text'] for l in b['lines'] for s in l['spans']).strip()
        if t: blocks.append(((b['bbox'][0]+b['bbox'][2])/2,(b['bbox'][1]+b['bbox'][3])/2,t))
    out=[]
    for cx,cy,t in blocks:
        if not CODE_RE.match(t): continue
        pre=prefix_of(t); name=None; m2=ft2=None; best=1e9
        for x,y,bt in blocks:
            if abs(x-cx)>17 or abs(y-cy)>17: continue
            am=AREA_RE.search(bt)
            if am: m2=float(am.group(1)); ft2=float(am.group(2)); continue
            if CODE_RE.match(bt) or re.fullmatch(r'[\d\.\s,]+',bt): continue
            if re.search(r'[A-Za-z]',bt):
                dd=abs(x-cx)+abs(y-cy)
                if dd<best: best=dd; name=bt
        cat=classify(name or '') or PREFIX_CAT.get(pre)
        out.append(dict(code=t,x=cx,y=cy,name=name or '',cat=cat,m2=m2,ft2=ft2))
    return out

NUM=re.compile(r'-?\d+(?:\.\d+)?')
def ring(d):
    seg=d.split('Z')[0]; n=NUM.findall(seg)
    return [(float(n[i]),float(n[i+1])) for i in range(0,len(n)-1,2)]
def shoelace(r):
    s=0.0
    for i in range(len(r)):
        x1,y1=r[i]; x2,y2=r[(i+1)%len(r)]
        s+=x1*y2-x2*y1
    return abs(s)/2.0
def polys_of(region):
    out=[]
    for m in re.finditer(r'<path class="unit" data-id="([^"]+)" data-cat="([^"]+)"[^>]*\sd="([^"]+)"',region):
        r=ring(m.group(3))
        if len(r)<3: continue
        xs=[p[0] for p in r]; ys=[p[1] for p in r]
        out.append(dict(id=m.group(1),cat=m.group(2),ring=r,area=shoelace(r),
                        bb=(min(xs),min(ys),max(xs),max(ys)),
                        c=(sum(xs)/len(xs),sum(ys)/len(ys))))
    return out
def pip(pt,poly):
    x,y=pt; inside=False; j=len(poly)-1
    for i in range(len(poly)):
        xi,yi=poly[i]; xj,yj=poly[j]
        if (yi>y)!=(yj>y) and x<(xj-xi)*(y-yi)/((yj-yi) or 1e-9)+xi: inside=not inside
        j=i
    return inside

def fit_sim(P,Q):
    n=len(P); mux=sum(p[0] for p in P)/n; muy=sum(p[1] for p in P)/n
    nux=sum(q[0] for q in Q)/n; nuy=sum(q[1] for q in Q)/n
    Sxx=Sxy=den=0.0
    for (px,py),(qx,qy) in zip(P,Q):
        px-=mux;py-=muy;qx-=nux;qy-=nuy
        Sxx+=px*qx+py*qy; Sxy+=px*qy-py*qx; den+=px*px+py*py
    a=Sxx/den; b=Sxy/den
    return (a,-b, nux-a*mux+b*muy, b,a, nuy-b*mux-a*muy)
# correct-handed seed (det>0) from 3 ground-truth correspondences incl. user's
# off-axis food village/court points -- prevents the mirrored local minimum.
SEED=(-0.0293,-0.9296,3283.27, 1.3786,0.0419,-465.3)
def fit_affine(P,Q):
    # solve [a b e;c d f]: Q = A*P+t , least squares
    n=len(P); Sx=Sy=Sxx=Syy=Sxy=0.0
    Sqx=Sqy=Sxqx=Syqx=Sxqy=Syqy=0.0
    for (px,py),(qx,qy) in zip(P,Q):
        Sx+=px; Sy+=py; Sxx+=px*px; Syy+=py*py; Sxy+=px*py
        Sqx+=qx; Sqy+=qy; Sxqx+=px*qx; Syqx+=py*qx; Sxqy+=px*qy; Syqy+=py*qy
    # normal matrix for params (a,b,e) using [Sxx Sxy Sx; Sxy Syy Sy; Sx Sy n]
    M=[[Sxx,Sxy,Sx],[Sxy,Syy,Sy],[Sx,Sy,n]]
    def solve(M,r):
        import copy
        A=[row[:]+[r[i]] for i,row in enumerate(M)]
        for i in range(3):
            p=A[i][i]
            if abs(p)<1e-12:
                for k in range(i+1,3):
                    if abs(A[k][i])>1e-12: A[i],A[k]=A[k],A[i]; p=A[i][i]; break
            for k in range(3):
                if k!=i:
                    f=A[k][i]/p
                    for j in range(4): A[k][j]-=f*A[i][j]
        return [A[i][3]/A[i][i] for i in range(3)]
    a,b,e=solve(M,[Sxqx,Syqx,Sqx])
    c,d,f=solve(M,[Sxqy,Syqy,Sqy])
    return (a,b,e,c,d,f)
def apply_aff(T,pt):
    a,b,e,c,d,f=T; x,y=pt
    return (a*x+b*y+e, c*x+d*y+f)

def init_T(labels,polys):
    lx=[l['x'] for l in labels]; ly=[l['y'] for l in labels]
    px=[p['c'][0] for p in polys]; py=[p['c'][1] for p in polys]
    # axis-swap mapping from extents: SVGx ~ f(PDFy), SVGy ~ g(PDFx)
    def lin(a0,a1,b0,b1):
        s=(b1-b0)/((a1-a0) or 1e-9); return s,b0-s*a0
    sx,tx=lin(min(ly),max(ly),min(px),max(px))
    sy,ty=lin(min(lx),max(lx),min(py),max(py))
    # Q = A P + t with A=[[0,sx],[sy,0]]
    return (0.0,sx,tx, sy,0.0,ty)

import math
def fit_transform(labels,polys):
    """similarity ICP seeded with the correct-handed SEED (det>0)."""
    T=SEED
    for _ in range(20):
        pairs=[]
        for l in labels:
            mp=apply_aff(T,(l['x'],l['y']))
            h=min(polys,key=lambda p:(p['c'][0]-mp[0])**2+(p['c'][1]-mp[1])**2)
            pairs.append((l,h,math.hypot(h['c'][0]-mp[0],h['c'][1]-mp[1])))
        ds=sorted(p[2] for p in pairs); med=ds[len(ds)//2]; thr=max(35,med*2.2)
        inl=[(p[0],p[1]) for p in pairs if p[2]<thr]
        if len(inl)<6: break
        T=fit_sim([(l['x'],l['y']) for l,_ in inl],[h['c'] for _,h in inl])
    return T

def est_scale(labels,polys,T):
    """m² per SVG-unit², from labels confidently contained in a single polygon."""
    rs=[]
    for l in labels:
        if not l['m2']: continue
        mp=apply_aff(T,(l['x'],l['y']))
        cand=[p for p in polys if pip(mp,p['ring']) and p['area']>1]
        if len(cand)==1:
            rs.append(l['m2']/cand[0]['area'])
    rs.sort()
    return rs[len(rs)//2] if rs else None

def assign(labels,polys,T,near_thr=60.0):
    """Area-aware global matching. For every plausible (label, polygon) pair we
    score by distance AND agreement between the label's stated m² and the
    polygon's geometric area, then greedily assign best pairs first (each label
    and polygon used once). This stops a stray small label from claiming a big
    anchor polygon just because it falls inside it, and lets the real anchor
    label (sitting a few px outside its irregular edge) win on area+proximity."""
    k=est_scale(labels,polys,T)
    pairs=[]
    for li,l in enumerate(labels):
        mp=apply_aff(T,(l['x'],l['y']))
        for p in polys:
            d=math.hypot(p['c'][0]-mp[0],p['c'][1]-mp[1])
            contained=(p['bb'][0]-3<=mp[0]<=p['bb'][2]+3 and p['bb'][1]-3<=mp[1]<=p['bb'][3]+3
                       and pip(mp,p['ring']))
            if not contained and d>near_thr: continue
            aerr=0.0
            if k and l['m2'] and p['area']>1:
                pred=k*p['area']
                aerr=abs(pred-l['m2'])/max(l['m2'],pred)   # 0=perfect .. ~1=way off
            # a non-contained (nearest-fallback) match whose area is wildly off is
            # most likely wrong -- skip it (a missing code beats a wrong code).
            if not contained and aerr>0.6: continue
            score=(0.0 if contained else 0.5)+d/120.0+1.3*aerr
            pairs.append((score,li,p['id'],l))
    pairs.sort(key=lambda x:x[0])
    res={}; used_l=set()
    for score,li,pid,l in pairs:
        if li in used_l or pid in res: continue
        used_l.add(li); res[pid]=(l,(score,))
    return res

html=open('index.html').read()
REG={'GF':html[html.index('id="floorSvg"'):html.index('id="locMarker"')],
     'F1':html[html.index('id="unitsF1"'):html.index('</template>',html.index('id="unitsF1"'))],
     'BL':html[html.index('id="unitsBL"'):html.index('</template>',html.index('id="unitsBL"'))]}

# fit ONE shared transform on the Ground floor (most/cleanest labels) and
# apply it to every floor -- all three A0 sheets share the same plan placement.
LG=labels_of(PDFS['GF']); PG=polys_of(REG['GF'])
T=fit_transform(LG,PG)
det=T[0]*T[4]-T[1]*T[3]
out={}; rep={'T':[round(v,4) for v in T],'det':round(det,4),'scale':round(math.sqrt(abs(det)),4)}
for fl,pdf in PDFS.items():
    L=labels_of(pdf); polys=polys_of(REG[fl])
    res=assign(L,polys,T)
    fm={}
    for uid,(l,_) in res.items():
        if not l['cat']: continue
        fm[uid]={'id':l['code'],'cat':l['cat'],'m2':l['m2'],'ft2':l['ft2'],'name':l['name']}
    # De-duplicate codes: a few codes appear twice in a PDF (real unit label +
    # a stray leader annotation). Keep the larger leasing unit (by m²) -- anchors
    # / majors are what leasing locates by code; drop & log the smaller.
    bycode={}
    for uid,v in fm.items():
        bycode.setdefault(v['id'],[]).append(uid)
    dropped=[]
    for code,uids in bycode.items():
        if len(uids)<2: continue
        keep=max(uids,key=lambda u:(fm[u]['m2'] or 0))
        for u in uids:
            if u!=keep:
                dropped.append({'floor':fl,'code':code,'dropped_uid':u,
                                'kept_uid':keep,'dropped_name':fm[u]['name']})
                del fm[u]
    out[fl]=fm
    rep[fl]={'labels':len(L),'polys':len(polys),'assigned':len(fm),
             'dup_dropped':dropped,
             'cats':dict(Counter(v['cat'] for v in fm.values()))}
json.dump(out,open('/tmp/relabel.json','w'))
# committed, human-readable summary for review (the full mapping lives in
# /tmp/relabel.json and is reproducible by re-running this script).
json.dump(rep,open('tools/relabel_report.json','w'),indent=1,ensure_ascii=False)
print(json.dumps(rep,indent=2))
for uid in ('G0162','F10340','F10244','F10401','F10450'):
    for fl in out:
        if uid in out[fl]: print(uid,'=>',out[fl][uid])
