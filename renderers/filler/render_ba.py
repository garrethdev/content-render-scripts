#!/usr/bin/env python3
"""Local ffmpeg renderer for the 2-slide Before/After (Grandma / Character 4) videos.
Replaces the Creatomate stitcher.

Layout (matches Creatomate template a9f6495d-...):
  1080x1920, 30fps. BEFORE segment (8s) -> hard cut -> AFTER segment (8s) = 16s total.
  text_hook burned on the BEFORE segment (0-8s), text_hook_after on the AFTER segment (8-16s).
  TikTok Sans, white fill + black stroke, centered, ~75% down. Silent audio (music is added at post time).

Source clips: private bucket `video-library`, signed via service key, keys before/<f> and after/<f>.
Output: bucket `grandma-before-after`/<carousel_id>.mp4, signed 1-year URL written to grandma_before_after.final_video.

Usage:
  python render_ba.py test  <carousel_id>     # render ONE existing row locally, NO upload / NO db write (proof)
  python render_ba.py one   <carousel_id>     # render + upload + patch ONE row
  python render_ba.py batch <batch_name>      # render every row in batch with empty final_video, upload + patch
"""
import os, sys, json, subprocess, urllib.request, urllib.parse
from PIL import Image, ImageDraw, ImageFont
import config

FF, FP, FONT, WORK = config.FFMPEG, config.FFPROBE, config.FONT, config.WORKDIR
SB, KEY = config.SUPABASE_URL, config.SERVICE_KEY
SRC_BUCKET, OUT_BUCKET = "video-library", "grandma-before-after"
W, H, FPS, SEG = 1080, 1920, 30, 8
YEAR = 31536000
_H = {"apikey": KEY, "Authorization": "Bearer " + KEY}


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
    with urllib.request.urlopen(urllib.request.Request(url), timeout=300) as r, open(out, "wb") as f:
        f.write(r.read())
    return out


def upload(bucket, key, path, content_type="video/mp4"):
    with open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        SB + "/storage/v1/object/" + bucket + "/" + urllib.parse.quote(key),
        data=data, method="POST", headers={**_H, "Content-Type": content_type, "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=600)


EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"
EMOJI_STRIKE = 160  # Apple Color Emoji only rasterizes at fixed strike sizes; 160 is the largest


def _is_emoji_cp(cp):
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2190 <= cp <= 0x21FF
            or 0x2B00 <= cp <= 0x2BFF or cp in (0xFE0F, 0x200D, 0x2764, 0x2728)
            or 0x1F3FB <= cp <= 0x1F3FF or 0x1F1E6 <= cp <= 0x1F1FF)


def _split_runs(s):
    """Split a string into (is_emoji, chunk) runs; ZWJ/VS16 stay glued to emoji runs."""
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
    """Render an emoji run via Apple Color Emoji, scaled to the hook font size."""
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


def make_segment(src_path, text, out_path, effects=False, seconds=SEG):
    """One 8s segment: 1080x1920/30fps, silent audio, caption composited LAST (after any zoom so
    the punch never clips it). effects=True adds a gentle ~1.5s opening float + a hard 1.25x cut-in
    punch engaging at t=1.5s on the VIDEO only."""
    png = out_path + ".png"; build_text_png(text, png)
    if effects:
        jx = "if(lt(t,1.5),(4*sin(2*PI*1.1*t)+1.5*sin(2*PI*3.0*t))*(1-t/1.5),0)"
        jy = "if(lt(t,1.5),(3.5*sin(2*PI*1.4*t)+1.2*sin(2*PI*3.7*t))*(1-t/1.5),0)"
        fc = ("[0:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d,"
              "scale=1144:2036,crop=w=1080:h=1920:x='32+(%s)':y='58+(%s)',setsar=1,split=2[base][z];"
              "[z]crop=w=864:h=1536:x=(iw-864)/2:y=(ih-1536)/2,scale=1080:1920,setsar=1[zoom];"
              "[base][zoom]overlay=x=0:y=0:enable='gte(t,1.5)'[fx];"
              "[fx][1:v]overlay=0:0[v]") % (W, H, W, H, FPS, jx, jy)
    else:
        fc = ("[0:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d[bg];"
              "[bg][1:v]overlay=0:0[v]") % (W, H, W, H, FPS)
    subprocess.run([FF, "-y", "-loglevel", "error",
                    "-stream_loop", "-1", "-i", src_path, "-i", png,
                    "-f", "lavfi", "-t", str(seconds), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-filter_complex", fc, "-map", "[v]", "-map", "2:a", "-t", str(seconds),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "44100", out_path], check=True, timeout=300)
    return out_path


def render_row(row):
    cid = row["carousel_id"]
    bkey = row["before_clip"]; akey = row["after_clip"]
    bkey = bkey if bkey.startswith("before/") else "before/" + bkey
    akey = akey if akey.startswith("after/") else "after/" + akey
    b_src = os.path.join(WORK, cid + "_b_src.mp4"); a_src = os.path.join(WORK, cid + "_a_src.mp4")
    download(sign_url(SRC_BUCKET, bkey), b_src)
    download(sign_url(SRC_BUCKET, akey), a_src)
    b_seg = make_segment(b_src, row.get("text_hook") or "", os.path.join(WORK, cid + "_b.mp4"), effects=True, seconds=6)
    a_seg = make_segment(a_src, row.get("text_hook_after") or "", os.path.join(WORK, cid + "_a.mp4"), effects=False, seconds=6)
    out = os.path.join(WORK, cid + ".mp4")
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", b_seg, "-i", a_seg,
                    "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", out], check=True, timeout=300)
    return out


