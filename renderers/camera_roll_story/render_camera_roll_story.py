"""
render_camera_roll_story.py: Pillow renderer for the Camera Roll Story lane (Character 6).

This file holds the look and the picture picking, and renders a JSON file of stories to local JPGs
(nothing is uploaded). render_table.py is the table mode: it reads rows of
public.camera_roll_story_carousel, uploads the slides and marks the row rendered.

The photo list is pulled fresh from carousel_images on every run and only rows stored under
rich-life-images/character-6/ are used. Photos get deleted from the library, and a saved list
brings them back.

Eight slides at 1080x1920 (9:16), JPG quality 90, per the Carousel Render Blueprint
(https://claude.ai/artifact/9CN9pvUkGhyQaiPBzNy5bb). The look is the Jealousy and Comparison
look: the shared Character 6 text from common/slide_text.py (Inter, white with a black outline and
a soft shadow, colour emoji), hook centred on slide 1, story text at the bottom ending 430 px above
the edge, a black legibility gradient, no dots, numbers or logos, and no weight labels. Each slide's
text shifts a little inside its area and about one slide in three is tilted slightly, seeded by the
story id, so a re-render matches.

Pictures: see pictures.py. A picture carries the mood of its beat, not the words of its line. Slide 1
is her before; slides 2 to 6 are mostly pictures with no person plus one or two of her before, in an
arrangement that changes per deck; the reveal is slide 7 (close) and slide 8 (full length).

Usage:
  python3 render_camera_roll_story.py --stories stories.json            # every story -> out/<id>/slide_0N.jpg
  python3 render_camera_roll_story.py --stories stories.json --story 1,4
  python3 render_camera_roll_story.py --stories stories.json --plan     # print the picture picks, render nothing
  python3 render_camera_roll_story.py --stories stories.json --sheet    # also write one contact sheet per story

A story is {"id": 1, "slides": [8 strings], "shots": [8 shot names from pictures.py], "reveal_from": 7}.
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

import pictures as P

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common import env  # noqa: E402
from common import slide_text as ST  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920
JPEG_QUALITY = 90
COL_W = 912
BOTTOM_MARGIN = 430
LINE_H = 1.28
OVERLAY = 0.42
TINT_MIN, TINT_MAX = 0.10, 0.26    # the light tint over the whole picture: dark photos get the low end
OVERLAY_BOTTOM_FROM = 0.35
OVERLAY_CENTER = (0.15, 0.85)
HOOK = {"weight": "Bold", "size": 68, "size_long": 58, "long_over": 70}
STORY_FONT = ("SemiBold", 52)
MAX_BLOCK_FRAC = 0.55
MIN_SIZE = 34
CACHE = os.path.expanduser(env.get("CR_CACHE_DIR", "~/.cache/camera_roll_story/src"))
SUPABASE_PROJECT_REF = "qlcmgxgwpzmiebzxflai"
BANNED = re.compile(r"[&–—]")                 # emoji are fine: common/slide_text.py draws them in colour


# ---------------------------------------------------------------- pictures
LIBRARY = "/rich-life-images/character-6/"


def supabase():
    """(base url, key). The secret key when there is one (uploads need it), else the public key."""
    ref = env.get("CAROUSEL_SUPABASE_PROJECT", SUPABASE_PROJECT_REF)
    key = (env.get("CAROUSEL_SUPABASE_SECRET_KEY") or env.get("SUPABASE_SERVICE_KEY")
           or env.require("SUPABASE_ANON_KEY"))
    return f"https://{ref}.supabase.co", key


def load_pool():
    """Character 6's library only, asked for fresh on every run. A row stored anywhere else is left out."""
    base, key = supabase()
    q = urllib.parse.urlencode({"select": "id,filename,image_url,image_type,has_subject,content,framing",
                                "filename": "like.character-6-%", "order": "id"})
    req = urllib.request.Request(f"{base}/rest/v1/carousel_images?{q}", headers={
        "apikey": key, "Authorization": "Bearer " + key, "User-Agent": "carousel-renderer"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = json.loads(r.read())
    return {r["id"]: r for r in rows if r.get("image_url") and LIBRARY in r["image_url"]}


_CHECKED = set()


def load_image(url):
    assert LIBRARY in url, f"picture outside the Character 6 library: {url}"
    if url not in _CHECKED:          # the local cache can outlive a deleted photo, so ask storage first
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "carousel-renderer"})
        try:
            urllib.request.urlopen(req, timeout=30)
        except Exception:
            raise SystemExit(f"picture no longer in the library (deleted?): {url}\nRender again: the photo list is pulled fresh each run.")
        _CHECKED.add(url)
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:16] + ".bin")
    if not os.path.exists(p):
        req = urllib.request.Request(url, headers={"User-Agent": "carousel-renderer"})
        with urllib.request.urlopen(req, timeout=60) as r, open(p, "wb") as f:
            f.write(r.read())
    return ImageOps.exif_transpose(Image.open(p)).convert("RGB")


