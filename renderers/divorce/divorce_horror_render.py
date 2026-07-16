#!/usr/bin/env python3
"""Divorce Horror Stories Stitcher.

Executes Director EDLs exactly: reads divorce_story_content rows with
stitch_status='ready', renders 1080x1920 silent video (music added at posting),
uploads to the divorce-videos storage bucket, writes final_video back.

No creative decisions here. Text comes verbatim from the EDL.
All ffmpeg calls run through ffguard.

Every visual tunable lives in DEFAULTS below and can be overridden per video
by the Director: put a "render_config" object in the EDL jsonb using the same
keys, e.g. {"render_config": {"story_stretch": 1.1, "photo": {"width_px": 220}}}.
"""
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common.ffguard import run_ffmpeg_guarded

SUPA_URL = os.environ.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co")
BUCKET = os.environ.get("DIVORCE_BUCKET", "divorce-videos")
OUT_DIR = os.environ.get("DIVORCE_OUT_DIR", os.path.join(os.path.dirname(__file__), "out"))

# ---------------------------------------------------------------- config --
DEFAULTS = {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    # story beats play this much slower so text holds longer on screen
    # (1.21 = the locked 15% + 5% slowdown; footage slows with it, imperceptible on yoga)
    "story_stretch": 1.21,
    "photo": {
        "width_px": 200,        # before-photo size on the reveal beat (locked 7/13)
        "center_x_pct": 42,     # horizontal centre of the photo
        "bottom_y_pct": 34,     # bottom edge lands here: at her raised fingertip
        "appears_at_s": 2.0,    # seconds into the reveal beat, after the arm is up
        "fade_s": 0.25,
        "label_lines": ["230lb", "6/24"],   # small caption above the photo (locked 7/13)
        "label_size": 38,
        "label_gap_px": 12,
    },
    "text": {
        "stroke": 6,            # black halo width
        "shadow_alpha": 150,
        "shadow_blur": 6,
        "shadow_dy": 5,
        "title_size": 76,
        "hook_size": 60,
        "top_margin_px": 110,   # text never starts above this
        "max_block_pct": 40,    # text block never taller than this % of frame
        "floor_pct": 55,        # text block never sinks below this line (her zone)
    },
    "title": {
        # "wrap" (locked 7/14): TikTok-caption text-wrap lockup — black per-line boxes
        # with concave step fillets, TikTok Sans weight 900, light pink text.
        # "hook_only": hook alone. "logo": the dripping-logo treatment (unused).
        "mode": "wrap",
        "wrap_lines": ["Divorce Horror", "Story"],
        "wrap_pink": [255, 159, 243],   # #ff9ff3 (user-picked variant A)
        "wrap_size": 88,
        "wrap_pad_x": 41,       # locked 7/14: padding trimmed 10%
        "wrap_pad_y": 23,
        "wrap_radius": 30,
        "wrap_y_center_pct": 26,
        "wrap_stroke": 2,               # same-color stroke fattens strokes
        "wrap_font": "~/Claude/divorce-render/assets/TikTokSans.ttf",
        "hook_gap_px": 110,             # gap between the lockup and the hook text
        "logo_path": "~/Claude/divorce-render/assets/title_logo.png",
        "logo_width_pct": 80,
        "logo_top_pct": 10,
        "pt_size": 52,
        "pt_gap_px": 46,
    },
    "encode": {
        "crf": 18, "preset": "slow",   # x264 fallback settings
        "hw": True,                    # use h264_videotoolbox when available (5-10x faster)
        "bitrate": "10M",              # hw encoder rate for 1080x1920@30 social video
    },
    "parallel": 3,                     # videos rendered concurrently in batch mode
}

# bump when renderer code changes visuals in a way cfg doesn't capture:
# invalidates the segment cache
RENDER_CODE_VERSION = "v1"
SEG_CACHE = os.path.expanduser("~/Claude/divorce-render/segments")

