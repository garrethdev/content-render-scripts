#!/usr/bin/env python3
"""
covered_eye_carousel.py — dedicated carousel renderer for the jessicas_tt aesthetic clone
("covered-eye" mirror-selfie hook + food flat-lays + product + body payoff).

Pure renderer: burns the PRE-APPROVED caption onto each slide. It NEVER writes copy —
copy comes from the n8n Writer and clears the quality gate first (pipeline rule).
Match to the proven test carousel:
  - white SF Pro Bold caption, TOP-anchored, centered, word-wrapped
  - soft drop shadow + thin dark stroke for legibility on any background
  - cover-fit each source image to a 9:16 canvas (default 1080x1920)

Content source
--------------
Canonical source is Supabase, project "Carousel command center"
(qlcmgxgwpzmiebzxflai), table `public.covered_eye_carousel`. One row = one carousel:
  slide_1..slide_6       -> caption copy per slide
  slide_1_url..slide_6_url -> image for each slide (public storage URL)
  approved (bool), quality_status, render_set, batch, rendered_at, carousel_id
The renderer only pulls rows where approved = true (and, by default, rendered_at IS NULL).

The renderer is the BRAIN: for any slide whose slide_N_url is empty, it picks an
image at random from the matching pool in `covered_eye_image_bank`
(slide 1 = cover mirror-selfie, 2-4 = distinct food, 5 = product, 6 = body).
Picks are seeded by carousel_id so each carousel is stable across re-renders.
With --mark-rendered it writes the chosen slide_N_url back and stamps rendered_at.

Connection is read from ~/.config/peptide-secrets/.env:
  CAROUSEL_SUPABASE_PROJECT, CAROUSEL_SUPABASE_SECRET_KEY

Usage
-----
  # SUPABASE (canonical): render every approved, not-yet-rendered carousel
  python3 covered_eye_carousel.py --supabase
  python3 covered_eye_carousel.py --supabase --render-set A       # filter to a render_set
  python3 covered_eye_carousel.py --supabase --batch covered_eye_carousel-2026-07-11-A
  python3 covered_eye_carousel.py --supabase --carousel CE-002    # one row by carousel_id
  python3 covered_eye_carousel.py --supabase --all                # ignore rendered_at filter
  python3 covered_eye_carousel.py --supabase --mark-rendered      # stamp rendered_at after render

  # LOCAL spec file (testing / offline)
  python3 covered_eye_carousel.py spec.json [out_dir/]

  # single ad-hoc slide
  python3 covered_eye_carousel.py --one images/v3/v3_01.jpg 'how are you never hungry?' out/s1.jpg

Spec format (JSON, local mode)
------------------------------
  {
    "name": "test_carousel_01",          # optional; names the out subdir
    "canvas": [1080, 1920],              # optional; default 1080x1920
    "slides": [
      {"image": "images/v3/v3_02.jpg", "caption": "how are you never hungry?", "quote": true},
      {"image": "content/food_ref_clean/r12_s04.jpg", "caption": "my family calls the way I eat 'a phase'"},
      ...
    ]
  }

Each slide: `image` (path OR http url), `caption` (str; "" = no text), optional
`quote` (bool -> wraps caption in curly quotes), optional `pos`
("top"|"center"|"bottom"; default "top"), optional `caption_scale` (float, default 1.0).
"""

import io
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

# ---------------------------------------------------------------- config
SF_FONT_PATH = "/System/Library/Fonts/SFNS.ttf"   # variable SF Pro; "Bold" axis
SF_VARIATION = "Bold"
DEFAULT_CANVAS = (1080, 1920)                       # 9:16 vertical

# ---- Supabase (Carousel command center) ----------------------------------
SUPABASE_PROJECT_REF = "qlcmgxgwpzmiebzxflai"          # override via CAROUSEL_SUPABASE_PROJECT
CE_TABLE = "covered_eye_carousel"
SECRETS_ENV = os.path.expanduser("~/.config/peptide-secrets/.env")
SLIDE_COPY_COLS = [f"slide_{i}" for i in range(1, 7)]
SLIDE_URL_COLS = [f"slide_{i}_url" for i in range(1, 7)]
CE_IMAGE_BANK = "covered_eye_image_bank"

