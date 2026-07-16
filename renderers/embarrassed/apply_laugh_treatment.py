#!/usr/bin/env python3
"""
Apply the "Oh no no no" laugh treatment to the EVEN-source half of the EA library.

Convention (user-approved 2026-07-07):
  - source_clip_id EVEN  -> laugh treatment (build intro + low tail under END clip)
  - source_clip_id ODD   -> stock cloned-voice VO (untouched)

For each even-source content row:
  1. render via stitch_embarrassed.py --local-only (renders/test_<content_id>.mp4,
     DB row untouched) with:
       EMBARRASSED_VO_BEGIN = assets/vo_begin_ohno.wav  (laugh 2-8s of source, builds 25%->100%)
       EMBARRASSED_VO_TAIL  = assets/vo_tail_ohno.wav   (laugh 8-16s, at 30% under the CTA)
       EMBARRASSED_VO_BUILD = 1
  2. upload the file to storage bucket `embarrassed-angle` as <content_id>.mp4 with
     x-upsert (SAME object name -> public URL unchanged, bytes replaced, no DB patch).

Idempotent: safe to re-run; it re-renders and re-uploads. Skips nothing by status
(none of the rows are Posted as of writing; Ready rows will post with the new audio).

Usage: /usr/bin/python3 apply_laugh_treatment.py [--limit N]
"""
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.expanduser("~/.config/peptide-secrets/.env")
for line in open(ENV_FILE):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SB_URL = "https://qlcmgxgwpzmiebzxflai.supabase.co"
SB_KEY = os.environ["CAROUSEL_SUPABASE_SECRET_KEY"].strip('"').strip("'")
BUCKET = "embarrassed-angle"

def sb_get(path):
    req = urllib.request.Request(SB_URL + path, headers={
        "apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def upload(local_path, object_name):
    with open(local_path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        f"{SB_URL}/storage/v1/object/{BUCKET}/{object_name}",
        data=data, method="POST",
        headers={"apikey": SB_KEY,  # sb_secret_ keys are not JWTs: apikey header, no Bearer
                 "Content-Type": "video/mp4", "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=120).read()

def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    rows = sb_get("/rest/v1/embarrassed_angle_content"
                  "?select=id,content_id,source_clip_id&order=id.asc")
    targets = [r for r in rows if r["source_clip_id"] % 2 == 0]
    if limit:
        targets = targets[:limit]
    print(f"laugh-treatment targets (even sources): {len(targets)}", flush=True)

    env = dict(os.environ,
               EMBARRASSED_VO_BEGIN=os.path.join(HERE, "assets", "vo_begin_ohno.wav"),
               EMBARRASSED_VO_TAIL=os.path.join(HERE, "assets", "vo_tail_ohno.wav"),
               EMBARRASSED_VO_BUILD="1")

    ok = fail = 0
    for r in targets:
        cid, name = r["id"], r["content_id"]
        try:
            subprocess.run(["/usr/bin/python3", os.path.join(HERE, "stitch_embarrassed.py"),
                            "--content_id", str(cid), "--local-only"],
                           env=env, check=True, capture_output=True, timeout=600)
            local = os.path.join(HERE, "renders", f"test_{name}.mp4")
            if not os.path.exists(local):
                raise RuntimeError("render output missing")
            upload(local, f"{name}.mp4")
            os.remove(local)
            ok += 1
            print(f"LAUGH OK   {name}", flush=True)
        except Exception as e:
            fail += 1
            msg = str(e)
            if isinstance(e, subprocess.CalledProcessError):
                msg = (e.stderr or b"").decode()[-200:]
            print(f"LAUGH FAIL {name}: {msg}", flush=True)

    print(f"DONE: {ok} uploaded, {fail} failed of {len(targets)}", flush=True)

if __name__ == "__main__":
    main()
