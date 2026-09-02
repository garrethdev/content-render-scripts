#!/usr/bin/env python3
"""
Viral Filler — MOVING CUTOUT variant (v0.0.1)

New format (replaces the split-screen top/bottom stack):
  - The FILLER clip fills the whole 1080x1920 frame and keeps its own audio.
  - A background-removed CHARACTER cutout (Char 2/3/4) nodding along is overlaid
    and DRIFTS smoothly around the frame. Its start position + drift path are
    seeded per video, so no two renders are pixel-identical (dup-strike safety).
  - A caption ("textbook") is burned top-center for the first few seconds, in a
    slightly different position/wording each time.

Everything is a swappable BLUEPRINT PIECE, chosen by name on the CLI or in a
JSON blueprint:
      base    -> any full-screen filler clip (path or URL)
      character -> char2 / char3 / char4  (an alpha .webm cutout)
      placement -> a named roaming zone     (roam_bottom / roam_right / roam_free)
      caption -> the text + a caption style

Usage (single video):
  python3 filler_mover.py \
      --base assets/base_XXXX.mp4 \
      --character char3 \
      --placement roam_bottom \
      --caption "when you finally stop dieting and just eat real food" \
      --seed 7 \
      --out work/filler_char3_0001.mp4

Or from a blueprint JSON (one dict, same keys as the flags):
  python3 filler_mover.py --blueprint my_video.json

Requires: ffmpeg/ffprobe with libvpx-vp9 (alpha), Pillow.
"""
import os, sys, re, json, math, random, textwrap, argparse, subprocess
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
WORK = os.path.join(HERE, "work")
os.makedirs(WORK, exist_ok=True)

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
FONT = os.environ.get("HOOK_FONT", os.path.join(ASSETS, "hook-font.ttf"))
OW, OH = 1080, 1920

# ---------------------------------------------------------------- emoji
# hook-font.ttf has no emoji glyphs, so a bare emoji rendered as a tofu box.
# We composite emoji from a real color-emoji font instead: render each emoji at
# its bitmap strike (Apple Color Emoji only exposes the 160px strike), then scale
# it inline to the caption's text size. Works without libraqm (single glyphs need
# no complex shaping). If the emoji font is missing (e.g. a non-mac render host),
# emoji are simply dropped rather than drawn as tofu.
EMOJI_FONT = os.environ.get("EMOJI_FONT", "/System/Library/Fonts/Apple Color Emoji.ttc")
_EMOJI_STRIKE = 160
_EMO_RANGES = ("\U0001F300-\U0001FAFF\U0001F000-\U0001F0FF☀-➿⬀-⯿"
               "\U0001F1E6-\U0001F1FF\U0001F3FB-\U0001F3FF️‍⃣")
_EMOJI_RUN = re.compile("[" + _EMO_RANGES + "]+")
_emoji_font_obj = "unset"
_emoji_glyphs = {}

def _emoji_font():
    global _emoji_font_obj
    if _emoji_font_obj == "unset":
        try:
            _emoji_font_obj = ImageFont.truetype(EMOJI_FONT, _EMOJI_STRIKE)
        except Exception:
            _emoji_font_obj = None
    return _emoji_font_obj

def _emoji_glyph(cluster, px):
    """RGBA image of one emoji cluster scaled to `px` tall, or None if unavailable."""
    px = max(1, int(px))
    key = (cluster, px)
    if key in _emoji_glyphs:
        return _emoji_glyphs[key]
    ef = _emoji_font()
    glyph = None
    if ef is not None:
        big = Image.new("RGBA", (_EMOJI_STRIKE * 2, _EMOJI_STRIKE * 2), (0, 0, 0, 0))
        try:
            ImageDraw.Draw(big).text((0, 0), cluster, font=ef, embedded_color=True)
            bb = big.getbbox()
            if bb:
                g = big.crop(bb)
                scale = px / float(g.height)
                glyph = g.resize((max(1, round(g.width * scale)), px), Image.LANCZOS)
        except Exception:
            glyph = None
    _emoji_glyphs[key] = glyph
    return glyph

