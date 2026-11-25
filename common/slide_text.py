"""The one text look every Character 6 carousel renderer draws with (Czedrick, 2026-11-26).

Look: Inter, white, a black outline (4 px on 58 px text, the sample Czedrick picked; it grows
with the text and is never thinner than 4 px), the soft offset shadow the Jealousy lane
already used, and colour emoji. Divorce Recovery keeps its white boxes with black Inter text
(`draw_boxes`), no outline.

Variation, so decks do not look stamped from one template: each slide's text shifts a little
inside the area its renderer planned (up or down by up to MAX_DY, sideways by up to MAX_DX),
and about one slide in three is tilted 1.5 to 4 degrees either way. A renderer says which
directions are allowed (text ending at the bottom limit may only move up) and the safe band
the block must stay inside, so the text never lands anywhere the renderer would not put it.
Shift and tilt are seeded by the deck id and slide number: re-rendering a deck draws it the
same way.

Font: common/fonts/Inter.ttf (SIL OFL, common/fonts/OFL.txt). Override with SLIDE_FONT_PATH.
Emoji: SLIDE_EMOJI_FONT, else Apple Color Emoji (macOS) or Noto Color Emoji (Linux).
"""
import hashlib
import os
import random
import re
import sys

from PIL import Image, ImageDraw, ImageFont

_HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.environ.get("SLIDE_FONT_PATH") or os.path.join(_HERE, "fonts", "Inter.ttf")

FILL = (255, 255, 255, 255)
OUTLINE = (0, 0, 0, 255)
OUTLINE_RATIO = 4 / 58          # Czedrick's pick: 4 px on the 58 px Jealousy hook
OUTLINE_MIN = 4
SHADOW = (0, 0, 0, 150)         # the Jealousy lane's shadow, kept under the outline
SHADOW_OFF = (2, 3)

MAX_DY = 96                     # about a tenth of a 1920 px slide, split up and down
MAX_DX = 36
TILT_CHANCE = 1 / 3
TILT_DEG = (1.5, 4.0)

NO_MOVE = (0.0, 0.0, 0.0)


# ---------------------------------------------------------------- font
_fonts = {}


def font(weight, size):
    """Inter at a named weight (Regular, Medium, SemiBold, Bold) and pixel size."""
    key = (weight, round(size))
    if key not in _fonts:
        if not os.path.exists(FONT_PATH):
            raise SystemExit(f"Inter not found at {FONT_PATH}; set SLIDE_FONT_PATH.")
        f = ImageFont.truetype(FONT_PATH, round(size))
        try:
            f.set_variation_by_name(weight)
        except (OSError, ValueError):
            pass                # a static font file: use it as it is
        _fonts[key] = f
    return _fonts[key]


def outline_width(size):
    return max(OUTLINE_MIN, round(size * OUTLINE_RATIO))


# ---------------------------------------------------------------- emoji
EMOJI_RE = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"
    "|[☀-➿⬀-⯿\U0001F000-\U0001FAFF]️?[\U0001F3FB-\U0001F3FF]?"
    "(?:‍[☀-➿\U0001F000-\U0001FAFF]️?[\U0001F3FB-\U0001F3FF]?)*)")
_emoji_font, _emoji_tile, _emoji_img = None, {}, {}


def _emoji_face():
    global _emoji_font
    if _emoji_font is None:
        _emoji_font = False
        for path in filter(None, [os.environ.get("SLIDE_EMOJI_FONT"),
                                  "/System/Library/Fonts/Apple Color Emoji.ttc",
                                  "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"]):
            for size in (160, 109, 137, 96, 64):      # colour emoji fonts only draw at bitmap sizes
                try:
                    _emoji_font = ImageFont.truetype(path, size)
                    return _emoji_font
                except OSError:
                    continue
        print("WARN: no colour emoji font found; emoji in slide text will be dropped", file=sys.stderr)
    return _emoji_font


