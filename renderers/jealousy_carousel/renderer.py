import json, os, sys, datetime, hashlib, urllib.request, urllib.parse
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
BP = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "blueprint.json")))
W, H = BP["canvas"]["w"], BP["canvas"]["h"]
# TikTok Sans variable font (SIL OFL, assets/OFL.txt). Override with JEALOUSY_FONT_PATH.
TT = os.environ.get("JEALOUSY_FONT_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "TikTokSans.ttf")
FONT, FONTB = "SemiBold", "Bold"
_fc = {}
def tfont(style, fs):
    k = (style, fs)
    if k not in _fc:
        f = ImageFont.truetype(TT, fs); f.set_variation_by_name(style); _fc[k] = f
    return _fc[k]
SIZES = {"xl": 74, "l": 58, "m": 47}
# Colour emoji in slide text (the writer's voice rules ask for some in every deck). TikTok Sans has none,
# so each emoji is drawn with a colour emoji font at its bitmap size and scaled to the line.
# Override with JEALOUSY_EMOJI_FONT; otherwise Apple Color Emoji (macOS) or Noto Color Emoji (Linux).
import re
EMOJI_SCALE = 1.0
EMOJI_RE = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"
    "|[☀-➿⬀-⯿\U0001F000-\U0001FAFF]️?[\U0001F3FB-\U0001F3FF]?"
    "(?:‍[☀-➿\U0001F000-\U0001FAFF]️?[\U0001F3FB-\U0001F3FF]?)*)")
_ef, _etile, _eimg = None, {}, {}
def emoji_font():
    global _ef
    if _ef is None:
        _ef = False
        for path in filter(None, [os.environ.get("JEALOUSY_EMOJI_FONT"), "/System/Library/Fonts/Apple Color Emoji.ttc",
                                  "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"]):
            for size in (160, 109, 137, 96, 64):
                try:
                    _ef = ImageFont.truetype(path, size); return _ef
                except OSError:
                    continue
        print("WARN: no colour emoji font found; emoji in slide text will be dropped", file=sys.stderr)
    return _ef