def kind_of(row):
    if not row.get("has_subject"):
        return P.OBJECT
    return P.BEFORE if row.get("image_type") == "Before" else P.AFTER


def pick_story(story, pool, usage):
    """Return {slide number: (photo id, what it is, note)} for one story."""
    sid = int(story["id"])
    rng = random.Random(f"cr-{sid}")
    reveal_from = story.get("reveal_from", P.DEFAULT_REVEAL_FROM)
    layout = "H" + P.LAYOUTS[(sid - 1) % len(P.LAYOUTS)]            # slide 1 is always her before
    taken, picks = set(), {}

    def take(ids, label, window=5):
        free = [i for i in ids if i in pool and i not in taken and usage.get(i, 0) < P.MAX_USES]
        if not free:
            return None
        low = min(usage.get(i, 0) for i in free)
        best = [i for i in free if usage.get(i, 0) == low][:window]   # best fit first, a little chance among the top
        pid = rng.choice(best)
        taken.add(pid)
        usage[pid] = usage.get(pid, 0) + 1
        return pid, label

    for n in range(1, 9):
        note = ""
        if n >= reveal_from:
            name = story["shots"][n - 1]
            got = take(P.NOW[name], name)
            if not got:
                fb = P.FALLBACK_NOW[n]
                got, note = take(P.NOW[fb], fb), f"no free '{name}' photo, used '{fb}'"
        elif n == 7:                                                  # reveal held to slide 8
            got = take(P.NOW["mirror_before"], "her before") or take(P.HER[3], "her before")
        elif layout[n - 1] == "H":
            got = take(P.HER[n], "her before")
            if not got:
                got, note = take(P.OBJ.get(n, P.OBJ[3]), "no person"), "no free photo of her, used a picture with no person"
        else:
            got = take(P.OBJ[n], "no person")
            if not got:
                got, note = take(P.HER[n], "her before"), "no free picture with no person, used her before"
        if not got:
            raise SystemExit(f"story {sid} slide {n}: no picture left")
        picks[n] = (got[0], got[1], note)
    for n, (pid, _, _) in picks.items():                              # the rule the lane stands on
        assert (kind_of(pool[pid]) == P.AFTER) == (n >= reveal_from), f"story {sid} slide {n} breaks the reveal rule"
    return picks


# ---------------------------------------------------------------- text (from the Comparison renderer)
def font(weight, size):
    return ST.font(weight, size)


def balanced(d, text, fnt, width):
    return ST.balanced(d, text, fnt, width)


def gradient(img, y0, y1, darkest_y=None):
    ov = Image.new("L", (1, H), 0)
    px = ov.load()
    for y in range(H):
        if darkest_y is None:
            a = 0 if y < y0 else (y - y0) / max(1, y1 - y0)
        else:
            a = 0 if (y < y0 or y > y1) else 1 - abs(y - darkest_y) / max(1, (y1 - y0) / 2)
        px[0, y] = round(255 * OVERLAY * max(0, min(1, a)))
    img.paste(Image.new("RGB", (W, H), "black"), (0, 0), ov.resize((W, H)))


def tint(img):
    """A very light dark tint over the whole picture, so white words read on any photo. Garreth,
    2026-11-19: a light overlay over the image, not a patch behind the words. A little more on a
    bright picture (a white plate), a little less on a dark one."""
    bright = ImageStat.Stat(img.convert("L").crop((0, int(H * 0.45), W, int(H * 0.85)))).mean[0] / 255
    amount = TINT_MIN + (TINT_MAX - TINT_MIN) * max(0.0, min(1.0, (bright - 0.30) / 0.40))
    return Image.blend(img, Image.new("RGB", img.size, "black"), amount)


def draw_text(img, lines, fnt, size, center_y=None, bottom=None, place=ST.NO_MOVE):
    step = size * LINE_H
    total = step * (len(lines) - 1) + size
    top = center_y - total / 2 if center_y is not None else bottom - total
    ST.draw_lines(img, lines, fnt, top, step, place=place, safe=(200, H - BOTTOM_MARGIN))


def fit_block(text, weight, size):
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    text = " ".join(str(text).split())
    while True:
        f = font(weight, size)
        lines = balanced(d, text, f, COL_W)
        if size * LINE_H * (len(lines) - 1) + size <= H * MAX_BLOCK_FRAC or size <= MIN_SIZE:
            return lines, f, size
        size -= 3


