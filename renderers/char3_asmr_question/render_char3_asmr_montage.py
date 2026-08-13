#!/usr/bin/env python3
"""Char3 ASMR "weightlifting question" MONTAGE renderer — recreates IG reel DbJi1GwJH2i.

Layout (see DIRECTOR_STITCH.md for the blueprint the n8n director produces):
  - Fast-ish montage of weightlifting-library clips, EACH CLIP USED ONCE (no repeats),
    varied length + order, tightened to a mid-rep window, continuity-grouped, 15-25s total.
  - Two centered cream-serif text slides, upper third, soft top scrim + heavy shadow:
      SLIDE 1 (hook question)  visible from t=0
      SLIDE 2 (payoff)         fades in at beat2_at (<3s), sits below slide 1, both stay
    Trailing emoji on a payoff is rendered in colour (Apple Color Emoji).
  - Full-frame, no inset. Warm filmic look inherited from the clips. Silent (music at post).

Usage:
  # self-blueprint from a hook number (deterministic, no DB needed):
  render_char3_asmr_montage.py auto <hook_no> "<hook>" "<payoff>" <out.mp4> [clipsdir]
  # execute a blueprint JSON (what the n8n Director-Stitch writes to char3_asmr_hooks.blueprint):
  render_char3_asmr_montage.py blueprint <blueprint.json> <out.mp4> [clipsdir]
"""
import os, sys, json, subprocess, hashlib, re
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
SERIF = os.environ.get("C3Q_FONT", "/System/Library/Fonts/Supplemental/Didot.ttc")
EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"
CREAM = (253, 245, 230, 255)
COVER = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CLIPS = os.environ.get("C3Q_CLIPS", os.path.join(_HERE, "clips"))
BEFORE_DIR = os.environ.get("C3Q_BEFORE", os.path.join(_HERE, "before"))
CTA_VARIANTS = [
    "My cheat code was in the comments.",
    "The cheat code's in the comments 👇",
    "I left the cheat code in the comments.",
    "Cheat code? It's in the comments.",
    "My secret's in the comments 👇",
    "The missing piece is in the comments.",
]
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF⬀-⯿←-⇿⌀-⏿]")


def probe(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip())


def _seed(n):
    return int(hashlib.md5(str(n).encode()).hexdigest(), 16)


