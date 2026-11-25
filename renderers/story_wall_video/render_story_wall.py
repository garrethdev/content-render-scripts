#!/usr/bin/env python3
"""Story Wall video (content type story_wall_video, Character 6) renderer.

An 8 second clip of her in the kitchen with one whole story from story_bank over it as a
single long paragraph (a wall of text). The text is on for the first 7 seconds and gone
for the last second, so the video ends on just her and the viewer has to watch it again
to finish reading.

A light dark shade sits behind the text (22 to 38%, a different strength per video, seeded by
the content id) and goes with the text.

  python3 render_story_wall.py                     # rows in story_wall_posts waiting to render
  python3 render_story_wall.py --batch sw-20261125 # one batch
  python3 render_story_wall.py SW-003 SW-007       # these rows, even if already rendered
  python3 render_story_wall.py --dry-run           # render to ./out/renders, no upload, no row changes
  python3 render_story_wall.py --story 18847 --clip 12 --out out/test   # test a story on a clip, no table

Rows come from create_batch.py. Finished files go to
kitchen-character/story-wall-video/renders/<YYYY-MM-DD>/<content_id>.mp4; the row gets video_url,
render_status = rendered, rendered_at and shade_pct. Keys through common/env (service key needed
for the table, which has no public access), or --env-file.

Look: the shared Character 6 text (common/slide_text.py: white Inter, black outline, soft
shadow, colour emoji), centred, no shift or tilt. The size is the largest that fits the
whole story, never below 52 px, between 220 px from the top and 430 px from the bottom (TikTok's top bar and
Instagram's caption zone stay clear), in a 920 px column.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import requests
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from common import env  # noqa: E402
from common import slide_text as ST  # noqa: E402
from common.ffguard import run_ffmpeg_guarded  # noqa: E402

W, H, FPS = 1080, 1920, 30
LENGTH = 8.0          # whole video (Garreth, 2026-11-25: 8 s)
TEXT_OFF = 7.0        # text disappears here; the last second is just her
TOP, BOTTOM, COL = 220, 430, 920
WEIGHT = "SemiBold"
SIZES = range(56, 51, -1)   # 52 px floor: the 124-word test at 53 px was right, the 164-word one at 46 px was too dense (Garreth, 2026-11-25)
LINE = 1.24
CLIP_CACHE = os.path.join(HERE, "cache", "clips")
BUCKET = "kitchen-character"
PREFIX = "story-wall-video"


def sb():
    url = env.require("SUPABASE_URL").rstrip("/")
    key = (env.get("SUPABASE_SERVICE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY")
           or env.require("SUPABASE_ANON_KEY"))
    return url, {"apikey": key, "Authorization": f"Bearer {key}"}


def get(table, **params):
    url, h = sb()
    r = requests.get(f"{url}/rest/v1/{table}", headers=h, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


TAG_RE = re.compile(r"^\s*[\[(]?\s*(NSV|SV)\s*[\])]?\s*[:!\-–—]*\s*", re.I)


def story_paragraph(row):
    """The story as one paragraph: whitespace collapsed, the post title joined to the body
    with a full stop when it has none, Reddit's 'NSV' tag dropped. Words are not changed."""
    title = re.sub(r"\s+", " ", (row.get("title") or "").strip())
    text = re.sub(r"\s+", " ", (row.get("text") or "").strip())
    if title and text.startswith(title):
        body = text[len(title):].strip()
        t = TAG_RE.sub("", title).strip()
        if t and t[-1] not in ".!?…":
            t += "."
        text = f"{t} {body}".strip()
    else:
        text = TAG_RE.sub("", text)
    return text


def fit(text):
    d = ImageDraw.Draw(Image.new("RGB", (W, H)))
    band = H - TOP - BOTTOM
    for size in SIZES:
        f = ST.font(WEIGHT, size)
        lines = ST.wrap(d, text, f, COL)
        asc, desc = f.getmetrics()
        step = round(size * LINE)
        height = step * (len(lines) - 1) + asc + desc
        if height <= band:
            return f, lines, step, height
    raise ValueError(f"story too long for one screen even at {SIZES[-1]} px ({len(text.split())} words)")


SHADE_RANGE = (0.22, 0.38)   # light dark shade behind the text; each video gets its own strength
SHADE_PAD, SHADE_BLUR = 70, 45