FONT_CANDIDATES = [
    os.path.expanduser("~/Library/Fonts/TikTokSans-Bold.ttf"),
    os.path.expanduser("~/Library/Fonts/TikTokText-Bold.ttf"),
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def merged_config(edl):
    """DEFAULTS overridden (shallow, per section) by the EDL's render_config."""
    cfg = json.loads(json.dumps(DEFAULTS))
    override = edl.get("render_config") or {}
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


# ------------------------------------------------------------- plumbing --
def _load_secret_key():
    """Service key from local secrets (storage uploads hit RLS on the anon key)."""
    path = os.path.expanduser("~/.config/peptide-secrets/.env")
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("CAROUSEL_SUPABASE_SECRET_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("CAROUSEL_SUPABASE_SECRET_KEY not found in ~/.config/peptide-secrets/.env")


SUPA_KEY = _load_secret_key()


def api(method, path, body=None, headers=None, raw=False):
    url = SUPA_URL + path
    h = {"apikey": SUPA_KEY, "Authorization": "Bearer " + SUPA_KEY}
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = r.read()
    if raw:
        return payload
    return json.loads(payload) if payload else None


def pick_font():
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    raise SystemExit("no usable bold font found")


FONT = pick_font()


# ----------------------------------------------------------- text layout --
def wrap_lines(text, width_chars):
    return textwrap.wrap(text.strip(), width=width_chars)


def fit_text(content, cfg):
    """Choose font size + wrap so the block never becomes a face-covering wall."""
    n = len(content)
    if n < 120:
        size, wrap = 58, 26
    elif n < 200:
        size, wrap = 50, 28
    elif n < 280:
        size, wrap = 42, 30
    else:
        size, wrap = 38, 32
    lines = wrap_lines(content, wrap)
    max_h = cfg["height"] * cfg["text"]["max_block_pct"] / 100
    while size > 34 and len(lines) * size * 1.32 > max_h:
        size -= 2
        lines = wrap_lines(content, wrap + 2)
    return lines, size


def draw_text_block(draw, img, lines, fontsize, y_center, tcfg):
    """Locked caption style: bold white fill, black halo (stroke + soft shadow)."""
    stroke = tcfg["stroke"]
    font = ImageFont.truetype(FONT, fontsize)
    line_gap = int(fontsize * 0.28)
    heights = []
    for ln in lines:
        box = draw.textbbox((0, 0), ln, font=font, stroke_width=stroke)
        heights.append(box[3] - box[1])
    total_h = sum(heights) + line_gap * (len(lines) - 1)
    y = y_center - total_h // 2

    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    yy = y
    for ln, hh in zip(lines, heights):
        box = sdraw.textbbox((0, 0), ln, font=font, stroke_width=stroke)
        x = (img.width - (box[2] - box[0])) // 2
        sdraw.text((x, yy + tcfg["shadow_dy"]), ln, font=font,
                   fill=(0, 0, 0, tcfg["shadow_alpha"]),
                   stroke_width=stroke, stroke_fill=(0, 0, 0, tcfg["shadow_alpha"]))
        yy += hh + line_gap
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(tcfg["shadow_blur"])))

    yy = y
    for ln, hh in zip(lines, heights):
        box = draw.textbbox((0, 0), ln, font=font, stroke_width=stroke)
        x = (img.width - (box[2] - box[0])) // 2
        draw.text((x, yy), ln, font=font, fill=(255, 255, 255, 255),
                  stroke_width=stroke, stroke_fill=(10, 10, 10, 230))
        yy += hh + line_gap
    return y + total_h


