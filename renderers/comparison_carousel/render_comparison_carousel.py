"""
render_comparison_carousel.py: Pillow renderer for the Comparison Carousel (Character 6).

Eight slides at 1080x1920 (9:16), JPG quality 90. Typography, placement, overlay and
weight labels follow the Jealousy Carousel Render Blueprint
(https://claude.ai/artifact/9CN9pvUkGhyQaiPBzNy5bb): TikTok Sans only, white text with a
drop shadow, hook centred on slide 1, story text at the bottom ending 430 px above the
edge (clear of the app's caption and buttons), a black legibility gradient, no dots, no numbers, no logos.

Copy comes from public.comparison_carousel (slide_1 = hook, slide_2..slide_8), written by the
n8n "Comparison Carousel: copy writer". The renderer never writes copy.

Weight labels (top left, 56 px from the left, 230 px from the top, "Mon YYYY Nlb"):
  slide 5 = the Before slide, slide 6 = the After slide. Only those two carry weights.
  Dates and weights come from the carousel id, so a re-render never changes them.

Images, one rule per slide (the renderer is the brain for images):
  1  cover from rich-life-images/character-6/divorce-recovery-covers/manifest.json (10 covers)
  2-4  food or atmosphere photos, and exactly one Before photo of her, in a random slot
  5  Before photo of her (carries the Before weight)
  6  After photo of her (carries the After weight)
  7-8  After photos of her
Before slide 6 she is only ever shown in Before photos. Picks are distinct inside a carousel,
least used across the table first, and seeded by carousel_id. A row that was already rendered
keeps the pictures stored in source_images, so a re-render only redraws; --repick picks again.

Usage:
  python3 render_comparison_carousel.py                        # pending rows -> local preview
  python3 render_comparison_carousel.py --upload               # pending rows -> storage + PATCH
  python3 render_comparison_carousel.py --carousel CC-0002 --all --upload
  python3 render_comparison_carousel.py --carousel CC-0002,CC-0005 --all   # several rows
  python3 render_comparison_carousel.py --batch cc-20261107 --limit 3

Needs SUPABASE_ANON_KEY (or a service key) via common/env. Requires pillow, requests.
Font: TikTok Sans variable font, path in CC_FONT_PATH
(default ~/Library/Fonts/TikTokSans[opsz,slnt,wdth,wght].ttf).
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import random
import re
import sys

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common import env  # noqa: E402

# ---------------------------------------------------------------- blueprint
W, H = 1080, 1920                # 9:16, so a reel or story shows the whole slide with no crop
JPEG_QUALITY = 90
COL_W = 912                      # 84 px side margins
BOTTOM_MARGIN = 430              # last line ends this far above the bottom edge (caption and buttons sit below)
LINE_H = 1.28
SHADOW = (0, 0, 0, 150)          # black at 59%
SHADOW_OFF = (2, 3)
OVERLAY = 0.40                   # legibility gradient strength (blueprint range 0.30 to 0.45)
OVERLAY_BOTTOM_FROM = 0.35       # gradient starts 35% down, darkest at the bottom
OVERLAY_CENTER = (0.15, 0.85)    # slide 1: darkest in the middle
HOOK = {"weight": "Bold", "size": 68, "size_long": 58, "long_over": 70}
STORY = {2: ("SemiBold", 50), 3: ("SemiBold", 50), 4: ("SemiBold", 54), 5: ("SemiBold", 54),
         6: ("SemiBold", 54), 7: ("SemiBold", 54), 8: ("SemiBold", 54)}
MAX_BLOCK_FRAC = 0.55            # shrink rule: block taller than 55% of the slide drops 3 px
MIN_SIZE = 34
LABEL = {"weight": "Bold", "size": 42, "x": 56, "y": 230}
LABEL_SLIDES = {5: "before", 6: "after"}
AFTER_RANGE = (146, 150)
LB_PER_MONTH = 7
BEFORE_MONTHS = ("2025-11", "2026-04")     # slide 5 month, inclusive
AFTER_GAP = (3, 6)                          # slide 6 is this many months after slide 5

# ---------------------------------------------------------------- supabase + storage
SUPABASE_PROJECT_REF = "qlcmgxgwpzmiebzxflai"
TABLE = "comparison_carousel"
IMAGE_TABLE = "carousel_images"
BUCKET = "rich-life-images"
COVER_MANIFEST = "character-6/divorce-recovery-covers/manifest.json"
RENDER_PREFIX = "comparison-carousel/renders"
CACHE_DIR = os.path.expanduser(env.get("CC_CACHE_DIR", "~/.cache/comparison_carousel"))
FONT_PATH = os.path.expanduser(env.get(
    "CC_FONT_PATH", "~/Library/Fonts/TikTokSans[opsz,slnt,wdth,wght].ttf"))

NOT_ALONE = ("friend", "two women", "two-person", "another", "a man", "man's", "family", "group",
             "class", "couple", "baby", "child", "partner", "husband", "boyfriend", "patrons",
             "guests", "people", "both")
PORTRAIT_MAX_ASPECT = 0.85


def _sb():
    ref = env.get("CAROUSEL_SUPABASE_PROJECT", SUPABASE_PROJECT_REF)
    key = (env.get("CAROUSEL_SUPABASE_SECRET_KEY") or env.get("SUPABASE_SERVICE_KEY")
           or env.require("SUPABASE_ANON_KEY"))
    return f"https://{ref}.supabase.co", {"apikey": key, "Authorization": f"Bearer {key}"}


def _public(path):
    base, _ = _sb()
    return f"{base}/storage/v1/object/public/{BUCKET}/{path}"


def fetch_rows(carousel_id=None, batch=None, all_rows=False, limit=50):
    base, h = _sb()
    params = {"select": "*", "order": "carousel_id", "limit": str(limit), "status": "neq.rejected"}
    if not all_rows:
        params["render_status"] = "eq.pending"
    if carousel_id:
        ids = [c.strip() for c in carousel_id.split(",") if c.strip()]
        params["carousel_id"] = f"eq.{ids[0]}" if len(ids) == 1 else "in.(%s)" % ",".join(ids)
    if batch:
        params["batch"] = f"eq.{batch}"
    r = requests.get(f"{base}/rest/v1/{TABLE}", headers=h, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_usage():
    base, h = _sb()
    r = requests.get(f"{base}/rest/v1/{TABLE}", headers=h, timeout=30,
                     params={"select": "source_images", "source_images": "not.is.null"})
    r.raise_for_status()
    usage = {}

    def count(v):
        if isinstance(v, dict):
            for x in v.values():
                count(x)
        elif isinstance(v, str) and v.startswith("http"):
            usage[v] = usage.get(v, 0) + 1

    for row in r.json():
        count(row.get("source_images") or {})
    return usage


def fetch_pools():
    base, h = _sb()
    r = requests.get(_public(COVER_MANIFEST), timeout=30)
    r.raise_for_status()
    covers = [c["public_url"] for c in r.json()["covers"]]
    r = requests.get(f"{base}/rest/v1/{IMAGE_TABLE}", headers=h, timeout=30, params={
        "select": "image_url,has_subject,image_type,content,framing",
        "filename": "like.character-6-%"})
    r.raise_for_status()
    rows = [p for p in r.json() if p.get("image_url")]
    text = lambda p: f"{p.get('content') or ''} {p.get('framing') or ''}".lower()
    alone = lambda p: not any(w in text(p) for w in NOT_ALONE)
    pools = {
        "covers": covers,
        "before": [p["image_url"] for p in rows if p.get("image_type") == "Before"
                   and p.get("has_subject") and alone(p)],
        "after": [p["image_url"] for p in rows if p.get("image_type") == "After"
                  and p.get("has_subject") and alone(p)],
        # food and atmosphere: Character 6 photos with nobody in frame; the bathroom scale shot is a Before
        "atmosphere": [p["image_url"] for p in rows if not p.get("has_subject")
                       and p.get("image_type") != "Before"],
    }
    for k, v in pools.items():
        if not v:
            raise SystemExit(f"Image pool '{k}' is empty; check carousel_images.")
    return pools


def patch_row(carousel_id, payload):
    base, h = _sb()
    r = requests.patch(f"{base}/rest/v1/{TABLE}", timeout=30, json=payload,
                       params={"carousel_id": f"eq.{carousel_id}"},
                       headers={**h, "Content-Type": "application/json", "Prefer": "return=minimal"})
    r.raise_for_status()


def upload_slide(img, carousel_id, idx):
    base, h = _sb()
    path = f"{RENDER_PREFIX}/{carousel_id}/slide_{idx:02d}.jpg"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY)
    r = requests.post(f"{base}/storage/v1/object/{BUCKET}/{path}", data=buf.getvalue(), timeout=60,
                      headers={**h, "Content-Type": "image/jpeg", "x-upsert": "true"})
    r.raise_for_status()
    return _public(path)


# ---------------------------------------------------------------- images
def _cache_path(url, kind, ext):
    d = os.path.join(CACHE_DIR, kind)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, hashlib.sha1(url.encode()).hexdigest()[:16] + ext)


def load_image(url):
    p = _cache_path(url, "src", ".bin")
    if not os.path.exists(p):
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        with open(p, "wb") as f:
            f.write(r.content)
    return ImageOps.exif_transpose(Image.open(p)).convert("RGB")


def fit(img):
    """Cover fit, centred horizontally, anchored 35% from the top so faces stay in frame."""
    return ImageOps.fit(img, (W, H), method=Image.LANCZOS, centering=(0.5, 0.35))


def pick_images(carousel_id, pools, usage):
    rng = random.Random(carousel_id)
    taken = set()

    def pick(urls, portrait=False):
        cands = [u for u in urls if u not in taken]
        rng.shuffle(cands)
        cands.sort(key=lambda u: usage.get(u, 0))
        if portrait:
            for u in cands[:12]:
                w, h = load_image(u).size
                if w / h <= PORTRAIT_MAX_ASPECT:
                    taken.add(u)
                    return u
        if not cands:
            raise SystemExit("Ran out of distinct images for a carousel; the pools are too small.")
        taken.add(cands[0])
        return cands[0]

    picks = {"1": pick(pools["covers"])}
    before_slot = rng.choice([2, 3, 4])           # one Before photo among the early slides
    for n in (2, 3, 4):
        picks[str(n)] = pick(pools["before"], portrait=True) if n == before_slot \
            else pick(pools["atmosphere"])
    picks["5"] = pick(pools["before"], portrait=True)
    picks["6"] = pick(pools["after"], portrait=True)
    picks["7"] = pick(pools["after"], portrait=True)
    picks["8"] = pick(pools["after"], portrait=True)
    return picks


# ---------------------------------------------------------------- weight labels
def month_add(ym, k):
    y, m = int(ym[:4]), int(ym[5:])
    t = y * 12 + (m - 1) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def labels_for(carousel_id):
    rng = random.Random("labels:" + carousel_id)
    months = []
    cur = BEFORE_MONTHS[0]
    while cur <= BEFORE_MONTHS[1]:
        months.append(cur)
        cur = month_add(cur, 1)
    m5 = rng.choice(months)
    gap = rng.randint(*AFTER_GAP)
    m6 = month_add(m5, gap)
    after = rng.randint(*AFTER_RANGE)
    before = after + gap * LB_PER_MONTH + rng.randint(0, 3)
    name = lambda ym: dt.date(int(ym[:4]), int(ym[5:]), 1).strftime("%b %Y")
    return {"5": f"{name(m5)} {before}lb", "6": f"{name(m6)} {after}lb"}


# ---------------------------------------------------------------- text
def font(weight, size):
    if not os.path.exists(FONT_PATH):
        raise SystemExit(f"TikTok Sans not found at {FONT_PATH}; set CC_FONT_PATH.")
    f = ImageFont.truetype(FONT_PATH, round(size))
    axes = f.get_variation_axes()
    wght = {"SemiBold": 600, "Bold": 700}[weight]
    vals = []
    for a in axes:
        n = a["name"] if isinstance(a["name"], str) else a["name"].decode()
        n = n.lower()
        if "weight" in n:
            vals.append(wght)
        elif "optical" in n:
            vals.append(min(max(round(size), a["minimum"]), a["maximum"]))
        elif "width" in n:
            vals.append(100 if a["minimum"] <= 100 <= a["maximum"] else a["default"])
        else:
            vals.append(a["default"])
    f.set_variation_by_axes(vals)
    return f


def wrap(d, text, fnt, width):
    lines, cur = [], ""
    for word in text.split():
        t = f"{cur} {word}".strip()
        if cur and d.textlength(t, font=fnt) > width:
            lines.append(cur)
            cur = word
        else:
            cur = t
    return lines + [cur]


def balanced(d, text, fnt, width):
    n = len(wrap(d, text, fnt, width))
    lo, hi = 1, width
    while lo < hi:
        mid = (lo + hi) // 2
        if len(wrap(d, text, fnt, mid)) <= n:
            hi = mid
        else:
            lo = mid + 1
    return wrap(d, text, fnt, hi)


def gradient(img, y0, y1, darkest_y=None):
    """Black gradient. Bottom text: y0..bottom, darkest at the bottom. Centre: darkest in the middle."""
    ov = Image.new("L", (1, H), 0)
    px = ov.load()
    for y in range(H):
        if darkest_y is None:
            a = 0 if y < y0 else (y - y0) / max(1, y1 - y0)
        else:
            a = 0 if (y < y0 or y > y1) else 1 - abs(y - darkest_y) / max(1, (y1 - y0) / 2)
        px[0, y] = round(255 * OVERLAY * max(0, min(1, a)))
    mask = ov.resize((W, H))
    img.paste(Image.new("RGB", (W, H), "black"), (0, 0), mask)


def draw_text(img, lines, fnt, size, center_y=None, bottom=None):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    step = size * LINE_H
    total = step * (len(lines) - 1) + size
    top = center_y - total / 2 if center_y is not None else bottom - total
    for i, line in enumerate(lines):
        w = d.textlength(line, font=fnt)
        x, y = (W - w) / 2, top + i * step
        d.text((x + SHADOW_OFF[0], y + SHADOW_OFF[1]), line, font=fnt, fill=SHADOW)
        d.text((x, y), line, font=fnt, fill=(255, 255, 255, 255))
    img.paste(layer, (0, 0), layer)


def fit_block(text, weight, size, floor=MIN_SIZE):
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    text = " ".join(str(text).split())
    while True:
        f = font(weight, size)
        lines = balanced(d, text, f, COL_W)
        if size * LINE_H * (len(lines) - 1) + size <= H * MAX_BLOCK_FRAC or size <= floor:
            return lines, f, size
        size -= 3


def render_slide(n, text, src_url, label=None):
    img = fit(load_image(src_url))
    if n == 1:
        size = HOOK["size_long"] if len(text) > HOOK["long_over"] else HOOK["size"]
        lines, f, size = fit_block(text, HOOK["weight"], size)
        gradient(img, int(H * OVERLAY_CENTER[0]), int(H * OVERLAY_CENTER[1]), H // 2)
        draw_text(img, lines, f, size, center_y=H / 2)
    else:
        weight, size = STORY[n]
        lines, f, size = fit_block(text, weight, size)
        gradient(img, int(H * OVERLAY_BOTTOM_FROM), H)
        draw_text(img, lines, f, size, bottom=H - BOTTOM_MARGIN)
    if label:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        lf = font(LABEL["weight"], LABEL["size"])
        d.text((LABEL["x"] + SHADOW_OFF[0], LABEL["y"] + SHADOW_OFF[1]), label, font=lf, fill=SHADOW)
        d.text((LABEL["x"], LABEL["y"]), label, font=lf, fill=(255, 255, 255, 255))
        img.paste(layer, (0, 0), layer)
    return img


def check_row(row):
    miss = [f"slide_{n}" for n in range(1, 9) if not str(row.get(f"slide_{n}") or "").strip()]
    if miss:
        raise ValueError("missing copy: " + ", ".join(miss))
    bad = [c for n in range(1, 9) for c in str(row[f"slide_{n}"]) if c in "&—–"]
    if bad:
        raise ValueError("ampersand or dash in the copy")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--carousel")
    ap.add_argument("--batch")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--repick", action="store_true", help="pick new pictures even if the row already has some")
    ap.add_argument("--out", default=os.path.join(CACHE_DIR, "out"))
    args = ap.parse_args()

    pools = fetch_pools()
    rows = fetch_rows(args.carousel, args.batch, args.all, args.limit)
    usage = fetch_usage()
    print(f"{len(rows)} carousel(s) to render")
    for row in rows:
        cid = row["carousel_id"]
        try:
            check_row(row)
            stored = row.get("source_images") or {}
            keep = not args.repick and all(str(stored.get(str(n)) or "").startswith("http") for n in range(1, 9))
            picks = {str(n): stored[str(n)] for n in range(1, 9)} if keep else pick_images(cid, pools, usage)
            labels = labels_for(cid)
            slides = {n: render_slide(n, row[f"slide_{n}"], picks[str(n)],
                                      labels.get(str(n)) if n in LABEL_SLIDES else None)
                      for n in range(1, 9)}
        except Exception as e:
            print(f"  {cid}: FAILED {e}")
            if args.upload:
                patch_row(cid, {"render_status": "failed", "render_error": str(e)[:500]})
            continue
        if not keep:  # kept pictures are already counted in the table
            for v in picks.values():
                usage[v] = usage.get(v, 0) + 1
        if args.upload:
            urls = {f"slide_{n}_url": upload_slide(im, cid, n) for n, im in slides.items()}
            patch_row(cid, {**urls, "source_images": {**picks, "labels": labels},
                            "render_status": "rendered", "status": "rendered", "render_error": None,
                            "rendered_at": dt.datetime.now(dt.timezone.utc).isoformat()})
            print(f"  {cid}: rendered and uploaded")
        else:
            out = os.path.join(args.out, cid)
            os.makedirs(out, exist_ok=True)
            for n, im in slides.items():
                im.save(os.path.join(out, f"slide_{n:02d}.jpg"), "JPEG", quality=JPEG_QUALITY)
            print(f"  {cid}: saved to {out}  labels {labels}")


if __name__ == "__main__":
    main()
