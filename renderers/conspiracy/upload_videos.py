#!/usr/bin/env python3
"""Upload rendered conspiracy-kitchen MP4s to Supabase storage and set video_url per row.
Maps each BATCH*.mp4 to its story by the sanitized-title embedded in the filename,
uploads as <content_id>.mp4 to the 'conspiracy-kitchen' bucket, sets medical_conspiracy_stories.video_url.

    python3 upload_videos.py --dry     # show the mapping only
    python3 upload_videos.py           # upload + set video_url
"""
import os, re, json, glob, urllib.request, argparse

PROJECT = "qlcmgxgwpzmiebzxflai"
BASE = f"https://{PROJECT}.supabase.co"
BUCKET = "conspiracy-kitchen"
EDIT = "/Users/garrethdottin/Desktop/AI Video Generation /Character 4 /Edit"
ENVFILE = os.path.expanduser("~/.config/peptide-secrets/.env")

def load_key():
    for line in open(ENVFILE):
        if line.startswith("CAROUSEL_SUPABASE_SECRET_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("CAROUSEL_SUPABASE_SECRET_KEY not found")

KEY = load_key()
H = {"apikey": KEY, "Authorization": "Bearer " + KEY}

def sanitize(title):
    t = re.sub(r'[^A-Za-z0-9 ]+', ' ', title or 'story').strip()
    return re.sub(r'\s+', ' ', t)[:48].strip()

def fetch_stories():
    q = f"{BASE}/rest/v1/medical_conspiracy_stories?select=id,content_id,title&music_id=not.is.null"
    return json.load(urllib.request.urlopen(urllib.request.Request(q, headers=H), timeout=30))

def match(files, stories):
    by_sani = {sanitize(s["title"]): s for s in stories}
    pairs, unmatched = [], []
    for f in files:
        base = os.path.basename(f)
        m = re.match(r'^BATCH\d*\s*-\s*(.+?)\s*-\s*Order\d.*\.mp4$', base)
        if not m: unmatched.append(base); continue
        tp = m.group(1).strip()
        s = by_sani.get(tp) or by_sani.get(tp[:48].strip())
        if not s:
            s = next((v for k, v in by_sani.items() if k[:40] == tp[:40]), None)
        if not s: unmatched.append(base); continue
        pairs.append((f, s))
    return pairs, unmatched

def upload(f, content_id):
    data = open(f, "rb").read()
    obj = f"{content_id}.mp4"
    req = urllib.request.Request(f"{BASE}/storage/v1/object/{BUCKET}/{obj}", data=data, method="POST",
                                 headers={**H, "Content-Type": "video/mp4", "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=180)
    return f"{BASE}/storage/v1/object/public/{BUCKET}/{obj}"

def set_url(sid, url):
    req = urllib.request.Request(f"{BASE}/rest/v1/medical_conspiracy_stories?id=eq.{sid}",
                                 data=json.dumps({"video_url": url}).encode(), method="PATCH",
                                 headers={**H, "Content-Type": "application/json", "Prefer": "return=minimal"})
    urllib.request.urlopen(req, timeout=30)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry", action="store_true"); a = ap.parse_args()
    stories = fetch_stories()
    files = sorted(glob.glob(os.path.join(EDIT, "BATCH*.mp4")))
    pairs, unmatched = match(files, stories)
    print(f"stories(music_id)={len(stories)}  files={len(files)}  matched={len(pairs)}  unmatched={len(unmatched)}")
    if unmatched: print("UNMATCHED:", unmatched)
    if a.dry:
        for f, s in pairs[:8]:
            print(f"  {s['content_id']}  <-  {os.path.basename(f)[:52]}")
        print("  ... (dry run, nothing uploaded)")
        return
    done = 0
    for f, s in pairs:
        try:
            url = upload(f, s["content_id"]); set_url(s["id"], url); done += 1
            print(f"  [{done}/{len(pairs)}] {s['content_id']}")
        except Exception as e:
            print("FAIL", s["content_id"], str(e)[:80])
    print(f"UPLOADED {done}/{len(pairs)} -> bucket '{BUCKET}', video_url set")

if __name__ == "__main__":
    main()
