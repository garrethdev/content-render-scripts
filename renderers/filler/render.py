#!/usr/bin/env python3
"""Render engine — builds ONE split-screen viral-filler video from a viral_filler_content row.

Layout: 1080x1920. Top cell = character clip (silent, looped to content length). Bottom cell =
filler_library clip (original audio). Each cell 1080x960, smart-resized (center-crop unless a
fill-crop would lose >30% -> blurred fit). Hook burned at the seam ONLY when the clip has no
on-screen text of its own. Per-clip analysis (dimensions, fit_mode, on-screen-text) is cached on
filler_library so the vision LLM only runs for clips that haven't been analyzed yet.
"""
import os, json, base64, subprocess, urllib.request, urllib.parse, datetime
from PIL import Image, ImageDraw, ImageFont
import config, supa

FF, FP = config.FFMPEG, config.FFPROBE
WORK, FONT = config.WORKDIR, config.FONT
SCK, ORK = config.SCRAPECREATORS_KEY, config.OPENROUTER_KEY
ANALYSIS_VERSION = 1
CELL_W, CELL_H = 1080, 960
BLUR_THRESHOLD = 0.30
# NOTE: color grade is now BAKED into the library source clips + character clips
# (unified neutralize+blend grade). Do not grade again here, or it double-grades.
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
      "Referer": "https://www.tiktok.com/"}

def _sc(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"x-api-key": SCK}), timeout=60))

def scrape_play_url(source_url):
    """Platform-aware: a downloadable video URL for a TikTok or Instagram source."""
    if "instagram.com" in source_url:
        d = _sc("https://api.scrapecreators.com/v2/instagram/post?" + urllib.parse.urlencode({"url": source_url}))
        v = d.get("video_url")
        if not v:
            acc = []
            def fv(o):
                if isinstance(o, dict):
                    for k, val in o.items():
                        if isinstance(val, str) and val.startswith("http") and (".mp4" in val or k.lower() == "video_url"):
                            acc.append(val)
                        fv(val)
                elif isinstance(o, list):
                    for val in o: fv(val)
            fv(d); v = acc[0] if acc else None
        if not v: raise RuntimeError("no IG video url")
        return v
    v = _sc("https://api.scrapecreators.com/v2/tiktok/video?" + urllib.parse.urlencode({"url": source_url}))["aweme_detail"]["video"]
    for k in ("play_addr_h264", "download_no_watermark_addr", "play_addr"):
        try: return v[k]["url_list"][0]
        except Exception: pass
    raise RuntimeError("no TikTok play url")

def download(url, out, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=180) as r, open(out, "wb") as f:
        f.write(r.read())
    return out

def probe(path):
    out = subprocess.run([FP, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-show_entries", "format=duration", "-of", "json", path], capture_output=True, text=True).stdout
    j = json.loads(out); s = j["streams"][0]
    return int(s["width"]), int(s["height"]), float(j["format"]["duration"])

def decide_fit(w, h):
    scale = max(CELL_W / w, CELL_H / h); nw, nh = w * scale, h * scale
    lost = max((nw - CELL_W) / nw if nw > CELL_W else 0, (nh - CELL_H) / nh if nh > CELL_H else 0)
    return ("blur" if lost > BLUR_THRESHOLD else "crop"), round(lost, 3)

def vision_detect_text(frames):
    content = [{"type": "text", "text":
        "These are frames from a vertical short-form video. Detect any BURNED-IN on-screen text or captions "
        "(ignore platform UI like @handles, like/share icons). Reply ONLY JSON: "
        '{"has_text":bool,"text":"the main caption text or empty","band":"top|middle|bottom|none"}.'}]
    for p in frames:
        b = base64.b64encode(open(p, "rb").read()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}})
    body = {"model": "anthropic/claude-haiku-4.5", "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"}, "max_tokens": 300, "temperature": 0}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {ORK}", "Content-Type": "application/json"})
    txt = json.load(urllib.request.urlopen(req, timeout=90))["choices"][0]["message"]["content"]
    return json.JSONDecoder().raw_decode(txt[txt.find("{"):])[0]

