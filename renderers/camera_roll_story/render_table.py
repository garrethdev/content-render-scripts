"""
render_table.py: table mode for the Camera Roll Story renderer.

Reads decks from public.camera_roll_story_carousel, renders them with render_camera_roll_story.py and
pictures.py, and with --upload saves the slides to storage and marks the row rendered.

  python3 render_table.py                      # pending rows -> ./out/<carousel_id>/ (nothing saved)
  python3 render_table.py --upload             # pending rows -> storage + PATCH
  python3 render_table.py --carousel CRS-0003 --all --upload     # one row again, same pictures
  python3 render_table.py --carousel CRS-0003 --all --repick --upload

The photo list is pulled fresh from carousel_images on every run and only rows stored under
rich-life-images/character-6/ are used (Garreth, 2026-11-19); see load_pool in the renderer. A row that already has source_images
keeps its pictures unless --repick, but a kept picture that has since been deleted stops that deck.

Keys are read through common/env: CAROUSEL_SUPABASE_SECRET_KEY or SUPABASE_SERVICE_KEY for --upload
(storage writes), otherwise SUPABASE_ANON_KEY is enough to read.
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

import pictures as P
import render_camera_roll_story as R

BASE = R.supabase()[0]
TABLE = "camera_roll_story_carousel"
BUCKET = "rich-life-images"
RENDER_PREFIX = "camera-roll-story/renders"
HERE = os.path.dirname(os.path.abspath(__file__))


def key():
    return R.supabase()[1]


def api(method, path, body=None, headers=None):
    h = {"apikey": key(), "Authorization": "Bearer " + key(), "User-Agent": "carousel-renderer"}
    h.update(headers or {})
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    return json.loads(raw) if raw and raw[:1] in b"[{" else raw


def fetch_rows(args):
    p = {"select": "*", "order": "carousel_id", "limit": str(args.limit)}
    if not args.all:
        p["render_status"] = "eq.pending"
    if args.carousel:
        p["carousel_id"] = "in.(%s)" % ",".join(c.strip() for c in args.carousel.split(","))
    if args.batch:
        p["batch"] = "eq." + args.batch
    return api("GET", f"/rest/v1/{TABLE}?{urllib.parse.urlencode(p)}")


def as_story(row):
    deck = row.get("deck") or {}
    n = deck.get("story_no") or int(re.sub(r"\D", "", row["carousel_id"]) or 0)
    s = {"id": n, "slides": [row.get(f"slide_{i}") or "" for i in range(1, 9)], "shots": deck.get("shots") or []}
    if deck.get("reveal_from"):
        s["reveal_from"] = deck["reveal_from"]
    return s


def upload(img, cid, n):
    path = f"{RENDER_PREFIX}/{cid}/slide_{n:02d}.jpg"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=R.JPEG_QUALITY)
    api("POST", f"/storage/v1/object/{BUCKET}/{path}", buf.getvalue(),
        {"Content-Type": "image/jpeg", "x-upsert": "true"})
    return f"{BASE}/storage/v1/object/public/{BUCKET}/{path}"


def patch(cid, payload):
    api("PATCH", f"/rest/v1/{TABLE}?carousel_id=eq.{cid}", json.dumps(payload).encode(),
        {"Content-Type": "application/json", "Prefer": "return=minimal"})


def main():
    ap = argparse.ArgumentParser(description="Render Camera Roll Story decks from the table.")
    ap.add_argument("--carousel")
    ap.add_argument("--batch")
    ap.add_argument("--all", action="store_true", help="include rows that are already rendered")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--repick", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    args = ap.parse_args()

    pool = R.load_pool()
    rows = fetch_rows(args)
    print(f"{len(rows)} deck(s) to render, {len(pool)} photos in the library")
    usage, plans = {}, {}
    for row in rows:                                    # plan the whole batch first so photos are shared fairly
        cid = row["carousel_id"]
        try:
            s = as_story(row)
            R.check_story(s)
            kept = row.get("source_images") or {}
            if kept and not args.repick:
                picks = {int(n): (v["photo_id"], v.get("shot", ""), "") for n, v in kept.items()}
                gone = [pid for pid, _, _ in picks.values() if pid not in pool]
                if gone:
                    raise ValueError(f"kept pictures no longer in the library: {gone}; run with --repick")
                for pid, _, _ in picks.values():
                    usage[pid] = usage.get(pid, 0) + 1
            else:
                picks = R.pick_story(s, pool, usage)
            plans[cid] = (s, picks)
        except (Exception, SystemExit) as e:
            print(f"  {cid}: FAILED {e}")
            if args.upload:
                patch(cid, {"render_status": "failed", "render_error": str(e)[:500]})
    for cid, (s, picks) in plans.items():
        try:
            imgs = {n: R.render_slide(n, s["slides"][n - 1], R.load_image(pool[pid]["image_url"]), seed=cid)
                    for n, (pid, _, _) in picks.items()}
            assert all(im.size == (R.W, R.H) for im in imgs.values())
        except (Exception, SystemExit) as e:
            print(f"  {cid}: FAILED {e}")
            if args.upload:
                patch(cid, {"render_status": "failed", "render_error": str(e)[:500]})
            continue
        src = {str(n): {"photo_id": pid, "shot": shot, "url": pool[pid]["image_url"]} for n, (pid, shot, _) in picks.items()}
        if args.upload:
            urls = {f"slide_{n}_url": upload(im, cid, n) for n, im in imgs.items()}
            patch(cid, {**urls, "source_images": src, "render_status": "rendered", "status": "rendered",
                        "render_error": None, "rendered_at": dt.datetime.now(dt.timezone.utc).isoformat()})
            print(f"  {cid}: rendered and uploaded")
        else:
            out = os.path.join(args.out, cid)
            os.makedirs(out, exist_ok=True)
            for n, im in imgs.items():
                im.save(os.path.join(out, f"slide_{n:02d}.jpg"), "JPEG", quality=R.JPEG_QUALITY)
            json.dump(src, open(os.path.join(out, "picks.json"), "w"), indent=1)
            print(f"  {cid}: saved to {out}")


if __name__ == "__main__":
    main()
