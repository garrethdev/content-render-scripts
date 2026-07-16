"""Fill filler_library.thumb_url for newly-ingested clips.

n8n ingests clips into filler_library with no preview (TikTok covers are HEIC and IG
covers expire, so we grab a frame from the video instead). This runs from the worker's
idle cycle, so a clip ingested by n8n gets a preview within a poll or two — no separate
scheduler. It's a no-op when nothing is missing (one cheap Supabase read).
"""
import os, base64, subprocess, urllib.parse
import config, supa, render

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")


def fill_missing(limit=50):
    """Generate inline JPEG previews for up to `limit` clips that lack one.
    Returns (ok, failed)."""
    rows = supa.rest("filler_library?select=aweme_id,url&thumb_url=is.null"
                     f"&order=created_at.desc&limit={limit}") or []
    if not rows:
        return 0, 0
    ok = fail = 0
    for r in rows:
        aid = r["aweme_id"]
        url = r.get("url") or ""
        ref = "https://www.instagram.com/" if "instagram.com" in url else "https://www.tiktok.com/"
        jpg = os.path.join(config.WORKDIR, f"thumb_{aid}.jpg")
        try:
            play = render.scrape_play_url(url)
            subprocess.run([config.FFMPEG, "-y", "-loglevel", "error", "-user_agent", UA,
                            "-headers", f"Referer: {ref}\r\n", "-ss", "1.2", "-i", play,
                            "-frames:v", "1", "-vf", "scale=170:-1", "-q:v", "7", jpg],
                           check=True, timeout=90)
            with open(jpg, "rb") as f:
                b = base64.b64encode(f.read()).decode()
            supa.rest("filler_library?aweme_id=eq." + urllib.parse.quote(str(aid)), "PATCH",
                      {"thumb_url": "data:image/jpeg;base64," + b}, prefer="return=minimal")
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  [thumbs] FAIL {aid}: {str(e)[:80]}")
        finally:
            try:
                os.remove(jpg)
            except OSError:
                pass
    return ok, fail