def analyze_clip(aweme_id, content_path, w, h):
    """Analyze a NEW clip and cache the result on filler_library. Fail-safe: never default to no-text."""
    fit, lost = decide_fit(w, h)
    _, _, dur = probe(content_path); frames = []
    for i, frac in enumerate((0.15, 0.55)):
        fp = os.path.join(WORK, f"an_{aweme_id}_{i}.jpg")
        subprocess.run([FF, "-y", "-loglevel", "error", "-ss", str(round(dur * frac, 2)), "-i", content_path,
                        "-frames:v", "1", "-vf", "scale=360:-1", fp], check=True)
        frames.append(fp)
    match = f"filler_library?aweme_id=eq.{urllib.parse.quote(str(aweme_id))}"
    try:
        det = vision_detect_text(frames)
    except Exception as ex:
        supa.rest(match, "PATCH", {"width": w, "height": h, "fit_mode": fit}, prefer="return=minimal")
        print(f"    vision FAILED ({ex}) -> not cached; conservative has_text=True (skip hook)")
        return fit, {"has_text": True, "band": "unknown", "text": ""}
    safe = {"has_text": bool(det.get("has_text")), "band": det.get("band", "none"), "text": (det.get("text") or "")[:300]}
    supa.rest(match, "PATCH", {"width": w, "height": h, "fit_mode": fit, "has_onscreen_hook": safe["has_text"],
                               "onscreen_text": safe["text"] or None, "text_safe_zone": safe,
                               "analyzed_at": datetime.datetime.utcnow().isoformat() + "Z",
                               "analysis_version": ANALYSIS_VERSION}, prefer="return=minimal")
    return fit, safe

# --- reuse "freshening" treatments, applied to the BOTTOM (viral) clip only ---
# A treatment is a "+"-joined token set, e.g. "flip+crop". "" / "none" = untouched.
# GEOMETRY ONLY on purpose: color grade is already baked into the library clips at promote
# time, so we never touch color here (that would double-grade). The vocabulary is fixed so a
# worker can refuse a job whose treatment it doesn't recognize.
TREATMENT_TOKENS = {
    "flip": "hflip",                  # horizontal mirror
    "crop": "crop=iw*0.9:ih*0.9",     # center 90% -> ~1.11x, re-framed
}
_TREATMENT_ORDER = ["crop", "flip"]   # geometry, applied in this order

def parse_treatment(treatment, has_text=False):
    """(filter_string, applied_tokens). Unknown token -> ValueError. 'flip' is dropped when the
    clip has burned-in text (mirroring would reverse the words)."""
    t = (treatment or "").strip().lower()
    if not t or t == "none":
        return "", []
    tokens = [x for x in t.replace(",", "+").split("+") if x]
    unknown = [x for x in tokens if x not in TREATMENT_TOKENS]
    if unknown:
        raise ValueError(f"unknown treatment token(s): {unknown}")
    if has_text and "flip" in tokens:
        tokens = [x for x in tokens if x != "flip"]
    tokens = [x for x in _TREATMENT_ORDER if x in tokens]
    return ",".join(TREATMENT_TOKENS[x] for x in tokens), tokens

def treatment_known(treatment):
    try:
        parse_treatment(treatment); return True
    except ValueError:
        return False

def _cell(src, fit, label):
    if fit == "crop":
        return f"[{src}]scale={CELL_W}:{CELL_H}:force_original_aspect_ratio=increase,crop={CELL_W}:{CELL_H},setsar=1[{label}]"
    return (f"[{src}]split=2[{label}a][{label}b];"
            f"[{label}a]scale={CELL_W}:{CELL_H}:force_original_aspect_ratio=increase,crop={CELL_W}:{CELL_H},boxblur=20:2[{label}bg];"
            f"[{label}b]scale={CELL_W}:{CELL_H}:force_original_aspect_ratio=decrease,setsar=1[{label}fg];"
            f"[{label}bg][{label}fg]overlay=(W-w)/2:(H-h)/2[{label}]")