def emoji_image(cluster, fs):
    """The emoji on a transparent tile cropped to the glyph, about one font size tall."""
    k = (cluster, fs)
    if k not in _eimg:
        ef = emoji_font(); im = None
        if ef:
            if cluster not in _etile:
                side = int(ef.size * 1.6); t = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                ImageDraw.Draw(t).text((side // 2, side // 2), cluster, font=ef, embedded_color=True, anchor="mm")
                b = t.getbbox(); _etile[cluster] = t.crop(b) if b else None
            t = _etile[cluster]
            if t:
                h = max(1, round(fs * EMOJI_SCALE)); im = t.resize((max(1, round(t.width * h / t.height)), h), Image.LANCZOS)
        _eimg[k] = im
    return _eimg[k]
def runs(text):
    """Split a line into ("text", s) and ("emoji", cluster) runs."""
    out, i = [], 0
    for m in EMOJI_RE.finditer(text):
        if m.start() > i: out.append(("text", text[i:m.start()]))
        out.append(("emoji", m.group(0))); i = m.end()
    if i < len(text): out.append(("text", text[i:]))
    return out
def measure(draw, text, font):
    w = 0
    for kind, s in runs(text):
        if kind == "text": w += draw.textlength(s, font=font)
        else:
            im = emoji_image(s, font.size); w += (im.width + round(font.size * 0.06)) if im else 0
    return w
here = os.path.dirname(os.path.abspath(__file__))
def fetch(url):
    os.makedirs(os.path.join(here, "cache"), exist_ok=True)
    f = os.path.join(here, "cache", hashlib.md5(url.encode()).hexdigest() + os.path.splitext(urllib.parse.urlparse(url).path)[1])
    if not os.path.exists(f):
        urllib.request.urlretrieve(url, f)
    return f
def cover(im):
    return ImageOps.fit(im.convert("RGB"), (W, H), Image.LANCZOS, centering=(0.5, BP["canvas"]["crop_anchor_y"]))
def wrap(draw, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if measure(draw, t, font) <= maxw: cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines
def soft_shadow(im, items, cfg, sw=0):
    """A blurred dark copy of the text under it (items: (text, x, y, font)). cfg: radius, offset, color, spread."""
    if not cfg or not items: return im
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    ox, oy = cfg.get("offset", [0, 3]); col = tuple(cfg.get("color", [0, 0, 0, 200])); spread = int(cfg.get("spread", 0)) + sw
    for s, x, y, f in items:
        d.text((x + ox, y + oy), s, font=f, fill=col, stroke_width=spread, stroke_fill=col)
    lay = lay.filter(ImageFilter.GaussianBlur(cfg.get("radius", 6)))
    return Image.alpha_composite(im, lay)

def render_slide(path, text, pos, color, size, opacity, blur, n, label=None):
    im0 = Image.open(fetch(path)).convert("RGB"); ow, oh = im0.size
    if BP["canvas"].get("fit") == "blur_fill":
        # 9:16 prototype: photo fills the width, blurred copy of itself fills the rest.
        fsc = W / ow
        if blur:  # blur the face on the original, in original pixels
            x0 = int(blur["x"] * ow); y0 = int(blur["y"] * oh); x1 = int((blur["x"] + blur["w"]) * ow); y1 = int((blur["y"] + blur["h"]) * oh)
            reg = im0.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(BP["blur"]["radius"] / fsc))
            mask = Image.new("L", reg.size, 0); ImageDraw.Draw(mask).ellipse((0, 0, reg.size[0], reg.size[1]), fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(BP["blur"]["feather"] / fsc))
            im0.paste(reg, (x0, y0), mask); blur = None
        bg = ImageOps.fit(im0, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(BP["canvas"].get("bg_blur", 45)))
        from PIL import ImageEnhance
        bg = ImageEnhance.Brightness(bg).enhance(BP["canvas"].get("bg_dim", 0.7))
        fh = round(oh * fsc); fg = im0.resize((W, fh), Image.LANCZOS)
        if fh > H:
            top = int((fh - H) * BP["canvas"]["crop_anchor_y"]); fg = fg.crop((0, top, W, top + H)); fh = H
        bg.paste(fg, (0, int((H - fh) * BP["canvas"].get("fg_anchor_y", 0.5))))
        im = bg
    else:
        im = cover(im0)
    if blur:
        # blur box is in fractions of the original image; map through the cover crop
        sc = max(W / ow, H / oh); nw, nh = ow * sc, oh * sc; ox, oy = (nw - W) * 0.5, (nh - H) * BP["canvas"]["crop_anchor_y"]
        x0 = int(blur["x"] * nw - ox); y0 = int(blur["y"] * nh - oy); x1 = int((blur["x"] + blur["w"]) * nw - ox); y1 = int((blur["y"] + blur["h"]) * nh - oy)
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if x1 > x0 and y1 > y0:
            reg = im.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(BP["blur"]["radius"]))
            mask = Image.new("L", reg.size, 0); ImageDraw.Draw(mask).ellipse((0, 0, reg.size[0], reg.size[1]), fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(BP["blur"]["feather"]))
            im.paste(reg, (x0, y0), mask)
    pos = BP["slides"][str(n)]["position"]
    # gradient overlay for legibility
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    a = int(255 * max(BP["overlay"]["floor"], opacity))
    if pos == "top": rng = range(0, int(H * .62))
    elif pos == "center": rng = range(int(H * .15), int(H * .85))
    else: rng = range(int(H * .35), H)
    lo, hi = rng.start, rng.stop
    for y in rng:
        t = (y - lo) / max(1, hi - lo)
        if pos == "top": al = a * (1 - t)
        elif pos == "bottom": al = a * t
        else: al = a * (1 - abs(t - .5) * 2) ** .6
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(al * BP["overlay"]["boost"])))
    im = Image.alpha_composite(im.convert("RGBA"), ov)
    dr = ImageDraw.Draw(im)
    sp = BP["slides"][str(n)]; tx = BP["text"]; wt = sp["weight"]
    fs = sp["size"]
    if "size_long" in sp and len(text) > sp["long_over_chars"]: fs = sp["size_long"]
    font = tfont(wt, fs)
    maxw = W - 2 * tx["side_margin"]
    lines = wrap(dr, text, font, maxw)
    lh = int(fs * tx["line_height"]); bh = lh * len(lines)
    while bh > H * tx["max_block_frac"] and fs > tx["min_size"]:
        fs -= tx["shrink_step"]; font = tfont(wt, fs); lines = wrap(dr, text, font, maxw); lh = int(fs * tx["line_height"]); bh = lh * len(lines)
    pos = sp["position"]
    if pos == "top": y = tx["top_y"]
    elif pos == "center": y = (H - bh) // 2
    else: y = H - tx["bottom_margin"] - bh
    fill = tuple(tx["fill"]); sh = tuple(tx["shadow"]); ox_, oy_ = tx["shadow_offset"]
    asc = font.getmetrics()[0]; gap = round(font.size * 0.06)
    sw = int(tx.get("stroke_width", 0)); sf = tuple(tx.get("stroke_fill", [0, 0, 0, 255]))
    # lay out runs first, so the soft shadow and the text use the same positions
    placed = []
    for ln in lines:
        x = (W - measure(dr, ln, font)) / 2
        for kind, s in runs(ln):
            if kind == "text":
                placed.append(("text", s, x, y)); x += dr.textlength(s, font=font)
            else:
                em = emoji_image(s, font.size)
                if em:
                    x += gap / 2; placed.append(("emoji", em, round(x), round(y + asc - em.height * 0.88))); x += em.width + gap / 2
        y += lh
    im = soft_shadow(im, [(s, x, y, font) for k, s, x, y in placed if k == "text"], tx.get("soft_shadow"), sw)
    dr = ImageDraw.Draw(im)
    for k, s, x, y in placed:
        if k == "text":
            if not tx.get("soft_shadow"): dr.text((x + ox_, y + oy_), s, font=font, fill=sh)
            dr.text((x, y), s, font=font, fill=fill, stroke_width=sw, stroke_fill=sf)
        else:
            im.paste(s, (x, y), s)
    if label:
        L = BP["label"]; lf = tfont(L["weight"], L["size"]); tw = dr.textlength(label, font=lf)
        bx0, by0 = L["x"], L["y"]; bx1, by1 = bx0 + tw + 2 * L["pad_x"], by0 + L["size"] + 2 * L["pad_y"] + 6
        if L.get("backdrop", True):
            dr.rounded_rectangle((bx0, by0, bx1, by1), radius=(by1 - by0) // 2, fill=tuple(L["fill"]))
            dr.text((bx0 + L["pad_x"], by0 + L["pad_y"]), label, font=lf, fill=tuple(L["text"]))
        else:
            lsw = int(L.get("stroke_width", 0))
            if L.get("soft_shadow"):
                im = soft_shadow(im, [(label, bx0, by0, lf)], L["soft_shadow"], lsw); dr = ImageDraw.Draw(im)
            else:
                so = L.get("shadow_offset", [2, 3])
                dr.text((bx0 + so[0], by0 + so[1]), label, font=lf, fill=tuple(L.get("shadow", [0, 0, 0, 170])))
            dr.text((bx0, by0), label, font=lf, fill=tuple(L["text"]), stroke_width=lsw, stroke_fill=tuple(L.get("stroke_fill", [0, 0, 0, 255])))
    return im.convert("RGB")
