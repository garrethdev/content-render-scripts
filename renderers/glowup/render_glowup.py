#!/usr/bin/env python3
"""Local renderer for the glow-up carousel pipeline.
Reads render_status='ready' decks from glowup_decks, composites 8 slides from the
(pre-graded) image bank, uploads PNGs to glowup-renders, marks the deck 'rendered'.
Run: source ~/.config/peptide-secrets/.env && .venv/bin/python render_glowup.py
"""
import os, io, sys, json, urllib.request, urllib.parse
from PIL import Image, ImageDraw, ImageFont

REF = "qlcmgxgwpzmiebzxflai"
KEY = os.environ.get("CAROUSEL_SUPABASE_SECRET_KEY")
if not KEY:
    sys.exit("CAROUSEL_SUPABASE_SECRET_KEY not set (source ~/.config/peptide-secrets/.env)")
REST = f"https://{REF}.supabase.co/rest/v1"
STORAGE = f"https://{REF}.supabase.co/storage/v1"
PUB = f"{STORAGE}/object/public/glowup-image-bank/"
HDR = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
OUT = os.path.expanduser("~/Claude/glowup-render/out")
W, H = 1080, 1440

def get_ready():
    req = urllib.request.Request(f"{REST}/glowup_decks?render_status=eq.ready&select=*", headers=HDR)
    return json.load(urllib.request.urlopen(req, timeout=60))

_cache = {}
def fetch(path):
    if path in _cache: return _cache[path]
    url = PUB + urllib.parse.quote(path)
    data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "glowup"}), timeout=60).read()
    im = Image.open(io.BytesIO(data)).convert("RGB"); _cache[path] = im; return im

def fill(im, box):
    tw, th = box; r = max(tw / im.width, th / im.height)
    im2 = im.resize((int(im.width * r), int(im.height * r)))
    x = (im2.width - tw) // 2; y = (im2.height - th) // 2
    return im2.crop((x, y, x + tw, y + th))

def wrap(d, text, f, maxw):
    words = text.split(); lines = []; cur = ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def caption(im, text, size):
    d = ImageDraw.Draw(im); f = ImageFont.truetype(FONT, size)
    lines = wrap(d, text, f, W * 0.86); lh = size * 1.2; total = lh * len(lines); y = H * 0.5 - total / 2
    for ln in lines:
        tw = d.textlength(ln, font=f); x = (W - tw) / 2
        d.text((x + 2, y + 3), ln, font=f, fill=(0, 0, 0))
        d.text((x, y), ln, font=f, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
        y += lh
    return im

def render_slide(slide):
    imgs = [fetch(p) for p in slide.get("images", [])]
    if len(imgs) >= 2:
        canvas = Image.new("RGB", (W, H), (12, 10, 9))
        for im, (x, y) in zip(imgs[:4], [(0, 0), (W // 2, 0), (0, H // 2), (W // 2, H // 2)]):
            canvas.paste(fill(im, (W // 2, H // 2)), (x, y))
    else:
        canvas = fill(imgs[0], (W, H)) if imgs else Image.new("RGB", (W, H), (12, 10, 9))
    size = 56 if slide["type"] == "cover" else (46 if slide["type"] in ("collage", "quiz") else 50)
    return caption(canvas, slide.get("text", ""), size)

def upload(deck_key, n, im):
    buf = io.BytesIO(); im.save(buf, "PNG"); buf.seek(0)
    url = f"{STORAGE}/object/glowup-renders/{deck_key}/slide{n}.png"
    req = urllib.request.Request(url, data=buf.read(), method="POST",
                                 headers={**HDR, "Content-Type": "image/png", "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=120).read()

def patch(deck_key, fields):
    req = urllib.request.Request(f"{REST}/glowup_decks?deck_key=eq.{urllib.parse.quote(deck_key)}",
                                 data=json.dumps(fields).encode(), method="PATCH",
                                 headers={**HDR, "Content-Type": "application/json", "Prefer": "return=minimal"})
    urllib.request.urlopen(req, timeout=60).read()

def main():
    decks = get_ready()
    print(f"{len(decks)} ready deck(s)")
    for deck in decks:
        dk = deck["deck_key"]; slides = deck["render_manifest"]["slides"]
        d = f"{OUT}/{dk}"; os.makedirs(d, exist_ok=True)
        for s in slides:
            im = render_slide(s); im.save(f"{d}/slide{s['n']}.png"); upload(dk, s["n"], im)
        patch(dk, {"render_status": "rendered"})
        print(f"  rendered {dk}: {len(slides)} slides | sound: {deck.get('suggested_sound', '')}")
    print("done")

if __name__ == "__main__":
    main()
