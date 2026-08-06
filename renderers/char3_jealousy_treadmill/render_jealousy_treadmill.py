#!/usr/bin/env python3
"""Jealousy-quote treadmill Before/After renderer (Character 3).

One fixed video pair (the treadmill masters in video-library/char3-treadmill/),
sixty-plus text pairs from jealousy_char3_content. Layout: 1080x1440 (3:4), 30fps.

  [BEFORE master, first 6s, heavy propped-camera jitter, text_hook burned]
    -> hard cut ->
  [AFTER master, 10s, calm jitter + 3% left crop + tighter frame + 5% punch-in,
   text_hook AND text_hook_after burned]

Camera + finish recipe locked 2026-08-06 in the gym-content session:
  jitter = stacked incommensurate sines (never loops, reads as real vibration),
  finish = approved iPhone pass (cool shift, curves, grain) + Apple metadata.
Text: TikTok caption style — TikTok Sans (shared hook-font.ttf), white text on a
black box per wrapped line, centered mid-screen. Quote on the before segment,
payoff on the after segment (user-locked format 8/6).

Source table: jealousy_char3_content (stitch_status ready -> done / stitch_failed).
`used`/`used_at` mark a hook pair as consumed so later batches never repeat copy.
Output: private bucket char3-before-after/<carousel_id>.mp4, 1-yr signed URL -> final_video.

Usage:
  python render_jealousy_treadmill.py test  <carousel_id>   # ONE row, local only, no upload/db
  python render_jealousy_treadmill.py one   <carousel_id>   # render + upload + patch ONE row
  python render_jealousy_treadmill.py batch <batch_name>    # rows where batch matches + not used
  python render_jealousy_treadmill.py queue [limit]         # every unused row (default all)
"""
import os, sys, json, subprocess, textwrap, urllib.request, urllib.parse
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)
from common import env
from common.ffguard import run_ffmpeg_guarded

env.load_env()
SB = os.environ.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co")
KEY = env.require("CAROUSEL_SUPABASE_SECRET_KEY")
FF = os.environ.get("FFMPEG", "ffmpeg")
WORK = os.environ.get("WORKDIR", os.path.join(_HERE, "work"))
os.makedirs(WORK, exist_ok=True)

TABLE = "jealousy_char3_content"
SRC_BUCKET, OUT_BUCKET = "video-library", "char3-before-after"
BEFORE_KEY = "char3-treadmill/before10_720p.mp4"
AFTER_KEY = "char3-treadmill/after10_720p.mp4"
W, H, FPS = 1080, 1440, 30
BEFORE_LEN = float(os.environ.get("JELT_BEFORE_LEN", "6"))
YEAR = 31536000
_H = {"apikey": KEY, "Authorization": "Bearer " + KEY}

from PIL import Image, ImageDraw, ImageFont, ImageFilter

TIKTOK_FONT = os.path.join(_REPO, "renderers", "char3_before_after", "assets", "hook-font.ttf")


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
    signed = urllib.parse.quote(signed, safe="/?&=%.")
    return SB + "/storage/v1" + signed


def fetch_master(key, out):
    if not os.path.exists(out):
        req = urllib.request.Request(sign_url(SRC_BUCKET, key),
                                     headers={"User-Agent": "Mozilla/5.0 (render_jealousy_treadmill)"})
        with urllib.request.urlopen(req, timeout=300) as r, open(out, "wb") as f:
            f.write(r.read())
    return out


