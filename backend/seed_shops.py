#!/usr/bin/env python3
"""
Seed Supabase with the existing 1,144 shops from tools/floors_3d.json.

This gives every editor the full shop inventory to browse and edit. It loads
each shop's CURRENT baked values (name, category, area) as the starting point;
the public map merges these back over the baked data, so seeding changes
nothing visible until someone actually edits a shop.

Run ONCE (re-running is safe — it upserts by id):

    export SUPABASE_URL="https://xxxx.supabase.co"
    export SUPABASE_SERVICE_KEY="<service_role key — NEVER commit this>"
    python3 backend/seed_shops.py

The service_role key bypasses Row-Level Security (that's why it's only used
here, locally, and never put in the website or committed to git).
"""
import json, os, sys, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "tools", "floors_3d.json")

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
if not URL or not KEY:
    sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables first.")


def num(v):
    """'8205' -> 8205.0 ; '' / None -> None"""
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def build_rows():
    floors = json.load(open(DATA, encoding="utf-8"))
    rows = []
    for fkey, fval in floors.items():
        for u in fval.get("units", []):
            uid = u.get("id")
            if not uid:
                continue
            rows.append({
                "id": uid,
                "floor": fkey,
                "name": (u.get("name") or "").strip(),
                "category": u.get("cat") or "",
                "area_m2": num(u.get("m2")),
                "is_published": True,
            })
    return rows


def upsert(batch):
    """POST a batch to PostgREST with upsert (merge by primary key)."""
    body = json.dumps(batch).encode("utf-8")
    req = urllib.request.Request(
        URL + "/rest/v1/shops",
        data=body,
        method="POST",
        headers={
            "apikey": KEY,
            "Authorization": "Bearer " + KEY,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    with urllib.request.urlopen(req) as r:
        return r.status


def main():
    rows = build_rows()
    print(f"Seeding {len(rows)} shops to {URL} ...")
    sent = 0
    for i in range(0, len(rows), 500):
        batch = rows[i:i + 500]
        try:
            upsert(batch)
            sent += len(batch)
            print(f"  upserted {sent}/{len(rows)}")
        except urllib.error.HTTPError as e:
            sys.exit(f"HTTP {e.code} on batch {i}: {e.read().decode('utf-8','ignore')}")
    print("Done. All shops are now editable in Supabase.")


if __name__ == "__main__":
    main()
