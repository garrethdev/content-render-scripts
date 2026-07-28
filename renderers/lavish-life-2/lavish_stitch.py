#!/usr/bin/env python3
"""Lavish Life 2.0 — Director + Stitcher.
Assembles dump carousels: slide-1 hook overlay, clean middle slides, card slide.
Base images come pre-iphoneified from keepers_iphoneified/; text overlays go on
AFTER the pass (app-rendered text is crisp over grainy photos, like real IG).
Cards are rendered clean (they read as screenshots, no grain).

Usage:
  python3 lavish_stitch.py spec.json            # local spec mode
Spec: [{"id":"LL2-001","occasion":"pool day","hook":"...","caption":"...",
        "card":{"text":"...","slot":"closer|buried","style":"white|pastel"}|null,
        "images":["dump_60.jpg", ...]}]
Output: carousels/<id>/slide_NN.jpg + caption.txt
Supabase mode (--supabase): TODO after the lavish_life_v2 table is live —
reads approved rows, mirrors covered_eye_carousel.py flow.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import json, os, sys, textwrap

BASE = os.path.dirname(os.path.abspath(__file__))
POOL = os.path.join(BASE, "keepers_iphoneified")
OUT = os.path.join(BASE, "carousels")
W, H = 1080, 1920

def font(sz, bold=True):
    return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", sz, index=1 if bold else 0)

def cover(img):
    sw, sh = img.size
    sc = max(W / sw, H / sh)
    img = img.resize((int(sw * sc), int(sh * sc)))
    sw, sh = img.size
    return img.crop(((sw - W) // 2, (sh - H) // 2, (sw - W) // 2 + W, (sh - H) // 2 + H))

def hook_slide(src, text, out, y_frac=0.18, size=64):
    """Approved style: white text, soft shadow, straight on the image."""
    img = cover(Image.open(src).convert("RGB"))
    f = font(size)
    lines = textwrap.wrap(text, 26)
    lh = int(size * 1.32)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    y = int(H * y_frac)
    for ln in lines:
        w = sd.textlength(ln, font=f)
        sd.text(((W - w) / 2 + 3, y + 3), ln, font=f, fill=(0, 0, 0, 190))
        y += lh
    shadow = shadow.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img.convert("RGBA"), shadow)
    d = ImageDraw.Draw(img)
    y = int(H * y_frac)
    for ln in lines:
        w = d.textlength(ln, font=f)
        d.text(((W - w) / 2, y), ln, font=f, fill=(255, 255, 255))
        y += lh
    img.convert("RGB").save(out, quality=92)

def card_slide(text, out, style="white"):
    """Camera-roll artifact card: whitespace-heavy, unbranded, lowercase-friendly."""
    bg = {"white": (250, 250, 248), "pastel": (233, 240, 235)}.get(style, (250, 250, 248))
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    f = font(46, bold=False)
    lines = []
    for para in text.split("\n"):
        lines += textwrap.wrap(para, 34) or [""]
    lh = 66
    y = int(H * 0.52) - len(lines) * lh // 2
    for ln in lines:
        w = d.textlength(ln, font=f)
        d.text(((W - w) / 2, y), ln, font=f, fill=(35, 38, 36))
        y += lh
    img.save(out, quality=92)

def assemble(c):
    cid = c["id"]
    dst = os.path.join(OUT, cid)
    os.makedirs(dst, exist_ok=True)
    imgs = c["images"]
    card = c.get("card")
    # director logic: hook on slide 1; card at closer (last) or buried (middle, never 1 or 2)
    total = len(imgs) + (1 if card else 0)
    card_pos = None
    if card:
        card_pos = total if card.get("slot") != "buried" else max(3, total // 2)
    pos, img_i = 1, 0
    while pos <= total:
        fn = os.path.join(dst, f"slide_{pos:02d}.jpg")
        if card_pos and pos == card_pos:
            card_slide(card["text"], fn, card.get("style", "white"))
        else:
            src = os.path.join(POOL, imgs[img_i])
            if not os.path.exists(src):
                src = os.path.join(BASE, "out", imgs[img_i])  # pen shots etc.
            if pos == 1:
                hook_slide(src, c["hook"], fn)
            else:
                Image.open(src).convert("RGB").save(fn, quality=92)
            img_i += 1
        pos += 1
    with open(os.path.join(dst, "caption.txt"), "w") as fh:
        fh.write(c["caption"])
    return cid, total

if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    for c in spec:
        cid, n = assemble(c)
        print(f"OK {cid}: {n} slides")
    print("DONE")
