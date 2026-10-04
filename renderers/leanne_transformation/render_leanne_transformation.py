#!/usr/bin/env python3
"""
render_leanne_transformation.py — carousel renderer for Character 6 (Leanne)
weight-loss / anti-aging TRANSFORMATION-REVEAL carousels for women over 40.

Pure renderer. It burns the PRE-APPROVED, already-humanized copy onto each slide
over a LANDSCAPE background. It NEVER writes copy: copy comes from the 3-call
writer (hook -> body -> humanizer) and is stored in `leanne_transformation_carousel`
(see Obsidian Frameworks/Leanne Carousel - Writer Prompts + Leanne Humanizer - Wrapper).

Backgrounds: the emphasis is the landscape / no-person images ALREADY in
`carousel_images`. The renderer is the brain: for any slide with no slide_N_url
set, it picks a no-subject landscape image from carousel_images, preferring the
pre-darkened version (`darkened_image`) so white text stays legible. Picks are
distinct within a carousel and seeded by carousel_id, so a given carousel is
stable across re-renders. An existing slide_N_url is respected (so slide 6 can
later carry a real before/after reveal photo without the brain overwriting it).

Content source (Supabase project qlcmgxgwpzmiebzxflai, story-finder):
  leanne_transformation_carousel
    slide_1..slide_6         -> caption copy per slide (slide_1 = hook + sub)
    slide_1_url..slide_6_url -> image per slide (public URL; empty => brain picks)
    approved (bool), status, rendered_at, source_images, carousel_id
  carousel_images            -> background pool (has_subject=false landscapes)

Connection from ~/.config/peptide-secrets/.env:
  CAROUSEL_SUPABASE_PROJECT, CAROUSEL_SUPABASE_SECRET_KEY

Usage
-----
  # render every approved, not-yet-rendered carousel, upload + stamp rendered
  python3 render_leanne_transformation.py --supabase --upload
  python3 render_leanne_transformation.py --supabase --carousel LEA-B1-10        # one row
  python3 render_leanne_transformation.py --supabase --all                       # ignore rendered_at
  python3 render_leanne_transformation.py --supabase --include-unapproved        # before approval (test)
  python3 render_leanne_transformation.py --supabase --carousel LEA-B1-10 --include-unapproved
         # ^ local render only (no --upload): writes PNGs + filmstrip to ./out/<id>/, touches nothing
"""

import io
import os
import sys
import random

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

# ---------------------------------------------------------------- config
SF_FONT_PATH = "/System/Library/Fonts/SFNS.ttf"
SF_VARIATION = "Bold"
DEFAULT_CANVAS = (1080, 1350)             # 4:5 IG carousel feed ratio

SUPABASE_PROJECT_REF = "qlcmgxgwpzmiebzxflai"
TABLE = "leanne_transformation_carousel"
IMAGE_TABLE = "carousel_images"
STORAGE_BUCKET = "leanne-carousel-images"
RENDER_PREFIX = "renders"
SECRETS_ENV = os.path.expanduser("~/.config/peptide-secrets/.env")

SLIDE_COPY_COLS = [f"slide_{i}" for i in range(1, 7)]
SLIDE_URL_COLS = [f"slide_{i}_url" for i in range(1, 7)]

# Caption look (fractions of canvas, so it scales with size).
CAP_FONT_FRAC = 0.045        # Leanne copy is short; slightly larger than covered_eye
CAP_MARGIN_X_FRAC = 0.08
CAP_LINE_SPACING = 1.14
SHADOW_BLUR_FRAC = 0.011
SHADOW_OFFSET_FRAC = 0.003
JPEG_QUALITY = 92

# Centered text reads best for a reflective transformation voice. Slide 1 (hook)
# a touch bigger to stop the scroll; the rest uniform.
HOOK_SCALE = 1.12
BODY_SCALE = 1.0


# ---------------------------------------------------------------- text helpers
def load_font(px):
    f = ImageFont.truetype(SF_FONT_PATH, px)
    try:
        f.set_variation_by_name(SF_VARIATION)
    except Exception:
        pass
    return f


def cover_fit(img, canvas):
    img = ImageOps.exif_transpose(img).convert("RGB")
    return ImageOps.fit(img, canvas, method=Image.LANCZOS, centering=(0.5, 0.5))


def scrim(base, strength=0.28):
    """Darken the whole image a touch so white text is always legible, even when
    the chosen background is not a pre-darkened one."""
    if strength <= 0:
        return base
    overlay = Image.new("RGB", base.size, (0, 0, 0))
    return Image.blend(base, overlay, strength)


