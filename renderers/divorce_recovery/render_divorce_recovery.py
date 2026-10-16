#!/usr/bin/env python3
"""
render_divorce_recovery.py: Pillow renderer for the Divorce Recovery carousel (Character 6).

Pure renderer. It NEVER writes copy: copy comes from the n8n writer
("Divorce Recovery: carousel copy writer", MLp2no3qGDAcDuLD) and is stored on each
row of `public.divorce_recovery_carousel` by ingest_decks.py.

Template source: Figma file y6FFRRkbtlwBD2SnZojelO, Batch 1 frames 1:2 (slide 1),
1:728 (slide 2, lock screen), 1:878, 1:885, 1:892, 1:899 (slides 3-6). Every
constant below is lifted from those frames:
  - canvas 1080x1920
  - text: TikTok Medium 70px in one white box per line, box 91px tall, boxes 85px
    apart (they overlap into one shape), radius 23, 26px side padding, black text
  - slide 2: iOS lock screen. Status bar, date (SF Pro Semibold 55), clock
    (SF Pro Rounded Semibold 264), one Messages notification card at y=554
    (x=49, w=978, radius 60, frosted dark 60%), contact photo 128px circle,
    Messages badge 51px, name 44px, "now" 33px at 50%, body 38.5px / 49.5px
    lines in a 760px column; her line in white boxes 131px below the card;
    flashlight + camera buttons, "Personal" focus, home bar.

Images, one rule per slide (the renderer is the brain for images):
  1  cover from rich-life-images/character-6/divorce-recovery-covers/manifest.json
  2  lock screen: an After photo of her alone as wallpaper + a contact photo from
     rich-life-images/divorce-recovery/contacts/
  3  After photo of her alone, NOT a selfie and NOT a close-up
  4  scenery from rich-life-images/scenery/ (no people, no food)
  5  always a Before photo
  6  After photo of her alone (selfies allowed)
Picks are distinct within a carousel, least-used across the table first (from
`source_images`), and seeded by carousel_id so a re-render gives the same picks.
After/Before photos come from `public.carousel_images` (filename character-6-*).

Text position on slides 3, 5 and 6 keeps off her face: the block sits low (ends at
y=1720) and only moves to the top slot (y=295) when the rembg person mask puts her
head in the lower half of the frame. Slides 1 and 4 always use the top slot.

Usage
-----
  python3 render_divorce_recovery.py                          # pending rows -> local preview
  python3 render_divorce_recovery.py --upload                 # pending rows -> storage + PATCH
  python3 render_divorce_recovery.py --carousel DRC-0001 --upload
  python3 render_divorce_recovery.py --batch dr-20261016 --all --upload   # re-render
  python3 render_divorce_recovery.py --deck-file deck.json --out ./out    # no database row

Connection: SUPABASE_SERVICE_KEY / CAROUSEL_SUPABASE_SECRET_KEY, or SUPABASE_ANON_KEY
(the table and the rich-life-images bucket allow the publishable key), via common/env.
Fonts: DR_FONT_PATH (default ~/Library/Fonts/TikTokDisplayMedium.otf) and
DR_SF_DIR (default /Library/Fonts) for the SF Pro files. Fonts are not committed.

Requires: pillow, numpy, requests. Optional: rembg + onnxruntime (text placement).
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

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common import env  # noqa: E402

# ---------------------------------------------------------------- template (from Figma)
W, H = 1080, 1920
JPEG_QUALITY = 92

TEXT_PX = 70
BOX_H, BOX_STEP, BOX_R, BOX_PAD = 91, 85, 23, 26
MAX_TEXT_W = 860                      # widest line in the Figma frames is 858px
TOP_SLOT = 295                        # first box top, slides 1 and 4 (and 3/5/6 when free)
BOTTOM_SLOT_END = 1720                # last box bottom when the text goes low

# slide 2: lock screen
CARD_X, CARD_Y, CARD_W, CARD_R, CARD_PAD = 49, 554, 978, 60, 33
CARD_TINT = (49, 49, 49, 153)         # #313131 at 60%
ICON_X, ICON_Y, ICON_D = 82, 587, 128
BADGE_X, BADGE_Y, BADGE_D, BADGE_R = 168, 664, 51, 11
COL_X, COL_W = 235, 760
NAME_PX, NOW_PX, BODY_PX, LINE_H = 44, 33, 38.5, 49.47
BODY_TOP = 648
CAPTION_GAP = 131                     # card bottom -> her line's first box (Figma 929 -> 1060)

# ---------------------------------------------------------------- supabase + storage
SUPABASE_PROJECT_REF = "qlcmgxgwpzmiebzxflai"
TABLE = "divorce_recovery_carousel"
IMAGE_TABLE = "carousel_images"
BUCKET = "rich-life-images"
COVER_MANIFEST = "character-6/divorce-recovery-covers/manifest.json"
SCENERY_PREFIX = "scenery/"
CONTACT_PREFIX = "divorce-recovery/contacts/"
MESSAGES_ICON = "divorce-recovery/assets/messages_icon.png"
RENDER_PREFIX = "divorce-recovery/renders"

CACHE_DIR = os.path.expanduser(env.get("DR_CACHE_DIR", "~/.cache/divorce_recovery"))
FONT_PATH = os.path.expanduser(env.get("DR_FONT_PATH", "~/Library/Fonts/TikTokDisplayMedium.otf"))
SF_DIR = os.path.expanduser(env.get("DR_SF_DIR", "/Library/Fonts"))

# her alone: anything that hints at another person in frame is out
NOT_ALONE = ("friend", "two women", "two-person", "another", "a man", "man's", "family", "group",
             "class", "couple", "baby", "child", "partner", "husband", "boyfriend", "patrons",
             "guests", "people", "both")
# slide 3: not a selfie (mirror shots are selfies), not a close-up
TOO_CLOSE = ("selfie", "mirror", "phone", "close", "tight", "face", "headshot")
WIDE_PREFER = ("full-body", "full body", "full-length", "environmental", "walk", "standing",
               "three-quarter", "portrait")
# slide 2 wallpaper: a photo that shows her, like a real lock-screen photo
WALLPAPER_PREFER = ("selfie", "portrait", "mirror", "smil", "posing", "pose")
PORTRAIT_MAX_ASPECT = 0.85            # w/h; squarer images are only a fallback


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
    params = {"select": "*", "order": "carousel_id", "limit": str(limit)}
    if not all_rows:
        params["render_status"] = "eq.pending"
    if carousel_id:
        params["carousel_id"] = f"eq.{carousel_id}"
    if batch:
        params["batch"] = f"eq.{batch}"
    r = requests.get(f"{base}/rest/v1/{TABLE}", headers=h, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_usage():
    """How many carousels already use each source image (for least-used picks)."""
    base, h = _sb()
    r = requests.get(f"{base}/rest/v1/{TABLE}", headers=h, timeout=30,
                     params={"select": "source_images", "source_images": "not.is.null"})
    r.raise_for_status()
    usage = {}

    def count(v):
        if isinstance(v, dict):
            for x in v.values():
                count(x)
        elif isinstance(v, str):
            usage[v] = usage.get(v, 0) + 1

    for row in r.json():
        count(row.get("source_images") or {})
    return usage


def list_storage(prefix):
    base, h = _sb()
    r = requests.post(f"{base}/storage/v1/object/list/{BUCKET}", headers=h, timeout=30,
                      json={"prefix": prefix, "limit": 1000, "sortBy": {"column": "name", "order": "asc"}})
    r.raise_for_status()
    names = [o["name"] for o in r.json() if re.search(r"\.(jpe?g|png|webp)$", o["name"], re.I)]
    return [_public(prefix + n) for n in names]


def fetch_pools():
    base, h = _sb()
    r = requests.get(_public(COVER_MANIFEST), timeout=30)
    r.raise_for_status()
    covers = [c["public_url"] for c in r.json()["covers"]]
    r = requests.get(f"{base}/rest/v1/{IMAGE_TABLE}", headers=h, timeout=30, params={
        "select": "image_url,has_subject,image_type,content,framing",
        "filename": "like.character-6-%", "has_subject": "eq.true"})
    r.raise_for_status()
    photos = [p for p in r.json() if p.get("image_url")]

    def text(p):
        return f"{p.get('content') or ''} {p.get('framing') or ''}".lower()

    alone = lambda p: not any(w in text(p) for w in NOT_ALONE)
    after = [p for p in photos if p.get("image_type") == "After" and alone(p)]
    pools = {
        "covers": covers,
        "after": [p["image_url"] for p in after],
        "wallpaper": [p["image_url"] for p in after if any(w in text(p) for w in WALLPAPER_PREFER)],
        "after_wide": [p["image_url"] for p in after if not any(w in text(p) for w in TOO_CLOSE)],
        "after_wide_pref": [p["image_url"] for p in after
                            if not any(w in text(p) for w in TOO_CLOSE)
                            and any(w in text(p) for w in WIDE_PREFER)],
        "before": [p["image_url"] for p in photos if p.get("image_type") == "Before" and alone(p)],
        "scenery": list_storage(SCENERY_PREFIX),
        "contacts": list_storage(CONTACT_PREFIX),
    }
    for k, v in pools.items():
        if not v and k not in ("after_wide_pref", "wallpaper"):
            raise SystemExit(f"Image pool '{k}' is empty; check storage and carousel_images.")
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


def load_image(url, mode="RGB"):
    p = _cache_path(url, "src", ".bin")
    if not os.path.exists(p):
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        with open(p, "wb") as f:
            f.write(r.content)
    return ImageOps.exif_transpose(Image.open(p)).convert(mode)


def fit(img):
    return ImageOps.fit(img, (W, H), method=Image.LANCZOS, centering=(0.5, 0.5))


def pick_images(carousel_id, pools, usage):
    """Return {"1": cover, "2": {"wallpaper", "contact"}, "3".."6": url}. Distinct, least-used."""
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
    picks["3"] = pick(pools["after_wide_pref"] or pools["after_wide"], portrait=True)
    picks["6"] = pick(pools["after"], portrait=True)
    picks["2"] = {"wallpaper": pick(pools["wallpaper"] or pools["after"], portrait=True),
                  "contact": pick(pools["contacts"])}
    picks["4"] = pick(pools["scenery"])
    picks["5"] = pick(pools["before"], portrait=True)
    return picks


# ---------------------------------------------------------------- text
def font(path, size):
    return ImageFont.truetype(path, round(size))


def sf(name, size):
    return font(os.path.join(SF_DIR, name), size)


def text_font():
    if not os.path.exists(FONT_PATH):
        raise SystemExit(f"Text font not found at {FONT_PATH}; set DR_FONT_PATH.")
    return font(FONT_PATH, TEXT_PX)


def wrap_balanced(d, text, fnt, max_width):
    """Greedy wrap, then rebalance to the narrowest width that keeps the same line count."""
    def greedy(limit):
        lines, cur = [], ""
        for word in text.split():
            t = f"{cur} {word}".strip()
            if cur and d.textlength(t, font=fnt) > limit:
                lines.append(cur)
                cur = word
            else:
                cur = t
        return lines + [cur]
    n = len(greedy(max_width))
    lo, hi = 1, max_width
    while lo < hi:
        mid = (lo + hi) // 2
        if len(greedy(mid)) <= n:
            hi = mid
        else:
            lo = mid + 1
    return greedy(hi)


def block_lines(text):
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    return wrap_balanced(d, " ".join(str(text).split()), text_font(), MAX_TEXT_W)


def block_height(n_lines):
    return BOX_H + BOX_STEP * (n_lines - 1)


def draw_block(img, text, top):
    """One white rounded box per line, hugging the line, centred; black text."""
    fnt = text_font()
    d = ImageDraw.Draw(img)
    lines = block_lines(text)
    for i, line in enumerate(lines):
        y = top + i * BOX_STEP
        w = d.textlength(line, font=fnt) + 2 * BOX_PAD
        x = (W - w) / 2
        d.rounded_rectangle((x, y, x + w, y + BOX_H), radius=BOX_R, fill="white")
    for i, line in enumerate(lines):
        d.text((W / 2, top + i * BOX_STEP + BOX_H / 2), line, font=fnt, fill="black", anchor="mm")
    return img


_rembg = None


def person_mask(img):
    """Bool HxW array of where she is, or None when rembg isn't installed."""
    global _rembg
    try:
        from rembg import new_session, remove
    except ImportError:
        return None
    if _rembg is None:
        _rembg = new_session("u2net_human_seg")
    small = img.resize((W // 4, H // 4))
    a = np.asarray(remove(small, session=_rembg).split()[3]) > 128
    return np.kron(a, np.ones((4, 4), dtype=bool))


def place_text(img, text, default="bottom"):
    """Keep the text off her face. Covering her body is fine, covering her face is not,
    and in these photos her face is almost always in the upper half, so the text goes
    low unless the person mask puts her head in the lower half. Returns the box top."""
    n = len(block_lines(text))
    slots = {"top": TOP_SLOT, "bottom": BOTTOM_SLOT_END - block_height(n)}
    mask = person_mask(img)
    if mask is None:
        return slots[default]
    rows = np.where(mask[:, 90:W - 90].mean(axis=1) > 0.02)[0]
    if not len(rows):
        return slots[default]
    head_y = rows[0] + 0.15 * (rows[-1] - rows[0])
    return slots["top"] if head_y > H * 0.55 else slots["bottom"]


# ---------------------------------------------------------------- slide 2: lock screen
def draw_tracked(d, xy_center, text, fnt, fill, tracking):
    """Centre a string with letter spacing (px) around xy_center (x, y middle)."""
    widths = [d.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = xy_center[0] - total / 2
    for ch, w in zip(text, widths):
        d.text((x, xy_center[1]), ch, font=fnt, fill=fill, anchor="lm")
        x += w + tracking


def frosted(base, box, radius, blur, tint):
    """Blur the wallpaper under `box`, tint it, round the corners and paste it back."""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    region = base.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(blur)).convert("RGBA")
    region = Image.alpha_composite(region, Image.new("RGBA", region.size, tint))
    mask = Image.new("L", region.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, x1 - x0 - 1, y1 - y0 - 1), radius=radius, fill=255)
    base.paste(region.convert("RGB"), (x0, y0), mask)


def circle(img, d):
    img = ImageOps.fit(img.convert("RGB"), (d, d), method=Image.LANCZOS)
    mask = Image.new("L", (d * 4, d * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d * 4 - 1, d * 4 - 1), fill=255)
    return img, mask.resize((d, d), Image.LANCZOS)


def status_bar(img):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((163.5, 57.5), "9:41", font=sf("SF-Pro-Display-Semibold.otf", 38.5), fill="white", anchor="mm")
    # signal: four bars in (808, 51, 47x33)
    bw, gap = 9.5, 3
    for i, frac in enumerate((0.36, 0.56, 0.78, 1.0)):
        x = 808 + i * (bw + gap)
        d.rounded_rectangle((x, 84 - 33 * frac, x + bw, 84), radius=2.5, fill="white")
    # wifi: three bands of a fan in (879, 51, 47x33), apex at the bottom middle
    cx, cy = 902.5, 86
    for r, fill in ((35, (255, 255, 255, 255)), (27, (0, 0, 0, 0)), (23, (255, 255, 255, 255)),
                    (15, (0, 0, 0, 0)), (11, (255, 255, 255, 255))):
        d.pieslice((cx - r, cy - r, cx + r, cy + r), 225, 315, fill=fill)
    # battery at (951, 49): body 69x36 r11, 40% white; level 58px; cap; "99"
    d.rounded_rectangle((951, 49, 1020, 85), radius=11, fill=(255, 255, 255, 102))
    lvl = Image.new("L", img.size, 0)
    ImageDraw.Draw(lvl).rounded_rectangle((951, 49, 1020, 85), radius=11, fill=255)
    ImageDraw.Draw(lvl).rectangle((1009, 40, 1030, 95), fill=0)
    layer.paste((255, 255, 255, 255), (0, 0), lvl)
    d.ellipse((1021, 62, 1027, 73), fill=(255, 255, 255, 102))
    d.text((985.5, 67), "99", font=sf("SF-Pro-Text-Bold.otf", 27.5), fill="black", anchor="mm")
    img.paste(layer, (0, 0), layer)


def bottom_controls(img):
    for x in (162, 797):
        frosted(img, (x, 1653, x + 121, 1774), 60.5, 30, (0, 0, 0, 51))
    d = ImageDraw.Draw(img)
    glyph = sf("SF-Pro-Rounded-Semibold.otf", 49.5)
    d.text((222.5, 1713.5), "\U0010074C", font=glyph, fill="white", anchor="mm")   # flashlight
    d.text((857.5, 1713.5), "\U0010031F", font=glyph, fill="white", anchor="mm")   # camera
    reg = sf("SF-Pro-Display-Regular.otf", 38.5)
    d.text((470, 1714), "\U0010026A", font=reg, fill="white", anchor="mm")          # person
    d.text((566, 1714), "Personal", font=reg, fill="white", anchor="mm")
    d.rounded_rectangle((356, 1887, 724, 1903), radius=8, fill="white")


def lock_clock(message_time, rng):
    m = re.match(r"\s*(\d{1,2}):(\d{2})", str(message_time or ""))
    if m:
        return f"{int(m.group(1))}:{m.group(2)}"
    return f"{rng.randint(6, 11)}:{rng.randint(0, 59):02d}"


def lock_date(rng):
    day = dt.date(2026, 1, 1) + dt.timedelta(days=rng.randint(0, 364))
    return f"{day:%A} {day.day} {day:%B}"


def render_lock_screen(row, wallpaper_url, contact_url, rng):
    img = fit(load_image(wallpaper_url))
    # keep the white chrome readable: soft darkening at the top and bottom
    shade = np.zeros((H, 1), dtype=np.float32)
    ys = np.arange(H)
    shade[:, 0] = np.clip(0.30 * (1 - ys / 700), 0, None) + np.clip(0.25 * (ys - 1500) / 420, 0, None)
    arr = np.asarray(img).astype(np.float32) * (1 - shade[:, :, None])
    img = Image.fromarray(arr.clip(0, 255).astype(np.uint8))

    status_bar(img)
    d = ImageDraw.Draw(img)
    draw_tracked(d, (540, 186), lock_date(rng), sf("SF-Pro-Display-Semibold.otf", 55),
                 (240, 240, 240), -2.75)
    draw_tracked(d, (540, 356), lock_clock(row.get("message_time"), rng),
                 sf("SF-Pro-Rounded-Semibold.otf", 264), "white", -11)

    # the notification card
    body_f = sf("SF-Pro-Display-Regular.otf", BODY_PX)
    body = wrap_greedy(d, " ".join(str(row.get("his_text") or "").split()), body_f, COL_W)
    card_h = CARD_PAD + 50 + 11 + LINE_H * len(body) + CARD_PAD
    card_h = max(card_h, CARD_PAD * 2 + ICON_D)
    frosted(img, (CARD_X, CARD_Y, CARD_X + CARD_W, CARD_Y + card_h), CARD_R, 45, CARD_TINT)
    photo, mask = circle(load_image(contact_url), ICON_D)
    img.paste(photo, (ICON_X, ICON_Y), mask)
    badge = load_image(_public(MESSAGES_ICON)).resize((BADGE_D, BADGE_D), Image.LANCZOS)
    bmask = Image.new("L", (BADGE_D * 4, BADGE_D * 4), 0)
    ImageDraw.Draw(bmask).rounded_rectangle((0, 0, BADGE_D * 4 - 1, BADGE_D * 4 - 1), radius=BADGE_R * 4, fill=255)
    img.paste(badge, (BADGE_X, BADGE_Y), bmask.resize((BADGE_D, BADGE_D), Image.LANCZOS))

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.text((COL_X, ICON_Y + 25), str(row.get("sender_name") or "").strip() or "Unknown",
            font=sf("SF-Pro-Display-Semibold.otf", NAME_PX), fill="white", anchor="lm")
    ld.text((COL_X + COL_W, ICON_Y + 25), "now", font=sf("SF-Pro-Display-Regular.otf", NOW_PX),
            fill=(255, 255, 255, 128), anchor="rm")
    for i, line in enumerate(body):
        ld.text((COL_X, BODY_TOP + i * LINE_H + LINE_H / 2), line, font=body_f,
                fill=(234, 234, 234, 255), anchor="lm")
    img.paste(layer, (0, 0), layer)

    bottom_controls(img)
    her_line = row.get("slide_2") or ""
    if her_line:
        draw_block(img, her_line, CARD_Y + card_h + CAPTION_GAP)
    return img


def wrap_greedy(d, text, fnt, width):
    lines, cur = [], ""
    for word in text.split():
        t = f"{cur} {word}".strip()
        if cur and d.textlength(t, font=fnt) > width:
            lines.append(cur)
            cur = word
        else:
            cur = t
    return lines + ([cur] if cur else [])


# ---------------------------------------------------------------- the carousel
def render_carousel(row, picks):
    rng = random.Random(row["carousel_id"] + ":lock")
    slides = {}
    s1 = fit(load_image(picks["1"]))
    slides[1] = draw_block(s1, row["slide_1"], TOP_SLOT)
    slides[2] = render_lock_screen(row, picks["2"]["wallpaper"], picks["2"]["contact"], rng)
    for n in (3, 4, 5, 6):
        img = fit(load_image(picks[str(n)]))
        top = TOP_SLOT if n == 4 else place_text(img, row[f"slide_{n}"])
        slides[n] = draw_block(img, row[f"slide_{n}"], top)
    return slides


def row_from_deck(deck, carousel_id="PREVIEW"):
    """Build a row-shaped dict from one writer deck (for --deck-file previews)."""
    s = {x["n"]: x for x in deck["slides"]}
    return {"carousel_id": carousel_id, "slide_1": s[1].get("text"), "slide_2": s[2].get("her_line"),
            "slide_3": s[3].get("text"), "slide_4": s[4].get("text"), "slide_5": s[5].get("text"),
            "slide_6": s[6].get("text"), "sender_name": s[2].get("sender_name"),
            "message_time": s[2].get("time"), "his_text": s[2].get("his_text")}


def check_row(row):
    missing = [k for k in ("slide_1", "slide_2", "slide_3", "slide_4", "slide_5", "slide_6", "his_text")
               if not str(row.get(k) or "").strip()]
    if missing:
        raise ValueError(f"missing copy: {', '.join(missing)}")
    for n in (1, 3, 4, 5, 6):
        if block_height(len(block_lines(row[f"slide_{n}"]))) > 700:
            raise ValueError(f"slide {n} text is too long for the template")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--carousel", help="one carousel_id")
    ap.add_argument("--batch", help="only rows in this batch")
    ap.add_argument("--all", action="store_true", help="include rows that are already rendered")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--upload", action="store_true", help="upload slides and PATCH the row")
    ap.add_argument("--deck-file", help="render decks from a saved writer response (no database row)")
    ap.add_argument("--out", default=os.path.join(CACHE_DIR, "out"), help="local output folder")
    args = ap.parse_args()

    pools = fetch_pools()
    if args.deck_file:
        data = json.load(open(args.deck_file))
        decks = data["decks"] if isinstance(data, dict) and "decks" in data else data
        rows = [row_from_deck(dk, f"PREVIEW-{i + 1:02d}") for i, dk in enumerate(decks)]
        usage = {}
    else:
        rows = fetch_rows(args.carousel, args.batch, args.all, args.limit)
        usage = fetch_usage()
    print(f"{len(rows)} carousel(s) to render")

    for row in rows:
        cid = row["carousel_id"]
        try:
            check_row(row)
            picks = pick_images(cid, pools, usage)
            slides = render_carousel(row, picks)
        except Exception as e:  # one bad row must not stop the batch
            print(f"  {cid}: FAILED {e}")
            if args.upload and not args.deck_file:
                patch_row(cid, {"render_status": "failed", "render_error": str(e)[:500]})
            continue
        for v in (picks["1"], picks["3"], picks["4"], picks["5"], picks["6"],
                  picks["2"]["wallpaper"], picks["2"]["contact"]):
            usage[v] = usage.get(v, 0) + 1
        if args.upload and not args.deck_file:
            urls = {f"slide_{n}_url": upload_slide(im, cid, n) for n, im in slides.items()}
            patch_row(cid, {**urls, "source_images": picks, "render_status": "rendered",
                            "status": "rendered", "render_error": None,
                            "rendered_at": dt.datetime.now(dt.timezone.utc).isoformat()})
            print(f"  {cid}: rendered and uploaded")
        else:
            out = os.path.join(args.out, cid)
            os.makedirs(out, exist_ok=True)
            for n, im in slides.items():
                im.save(os.path.join(out, f"slide_{n:02d}.jpg"), "JPEG", quality=JPEG_QUALITY)
            print(f"  {cid}: saved to {out}")


if __name__ == "__main__":
    main()
