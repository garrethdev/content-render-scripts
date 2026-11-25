"""
render_womens_complaints.py: render agent for the Women's Complaints carousel lane (Character 6).

Reads decks from public.womens_complaints_carousel, picks the pictures, renders eight 1080x1920 slides in the
Camera Roll Story look (shared Character 6 text from common/slide_text.py), and with --upload saves them to
storage and marks the row rendered.

  python3 render_womens_complaints.py                      # pending rows -> ./out/<carousel_id>/ (nothing saved)
  python3 render_womens_complaints.py --plan               # print the picture picks, render nothing
  python3 render_womens_complaints.py --upload             # pending rows -> storage + PATCH
  python3 render_womens_complaints.py --carousel WC-0003 --all --upload            # one row again, same pictures
  python3 render_womens_complaints.py --carousel WC-0003 --all --repick --upload   # one row again, new pictures
  python3 render_womens_complaints.py --upload-complaint-photos DIR               # put the slide 1 photos in storage

Picture rules (Garreth, 2026-11-25; he asked that "or" and "and" be read as written):
  slide 1     one of the complaint photos he approved on the photo page (COMPLAINT_PHOTOS below), stored under
              rich-life-images/womens-complaints/complaint-photos/. The hook sits away from the body part (CENTER).
  slides 2-6  nature OR a photo tagged "before" AND "old". One or two nature slides at random among 3 to 6.
  slides 7-8  the reveal: photos tagged "after" AND "old".
Tags come from public.v_character6_picture_pool, read fresh on every run: active rows of jealousy_image_pool under
rich-life-images/character-6/ whose file still exists in storage. Nothing outside that folder is ever used for
slides 2 to 8. Nature = no person in the photo, described as scenery (garden, field, sky, beach ...), no food, no
kitchen. No picture repeats inside a deck; across a run the least used picture goes first.
Text is straight on every slide (no shift, no tilt).

Keys come through common/env: SUPABASE_ANON_KEY is enough for everything here (the table and both storage
folders are open to it, like Camera Roll Story).
"""
import argparse
import datetime as dt
import io
import json
import os
import random
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "camera_roll_story"))
import render_camera_roll_story as R  # noqa: E402  (the look: fit_block, tint, gradient, draw_text, fonts)

from PIL import Image, ImageOps  # noqa: E402

ST = R.ST
TABLE = "womens_complaints_carousel"
POOL_VIEW = "v_character6_picture_pool"
BUCKET = "rich-life-images"
RENDER_PREFIX = "womens-complaints/renders"
COMPLAINT_PREFIX = "womens-complaints/complaint-photos"

# Approved on https://claude.ai/artifact/7FRJMeHisPZiSLxc7CPMaq (votes, 2026-11-25). BL26 has no vote; it is his
# reference look for belly ("I want more image like BL26") and was used in the first hook render he saw.
COMPLAINT_PHOTOS = {
    "arms": ["UA15", "UA12z", "UA13c", "UA10", "LS02", "LS03", "LS09", "UA03", "UA05"],
    "chin": ["DC21", "DC22", "DC15", "DC16", "DC18", "DC12", "DC03"],
    "belly": ["BL17b", "BL26"],
}
# Where the hook's centre sits on each complaint photo, as a share of the height, away from the body part.
CENTER = {"UA15": .68, "UA12z": .68, "UA13c": .72, "UA10": .70, "LS02": .62, "LS03": .68, "LS09": .65, "UA03": .68, "UA05": .72,
          "DC21": .70, "DC22": .70, "DC15": .70, "DC16": .70, "DC18": .70, "DC12": .68, "DC03": .70, "BL17b": .40, "BL26": .52}

NATURE = re.compile(r"\b(garden|field|sky|clouds|beach|sea|ocean|trees?|leaves|vines|lane|bougainvillea|flowers?|park|lake|sunset|meadow|hills?)\b", re.I)
NOT_NATURE = re.compile(r"\b(kitchen|plate|bowl|cake|pasta|soup|dessert|burger|salad|cutlet|ribs|casserole|pastries|meat|eggs|jar|tongs|dish|bars|sandwich|platter|skewers|lunch|dinner)\b", re.I)


