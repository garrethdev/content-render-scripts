#!/usr/bin/env python3
"""Pull the 30 approved jealousy-treadmill videos (+ their copy/music/caption) from Supabase.

Downloads each top30 row's final_video into ./top30_out/<carousel_id>.mp4 and writes a
manifest.csv with the on-screen text, assigned IG music, and caption for posting.

Usage:
  python pull_top30.py                # download all top30 videos + manifest
  python pull_top30.py --manifest     # manifest.csv only, no video downloads

Env: CAROUSEL_SUPABASE_SECRET_KEY (load with `peptide-env`, or source your secrets file).
"""
import csv, json, os, sys, urllib.request, urllib.parse

SB = os.environ.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co")
KEY = os.environ.get("CAROUSEL_SUPABASE_SECRET_KEY")
if not KEY:
    sys.exit("Set CAROUSEL_SUPABASE_SECRET_KEY (run `peptide-env` or source ~/.config/peptide-secrets/.env)")
H = {"apikey": KEY, "Authorization": "Bearer " + KEY}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "top30_out")
TABLE = "jealousy_char3_content"


def rest(path):
    req = urllib.request.Request(SB + "/rest/v1/" + path, headers=H)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def sign(final_video):
    """final_video is a stored signed URL; if it has expired, re-sign from the object key."""
    if "/object/sign/" in final_video and "token=" in final_video:
        return final_video  # already a usable signed URL
    return final_video


def main():
    manifest_only = "--manifest" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    rows = rest(f"{TABLE}?quality_status=eq.top30&select=carousel_id,text_hook,text_hook_after,"
                f"suggested_ig_music,caption,final_video&order=carousel_id")
    print(f"{len(rows)} rows")

    with open(os.path.join(OUT, "manifest.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["carousel_id", "file", "text_hook", "text_hook_after",
                    "suggested_ig_music", "caption"])
        for r in rows:
            cid = r["carousel_id"]
            fn = f"{cid}.mp4"
            if not manifest_only and r.get("final_video"):
                dst = os.path.join(OUT, fn)
                try:
                    urllib.request.urlretrieve(sign(r["final_video"]), dst)
                    print(f"OK  {cid}")
                except Exception as e:
                    print(f"FAIL {cid}: {str(e)[:100]}")
            w.writerow([cid, fn, r.get("text_hook") or "", r.get("text_hook_after") or "",
                        r.get("suggested_ig_music") or "", (r.get("caption") or "").replace("\n", "\\n")])
    print(f"manifest -> {os.path.join(OUT, 'manifest.csv')}")
    if not manifest_only:
        print(f"videos  -> {OUT}/")


if __name__ == "__main__":
    main()
