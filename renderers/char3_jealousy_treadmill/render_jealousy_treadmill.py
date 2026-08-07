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
Text (locked 8/6 final): ONE rounded solid WHITE box, BLACK Montserrat Bold,
balanced wrap, centered mid-screen. Quote on the before segment, payoff on the
after. Segment lengths vary slightly per piece via seg_lengths() so the batch
does not read as one template (before 5-7s, after 8.5-10s, deterministic).

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
PUNCH_AT = float(os.environ.get("JELT_PUNCH_AT", "4"))     # sec into the after clip
PUNCH_ZOOM = float(os.environ.get("JELT_PUNCH_ZOOM", "0.8"))  # crop fraction = 20% punch-in


def seg_lengths(cid):
    """Deterministic slight length variation per piece (re-renders reproduce):
    before 5.0-7.0s, after 8.5-10.0s, keyed off the carousel_id digits."""
    n = sum(ord(c) for c in cid)
    return 5.0 + (n % 5) * 0.5, 8.5 + ((n // 5) % 4) * 0.5
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


# ---- text-block overlay (single rounded black box, white Montserrat Bold) ----

MONTSERRAT = os.path.join(_HERE, "assets", "Montserrat-Bold.ttf")


def _font(size):
    return ImageFont.truetype(MONTSERRAT, size)


def build_text_png(lines_specs, out):
    """lines_specs: [(text, y_center_fraction, font_size)] -> transparent 1080x1440 PNG.
    Wrap-around-text style (user-locked 8/7, Canva "wrap around text"): each wrapped
    line gets its OWN white rounded rectangle sized to that line's width, stacked with
    a RADIUS-sized vertical overlap so they union into ONE continuous contoured shape
    that hugs the text outline (box steps in/out per line, no floating side gaps).
    Black Montserrat Bold. Drawing all boxes on a separate layer first makes the
    overlaps merge cleanly before the text goes on top."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    PAD_X, PAD_Y, RADIUS = 34, 16, 26
    for text, y_frac, size in lines_specs:
        font = _font(size)
        wrapped = textwrap.wrap(text, width=20)
        line_h = size + PAD_Y * 2
        step = line_h - RADIUS                       # overlap by RADIUS -> merged contour
        total_h = step * (len(wrapped) - 1) + line_h
        y = int(H * y_frac) - total_h // 2
        shape = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shape)
        geo = []
        for line in wrapped:
            bbox = font.getbbox(line)
            tw = bbox[2] - bbox[0]
            x0 = (W - tw) // 2 - PAD_X
            x1 = (W + tw) // 2 + PAD_X
            sd.rounded_rectangle([x0, y, x1, y + line_h], radius=RADIUS, fill=(255, 255, 255, 255))
            geo.append((line, bbox, y))
            y += step
        img.alpha_composite(shape)
        for line, bbox, yy in geo:
            tw = bbox[2] - bbox[0]
            d.text(((W - tw) // 2 - bbox[0], yy + PAD_Y - bbox[1]), line,
                   font=font, fill=(12, 12, 12, 255))
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
    quote_png = (build_text_png([(row["text_hook"], 0.45, 46)],
                                os.path.join(WORK, f"{cid}_quote.png"))
                 if (row.get("text_hook") or "").strip() else None)
    payoff_png = (build_text_png([(row["text_hook_after"], 0.45, 46)],
                                 os.path.join(WORK, f"{cid}_payoff.png"))
                  if (row.get("text_hook_after") or "").strip() else None)
    b_len, a_len = seg_lengths(cid)
    total = b_len + a_len
    # after-only rows (text_hook NULL, e.g. the SEMAGLUTIDE-face set) get no
    # overlay on the before segment; both-slot rows get quote then payoff.
    overlays, inputs = [], []
    prev = "base"
    if quote_png:
        inputs += ["-i", quote_png]
        overlays.append((prev, len(inputs) // 2 + 1, f"lt(t,{b_len})", "t1")); prev = "t1"
    if payoff_png:
        inputs += ["-i", payoff_png]
        overlays.append((prev, len(inputs) // 2 + 1, f"gte(t,{b_len})", "out"))
    # PUNCH_AT sec into the after clip, a harsh hard-cut zoom PUNCH_ZOOM tighter for
    # the remainder (re-emphasizes the reveal right as the payoff lands). Locked 8/7.
    if a_len > PUNCH_AT + 0.5:
        after_fc = (f"[1:v]{AFTER_CHAIN},split=2[af1][af2];"
                    f"[af1]trim=0:{PUNCH_AT},setpts=PTS-STARTPTS[a1];"
                    f"[af2]trim={PUNCH_AT},setpts=PTS-STARTPTS,"
                    f"crop=iw*{PUNCH_ZOOM}:ih*{PUNCH_ZOOM},scale={W}:{H}:flags=lanczos,setsar=1[a2];"
                    f"[b][a1][a2]concat=n=3:v=1:a=0,{FINISH}[base];")
    else:
        after_fc = f"[1:v]{AFTER_CHAIN}[a];[b][a]concat=n=2:v=1:a=0,{FINISH}[base];"
    fc = f"[0:v]{BEFORE_CHAIN}[b];" + after_fc
    for i, (src_lbl, idx, enable, dst) in enumerate(overlays):
        fc += f"[{src_lbl}][{idx}]overlay=0:0:enable='{enable}'[{dst}];"
    fc = fc.rstrip(";")
    out_lbl = overlays[-1][3] if overlays else "base"
    cmd = [FF, "-y", "-t", str(b_len), "-i", before, "-t", str(a_len), "-i", after] + inputs + [
           "-filter_complex", fc,
           "-map", f"[{out_lbl}]", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
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
