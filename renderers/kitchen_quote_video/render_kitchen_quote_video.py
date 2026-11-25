#!/usr/bin/env python3
"""Kitchen Quote Video renderer (content type kitchen_quote_video, Character 6).

Puts a post's on-screen line (quote_video_posts.hook_text) over a kitchen clip from
quote_video_clips with the dark fade, renders 1080x1920, uploads it to storage and marks
the row rendered. The song stays a name in quote_video_posts.music and is added at posting,
so every video is silent.

Clips: every active row in quote_video_clips, the white-shirt originals (1 to 27) and the
dusty-blue versions (28 to 33). A row with no clip_no gets the least used clip (posts that
already use it plus its use counter), clips with her face first; when a white clip and its
blue version are tied, the shirt with fewer posts wins, so the blue clips get their turn. A blue clip and the white
clip it was made from count as one scene, so one run does not use the same scene twice
until every other scene has had a turn, and never back to back.

Music: a row with no song gets the least used active song tagged kitchen_quote_video in
music_library, never the same song twice in a row.

  python3 render_kitchen_quote_video.py                     # rows waiting to render (no status, pending, failed)
  python3 render_kitchen_quote_video.py --batch 2026-12-01  # rows in one batch that are not rendered yet
  python3 render_kitchen_quote_video.py KQV-B-01 KQV-W-03   # these rows, even if already rendered
  python3 render_kitchen_quote_video.py --shirt blue        # only pick from the blue-shirt clips
  python3 render_kitchen_quote_video.py --dry-run           # render to ./out only, no upload, no row changes

Rendered files go to kitchen-character/kitchen-quote-video/renders/<YYYY-MM-DD>/<video_id>.mp4.
Rerendering a row keeps its clip unless --repick is given.

Connection: SUPABASE_URL plus a service key (SUPABASE_SERVICE_KEY, CAROUSEL_SUPABASE_SECRET_KEY
or SUPABASE_SERVICE_ROLE_KEY) through common/env. --dry-run can read with SUPABASE_ANON_KEY.
ffmpeg comes from FFMPEG / PATH, else the imageio-ffmpeg binary.
"""
import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from common import env  # noqa: E402
from common.ffguard import run_ffmpeg_guarded  # noqa: E402

BUCKET = "kitchen-character"
PREFIX = "kitchen-quote-video"
LANE = "kitchen_quote_video"
W, H, FPS, MAX_S = 1080, 1920, 24, 10.0
OUT = os.path.join(HERE, "out")
CLIP_CACHE = os.path.join(env.get("KQV_CACHE_DIR", os.path.join(HERE, "cache")), "clips")


# ---------- supabase ----------