# The renderer is the brain: for any slide with no image assigned, it pulls one
# at random from the right pool in covered_eye_image_bank. Each entry is
# (pool, cover_only, distinct_group). distinct_group ties slides that must NOT
# repeat an image within one carousel (the 3 food flat-lays).
SLIDE_POOLS = {
    1: ("slide1_selfie", True, None),    # covered-eye mirror-selfie hook, cover shots only
    2: ("food", False, "food"),          # breakfast flat-lay
    3: ("food", False, "food"),          # lunch flat-lay   (distinct from 2)
    4: ("food", False, "food"),          # dinner flat-lay  (distinct from 2,3)
    5: ("product", False, None),         # Peptide Miracles quiz screenshot
    6: ("body", False, None),            # abs / body payoff
}

# Caption look, expressed as fractions of canvas so it scales with size.
CAP_FONT_FRAC = 0.038        # base font height as fraction of canvas height
CAP_MARGIN_X_FRAC = 0.06     # side margin (text wrap width)
CAP_TOP_FRAC = 0.055         # distance from top when pos="top"
CAP_LINE_SPACING = 1.12      # line-height multiplier
STROKE_FRAC = 0.006          # dark stroke width as fraction of font size
SHADOW_BLUR_FRAC = 0.010     # gaussian blur radius as fraction of canvas height
SHADOW_OFFSET_FRAC = 0.003   # shadow drop offset
JPEG_QUALITY = 92


# ---------------------------------------------------------------- helpers
def load_font(px):
    f = ImageFont.truetype(SF_FONT_PATH, px)
    try:
        f.set_variation_by_name(SF_VARIATION)
    except Exception:
        pass  # non-variable fallback still renders, just at default weight
    return f


