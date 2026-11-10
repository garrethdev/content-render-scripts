#!/usr/bin/env python3
"""
render_journey_3slide.py: Pillow renderer for the "3-Slide Journey Carousel" (Character 6).

A subtle prank:
  slide 1  Character 6 BEFORE photo + hook ("I'm gonna lose some weight" variants)
  slide 2  constant "Directed by Robert B. Weide" card (she didn't follow through)
  slide 3  Character 6 AFTER photo (the shock)

Template source: Figma "3-Slide Journey Carousel" (ZqDGTufoZyJX3EnRvdJyVi). Constants lifted from it:
  canvas 1080x1920; photos at 102.04% x 102.29% of the frame, offset -1.02% left;
  hook Gotham Bold 50px white, black outline, ~60px line height, wrapped to two balanced
  lines; the hook position differs per sample, so it is stored per row (hook_center_x,
  hook_top_y).

Content: Supabase table public.journey_3slide_carousel (see schema.sql). One row = one carousel.
Reads rows with render_status='pending' and both before/after image urls set, renders,
uploads to carousel-renders/journey-3slide/<carousel_id>/slide_N.jpg and PATCHes
slide_1..3_url, render_status='rendered', status='rendered', rendered_at back to the row.

Slide 2 is a constant. Binaries are not committed to this repo, so it is fetched from
storage (JOURNEY_SLIDE2_URL, default carousel-renders/journey-3slide/_assets/slide2_directed_by.png),
or from a row's slide_2_source_url when set.

Connection: SUPABASE_URL / SUPABASE_SERVICE_KEY via common/env.
Font: JOURNEY_FONT_PATH (default ~/Library/Fonts/Gotham-Bold.otf). Gotham is licensed, NOT committed.

Usage
  python render_journey_3slide.py                 # all pending rows
  python render_journey_3slide.py J3-005          # one row
  python render_journey_3slide.py --dry-run       # render to ./out, no uploads/writes
  python render_journey_3slide.py --limit 5
  python render_journey_3slide.py --env-file /path/to/.env   # load secrets from a local file

Emoji in hooks are drawn with the colour emoji font (EMOJI_FONT, default Apple Color Emoji),
and the hook block is kept between SAFE_TOP and SAFE_BOTTOM so TikTok's UI never covers it.
"""
import argparse, io, re, sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import env  # noqa: E402

TABLE = "journey_3slide_carousel"
BUCKET = "carousel-renders"
W, H = 1080, 1920
PHOTO = {"scale_w": 1.0204, "scale_h": 1.0229, "offset_x": -11, "offset_y": 0}
HOOK = {"size": 50, "line_height": 60, "fill": "#FFFFFF", "stroke": "#000000",
        "stroke_width": 7, "max_width": 640, "default_x": 540, "default_y": 1000}
# Keep the hook clear of TikTok's own UI on a 9:16 post: the top bar, and the caption,
# username and music line along the bottom. A hook block that would end below SAFE_BOTTOM
# is moved up; one that would start above SAFE_TOP is moved down.
SAFE_TOP, SAFE_BOTTOM = 250, 1440
EMOJI_SCALE = 1.05   # emoji height relative to the hook font size
EMOJI_RE = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"
    "|[\u2600-\u27BF\u2B00-\u2BFF\U0001F000-\U0001FAFF]\uFE0F?"
    "(?:\u200D[\u2600-\u27BF\U0001F000-\U0001FAFF]\uFE0F?)*)")
OUT = Path(__file__).resolve().parent / "out"


def cfg():
    url = env.require("SUPABASE_URL").rstrip("/")
    key = env.get("SUPABASE_SERVICE_KEY") or env.require("CAROUSEL_SUPABASE_SECRET_KEY")
    return url, {"apikey": key, "Authorization": f"Bearer {key}"}


def fetch_image(url):
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def place_photo(img):
    """Figma places photos at 102.04% x 102.29% of the frame, offset -1.02% left."""
    bw, bh = round(W * PHOTO["scale_w"]), round(H * PHOTO["scale_h"])
    fitted = ImageOps.fit(img, (bw, bh), method=Image.LANCZOS, centering=(0.5, 0.5))
    canvas = Image.new("RGB", (W, H), "black")
    canvas.paste(fitted, (PHOTO["offset_x"], PHOTO["offset_y"]))
    return canvas


def load_font():
    p = Path(env.get("JOURNEY_FONT_PATH") or "~/Library/Fonts/Gotham-Bold.otf").expanduser()
    if p.exists():
        return ImageFont.truetype(str(p), HOOK["size"])
    print(f"WARN: font not found at {p}; falling back to Pillow default", file=sys.stderr)
    try:
        return ImageFont.load_default(size=HOOK["size"])
    except TypeError:
        return ImageFont.load_default()


_emoji_font = None


def emoji_font():
    """Colour emoji font. Apple Color Emoji only draws at its bitmap sizes (160 is the largest);
    Noto Color Emoji only at 109. The glyph is drawn at that size and scaled to the hook."""
    global _emoji_font
    if _emoji_font is None:
        candidates = [env.get("EMOJI_FONT"), "/System/Library/Fonts/Apple Color Emoji.ttc",
                      "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"]
        for path in filter(None, candidates):
            for size in (160, 109, 137, 96, 64):
                try:
                    _emoji_font = ImageFont.truetype(path, size)
                    return _emoji_font
                except OSError:
                    continue
        _emoji_font = False
        print("WARN: no colour emoji font found; emoji in hooks will be dropped", file=sys.stderr)
    return _emoji_font


