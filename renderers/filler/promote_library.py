#!/usr/bin/env python3
"""Promote newly-ingested clips into the GRADED source library.

The n8n 'Creator Ingest' drops new clips into filler_library as status='clean' (metadata only).
This worker-side step picks those up and, for each:
  download (ScrapeCreators) -> AI-screen for a Black-women creator -> bake the unified grade ->
  upload graded to clips/ (raw backup to clips_raw/) -> mark status='library' (last_used_at=null).
Clips that fail the screen are marked 'discarded' so they're never retried.

Runs on the render-worker machine (same Supabase 'mailbox' pattern as worker.py — no n8n->worker
connection needed). Schedule it (cron/launchd) or run after an ingest. Usage: python3 promote_library.py [MAX]
"""
import os, sys, json, base64, subprocess, tempfile, urllib.request, urllib.parse
import config, supa, render

MAX = int(sys.argv[1]) if len(sys.argv) > 1 else 50
# unified neutralize+blend grade (same recipe baked into the existing 50 + characters)
GRADE = "normalize=smoothing=120:strength=0.7,eq=contrast=1.10:saturation=1.12,colortemperature=temperature=6200"
FF = config.FFMPEG
ORK = config.OPENROUTER_KEY
PUB = f"{config.SUPABASE_URL}/storage/v1/object/public/{config.BUCKET}/clips/"

def is_black_woman(frames):
    """Vision screen: True only if the main on-camera person clearly appears to be a Black woman.
    Conservative — any error/refusal or no clear person returns False."""
    content = [{"type": "text", "text": (
        "Frames from a short social video. Look at the MAIN on-camera person across the frames. "
        'Reply ONLY JSON {"is_black_woman":true|false,"confidence":"low|medium|high","note":"short"}. '
        "Set true ONLY if the primary person clearly appears to be a Black/African-descent woman. "
        "If no clear person/face is visible, set false.")}]
    for p in frames:
        content.append({"type": "image_url", "image_url":
            {"url": "data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()}})
    body = {"model": "anthropic/claude-haiku-4.5", "temperature": 0, "max_tokens": 150,
            "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": content}]}
    try:
        r = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + ORK, "Content-Type": "application/json"})
        txt = json.load(urllib.request.urlopen(r, timeout=90))["choices"][0]["message"]["content"]
        return bool(json.loads(txt[txt.find("{"):txt.rfind("}") + 1]).get("is_black_woman"))
    except Exception:
        return False

def set_status(aid, fields):
    supa.rest(f"filler_library?aweme_id=eq.{urllib.parse.quote(str(aid))}", "PATCH", fields, prefer="return=minimal")

def promote(clip):
    aid = str(clip["aweme_id"])
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "raw.mp4"); graded = os.path.join(tmp, "graded.mp4")
        render.download(render.scrape_play_url(clip["url"]), raw, render.UA)
        _, _, dur = render.probe(raw)
        frames = []
        for i, frac in enumerate((0.25, 0.6)):
            fp = os.path.join(tmp, f"f{i}.jpg")
            subprocess.run([FF, "-y", "-loglevel", "error", "-ss", str(round(dur * frac, 1)),
                            "-i", raw, "-frames:v", "1", "-vf", "scale=360:-1", fp], check=False)
            if os.path.exists(fp): frames.append(fp)
        if not (frames and is_black_woman(frames)):
            set_status(aid, {"status": "discarded"})
            return "discarded"
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", raw, "-vf", GRADE,
                        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                        "-c:a", "copy", graded], check=True, timeout=600)
        supa.upload(f"clips_raw/{aid}.mp4", open(raw, "rb").read(), "video/mp4")     # preserve original
        supa.upload(f"clips/{aid}.mp4", open(graded, "rb").read(), "video/mp4")       # graded library file
        set_status(aid, {"status": "library", "source_video_url": PUB + aid + ".mp4", "last_used_at": None})
        return "library"

def main():
    clips = supa.rest(f"filler_library?status=eq.clean&select=aweme_id,url,handle&limit={MAX}") or []
    print(f"promoting up to {len(clips)} newly-ingested 'clean' clips -> graded library...")
    counts = {"library": 0, "discarded": 0, "error": 0}
    for c in clips:
        try:
            res = promote(c); counts[res] += 1
            print(f"  @{c.get('handle')} {c['aweme_id']}: {res}", flush=True)
        except Exception as e:
            counts["error"] += 1
            print(f"  @{c.get('handle')} {c['aweme_id']}: ERROR {str(e)[:90]}", flush=True)
    print(f"done: {counts}")

if __name__ == "__main__":
    main()