def emoji_image(cluster, size):
    """The emoji on a transparent tile cropped to the glyph, `size` px tall."""
    key = (cluster, round(size))
    if key not in _emoji_img:
        ef, im = _emoji_face(), None
        if ef:
            if cluster not in _emoji_tile:
                side = int(ef.size * 1.6)
                t = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                ImageDraw.Draw(t).text((side // 2, side // 2), cluster, font=ef, embedded_color=True, anchor="mm")
                b = t.getbbox()
                _emoji_tile[cluster] = t.crop(b) if b else None
            t = _emoji_tile[cluster]
            if t:
                h = max(1, round(size))
                im = t.resize((max(1, round(t.width * h / t.height)), h), Image.LANCZOS)
        _emoji_img[key] = im
    return _emoji_img[key]


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


def _gap(fnt):
    return round(fnt.size * 0.06)


def measure(draw, text, fnt):
    """Width of a line, emoji included."""
    w = 0
    for kind, s in runs(text):
        if kind == "text":
            w += draw.textlength(s, font=fnt)
        else:
            im = emoji_image(s, fnt.size)
            w += (im.width + _gap(fnt)) if im else 0
    return w


def wrap(draw, text, fnt, width):
    """Greedy wrap by measured width (emoji included)."""
    lines, cur = [], ""
    for word in str(text).split():
        t = f"{cur} {word}".strip()
        if cur and measure(draw, t, fnt) > width:
            lines.append(cur)
            cur = word
        else:
            cur = t
    return lines + ([cur] if cur else [])


def balanced(draw, text, fnt, width):
    """Wrap, then narrow the column as far as it goes without adding a line."""
    n = len(wrap(draw, text, fnt, width))
    lo, hi = 1, width
    while lo < hi:
        mid = (lo + hi) // 2
        if len(wrap(draw, text, fnt, mid)) <= n:
            hi = mid
        else:
            lo = mid + 1
    return wrap(draw, text, fnt, hi)


# ---------------------------------------------------------------- variation
def placement(key, up=MAX_DY, down=MAX_DY, sideways=MAX_DX, tilt=True):
    """(dx, dy, degrees) for one slide, seeded by `key` (deck id + slide number).
    `up` / `down` / `sideways` are the most the text may move that way (0 = not at all)."""
    r = random.Random(hashlib.sha256(str(key).encode()).hexdigest())
    dy = r.uniform(-up, down)
    dx = r.uniform(-sideways, sideways)
    deg = 0.0
    if r.random() < TILT_CHANCE:            # drawn every time so the shift does not depend on `tilt`
        deg = r.choice((-1, 1)) * r.uniform(*TILT_DEG)
    return dx, dy, deg if tilt else 0.0


def _settle(top, height, dy, safe):
    """Shifted block top, kept inside the safe band. A block that never fitted keeps its place."""
    y = top + dy
    if safe:
        lo, hi = safe
        if height <= hi - lo:
            y = min(max(y, lo), hi - height)
        else:
            y = top
    return y


def _paste(img, layer, deg, cx, cy):
    if deg:
        layer = layer.rotate(deg, resample=Image.BICUBIC, center=(cx, cy))
    img.paste(layer, (0, 0), layer)
    return img


# ---------------------------------------------------------------- drawing
def draw_lines(img, lines, fnt, top, step, cx=None, place=NO_MOVE, safe=None,
               fill=FILL, outline=True, shadow=True):
    """Centred lines of white text: shadow, then the outlined letters, then colour emoji.
    `top` is the first line's top, `step` the distance between line tops. Draws into `img`
    (RGB or RGBA) and returns it."""
    W, H = img.size
    dx, dy, deg = place
    cx = (W / 2 if cx is None else cx) + dx
    asc, desc = fnt.getmetrics()
    height = step * (len(lines) - 1) + asc + desc
    y0 = _settle(top, height, dy, safe)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    sw = outline_width(fnt.size) if outline else 0
    gap = _gap(fnt)
    spans = []                                   # (x, y, kind, s) for every run
    for i, line in enumerate(lines):
        x, y = cx - measure(d, line, fnt) / 2, y0 + i * step
        for kind, s in runs(line):
            spans.append((x, y, kind, s))
            if kind == "text":
                x += d.textlength(s, font=fnt)
            else:
                im = emoji_image(s, fnt.size)
                x += (im.width + gap) if im else 0
    if shadow:
        for x, y, kind, s in spans:
            if kind == "text":
                d.text((x + SHADOW_OFF[0], y + SHADOW_OFF[1]), s, font=fnt, fill=SHADOW)
    for x, y, kind, s in spans:
        if kind == "text":
            d.text((x, y), s, font=fnt, fill=fill, stroke_width=sw, stroke_fill=OUTLINE)
        else:
            im = emoji_image(s, fnt.size)
            if im:
                layer.paste(im, (round(x + gap / 2), round(y + asc - im.height * 0.88)), im)
    return _paste(img, layer, deg, cx, y0 + height / 2)


def draw_boxes(img, lines, fnt, top, box_h, box_step, radius, pad, place=NO_MOVE, safe=None,
               box_fill="white", text_fill="black"):
    """TikTok's box style: one rounded box per line hugging the line, centred, dark text.
    `top` is the first box's top. Draws into `img` and returns it."""
    W, H = img.size
    dx, dy, deg = place
    cx = W / 2 + dx
    height = box_h + box_step * (len(lines) - 1)
    y0 = _settle(top, height, dy, safe)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    gap = _gap(fnt)
    widths = [measure(d, ln, fnt) for ln in lines]
    for i, w in enumerate(widths):
        y = y0 + i * box_step
        d.rounded_rectangle((cx - w / 2 - pad, y, cx + w / 2 + pad, y + box_h), radius=radius, fill=box_fill)
    for i, (line, w) in enumerate(zip(lines, widths)):
        x, mid = cx - w / 2, y0 + i * box_step + box_h / 2
        for kind, s in runs(line):
            if kind == "text":
                d.text((x, mid), s, font=fnt, fill=text_fill, anchor="lm")
                x += d.textlength(s, font=fnt)
            else:
                im = emoji_image(s, fnt.size)
                if im:
                    layer.paste(im, (round(x + gap / 2), round(mid - im.height / 2)), im)
                    x += im.width + gap
    return _paste(img, layer, deg, cx, y0 + height / 2)