def publish(row, local_path):
    cid = row["carousel_id"]; key = cid + ".mp4"
    upload(OUT_BUCKET, key, local_path)
    url = sign_url(OUT_BUCKET, key, expires=YEAR)
    rest("grandma_before_after?carousel_id=eq." + urllib.parse.quote(cid), "PATCH",
         {"final_video": url, "stitch_status": "done"}, prefer="return=minimal")
    return url


def publish_ba(row, local_path):
    """Render output for ba_2slide_content rows: upload to a public bucket (easy review links),
    write ONLY final_video + stitch_status back (guard-allowed)."""
    cid = row["carousel_id"]; key = "owg_renders/" + cid + ".mp4"
    upload("rich-life-images", key, local_path)
    url = SB + "/storage/v1/object/public/rich-life-images/" + key
    rest("ba_2slide_content?carousel_id=eq." + urllib.parse.quote(cid), "PATCH",
         {"final_video": url, "stitch_status": "done"}, prefer="return=minimal")
    return url


def get_row(cid):
    rows = rest("grandma_before_after?carousel_id=eq." + urllib.parse.quote(cid) + "&select=*")
    if not rows:
        raise SystemExit("no row " + cid)
    return rows[0]


APPROVED = "&audit_status=eq.approved&gatekeep_status=eq.approved"

def run_rows(rows, publish_fn, label):
    print(label, "rows to render:", len(rows or []))
    ok = 0; errs = []
    for row in (rows or []):
        try:
            p = render_row(row); publish_fn(row, p); ok += 1
            print("  ok", row["carousel_id"])
        except Exception as e:
            errs.append(row["carousel_id"] + ": " + str(e)[:120])
            print("  ERR", row["carousel_id"], str(e)[:120])
    print("DONE", label, "ok", ok, "errors", len(errs))
    for e in errs:
        print("   ", e)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "test"
    if mode == "test":
        row = get_row(sys.argv[2])
        p = render_row(row)
        print("RENDERED (local only, not uploaded):", p, os.path.getsize(p), "bytes")
    elif mode == "one":
        row = get_row(sys.argv[2])
        p = render_row(row); url = publish(row, p)
        print("DONE", row["carousel_id"], url)
    elif mode == "batch":
        prefix = sys.argv[2]
        rows = rest("grandma_before_after?carousel_id=like." + urllib.parse.quote(prefix) + "*" +
                    "&or=(final_video.is.null,final_video.eq.)&select=*&order=carousel_id")
        print("batch", prefix, "rows to render:", len(rows or []))
        ok = 0; errs = []
        for row in (rows or []):
            try:
                p = render_row(row); publish(row, p); ok += 1
                print("  ok", row["carousel_id"])
            except Exception as e:
                errs.append(row["carousel_id"] + ": " + str(e)[:120])
                print("  ERR", row["carousel_id"], str(e)[:120])
        print("DONE batch", prefix, "ok", ok, "errors", len(errs))
        for e in errs:
            print("   ", e)
    elif mode == "ba":
        prefix = sys.argv[2]
        rows = rest("ba_2slide_content?carousel_id=like." + urllib.parse.quote(prefix) + "*" +
                    "&before_clip=not.is.null&or=(final_video.is.null,final_video.eq.)&select=*&order=carousel_id")
        print("ba batch", prefix, "rows to render:", len(rows or []))
        ok = 0; errs = []
        for row in (rows or []):
            try:
                p = render_row(row); publish_ba(row, p); ok += 1
                print("  ok", row["carousel_id"])
            except Exception as e:
                errs.append(row["carousel_id"] + ": " + str(e)[:120])
                print("  ERR", row["carousel_id"], str(e)[:120])
        print("DONE ba", prefix, "ok", ok, "errors", len(errs))
        for e in errs:
            print("   ", e)
    elif mode == "queue":
        # command-center mode: audit+gate approved grandma rows with no video yet
        rows = rest("grandma_before_after?select=*" + APPROVED +
                    "&or=(final_video.is.null,final_video.eq.)&order=carousel_id")
        if not rows:
            print("QUEUE EMPTY: no approved unrendered grandma rows"); return
        run_rows(rows, publish, "queue")
    elif mode == "ba-queue":
        # command-center mode: audit+gate approved 2-slide rows with no video yet
        rows = rest("ba_2slide_content?select=*" + APPROVED + "&before_clip=not.is.null" +
                    "&or=(final_video.is.null,final_video.eq.)&order=carousel_id")
        if not rows:
            print("QUEUE EMPTY: no approved unrendered ba rows"); return
        run_rows(rows, publish_ba, "ba-queue")
    else:
        raise SystemExit("usage: render_ba.py test|one|batch|ba <arg> | queue | ba-queue")


if __name__ == "__main__":
    main()