def upload(bucket, key, path):
    with open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        SB + "/storage/v1/object/" + bucket + "/" + urllib.parse.quote(key),
        data=data, method="POST",
        headers={**_H, "Content-Type": "video/mp4", "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=600)


# ---- serif text overlay (Didot white + soft shadow, per the approved mockups) ----

def _font(size):
    return ImageFont.truetype(TIKTOK_FONT, size)


def build_text_png(lines_specs, out):
    """lines_specs: [(text, y_center_fraction, font_size)] -> transparent 1080x1440 PNG.
    TikTok caption style: each wrapped line sits on its own solid black box, white text."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    PAD_X, PAD_Y, GAP = 22, 12, 6
    for text, y_frac, size in lines_specs:
        font = _font(size)
        wrapped = textwrap.wrap(text, width=28)
        line_h = size + PAD_Y * 2
        total_h = line_h * len(wrapped) + GAP * (len(wrapped) - 1)
        y = int(H * y_frac) - total_h // 2
        for line in wrapped:
            bbox = d.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (W - tw) // 2
            d.rectangle([x - PAD_X, y, x + tw + PAD_X, y + line_h], fill=(0, 0, 0, 255))
            d.text((x - bbox[0], y + PAD_Y - bbox[1]), line, font=font, fill=(255, 255, 255, 255))
            y += line_h + GAP
    img.save(out)
    return out


# ---- the locked camera + finish recipe ----

BEFORE_CHAIN = (
    "scale=1160:1547:flags=lanczos,"
    "crop=1080:1440:x='(iw-ow)/2+5.5*sin(n/1.7)+3.2*sin(n/2.9+1.0)+5*sin(n/89)':"
    "y='(ih-oh)/2+7*sin(n/1.5+0.6)+4*sin(n/2.3+1.8)+4*sin(n/73)',fps=30,setsar=1")
AFTER_CHAIN = (
    "crop=iw*0.97:ih*0.97:x=iw*0.03:y='(ih-oh)/2',crop=iw*0.95:ih*0.95,"
    "scale=1160:1547:flags=lanczos,"
    "crop=1080:1440:x='(iw-ow)/2+3.5*sin(n/1.7)+2*sin(n/2.9+1.0)+4*sin(n/89)':"
    "y='(ih-oh)/2+4.5*sin(n/1.5+0.6)+2.5*sin(n/2.3+1.8)+3*sin(n/73)',fps=30,setsar=1")
FINISH = ("colorchannelmixer=rr=0.975:gg=1.0:bb=1.03,"
          "curves=all='0/0.01 1/0.985',noise=alls=9:allf=t+u")


def render(row, out_path):
    before = fetch_master(BEFORE_KEY, os.path.join(WORK, "before10_720p.mp4"))
    after = fetch_master(AFTER_KEY, os.path.join(WORK, "after10_720p.mp4"))
    cid = row["carousel_id"]
    quote_png = build_text_png([(row["text_hook"], 0.45, 46)],
                               os.path.join(WORK, f"{cid}_quote.png"))
    payoff_png = build_text_png([(row["text_hook_after"], 0.45, 46)],
                                os.path.join(WORK, f"{cid}_payoff.png"))
    total = BEFORE_LEN + 10
    cmd = [FF, "-y", "-t", str(BEFORE_LEN), "-i", before, "-i", after,
           "-i", quote_png, "-i", payoff_png,
           "-filter_complex",
           f"[0:v]{BEFORE_CHAIN}[b];[1:v]{AFTER_CHAIN}[a];"
           f"[b][a]concat=n=2:v=1:a=0,{FINISH}[base];"
           f"[base][2]overlay=0:0:enable='lt(t,{BEFORE_LEN})'[t1];"
           f"[t1][3]overlay=0:0:enable='gte(t,{BEFORE_LEN})'[out]",
           "-map", "[out]", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
           "-tune", "grain", "-pix_fmt", "yuv420p", "-an",
           "-metadata", "make=Apple", "-metadata", "model=iPhone 15 Pro",
           "-movflags", "use_metadata_tags", out_path, "-loglevel", "error"]
    run_ffmpeg_guarded(cmd, out_path, expected_seconds=total)
    return out_path


def patch(cid, body):
    rest(f"{TABLE}?carousel_id=eq.{urllib.parse.quote(cid)}", "PATCH", body)


def finish_row(row, out_path):
    cid = row["carousel_id"]
    key = f"{cid}.mp4"
    upload(OUT_BUCKET, key, out_path)
    final = sign_url(OUT_BUCKET, key, YEAR)
    patch(cid, {"final_video": final, "stitch_status": "done", "used": True,
                "used_at": datetime.now(timezone.utc).isoformat(),
                "before_clip": BEFORE_KEY, "after_clip": AFTER_KEY})
    os.remove(out_path)          # nothing kept local
    return final


def get_rows(where):
    return rest(f"{TABLE}?{where}&select=carousel_id,text_hook,text_hook_after,used&order=carousel_id")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "queue"
    if mode == "test":
        row = get_rows(f"carousel_id=eq.{sys.argv[2]}")[0]
        p = render(row, os.path.join(WORK, f"{row['carousel_id']}_test.mp4"))
        print("TEST OK (local only):", p)
        return
    if mode == "one":
        rows = get_rows(f"carousel_id=eq.{sys.argv[2]}")
    elif mode == "ids":
        rows = get_rows(f"carousel_id=in.({sys.argv[2]})")
    elif mode == "batch":
        rows = get_rows(f"batch=eq.{urllib.parse.quote(sys.argv[2])}&used=eq.false")
    else:
        rows = get_rows("used=eq.false")
        if len(sys.argv) > 2:
            rows = rows[: int(sys.argv[2])]
    print(f"{len(rows)} rows to render", flush=True)
    ok = fail = 0
    for row in rows:
        cid = row["carousel_id"]
        try:
            out = render(row, os.path.join(WORK, f"{cid}.mp4"))
            finish_row(row, out)
            ok += 1
            print(f"OK  {cid}", flush=True)
        except Exception as e:
            fail += 1
            patch(cid, {"stitch_status": "stitch_failed"})
            print(f"FAIL {cid}: {str(e)[:140]}", flush=True)
    print(f"DONE ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