def build_hook_png(hook, out, seam_y=960):
    W, H, SIZE, MAXW = 1080, 1920, 54, 900
    font = ImageFont.truetype(FONT, SIZE); img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    words = hook.split(); lines = []; cur = ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) > MAXW and cur: lines.append(cur); cur = w
        else: cur = t
    if cur: lines.append(cur)
    lh = SIZE + 14; total = len(lines) * lh - 14; top = seam_y - total // 2
    bw = max(d.textlength(l, font=font) for l in lines) + 56
    d.rounded_rectangle([(W - bw) // 2, top - 22, (W + bw) // 2, top + total + 16], radius=24, fill=(0, 0, 0, 140))
    for i, l in enumerate(lines):
        lw = d.textlength(l, font=font)
        d.text(((W - lw) // 2, top + i * lh), l, font=font, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0, 255))
    img.save(out)

def render_job(row, max_seconds=None):
    """Render one row -> local mp4 path. (Upload/DB status handled by the worker.)"""
    aweme = row["filler_aweme_id"]; hook = row.get("hook") or ""
    char_url = row["character_url"]; source_url = row["source_url"]
    lib = supa.rest(f"filler_library?aweme_id=eq.{urllib.parse.quote(str(aweme))}&select=*")
    lib = lib[0] if lib else None

    content = os.path.join(WORK, f"content_{aweme}.mp4")
    if not os.path.exists(content):
        graded = (lib or {}).get("source_video_url")
        if graded:
            download(graded, content)                       # pre-graded library file (direct from storage)
        else:
            download(scrape_play_url(source_url), content, UA)   # fallback: fresh TikTok/IG download
    w, h, dur = probe(content)

    if lib and lib.get("analyzed_at"):
        fit = lib.get("fit_mode") or decide_fit(w, h)[0]
        safe = lib.get("text_safe_zone") or {"has_text": bool(lib.get("has_onscreen_hook")), "text": lib.get("onscreen_text") or ""}
    else:
        fit, safe = analyze_clip(aweme, content, w, h)

    char = os.path.join(WORK, "char_" + os.path.basename(char_url))
    if not os.path.exists(char):
        download(char_url, char)
    cw, ch, _ = probe(char); char_fit, _ = decide_fit(cw, ch)

    add_hook = bool(hook) and not safe.get("has_text")
    if add_hook:
        hook_png = os.path.join(WORK, f"overlay_{row['id']}.png"); build_hook_png(hook, hook_png)

    tr_filters, tr_applied = parse_treatment(row.get("treatment"), has_text=bool(safe.get("has_text")))
    if tr_filters:
        pre, bot_src = f"[1:v]{tr_filters}[btr];", "btr"
        print(f"    treatment {row.get('treatment')!r} -> applied {tr_applied}")
    else:
        pre, bot_src = "", "1:v"

    out = os.path.join(WORK, f"render_{row['id']}.mp4")
    # bottom + char are pre-graded in the library (no color here); treatment adds geometry only, on reuse
    fc = f"{pre}{_cell('0:v', char_fit, 'top')};{_cell(bot_src, fit, 'bot')};[top][bot]vstack[s]"
    inputs = ["-stream_loop", "-1", "-i", char, "-i", content]
    if add_hook:
        inputs += ["-i", hook_png]; fc += ";[s][2:v]overlay=0:0[outv]"; vmap = "[outv]"
    else:
        vmap = "[s]"
    rdur = min(dur, float(max_seconds)) if max_seconds else dur
    subprocess.run([FF, "-y", "-loglevel", "error", *inputs, "-filter_complex", fc, "-map", vmap, "-map", "1:a",
                    "-t", str(rdur), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", out], check=True, timeout=900)
    return out

def trigger_captions():
    """Fire the live [Universal] Caption Maker to fill captions for newly-rendered rows."""
    cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "caption_config.json")))
    req = urllib.request.Request(config.N8N_BASE + "/webhook/caption-maker", data=json.dumps(cfg).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=60)