def base_key():
    return R.supabase()


def api(method, path, body=None, headers=None):
    base, key = base_key()
    h = {"apikey": key, "Authorization": "Bearer " + key, "User-Agent": "carousel-renderer"}
    h.update(headers or {})
    req = urllib.request.Request(base + path, data=body, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    return json.loads(raw) if raw and raw[:1] in b"[{" else raw


def public_url(path):
    return f"{base_key()[0]}/storage/v1/object/public/{BUCKET}/{urllib.parse.quote(path)}"


def load_pools():
    """Fresh from the view on every run. Each pool follows his tags exactly."""
    rows = api("GET", f"/rest/v1/{POOL_VIEW}?select=*")
    rows = [r for r in rows if r.get("url") and R.LIBRARY in r["url"]]
    pools = {
        "before_old": [r for r in rows if r["stage"] == "before" and r["age_group"] == "old"],
        "nature": [r for r in rows if not r["her_in_photo"] and NATURE.search(r["what"] or "") and not NOT_NATURE.search(r["what"] or "")],
        "after_old": [r for r in rows if r["stage"] == "after" and r["age_group"] == "old"],
    }
    for k, v in pools.items():
        assert v, f"picture pool {k} is empty"
    return pools, {r["storage_path"] for r in rows}


USED = Counter()


def pick(pool, taken, rng):
    free = [r for r in pool if r["storage_path"] not in taken]
    assert free, "picture pool ran out"
    low = min(USED[r["storage_path"]] for r in free)
    r = rng.choice([r for r in free if USED[r["storage_path"]] == low])
    USED[r["storage_path"]] += 1
    taken.add(r["storage_path"])
    return r


def plan_row(row, k, pools):
    """Eight picks: [{'kind', 'path'}]. slide 1 is a complaint photo id, the rest are library storage paths."""
    rng = random.Random(row["carousel_id"])
    pics = COMPLAINT_PHOTOS[row["complaint"]]
    plan = [{"kind": "complaint", "path": f"{COMPLAINT_PREFIX}/{pics[k % len(pics)]}.jpg", "id": pics[k % len(pics)]}]
    nature_at = set(rng.sample([3, 4, 5, 6], rng.choice([1, 2])))
    taken = set()
    for n in range(2, 7):
        kind = "nature" if n in nature_at else "before_old"
        plan.append({"kind": kind, "path": pick(pools[kind], taken, rng)["storage_path"]})
    for _ in (7, 8):
        plan.append({"kind": "after_old", "path": pick(pools["after_old"], taken, rng)["storage_path"]})
    return plan


def slide_one(text, src, center):
    img = ImageOps.fit(src, (R.W, R.H), method=Image.LANCZOS, centering=(0.5, 0.35))
    img = R.tint(img)
    size = R.HOOK["size_long"] if len(text) > R.HOOK["long_over"] else R.HOOK["size"]
    lines, f, size = R.fit_block(text, R.HOOK["weight"], size)
    cy = R.H * center
    R.gradient(img, int(cy - R.H * 0.2), int(cy + R.H * 0.2), int(cy))
    R.draw_text(img, lines, f, size, center_y=cy, place=ST.NO_MOVE)
    return img


def story_slide(text, src):
    img = ImageOps.fit(src, (R.W, R.H), method=Image.LANCZOS, centering=(0.5, 0.35))
    img = R.tint(img)
    lines, f, size = R.fit_block(text, *R.STORY_FONT)
    R.gradient(img, int(R.H * R.OVERLAY_BOTTOM_FROM), R.H)
    R.draw_text(img, lines, f, size, bottom=R.H - R.BOTTOM_MARGIN, place=ST.NO_MOVE)
    return img


def load_src(p):
    if p["kind"] == "complaint":
        url = public_url(p["path"])
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "carousel-renderer"}), timeout=60) as r:
            return Image.open(io.BytesIO(r.read())).convert("RGB")
    return R.load_image(public_url(p["path"]))   # asserts the Character 6 folder and that the file still exists


def upload(img, cid, n):
    path = f"{RENDER_PREFIX}/{cid}/slide_{n:02d}.jpg"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=R.JPEG_QUALITY)
    api("POST", f"/storage/v1/object/{BUCKET}/{path}", buf.getvalue(), {"Content-Type": "image/jpeg", "x-upsert": "true"})
    return public_url(path)


