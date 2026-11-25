"""Kitchen Quote Video overlay: dark fade + white TikTok Sans Bold text + Apple emoji.

Same numbers as the 2026-11-24 rerender of all 21 live videos (1080x1920):
  - text: TikTok Sans Bold 64 px, white, centred, wrapped to a 912 px column
  - last line ends 430 px above the bottom edge (Instagram caption zone stays clear)
  - dark fade: black, alpha 0 at (text top - 420) rising (ease-in, exp 1.5) over 370 px
    to 72%, then flat to the bottom edge
  - drop shadow: 2,3 px offset, blur 1, 80%
  - 1 or 2 colour emoji, kept on the line of the last word

The font and emoji pictures are not in git (the repo holds no binaries). assets.py fetches
them from storage the first time and keeps them in ./cache/.
"""
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import assets

W, H = 1080, 1920
P = dict(
    size=64, col=912, bottom_margin=430, line_gap=1.22,
    fade_above=420, fade_ramp=370, fade_exp=1.5, max_alpha=0.72,
    shadow_dx=2, shadow_dy=3, shadow_blur=1, shadow_alpha=0.8,
    emoji_scale=1.04, emoji_adv=0.95, emoji_gap=8, emoji_dy=1,
)

EMOJI_RE = re.compile('([←-⯿\U0001F000-\U0001FAFF][️‍]*)+')


def split_emoji(seq):
    out, buf = [], ''
    for ch in seq:
        if ch in '️‍' and buf:
            buf += ch
        else:
            if buf:
                out.append(buf)
            buf = ch
    if buf:
        out.append(buf)
    return out


def tokenize(text):
    """Words, with the trailing emoji run attached to the last word."""
    text = text.strip()
    m = EMOJI_RE.search(text)
    words_part, emoji_part = (text[:m.start()].rstrip(), text[m.start():].strip()) if m else (text, '')
    words = [[w, []] for w in words_part.split()]
    if emoji_part:
        ems = split_emoji(emoji_part.replace(' ', ''))
        if words:
            words[-1][1] = ems
        else:
            words = [['', ems]]
    return words


def emojis_in(text):
    return [e for _, ems in tokenize(text) for e in ems]


def build_overlay(text, p=P):
    font = ImageFont.truetype(assets.font_path(), p['size'])
    asc, desc = font.getmetrics()
    em = int(round(p['size'] * p['emoji_scale']))
    space = font.getlength(' ')

    def tok_w(t):
        w = font.getlength(t[0])
        if t[1]:
            w += p['emoji_gap'] + (len(t[1]) - 1) * em * p['emoji_adv'] + em
        return w

    lines, cur = [], []
    for t in tokenize(text):
        trial = cur + [t]
        tw = sum(tok_w(x) for x in trial) + space * (len(trial) - 1)
        if cur and tw > p['col']:
            lines.append(cur)
            cur = [t]
        else:
            cur = trial
    if cur:
        lines.append(cur)

    lh = int(round(p['size'] * p['line_gap']))
    top = H - p['bottom_margin'] - (len(lines) - 1) * lh - (asc + desc)

    # fade
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    fade = Image.new('L', (1, H), 0)
    y0 = top - p['fade_above']
    for y in range(H):
        a = 0.0 if y < y0 else p['max_alpha'] * min(1.0, (y - y0) / p['fade_ramp']) ** p['fade_exp']
        fade.putpixel((0, y), int(round(a * 255)))
    img.putalpha(fade.resize((W, H)))

    text_l = Image.new('L', (W, H), 0)
    td = ImageDraw.Draw(text_l)
    emoji_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for i, line in enumerate(lines):
        lw = sum(tok_w(x) for x in line) + space * (len(line) - 1)
        x = (W - lw) / 2
        y = top + i * lh
        for j, t in enumerate(line):
            if t[0]:
                td.text((x, y), t[0], font=font, fill=255)
                x += font.getlength(t[0])
            if t[1]:
                x += p['emoji_gap']
                for e in t[1]:
                    im = Image.open(assets.emoji_path(e)).convert('RGBA').resize((em, em), Image.LANCZOS)
                    ey = int(round(y + asc - em * 0.86 + p['emoji_dy']))
                    emoji_layer.alpha_composite(im, (int(round(x)), ey))
                    x += em * p['emoji_adv']
                x += em * (1 - p['emoji_adv'])
            if j < len(line) - 1:
                x += space

    # shadow from the text and the emoji shapes
    sh_mask = Image.fromarray(np.maximum(np.asarray(text_l), np.asarray(emoji_layer.split()[3])))
    sh = Image.new('L', (W, H), 0)
    sh.paste(sh_mask, (p['shadow_dx'], p['shadow_dy']))
    if p['shadow_blur']:
        sh = sh.filter(ImageFilter.GaussianBlur(p['shadow_blur']))
    sh = sh.point(lambda v: int(v * p['shadow_alpha']))
    shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    shadow.putalpha(sh)
    img.alpha_composite(shadow)
    white = Image.new('RGBA', (W, H), (255, 255, 255, 0))
    white.putalpha(text_l)
    img.alpha_composite(white)
    img.alpha_composite(emoji_layer)
    return img, dict(lines=[' '.join(t[0] + ''.join(t[1]) for t in l) for l in lines], top=top)


if __name__ == '__main__':
    import sys
    im, info = build_overlay(sys.argv[1])
    im.save(sys.argv[2])
    print(info)