class SB:
    def __init__(self, need_write):
        self.url = env.require("SUPABASE_URL").rstrip("/")
        key = (env.get("SUPABASE_SERVICE_KEY") or env.get("CAROUSEL_SUPABASE_SECRET_KEY")
               or env.get("SUPABASE_SERVICE_ROLE_KEY"))
        if not key:
            if need_write:
                raise SystemExit("A service key is needed to upload and update rows "
                                 "(SUPABASE_SERVICE_KEY). Use --dry-run to render without one.")
            key = env.require("SUPABASE_ANON_KEY")
        self.h = {"apikey": key, "Authorization": f"Bearer {key}"}

    def get(self, table, **params):
        r = requests.get(f"{self.url}/rest/v1/{table}", headers=self.h, params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def patch(self, table, row_id, body):
        r = requests.patch(f"{self.url}/rest/v1/{table}", params={"id": f"eq.{row_id}"},
                           headers={**self.h, "Content-Type": "application/json", "Prefer": "return=minimal"},
                           json=body, timeout=60)
        r.raise_for_status()

    def upload(self, path, local):
        with open(local, "rb") as f:
            r = requests.post(f"{self.url}/storage/v1/object/{BUCKET}/{path}", data=f,
                              headers={**self.h, "Content-Type": "video/mp4", "x-upsert": "true"}, timeout=600)
        r.raise_for_status()
        return f"{self.url}/storage/v1/object/public/{BUCKET}/{path}"


# ---------- ffmpeg ----------

def ffmpeg_bin():
    for c in (env.get("FFMPEG"), "ffmpeg"):
        if c and shutil.which(c):
            return shutil.which(c)
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe(ff, path):
    """(width, height, seconds) read from ffmpeg's own report."""
    err = subprocess.run([ff, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if not m or not d:
        raise RuntimeError(f"could not read {path}")
    secs = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    return int(m.group(1)), int(m.group(2)), secs


def fetch_clip(clip):
    """Download a clip once per storage version (the clips were replaced in place on 2026-11-24)."""
    os.makedirs(CLIP_CACHE, exist_ok=True)
    ver = re.sub(r"\D", "", str(clip.get("updated_at") or ""))[:14] or "0"
    local = os.path.join(CLIP_CACHE, f"{ver}_{clip['filename']}")
    if not os.path.exists(local) or os.path.getsize(local) == 0:
        url = clip["storage_path"] + "?v=" + ver
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(local + ".part", "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        os.replace(local + ".part", local)
    return local


def render_file(ff, clip_file, text, dst):
    import kqv_overlay as K
    sw, sh, secs = probe(ff, clip_file)
    dur = round(min(secs, MAX_S), 3)
    ov, info = K.build_overlay(text)
    ovp = dst[:-4] + "_overlay.png"
    ov.save(ovp)
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}")
    if sw < W:
        # the blue-shirt clips are 704x1248; a light sharpen after the upscale keeps them
        # close to the 1080-wide originals
        vf += ",unsharp=5:5:0.6:5:5:0.0"
    vf += f",setsar=1,fps={FPS}[b];[b][1:v]overlay=0:0:format=auto,format=yuv420p[v]"
    cmd = [ff, "-v", "error", "-y", "-i", clip_file, "-loop", "1", "-t", str(dur), "-i", ovp,
           "-filter_complex", vf, "-map", "[v]", "-an", "-t", str(dur),
           "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high",
           "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart", dst]
    try:
        run_ffmpeg_guarded(cmd, dst, expected_seconds=dur, verbose=False)
    finally:
        if os.path.exists(ovp):
            os.remove(ovp)
    ow, oh, osecs = probe(ff, dst)
    if (ow, oh) != (W, H) or abs(osecs - dur) > 0.25:
        raise RuntimeError(f"output is {ow}x{oh}, {osecs:.2f}s; expected {W}x{H}, {dur}s")
    return dict(lines=info["lines"], seconds=dur, source=f"{sw}x{sh}")


# ---------- picking ----------

def scene(c):
    return c.get("source_clip_no") or c["clip_no"]


def is_blue(c):
    return "blue" in (c.get("shirt_color") or "")


def pick_clip(clips, post_counts, run_scenes, last_scene, shirt, shirt_counts=None):
    pool = [c for c in clips if shirt == "any" or (shirt == "blue") == is_blue(c)]
    if not pool:
        raise SystemExit(f"no active clips for --shirt {shirt}")
    fresh = [c for c in pool if scene(c) != last_scene] or pool
    return min(fresh, key=lambda c: (run_scenes.get(scene(c), 0),
                                     post_counts.get(c["clip_no"], 0) + (c.get("usage_count") or 0),
                                     not c.get("face_visible"),
                                     (shirt_counts or {}).get(is_blue(c), 0), c["clip_no"]))


def pick_song(songs, song_counts, last):
    fresh = [s for s in songs if s != last] or songs
    return min(fresh, key=lambda s: (song_counts.get(s, 0), songs.index(s))) if fresh else None


# ---------- main ----------

def select_rows(sb, a):
    cols = "id,video_id,batch,clip_no,hook_text,music,render_status,shirt_color"
    if a.video_ids:
        ids = ",".join(f'"{v}"' for v in a.video_ids)
        rows = sb.get("quote_video_posts", select=cols, video_id=f"in.({ids})", order="video_id")
        missing = set(a.video_ids) - {r["video_id"] for r in rows}
        if missing:
            raise SystemExit(f"not in quote_video_posts: {', '.join(sorted(missing))}")
        return rows
    params = dict(select=cols, order="video_id", hook_text="not.is.null")
    if a.batch:
        params["batch"] = f"eq.{a.batch}"
    if not a.rerender:
        params["or"] = "(render_status.is.null,render_status.in.(pending,failed))"
    return sb.get("quote_video_posts", **params)[:a.limit]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video_ids", nargs="*", help="video_id values to (re)render")
    ap.add_argument("--batch", help="only rows in this batch")
    ap.add_argument("--rerender", action="store_true", help="with --batch: include rows already rendered")
    ap.add_argument("--repick", action="store_true", help="pick a new clip even if the row has one")
    ap.add_argument("--shirt", choices=["any", "white", "blue"], default="any",
                    help="which clips a new pick may use (white also covers the hands and food-only clips)")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true", help="render to ./out, no upload, no row changes")
    ap.add_argument("--env-file", help="extra .env to load; never committed")
    a = ap.parse_args()
    if a.env_file:
        env.load_env(os.path.expanduser(a.env_file))

    sb = SB(need_write=not a.dry_run)
    rows = select_rows(sb, a)
    if not rows:
        print("nothing to render")
        return
    clips = sb.get("quote_video_clips", is_active="eq.true", order="clip_no",
                   select="clip_no,filename,storage_path,duration_s,face_visible,shirt_color,"
                          "source_clip_no,usage_count,updated_at")
    by_no = {c["clip_no"]: c for c in clips}
    all_posts = sb.get("quote_video_posts", select="video_id,clip_no,music")
    post_counts, song_counts, shirt_counts = {}, {}, {}
    blue_nos = {c["clip_no"] for c in clips if is_blue(c)}
    for p in all_posts:
        if p["video_id"] in {r["video_id"] for r in rows}:
            continue  # the rows being rendered do not count against themselves
        post_counts[p["clip_no"]] = post_counts.get(p["clip_no"], 0) + 1
        b = p["clip_no"] in blue_nos
        shirt_counts[b] = shirt_counts.get(b, 0) + 1
        if p.get("music"):
            song_counts[p["music"]] = song_counts.get(p["music"], 0) + 1
    songs = [f"{s['artist']} - {s['title']}" for s in
             sb.get("music_library", select="artist,title", is_active="eq.true",
                    pillar_fit=f"cs.{{{LANE}}}", order="created_at")]

    ff = ffmpeg_bin()
    day = dt.date.today().isoformat()
    os.makedirs(OUT, exist_ok=True)
    run_scenes, last_scene, last_song = {}, None, None
    print(f"{len(rows)} row(s), {len(clips)} active clips "
          f"({sum(map(is_blue, clips))} blue), {len(songs)} songs{' [dry run]' if a.dry_run else ''}")

    ok = failed = 0
    for row in rows:
        vid = row["video_id"]
        body = {}
        try:
            clip = by_no.get(row.get("clip_no")) if not a.repick else None
            if row.get("clip_no") and not a.repick and clip is None:
                raise RuntimeError(f"clip {row['clip_no']} is not an active row in quote_video_clips")
            if clip is None:
                clip = pick_clip(clips, post_counts, run_scenes, last_scene, a.shirt, shirt_counts)
                body["clip_no"] = clip["clip_no"]
            body["shirt_color"] = clip.get("shirt_color")
            run_scenes[scene(clip)] = run_scenes.get(scene(clip), 0) + 1
            post_counts[clip["clip_no"]] = post_counts.get(clip["clip_no"], 0) + 1
            shirt_counts[is_blue(clip)] = shirt_counts.get(is_blue(clip), 0) + 1
            last_scene = scene(clip)
            if not row.get("music") and songs:
                body["music"] = pick_song(songs, song_counts, last_song)
                song_counts[body["music"]] = song_counts.get(body["music"], 0) + 1
            last_song = body.get("music") or row.get("music")

            dst = os.path.join(OUT, f"{vid}.mp4")
            info = render_file(ff, fetch_clip(clip), row["hook_text"], dst)
            note = (f"{vid}: clip {clip['clip_no']} {clip['filename']} ({info['source']}, "
                    f"{clip.get('shirt_color') or 'no shirt'}), {info['seconds']}s, "
                    f"song {last_song!r}, lines {info['lines']}")
            if a.dry_run:
                print("rendered", note, "->", os.path.relpath(dst))
            else:
                path = f"{PREFIX}/renders/{day}/{vid}.mp4"
                body.update(video_url=sb.upload(path, dst), local_file=f"renders/{day}/{vid}.mp4",
                            has_baked_audio=False, render_status="rendered", render_error=None,
                            rendered_at=dt.datetime.now(dt.timezone.utc).isoformat())
                sb.patch("quote_video_posts", row["id"], body)
                print("rendered + uploaded", note)
            ok += 1
        except Exception as e:  # one bad row should not stop the batch
            failed += 1
            print(f"FAILED {vid}: {e}", file=sys.stderr)
            if not a.dry_run:
                try:
                    sb.patch("quote_video_posts", row["id"],
                             {"render_status": "failed", "render_error": str(e)[:500]})
                except Exception as e2:
                    print(f"  could not mark {vid} failed: {e2}", file=sys.stderr)
    print(f"done: {ok} rendered, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
