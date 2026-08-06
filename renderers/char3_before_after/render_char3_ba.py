#!/usr/bin/env python3
"""Local ffmpeg stitcher for the Character 3 simple Before/After videos.

Layout: 1080x1920, 30fps, natural clip lengths, hard cuts.
  [optional opener IMAGE, 2.5s static] -> [BEFORE video, full length] -> [AFTER video, full length]
  text_hook (custom, per row) burned on the opener image + before video only; after is clean.
  Silent audio — music_id points at music_library and is attached at POST time (Char 4 pattern).

Source table: char3_before_after (stitch_status ready -> done / stitch_failed).
Asset columns (before_image / before_video / after_video) hold either a full https URL
or a storage key in the private video-library bucket (signed via service key).
Output: private bucket char3-before-after/<carousel_id>.mp4, 1-year signed URL -> final_video.

Usage:
  python render_char3_ba.py local <hook> <before_video> <after_video> [image]   # proof render, no DB
  python render_char3_ba.py test  <carousel_id>    # render ONE row locally, NO upload / NO db write
  python render_char3_ba.py one   <carousel_id>    # render + upload + patch ONE row
  python render_char3_ba.py batch <batch_name>     # every stitch_status=ready row in the batch
  python render_char3_ba.py queue                  # every stitch_status=ready row
"""
import os, sys, json, subprocess, urllib.request, urllib.parse

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)
from common import env
from common.ffguard import run_ffmpeg_guarded

env.load_env()
SB = os.environ.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co")
KEY = env.require("CAROUSEL_SUPABASE_SECRET_KEY")
FF = os.environ.get("FFMPEG", "ffmpeg")
FP = os.environ.get("FFPROBE", "ffprobe")
FONT = os.environ.get("HOOK_FONT", os.path.join(_HERE, "assets", "hook-font.ttf"))
WORK = os.environ.get("WORKDIR", os.path.join(_HERE, "work"))
os.makedirs(WORK, exist_ok=True)

TABLE = "char3_before_after"
SRC_BUCKET, OUT_BUCKET = "video-library", "char3-before-after"
W, H, FPS = 1080, 1920, 30
IMAGE_HOLD = float(os.environ.get("C3BA_IMAGE_HOLD", "2.5"))
MAX_SEG = float(os.environ.get("C3BA_MAX_SEG", "45"))   # safety cap per video segment
YEAR = 31536000
_H = {"apikey": KEY, "Authorization": "Bearer " + KEY}

from PIL import Image, ImageDraw, ImageFont