def _rich_segments(line):
    """Split a line into ordered ('t', text) / ('e', emoji) segments."""
    segs, i = [], 0
    for m in _EMOJI_RUN.finditer(line):
        if m.start() > i:
            segs.append(("t", line[i:m.start()]))
        segs.append(("e", m.group()))
        i = m.end()
    if i < len(line):
        segs.append(("t", line[i:]))
    return segs

def _rich_width(line, font, draw, px):
    w = 0.0
    for kind, seg in _rich_segments(line):
        if kind == "t":
            w += draw.textlength(seg, font=font)
        else:
            g = _emoji_glyph(seg, px)
            if g:
                w += g.width + int(px * 0.08)
    return w

def _draw_rich(draw, img, cx, cy, line, font, px, fill, stroke_width=0, stroke_fill=None):
    """Draw `line` centered at (cx, cy), text via `font` and emoji composited inline."""
    x = cx - _rich_width(line, font, draw, px) / 2.0
    for kind, seg in _rich_segments(line):
        if kind == "t":
            draw.text((x, cy), seg, font=font, anchor="lm", fill=fill,
                      stroke_width=stroke_width, stroke_fill=stroke_fill)
            x += draw.textlength(seg, font=font)
        else:
            g = _emoji_glyph(seg, px)
            if g:
                img.alpha_composite(g, (int(round(x)), int(round(cy - g.height / 2.0))))
                x += g.width + int(px * 0.08)

# ---------------------------------------------------------------- registries
# CHARACTERS: key -> alpha cutout webm (nodding/reacting, background removed).
# Mint new ones with make_cutout.py (see README) then drop the path here.
# Variant suffixes (_v2, _v3) are DIFFERENT NOD CLIPS OF THE SAME PERSONA — different
# wardrobe / hair / angle, same identity. Spreading a batch across variants is what keeps
# any one anchor clip from repeating across the fleet (the CIB fingerprint that drove bans).
# character_id for the DB is the digit in the key: char2* -> 2, char3* -> 3, char4* -> 4.
CHARACTERS = {
    "char2":    os.path.join(ASSETS, "char2_cutout.webm"),
    "char2_v2": os.path.join(ASSETS, "char2_v2_cutout.webm"),
    "char3":    os.path.join(ASSETS, "char3_cutout.webm"),
    "char3_v2": os.path.join(ASSETS, "char3_v2_cutout.webm"),
    "char4":    os.path.join(ASSETS, "char4_cutout.webm"),
    "char4_v2": os.path.join(ASSETS, "char4_v2_cutout.webm"),
    "char4_v3": os.path.join(ASSETS, "char4_v3_cutout.webm"),
}

# PLACEMENTS: a roaming zone for the cutout's TOP-LEFT corner, as fractions of
# the frame. The cutout drifts inside [x_lo,x_hi] x [y_lo,y_hi]; the exact
# center, amplitude, periods and phases are seeded per render for uniqueness.
# Zones are chosen to NOT cover the top caption band (top ~18%).
PLACEMENTS = {
    "roam_bottom": dict(x_lo=0.02, x_hi=0.98, y_lo=0.34, y_hi=0.62),
    "roam_right":  dict(x_lo=0.40, x_hi=0.98, y_lo=0.22, y_hi=0.68),
    "roam_left":   dict(x_lo=0.02, x_hi=0.55, y_lo=0.22, y_hi=0.68),
    "roam_free":   dict(x_lo=0.02, x_hi=0.98, y_lo=0.20, y_hi=0.66),
}

# CAPTION FORMATS: the three interchangeable hook looks. The renderer rolls one
# per video (seeded) unless a specific format is forced.
#   outline    -> plate-less white text + thick black outline (the classic look)
#   black_box  -> black backdrop plate, white text (per-line boxes)
#   white_box  -> white backdrop plate, black text (per-line boxes)
CAPTION_FORMATS = ["outline", "black_box", "white_box"]
CAPTION_STYLE = dict(y_frac=0.09, dur=2.6, radius=16)   # shared geometry
CAPTION_MIN_FS_FRAC = 0.044                              # font-size floor (~48px) before dropping below the face