def render_slide(n, text, src, seed=None):
    """`seed` (the story or carousel id) turns on the per-slide shift and tilt."""
    img = ImageOps.fit(src, (W, H), method=Image.LANCZOS, centering=(0.5, 0.35))
    img = tint(img)
    if n == 1:
        size = HOOK["size_long"] if len(text) > HOOK["long_over"] else HOOK["size"]
        lines, f, size = fit_block(text, HOOK["weight"], size)
        gradient(img, int(H * OVERLAY_CENTER[0]), int(H * OVERLAY_CENTER[1]), H // 2)
        place = ST.placement(f"{seed}:{n}") if seed is not None else ST.NO_MOVE
        draw_text(img, lines, f, size, center_y=H / 2, place=place)
    else:
        lines, f, size = fit_block(text, *STORY_FONT)
        gradient(img, int(H * OVERLAY_BOTTOM_FROM), H)
        place = ST.placement(f"{seed}:{n}", down=0) if seed is not None else ST.NO_MOVE   # already on the lowest line
        draw_text(img, lines, f, size, bottom=H - BOTTOM_MARGIN, place=place)
    return img


def check_story(s):
    assert len(s["slides"]) == 8 and len(s["shots"]) == 8, f"story {s['id']}: needs 8 slides and 8 shots"
    for n in range(s.get("reveal_from", P.DEFAULT_REVEAL_FROM), 9):
        assert s["shots"][n - 1] in P.NOW, f"story {s['id']}: slide {n} must name one of {sorted(P.NOW)}"
    for t in s["slides"]:
        assert t.strip() and not BANNED.search(t), f"story {s['id']}: empty slide, ampersand or dash"


def sheet(out_dir, sid):
    tw, th = 270, 480
    im = Image.new("RGB", (tw * 8 + 9 * 8, th + 16), (24, 24, 24))
    for n in range(1, 9):
        s = Image.open(os.path.join(out_dir, f"slide_{n:02d}.jpg")).resize((tw, th), Image.LANCZOS)
        im.paste(s, (8 + (n - 1) * (tw + 8), 8))
    p = os.path.join(os.path.dirname(out_dir), f"sheet_{sid}.jpg")
    im.save(p, "JPEG", quality=85)
    return p


def main():
    ap = argparse.ArgumentParser(description="Render Camera Roll Story decks locally.")
    ap.add_argument("--stories", required=True, help="JSON file: a list of stories")
    ap.add_argument("--story", help="comma list of story ids")
    ap.add_argument("--plan", action="store_true", help="print the picks, render nothing")
    ap.add_argument("--sheet", action="store_true", help="also write a contact sheet per story")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    args = ap.parse_args()

    pool = load_pool()
    stories = json.load(open(args.stories))
    want = {x.strip() for x in args.story.split(",")} if args.story else None
    usage, plan = {}, {}
    for s in stories:                                   # pick for every story so a partial run matches a full one
        check_story(s)
        plan[s["id"]] = pick_story(s, pool, usage)
    for s in stories:
        sid = str(s["id"])
        if want and sid not in want:
            continue
        picks = plan[s["id"]]
        line = "  ".join(f"{n}:{pid}({shot})" for n, (pid, shot, _) in picks.items())
        print(f"story {sid}  {line}")
        for n, (pid, shot, note) in picks.items():
            if note:
                print(f"    slide {n}: {note}")
        if args.plan:
            continue
        out = os.path.join(args.out, f"story_{int(sid):02d}")
        os.makedirs(out, exist_ok=True)
        for n, (pid, _, _) in picks.items():
            assert LIBRARY in pool[pid]["image_url"], f"photo {pid} is outside the Character 6 library"
            im = render_slide(n, s["slides"][n - 1], load_image(pool[pid]["image_url"]), seed=sid)
            assert im.size == (W, H)
            im.save(os.path.join(out, f"slide_{n:02d}.jpg"), "JPEG", quality=JPEG_QUALITY)
        json.dump({str(n): {"photo_id": pid, "shot": shot, "url": pool[pid]["image_url"],
                            "shows": pool[pid].get("content"), "note": note}
                   for n, (pid, shot, note) in picks.items()},
                  open(os.path.join(out, "picks.json"), "w"), indent=1)
        if args.sheet:
            print("    sheet:", sheet(out, f"{int(sid):02d}"))
    top = sorted(usage.items(), key=lambda kv: -kv[1])[:8]
    print("most used photos:", top)


if __name__ == "__main__":
    main()
