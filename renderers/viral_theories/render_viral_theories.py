#!/usr/bin/env python3
"""
render_viral_theories.py: Pillow renderer for the "5 viral theories" carousel.

Pure renderer. It NEVER writes copy: copy comes from the writer (see the
"Viral Theories Carousel: Writer Handover" doc) as the `slots` JSON on each row.

Template source: Figma "Viral Theories Carousel Template"
(yw1p6G09rkMIN6HdY5wIJ3, section 1:35). Every constant below is lifted from it:
  - canvas 1080x1920, Gotham Medium, #FBF798, letter-spacing -5%
  - slide 1: hook 90px / line-height 1.0, top 1077, centered on x=426
             sub  50px / line-height 1.0, top 1539, same center
             photo zoomed 120%, blurred + darkened, subject cut out and kept sharp
  - slides 2-6: 890px-wide block centered on the canvas; title 68px (lh 1.0),
             158px gap, body 50px (lh 1.2) with one empty line between paragraphs;
             background cover-fit and darkened

Content source
--------------
Supabase project qlcmgxgwpzmiebzxflai, table `public.viral_theories_carousel`.
One row = one carousel. The renderer reads `slots`:
  {hook_lines[4], hook_sub[2], theories[5]{title, body_1, body_2}, plug_theory, caption}
and the image pool from `public.carousel_images` (Character 6 approved set).

The renderer is the BRAIN for images: slide 1 gets a subject photo, slides 2-5
get scenery/food with no person, slide 6 gets a subject photo. Picks prefer the
images used least across the table, seeded by carousel_id so re-renders are stable.

With --upload it writes the final slides to storage
(rich-life-images/viral-theories/renders/<id>/slide_0N.jpg), then PATCHes
slide_N_url, source_images, rendered_at and status='rendered' back to the row.

Connection: CAROUSEL_SUPABASE_PROJECT / CAROUSEL_SUPABASE_SECRET_KEY via common/env.
Font: VT_FONT_PATH (default ~/Library/Fonts/Gotham-Medium.otf). Gotham is a
licensed font, so it is NOT committed to this public repo.
Brand: the row's `brand` column, else --brand, else VT_BRAND. It replaces the
literal "[brand]" token. An unresolved token blocks --upload unless
--allow-placeholder is passed.

Usage
-----
  python3 render_viral_theories.py                         # approved, not yet rendered
  python3 render_viral_theories.py --carousel VT-001 --include-unapproved
  python3 render_viral_theories.py --batch viral-theories-seed-2026-09-28 --upload
  python3 render_viral_theories.py --carousel VT-001 --all --upload --brand "Peptide Miracles"

Requires: pillow, numpy, requests, rembg, onnxruntime.
"""

import argparse
import hashlib
import io
import os
import random
import sys
from datetime import datetime, timezone

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common import env  # noqa: E402

# ---------------------------------------------------------------- template (from Figma)
CANVAS = (1080, 1920)
TEXT_COLOR = (0xFB, 0xF7, 0x98)
TRACKING = -0.05                      # letter-spacing, fraction of font size

HOOK_PX, HOOK_TOP, HOOK_CX = 90, 1077, 426
SUB_PX, SUB_TOP = 50, 1539
SIDE_MARGIN = 30                      # keep hook lines this far from the edges

S1_ZOOM = 1.2                         # photo drawn at 1296x2304 ...
S1_SHIFT = (50, -8)                   # ... nudged right 50px, top at -8 (Figma: -58, -8)
S1_BLUR = 3.5
# per-channel (gain, offset) fitted against the Figma export of slide 1
S1_BG_LEVELS = [(0.921, -34.3), (0.888, -29.3), (0.850, -24.8)]
S1_FG_LEVELS = [(0.967, -11.1), (0.917, -5.0), (0.883, -2.5)]
CUTOUT_MODEL = "u2net_human_seg"
CUTOUT_MIN, CUTOUT_MAX = 0.06, 0.75   # subject must cover this share of the frame