def emoji_image(cluster):
    """The emoji drawn on a transparent tile, cropped to the glyph, HOOK size tall."""
    ef = emoji_font()
    if not ef:
        return None
    side = int(ef.size * 1.4)
    tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((side // 2, side // 2), cluster, font=ef, embedded_color=True, anchor="mm")
    box = tile.getbbox()
    if not box:
        return None
    tile = tile.crop(box)
    h = round(HOOK["size"] * EMOJI_SCALE)
    return tile.resize((max(1, round(tile.width * h / tile.height)), h), Image.LANCZOS)


def runs(text):
    """Split a line into ("text", s) and ("emoji", cluster) runs."""
    out, i = [], 0
    for m in EMOJI_RE.finditer(text):
        if m.start() > i:
            out.append(("text", text[i:m.start()]))
        out.append(("emoji", m.group(0)))
        i = m.end()
    if i < len(text):
        out.append(("text", text[i:]))
    return out


def measure(d, text, font):
    w = 0
    for kind, s in runs(text):
        if kind == "text":
            w += d.textlength(s, font=font)
        else:
            im = emoji_image(s)
            w += im.width if im else 0
    return w


def wrap_balanced(d, text, font, max_width):
    """Greedy wrap, then rebalance to the narrowest width that keeps the same line count."""
    def greedy(limit):
        lines, cur = [], ""
        for word in text.split():
            t = f"{cur} {word}".strip()
            if cur and measure(d, t, font) > limit:
                lines.append(cur); cur = word
            else:
                cur = t
        return lines + [cur]
    n = len(greedy(max_width))
    lo, hi = 1, max_width
    while lo < hi:
        mid = (lo + hi) // 2
        if len(greedy(mid)) <= n: hi = mid
        else: lo = mid + 1
    return greedy(hi)


def draw_hook(img, text, center_x=None, top_y=None):
    cx = float(center_x if center_x is not None else HOOK["default_x"])
    y = float(top_y if top_y is not None else HOOK["default_y"])
    d, font = ImageDraw.Draw(img), load_font()
    lines = wrap_balanced(d, f'"{text}"', font, HOOK["max_width"])
    ascent, descent = font.getmetrics()
    block_bottom = y + (len(lines) - 1) * HOOK["line_height"] + ascent + descent + HOOK["stroke_width"]
    if block_bottom > SAFE_BOTTOM:
        y -= block_bottom - SAFE_BOTTOM
    y = max(y, SAFE_TOP)
    for line in lines:
        x = cx - measure(d, line, font) / 2
        baseline = y + ascent
        for kind, s in runs(line):
            if kind == "text":
                d.text((x, baseline), s, font=font, fill=HOOK["fill"], anchor="ls",
                       stroke_width=HOOK["stroke_width"], stroke_fill=HOOK["stroke"])
                x += d.textlength(s, font=font)
            else:
                im = emoji_image(s)
                if im:
                    img.paste(im, (round(x), round(baseline - im.height * 0.86)), im)
                    x += im.width
        y += HOOK["line_height"]
    return img


def upload(sb, hdr, img, path):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    r = requests.post(f"{sb}/storage/v1/object/{BUCKET}/{path}", data=buf.getvalue(),
                      headers={**hdr, "Content-Type": "image/jpeg", "x-upsert": "true"}, timeout=120)
    r.raise_for_status()
    return f"{sb}/storage/v1/object/public/{BUCKET}/{path}"


def slide2_for(sb, row):
    url = (row.get("slide_2_source_url") or env.get("JOURNEY_SLIDE2_URL")
           or f"{sb}/storage/v1/object/public/{BUCKET}/journey-3slide/_assets/slide2_directed_by.png")
    return fetch_image(url).resize((W, H), Image.LANCZOS)


def render_row(sb, hdr, row, dry_run):
    cid = row["carousel_id"]
    s1 = draw_hook(place_photo(fetch_image(row["before_image_url"])), row["hook_text"],
                   row.get("hook_center_x"), row.get("hook_top_y"))
    s2 = slide2_for(sb, row)
    s3 = place_photo(fetch_image(row["after_image_url"]))
    if dry_run:
        OUT.mkdir(exist_ok=True)
        for i, im in ((1, s1), (2, s2), (3, s3)):
            im.save(OUT / f"{cid}_slide_{i}.png")
        print("dry-run saved", cid)
        return
    urls = {f"slide_{i}_url": upload(sb, hdr, im, f"journey-3slide/{cid}/slide_{i}.jpg")
            for i, im in ((1, s1), (2, s2), (3, s3))}
    patch = {**urls, "render_status": "rendered", "status": "rendered",
             "rendered_at": datetime.now(timezone.utc).isoformat()}
    requests.patch(f"{sb}/rest/v1/{TABLE}?carousel_id=eq.{cid}", json=patch,
                   headers={**hdr, "Prefer": "return=minimal"}, timeout=60).raise_for_status()
    print("rendered", cid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("carousel_id", nargs="?")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--env-file", help="extra .env to load (e.g. a project-local one); never committed")
    a = ap.parse_args()
    if a.env_file:
        env.load_env(a.env_file)
    sb, hdr = cfg()
    q = (f"{sb}/rest/v1/{TABLE}?render_status=eq.pending&before_image_url=not.is.null"
         f"&after_image_url=not.is.null&select=*&limit={a.limit}")
    if a.carousel_id:
        q = f"{sb}/rest/v1/{TABLE}?carousel_id=eq.{a.carousel_id}&select=*"
    rows = requests.get(q, headers=hdr, timeout=60).json()
    print(f"{len(rows)} row(s) to render")
    for row in rows:
        render_row(sb, hdr, row, a.dry_run)


if __name__ == "__main__":
    main()
