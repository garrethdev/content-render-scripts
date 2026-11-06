#!/usr/bin/env python3
"""Jealousy content risk gate (pipeline step 4).

Sends a batch's carousels to the n8n Content Risk Gate webhook (15 per call), then writes
gatekeep_status (high = rejected, anything else = approved), gatekeep_notes, gatekeep_reviewed_at
and quality_status = 'ok' back to jealousy_carousels.

Env:   SUPABASE_URL, SUPABASE_SERVICE_KEY or CAROUSEL_SUPABASE_SECRET_KEY (same as stitch.py,
       loaded via common/env.py)
       RISK_GATE_URL  optional, defaults to the n8n production webhook
Usage: python3 gate.py --batch jealousy_v3_2026_11_05
       python3 gate.py --batch <name> --only-unreviewed   skip rows that already have a gatekeep_status
"""
import argparse, datetime, json, os, sys, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root
from common import env  # noqa: E402

URL = (env.get("SUPABASE_URL") or "").rstrip("/")
KEY = env.get("SUPABASE_SERVICE_KEY") or env.get("CAROUSEL_SUPABASE_SECRET_KEY") or ""
GATE = env.get("RISK_GATE_URL", "https://czed.app.n8n.cloud/webhook/content-risk-gate")
CHUNK = 15


def call(url, method="GET", body=None, headers=None):
    h = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=300) as r:
        t = r.read()
        return json.loads(t) if t else None


def sb(path, method="GET", body=None, extra=None):
    h = {"apikey": KEY, "Authorization": "Bearer " + KEY}
    h.update(extra or {})
    return call(URL + path, method, body, h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--only-unreviewed", action="store_true")
    args = ap.parse_args()
    if not URL or not KEY:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY first.")

    q = ("select=id,carousel_id,caption,slide_1,slide_2,slide_3,slide_4,slide_5,slide_6"
         "&render_status=eq.rendered&batch=eq." + urllib.parse.quote(args.batch))
    if args.only_unreviewed:
        q += "&gatekeep_status=is.null"
    rows = sb("/rest/v1/jealousy_carousels?" + q)
    print("%d row(s) to gate" % len(rows))
    if not rows:
        return
    by_cid = {r["carousel_id"]: r for r in rows}
    items = [{"type": "jealousy_carousel", "content_id": r["carousel_id"], "caption": r["caption"] or "",
              "text_hook": r["slide_1"] or "", "transcript": "",
              "on_screen_text": " \n ".join(r["slide_%d" % i] or "" for i in range(1, 7))} for r in rows]

    counts = {}
    for k in range(0, len(items), CHUNK):
        res = call(GATE, "POST", {"items": items[k:k + CHUNK]})
        print("gate call %d: %s" % (k // CHUNK + 1, res.get("summary")))
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for v in res.get("results", []):
            row = by_cid.get(v.get("content_id"))
            if not row:
                continue
            lvl = v.get("risk_level", "unknown")
            counts[lvl] = counts.get(lvl, 0) + 1
            notes = "risk %s: %s" % (lvl, v.get("llm_reasons") or "")
            if v.get("violations"):
                notes += " | violations: " + json.dumps(v["violations"])
            patch = {"gatekeep_status": "rejected" if lvl == "high" else "approved", "gatekeep_notes": notes,
                     "gatekeep_reviewed_at": now, "quality_status": "ok"}
            sb("/rest/v1/jealousy_carousels?id=eq." + row["id"], "PATCH", patch, {"Prefer": "return=minimal"})
    print("risk levels:", counts)


if __name__ == "__main__":
    main()