BLOCK_W = 890
TITLE_PX, BODY_PX, BODY_LH = 68, 50, 1.2
TITLE_BODY_GAP = 158
BLOCK_MAX_H = 1700                    # a taller block means the copy is over its limits
BG_GAIN = 0.62                        # slides 2-6: Figma darkening, measured on slides 2-3
TEXT_ZONE_MAX_LUM = 72.0              # darken further if the text zone is still brighter

JPEG_QUALITY = 92
PORTRAIT_MAX_ASPECT = 0.85            # w/h; squarer images are used only as a fallback

# ---------------------------------------------------------------- supabase
SUPABASE_PROJECT_REF = "qlcmgxgwpzmiebzxflai"
TABLE = "viral_theories_carousel"
IMAGE_TABLE = "carousel_images"
POOL_FILENAME_LIKE = "character-6-approved-%"
STORAGE_BUCKET = "rich-life-images"
RENDER_PREFIX = "viral-theories/renders"

CACHE_DIR = os.path.expanduser(env.get("VT_CACHE_DIR", "~/.cache/viral_theories"))
BRAND_TOKEN = "[brand]"
# subject slides show her alone; slide 1 prefers body-check / portrait framing
SUBJECT_EXCLUDE = ("friend", "two women", "another", "a man", "family", "group", "class",
                   "couple", "baby", "child")
HOOK_PREFER = ("mirror", "body-check", "body check", "full-body")
HOOK_AVOID = ("close", "tight", "overhead", "low-angle")   # the hook would cover her face


def _sb():
    ref = env.get("CAROUSEL_SUPABASE_PROJECT", SUPABASE_PROJECT_REF)
    # both names are in use across this repo (see .env.example)
    key = env.get("CAROUSEL_SUPABASE_SECRET_KEY") or env.require("SUPABASE_SERVICE_KEY")
    return ref, {"apikey": key, "Authorization": f"Bearer {key}"}


def _rest(path):
    ref, _ = _sb()
    return f"https://{ref}.supabase.co/rest/v1/{path}"