# ---------------------------------------------------------------- helpers
def probe(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-show_entries", "format=duration",
        "-of", "json", path], capture_output=True, text=True).stdout
    j = json.loads(out); s = j["streams"][0]
    return int(s["width"]), int(s["height"]), float(j["format"]["duration"])


def _wrap_pixels(words, font, draw, maxw):
    """Greedy word-wrap by MEASURED pixel width to a fixed box width — the way
    TikTok wraps (fill each line as full as it goes, break on word boundaries)."""
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if not cur or draw.textlength(trial, font=font) <= maxw:
            cur = trial
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def hits_bands(y0, reserve, caption_bands, m=0.015):
    """True if a block starting at y0 (frac) of height `reserve` (frac) would land
    on top of text the CLIP already has burned in. Never stack two hooks."""
    y1 = y0 + reserve
    for b0, b1 in (caption_bands or []):
        if y0 < b1 + m and y1 > b0 - m:
            return True
    return False


def choose_hook_y_frac(face, caption_bands, reserve, default=0.06):
    """Pick the hook's top (as a frame fraction) so the block covers NEITHER the
    face NOR the clip's own burned-in text. Prefer headroom above the face, else
    tuck below the face and above any existing bottom caption, else scan for any
    clear gap. Returns None when nothing is safe -> caller SKIPS our hook, which
    is the proven rule from the split-screen pipeline (never double-hook)."""
    m = 0.02
    bands = caption_bands or []
    if not face or face.get("present_frac", 0) < 0.12:
        # no reliable face: still must clear the clip's own text
        if not hits_bands(default, reserve, bands):
            return default
        for y in [round(x / 100, 2) for x in range(3, int((0.95 - reserve) * 100))]:
            if not hits_bands(y, reserve, bands):
                return y
        return None
    ft, fb = face["top"], face["bottom"]
    if 0.045 + reserve <= ft - m and not hits_bands(0.05, reserve, bands):
        return 0.05                                      # A) clear headroom above the face
    cap_top = min([b[0] for b in bands if b[0] > fb], default=0.97)
    floor = min(cap_top, 0.97) - m                       # B) below face, above bottom captions
    if floor - reserve >= fb + m and not hits_bands(floor - reserve, reserve, bands):
        return round(floor - reserve, 4)
    for y in [round(x / 100, 2) for x in range(3, int((0.95 - reserve) * 100))]:
        if y + reserve <= ft - m or y >= fb + m:         # C) any gap clearing face AND text
            if not hits_bands(y, reserve, bands):
                return y
    return None                                          # D) nowhere safe -> skip the hook


