#!/usr/bin/env python3
"""Glow-Up deck PAINTER (ARCHITECTURE.md, 2026-07-31).

Dumb by design. Makes ZERO layout decisions. Reads render_manifest built by the
n8n Director (the brain), paints each slide literally, uploads, marks rendered.
All image selection, diagonal placement, brightness matching live in the Director.

Run: python3 paint_manifest.py "batch=eq.<batch>"   (any PostgREST filter)
     python3 paint_manifest.py "deck_key=eq.<key>"
Adds &render_status=eq.ready by default (the state the Director leaves decks in).
"""
import os, io, sys, json, subprocess, urllib.request, urllib.parse
from PIL import Image, ImageDraw, ImageFont

REF = "qlcmgxgwpzmiebzxflai"
KEY = os.environ["CAROUSEL_SUPABASE_SECRET_KEY"]
REST = f"https://{REF}.supabase.co/rest/v1"
STOR = f"https://{REF}.supabase.co/storage/v1"
HDR = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
OUT = os.path.expanduser("~/Claude/glowup-render/out2")
W, H = 1080, 1440
REPO = os.path.expanduser("~/Claude/peptide-renderers")


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=60))


def patch(dk, fields):
    urllib.request.urlopen(urllib.request.Request(
        f"{REST}/glowup_decks?deck_key=eq.{urllib.parse.quote(dk)}",
        data=json.dumps(fields).encode(), method="PATCH",
        headers={**HDR, "Content-Type": "application/json", "Prefer": "return=minimal"}), timeout=60).read()


_cache = {}
def fetch(u):
    if u in _cache:
        return _cache[u]
    d = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "g"}), timeout=60).read()
    im = Image.open(io.BytesIO(d)).convert("RGB")
    _cache[u] = im
    return im


def fill(im, box):
    tw, th = box
    r = max(tw / im.width, th / im.height)
    im = im.resize((int(im.width * r), int(im.height * r)))
    x = (im.width - tw) // 2
    y = (im.height - th) // 2
    return im.crop((x, y, x + tw, y + th))


def wrap(d, t, f, mw):
    ls, cur = [], ""
    for w in str(t).split():
        s = (cur + " " + w).strip()
        if d.textlength(s, font=f) <= mw:
            cur = s
        else:
            ls.append(cur); cur = w
    if cur:
        ls.append(cur)
    return ls


def cap(im, t, sz, yc=0.5):
    if not t:
        return im
    d = ImageDraw.Draw(im); f = ImageFont.truetype(FONT, sz)
    ls = wrap(d, t, f, W * 0.86); lh = sz * 1.2; y = H * yc - lh * len(ls) / 2
    for ln in ls:
        x = (W - d.textlength(ln, font=f)) / 2
        d.text((x + 2, y + 3), ln, font=f, fill=(0, 0, 0))
        d.text((x, y), ln, font=f, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
        y += lh
    return im


def datestamp(im, text):
    d = ImageDraw.Draw(im); f = ImageFont.truetype(FONT, 60)
    for i, txt in enumerate(str(text).split("\n")):
        tw = d.textlength(txt, font=f); x = W - tw - 46; y = 40 + i * 66
        d.text((x + 2, y + 3), txt, font=f, fill=(0, 0, 0))
        d.text((x, y), txt, font=f, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
    return im


def quad(cells):
    c = Image.new("RGB", (W, H), (12, 10, 9))
    for u, (x, y) in zip(cells, [(0, 0), (W // 2, 0), (0, H // 2), (W // 2, H // 2)]):
        c.paste(fill(fetch(u), (W // 2, H // 2)), (x, y))
    return c


def single(u):
    return fill(fetch(u), (W, H))


def upload(dk, n, im):
    buf = io.BytesIO(); im.save(buf, "PNG"); buf.seek(0)
    urllib.request.urlopen(urllib.request.Request(
        f"{STOR}/object/glowup-renders/{dk}/slide{n}.png",
        data=buf.read(), method="POST",
        headers={**HDR, "Content-Type": "image/png", "x-upsert": "true"}), timeout=120).read()


def paint_slide(s):
    """Paint ONE slide from its manifest entry. No choices — literal."""
    layout = s.get("layout")
    cells = s.get("cells", [])
    font = int(s.get("font", 48))
    if layout == "quad":
        im = cap(quad(cells), s.get("text"), font)
    elif layout == "quiz":
        im = cap(cap(single(cells[0]), s.get("text"), font, 0.13), s.get("cta"), int(s.get("cta_font", 40)), 0.9)
    else:  # single
        im = cap(single(cells[0]), s.get("text"), font)
    if s.get("datestamp"):
        im = datestamp(im, s["datestamp"])
    return im


def main():
    # 1. always run current code — pull source of truth before painting
    try:
        subprocess.run(["git", "-C", REPO, "pull", "--quiet"], timeout=60)
    except Exception as e:
        print("git pull skipped:", str(e)[:80])

    args = [a for a in sys.argv[1:]]
    q = "".join("&" + a for a in args)
    if not any(a.startswith("render_status") for a in args):
        q += "&render_status=eq.ready"
    decks = get(f"{REST}/glowup_decks?select=deck_key,render_manifest{q}&order=id")
    print(f"{len(decks)} decks to paint")
    for k, deck in enumerate(decks):
        dk = deck["deck_key"]
        man = deck.get("render_manifest")
        if not man or not man.get("slides"):
            print(f"  [SKIP] {dk}: no manifest (Director hasn't run)")
            continue
        d = f"{OUT}/{dk}"; os.makedirs(d, exist_ok=True)
        for s in man["slides"]:
            im = paint_slide(s)
            n = s["n"]
            im.save(f"{d}/slide{n}.png")
            upload(dk, n, im)
        urls = {f"slide_{i}_url": f"{STOR}/object/public/glowup-renders/{dk}/slide{i}.png" for i in range(1, 8)}
        patch(dk, {**urls, "render_status": "rendered"})
        print(f"  [{k+1}/{len(decks)}] {dk} painted")
    print("done")


if __name__ == "__main__":
    main()