def cover_fit(img, canvas):
    """Scale + center-crop `img` to exactly `canvas` (like CSS object-fit: cover)."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    return ImageOps.fit(img, canvas, method=Image.LANCZOS, centering=(0.5, 0.5))


# ---- emoji support (SF Pro has no color emoji: they render as tofu boxes).
# Same approach as the conspiracy renderer: render each emoji via Apple Color
# Emoji with embedded_color and paste it inline as an image.
import re as _re
EMOJI_FONT_PATH = "/System/Library/Fonts/Apple Color Emoji.ttc"
EMOJI_RE = _re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF\U0001F900-\U0001F9FF]️?|️")
_emoji_font = None

def _get_emoji_font():
    global _emoji_font
    if _emoji_font is None:
        _emoji_font = ImageFont.truetype(EMOJI_FONT_PATH, 160)
    return _emoji_font

def render_emoji(ch, target_h):
    img = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((120, 120), ch, font=_get_emoji_font(),
                             embedded_color=True, anchor="mm")
    bb = img.getbbox()
    if not bb:
        return None
    img = img.crop(bb)
    s = target_h / img.height
    return img.resize((max(1, int(img.width * s)), target_h), Image.LANCZOS)

def split_runs(line):
    """[('text', str)|('emoji', ch), ...] preserving order."""
    runs, pos = [], 0
    for m in EMOJI_RE.finditer(line):
        if m.start() > pos:
            runs.append(("text", line[pos:m.start()]))
        ch = m.group().replace("️", "")
        if ch:
            runs.append(("emoji", ch))
        pos = m.end()
    if pos < len(line):
        runs.append(("text", line[pos:]))
    return runs

def line_width(draw, font, line, emoji_h):
    w = 0
    for kind, val in split_runs(line):
        if kind == "text":
            w += draw.textlength(val, font=font)
        else:
            em = render_emoji(val, emoji_h)
            if em is not None:
                w += em.width + 6
    return w


def wrap_caption(draw, text, font, max_width, emoji_h=None):
    """Greedy word-wrap to fit max_width in pixels (emoji-aware)."""
    if emoji_h is None:
        emoji_h = font.size
    words = text.split()
    if not words:
        return []
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if line_width(draw, font, trial, emoji_h) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def draw_caption(base, text, canvas, pos="top", scale=1.0):
    """Draw a centered, wrapped, white SF Pro Bold caption with shadow + stroke."""
    if not text:
        return base
    W, H = canvas
    font_px = max(12, int(H * CAP_FONT_FRAC * scale))
    font = load_font(font_px)
    margin_x = int(W * CAP_MARGIN_X_FRAC)
    max_text_w = W - 2 * margin_x
    stroke_w = max(1, int(font_px * STROKE_FRAC / 0.006 * 0.006))  # ~STROKE_FRAC*font_px
    stroke_w = max(2, int(font_px * 0.10))                          # visible dark rim
    line_h = int(font_px * CAP_LINE_SPACING)

    draw = ImageDraw.Draw(base)
    emoji_h = int(font_px * 1.0)
    lines = wrap_caption(draw, text, font, max_text_w, emoji_h=emoji_h)
    block_h = line_h * len(lines)

    if pos == "top":
        y0 = int(H * CAP_TOP_FRAC)
    elif pos == "bottom":
        y0 = H - int(H * CAP_TOP_FRAC) - block_h
    else:  # center
        y0 = (H - block_h) // 2

    # ---- soft drop shadow on its own RGBA layer, then blur + composite
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    off = int(H * SHADOW_OFFSET_FRAC)
    for i, ln in enumerate(lines):
        w = line_width(sdraw, font, ln, emoji_h)
        x = (W - w) / 2
        y = y0 + i * line_h
        for kind, val in split_runs(ln):
            if kind == "text":
                sdraw.text((x + off, y + off), val, font=font, fill=(0, 0, 0, 170))
                x += sdraw.textlength(val, font=font)
            else:
                em = render_emoji(val, emoji_h)
                if em is None:
                    continue
                sil = Image.new("RGBA", em.size, (0, 0, 0, 170))
                shadow.paste(sil, (int(x + off) + 3, int(y + off)), em.split()[3])
                x += em.width + 6
    blur = max(1, int(H * SHADOW_BLUR_FRAC))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    base = Image.alpha_composite(base.convert("RGBA"), shadow).convert("RGB")

    # ---- crisp white text w/ thin dark stroke on top; emojis pasted as images
    draw = ImageDraw.Draw(base)
    for i, ln in enumerate(lines):
        w = line_width(draw, font, ln, emoji_h)
        x = (W - w) / 2
        y = y0 + i * line_h
        for kind, val in split_runs(ln):
            if kind == "text":
                draw.text(
                    (x, y), val, font=font, fill=(255, 255, 255),
                    stroke_width=stroke_w, stroke_fill=(0, 0, 0),
                )
                x += draw.textlength(val, font=font)
            else:
                em = render_emoji(val, emoji_h)
                if em is None:
                    continue
                base.paste(em, (int(x) + 3, int(y) + int((line_h - emoji_h) * 0.3)), em)
                x += em.width + 6
    return base


def open_image(src):
    """Open an image from a local path or an http(s) URL."""
    if isinstance(src, str) and src.lower().startswith(("http://", "https://")):
        import requests  # lazy: only needed for URL/Supabase sources
        r = requests.get(src, timeout=30)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content))
    return Image.open(src)


def render_slide(image_src, caption, canvas, pos="top", quote=False, scale=1.0):
    img = open_image(image_src)
    canvas_img = cover_fit(img, canvas)
    text = caption or ""
    if quote and text:
        text = f"“{text}”"
    return draw_caption(canvas_img, text, canvas, pos=pos, scale=scale)


def make_filmstrip(slide_imgs, out_path, label=True):
    """Horizontal contact strip of all slides for quick QA."""
    if not slide_imgs:
        return
    thumb_h = 560
    thumbs = []
    for idx, im in enumerate(slide_imgs, 1):
        r = thumb_h / im.height
        t = im.resize((int(im.width * r), thumb_h), Image.LANCZOS).convert("RGB")
        if label:
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


# ---------------------------------------------------------------- drivers
def render_from_spec(spec_path, out_dir=None):
    with open(spec_path) as f:
        spec = json.load(f)
    spec_dir = os.path.dirname(os.path.abspath(spec_path))
    canvas = tuple(spec.get("canvas", DEFAULT_CANVAS))
    name = spec.get("name", os.path.splitext(os.path.basename(spec_path))[0])
    out_dir = out_dir or os.path.join(os.getcwd(), "out", name)
    os.makedirs(out_dir, exist_ok=True)

    rendered = []
    for i, s in enumerate(spec["slides"], 1):
        img_path = s["image"]
        if not os.path.isabs(img_path):
            # try CWD first, then spec dir
            cand = img_path if os.path.exists(img_path) else os.path.join(spec_dir, img_path)
            img_path = cand
        if not os.path.exists(img_path):
            print(f"  ! slide {i}: MISSING image {s['image']}")
            continue
        slide = render_slide(
            img_path, s.get("caption", ""), canvas,
            pos=s.get("pos", "top"), quote=s.get("quote", False),
            scale=float(s.get("caption_scale", 1.0)),
        )
        out_path = os.path.join(out_dir, f"slide_{i:02d}.jpg")
        slide.save(out_path, quality=JPEG_QUALITY)
        rendered.append(slide)
        print(f"  ✓ slide {i:02d} -> {out_path}")

    if rendered:
        strip = os.path.join(out_dir, "filmstrip.jpg")
        make_filmstrip(rendered, strip)
        print(f"  ✓ filmstrip -> {strip}")
    print(f"Done: {len(rendered)} slides in {out_dir}")
    return out_dir


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
    env.update(os.environ)  # real env vars win
    return env


def _sb_conn():
    env = _load_env()
    ref = env.get("CAROUSEL_SUPABASE_PROJECT", SUPABASE_PROJECT_REF)
    key = env.get("CAROUSEL_SUPABASE_SECRET_KEY")
    if not key:
        sys.exit("! CAROUSEL_SUPABASE_SECRET_KEY not found in env or "
                 f"{SECRETS_ENV}")
    base = f"https://{ref}.supabase.co/rest/v1"
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    return base, headers


def fetch_carousels(render_set=None, batch=None, carousel_id=None, all_rows=False,
                    include_unapproved=False):
    """Pull covered_eye_carousel rows (approved=true unless --include-unapproved;
    rendered_at IS NULL unless --all)."""
    import requests
    base, headers = _sb_conn()
    cols = ["carousel_id", "hook_text", "hook_type", "caption"] + SLIDE_COPY_COLS + SLIDE_URL_COLS
    params = {"select": ",".join(cols), "order": "carousel_id"}
    if not include_unapproved:
        params["approved"] = "eq.true"
    if not all_rows:
        params["rendered_at"] = "is.null"
    if render_set:
        params["render_set"] = f"eq.{render_set}"
    if batch:
        params["batch"] = f"eq.{batch}"
    if carousel_id:
        params["carousel_id"] = f"eq.{carousel_id}"
    r = requests.get(f"{base}/{CE_TABLE}", headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def mark_rendered(carousel_id):
    import requests
    base, headers = _sb_conn()
    h = {**headers, "Content-Type": "application/json", "Prefer": "return=minimal"}
    r = requests.patch(
        f"{base}/{CE_TABLE}", headers=h,
        params={"carousel_id": f"eq.{carousel_id}"},
        json={"rendered_at": "now()", "status": "rendered"}, timeout=30,
    )
    r.raise_for_status()


def fetch_image_bank():
    """Return {pool: [ {public_url, is_cover}, ... ]} for active bank images."""
    import requests
    base, headers = _sb_conn()
    r = requests.get(
        f"{base}/{CE_IMAGE_BANK}", headers=headers,
        params={"select": "pool,public_url,is_cover", "status": "eq.active"},
        timeout=30,
    )
    r.raise_for_status()
    bank = {}
    for img in r.json():
        if img.get("public_url"):
            bank.setdefault(img["pool"], []).append(img)
    return bank


def assign_images(row, bank, rng):
    """Fill any empty slide_N_url by random pick from the pool (brain logic).

    Returns {slide_N_url: chosen_url} for the slots this call assigned (so the
    caller can persist them). Existing URLs on the row are left untouched.
    Cover-only pools prefer is_cover=true. Food slides are drawn distinct.
    """
    assigned = {}
    used_by_group = {}
    for i in range(1, 7):
        ucol = SLIDE_URL_COLS[i - 1]
        if row.get(ucol):
            continue  # already assigned upstream — respect it
        pool, cover_only, group = SLIDE_POOLS[i]
        candidates = bank.get(pool, [])
        if cover_only:
            covers = [c for c in candidates if c.get("is_cover")]
            candidates = covers or candidates  # fall back if none flagged
        if group is not None:
            used = used_by_group.setdefault(group, set())
            fresh = [c for c in candidates if c["public_url"] not in used]
            candidates = fresh or candidates  # allow repeat only if pool exhausted
        if not candidates:
            continue  # no image available for this slot
        pick = rng.choice(candidates)
        url = pick["public_url"]
        if group is not None:
            used_by_group[group].add(url)
        row[ucol] = url          # mutate in-memory so row_to_slides sees it
        assigned[ucol] = url
    return assigned


def persist_image_urls(carousel_id, url_map):
    """Write brain-assigned slide_N_url values back to the carousel row."""
    if not url_map:
        return
    import requests
    base, headers = _sb_conn()
    h = {**headers, "Content-Type": "application/json", "Prefer": "return=minimal"}
    r = requests.patch(
        f"{base}/{CE_TABLE}", headers=h,
        params={"carousel_id": f"eq.{carousel_id}"}, json=url_map, timeout=30,
    )
    r.raise_for_status()


# ---- storage upload for the FINAL captioned renders --------------------
STORAGE_BUCKET = "covered-eye-images"     # existing public bucket
RENDER_PREFIX = "renders"                 # renders/<CE-id>/slide_0N.jpg


def _sb_storage():
    """Return (ref, storage_base, headers) for Supabase storage calls."""
    env = _load_env()
    ref = env.get("CAROUSEL_SUPABASE_PROJECT", SUPABASE_PROJECT_REF)
    key = env.get("CAROUSEL_SUPABASE_SECRET_KEY")
    return ref, f"https://{ref}.supabase.co/storage/v1", {
        "apikey": key, "Authorization": f"Bearer {key}",
    }


def upload_render(local_path, carousel_id, idx):
    """Upload one captioned slide to storage; return its public URL."""
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


# Per-slide caption placement. Slide 5 is the product screenshot — its copy is
# long, so anchor it to the bottom (over the hands) to keep the logo/quiz visible.
SLIDE_POS = {5: "bottom"}
SLIDE_SCALE = {5: 0.9}
# Hook types that are a direct spoken line (someone reacting to/about her) —
# these get slide 1 wrapped in curly quotes. POV / Open Loop are narration, no quotes.
QUOTED_HOOK_TYPES = {"Jealous Friend"}


def row_to_slides(row):
    """Turn a covered_eye_carousel row into an ordered slide list (skips empty slots)."""
    quote_s1 = (row.get("hook_type") or "") in QUOTED_HOOK_TYPES
    slides = []
    for i, (ccol, ucol) in enumerate(zip(SLIDE_COPY_COLS, SLIDE_URL_COLS), 1):
        url = row.get(ucol)
        if not url:
            continue  # no image for this slot -> skip
        slides.append({
            "image": url,
            "caption": row.get(ccol) or "",
            "quote": (i == 1 and quote_s1),   # quote slide 1 only for spoken-line hooks
            "pos": SLIDE_POS.get(i, "top"),
            "caption_scale": SLIDE_SCALE.get(i, 1.0),
        })
    return slides


def render_from_supabase(render_set=None, batch=None, carousel_id=None,
                         all_rows=False, mark=False, upload=False, out_root=None,
                         include_unapproved=False):
    import random
    rows = fetch_carousels(render_set, batch, carousel_id, all_rows,
                           include_unapproved=include_unapproved)
    if not rows:
        print("No rows to render "
              f"(need {'any approval' if include_unapproved else 'approved=true'}"
              f"{'' if all_rows else ' and rendered_at IS NULL'}).")
        return
    bank = fetch_image_bank()   # the brain's image pool, fetched once
    out_root = out_root or os.path.join(os.getcwd(), "out")
    action = "Rendering + uploading" if upload else "Rendering"
    print(f"{action} {len(rows)} carousel(s) from Supabase {CE_TABLE} ...")
    for row in rows:
        cid = row.get("carousel_id") or "unknown"
        # Brain: assign any missing slide images at random from the pools.
        # Seed by carousel_id so a given carousel is stable across re-renders.
        rng = random.Random(cid)
        assigned = assign_images(row, bank, rng)
        slides = row_to_slides(row)
        if not slides:
            print(f"  · {cid}: no images available in bank — skipped")
            continue
        out_dir = os.path.join(out_root, cid)
        os.makedirs(out_dir, exist_ok=True)
        rendered = []
        slide_paths = []   # (index, local_path) for upload
        for i, s in enumerate(slides, 1):
            try:
                slide = render_slide(
                    s["image"], s["caption"], DEFAULT_CANVAS,
                    pos=s.get("pos", "top"), quote=s.get("quote", False),
                    scale=float(s.get("caption_scale", 1.0)),
                )
            except Exception as e:
                print(f"  ! {cid} slide {i}: {e}")
                continue
            p = os.path.join(out_dir, f"slide_{i:02d}.jpg")
            slide.save(p, quality=JPEG_QUALITY)
            rendered.append(slide)
            slide_paths.append((i, p))
        if not rendered:
            continue
        make_filmstrip(rendered, os.path.join(out_dir, "filmstrip.jpg"))
        picked = f" ({len(assigned)} imgs auto-picked)" if assigned else ""
        print(f"  ✓ {cid}: {len(rendered)} slides -> {out_dir}{picked}")
        if upload:
            # Upload the FINAL captioned renders; slide_N_url points at those.
            render_urls = {}
            for i, p in slide_paths:
                render_urls[SLIDE_URL_COLS[i - 1]] = upload_render(p, cid, i)
            persist_image_urls(cid, render_urls)
            mark_rendered(cid)
            print(f"    ↳ uploaded {len(render_urls)} slides + set rendered_at")
        elif mark:
            persist_image_urls(cid, assigned)   # record the brain's source picks
            mark_rendered(cid)
            print(f"    ↳ committed source image URLs + rendered_at to Supabase")
    print("Done.")


def main(argv):
    if len(argv) >= 2 and argv[1] == "--supabase":
        flags = argv[2:]
        def val(name):
            return flags[flags.index(name) + 1] if name in flags else None
        render_from_supabase(
            render_set=val("--render-set"),
            batch=val("--batch"),
            carousel_id=val("--carousel"),
            all_rows="--all" in flags,
            mark="--mark-rendered" in flags,
            upload="--upload" in flags,
            include_unapproved="--include-unapproved" in flags,
        )
        return

    if len(argv) >= 2 and argv[1] == "--one":
        # --one <image> <caption> <out.jpg> [canvas_w canvas_h]
        image_path, caption, out_path = argv[2], argv[3], argv[4]
        canvas = DEFAULT_CANVAS
        if len(argv) >= 7:
            canvas = (int(argv[5]), int(argv[6]))
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        render_slide(image_path, caption, canvas).save(out_path, quality=JPEG_QUALITY)
        print(f"✓ {out_path}")
        return

    if len(argv) < 2:
        print(__doc__)
        sys.exit(1)

    spec_path = argv[1]
    out_dir = argv[2] if len(argv) >= 3 else None
    render_from_spec(spec_path, out_dir)


if __name__ == "__main__":
    main(sys.argv)