def wrap_caption(draw, text, font, max_width):
    words = text.split()
    if not words:
        return []
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def draw_caption(base, text, canvas, scale=1.0, pos="center"):
    """Wrapped, white SF Pro Bold caption with soft shadow + dark stroke.
    pos = center | top | bottom. Blank lines in `text` are preserved (used to
    separate the hook from its sub-line)."""
    if not text:
        return base
    W, H = canvas
    font_px = max(12, int(H * CAP_FONT_FRAC * scale))
    font = load_font(font_px)
    margin_x = int(W * CAP_MARGIN_X_FRAC)
    max_text_w = W - 2 * margin_x
    stroke_w = max(2, int(font_px * 0.08))
    line_h = int(font_px * CAP_LINE_SPACING)

    draw = ImageDraw.Draw(base)
    lines = []
    for para in text.split("\n"):
        if para.strip() == "":
            lines.append("")                       # keep the blank spacer line
        else:
            lines.extend(wrap_caption(draw, para, font, max_text_w))
    block_h = line_h * len(lines)
    if pos == "top":
        y0 = int(H * 0.07)
    elif pos == "bottom":
        y0 = H - int(H * 0.07) - block_h
    else:
        y0 = (H - block_h) // 2                      # vertical center

    # soft drop shadow on its own layer, blurred then composited
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    off = int(H * SHADOW_OFFSET_FRAC)
    for i, ln in enumerate(lines):
        if ln == "":
            continue
        w = sdraw.textlength(ln, font=font)
        x = (W - w) / 2
        y = y0 + i * line_h
        sdraw.text((x + off, y + off), ln, font=font, fill=(0, 0, 0, 180))
    blur = max(1, int(H * SHADOW_BLUR_FRAC))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    base = Image.alpha_composite(base.convert("RGBA"), shadow).convert("RGB")

    # crisp white text with a thin dark rim
    draw = ImageDraw.Draw(base)
    for i, ln in enumerate(lines):
        if ln == "":
            continue
        w = draw.textlength(ln, font=font)
        x = (W - w) / 2
        y = y0 + i * line_h
        draw.text((x, y), ln, font=font, fill=(255, 255, 255),
                  stroke_width=stroke_w, stroke_fill=(0, 0, 0))
    return base


def open_image(src):
    if isinstance(src, str) and src.lower().startswith(("http://", "https://")):
        import requests
        r = requests.get(src, timeout=30)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content))
    return Image.open(src)


def render_slide(image_src, caption, canvas, scale=1.0, predarkened=False,
                 pos="center", scrim_strength=None):
    img = open_image(image_src)
    canvas_img = cover_fit(img, canvas)
    if scrim_strength is None:
        scrim_strength = 0.18 if predarkened else 0.34
    canvas_img = scrim(canvas_img, strength=scrim_strength)
    return draw_caption(canvas_img, caption or "", canvas, scale=scale, pos=pos)


def make_filmstrip(slide_imgs, out_path):
    if not slide_imgs:
        return
    thumb_h = 520
    thumbs = []
    for idx, im in enumerate(slide_imgs, 1):
        r = thumb_h / im.height
        t = im.resize((int(im.width * r), thumb_h), Image.LANCZOS).convert("RGB")
        d = ImageDraw.Draw(t)
        f = load_font(22)
        d.rectangle([0, 0, 46, 30], fill=(0, 0, 0))
        d.text((6, 4), f"S{idx}", font=f, fill=(255, 255, 255))
        thumbs.append(t)
    gap = 8
    W = sum(t.width for t in thumbs) + gap * (len(thumbs) + 1)
    strip = Image.new("RGB", (W, thumb_h + 2 * gap), (0, 0, 0))
    x = gap
    for t in thumbs:
        strip.paste(t, (x, gap))
        x += t.width + gap
    strip.save(out_path, quality=JPEG_QUALITY)


# ---------------------------------------------------------------- supabase
def _load_env(path=SECRETS_ENV):
    env = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update(os.environ)
    return env


def _sb_conn():
    env = _load_env()
    ref = env.get("CAROUSEL_SUPABASE_PROJECT", SUPABASE_PROJECT_REF)
    key = env.get("CAROUSEL_SUPABASE_SECRET_KEY")
    if not key:
        sys.exit(f"! CAROUSEL_SUPABASE_SECRET_KEY not found in env or {SECRETS_ENV}")
    base = f"https://{ref}.supabase.co/rest/v1"
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    return base, headers