def fetch_rows(carousel_id=None, batch=None, include_unapproved=False, all_rows=False):
    _, h = _sb()
    params = {"select": "*", "order": "carousel_id"}
    if not include_unapproved:
        params["approved"] = "eq.true"
    if not all_rows:
        params["rendered_at"] = "is.null"
    if carousel_id:
        params["carousel_id"] = f"eq.{carousel_id}"
    if batch:
        params["batch"] = f"eq.{batch}"
    r = requests.get(_rest(TABLE), headers=h, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_pool():
    _, h = _sb()
    r = requests.get(_rest(IMAGE_TABLE), headers=h, timeout=30, params={
        "select": "id,filename,image_url,has_subject,image_type,content",
        "filename": f"like.{POOL_FILENAME_LIKE}",
    })
    r.raise_for_status()
    return [p for p in r.json() if p.get("image_url")]


def fetch_usage():
    """How many carousels already use each source image (for least-used picks)."""
    _, h = _sb()
    r = requests.get(_rest(TABLE), headers=h, timeout=30,
                     params={"select": "carousel_id,source_images", "source_images": "not.is.null"})
    r.raise_for_status()
    usage = {}
    for row in r.json():
        for url in (row.get("source_images") or {}).values():
            usage[url] = usage.get(url, 0) + 1
    return usage


def patch_row(carousel_id, payload):
    _, h = _sb()
    r = requests.patch(_rest(TABLE), timeout=30, json=payload,
                       params={"carousel_id": f"eq.{carousel_id}"},
                       headers={**h, "Content-Type": "application/json", "Prefer": "return=minimal"})
    r.raise_for_status()


def upload_slide(local_path, carousel_id, idx):
    ref, h = _sb()
    path = f"{RENDER_PREFIX}/{carousel_id}/slide_{idx:02d}.jpg"
    with open(local_path, "rb") as f:
        r = requests.post(f"https://{ref}.supabase.co/storage/v1/object/{STORAGE_BUCKET}/{path}",
                          headers={**h, "Content-Type": "image/jpeg", "x-upsert": "true"},
                          data=f.read(), timeout=60)
    r.raise_for_status()
    return f"https://{ref}.supabase.co/storage/v1/object/public/{STORAGE_BUCKET}/{path}"


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


_rembg_session = None


def load_cutout(url):
    """Subject-only RGBA of the source image (rembg), cached on disk."""
    global _rembg_session
    p = _cache_path(url, "cutout", ".png")
    if not os.path.exists(p):
        from rembg import new_session, remove
        if _rembg_session is None:
            _rembg_session = new_session(CUTOUT_MODEL)
        remove(load_image(url), session=_rembg_session).save(p)
    return Image.open(p).convert("RGBA")


def _aspect(url):
    w, h = load_image(url).size
    return w / h


def pick_images(carousel_id, pool, usage):
    """Return {slide_no: pool_item}. Least-used first, seeded by carousel_id."""
    rng = random.Random(carousel_id)

    def ranked(cands, taken, prefer=()):
        cands = [c for c in cands if c["image_url"] not in taken]
        rng.shuffle(cands)
        miss = lambda c: not any(w in (c.get("content") or "").lower() for w in prefer)
        return sorted(cands, key=lambda c: (bool(prefer) and miss(c), usage.get(c["image_url"], 0)))

    def first_fit(cands, taken, check=None, prefer=()):
        fallback = None
        for c in ranked(cands, taken, prefer):
            if check and not check(c):
                continue
            if _aspect(c["image_url"]) <= PORTRAIT_MAX_ASPECT:
                return c
            fallback = fallback or c
        return fallback

    subjects = [p for p in pool if p.get("has_subject") and p.get("image_type") == "After"
                and not any(w in (p.get("content") or "").lower() for w in SUBJECT_EXCLUDE)]
    scenery = [p for p in pool if p.get("has_subject") is False]

    def cutout_ok(c):
        if any(w in (c.get("content") or "").lower() for w in HOOK_AVOID):
            return False
        a = np.asarray(load_cutout(c["image_url"]).split()[3]) > 128
        return CUTOUT_MIN <= a.mean() <= CUTOUT_MAX

    taken, picks = set(), {}
    plan = [(1, subjects, cutout_ok, HOOK_PREFER), (6, subjects, None, ())] + \
           [(i, scenery, None, ()) for i in range(2, 6)]
    for slide, cands, check, prefer in plan:
        c = first_fit(cands, taken, check, prefer)
        if not c:
            raise RuntimeError(f"no image left in the pool for slide {slide}")
        picks[slide] = c
        taken.add(c["image_url"])
    return picks


def _levels(img, levels):
    a = np.asarray(img.convert("RGB")).astype(np.float32)
    for c, (gain, off) in enumerate(levels):
        a[..., c] = a[..., c] * gain + off
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _slide1_geometry(img):
    """Cover-fit to the canvas, then apply the Figma zoom + offset."""
    cover = ImageOps.fit(img, CANVAS, Image.LANCZOS)
    w, h = round(CANVAS[0] * S1_ZOOM), round(CANVAS[1] * S1_ZOOM)
    big = cover.resize((w, h), Image.LANCZOS)
    x = (CANVAS[0] - w) // 2 + S1_SHIFT[0]
    layer = Image.new(big.mode, CANVAS)
    layer.paste(big, (x, S1_SHIFT[1]))
    return layer


def slide1_background(url):
    src = load_image(url)
    photo = _slide1_geometry(src)
    bg = _levels(photo.filter(ImageFilter.GaussianBlur(S1_BLUR)), S1_BG_LEVELS)
    fg = _levels(photo, S1_FG_LEVELS)
    cut = load_cutout(url)
    if cut.size != src.size:
        cut = cut.resize(src.size, Image.LANCZOS)
    mask = _slide1_geometry(cut).split()[3]
    bg.paste(fg, (0, 0), mask)
    return bg


def theory_background(url):
    img = ImageOps.fit(load_image(url), CANVAS, Image.LANCZOS)
    a = np.asarray(img).astype(np.float32)
    zone = a[500:1450, 60:1020]
    lum = (zone[..., 0] * .299 + zone[..., 1] * .587 + zone[..., 2] * .114).mean()
    gain = min(BG_GAIN, TEXT_ZONE_MAX_LUM / max(lum, 1.0))
    return Image.fromarray(np.clip(a * gain, 0, 255).astype(np.uint8))


# ---------------------------------------------------------------- text
_fonts = {}


def font(px):
    if px not in _fonts:
        path = os.path.expanduser(env.get("VT_FONT_PATH", "~/Library/Fonts/Gotham-Medium.otf"))
        if not os.path.exists(path):
            raise SystemExit(f"Font not found: {path} (set VT_FONT_PATH to Gotham-Medium.otf)")
        _fonts[px] = ImageFont.truetype(path, px)
    return _fonts[px]


def text_width(text, px):
    return font(px).getlength(text) + TRACKING * px * max(len(text) - 1, 0)


def draw_line(draw, text, px, cx, top, line_h):
    """One centered line with Figma letter-spacing; glyphs centered in the line box."""
    f = font(px)
    asc, desc = f.getmetrics()
    baseline = top + (line_h - (asc + desc)) / 2 + asc
    x = cx - text_width(text, px) / 2
    track = TRACKING * px
    for i, ch in enumerate(text):
        draw.text((x + f.getlength(text[:i]) + track * i, baseline), ch,
                  font=f, fill=TEXT_COLOR, anchor="ls")


def wrap(text, px, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and text_width(trial, px) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def render_slide1(bg_url, hook_lines, hook_sub):
    img = slide1_background(bg_url)
    d = ImageDraw.Draw(img)
    widest = max(text_width(l, HOOK_PX) for l in hook_lines)
    cx = min(max(HOOK_CX, widest / 2 + SIDE_MARGIN), CANVAS[0] - widest / 2 - SIDE_MARGIN)
    for i, line in enumerate(hook_lines):
        draw_line(d, line, HOOK_PX, cx, HOOK_TOP + i * HOOK_PX, HOOK_PX)
    for i, line in enumerate(hook_sub):
        draw_line(d, line, SUB_PX, cx, SUB_TOP + i * SUB_PX, SUB_PX)
    return img


def render_theory(bg_url, theory):
    img = theory_background(bg_url)
    d = ImageDraw.Draw(img)
    title = wrap(theory["title"], TITLE_PX, BLOCK_W)
    body = wrap(theory["body_1"], BODY_PX, BLOCK_W) + [""] + wrap(theory["body_2"], BODY_PX, BLOCK_W)
    body_lh = BODY_PX * BODY_LH
    block_h = len(title) * TITLE_PX + TITLE_BODY_GAP + len(body) * body_lh
    if block_h > BLOCK_MAX_H:
        raise ValueError(f"text block is {block_h:.0f}px tall (max {BLOCK_MAX_H}): copy over limits")
    top = (CANVAS[1] - block_h) / 2
    cx = CANVAS[0] / 2
    for i, line in enumerate(title):
        draw_line(d, line, TITLE_PX, cx, top + i * TITLE_PX, TITLE_PX)
    top += len(title) * TITLE_PX + TITLE_BODY_GAP
    for i, line in enumerate(body):
        if line:
            draw_line(d, line, BODY_PX, cx, top + i * body_lh, body_lh)
    return img


# ---------------------------------------------------------------- carousel
def resolve_brand(slots, brand):
    import json
    raw = json.dumps(slots)
    if brand:
        raw = raw.replace(BRAND_TOKEN, brand)
    return json.loads(raw), BRAND_TOKEN in raw


def check_slots(s):
    assert len(s.get("hook_lines", [])) == 4, "hook_lines must have 4 lines"
    assert len(s.get("hook_sub", [])) == 2, "hook_sub must have 2 lines"
    assert len(s.get("theories", [])) == 5, "theories must have 5 items"
    for t in s["theories"]:
        assert all(t.get(k) for k in ("title", "body_1", "body_2")), f"incomplete theory: {t}"


def make_filmstrip(slides, path):
    w, h = CANVAS[0] // 4, CANVAS[1] // 4
    strip = Image.new("RGB", (w * len(slides) + 8 * (len(slides) - 1), h), (30, 30, 30))
    for i, s in enumerate(slides):
        strip.paste(s.resize((w, h), Image.LANCZOS), (i * (w + 8), 0))
    strip.save(path, quality=85)


def render_row(row, pool, usage, out_root, brand_arg, upload, allow_placeholder):
    cid = row["carousel_id"]
    slots, unresolved = resolve_brand(row["slots"], row.get("brand") or brand_arg or env.get("VT_BRAND"))
    check_slots(slots)
    if unresolved and upload and not allow_placeholder:
        raise RuntimeError(f"'{BRAND_TOKEN}' is unresolved: set the row's brand, --brand or VT_BRAND")

    picks = pick_images(cid, pool, usage)
    slides = [render_slide1(picks[1]["image_url"], slots["hook_lines"], slots["hook_sub"])]
    slides += [render_theory(picks[i + 2]["image_url"], t) for i, t in enumerate(slots["theories"])]

    out_dir = os.path.join(out_root, cid)
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, s in enumerate(slides, 1):
        p = os.path.join(out_dir, f"slide_{i:02d}.jpg")
        s.save(p, quality=JPEG_QUALITY)
        paths.append(p)
    make_filmstrip(slides, os.path.join(out_dir, "filmstrip.jpg"))
    for url in (p["image_url"] for p in picks.values()):
        usage[url] = usage.get(url, 0) + 1
    note = " (placeholder [brand] left in)" if unresolved else ""
    print(f"  ✓ {cid}: 6 slides -> {out_dir}{note}")

    if upload:
        payload = {f"slide_{i}_url": upload_slide(p, cid, i) for i, p in enumerate(paths, 1)}
        payload["source_images"] = {str(k): v["image_url"] for k, v in sorted(picks.items())}
        payload["rendered_at"] = datetime.now(timezone.utc).isoformat()
        payload["status"] = "rendered"
        patch_row(cid, payload)
        print(f"    ↳ uploaded 6 slides + wrote slide_N_url, source_images, rendered_at")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--carousel", help="one carousel_id, e.g. VT-001")
    ap.add_argument("--batch")
    ap.add_argument("--include-unapproved", action="store_true")
    ap.add_argument("--all", action="store_true", help="ignore the rendered_at IS NULL filter")
    ap.add_argument("--upload", action="store_true", help="upload renders + write back to the row")
    ap.add_argument("--brand", help="replaces the [brand] token")
    ap.add_argument("--allow-placeholder", action="store_true",
                    help="let --upload proceed with [brand] unresolved (test renders only)")
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "out"))
    a = ap.parse_args()

    rows = fetch_rows(a.carousel, a.batch, a.include_unapproved, a.all)
    if not rows:
        print("No rows to render.")
        return
    pool, usage = fetch_pool(), fetch_usage()
    print(f"{'Rendering + uploading' if a.upload else 'Rendering'} {len(rows)} carousel(s); "
          f"image pool {len(pool)}")
    failed = 0
    for row in rows:
        try:
            render_row(row, pool, usage, a.out, a.brand, a.upload, a.allow_placeholder)
        except Exception as e:  # keep going; one bad row shouldn't stop the batch
            failed += 1
            print(f"  ! {row.get('carousel_id')}: {e}")
    print(f"Done. {len(rows) - failed} rendered, {failed} failed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
