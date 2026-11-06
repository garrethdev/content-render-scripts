#!/usr/bin/env python3
"""Jealousy Director Stitch.

Takes jealousy_carousels rows the n8n director has finished (status = 'directed',
render_status empty), renders the 6 slides to the blueprint, uploads them to the
public rich-life-images bucket and writes the slide URLs back to the row.

Needs: Python 3.9+, Pillow (pip install -r requirements.txt).
Env (via common/env.py, i.e. ~/.config/peptide-secrets/.env or the repo .env):
       SUPABASE_URL          e.g. https://qlcmgxgwpzmiebzxflai.supabase.co
       SUPABASE_SERVICE_KEY  service role (secret) key, or CAROUSEL_SUPABASE_SECRET_KEY.
                             The publishable key cannot see jealousy_carousels (RLS, no policies).

Usage:
  python3 stitch.py --batch jealousy_v3 --limit 25            render, upload, update rows
  python3 stitch.py --batch jealousy_v3 --limit 3 --dry-run   render to ./out only, touch nothing
  python3 stitch.py --ids <row uuid>,<row uuid>               specific rows
"""
import argparse, hashlib, json, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))  # repo root, for common/
from common import env  # noqa: E402
import renderer  # noqa: E402

URL = (env.get("SUPABASE_URL") or "").rstrip("/")
KEY = env.get("SUPABASE_SERVICE_KEY") or env.get("CAROUSEL_SUPABASE_SECRET_KEY") or ""
BUCKET = "rich-life-images"
BP = renderer.BP

def api(method, path, body=None, headers=None, raw=False):
    h = {"apikey": KEY, "Authorization": "Bearer " + KEY}
    h.update(headers or {})
    data = body if raw else (json.dumps(body).encode() if body is not None else None)
    if body is not None and not raw:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(URL + path, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=120) as r:
        t = r.read()
        return json.loads(t) if t and not raw else t

def get_rows(args):
    q = "select=id,source_id,carousel_id,batch,slides,directing,status,render_status&status=eq.directed&render_status=is.null&order=created_at.asc"
    if args.ids:
        q = "select=id,source_id,carousel_id,batch,slides,directing,status,render_status&id=in.(%s)" % args.ids
    elif args.batch:
        q += "&batch=eq." + urllib.parse.quote(args.batch)
    if args.limit:
        q += "&limit=%d" % args.limit
    return api("GET", "/rest/v1/jealousy_carousels?" + q)

def labels_for(cid):
    # Same dating and weight labels as the blueprint, derived from the carousel id so reruns are stable.
    import datetime
    hv = int(hashlib.md5(cid.encode()).hexdigest(), 16); LD = BP["label_dates"]
    y0, m0 = map(int, LD["before_start"].split("-")); y1, m1 = map(int, LD["before_end"].split("-"))
    span = (y1 * 12 + m1) - (y0 * 12 + m0); bi = y0 * 12 + (m0 - 1) + hv % (span + 1)
    g0, g1 = LD["gap_months"]; gap = g0 + (hv >> 12) % (g1 - g0 + 1); ai = bi + gap
    bdate = datetime.date(bi // 12, bi % 12 + 1, 1); adate = datetime.date(ai // 12, ai % 12 + 1, 1)
    lo, hi = BP["slides"]["6"]["label_range"]; after_w = lo + (hv >> 24) % (hi - lo + 1)
    j0, j1 = LD["loss_jitter_lb"]; before_w = after_w + gap * LD["loss_per_month_lb"] + j0 + (hv >> 32) % (j1 - j0 + 1)
    return {5: BP["slides"]["5"]["label"].format(date=bdate.strftime(LD["format"]), n=before_w),
            6: BP["slides"]["6"]["label"].format(date=adate.strftime(LD["format"]), n=after_w)}

def check(row):
    s, d = row.get("slides") or [], (row.get("directing") or {}).get("slides") or []
    if len(s) != 6 or len(d) != 6:
        return "needs 6 slides and 6 directed images"
    for k in range(6):
        if not d[k].get("image_url"):
            return "slide %d has no image_url" % (k + 1)
        if not s[k].get("text"):
            return "slide %d has no text" % (k + 1)
    return None

def render_row(row, cid, outdir):
    s, d = row["slides"], row["directing"]["slides"]
    lab = labels_for(cid); paths = []
    os.makedirs(outdir, exist_ok=True)
    for k in range(6):
        im = renderer.render_slide(d[k]["image_url"], s[k]["text"], d[k].get("text_position"), d[k].get("text_color"),
                                   d[k].get("text_size"), float(d[k].get("overlay_opacity") or 0.4), d[k].get("blur_box"), k + 1, lab.get(k + 1))
        p = os.path.join(outdir, "slide%d.jpg" % (k + 1))
        im.save(p, "JPEG", quality=BP["canvas"]["jpg_quality"]); paths.append(p)
    return paths

def upload(cid, paths):
    urls = []
    for i, p in enumerate(paths, 1):
        obj = "jealousy/%s/slide%d.jpg" % (cid, i)
        api("POST", "/storage/v1/object/%s/%s" % (BUCKET, obj), open(p, "rb").read(),
            {"Content-Type": "image/jpeg", "x-upsert": "true"}, raw=True)
        urls.append("%s/storage/v1/object/public/%s/%s" % (URL, BUCKET, obj))
    return urls

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch"); ap.add_argument("--limit", type=int); ap.add_argument("--ids")
    ap.add_argument("--out", default=os.path.join(HERE, "out")); ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not URL or not KEY:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY first.")
    rows = get_rows(args)
    print("%d row(s) to stitch" % len(rows))
    done = bad = 0
    for row in rows:
        why = check(row)
        if why:
            print("SKIP", row["id"], why); bad += 1; continue
        cid = row.get("carousel_id") or "%s-%s" % (row["source_id"], row["id"][:6])
        try:
            paths = render_row(row, cid, os.path.join(args.out, cid))
            if args.dry_run:
                print("dry run ok", cid, os.path.join(args.out, cid)); done += 1; continue
            urls = upload(cid, paths)
            patch = {"carousel_id": cid, "render_status": "rendered", "status": "rendered",
                     "rendered_at": "now()"}
            patch = {k: v for k, v in patch.items() if k != "rendered_at"}
            patch["rendered_at"] = __import__("datetime").datetime.utcnow().isoformat() + "Z"
            if args.batch and not row.get("batch"):
                patch["batch"] = args.batch
            for i, u in enumerate(urls, 1):
                patch["slide_%d_url" % i] = u
            api("PATCH", "/rest/v1/jealousy_carousels?id=eq." + row["id"], patch, {"Prefer": "return=minimal"})
            print("stitched", cid); done += 1
        except Exception as e:
            print("FAIL", row["id"], e); bad += 1
    print("done %d, skipped or failed %d" % (done, bad))

if __name__ == "__main__":
    main()