def fetch_carousels(carousel_id=None, all_rows=False, include_unapproved=False):
    import requests
    base, headers = _sb_conn()
    cols = ["carousel_id", "hook_text"] + SLIDE_COPY_COLS + SLIDE_URL_COLS
    params = {"select": ",".join(cols), "order": "carousel_id"}
    if not include_unapproved:
        params["approved"] = "eq.true"
    if not all_rows:
        params["rendered_at"] = "is.null"
    if carousel_id:
        params["carousel_id"] = f"eq.{carousel_id}"
    r = requests.get(f"{base}/{TABLE}", headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


# Approved Character 6 image sets in carousel_images (bucket rich-life-images):
#   carousel-basis/2026-09-20 (the "after" batch): atmosphere 7, food(no-person) 30,
#     her 69, working_out 74.
#   before-basis/2026-09-26 (the "before" batch): her(before) 25, ...
# Background strategy (per the owner):
#   slides 1..n-2  -> GENERAL pool: the 7 atmosphere + 30 food(no-person) + a few her lifestyle
#   slide  n-1     -> BEFORE reveal: a real before photo (before-basis, her, before)
#   slide  n       -> AFTER  reveal: a real after  photo (carousel-basis, her, after)
AFTER_FOLDER = "character-6/carousel-basis/2026-09-20"
BEFORE_FOLDER = "character-6/before-basis/2026-09-26"
HER_IN_GENERAL = 12          # cap on how many "her" lifestyle shots join the general pool


import re as _re
# Tag JSON spacing is inconsistent across batches ("category":"her" vs
# "category": "her"), so classify in Python with a spacing-tolerant regex
# rather than a brittle SQL/PostgREST ilike.
def _tag(row, key):
    m = _re.search(r'"' + key + r'"\s*:\s*"([^"]*)"', row.get("tags") or "")
    return m.group(1) if m else None


def _fetch_folder(folder):
    import requests
    base, headers = _sb_conn()
    r = requests.get(
        f"{base}/{IMAGE_TABLE}", headers=headers,
        params={"select": "id,image_url,darkened_image,quality_score,has_subject,tags",
                "image_url": f"ilike.*{folder}*",
                "order": "quality_score.desc.nullslast"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _as_bg(row_list):
    out = []
    for row in row_list:
        dark = row.get("darkened_image")
        url = dark or row.get("image_url")
        if url:
            out.append({"url": url, "predarkened": bool(dark), "id": row.get("id")})
    return out


def fetch_pools():
    """Return (general, before, after) background pools.

    general = atmosphere + food(no-person) + up to HER_IN_GENERAL her shots, all
    from the carousel-basis (after) batch. before/after are the real reveal
    photos. Highest-quality first. Tags are classified in Python (spacing-safe)."""
    after_rows = _fetch_folder(AFTER_FOLDER)
    atmosphere = _as_bg([r for r in after_rows if _tag(r, "category") == "atmosphere"])
    food = _as_bg([r for r in after_rows
                   if _tag(r, "category") == "food" and r.get("has_subject") is False])
    her_after = [r for r in after_rows if _tag(r, "category") == "her"]
    her_general = _as_bg(her_after[:HER_IN_GENERAL])
    general = atmosphere + food + her_general

    before_rows = _fetch_folder(BEFORE_FOLDER)
    before = _as_bg([r for r in before_rows if _tag(r, "category") == "her"])
    after = _as_bg(her_after)        # all her/after shots are eligible reveal photos
    return general, before, after


def _distinct_picker(pool, rng):
    """Returns a function that yields distinct picks from pool (reshuffles when
    exhausted), seeded by rng."""
    order = list(range(len(pool)))
    rng.shuffle(order)
    state = {"i": 0}
    def pick():
        if not pool:
            return None
        p = pool[order[state["i"] % len(order)]]
        state["i"] += 1
        return p
    return pick


def assign_backgrounds(row, pools, rng):
    """Fill empty slide_N_url. Slides 1..n-1 draw from the general pool (atmosphere
    + food + a few her lifestyle); the FINAL populated slide is the AFTER reveal
    photo (a real her photo). n = number of slides that have copy. Respects any
    slide_N_url already set. Returns the {slide_N_url: url} map assigned."""
    general, before, after = pools
    filled = [i for i in range(1, 7) if row.get(SLIDE_COPY_COLS[i - 1])]
    if not filled:
        return {}
    after_slot = filled[-1]

    gpick = _distinct_picker(general, rng)
    apick = _distinct_picker(after, rng)
    assigned = {}
    for i in filled:
        ucol = SLIDE_URL_COLS[i - 1]
        if row.get(ucol):
            continue
        p = apick() if i == after_slot else gpick()
        if p is None:
            continue
        row[ucol] = p["url"]
        row.setdefault("_predark", {})[ucol] = p["predarkened"]
        row.setdefault("_reveal", {})[ucol] = (i == after_slot)
        assigned[ucol] = p["url"]
    return assigned


def persist(carousel_id, patch):
    import requests
    base, headers = _sb_conn()
    h = {**headers, "Content-Type": "application/json", "Prefer": "return=minimal"}
    r = requests.patch(f"{base}/{TABLE}", headers=h,
                       params={"carousel_id": f"eq.{carousel_id}"},
                       json=patch, timeout=30)
    r.raise_for_status()


def _sb_storage():
    env = _load_env()
    ref = env.get("CAROUSEL_SUPABASE_PROJECT", SUPABASE_PROJECT_REF)
    key = env.get("CAROUSEL_SUPABASE_SECRET_KEY")
    return ref, f"https://{ref}.supabase.co/storage/v1", {
        "apikey": key, "Authorization": f"Bearer {key}"}


def upload_render(local_path, carousel_id, idx):
    import requests
    ref, sbase, headers = _sb_storage()
    path = f"{RENDER_PREFIX}/{carousel_id}/slide_{idx:02d}.jpg"
    with open(local_path, "rb") as f:
        data = f.read()
    r = requests.post(
        f"{sbase}/object/{STORAGE_BUCKET}/{path}",
        headers={**headers, "Content-Type": "image/jpeg", "x-upsert": "true"},
        data=data, timeout=60,
    )
    r.raise_for_status()
    return f"https://{ref}.supabase.co/storage/v1/object/public/{STORAGE_BUCKET}/{path}"


# ---------------------------------------------------------------- driver
def render_from_supabase(carousel_id=None, all_rows=False, upload=False,
                         include_unapproved=False, out_root=None):
    rows = fetch_carousels(carousel_id, all_rows, include_unapproved)
    if not rows:
        print("No rows to render "
              f"(need {'any approval' if include_unapproved else 'approved=true'}"
              f"{'' if all_rows else ' and rendered_at IS NULL'}).")
        return
    general, before, after = fetch_pools()
    print(f"Pools: general={len(general)} (atmosphere+food+her), "
          f"before={len(before)}, after={len(after)}.")
    out_root = out_root or os.path.join(os.getcwd(), "out")
    print(f"{'Rendering + uploading' if upload else 'Rendering'} "
          f"{len(rows)} carousel(s) from {TABLE} ...")
    for row in rows:
        cid = row.get("carousel_id") or "unknown"
        rng = random.Random(cid)
        assigned = assign_backgrounds(row, (general, before, after), rng)
        out_dir = os.path.join(out_root, cid)
        os.makedirs(out_dir, exist_ok=True)
        rendered, slide_paths = [], []
        for i in range(1, 7):
            caption = row.get(SLIDE_COPY_COLS[i - 1])
            url = row.get(SLIDE_URL_COLS[i - 1])
            if not caption or not url:
                continue
            ucol = SLIDE_URL_COLS[i - 1]
            predark = row.get("_predark", {}).get(ucol, False)
            is_reveal = row.get("_reveal", {}).get(ucol, False)
            scale = HOOK_SCALE if i == 1 else BODY_SCALE
            # reveal slides are real photos of her: anchor text low and scrim
            # lighter so her face stays visible.
            pos = "bottom" if is_reveal else "center"
            scrim_strength = 0.22 if is_reveal else None
            try:
                slide = render_slide(url, caption, DEFAULT_CANVAS,
                                     scale=scale, predarkened=predark,
                                     pos=pos, scrim_strength=scrim_strength)
            except Exception as e:
                print(f"  ! {cid} slide {i}: {e}")
                continue
            p = os.path.join(out_dir, f"slide_{i:02d}.jpg")
            slide.save(p, quality=JPEG_QUALITY)
            rendered.append(slide)
            slide_paths.append((i, p))
        if not rendered:
            print(f"  · {cid}: nothing rendered (no copy or no backgrounds) — skipped")
            continue
        make_filmstrip(rendered, os.path.join(out_dir, "filmstrip.jpg"))
        picked = f" ({len(assigned)} backgrounds auto-picked)" if assigned else ""
        print(f"  ✓ {cid}: {len(rendered)} slides -> {out_dir}{picked}")
        if upload:
            render_urls, source_images = {}, {}
            for i, p in slide_paths:
                render_urls[SLIDE_URL_COLS[i - 1]] = upload_render(p, cid, i)
                source_images[str(i)] = row.get(SLIDE_URL_COLS[i - 1])
            patch = dict(render_urls)
            patch["source_images"] = source_images
            patch["status"] = "rendered"
            patch["rendered_at"] = "now()"
            persist(cid, patch)
            print(f"    ↳ uploaded {len(render_urls)} slides + stamped rendered")
    print("Done.")


def main(argv):
    if len(argv) >= 2 and argv[1] == "--supabase":
        flags = argv[2:]
        def val(name):
            return flags[flags.index(name) + 1] if name in flags else None
        render_from_supabase(
            carousel_id=val("--carousel"),
            all_rows="--all" in flags,
            upload="--upload" in flags,
            include_unapproved="--include-unapproved" in flags,
        )
        return
    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
