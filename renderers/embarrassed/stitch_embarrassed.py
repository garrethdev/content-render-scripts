#!/usr/bin/env python3
"""
Embarrassed Content Angle stitcher.

Final video = 3 clips, in this order:
  1. BEGINNING — character reaction (4s, crash zoom @2s, jitter)   [fixed, reused]
  2. VIRAL     — the embarrassing clip, per content row            [from library cache]
  3. END       — kitchen + pen, before-photo overlaid on point-up  [fixed, reused]

No transitions. All clips normalized to 1080x1920 / 30fps / AAC 44.1k, then concat.

After concat + hook, two fixed VO lines (Seed Audio 1.0, cloned voice) are baked in:
the BEGIN line over the reaction and the CTA line over the END reveal, with the tail
trimmed. See the VO_* constants below — placement is anchored to the clip structure so
it's consistent across every render.

Usage:
  python stitch_embarrassed.py --content_id 61          # one row
  python stitch_embarrassed.py                          # all waiting_render rows
  # --begin / --end override the fixed character clips (else env or defaults)
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import urllib.request

# ── env ──────────────────────────────────────────────────────────────────────
_ENV_FILE = os.path.expanduser("~/.config/peptide-secrets/.env")

def _load_env(path=_ENV_FILE):
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_env()

SB_URL = "https://qlcmgxgwpzmiebzxflai.supabase.co"
SB_KEY = (os.environ.get("CAROUSEL_SUPABASE_SECRET_KEY")
          or os.environ.get("CAROUSEL_SUPABASE_PUBLISHABLE_KEY"))
if not SB_KEY:
    sys.exit("ERROR: CAROUSEL_SUPABASE_SECRET_KEY not found in env. Check ~/.config/peptide-secrets/.env")

FF = os.environ.get("FFMPEG",  "/opt/homebrew/bin/ffmpeg")
FP = os.environ.get("FFPROBE", "/opt/homebrew/bin/ffprobe")

_HERE      = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.environ.get("EMBARRASSED_CACHE_DIR",  os.path.join(_HERE, "cache"))
RENDER_DIR = os.environ.get("EMBARRASSED_RENDER_DIR", os.path.join(_HERE, "renders"))
CHAR_DIR   = os.path.join(_HERE, "character")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(RENDER_DIR, exist_ok=True)

# Fixed, reused character clips
DEFAULT_BEGIN = os.environ.get("EMBARRASSED_BEGIN_CLIP", os.path.join(CHAR_DIR, "beginning_clip_edited.mp4"))
DEFAULT_END   = os.environ.get("EMBARRASSED_END_CLIP",   os.path.join(CHAR_DIR, "end_clip_with_before.mp4"))

# Fixed, reused voiceover (Seed Audio 1.0, cloned "Character 3" voice). Two lines, baked
# into every render at a consistent position anchored to the clip structure:
#   • BEGIN VO  ("Guuurl, that COULD never be me!") starts VO_BEGIN_START into the reaction.
#   • END VO    ("If losing weight scares you… keep scrolling") starts VO_END_LEAD into the
#     END (kitchen reveal) clip — anchored to END-start so it lands the same on every video
#     regardless of viral length.
#   • VO_TAIL_TRIM seconds are cut off the very end after the CTA finishes.
VO_BEGIN_CLIP   = os.environ.get("EMBARRASSED_VO_BEGIN", os.path.join(CHAR_DIR, "vo_begin.wav"))
VO_END_CLIP     = os.environ.get("EMBARRASSED_VO_END",   os.path.join(CHAR_DIR, "vo_end.wav"))
VO_BEGIN_START  = 2.0    # seconds into the video (≈ mid-reaction)
VO_END_LEAD     = 0.4    # seconds into the END clip before the CTA speaks
VO_TAIL_TRIM    = 2.0    # seconds trimmed off the final end
VO_DUCK         = 0.2    # original audio level under the BEGIN VO
VO_DUCK_PAD     = 0.15   # extra duck time after the BEGIN VO ends

# Text-hook style — matches the dating-reaction-video "halo" caption (white + thick black border)
HOOK_FONT = os.path.join(_HERE, "assets", "TikTokSans-ExtraBold.ttf")

TARGET_W, TARGET_H = 1080, 1920
TARGET_FPS = 30
SOURCE_TABLE  = "embarrassed_angle_sources"
CONTENT_TABLE = "embarrassed_angle_content"

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
if OPENROUTER_KEY:  # env stores some keys wrapped in quotes -> strip or the API 401s
    OPENROUTER_KEY = OPENROUTER_KEY.strip().strip('"').strip("'")

# Reuse variation: when a source is re-hooked (content_id version >= 4), the viral segment is
# subtly reframed (zoom + off-center crop) so the re-post isn't a pixel-identical duplicate.
# Each version gets a distinct framing. A horizontal mirror is ALSO applied, but ONLY when the
# source has no burned-in on-screen text (a flip would reverse readable text) — see
# detect_onscreen_text(); the default is NO flip whenever text presence is unknown/uncertain.
# dx/dy are FIXED pixel offsets from the centered crop, clamped to the frame — a fractional
# offset would scale with the source's leftover width and shove the subject off-frame entirely
# on square/landscape sources (leftover ≈130px on 9:16 but 600-2700px on square/16:9).
REUSE_REFRAME = {
    4: {"sw": 1210, "sh": 2150, "dx": -120, "dy": -80},   # zoom ~1.12, nudge left + up
    5: {"sw": 1210, "sh": 2150, "dx":  120, "dy":   0},   # zoom ~1.12, nudge right
    6: {"sw": 1274, "sh": 2266, "dx":    0, "dy": -160},  # zoom ~1.18, tighter, raised focus
}

def _reuse_version(content_id_str):
    m = re.search(r"-V(\d+)$", content_id_str or "")
    return int(m.group(1)) if m else 1

# ── Supabase ──────────────────────────────────────────────────────────────────
def _sb_headers():
    return {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"}

def sb_get(table, qs):
    req = urllib.request.Request(f"{SB_URL}/rest/v1/{table}?{qs}", headers=_sb_headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def sb_patch(table, match_qs, body):
    req = urllib.request.Request(f"{SB_URL}/rest/v1/{table}?{match_qs}",
        data=json.dumps(body).encode(), method="PATCH",
        headers={**_sb_headers(), "Prefer": "return=representation"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def sb_upload_video(path, content_id):
    obj = f"{content_id}.mp4"
    with open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        f"{SB_URL}/storage/v1/object/embarrassed-angle/{obj}", data=data, method="POST",
        headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}",
                 "Content-Type": "video/mp4", "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=180)
    return f"{SB_URL}/storage/v1/object/public/embarrassed-angle/{obj}"

# ── ffmpeg helpers ────────────────────────────────────────────────────────────
def probe(path):
    out = subprocess.run(
        [FP, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-show_entries", "format=duration",
         "-of", "json", path], capture_output=True, text=True, check=True).stdout
    j = json.loads(out); s = j["streams"][0]
    return int(s["width"]), int(s["height"]), float(j["format"]["duration"])

def dur_of(path):
    """Duration (seconds) from the container — works for audio-only files too (no video stream)."""
    out = subprocess.run(
        [FP, "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])

def has_audio(path):
    out = subprocess.run(
        [FP, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
         "-of", "json", path], capture_output=True, text=True).stdout
    try:
        return bool(json.loads(out).get("streams"))
    except Exception:
        return False

def _extract_montage(clip_path, out_png, n=9):
    """Tile n evenly-sampled frames into one 3x3 image for a cheap vision probe. 9 frames
    (not 4) so text that only appears briefly still shows up in at least one cell."""
    dur = max(dur_of(clip_path), 0.1)
    fps = max(0.1, round(n / min(dur, 60.0), 3))
    subprocess.run([FF, "-y", "-loglevel", "error", "-t", "60", "-i", clip_path,
                    "-vf", f"fps={fps},scale=240:-1,tile=3x3", "-frames:v", "1", out_png], check=True)
    return out_png

def detect_onscreen_text(clip_path, source):
    """True if the source clip has burned-in on-screen text/captions. Result is cached on the
    source row (has_onscreen_text) so it's decided once. Conservative: ANY failure returns True,
    i.e. assume text is present so the caller does NOT mirror-flip."""
    cached = source.get("has_onscreen_text")
    if cached is not None:
        return bool(cached)
    if not OPENROUTER_KEY:
        return True
    try:
        png = os.path.join(CACHE_DIR, f"textprobe_{source['id']}.png")
        _extract_montage(clip_path, png)
        b64 = base64.b64encode(open(png, "rb").read()).decode()
        prompt = ("This is a 2x2 montage of frames from a short video. Does the video have "
                  "burned-in on-screen TEXT or CAPTIONS (words overlaid on the footage: a caption, "
                  "meme text, subtitles, or a sticker with words)? Ignore platform logos, "
                  "watermarks/usernames, and text that is naturally part of the scene (signs, "
                  "clothing). Reply ONLY JSON: {\"has_text\": true|false}.")
        body = {"model": "google/gemini-2.5-flash", "reasoning": {"enabled": False},
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}],
                "temperature": 0, "max_tokens": 60}
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read())
        txt = resp["choices"][0]["message"]["content"]
        if isinstance(txt, list):
            txt = " ".join(p.get("text", "") for p in txt)
        i, j = txt.find("{"), txt.rfind("}")
        has = bool(json.loads(txt[i:j + 1]).get("has_text", True))
    except Exception as e:
        # transient failure: assume text present (no flip) but DON'T cache, so it retries later
        print(f"  [text-detect failed: {e} -> assuming text present, no flip]")
        return True
    try:
        sb_patch(SOURCE_TABLE, f"id=eq.{source['id']}", {"has_onscreen_text": has})
    except Exception:
        pass
    return has

def normalize_clip(src, dst, *, keep_audio=True, clip_in=None, clip_out=None, fill=False,
                   reframe=None, mirror=False):
    """Normalize to TARGET, force 30fps, AAC 44.1k. fill=True crops to fill the frame
    (full-screen, no bars); fill=False fits with black padding. reframe={sw,sh,fx,fy} zooms and
    off-center crops (reuse variation, fills the frame). mirror=True horizontally flips first.
    Silent track if no/!keep audio."""
    pre = "hflip," if mirror else ""
    if reframe:
        sw, sh, dx, dy = reframe["sw"], reframe["sh"], reframe["dx"], reframe["dy"]
        cx = f"max(0\\,min(iw-{TARGET_W}\\,(iw-{TARGET_W})/2+({dx})))"
        cy = f"max(0\\,min(ih-{TARGET_H}\\,(ih-{TARGET_H})/2+({dy})))"
        vf = (f"{pre}scale={sw}:{sh}:force_original_aspect_ratio=increase,"
              f"crop={TARGET_W}:{TARGET_H}:{cx}:{cy},"
              f"fps={TARGET_FPS},setsar=1")
    elif fill:
        vf = (f"{pre}scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
              f"crop={TARGET_W}:{TARGET_H},fps={TARGET_FPS},setsar=1")
    else:
        vf = (f"{pre}scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
              f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,fps={TARGET_FPS},setsar=1")
    use_src_audio = keep_audio and has_audio(src)

    cmd = [FF, "-y", "-loglevel", "error"]
    if clip_in is not None:
        cmd += ["-ss", str(clip_in)]
    cmd += ["-i", src]
    if not use_src_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    if clip_out is not None:
        cmd += ["-t", str((clip_out - clip_in) if clip_in is not None else clip_out)]
    cmd += ["-vf", vf, "-r", str(TARGET_FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
    if use_src_audio:
        cmd += ["-map", "0:v", "-map", "0:a", "-c:a", "aac", "-ar", "44100", "-b:a", "128k"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-ar", "44100", "-b:a", "96k", "-shortest"]
    cmd.append(dst)
    subprocess.run(cmd, check=True)
    return dst

def concat_clips(clips, out):
    """Concat normalized clips (stream copy) via the concat demuxer, in given order."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for c in clips:
            f.write(f"file '{c}'\n")
        list_path = f.name
    try:
        subprocess.run([FF, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", list_path, "-c", "copy", out], check=True)
    finally:
        os.unlink(list_path)
    return out

def _render_hook_png(text, png_path):
    """Render the halo-style hook to a transparent PNG (white + thick black stroke +
    drop shadow), centered top at 7%. Mirrors the dating-reaction-video caption."""
    from PIL import Image, ImageDraw, ImageFont
    clean = re.sub(r"[\U0001F000-\U0001FAFF←-➿︀-️‍]", "", text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return False
    lines = textwrap.wrap(clean, width=28)
    fontsize = {1: 66, 2: 64, 3: 58, 4: 50}.get(len(lines), 44)
    font = ImageFont.truetype(HOOK_FONT, fontsize)
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    line_h = fontsize + 14
    y0 = (TARGET_H - line_h * len(lines)) // 2   # vertically centered on screen
    for i, line in enumerate(lines):
        tw = d.textlength(line, font=font)
        x = (TARGET_W - tw) / 2
        y = y0 + i * line_h
        d.text((x, y + 3), line, font=font, fill=(0, 0, 0, 115))                       # drop shadow
        d.text((x, y), line, font=font, fill=(255, 255, 255, 255),
               stroke_width=7, stroke_fill=(0, 0, 0, 255))                              # white + halo
    img.save(png_path)
    return True

def burn_hook(src, out, hook_text, hook_end):
    """Overlay the halo text hook onto `src` for t in [0, hook_end] → `out` (no drawtext)."""
    png = os.path.join(CACHE_DIR, "_hook_overlay.png")
    if not _render_hook_png(hook_text, png):
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", src, "-c", "copy", out], check=True)
        return out
    filt = f"[0:v][1:v]overlay=0:0:enable='between(t,0,{hook_end:.2f})'[vo]"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as ff:
        ff.write(filt); filt_path = ff.name
    try:
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", src, "-i", png,
                        "-filter_complex_script", filt_path, "-map", "[vo]", "-map", "0:a?",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-c:a", "copy", out], check=True)
    finally:
        os.unlink(filt_path)
    return out

def add_voiceover(src, dst, end_clip_start):
    """Mux the two fixed VO lines onto `src` and trim the tail → `dst`.

    BEGIN VO at VO_BEGIN_START (ducks the bed under it); END/CTA VO anchored to
    end_clip_start + VO_END_LEAD (the END clip is silent, so the CTA plays clean);
    final length = src - VO_TAIL_TRIM (never cutting into the CTA). Video is stream-copied
    — only audio is re-mixed. Falls back to a plain copy if the VO assets are missing.
    """
    if not (os.path.exists(VO_BEGIN_CLIP) and os.path.exists(VO_END_CLIP)):
        print(f"  [vo] assets missing ({VO_BEGIN_CLIP} / {VO_END_CLIP}) — skipping VO")
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", src, "-c", "copy", dst], check=True)
        return dst

    total   = dur_of(src)
    vb_dur  = dur_of(VO_BEGIN_CLIP)
    ve_dur  = dur_of(VO_END_CLIP)
    duck_to = VO_BEGIN_START + vb_dur + VO_DUCK_PAD
    cta_at  = end_clip_start + VO_END_LEAD
    final   = total - VO_TAIL_TRIM
    if final < cta_at + ve_dur + 0.3:          # never trim into the CTA
        final = cta_at + ve_dur + 0.3
    b_ms, c_ms = int(round(VO_BEGIN_START * 1000)), int(round(cta_at * 1000))

    tail_clip = os.environ.get("EMBARRASSED_VO_TAIL", "")
    use_tail = False
    if os.environ.get("EMBARRASSED_VO_BUILD") == "1":
        # "slow build" mix: overlay fades in 0.25→1.0 across its own length while the
        # bed (viral clip audio) eases down only to 0.55 — both stay audible throughout.
        # If EMBARRASSED_VO_TAIL is set, that laugh tail plays low (0.3) under the END
        # clip, beneath the CTA line.
        window = vb_dur + VO_DUCK_PAD
        e_ms = int(round(end_clip_start * 1000))
        use_tail = bool(tail_clip) and os.path.exists(tail_clip)
        filt = (
            f"[0:a]volume='if(between(t,{VO_BEGIN_START:.2f},{duck_to:.2f}),"
            f"max(0.55,1-0.45*((t-{VO_BEGIN_START:.2f})/{window:.2f})),1)':eval=frame[bed];"
            f"[1:a]volume='min(1,0.25+0.75*(t/{vb_dur:.2f}))':eval=frame,"
            f"adelay={b_ms}|{b_ms}[v1];"
            f"[2:a]adelay={c_ms}|{c_ms}[v2];"
        )
        if use_tail:
            filt += (
                f"[3:a]volume=0.3,adelay={e_ms}|{e_ms}[v3];"
                f"[bed][v1][v2][v3]amix=inputs=4:normalize=0:duration=longest[aout]"
            )
        else:
            filt += "[bed][v1][v2]amix=inputs=3:normalize=0:duration=longest[aout]"
    else:
        filt = (
            f"[0:a]volume={VO_DUCK}:enable='between(t,{VO_BEGIN_START:.2f},{duck_to:.2f})'[bed];"
            f"[1:a]adelay={b_ms}|{b_ms}[v1];"
            f"[2:a]adelay={c_ms}|{c_ms}[v2];"
            f"[bed][v1][v2]amix=inputs=3:normalize=0:duration=longest[aout]"
        )
    cmd = [FF, "-y", "-loglevel", "error",
           "-i", src, "-i", VO_BEGIN_CLIP, "-i", VO_END_CLIP]
    if use_tail:
        cmd += ["-i", tail_clip]
    cmd += ["-filter_complex", filt, "-map", "0:v", "-map", "[aout]",
            "-t", f"{final:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", dst]
    subprocess.run(cmd, check=True)
    print(f"  [vo] begin@{VO_BEGIN_START:.1f}s  cta@{cta_at:.1f}s  trim={VO_TAIL_TRIM:.1f}s  final={final:.1f}s")
    return dst

# ── per-row stitch ────────────────────────────────────────────────────────────
def stitch_one(content_id, norm_begin, norm_end, local_only=False):
    print(f"== stitch content_id={content_id} ==")
    rows = sb_get(CONTENT_TABLE, f"id=eq.{content_id}&select=*")
    if not rows:
        raise RuntimeError(f"no row id={content_id} in {CONTENT_TABLE}")
    content = rows[0]

    srows = sb_get(SOURCE_TABLE, f"id=eq.{content['source_clip_id']}&select=*")
    if not srows:
        raise RuntimeError(f"source_clip_id={content['source_clip_id']} not found")
    source = srows[0]
    print(f"  {content['content_id']} → source {source['id']} ({source['url']})")

    clip_in  = source.get("clip_in_seconds")
    clip_out = source.get("clip_out_seconds")
    clip_in  = float(clip_in)  if clip_in  is not None else None
    clip_out = float(clip_out) if clip_out is not None else None

    # locate cached viral Clip A
    aweme_id = source.get("aweme_id") or str(source["id"])
    cached_a = os.path.join(CACHE_DIR, f"clip_a_{aweme_id}.mp4")
    existing = source.get("video_public_url")
    if existing and os.path.exists(existing) and os.path.getsize(existing) > 0:
        raw_viral = existing
    elif os.path.exists(cached_a) and os.path.getsize(cached_a) > 0:
        raw_viral = cached_a
    else:
        raise RuntimeError(f"viral clip not cached (aweme_id={aweme_id}); run download_library.py --id {source['id']}")

    # RULE: clips under 15s play full length — never trim a short clip, even if a window is set
    raw_dur = probe(raw_viral)[2]
    if raw_dur < 15:
        clip_in = clip_out = None

    # normalize the per-row viral clip (begin/end already normalized once in main).
    # Reuse rows (content_id version >= 4) get a subtle reframe so the re-post isn't a
    # pixel-identical duplicate, plus a mirror flip when the source has no burned-in text.
    version = _reuse_version(content.get("content_id"))
    reframe = REUSE_REFRAME.get(version) if version >= 4 else None
    mirror = False
    if reframe:
        mirror = not detect_onscreen_text(raw_viral, source)
        print(f"  reuse V{version}: reframe ON" +
              (", mirror-flip (no source text)" if mirror else ", no flip (source has text)"))
    # per content_id (not per source) so different versions don't share a normalized cache
    norm_viral = os.path.join(CACHE_DIR, f"norm_viral_{content['content_id']}.mp4")
    normalize_clip(raw_viral, norm_viral, keep_audio=True, clip_in=clip_in, clip_out=clip_out,
                   reframe=reframe, mirror=mirror)

    # concat: BEGINNING -> VIRAL -> END
    concat_tmp = os.path.join(CACHE_DIR, f"concat_{content['content_id']}.mp4")
    concat_clips([norm_begin, norm_viral, norm_end], concat_tmp)

    # burn the text hook over the BEGINNING reaction only (keeps it off the viral clip,
    # which often has its own burned-in caption, and off the END kitchen reveal)
    hook_end = probe(norm_begin)[2]
    hooked_tmp = os.path.join(CACHE_DIR, f"hooked_{content['content_id']}.mp4")
    burn_hook(concat_tmp, hooked_tmp, content.get("text_hook"), hook_end)
    os.remove(concat_tmp)

    # bake the two fixed VO lines in + tail trim. CTA is anchored to where the END clip
    # starts (begin + viral durations) so it lands consistently on every render.
    prefix = "test_" if local_only else ""
    out_path = os.path.join(RENDER_DIR, f"{prefix}{content['content_id']}.mp4")
    end_clip_start = probe(norm_begin)[2] + probe(norm_viral)[2]
    add_voiceover(hooked_tmp, out_path, end_clip_start)
    os.remove(hooked_tmp)

    w, h, dur = probe(out_path)
    hk = (content.get("text_hook") or "").strip()
    print(f"  OUTPUT: {out_path}  ({w}x{h}, {dur:.1f}s)  hook={hk[:40]!r} for {hook_end:.1f}s")

    if local_only:
        print(f"  --local-only: skipping DB patch (row untouched)")
        return out_path

    import datetime
    public_url = sb_upload_video(out_path, content["content_id"])
    sb_patch(CONTENT_TABLE, f"id=eq.{content_id}", {
        "video_local_path": out_path,
        "video_public_url": public_url,
        "stitch_status": "rendered",
        "rendered_at": datetime.datetime.utcnow().isoformat() + "Z",
    })
    print(f"  content row → stitch_status=rendered, uploaded {public_url}")
    return out_path

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Stitch Embarrassed Content Angle (Beginning → Viral → End)")
    ap.add_argument("--content_id", type=int, default=None,
                    help="Row ID in embarrassed_angle_content (omit to process all waiting_render)")
    ap.add_argument("--begin", default=DEFAULT_BEGIN, help="Beginning (reaction) clip")
    ap.add_argument("--end",   default=DEFAULT_END,   help="End (kitchen+pen+before) clip")
    ap.add_argument("--local-only", action="store_true",
                    help="Render to renders/test_<id>.mp4 only; no DB patch (safe A/B test)")
    args = ap.parse_args()

    for label, p in (("begin", args.begin), ("end", args.end)):
        if not os.path.exists(p):
            sys.exit(f"ERROR: {label} clip not found: {p}")

    # normalize the two fixed character clips ONCE (reused across every row)
    print("normalizing fixed character clips (begin + end)...")
    norm_begin = os.path.join(CACHE_DIR, "norm_begin.mp4")
    norm_end   = os.path.join(CACHE_DIR, "norm_end.mp4")
    normalize_clip(args.begin, norm_begin, keep_audio=True, fill=True)   # reaction: full-screen, keep audio
    normalize_clip(args.end,   norm_end,   keep_audio=False)             # end clip is silent (already 9:16)

    if args.content_id:
        ids = [args.content_id]
    else:
        ids = [r["id"] for r in sb_get(CONTENT_TABLE, "stitch_status=eq.waiting_render&select=id&order=id.asc")]
        print(f"batch: {len(ids)} waiting_render rows")

    ok = fail = 0
    for cid in ids:
        try:
            stitch_one(cid, norm_begin, norm_end, local_only=args.local_only); ok += 1
        except Exception as e:
            print(f"  [content_id={cid}] FAILED: {e}"); fail += 1

    if len(ids) > 1:
        print(f"\nbatch done: {ok} rendered, {fail} failed")

if __name__ == "__main__":
    main()