def build_caption_png(text, fmt, seed, out, style=CAPTION_STYLE,
                      face=None, caption_bands=None):
    """Full-frame transparent PNG, TikTok-style top hook, in one of three formats:
      outline   -> white text + thick black outline, NO box
      black_box -> black plate, white text
      white_box -> white plate, black text
    Wrap is PIXEL-MEASURED to a fixed text-box width (not a char count), so lines
    fill evenly. Box plates TOUCH vertically (one continuous block), dead-centered.
    Font auto-shrinks so the block never exceeds ~4 lines."""
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return None
    img = Image.new("RGBA", (OW, OH), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    words = clean.split()
    box_w = int(OW * 0.80)                        # the TikTok-ish text-box width (~864px)
    START_FS = int(OW * 0.060)                     # ~65px ExtraBold
    MIN_FS = int(OW * CAPTION_MIN_FS_FRAC)         # font-size floor
    cx = OW / 2
    top_y, m = 0.05, 0.02                          # preferred top placement + face margin

    def layout(fs):
        font = ImageFont.truetype(FONT, fs)
        pad_x, pad_y = int(fs * 0.20), int(fs * 0.10)
        lines = _wrap_pixels(words, font, d, box_w - 2 * pad_x)
        widths = [_rich_width(ln, font, d, int(fs * 0.92)) for ln in lines]
        n = len(lines)
        if n >= 2 and widths[-1] < 0.80 * max(widths[:-1]):
            groups = [list(range(0, n - 1)), [n - 1]]
        else:
            groups = [list(range(0, n))]
        asc, desc = font.getmetrics()
        line_h = asc + desc + int(fs * 0.06)
        gap = int(fs * 0.16)
        total_h = 2 * pad_y + n * line_h + (gap if len(groups) > 1 else 0)
        return dict(fs=fs, font=font, pad_x=pad_x, pad_y=pad_y, lines=lines,
                    widths=widths, n=n, groups=groups, line_h=line_h, gap=gap,
                    total_h=total_h, radius=int(fs * 0.12))

    # KEEP THE HOOK AT TOP: shrink the font (to a floor) until the block fits in
    # the headroom above the face. Only if it STILL won't fit at MIN_FS do we drop
    # it below the face (choose_hook_y_frac handles that fallback).
    face_on = bool(face) and face.get("present_frac", 0) >= 0.12
    L = None; y_frac = style["y_frac"]
    for fs in range(START_FS, MIN_FS - 1, -3):
        L = layout(fs)
        if L["n"] > 4:                             # too many lines -> keep shrinking
            continue
        h = L["total_h"] / OH
        clears_text = not hits_bands(top_y, h, caption_bands)
        if not face_on:
            if clears_text:
                y_frac = style["y_frac"]; break
            continue
        if top_y + h <= face["top"] - m and clears_text:   # fits above face AND clear of text
            y_frac = top_y; break
    if L is None:
        L = layout(MIN_FS)
    h = L["total_h"] / OH
    if (face_on and not (top_y + h <= face["top"] - m)) or hits_bands(top_y, h, caption_bands):
        # can't clear the face and/or the clip's own text from the top -> relocate
        L = layout(MIN_FS)
        y_frac = choose_hook_y_frac(face, caption_bands, L["total_h"] / OH,
                                    default=style["y_frac"])
        if y_frac is None:
            return None            # nowhere safe: skip our hook rather than double-hook

    fs = L["fs"]; font = L["font"]; pad_x, pad_y = L["pad_x"], L["pad_y"]
    lines, widths, n = L["lines"], L["widths"], L["n"]
    groups, line_h, gap, radius = L["groups"], L["line_h"], L["gap"], L["radius"]
    group_of = {i: gi for gi, idxs in enumerate(groups) for i in idxs}
    y0 = int(OH * y_frac)

    # lay out line centers top-down, inserting `gap` between groups
    cys = []
    cur = y0 + pad_y
    for i in range(n):
        if i > 0 and group_of[i] != group_of[i - 1]:
            cur += gap
        cys.append(cur + line_h / 2)
        cur += line_h

    epx = int(fs * 0.92)
    if fmt == "outline":
        for i, ln in enumerate(lines):
            _draw_rich(d, img, cx, cys[i] + 3, ln, font, epx, (0, 0, 0, 120))
            _draw_rich(d, img, cx, cys[i], ln, font, epx, (255, 255, 255, 255),
                       stroke_width=max(3, fs // 9), stroke_fill=(0, 0, 0, 255))
        img.save(out)
        return out

    box = (255, 255, 255, 255) if fmt == "white_box" else (0, 0, 0, 255)
    ink = (0, 0, 0, 255) if fmt == "white_box" else (255, 255, 255, 255)
    # one rounded rect per group, at a UNIFORM width; words then fill it
    for idxs in groups:
        gw = max(widths[i] for i in idxs)
        top = cys[idxs[0]] - line_h / 2 - pad_y
        bot = cys[idxs[-1]] + line_h / 2 + pad_y
        d.rounded_rectangle([cx - gw / 2 - pad_x, top, cx + gw / 2 + pad_x, bot],
                            radius=radius, fill=box)
    for i, ln in enumerate(lines):
        _draw_rich(d, img, cx, cys[i], ln, font, epx, ink)
    img.save(out)
    return out


def pick_caption_format(seed, forced=None):
    if forced in CAPTION_FORMATS:
        return forced
    return random.Random(seed * 31 + 3).choice(CAPTION_FORMATS)


def _smoothstep(center, half):
    """ffmpeg-expr smoothstep 0->1 centered at `center`, spanning +-half secs."""
    u = f"clip((t-({center:.3f}-{half:.3f}))/({2*half:.3f}),0,1)"
    return f"({u})*({u})*(3-2*({u}))"


def motion_from_segments(seg_src, cut_w, cut_h, seed, transition=0.7,
                         bob_px=7, sway_px=5):
    """Turn subject-aware motion segments (from motion_solver.py) into smooth,
    CONTINUOUS overlay x/y expressions. The cutout HOLDS a corner and GLIDES to
    the next corner across a short eased transition (no teleport, no chaotic
    floating). HIDE segments are collapsed to 'hold the last spot' so the reactor
    never disappears. A tiny idle bob/sway keeps it alive without wandering.
    `seg_src` may be a path, a {segments:[...]} dict, or a raw segments list."""
    if isinstance(seg_src, str):
        seg_src = json.load(open(seg_src))
    seglist = seg_src["segments"] if isinstance(seg_src, dict) else seg_src
    segs = [s for s in seglist if s.get("visible")]
    if not segs:
        return None
    # anchors = each visible segment's top-left, re-clamped for the FIXED cutout
    def clampx(nx): return max(0, min(OW - cut_w, int(round(nx * OW))))
    def clampy(ny): return max(0, min(OH - cut_h, int(round(ny * OH))))
    anchors = [(s["t0"], clampx(s["x"]), clampy(s["y"])) for s in segs]

    x0 = anchors[0][1]; y0 = anchors[0][2]
    x_terms = [f"{x0}"]; y_terms = [f"{y0}"]
    for i in range(1, len(anchors)):
        tb = anchors[i][0]                       # boundary = start time of seg i
        S = _smoothstep(tb, transition / 2.0)
        dx = anchors[i][1] - anchors[i - 1][1]
        dy = anchors[i][2] - anchors[i - 1][2]
        if dx: x_terms.append(f"({dx})*{S}")
        if dy: y_terms.append(f"({dy})*{S}")
    # idle life: gentle bob (y) + micro sway (x), seeded phase, small amplitude
    rnd = random.Random(seed)
    ph = rnd.uniform(0, 6.28)
    y_terms.append(f"{bob_px}*sin(2*PI*t/2.6+{ph:.2f})")
    x_terms.append(f"{sway_px}*sin(2*PI*t/3.7+{ph:.2f})")
    return "+".join(x_terms), "+".join(y_terms)


def static_corner_motion(placement, cut_w, cut_h, seed, bob_px=7, sway_px=5):
    """Fallback when no motion.json: park in ONE seeded corner (never center)
    with a gentle idle bob. Corners chosen from the placement zone edges."""
    rnd = random.Random(seed)
    m = int(0.03 * OW)
    corners = [(m, int(0.06 * OH)), (OW - cut_w - m, int(0.06 * OH)),
               (m, OH - cut_h - int(0.05 * OH)), (OW - cut_w - m, OH - cut_h - int(0.05 * OH))]
    cx, cy = rnd.choice(corners)
    ph = rnd.uniform(0, 6.28)
    return (f"{cx}+{sway_px}*sin(2*PI*t/3.7+{ph:.2f})",
            f"{cy}+{bob_px}*sin(2*PI*t/2.6+{ph:.2f})")


# ---------------------------------------------------------------- render
def render(base, character, placement, caption, seed, out,
           cut_h_frac=0.30, caption_format=None, max_seconds=None,
           motion_json=None, manifest=None):
    char_webm = CHARACTERS.get(character) or character
    if not os.path.exists(char_webm):
        sys.exit(f"cutout not found for character={character!r}: {char_webm}")
    fmt = pick_caption_format(seed, forced=caption_format)

    man = None
    if manifest:
        man = manifest if isinstance(manifest, dict) else json.load(open(manifest))

    _, _, base_dur = probe(base)
    dur = min(base_dur, float(max_seconds)) if max_seconds else base_dur

    cw, ch, _ = probe(char_webm)
    cut_h = int(OH * cut_h_frac); cut_w = int(round(cw * (cut_h / ch)))
    cut_w -= cut_w % 2; cut_h -= cut_h % 2

    # --- motion: prefer cached manifest segments, then a --motion-json, then fallback
    xe = ye = None
    seg_src = None
    if man:
        seg_src = man.get("pip", {}).get("segments")
    elif motion_json and os.path.exists(motion_json):
        seg_src = motion_json
    if seg_src:
        m = motion_from_segments(seg_src, cut_w, cut_h, seed)
        if m:
            xe, ye = m
            print("[motion] subject-aware glide (manifest)" if man
                  else f"[motion] subject-aware glide from {os.path.basename(motion_json)}")
    if xe is None:
        xe, ye = static_corner_motion(placement, cut_w, cut_h, seed)
        print("[motion] fallback: seeded static corner + bob")

    face = man.get("face") if man else None
    cbands = man.get("caption_bands") if man else None
    cap_png = build_caption_png(caption, fmt, seed,
                                os.path.join(WORK, f"_cap_{seed}.png"),
                                face=face, caption_bands=cbands) if caption else None
    cap_dur = CAPTION_STYLE["dur"]     # hook shows for the first ~2.6s then fades (intended)

    inputs = ["-i", base,
              "-stream_loop", "-1", "-c:v", "libvpx-vp9", "-i", char_webm]
    fc = [
        f"[0:v]scale={OW}:{OH}:force_original_aspect_ratio=increase,"
        f"crop={OW}:{OH},setsar=1,fps=30[base]",
        f"[1:v]scale={cut_w}:{cut_h},format=yuva420p[cut]",
        f"[base][cut]overlay=x='{xe}':y='{ye}':eof_action=pass:shortest=1[bg]",
    ]
    last = "bg"
    if cap_png:
        inputs += ["-loop", "1", "-framerate", "30", "-t", f"{cap_dur:.2f}", "-i", cap_png]
        fc.append(f"[2:v]format=yuva420p,fade=t=out:st={cap_dur-0.5:.2f}:d=0.5:alpha=1[cap]")
        fc.append(f"[{last}][cap]overlay=0:0:eof_action=pass[v0]")
        last = "v0"
    fc.append(f"[{last}]fps=30,format=yuv420p[outv]")
    fc.append("[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")

    cmd = [FFMPEG, "-y", "-loglevel", "error", *inputs,
           "-filter_complex", ";".join(fc),
           "-map", "[outv]", "-map", "[aout]", "-t", f"{dur:.2f}",
           "-c:v", "libx264", "-profile:v", "high", "-preset", "veryfast",
           "-crf", "21", "-maxrate", "8M", "-bufsize", "16M", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
           "-movflags", "+faststart", out]
    print(f"[render] base={os.path.basename(base)} char={character} zone={placement} "
          f"seed={seed} cut={cut_w}x{cut_h} caption={fmt} dur={dur:.1f}s")
    subprocess.run(cmd, check=True, timeout=1200)
    print("[done]", out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blueprint", help="JSON file with the same keys as the flags")
    ap.add_argument("--base"); ap.add_argument("--character", default="char3")
    ap.add_argument("--placement", default="roam_bottom")
    ap.add_argument("--caption", default="")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--cut-h-frac", type=float, default=0.30)
    ap.add_argument("--caption-format", default=None,
                    choices=CAPTION_FORMATS,
                    help="force one look; omit to roll one at random per seed")
    ap.add_argument("--manifest", default=None,
                    help="probe_base.py manifest (face-aware hook + cached PiP motion)")
    ap.add_argument("--motion-json", default=None,
                    help="segments from motion_solver.py (subject-aware glide)")
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--out")
    a = ap.parse_args()

    cfg = {}
    if a.blueprint:
        cfg = json.load(open(a.blueprint))
    def g(k, d=None): return cfg.get(k, getattr(a, k.replace("-", "_"), d))

    base = g("base")
    if not base:
        sys.exit("need --base (path or URL to the filler clip)")
    out = g("out") or os.path.join(WORK, f"filler_{g('character')}_{g('seed')}.mp4")
    render(base, g("character", "char3"), g("placement", "roam_bottom"),
           g("caption", ""), int(g("seed", 1)), out,
           cut_h_frac=float(g("cut-h-frac", g("cut_h_frac", 0.30))),
           caption_format=g("caption-format", g("caption_format")),
           max_seconds=g("max-seconds", g("max_seconds")),
           motion_json=g("motion-json", g("motion_json")),
           manifest=g("manifest"))


if __name__ == "__main__":
    main()