def rest(path, method="GET", body=None, prefer=None):
    headers = dict(_H); data = None
    if body is not None:
        headers["Content-Type"] = "application/json"; data = json.dumps(body).encode()
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(SB + "/rest/v1/" + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as r:
        t = r.read().decode(); return json.loads(t) if t else None


def sign_url(bucket, key, expires=3600):
    req = urllib.request.Request(
        SB + "/storage/v1/object/sign/" + bucket + "/" + urllib.parse.quote(key),
        data=json.dumps({"expiresIn": expires}).encode(), method="POST",
        headers={**_H, "Content-Type": "application/json"})
    signed = json.load(urllib.request.urlopen(req, timeout=60))["signedURL"]
    if not signed.startswith("/"):
        signed = "/" + signed
    # Supabase returns the object path unencoded; spaces in filenames break urllib
    signed = urllib.parse.quote(signed, safe="/?&=%.")
    return SB + "/storage/v1" + signed


def download(url, out):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (render_char3_ba)"})
    with urllib.request.urlopen(req, timeout=300) as r, open(out, "wb") as f:
        f.write(r.read())
    return out


def fetch_asset(val, out):
    """Asset columns hold either a full URL or a video-library storage key."""
    return download(val if val.startswith("http") else sign_url(SRC_BUCKET, val), out)


def upload(bucket, key, path, content_type="video/mp4"):
    with open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        SB + "/storage/v1/object/" + bucket + "/" + urllib.parse.quote(key),
        data=data, method="POST", headers={**_H, "Content-Type": content_type, "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=600)


def probe_duration(path):
    out = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


# ---- hook PNG (same TikTok Sans white + black stroke + Apple emoji as the grandma BA) ----
EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"
EMOJI_STRIKE = 160  # Apple Color Emoji only rasterizes at fixed strike sizes; 160 is the largest


def _is_emoji_cp(cp):
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2190 <= cp <= 0x21FF
            or 0x2B00 <= cp <= 0x2BFF or cp in (0xFE0F, 0x200D, 0x2764, 0x2728)
            or 0x1F3FB <= cp <= 0x1F3FF or 0x1F1E6 <= cp <= 0x1F1FF)


def _split_runs(s):
    runs = []
    for ch in s:
        e = _is_emoji_cp(ord(ch))
        if runs and runs[-1][0] == e:
            runs[-1][1] += ch
        else:
            runs.append([e, ch])
    return runs


_emoji_cache = {}


def _emoji_img(chunk, size):
    key = (chunk, size)
    if key not in _emoji_cache:
        f = ImageFont.truetype(EMOJI_FONT, EMOJI_STRIKE)
        pad = EMOJI_STRIKE // 2
        tmp = Image.new("RGBA", (EMOJI_STRIKE * (len(chunk) + 1) + pad, EMOJI_STRIKE + pad), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((pad // 2, pad // 2), chunk, font=f, embedded_color=True)
        box = tmp.getbbox()
        tmp = tmp.crop(box) if box else tmp
        scale = size / float(tmp.height or 1)
        _emoji_cache[key] = tmp.resize((max(1, int(tmp.width * scale)), size), Image.LANCZOS)
    return _emoji_cache[key]


def build_text_png(text, out):
    SIZE, MAXW = 64, 950
    font = ImageFont.truetype(FONT, SIZE)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)

    def wlen(s):
        return sum(_emoji_img(c, SIZE).width + 6 if e else d.textlength(c, font=font)
                   for e, c in _split_runs(s))

    words = (text or "").split(); lines = []; cur = ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if wlen(t) > MAXW and cur:
            lines.append(cur); cur = wd
        else:
            cur = t
    if cur:
        lines.append(cur)
    lh = SIZE + 16; total = len(lines) * lh - 16
    top = int(H * 0.75) - total // 2
    for i, l in enumerate(lines):
        x = (W - wlen(l)) // 2; y = top + i * lh
        for e, chunk in _split_runs(l):
            if e:
                em = _emoji_img(chunk, SIZE)
                img.alpha_composite(em, (int(x) + 3, y + (SIZE - em.height) // 2 + 8))
                x += em.width + 6
            else:
                d.text((int(x), y), chunk, font=font, fill=(255, 255, 255, 255),
                       stroke_width=6, stroke_fill=(0, 0, 0, 255))
                x += d.textlength(chunk, font=font)
    img.save(out)


# ---- segments (all encoded with identical params so concat is clean) ----
_ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100"]
_COVER = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d" % (W, H, W, H, FPS)


def image_segment(src_path, hook_png, out_path):
    fc = "[0:v]" + _COVER + "[bg];[bg][1:v]overlay=0:0[v]"
    cmd = [FF, "-y", "-loglevel", "error",
           "-loop", "1", "-t", str(IMAGE_HOLD), "-i", src_path, "-i", hook_png,
           "-f", "lavfi", "-t", str(IMAGE_HOLD), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-filter_complex", fc, "-map", "[v]", "-map", "2:a", "-t", str(IMAGE_HOLD),
           *_ENC, out_path]
    run_ffmpeg_guarded(cmd, out_path, IMAGE_HOLD)
    return out_path


def video_segment(src_path, hook_png, out_path):
    """Natural length (capped at MAX_SEG), cover-cropped, silent audio; hook overlaid if given."""
    seconds = min(probe_duration(src_path), MAX_SEG)
    if hook_png:
        fc = "[0:v]" + _COVER + "[bg];[bg][1:v]overlay=0:0[v]"
        inputs = ["-i", src_path, "-i", hook_png]
    else:
        fc = "[0:v]" + _COVER + "[v]"
        inputs = ["-i", src_path]
    cmd = [FF, "-y", "-loglevel", "error", *inputs,
           "-f", "lavfi", "-t", str(seconds), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-filter_complex", fc, "-map", "[v]", "-map", str(len(inputs) // 2) + ":a",
           "-t", str(seconds), *_ENC, out_path]
    run_ffmpeg_guarded(cmd, out_path, seconds)
    return out_path, seconds


def stitch(segments, out_path, total_seconds):
    n = len(segments)
    inputs = []
    for s in segments:
        inputs += ["-i", s]
    fc = "".join("[%d:v][%d:a]" % (i, i) for i in range(n)) + "concat=n=%d:v=1:a=1[v][a]" % n
    cmd = [FF, "-y", "-loglevel", "error", *inputs, "-filter_complex", fc,
           "-map", "[v]", "-map", "[a]", *_ENC, out_path]
    run_ffmpeg_guarded(cmd, out_path, total_seconds)
    return out_path


def render_assets(cid, hook, before_video, after_video, before_image=None):
    png = os.path.join(WORK, cid + "_hook.png"); build_text_png(hook or "", png)
    segs = []; total = 0.0
    if before_image:
        img_src = fetch_asset(before_image, os.path.join(WORK, cid + "_img_src"))
        segs.append(image_segment(img_src, png, os.path.join(WORK, cid + "_img.mp4")))
        total += IMAGE_HOLD
    b_src = fetch_asset(before_video, os.path.join(WORK, cid + "_b_src.mp4"))
    a_src = fetch_asset(after_video, os.path.join(WORK, cid + "_a_src.mp4"))
    b_seg, b_len = video_segment(b_src, png, os.path.join(WORK, cid + "_b.mp4"))
    a_seg, a_len = video_segment(a_src, None, os.path.join(WORK, cid + "_a.mp4"))
    segs += [b_seg, a_seg]; total += b_len + a_len
    return stitch(segs, os.path.join(WORK, cid + ".mp4"), total)


def render_row(row):
    return render_assets(row["carousel_id"], row.get("text_hook"),
                         row["before_video"], row["after_video"], row.get("before_image"))


def publish(row, local_path):
    cid = row["carousel_id"]; key = cid + ".mp4"
    upload(OUT_BUCKET, key, local_path)
    url = sign_url(OUT_BUCKET, key, expires=YEAR)
    rest(TABLE + "?carousel_id=eq." + urllib.parse.quote(cid), "PATCH",
         {"final_video": url, "stitch_status": "done", "error_note": None,
          "updated_at": "now()"}, prefer="return=minimal")
    return url


def mark_failed(row, err):
    try:
        rest(TABLE + "?carousel_id=eq." + urllib.parse.quote(row["carousel_id"]), "PATCH",
             {"stitch_status": "stitch_failed", "error_note": str(err)[:300],
              "updated_at": "now()"}, prefer="return=minimal")
    except Exception:
        pass


def get_row(cid):
    rows = rest(TABLE + "?carousel_id=eq." + urllib.parse.quote(cid) + "&select=*")
    if not rows:
        raise SystemExit("no row " + cid)
    return rows[0]


def run_rows(rows, label):
    print(label, "rows to render:", len(rows or []))
    ok = 0; errs = []
    for row in (rows or []):
        try:
            p = render_row(row); url = publish(row, p); ok += 1
            print("  ok", row["carousel_id"], url[:80])
        except Exception as e:
            mark_failed(row, e)
            errs.append(row["carousel_id"] + ": " + str(e)[:120])
            print("  ERR", row["carousel_id"], str(e)[:120])
    print("DONE", label, "ok", ok, "errors", len(errs))
    for e in errs:
        print("   ", e)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "queue"
    if mode == "local":
        hook, bvid, avid = sys.argv[2], sys.argv[3], sys.argv[4]
        img = sys.argv[5] if len(sys.argv) > 5 else None
        p = render_assets("C3BA-LOCAL", hook, bvid, avid, img)
        print("RENDERED (local proof, no DB):", p, os.path.getsize(p), "bytes")
    elif mode == "test":
        row = get_row(sys.argv[2])
        p = render_row(row)
        print("RENDERED (local only, not uploaded):", p, os.path.getsize(p), "bytes")
    elif mode == "one":
        row = get_row(sys.argv[2])
        try:
            p = render_row(row); url = publish(row, p)
            print("DONE", row["carousel_id"], url)
        except Exception as e:
            mark_failed(row, e); raise
    elif mode == "batch":
        batch = sys.argv[2]
        rows = rest(TABLE + "?batch=eq." + urllib.parse.quote(batch) +
                    "&stitch_status=eq.ready&select=*&order=carousel_id")
        run_rows(rows, "batch " + batch)
    elif mode == "queue":
        rows = rest(TABLE + "?stitch_status=eq.ready&select=*&order=carousel_id")
        if not rows:
            print("QUEUE EMPTY: no ready char3_before_after rows"); return
        run_rows(rows, "queue")
    else:
        raise SystemExit("usage: render_char3_ba.py local <hook> <before> <after> [image] | test|one <cid> | batch <name> | queue")


if __name__ == "__main__":
    main()
