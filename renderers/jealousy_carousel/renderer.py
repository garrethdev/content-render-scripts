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
        if draw.textlength(t, font=font) <= maxw: cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines
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
    for ln in lines:
        x = (W - dr.textlength(ln, font=font)) / 2
        dr.text((x + ox_, y + oy_), ln, font=font, fill=sh)
        dr.text((x, y), ln, font=font, fill=fill); y += lh
    if label:
        L = BP["label"]; lf = tfont(L["weight"], L["size"]); tw = dr.textlength(label, font=lf)
        bx0, by0 = L["x"], L["y"]; bx1, by1 = bx0 + tw + 2 * L["pad_x"], by0 + L["size"] + 2 * L["pad_y"] + 6
        if L.get("backdrop", True):
            dr.rounded_rectangle((bx0, by0, bx1, by1), radius=(by1 - by0) // 2, fill=tuple(L["fill"]))
            dr.text((bx0 + L["pad_x"], by0 + L["pad_y"]), label, font=lf, fill=tuple(L["text"]))
        else:
            so = L.get("shadow_offset", [2, 3])
            dr.text((bx0 + so[0], by0 + so[1]), label, font=lf, fill=tuple(L.get("shadow", [0, 0, 0, 170])))
            dr.text((bx0, by0), label, font=lf, fill=tuple(L["text"]))
    return im.convert("RGB")