def shade_strength(key):
    """A strength in SHADE_RANGE seeded by the video id, so a re-render matches."""
    h = int(hashlib.sha1(str(key).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return round(SHADE_RANGE[0] + h * (SHADE_RANGE[1] - SHADE_RANGE[0]), 2)


def overlay(text, path, key):
    """Shade, then the text. The shade is a soft dark shape just bigger than the text block,
    gone together with the text in the last second."""
    f, lines, step, height = fit(text)
    top = TOP + (H - TOP - BOTTOM - height) / 2
    d = ImageDraw.Draw(Image.new("RGB", (W, H)))
    width = max(ST.measure(d, ln, f) for ln in lines)
    strength = shade_strength(key)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(W - width) / 2 - SHADE_PAD, top - SHADE_PAD, (W + width) / 2 + SHADE_PAD, top + height + SHADE_PAD],
        radius=SHADE_PAD, fill=int(255 * strength))
    mask = mask.filter(ImageFilter.GaussianBlur(SHADE_BLUR))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.putalpha(mask)
    ST.draw_lines(img, lines, f, top, step)
    img.save(path)
    return dict(size=f.size, lines=len(lines), words=len(text.split()), shade=strength)


def ffmpeg_bin():
    for c in (env.get("FFMPEG"), "ffmpeg"):
        if c and shutil.which(c):
            return shutil.which(c)
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def fetch_clip(clip):
    os.makedirs(CLIP_CACHE, exist_ok=True)
    ver = re.sub(r"\D", "", str(clip.get("updated_at") or ""))[:14] or "0"
    local = os.path.join(CLIP_CACHE, f"{ver}_{clip['filename']}")
    if not os.path.exists(local):
        with requests.get(clip["storage_path"] + "?v=" + ver, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(local + ".part", "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
        os.replace(local + ".part", local)
    return local


def render(clip_file, text, dst, key):
    ff = ffmpeg_bin()
    ovp = dst[:-4] + "_overlay.png"
    info = overlay(text, ovp, key)
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
          f"setsar=1,fps={FPS}[b];[b][1:v]overlay=0:0:enable='lt(t,{TEXT_OFF})',format=yuv420p[v]")
    cmd = [ff, "-v", "error", "-y", "-i", clip_file, "-loop", "1", "-t", str(LENGTH), "-i", ovp,
           "-filter_complex", vf, "-map", "[v]", "-an", "-t", str(LENGTH),
           "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high",
           "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart", dst]
    try:
        run_ffmpeg_guarded(cmd, dst, expected_seconds=LENGTH, verbose=False)
    finally:
        if os.path.exists(ovp):
            os.remove(ovp)
    return info


def probe(path):
    err = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if not m or not d:
        raise RuntimeError(f"could not read {path}")
    return int(m.group(1)), int(m.group(2)), int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))


def service():
    url = env.require("SUPABASE_URL").rstrip("/")
    key = (env.get("SUPABASE_SERVICE_KEY") or env.get("CAROUSEL_SUPABASE_SECRET_KEY")
           or env.get("SUPABASE_SERVICE_ROLE_KEY"))
    if not key:
        raise SystemExit("A service key is needed to upload and update rows (SUPABASE_SERVICE_KEY). "
                         "Use --dry-run to render without one.")
    return url, {"apikey": key, "Authorization": f"Bearer {key}"}


def upload(path, local):
    url, h = service()
    with open(local, "rb") as fh:
        r = requests.post(f"{url}/storage/v1/object/{BUCKET}/{path}", data=fh,
                          headers={**h, "Content-Type": "video/mp4", "x-upsert": "true"}, timeout=600)
    r.raise_for_status()
    return f"{url}/storage/v1/object/public/{BUCKET}/{path}"


def patch(row_id, body):
    url, h = service()
    r = requests.patch(f"{url}/rest/v1/story_wall_posts", params={"id": f"eq.{row_id}"},
                       headers={**h, "Content-Type": "application/json", "Prefer": "return=minimal"},
                       json=body, timeout=60)
    r.raise_for_status()


