#!/usr/bin/env python3
"""Char3 ASMR "two-beat question" stitcher.

Recipe (cloned from IG reel DbJi1GwJH2i, with our before-image inset added):
  ONE locked ASMR workout clip (natural length), warm filmic grade.
  Two TEXT beats, editorial serif, warm cream, soft drop shadow, upper-left, left-aligned:
    Beat 1 (question)  -> visible from t=0
    Beat 2 (payoff)    -> fades in at BEAT2_AT (default 2.0s), sits below beat 1, both stay.
  Before-image INSET (our differentiator, NOT in the reference): small rounded card,
    bottom-right, static, labelled BEFORE. Reused across the whole batch (2-3 images).
  Silent audio (music attached at POST time, Char4 pattern).

Local proof (no DB):
  python render_char3_asmr_q.py local <clip> <before_image> "<beat1>" "<beat2>" [out.mp4]
"""
import os, sys, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)
try:
    from common.ffguard import run_ffmpeg_guarded
except Exception:  # standalone fallback
    def run_ffmpeg_guarded(cmd, out, secs): subprocess.run(cmd, check=True)

FF = os.environ.get("FFMPEG", "ffmpeg")
FP = os.environ.get("FFPROBE", "ffprobe")
WORK = os.environ.get("WORKDIR", os.path.join(_HERE, "work")); os.makedirs(WORK, exist_ok=True)
W, H, FPS = 1080, 1920, 30
MAX_SEG = float(os.environ.get("C3Q_MAX_SEG", "30"))
BEAT2_AT = float(os.environ.get("C3Q_BEAT2_AT", "2.0"))

# ---- accent-touch constants (from Gemini spec on the reference reel) ----
SERIF = os.environ.get("C3Q_FONT", "/System/Library/Fonts/Supplemental/Didot.ttc")
CREAM = (253, 245, 230, 255)          # warm off-white #FDF5E6, not pure white
SIZE1, SIZE2 = 60, 58
MARGIN_X = int(W * 0.11)               # ~left 11%
TOP_Y = int(H * 0.14)                  # ~top 14%
LINE_GAP = 14
BEAT_GAP = 46
MAXW = int(W * 0.72)                   # wrap width
EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"


def probe_dur(p):
    o = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", p], capture_output=True, text=True, check=True)
    return float(o.stdout.strip())


def _wrap(draw, text, font):
    lines, cur = [], ""
    for w in (text or "").split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) > MAXW and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def _draw_block(base, lines, font, top, size):
    """Left-aligned block with soft drop shadow. Returns y after the block."""
    lh = size + LINE_GAP
    # shadow layer (blurred, low-opacity, offset down-right) -> the reference's soft glow
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0)); sd = ImageDraw.Draw(shadow)
    for i, ln in enumerate(lines):
        sd.text((MARGIN_X + 4, top + i * lh + 6), ln, font=font, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(6))
    base.alpha_composite(shadow)
    d = ImageDraw.Draw(base)
    for i, ln in enumerate(lines):
        d.text((MARGIN_X, top + i * lh), ln, font=font, fill=CREAM)
    return top + len(lines) * lh


def build_beats(beat1, beat2):
    """Two full-frame transparent PNGs. png1 = beat1 only. png2 = beat2 only (positioned below beat1)."""
    try:
        f1 = ImageFont.truetype(SERIF, SIZE1); f2 = ImageFont.truetype(SERIF, SIZE2)
    except Exception:
        f1 = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", SIZE1)
        f2 = f1
    probe = Image.new("RGBA", (W, H)); pd = ImageDraw.Draw(probe)
    l1 = _wrap(pd, beat1, f1)
    # beat1 png
    p1 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    y_after = _draw_block(p1, l1, f1, TOP_Y, SIZE1)
    out1 = os.path.join(WORK, "beat1.png"); p1.save(out1)
    # beat2 png (down-arrow emoji rendered separately if present)
    b2_txt = (beat2 or "").replace("⬇️", "").strip()
    l2 = _wrap(pd, b2_txt, f2)
    p2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _draw_block(p2, l2, f2, y_after + BEAT_GAP, SIZE2)
    out2 = os.path.join(WORK, "beat2.png"); p2.save(out2)
    return out1, out2


