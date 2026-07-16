#!/usr/bin/env python3
"""Pull all APPROVED Character 2 "2-Slide Before/After" videos + metadata.

For handoff: no dependencies beyond Python 3.8+ stdlib. Uses the public
(anon) Supabase key — read-only access to public data, safe to share.

What it does:
  1. Queries ba_2slide_content for approved, finished 2BA rows
     (quality_status=approved, stitch_status=done) — 85 rows as of 2026-07-11.
  2. Downloads each final MP4 into ./char2_ba_approved/ (skips files it
     already has, so re-running resumes).
  3. Writes manifest.csv + manifest.json with everything needed to post:
     carousel_id, batch, angle, both text hooks, IG caption, suggested music,
     and the public video URL.

Usage:
  python3 pull_ba_approved.py            # pull into ./char2_ba_approved
  python3 pull_ba_approved.py /some/dir  # pull into a custom directory
"""
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common import env

SB = env.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co")
# Anon (publishable) key — read-only, NOT the service key.
KEY = env.require("SUPABASE_ANON_KEY")

FIELDS = ["carousel_id", "batch", "angle", "text_hook", "text_hook_after",
          "caption_story", "suggested_ig_music", "final_video", "created_at"]


def fetch_rows():
    q = (SB + "/rest/v1/ba_2slide_content"
         "?select=" + ",".join(FIELDS) +
         "&carousel_id=like.2BA-*"
         "&quality_status=eq.approved"
         "&stitch_status=eq.done"
         "&order=carousel_id.asc&limit=1000")
    req = urllib.request.Request(q, headers={"apikey": KEY, "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def download(row, outdir):
    url = row["final_video"]
    dest = os.path.join(outdir, row["carousel_id"] + ".mp4")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return row["carousel_id"], "cached"
    try:
        tmp = dest + ".part"
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, dest)
        return row["carousel_id"], "ok"
    except Exception as e:
        return row["carousel_id"], "ERROR: " + str(e)


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "char2_ba_approved"
    os.makedirs(outdir, exist_ok=True)

    rows = fetch_rows()
    print(f"approved finished videos: {len(rows)}")
    if not rows:
        sys.exit("nothing to pull")

    # manifests first, so metadata exists even if downloads are interrupted
    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump(rows, f, indent=1)
    with open(os.path.join(outdir, "manifest.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    errs = 0
    with ThreadPoolExecutor(8) as ex:
        for cid, status in ex.map(lambda r: download(r, outdir), rows):
            if status.startswith("ERROR"):
                errs += 1
                print(f"  {cid}  {status}")
    print(f"DONE: {len(rows) - errs}/{len(rows)} videos in ./{outdir}/  "
          f"(+ manifest.csv / manifest.json){'  ERRORS: ' + str(errs) if errs else ''}")


if __name__ == "__main__":
    main()