def run_rows(a):
    params = dict(select="id,content_id,batch,story_text,clip_no,render_status", order="content_id")
    if a.ids:
        params["content_id"] = "in.(" + ",".join(f'"{i}"' for i in a.ids) + ")"
    else:
        if a.batch:
            params["batch"] = f"eq.{a.batch}"
        if not a.rerender:
            params["or"] = "(render_status.is.null,render_status.in.(pending,failed))"
    rows = get("story_wall_posts", **params)[:a.limit]
    if not rows:
        print("nothing to render")
        return 0
    clips = {c["clip_no"]: c for c in get("quote_video_clips", is_active="eq.true",
                                         select="clip_no,filename,storage_path,duration_s,updated_at")}
    day = dt.date.today().isoformat()
    out = os.path.join(HERE, "out", "renders")
    os.makedirs(out, exist_ok=True)
    failed = 0
    for row in rows:
        cid = row["content_id"]
        try:
            clip = clips.get(row["clip_no"])
            if not clip:
                raise RuntimeError(f"clip {row['clip_no']} is not an active clip")
            if float(clip["duration_s"]) < LENGTH:
                raise RuntimeError(f"clip {clip['clip_no']} is {clip['duration_s']} s, shorter than {LENGTH} s")
            dst = os.path.join(out, f"{cid}.mp4")
            info = render(fetch_clip(clip), row["story_text"], dst, cid)
            w, h, secs = probe(dst)
            if (w, h) != (W, H) or abs(secs - LENGTH) > 0.25:
                raise RuntimeError(f"output is {w}x{h}, {secs:.2f}s; expected {W}x{H}, {LENGTH}s")
            note = (f"{cid}: clip {clip['clip_no']}, {info['words']} words, {info['lines']} lines at "
                    f"{info['size']} px, shade {round(info['shade'] * 100)}%")
            if a.dry_run:
                print("rendered", note, "->", os.path.relpath(dst))
                continue
            vurl = upload(f"{PREFIX}/renders/{day}/{cid}.mp4", dst)
            patch(row["id"], dict(video_url=vurl, render_status="rendered", render_error=None,
                                  shade_pct=round(info["shade"] * 100),
                                  rendered_at=dt.datetime.now(dt.timezone.utc).isoformat()))
            print("rendered + uploaded", note)
        except Exception as e:
            failed += 1
            print(f"FAILED {cid}: {e}", file=sys.stderr)
            if not a.dry_run:
                try:
                    patch(row["id"], {"render_status": "failed", "render_error": str(e)[:500]})
                except Exception as e2:
                    print(f"  could not mark {cid} failed: {e2}", file=sys.stderr)
    print(f"done: {len(rows) - failed} rendered, {failed} failed")
    return 1 if failed else 0


def run_test(a):
    if len(a.story) != len(a.clip):
        raise SystemExit("give one --clip per --story")
    os.makedirs(a.out, exist_ok=True)
    overrides = json.load(open(a.text_file)) if a.text_file else {}
    ids = ",".join(map(str, a.story))
    stories = {s["id"]: s for s in get("story_bank", select="id,title,text", id=f"in.({ids})")}
    nos = ",".join(map(str, a.clip))
    clips = {c["clip_no"]: c for c in get("quote_video_clips", select="clip_no,filename,storage_path,duration_s,updated_at",
                                         clip_no=f"in.({nos})")}
    for sid, cno in zip(a.story, a.clip):
        clip = clips[cno]
        text = overrides.get(str(sid)) or story_paragraph(stories[sid])
        dst = os.path.join(a.out, f"story{sid}_clip{cno}.mp4")
        info = render(fetch_clip(clip), text, dst, f"story{sid}")
        print(f"{os.path.basename(dst)}: {info['words']} words, {info['lines']} lines at {info['size']} px, shade {round(info['shade']*100)}%")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="content_id values to (re)render, e.g. SW-001")
    ap.add_argument("--batch", help="only rows in this batch")
    ap.add_argument("--rerender", action="store_true", help="with --batch: include rows already rendered")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true", help="render to ./out/renders only, no upload, no row changes")
    ap.add_argument("--story", type=int, action="append", help="test mode: a story_bank id (pair each with --clip)")
    ap.add_argument("--clip", type=int, action="append", help="test mode: a clip number")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "test"))
    ap.add_argument("--text-file", help="test mode: JSON {story_id: text} to use instead of story_bank text")
    ap.add_argument("--env-file")
    a = ap.parse_args()
    if a.env_file:
        env.load_env(os.path.expanduser(a.env_file))
    sys.exit(run_test(a) if a.story else run_rows(a))


if __name__ == "__main__":
    main()