def build_inset(before_img, label="BEFORE"):
    """Rounded before-card, subtle white border + label. ~30% width, 3:4."""
    IW, IH, RAD, BORDER = 330, 440, 26, 4
    src = Image.open(before_img).convert("RGB")
    # cover-crop to IWxIH
    sr, tr = src.width / src.height, IW / IH
    if sr > tr:
        nw = int(src.height * tr); src = src.crop(((src.width - nw) // 2, 0, (src.width + nw) // 2, src.height))
    else:
        nh = int(src.width / tr); src = src.crop((0, (src.height - nh) // 2, src.width, (src.height + nh) // 2))
    src = src.resize((IW, IH), Image.LANCZOS).convert("RGBA")
    # rounded mask
    mask = Image.new("L", (IW, IH), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, IW, IH], RAD, fill=255)
    card = Image.new("RGBA", (IW + BORDER * 2, IH + BORDER * 2), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle(
        [0, 0, IW + BORDER * 2, IH + BORDER * 2], RAD + BORDER, fill=(255, 255, 255, 235))
    card.paste(src, (BORDER, BORDER), mask)
    # label chip
    try:
        lf = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", 30)
    except Exception:
        lf = ImageFont.load_default()
    d = ImageDraw.Draw(card)
    tw = d.textlength(label, font=lf)
    d.rectangle([BORDER + 12, BORDER + 12, BORDER + 12 + tw + 24, BORDER + 12 + 42], fill=(0, 0, 0, 170))
    d.text((BORDER + 24, BORDER + 16), label, font=lf, fill=(255, 255, 255, 255))
    out = os.path.join(WORK, "inset.png"); card.save(out)
    return out


GRADE = ("eq=contrast=0.93:saturation=0.86:brightness=0.015,"
         "colorbalance=rm=0.05:gm=0.0:bm=-0.05,"
         "curves=all='0/0.03 0.5/0.5 1/0.97'")
COVER = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d" % (W, H, W, H, FPS)
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "128k", "-ar", "44100"]


def render(clip, before_img, beat1, beat2, out):
    secs = min(probe_dur(clip), MAX_SEG)
    p1, p2 = build_beats(beat1, beat2)
    inset = build_inset(before_img)
    fc = (
        "[0:v]" + COVER + "," + GRADE + "[bg];"
        "[bg][1:v]overlay=W-w-40:H-h-150[b];"            # inset bottom-right, above safe zone
        "[b][2:v]overlay=0:0[t1];"                        # beat1 always
        "[t1][3:v]overlay=0:0:enable='gte(t,%.2f)'[v]" % BEAT2_AT
    )
    cmd = [FF, "-y", "-loglevel", "error",
           "-i", clip, "-i", inset, "-i", p1, "-i", p2,
           "-f", "lavfi", "-t", str(secs), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-filter_complex", fc, "-map", "[v]", "-map", "4:a", "-t", str(secs), *ENC, out]
    run_ffmpeg_guarded(cmd, out, secs)
    return out


def main():
    if len(sys.argv) >= 5 and sys.argv[1] == "local":
        clip, before_img, beat1, beat2 = sys.argv[2:6]
        out = sys.argv[6] if len(sys.argv) > 6 else os.path.join(WORK, "proof.mp4")
        p = render(clip, before_img, beat1, beat2, out)
        print("RENDERED:", p, os.path.getsize(p), "bytes")
    else:
        raise SystemExit('usage: render_char3_asmr_q.py local <clip> <before_image> "<beat1>" "<beat2>" [out.mp4]')


if __name__ == "__main__":
    main()
