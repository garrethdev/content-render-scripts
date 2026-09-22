"""Render the on-screen hook card, with emoji.

The card font (Liberation Sans Bold) has no emoji glyphs, so an emoji in the hook text would draw as an
empty box. Emoji are therefore cut out of the string, rendered separately from Noto Color Emoji and
pasted in line. Noto Color Emoji is a CBDT bitmap font that PIL will only open at 109 px, so each glyph
is drawn at 109, cropped and resized down to sit with the text.

Mixed case, ellipses and apostrophes need nothing special - they are ordinary glyphs in the card font.
"""
import re
from PIL import Image, ImageDraw, ImageFont

EMOJI_PATH = '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'
EMOJI_NATIVE = 109                      # the only size PIL can open this bitmap font at

# Codepoint ranges that Noto Color Emoji actually carries. Variation selectors and ZWJ ride along with
# the glyph before them so a joined sequence is not split down the middle.
_EMOJI = re.compile(
    '[\U0001F000-\U0001FAFF←-⇿⌀-➿⬀-⯿️‍⃣©®]+')

def _emoji_font():
    try:
        return ImageFont.truetype(EMOJI_PATH, EMOJI_NATIVE)
    except Exception:
        return None

def runs(s):
    """Split into [(is_emoji, text)] so each part is drawn with the font that has its glyphs."""
    out = []; i = 0
    for m in _EMOJI.finditer(s):
        if m.start() > i: out.append((False, s[i:m.start()]))
        out.append((True, m.group())); i = m.end()
    if i < len(s): out.append((False, s[i:]))
    return out or [(False, s)]

class CardRenderer:
    def __init__(self, font_path, size, max_line_px=800, pad_x=80, pad_y=26, gap=4):
        self.font = ImageFont.truetype(font_path, size)
        self.size = size
        self.emoji = _emoji_font()
        self.max_line_px = max_line_px
        self.pad_x, self.pad_y, self.gap = pad_x, pad_y, gap
        self.em_px = int(size * 0.95)                    # emoji drawn at cap height, not full em
        self._probe = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
        self._cache = {}

    def _glyph(self, ch):
        """One emoji cluster, rendered at 109 and resized to the text's cap height."""
        if ch in self._cache: return self._cache[ch]
        g = None
        if self.emoji:
            im = Image.new('RGBA', (EMOJI_NATIVE * 2, EMOJI_NATIVE * 2), (0, 0, 0, 0))
            try:
                ImageDraw.Draw(im).text((0, 0), ch, font=self.emoji, embedded_color=True)
                bb = im.getbbox()
                if bb: g = im.crop(bb).resize((self.em_px, self.em_px), Image.LANCZOS)
            except Exception:
                g = None
        self._cache[ch] = g
        return g

    def width(self, s):
        w = 0
        for is_em, part in runs(s):
            if is_em:
                # an unrenderable emoji takes no space rather than leaving a hole
                w += sum(self.em_px for c in part.split() or [part] if self._glyph(part)) or (
                    self.em_px if self._glyph(part) else 0)
            else:
                b = self._probe.textbbox((0, 0), part, font=self.font); w += b[2] - b[0]
        return w

    def wrap(self, text):
        lines, cur = [], ''
        for word in text.split():
            trial = (cur + ' ' + word).strip()
            if not cur or self.width(trial) <= self.max_line_px: cur = trial
            else: lines.append(cur); cur = word
        if cur: lines.append(cur)
        return lines

    def draw_line(self, card, x, y, s):
        dr = ImageDraw.Draw(card)
        asc, _ = self.font.getmetrics()
        for is_em, part in runs(s):
            if is_em:
                g = self._glyph(part)
                if g:
                    card.alpha_composite(g, (int(x), int(y + asc - self.em_px)))
                    x += self.em_px
            else:
                dr.text((x, y), part, font=self.font, fill=(255, 255, 255, 255))
                b = self._probe.textbbox((0, 0), part, font=self.font); x += b[2] - b[0]

    def render(self, text, canvas_w=1080):
        lines = self.wrap(text)
        asc, desc = self.font.getmetrics(); lh = asc + desc
        bw = max(self.width(l) for l in lines) + self.pad_x
        bh = len(lines) * lh + (len(lines) - 1) * self.gap + self.pad_y * 2
        card = Image.new('RGBA', (canvas_w, bh), (0, 0, 0, 0))
        x0 = (canvas_w - bw) // 2
        ImageDraw.Draw(card).rounded_rectangle([x0, 0, x0 + bw, bh], radius=28, fill=(0, 0, 0, 255))
        y = self.pad_y
        for l in lines:
            self.draw_line(card, (canvas_w - self.width(l)) // 2, y, l); y += lh + self.gap
        return card, bw, bh