# -------------------------------------------------------------- overlays --
def make_text_png(beat, cfg, workdir, idx, part_label):
    """Full-frame transparent text overlay for one beat (empty for reveal beats)."""
    W, H = cfg["width"], cfg["height"]
    tcfg = cfg["text"]
    t = beat.get("text") or {}
    kind = str(t.get("kind", "caption")).lower()
    role = str(beat.get("role", "")).lower()
    y_center = int(H * float(beat.get("y_pct", 25)) / 100)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    is_title = (role == "hook" or kind in ("title_hook", "title_card", "title")
                or (t.get("hook") and not t.get("content")))
    no_text = (role == "reveal" or kind == "none" or
               (not t.get("content") and not t.get("hook") and not is_title))

    if is_title:
        lcfg = cfg.get("title", {})
        mode = lcfg.get("mode", "hook_only")
        logo_path = os.path.expanduser(lcfg.get("logo_path", ""))
        if mode == "wrap":
            block_bottom = draw_wrap_title(img, lcfg, W, H)
            draw_text_block(draw, img, wrap_lines(t.get("hook", ""), 22),
                            tcfg["hook_size"],
                            block_bottom + lcfg.get("hook_gap_px", 110), tcfg)
        elif mode == "logo" and logo_path and os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            lw = int(W * lcfg.get("logo_width_pct", 80) / 100)
            lh = int(logo.height * lw / logo.width)
            logo = logo.resize((lw, lh))
            ly = int(H * lcfg.get("logo_top_pct", 10) / 100)
            img.alpha_composite(logo, ((W - lw) // 2, ly))
            bottom = ly + lh + lcfg.get("pt_gap_px", 46)
            if part_label:
                bottom = draw_text_block(draw, img, [part_label],
                                         lcfg.get("pt_size", 52),
                                         bottom + lcfg.get("pt_size", 52) // 2, tcfg)
            draw_text_block(draw, img, wrap_lines(t.get("hook", ""), 24),
                            tcfg["hook_size"],
                            bottom + lcfg.get("hook_gap_px", 60), tcfg)
        else:
            draw_text_block(draw, img, wrap_lines(t.get("hook", ""), 22),
                            tcfg["hook_size"], max(y_center, 300), tcfg)
    elif not no_text:
        content = t.get("content", "")
        lines, size = fit_text(content, cfg)
        block_h = int(len(lines) * size * 1.32)
        y_min = block_h // 2 + tcfg["top_margin_px"]
        y_max = int(H * tcfg["floor_pct"] / 100) - block_h // 2
        draw_text_block(draw, img, lines, size,
                        max(min(y_center, max(y_max, y_min)), y_min), tcfg)

    path = os.path.join(workdir, f"txt_{idx:02d}.png")
    img.save(path)
    return path


def draw_wrap_title(img, lcfg, W, H):
    """The locked title lockup: per-line black boxes fused with concave step fillets
    (TikTok caption silhouette), TikTok Sans weight 900, light pink. Returns block bottom y."""
    font = ImageFont.truetype(os.path.expanduser(lcfg["wrap_font"]), int(lcfg["wrap_size"]))
    try:
        font.set_variation_by_axes([36, 100, 900, 0])  # opsz / width / WEIGHT / slant
    except Exception:
        pass
    stroke = int(lcfg.get("wrap_stroke", 2))
    pad_x, pad_y = int(lcfg["wrap_pad_x"]), int(lcfg["wrap_pad_y"])
    radius = int(lcfg["wrap_radius"])
    pink = tuple(lcfg["wrap_pink"]) + (255,)
    lines = lcfg["wrap_lines"]

    probe = ImageDraw.Draw(img)
    metrics = []
    for ln in lines:
        b = probe.textbbox((0, 0), ln, font=font, stroke_width=stroke)
        metrics.append((ln, b, b[2] - b[0]))
    line_h = max(b[3] - b[1] for _, b, _ in metrics) + pad_y * 2
    top = int(H * lcfg["wrap_y_center_pct"] / 100) - (line_h * len(metrics)) // 2

    boxes = []
    y = top
    for ln, b, tw in metrics:
        bw = tw + pad_x * 2
        boxes.append(((W - bw) // 2, y, bw, line_h))
        y += line_h

    # mask drawn 4x supersampled then downscaled: smooth antialiased silhouette
    SS = 4
    mss = Image.new("L", (W * SS, H * SS), 0)
    md = ImageDraw.Draw(mss)
    R = radius * SS
    B = [(x * SS, y * SS, w * SS, h * SS) for (x, y, w, h) in boxes]
    for (bx, by, bw, bh) in B:
        md.rounded_rectangle([bx, by, bx + bw, by + bh], radius=R, fill=255)
    for i in range(len(B) - 1):
        x1, y1, w1, h1 = B[i]
        x2, y2, w2, h2 = B[i + 1]
        yj = y1 + h1
        narrow_l, narrow_r = max(x1, x2), min(x1 + w1, x2 + w2)
        md.rectangle([narrow_l, yj - R, narrow_r, yj + R], fill=255)
        if w1 > w2:
            md.rectangle([x2 - R, yj, x2, yj + R], fill=255)
            md.rectangle([x2 + w2, yj, x2 + w2 + R, yj + R], fill=255)
            md.ellipse([x2 - 2 * R, yj, x2, yj + 2 * R], fill=0)
            md.ellipse([x2 + w2, yj, x2 + w2 + 2 * R, yj + 2 * R], fill=0)
        elif w2 > w1:
            md.rectangle([x1 - R, yj - R, x1, yj], fill=255)
            md.rectangle([x1 + w1, yj - R, x1 + w1 + R, yj], fill=255)
            md.ellipse([x1 - 2 * R, yj - 2 * R, x1, yj], fill=0)
            md.ellipse([x1 + w1, yj - 2 * R, x1 + w1 + 2 * R, yj], fill=0)
    mask = mss.resize((W, H), Image.LANCZOS)

    black = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    img.paste(black, (0, 0), mask)
    od = ImageDraw.Draw(img)
    y = top
    for ln, b, tw in metrics:
        tx = (W - tw) // 2 - b[0]
        ty = y + (line_h - (b[3] - b[1])) // 2 - b[1]
        od.text((tx, ty), ln, font=font, fill=pink, stroke_width=stroke, stroke_fill=pink)
        y += line_h
    return top + line_h * len(lines)


def make_photo_png(before_img, cfg, workdir, idx):
    """Reveal-beat overlay: the plain before photo (no border), bottom edge at her fingertip.
    A small label (weight / date) sits just above the photo in the house caption style."""
    W, H = cfg["width"], cfg["height"]
    pcfg = cfg["photo"]
    photo = Image.open(before_img).convert("RGBA")
    w = int(pcfg["width_px"])
    photo = photo.resize((w, int(w * photo.height / photo.width)))

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cx = int(W * pcfg["center_x_pct"] / 100) - photo.width // 2
    cy = max(int(H * pcfg["bottom_y_pct"] / 100) - photo.height, 70)

    label_lines = pcfg.get("label_lines") or []
    if label_lines:
        size = int(pcfg.get("label_size", 38))
        gap = int(pcfg.get("label_gap_px", 12))
        stroke = max(3, int(size * 0.1))
        font = ImageFont.truetype(FONT, size)
        draw = ImageDraw.Draw(img)
        line_h = int(size * 1.25)
        block_h = line_h * len(label_lines)
        # keep the photo's bottom anchored: shift nothing, draw label above the photo top
        ly = cy - gap - block_h
        if ly < 40:  # not enough headroom: nudge photo down instead
            cy = 40 + block_h + gap
            ly = 40
        photo_cx = cx + photo.width // 2
        for ln in label_lines:
            box = draw.textbbox((0, 0), ln, font=font, stroke_width=stroke)
            lx = photo_cx - (box[2] - box[0]) // 2
            draw.text((lx, ly), ln, font=font, fill=(255, 255, 255, 255),
                      stroke_width=stroke, stroke_fill=(10, 10, 10, 230))
            ly += line_h

    img.alpha_composite(photo, (cx, cy))
    path = os.path.join(workdir, f"photo_{idx:02d}.png")
    img.save(path)
    return path


# -------------------------------------------------------------- rendering --
def beat_out_duration(beat, cfg):
    src = float(beat["trim_end"]) - float(beat["trim_start"])
    if str(beat.get("role", "")).lower() == "story":
        return src * cfg["story_stretch"]
    return src


def _hw_encoder_available():
    try:
        out = subprocess.check_output(["ffmpeg", "-hide_banner", "-encoders"],
                                      stderr=subprocess.DEVNULL).decode()
        return "h264_videotoolbox" in out
    except Exception:
        return False


HW_OK = _hw_encoder_available()


def segment_cache_key(beat, clip, cfg, part_label, before_photo_url):
    """Everything that determines this segment's pixels. Same key => reuse the file."""
    try:
        st = os.stat(clip["file_url"])
        clip_id = f"{clip['file_url']}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        clip_id = clip["file_url"]
    payload = json.dumps({
        "v": RENDER_CODE_VERSION, "clip": clip_id, "beat": beat,
        "cfg": cfg, "part": part_label,
        "photo": before_photo_url if beat.get("overlay_before_photo") else None,
    }, sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()


def render_beat(beat, clip, cfg, workdir, idx, part_label, before_img=None,
                before_photo_url=None):
    """Render one timeline beat, reusing the persistent segment cache when possible."""
    src = clip["file_url"]
    if not os.path.exists(src):
        raise RuntimeError(f"clip file missing: {src}")

    os.makedirs(SEG_CACHE, exist_ok=True)
    key = segment_cache_key(beat, clip, cfg, part_label, before_photo_url)
    cached = os.path.join(SEG_CACHE, f"{key}.mp4")
    if os.path.exists(cached) and os.path.getsize(cached) > 10000:
        return cached, True

    W, H, FPS = cfg["width"], cfg["height"], cfg["fps"]
    role = str(beat.get("role", "")).lower()
    src_dur = float(beat["trim_end"]) - float(beat["trim_start"])
    out_dur = beat_out_duration(beat, cfg)
    stretch = out_dur / src_dur if src_dur else 1.0
    seg = os.path.join(workdir, f"seg_{idx:02d}.mp4")

    bg = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    if abs(stretch - 1.0) > 1e-3:
        bg += f",setpts={stretch:.4f}*PTS"
    bg += f",fps={FPS}"
    if beat.get("transition") == "zoom_in":
        frames = max(int(out_dur * FPS), 1)
        bg += (f",zoompan=z='min(1+0.06*on/{frames},1.06)':d=1"
               f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}")

    text_png = make_text_png(beat, cfg, workdir, idx, part_label)
    inputs = ["-ss", str(beat["trim_start"]), "-t", f"{src_dur:.3f}", "-i", src, "-i", text_png]
    fc = f"[0:v]{bg}[bg];[bg][1:v]overlay=0:0:format=auto[v1]"
    last = "[v1]"

    # the before photo exists only on the reveal beat, appearing after she points up
    if role == "reveal" and beat.get("overlay_before_photo") and before_img:
        pcfg = cfg["photo"]
        photo_png = make_photo_png(before_img, cfg, workdir, idx)
        inputs += ["-loop", "1", "-t", f"{out_dur:.3f}", "-i", photo_png]
        fc += (f";[2:v]format=rgba,fade=in:st={pcfg['appears_at_s']}:d={pcfg['fade_s']}:alpha=1[ph]"
               f";[v1][ph]overlay=0:0:format=auto:enable='gte(t,{pcfg['appears_at_s']})'[v2]")
        last = "[v2]"

    ecfg = cfg["encode"]
    if ecfg.get("hw") and HW_OK:
        vcodec = ["-c:v", "h264_videotoolbox", "-b:v", str(ecfg.get("bitrate", "10M"))]
    else:
        vcodec = ["-c:v", "libx264", "-crf", str(ecfg["crf"]), "-preset", ecfg["preset"]]
    cmd = (["ffmpeg", "-y", "-loglevel", "error"] + inputs +
           ["-filter_complex", fc, "-map", last, "-an"] + vcodec +
           ["-pix_fmt", "yuv420p", seg])
    run_ffmpeg_guarded(cmd, seg, expected_seconds=out_dur, verbose=False)
    shutil.move(seg, cached)     # atomic publish into the cache
    return cached, False


def stitch(row, clips_by_id):
    content_id = row["content_id"]
    edl = row["edl"]
    cfg = merged_config(edl)
    part_label = f"Pt {row.get('part_number', '')}".strip()
    timeline = sorted(edl["timeline"], key=lambda b: b["seq"])
    workdir = tempfile.mkdtemp(prefix=f"stitch_{content_id}_")
    try:
        before_img = None
        if row.get("before_photo_url") and any(b.get("overlay_before_photo") for b in timeline):
            before_img = os.path.join(workdir, "before_photo.img")
            with urllib.request.urlopen(row["before_photo_url"], timeout=60) as r, open(before_img, "wb") as f:
                f.write(r.read())

        segs, hits = [], 0
        for i, beat in enumerate(timeline):
            clip = clips_by_id.get(beat["clip_id"])
            if not clip:
                raise RuntimeError(f"unknown clip_id {beat['clip_id']}")
            seg, from_cache = render_beat(beat, clip, cfg, workdir, i, part_label,
                                          before_img=before_img,
                                          before_photo_url=row.get("before_photo_url"))
            segs.append(seg)
            hits += from_cache

        concat_list = os.path.join(workdir, "concat.txt")
        with open(concat_list, "w") as f:
            for s in segs:
                f.write(f"file '{s}'\n")

        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, f"{content_id}.mp4")
        total = sum(beat_out_duration(b, cfg) for b in timeline)
        run_ffmpeg_guarded(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", concat_list, "-c", "copy", out],
            out, expected_seconds=total, verbose=False)

        probed = float(subprocess.check_output(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", out]).decode().strip())
        if abs(probed - total) > 1.5:
            raise RuntimeError(f"duration drift: got {probed:.1f}s, expected {total:.1f}s")

        with open(out, "rb") as f:
            data = f.read()
        api("POST", f"/storage/v1/object/{BUCKET}/{content_id}.mp4", body=data,
            headers={"Content-Type": "video/mp4", "x-upsert": "true"}, raw=True)
        public_url = f"{SUPA_URL}/storage/v1/object/public/{BUCKET}/{content_id}.mp4"

        api("PATCH", f"/rest/v1/divorce_story_content?content_id=eq.{content_id}",
            body={"final_video": public_url, "stitch_status": "done"},
            headers={"Prefer": "return=minimal"})
        print(f"[{content_id}] DONE {probed:.1f}s ({hits}/{len(timeline)} segments cached) -> {public_url}")
        return True
    except Exception as e:
        print(f"[{content_id}] FAILED: {e}")
        try:
            api("PATCH", f"/rest/v1/divorce_story_content?content_id=eq.{content_id}",
                body={"stitch_status": "stitch_failed", "audit_notes": f"stitch error: {str(e)[:300]}"},
                headers={"Prefer": "return=minimal"})
        except Exception:
            pass
        return False
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    q = "/rest/v1/divorce_story_content?select=content_id,part_number,edl,before_photo_url&edl=not.is.null"
    if only:
        # explicit target: also retry after a previous failure or redo a done row
        q += f"&content_id=eq.{only}&stitch_status=in.(ready,stitch_failed,done)"
    else:
        q += "&stitch_status=eq.ready"
    rows = api("GET", q)
    if not rows:
        print("nothing ready to stitch")
        return
    clips = api("GET", "/rest/v1/divorce_source_clips?select=id,file_url,duration_s")
    clips_by_id = {c["id"]: c for c in clips}
    workers = int(DEFAULTS.get("parallel", 3)) if len(rows) > 1 else 1
    print(f"stitching {len(rows)} video(s), {workers} parallel, "
          f"encoder {'videotoolbox' if HW_OK else 'x264'}, font {os.path.basename(FONT)}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda r: stitch(r, clips_by_id), rows))
    print(f"finished: {sum(results)}/{len(rows)} succeeded")


if __name__ == "__main__":
    main()