def upload_complaint_photos(folder):
    names = {i for v in COMPLAINT_PHOTOS.values() for i in v}
    for f in sorted(os.listdir(folder)):
        pid = f.rsplit(".", 1)[0]
        if pid not in names:
            continue
        data = open(os.path.join(folder, f), "rb").read()
        api("POST", f"/storage/v1/object/{BUCKET}/{COMPLAINT_PREFIX}/{pid}.jpg", data, {"Content-Type": "image/jpeg", "x-upsert": "true"})
        print("uploaded", pid)
        names.discard(pid)
    if names:
        raise SystemExit("missing complaint photos: " + ", ".join(sorted(names)))


def main():
    ap = argparse.ArgumentParser(description="Render Women's Complaints decks.")
    ap.add_argument("--carousel", help="comma list of carousel ids")
    ap.add_argument("--batch")
    ap.add_argument("--all", action="store_true", help="include rows already rendered")
    ap.add_argument("--repick", action="store_true", help="pick new pictures even when the row has some")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--upload-complaint-photos", metavar="DIR")
    args = ap.parse_args()
    if args.upload_complaint_photos:
        return upload_complaint_photos(args.upload_complaint_photos)

    p = {"select": "*", "order": "carousel_id", "limit": str(args.limit)}
    if not args.all:
        p["render_status"] = "eq.pending"
    if args.carousel:
        p["carousel_id"] = "in.(%s)" % ",".join(c.strip() for c in args.carousel.split(","))
    if args.batch:
        p["batch"] = "eq." + args.batch
    rows = api("GET", f"/rest/v1/{TABLE}?{urllib.parse.urlencode(p)}")
    print(len(rows), "rows")
    pools, live = load_pools()
    print({k: len(v) for k, v in pools.items()})
    seen = Counter()
    for row in rows:
        k = seen[row["complaint"]]; seen[row["complaint"]] += 1
        kept = row.get("source_images")
        if kept and not args.repick:
            gone = [x["path"] for x in kept[1:] if x["path"] not in live]
            if gone:
                print(row["carousel_id"], "keeps pictures no longer in the library, render with --repick:", gone); continue
            plan = kept
        else:
            plan = plan_row(row, k, pools)
        print(row["carousel_id"], row["complaint"], [x["kind"] for x in plan])
        if args.plan:
            continue
        texts = [row.get(f"slide_{n}") or "" for n in range(1, 9)]
        assert all(t.strip() for t in texts), f"{row['carousel_id']}: empty slide"
        urls, out_dir = [], os.path.join(args.out, row["carousel_id"])
        os.makedirs(out_dir, exist_ok=True)
        try:
            for n, (t, pk) in enumerate(zip(texts, plan), 1):
                src = load_src(pk)
                img = slide_one(t, src, CENTER[pk["id"]]) if n == 1 else story_slide(t, src)
                img.save(os.path.join(out_dir, f"slide_{n:02d}.jpg"), "JPEG", quality=R.JPEG_QUALITY)
                if args.upload:
                    urls.append(upload(img, row["carousel_id"], n))
        except Exception as e:  # noqa: BLE001
            print(row["carousel_id"], "failed:", e)
            if args.upload:
                api("PATCH", f"/rest/v1/{TABLE}?carousel_id=eq.{row['carousel_id']}",
                    json.dumps({"render_status": "failed", "render_error": str(e)[:500]}).encode(), {"Content-Type": "application/json", "Prefer": "return=minimal"})
            continue
        if args.upload:
            patch = {f"slide_{n}_url": u for n, u in enumerate(urls, 1)}
            patch.update({"source_images": plan, "render_status": "rendered", "rendered_at": dt.datetime.now(dt.timezone.utc).isoformat(), "render_error": None})
            api("PATCH", f"/rest/v1/{TABLE}?carousel_id=eq.{row['carousel_id']}", json.dumps(patch).encode(),
                {"Content-Type": "application/json", "Prefer": "return=minimal"})
            print(row["carousel_id"], "rendered and saved")


if __name__ == "__main__":
    main()
