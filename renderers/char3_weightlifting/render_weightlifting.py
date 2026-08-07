#!/usr/bin/env python3
"""Char 3 metabolic-health "weightlifting" director-stitch (montage lane).

Recreates the DbJi1GwJH2i metabolism reel format with our own footage:

  [after-shot montage, 4 clips, randomized order, ~4.5s each = ~18s]
    text beats over the montage (wrap-around white box, Montserrat Bold):
      0.0-4.5s   HOOK   (mito_hooks.hook_text — the "I can spot how you..." diagnosis)
      4.5-9.0s   BEAT1  (uncontrollable cause — insulin resistance)
      9.0-13.5s  BEAT2  (until recently, hopeless)
      13.5-18s   BEAT3  (P3ptides made it controllable)
  [ ~20% of rows only ] + ~2s frozen still of an Option-A (bigger/before) clip,
    overlaid "Me insulin resistant, before peptides.." in Anton (white + black stroke).

Option B (after/fit footage) is the montage; barbell/free-squat is EXCLUDED
(machine squat kept). Option A (bigger/before) appears ONLY as the end still.
Silent render — music rides in suggested_ig_music (attached on IG at post time).

Source table: mito_hooks (gate_status=approved). beat1/2/3, suggested_ig_music,
before_card, caption are pre-assigned; used/used_at/final_video written on render.
Output: private bucket char3-before-after/<hook_id>.mp4, 1-yr signed URL -> final_video.

Usage:
  python render_weightlifting.py test  <hook_id>     # ONE row, local only
  python render_weightlifting.py one   <hook_id>     # render + upload + patch ONE
  python render_weightlifting.py batch <batch_name>  # approved rows in batch, not used
  python render_weightlifting.py queue [limit]       # every approved not-used row
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
FP = os.environ.get("FFPROBE", "ffprobe")
WORK = os.environ.get("WORKDIR", os.path.join(_HERE, "work"))
os.makedirs(WORK, exist_ok=True)

TABLE = "mito_hooks"
SRC_BUCKET, OUT_BUCKET = "video-library", "char3-before-after"
AFTER = ["after_machine", "after_kitchen", "after_cablerow", "after_legpress"]   # Option B pool
BEFORE = ["before_machine", "before_kitchen", "before_cablerow", "before_legpress"]  # Option A stills
W, H, FPS = 1080, 1920, 30
CLIP_LEN = float(os.environ.get("WL_CLIP_LEN", "4.5"))
BEFORE_CARD_LEN = float(os.environ.get("WL_BEFORE_LEN", "2"))
BEFORE_CARD_TEXT = "Me insulin resistant, before peptides.."
YEAR = 31536000
_H = {"apikey": KEY, "Authorization": "Bearer " + KEY}

from PIL import Image, ImageDraw, ImageFont

MONTSERRAT = os.path.join(_HERE, "assets", "Montserrat-Bold.ttf")
ANTON = os.path.join(_HERE, "assets", "Anton-Regular.ttf")


def rest(path, method="GET", body=None):
    hd = dict(_H); data = None
    if body is not None:
        hd["Content-Type"] = "application/json"; data = json.dumps(body).encode()
    req = urllib.request.Request(SB + "/rest/v1/" + path, data=data, method=method, headers=hd)
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
    return SB + "/storage/v1" + urllib.parse.quote(signed, safe="/?&=%.")


def fetch(name, out):
    if not os.path.exists(out):
        req = urllib.request.Request(sign_url(SRC_BUCKET, f"char3-weightlifting/{name}.mp4"),
                                     headers={"User-Agent": "Mozilla/5.0 (render_weightlifting)"})
        with urllib.request.urlopen(req, timeout=300) as r, open(out, "wb") as f:
            f.write(r.read())
    return out


def upload(bucket, key, path):
    with open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(SB + "/storage/v1/object/" + bucket + "/" + urllib.parse.quote(key),
                                 data=data, method="POST",
                                 headers={**_H, "Content-Type": "video/mp4", "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=600)


# ---- wrap-around-text card (Montserrat, white contoured box) ----

def wrap_card(text, y_frac, out, size=48, wrap=22):
    font = ImageFont.truetype(MONTSERRAT, size)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    wrapped = textwrap.wrap(text, width=wrap)
    PAD_X, PAD_Y, RADIUS = 34, 16, 26
    line_h = size + PAD_Y * 2; step = line_h - RADIUS
    total = step * (len(wrapped) - 1) + line_h; y = int(H * y_frac) - total // 2
    shape = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sd = ImageDraw.Draw(shape); geo = []
    for ln in wrapped:
        bb = font.getbbox(ln); tw = bb[2] - bb[0]
        sd.rounded_rectangle([(W - tw)//2 - PAD_X, y, (W + tw)//2 + PAD_X, y + line_h],
                             radius=RADIUS, fill=(255, 255, 255, 255))
        geo.append((ln, bb, y)); y += step
    img.alpha_composite(shape)
    for ln, bb, yy in geo:
        tw = bb[2] - bb[0]
        d.text(((W - tw)//2 - bb[0], yy + PAD_Y - bb[1]), ln, font=font, fill=(12, 12, 12, 255))
    img.save(out); return out


# ---- Anton outline caption (the "before peptides" punchline over the Option-A still) ----

def anton_card(text, out, size=104, wrap=16):
    font = ImageFont.truetype(ANTON, size)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    wrapped = textwrap.wrap(text, width=wrap)
    line_h = int(size * 1.05)
    total = line_h * len(wrapped); y = int(H * 0.5) - total // 2
    stroke = max(6, size // 12)
    for ln in wrapped:
        bb = d.textbbox((0, 0), ln, font=font, stroke_width=stroke); tw = bb[2] - bb[0]
        x = (W - tw)//2 - bb[0]
        d.text((x, y - bb[1]), ln, font=font, fill=(255, 255, 255, 255),
               stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        y += line_h
    img.save(out); return out


FINISH = ("colorchannelmixer=rr=0.975:gg=1.0:bb=1.03,curves=all='0/0.01 1/0.985',"
          "fps=30,noise=alls=9:allf=t+u")
COVER = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30"


def order_for(hid):
    """Deterministic montage order + before-still pick from the hook id."""
    s = sum(ord(c) for c in hid)
    order = AFTER[s % 4:] + AFTER[:s % 4]      # rotate start
    if s % 2:
        order = list(reversed(order))
    before_pick = BEFORE[(s // 3) % len(BEFORE)]
    return order, before_pick


def render(row, out_path):
    hid = row["hook_id"]
    order, before_pick = order_for(hid)
    clips = [fetch(n, os.path.join(WORK, f"{n}.mp4")) for n in order]
    # text cards
    cards = [
        wrap_card(row["hook_text"], 0.22, os.path.join(WORK, f"{hid}_hook.png"), size=44, wrap=23),
        wrap_card(row["beat1"], 0.22, os.path.join(WORK, f"{hid}_b1.png"), size=46, wrap=22),
        wrap_card(row["beat2"], 0.22, os.path.join(WORK, f"{hid}_b2.png"), size=48, wrap=20),
        wrap_card(row["beat3"], 0.22, os.path.join(WORK, f"{hid}_b3.png"), size=48, wrap=20),
    ]
    # montage inputs + card overlays
    inp = []
    for c in clips:
        inp += ["-t", str(CLIP_LEN), "-i", c]
    for c in cards:
        inp += ["-i", c]
    vparts = "".join(f"[{i}:v]{COVER}[v{i}];" for i in range(4))
    concat = "".join(f"[v{i}]" for i in range(4)) + "concat=n=4:v=1:a=0," + FINISH + "[base];"
    b = CLIP_LEN
    ov = (f"[base][4]overlay=0:0:enable='lt(t,{b})'[t1];"
          f"[t1][5]overlay=0:0:enable='between(t,{b},{2*b})'[t2];"
          f"[t2][6]overlay=0:0:enable='between(t,{2*b},{3*b})'[t3];"
          f"[t3][7]overlay=0:0:enable='gte(t,{3*b})'[mv]")
    montage = os.path.join(WORK, f"{hid}_montage.mp4")
    cmd = [FF, "-y"] + inp + ["-filter_complex", vparts + concat + ov,
           "-map", "[mv]", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-tune", "grain",
           "-pix_fmt", "yuv420p", "-an", montage, "-loglevel", "error"]
    run_ffmpeg_guarded(cmd, montage, expected_seconds=4 * CLIP_LEN)

    if not row.get("before_card"):
        os.replace(montage, out_path)
        return out_path

    # Option A end still: frozen frame from a before clip + Anton punchline, ~2s, then concat
    bclip = fetch(before_pick, os.path.join(WORK, f"{before_pick}.mp4"))
    frame = os.path.join(WORK, f"{hid}_beforeframe.png")
    subprocess.run([FF, "-y", "-loglevel", "error", "-ss", "2.5", "-i", bclip,
                    "-frames:v", "1", frame], check=True)
    acard = anton_card(BEFORE_CARD_TEXT, os.path.join(WORK, f"{hid}_anton.png"))
    card_mp4 = os.path.join(WORK, f"{hid}_card.mp4")
    subprocess.run([FF, "-y", "-loglevel", "error", "-loop", "1", "-t", str(BEFORE_CARD_LEN),
                    "-i", frame, "-i", acard, "-filter_complex",
                    f"[0:v]{COVER},{FINISH}[bg];[bg][1]overlay=0:0[o]",
                    "-map", "[o]", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-tune", "grain", "-pix_fmt", "yuv420p", "-r", "30", card_mp4], check=True)
    lst = os.path.join(WORK, f"{hid}_concat.txt")
    open(lst, "w").write(f"file '{montage}'\nfile '{card_mp4}'\n")
    run_ffmpeg_guarded([FF, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-tune", "grain",
                        "-pix_fmt", "yuv420p", "-an",
                        "-metadata", "make=Apple", "-metadata", "model=iPhone 15 Pro",
                        "-movflags", "use_metadata_tags", out_path, "-loglevel", "error"],
                       out_path, expected_seconds=4 * CLIP_LEN + BEFORE_CARD_LEN)
    return out_path


def get_rows(where):
    return rest(f"{TABLE}?{where}&select=hook_id,hook_text,beat1,beat2,beat3,before_card,"
                f"suggested_ig_music,used&order=hook_id")


def finish_row(row, out_path):
    hid = row["hook_id"]
    key = f"{hid}.mp4"
    upload(OUT_BUCKET, key, out_path)
    final = sign_url(OUT_BUCKET, key, YEAR)
    rest(f"{TABLE}?hook_id=eq.{urllib.parse.quote(hid)}", "PATCH",
         {"final_video": final, "stitch_status": "done", "used": True,
          "used_at": datetime.now(timezone.utc).isoformat()})
    os.remove(out_path)
    return final


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "queue"
    if mode == "test":
        row = get_rows(f"hook_id=eq.{sys.argv[2]}")[0]
        p = render(row, os.path.join(WORK, f"{row['hook_id']}_test.mp4"))
        print("TEST OK (local only):", p); return
    if mode == "one":
        rows = get_rows(f"hook_id=eq.{sys.argv[2]}")
    elif mode == "batch":
        rows = get_rows(f"batch=eq.{urllib.parse.quote(sys.argv[2])}&gate_status=eq.approved&used=eq.false")
    else:
        rows = get_rows("gate_status=eq.approved&used=eq.false")
        if len(sys.argv) > 2:
            rows = rows[: int(sys.argv[2])]
    print(f"{len(rows)} rows to render", flush=True)
    ok = fail = 0
    for row in rows:
        hid = row["hook_id"]
        try:
            out = render(row, os.path.join(WORK, f"{hid}.mp4"))
            finish_row(row, out); ok += 1; print(f"OK  {hid}", flush=True)
        except Exception as e:
            fail += 1
            rest(f"{TABLE}?hook_id=eq.{urllib.parse.quote(hid)}", "PATCH", {"stitch_status": "stitch_failed"})
            print(f"FAIL {hid}: {str(e)[:140]}", flush=True)
    print(f"DONE ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