def auto_blueprint(hook_no, hook, payoff, clipsdir):
    """Mirror of the n8n Director-Stitch logic, for local/no-DB rendering."""
    clips = sorted([f for f in os.listdir(clipsdir) if f.endswith(".mp4")])
    s = _seed(hook_no)
    # Vary the FIRST clip heavily across videos: seeded Fisher-Yates shuffle of the whole
    # pool (deterministic per hook_no) so consecutive hooks do not open on the same clip.
    ordered = clips[:]
    r = s
    for i in range(len(ordered) - 1, 0, -1):
        r = (r * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        j = r % (i + 1)
        ordered[i], ordered[j] = ordered[j], ordered[i]
    total = 18 + (s % 8)                        # 18-25s (keeps BEFORE inset at ~8-10s)
    n = len(ordered)
    base = total / n
    segs = []
    for i, c in enumerate(ordered):
        length = round(base + (((s >> (i + 1)) % 100) / 100.0 - 0.5) * 1.4, 2)  # jitter +-0.7s
        length = max(2.3, min(4.6, length))
        dur = probe(os.path.join(clipsdir, c))
        win = max(0.0, dur - length - 0.2)
        tin = round((((s >> (i + 2)) % 1000) / 1000.0) * win, 2)
        segs.append({"clip": c, "in_sec": tin, "len_sec": length})
    beat2 = round(1.8 + (s % 8) / 10.0, 2)      # 1.8-2.5s, hook <3s
    return {"total_target_sec": total, "beat2_at_sec": beat2,
            "segments": segs, "text": {"slide1": hook, "slide2": payoff}}


# ---------- text rendering (centered serif + scrim + shadow + colour emoji) ----------

def _wrap(draw, text, font, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) > maxw and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def _emoji_img(ch, px):
    """Render a single colour emoji to an RGBA image ~px tall."""
    for sz in (160, 137, 96):
        try:
            f = ImageFont.truetype(EMOJI_FONT, sz)
            im = Image.new("RGBA", (sz + 20, sz + 20), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
            bb = im.getbbox()
            if bb:
                im = im.crop(bb)
            scale = px / im.height
            return im.resize((max(1, int(im.width * scale)), px), Image.LANCZOS)
        except Exception:
            continue
    return None


def slide_png(text, out, size=60):
    """Render ONE centered cream-serif text block in the upper third, with scrim,
    heavy shadow, and a trailing colour emoji if present."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    f = ImageFont.truetype(SERIF, size)
    maxw = int(W * 0.80)
    m = _EMOJI_RE.search(text or "")
    emoji = m.group() if m else None
    txt = _EMOJI_RE.sub("", text).strip() if emoji else text
    lines = _wrap(d, txt, f, maxw)
    geo = []
    y = int(H * 0.15)
    for i, ln in enumerate(lines):
        tw = d.textlength(ln, font=f)
        emo = emoji if (i == len(lines) - 1 and emoji) else None
        ew = (f.size + 6) if emo else 0
        x = (W - tw - ew) // 2
        geo.append((ln, f, x, y, emo)); y += f.size + 12

    # top scrim (dark -> transparent over top 42%)
    scrim = Image.new("L", (1, H), 0); band = int(H * 0.42)
    for yy in range(H):
        scrim.putpixel((0, yy), int(120 * max(0.0, 1 - yy / band)) if yy < band else 0)
    black = Image.new("RGBA", (W, H), (0, 0, 0, 255)); black.putalpha(scrim.resize((W, H)))
    img.alpha_composite(black)

    # heavy shadow
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sd = ImageDraw.Draw(sh)
    for ln, font, x, yy, emo in geo:
        for dx, dy in ((3, 3), (-2, 2), (2, -2), (0, 4)):
            sd.text((x + dx, yy + dy), ln, font=font, fill=(0, 0, 0, 180))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(7)))

    # text + trailing emoji
    for ln, font, x, yy, emo in geo:
        d.text((x, yy), ln, font=font, fill=CREAM)
        if emo:
            tw = d.textlength(ln, font=font)
            ei = _emoji_img(emo, font.size)
            if ei:
                img.alpha_composite(ei, (int(x + tw + 8), int(yy)))
    img.save(out); return out


def before_card(before_path, out):
    """Plain rectangular before image in the bottom-right corner — no border, no rounded
    corners, no card/shadow. Just the photo dropped in, with a plain 'BEFORE' label."""
    from PIL import ImageOps
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cw, ch = int(W * 0.32), int(W * 0.32 * 1.5)
    src = ImageOps.fit(Image.open(before_path).convert("RGB"), (cw, ch), Image.LANCZOS).convert("RGBA")
    mx, my = int(W * 0.03), int(H * 0.03)
    px, py = W - cw - mx, H - ch - my
    canvas.alpha_composite(src, (px, py))
    # plain BEFORE label (white text + soft shadow, no box)
    lf = ImageFont.truetype(SERIF, 34)
    d = ImageDraw.Draw(canvas)
    lx, ly = px + 16, py + 12
    for dx, dy in ((2, 2), (-1, 1), (1, -1)):
        d.text((lx + dx, ly + dy), "BEFORE", font=lf, fill=(0, 0, 0, 190))
    d.text((lx, ly), "BEFORE", font=lf, fill=(255, 255, 255, 255))
    canvas.save(out); return out


# ---------------------------- montage assembly ----------------------------

def render(bp, out, clipsdir):
    seed = hashlib.md5(json.dumps(bp["text"], sort_keys=True).encode()).hexdigest()[:8]
    work = os.path.join(os.path.dirname(os.path.abspath(out)), "work_" + seed); os.makedirs(work, exist_ok=True)
    parts = []
    for i, seg in enumerate(bp["segments"]):
        src = seg["clip"] if os.path.isabs(seg["clip"]) else os.path.join(clipsdir, seg["clip"])
        p = os.path.join(work, f"seg{i}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(seg["in_sec"]),
                        "-t", str(seg["len_sec"]), "-i", src, "-vf", COVER, "-an",
                        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", p], check=True)
        parts.append(p)
    lst = os.path.join(work, "list.txt"); open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    montage = os.path.join(work, "montage.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", montage], check=True)
    total = probe(montage)
    # sequential text: hook 0->b2at, payoff b2at->b2at+pdur, then NO text.
    hook = bp["text"]["slide1"]; payoff = bp["text"]["slide2"]
    b2at = bp.get("beat2_at_sec", 2.4)
    words = len((payoff or "").split())
    pdur = max(4.0, min(7.0, round(words * 0.42, 1)))   # readable dwell for the payoff
    # before-image inset: ~8-10s in, 4s long (clamped inside the clip)
    before_img = bp.get("before_image") or _pick(BEFORE_DIR, ".png", bp)
    before_at = bp.get("before_at_sec", min(9.0, max(8.0, total * 0.45)))
    before_dur = bp.get("before_dur_sec", 4.0)
    before_at = min(before_at, max(0.0, total - before_dur - 3.5))   # leave room for CTA
    # end CTA
    cta = bp.get("cta") or CTA_VARIANTS[int(hashlib.md5(hook.encode()).hexdigest(), 16) % len(CTA_VARIANTS)]
    cta_dur = 3.2
    cta_at = round(total - cta_dur, 2)

    t_hook = slide_png(hook, os.path.join(work, "t_hook.png"), size=62)
    t_pay = slide_png(payoff, os.path.join(work, "t_pay.png"), size=56)
    t_cta = slide_png(cta, os.path.join(work, "t_cta.png"), size=64)
    bcard = before_card(before_img, os.path.join(work, "before.png")) if before_img else None

    inputs = ["-i", montage, "-i", t_hook, "-i", t_pay, "-i", t_cta]
    fc = (f"[0][1]overlay=0:0:enable='lt(t,{b2at})'[a];"
          f"[a][2]overlay=0:0:enable='between(t,{b2at},{b2at + pdur})'[b];"
          f"[b][3]overlay=0:0:enable='gte(t,{cta_at})'[c]")
    last = "c"
    if bcard:
        inputs += ["-i", bcard]
        fc += f";[{last}][4]overlay=0:0:enable='between(t,{before_at},{before_at + before_dur})'[v]"
        last = "v"
    else:
        fc = fc[:-3] + "[v]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc,
                    "-map", f"[{last}]", "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-metadata", "make=Apple", "-metadata", "model=iPhone 15 Pro", out], check=True)
    print("RENDERED", out, round(probe(out), 2), "s,", len(parts), "clips | payoff",
          round(b2at, 1), "-", round(b2at + pdur, 1), "| before", round(before_at, 1), "-",
          round(before_at + before_dur, 1), "| cta", cta_at, "-> end | \"" + cta + "\"")


def _pick(d, ext, bp):
    if not os.path.isdir(d):
        return None
    opts = sorted([os.path.join(d, f) for f in os.listdir(d) if f.endswith(ext)])
    if not opts:
        return None
    s = int(hashlib.md5(json.dumps(bp["text"], sort_keys=True).encode()).hexdigest(), 16)
    return opts[s % len(opts)]


def main():
    mode = sys.argv[1]
    if mode == "auto":
        hook_no, hook, payoff, out = sys.argv[2:6]
        clipsdir = sys.argv[6] if len(sys.argv) > 6 else DEFAULT_CLIPS
        bp = auto_blueprint(hook_no, hook, payoff, clipsdir)
        render(bp, out, clipsdir)
    elif mode == "blueprint":
        bp = json.load(open(sys.argv[2])); out = sys.argv[3]
        clipsdir = sys.argv[4] if len(sys.argv) > 4 else DEFAULT_CLIPS
        render(bp, out, clipsdir)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
